#!/usr/bin/env python3
"""
S3-to-Cloud Delta Sync Batch Script

Monitors an SQS queue for S3 change notifications and runs delta migration
to push workspace data to cloud storages (MongoDB, Milvus, Neptune, OpenSearch).

Execution model: One-shot batch job. Run once, drain SQS messages, process
changed workspaces, exit.

Flow:
    1. Poll SQS queue (drain all available messages, up to MAX_MESSAGES)
    2. Parse S3 event notifications to extract affected workspace names (deduplicate)
    3. For each changed workspace:
       a. Download the full workspace folder from S3 to a temp directory
       b. Run do_delta() (reused from migrate_storage.py) against the temp workspace
       c. Clean up temp directory
    4. Delete successfully processed SQS messages
    5. Exit with success/failure status

Required environment variables:
    SQS_QUEUE_URL       - URL of the SQS queue receiving S3 notifications
    S3_BUCKET           - S3 bucket name (fallback; bucket is also in SQS messages)
    S3_PREFIX           - Prefix under which workspace folders live
    AWS_REGION          - AWS region (default: us-east-1)
    MAX_MESSAGES        - Max messages to drain per run (default: 100)
    BATCH_SIZE          - Batch size for cloud upsert operations (default: 500)
    SKIP_CACHE          - Skip llm_response_cache namespace (default: true)
    DELETE_ORPHANS      - Whether to delete orphaned cloud records (default: true)
    DRY_RUN             - Report what would happen without touching cloud (default: false)

    Plus all existing migrate_storage.py env vars (MONGO_URI, MILVUS_URI, etc.)

Usage:
    python s3_sync_pipeline.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("s3_sync_pipeline")

# ---------------------------------------------------------------------------
# Import delta sync logic from migrate_storage
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from migrate_storage import KV_NAMESPACES, do_delta  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def _env_bool(key: str, default: str = "false") -> bool:
    return os.environ.get(key, default).lower() in ("true", "1", "yes")


@dataclass
class Config:
    sqs_queue_url: str = field(default_factory=lambda: os.environ.get("SQS_QUEUE_URL", ""))
    s3_bucket: str = field(default_factory=lambda: os.environ.get("S3_BUCKET", ""))
    s3_prefix: str = field(default_factory=lambda: os.environ.get("S3_PREFIX", ""))
    aws_region: str = field(default_factory=lambda: os.environ.get("AWS_REGION", "us-east-1"))
    max_messages: int = field(default_factory=lambda: int(os.environ.get("MAX_MESSAGES", "100")))
    batch_size: int = field(default_factory=lambda: int(os.environ.get("BATCH_SIZE", "500")))
    skip_cache: bool = field(default_factory=lambda: _env_bool("SKIP_CACHE", "true"))
    delete_orphans: bool = field(default_factory=lambda: _env_bool("DELETE_ORPHANS", "true"))
    dry_run: bool = field(default_factory=lambda: _env_bool("DRY_RUN", "false"))

    def validate(self):
        if not self.sqs_queue_url:
            raise ValueError("SQS_QUEUE_URL environment variable is required")
        if not self.s3_bucket:
            raise ValueError("S3_BUCKET environment variable is required")


# ---------------------------------------------------------------------------
# SQS Event Processor
# ---------------------------------------------------------------------------
class SQSEventProcessor:
    """Poll SQS, parse S3 event notifications, deduplicate by workspace."""

    def __init__(self, config: Config):
        self.config = config
        self.sqs = boto3.client("sqs", region_name=config.aws_region)

    def drain_messages(self) -> list[dict]:
        """Drain all available messages from SQS up to max_messages.

        Returns list of raw SQS message dicts (with Body, ReceiptHandle, etc.).
        """
        messages: list[dict] = []
        remaining = self.config.max_messages

        while remaining > 0:
            # SQS allows max 10 messages per receive call
            batch_size = min(remaining, 10)
            response = self.sqs.receive_message(
                QueueUrl=self.config.sqs_queue_url,
                MaxNumberOfMessages=batch_size,
                WaitTimeSeconds=20,  # Long poll
                AttributeNames=["All"],
            )

            batch = response.get("Messages", [])
            if not batch:
                break

            messages.extend(batch)
            remaining -= len(batch)

            # If we got fewer than requested, queue is likely empty
            if len(batch) < batch_size:
                break

        logger.info("Drained %d messages from SQS", len(messages))
        return messages

    def extract_workspaces(
        self, messages: list[dict]
    ) -> dict[str, list[str]]:
        """Parse S3 event notifications and extract workspace names.

        Returns {workspace_name: [receipt_handle, ...]} mapping.
        Deduplicates by workspace name.
        """
        workspace_receipts: dict[str, list[str]] = {}
        prefix = self.config.s3_prefix.strip("/")

        for msg in messages:
            receipt_handle = msg["ReceiptHandle"]
            body = msg.get("Body", "")

            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                logger.warning("Skipping non-JSON SQS message: %s", msg.get("MessageId"))
                continue

            # Handle SNS-wrapped messages (S3 -> SNS -> SQS)
            if "Message" in payload and isinstance(payload.get("Message"), str):
                try:
                    payload = json.loads(payload["Message"])
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed SNS message payload")
                    continue

            records = payload.get("Records", [])
            if not records:
                # Some S3 test events have no Records
                logger.debug("Message %s has no Records, skipping", msg.get("MessageId"))
                # Still track for deletion since it's not a real event
                workspace_receipts.setdefault("__no_workspace__", []).append(receipt_handle)
                continue

            for record in records:
                s3_info = record.get("s3", {})
                obj_key = s3_info.get("object", {}).get("key", "")

                if not obj_key:
                    continue

                # Strip prefix and extract workspace name
                workspace = self._extract_workspace(obj_key, prefix)
                if workspace:
                    workspace_receipts.setdefault(workspace, []).append(receipt_handle)
                else:
                    logger.debug(
                        "Could not extract workspace from key: %s", obj_key
                    )

        # Remove the placeholder for non-workspace messages
        no_ws_receipts = workspace_receipts.pop("__no_workspace__", [])
        if no_ws_receipts:
            logger.info(
                "Found %d messages with no workspace (test events), will delete after processing",
                len(no_ws_receipts),
            )
            # Store these so we can delete them
            workspace_receipts["__no_workspace__"] = no_ws_receipts

        real_workspaces = {
            k for k in workspace_receipts if k != "__no_workspace__"
        }
        logger.info(
            "Extracted %d unique workspace(s): %s",
            len(real_workspaces),
            ", ".join(sorted(real_workspaces)) if real_workspaces else "(none)",
        )
        return workspace_receipts

    def delete_messages(self, receipt_handles: list[str]):
        """Delete processed messages from SQS in batches of 10."""
        # Deduplicate receipt handles
        unique_handles = list(set(receipt_handles))

        for i in range(0, len(unique_handles), 10):
            batch = unique_handles[i : i + 10]
            entries = [
                {"Id": str(idx), "ReceiptHandle": handle}
                for idx, handle in enumerate(batch)
            ]
            response = self.sqs.delete_message_batch(
                QueueUrl=self.config.sqs_queue_url, Entries=entries
            )
            failed = response.get("Failed", [])
            if failed:
                logger.warning(
                    "Failed to delete %d SQS messages: %s",
                    len(failed),
                    [f["Code"] for f in failed],
                )

    @staticmethod
    def _extract_workspace(obj_key: str, prefix: str) -> str | None:
        """Extract workspace name from S3 object key.

        Key structure: <prefix>/<workspace_name>/<file>
        """
        # Normalize: ensure prefix doesn't have leading/trailing slashes for comparison
        if prefix:
            # Strip the prefix from the key
            if obj_key.startswith(prefix + "/"):
                relative = obj_key[len(prefix) + 1 :]
            elif obj_key.startswith(prefix):
                relative = obj_key[len(prefix) :]
            else:
                return None
        else:
            relative = obj_key

        # Remove leading slash if any
        relative = relative.lstrip("/")

        # First segment is the workspace name
        parts = relative.split("/", 1)
        if parts and parts[0]:
            return parts[0]
        return None


# ---------------------------------------------------------------------------
# S3 Workspace Downloader
# ---------------------------------------------------------------------------
class S3WorkspaceDownloader:
    """Download workspace files from S3 to a temp directory."""

    def __init__(self, config: Config):
        self.config = config
        self.s3 = boto3.client("s3", region_name=config.aws_region)

    def download_workspace(self, workspace: str, dest_dir: Path) -> bool:
        """Download all files for a workspace from S3 to dest_dir.

        Returns True if files were downloaded, False if workspace is empty.
        """
        prefix = self.config.s3_prefix.strip("/")
        if prefix:
            s3_workspace_prefix = f"{prefix}/{workspace}/"
        else:
            s3_workspace_prefix = f"{workspace}/"

        logger.info(
            "Downloading workspace '%s' from s3://%s/%s",
            workspace,
            self.config.s3_bucket,
            s3_workspace_prefix,
        )

        paginator = self.s3.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(
            Bucket=self.config.s3_bucket, Prefix=s3_workspace_prefix
        )

        file_count = 0
        for page in page_iterator:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # Compute relative path within the workspace
                relative_path = key[len(s3_workspace_prefix) :]
                if not relative_path:
                    continue  # Skip the directory marker itself

                local_path = dest_dir / relative_path
                local_path.parent.mkdir(parents=True, exist_ok=True)

                self.s3.download_file(self.config.s3_bucket, key, str(local_path))
                file_count += 1

        if file_count == 0:
            logger.warning("No files found for workspace '%s' in S3", workspace)
            return False

        logger.info("Downloaded %d files for workspace '%s'", file_count, workspace)
        return True


# ---------------------------------------------------------------------------
# Workspace processing
# ---------------------------------------------------------------------------
async def process_workspace(
    workspace: str,
    downloader: S3WorkspaceDownloader,
    config: Config,
) -> bool:
    """Download workspace from S3 and run delta sync.

    Returns True on success, False on failure.
    """
    temp_dir = None
    try:
        # Create temp directory for workspace files
        temp_dir = Path(tempfile.mkdtemp(prefix=f"s3sync_{workspace}_"))
        logger.info("Processing workspace '%s' (temp: %s)", workspace, temp_dir)

        # Download workspace files from S3
        has_files = downloader.download_workspace(workspace, temp_dir)
        if not has_files:
            logger.warning(
                "Workspace '%s' has no files in S3, skipping delta sync", workspace
            )
            return True  # Not an error, just empty

        # Run delta sync
        await do_delta(
            workspace_dir=temp_dir,
            workspace=workspace,
            batch_size=config.batch_size,
            dry_run=config.dry_run,
            delete_orphans=config.delete_orphans,
        )

        logger.info("Successfully processed workspace '%s'", workspace)
        return True

    except Exception as e:
        logger.error("Failed to process workspace '%s': %s", workspace, e, exc_info=True)
        return False

    finally:
        # Clean up temp directory
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug("Cleaned up temp dir: %s", temp_dir)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    config = Config()

    try:
        config.validate()
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("S3-to-Cloud Delta Sync Pipeline")
    logger.info("=" * 60)
    logger.info("SQS Queue   : %s", config.sqs_queue_url)
    logger.info("S3 Bucket   : %s", config.s3_bucket)
    logger.info("S3 Prefix   : %s", config.s3_prefix)
    logger.info("AWS Region  : %s", config.aws_region)
    logger.info("Max Messages: %d", config.max_messages)
    logger.info("Batch Size  : %d", config.batch_size)
    logger.info("Skip Cache  : %s", config.skip_cache)
    logger.info("Delete Orphans: %s", config.delete_orphans)
    logger.info("Dry Run     : %s", config.dry_run)
    logger.info("=" * 60)

    # Apply skip_cache setting globally
    if config.skip_cache:
        import migrate_storage

        migrate_storage.KV_NAMESPACES = [
            ns for ns in migrate_storage.KV_NAMESPACES if ns != "llm_response_cache"
        ]
        logger.info("Skipping llm_response_cache namespace")

    # Step 1: Drain SQS messages
    sqs_processor = SQSEventProcessor(config)
    messages = sqs_processor.drain_messages()

    if not messages:
        logger.info("No messages in SQS queue. Nothing to do.")
        sys.exit(0)

    # Step 2: Parse and deduplicate workspaces
    workspace_receipts = sqs_processor.extract_workspaces(messages)

    # Separate real workspaces from no-workspace messages
    no_ws_receipts = workspace_receipts.pop("__no_workspace__", [])
    real_workspaces = sorted(workspace_receipts.keys())

    if not real_workspaces:
        logger.info("No workspaces identified from SQS messages.")
        # Delete non-workspace messages (test events) since they're processed
        if no_ws_receipts:
            sqs_processor.delete_messages(no_ws_receipts)
        sys.exit(0)

    # Step 3: Process each workspace
    downloader = S3WorkspaceDownloader(config)
    success_receipts: list[str] = []
    failure_count = 0

    for workspace in real_workspaces:
        ok = await process_workspace(workspace, downloader, config)
        if ok:
            success_receipts.extend(workspace_receipts[workspace])
        else:
            failure_count += 1
            # Leave failed workspace messages in the queue
            # (they'll become visible again after visibility timeout)
            logger.warning(
                "Leaving %d messages for failed workspace '%s' in queue",
                len(workspace_receipts[workspace]),
                workspace,
            )

    # Step 4: Delete successfully processed messages
    all_delete_receipts = success_receipts + no_ws_receipts
    if all_delete_receipts:
        logger.info("Deleting %d processed SQS messages", len(all_delete_receipts))
        sqs_processor.delete_messages(all_delete_receipts)

    # Step 5: Report and exit
    logger.info("=" * 60)
    logger.info("Pipeline complete.")
    logger.info(
        "  Workspaces processed: %d success, %d failed",
        len(real_workspaces) - failure_count,
        failure_count,
    )
    logger.info("  SQS messages deleted: %d", len(all_delete_receipts))
    logger.info("=" * 60)

    if failure_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
