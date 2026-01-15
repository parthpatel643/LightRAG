#!/usr/bin/env python3
"""
Upload entire folder contents to an S3 bucket.

This script recursively uploads all files from a local directory to an S3 bucket,
preserving the folder structure.

Usage:
    python upload_to_s3.py --folder <local_folder> --bucket <bucket_name> [--prefix <s3_prefix>]

Example:
    python upload_to_s3.py --folder ./rag_storage --bucket my-lightrag-bucket --prefix backups/2024-01-15/
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("Error: boto3 is not installed. Install it with: pip install boto3")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class S3Uploader:
    """Handle folder uploads to S3 bucket."""

    def __init__(self, bucket_name: str, region_name: Optional[str] = None):
        """
        Initialize S3 uploader.

        Args:
            bucket_name: Name of the S3 bucket
            region_name: AWS region name (optional)
        """
        self.bucket_name = bucket_name
        self.s3_client = boto3.client("s3", region_name=region_name)
        self.uploaded_files = 0
        self.failed_files = 0

    def upload_file(self, local_path: Path, s3_key: str) -> bool:
        """
        Upload a single file to S3.

        Args:
            local_path: Local file path
            s3_key: S3 object key

        Returns:
            True if upload was successful, False otherwise
        """
        try:
            file_size = local_path.stat().st_size
            logger.info(
                f"Uploading {local_path} ({file_size:,} bytes) -> s3://{self.bucket_name}/{s3_key}"
            )

            self.s3_client.upload_file(
                str(local_path),
                self.bucket_name,
                s3_key,
                ExtraArgs={"ContentType": self._get_content_type(local_path)},
            )
            self.uploaded_files += 1
            return True
        except ClientError as e:
            logger.error(f"Failed to upload {local_path}: {e}")
            self.failed_files += 1
            return False
        except Exception as e:
            logger.error(f"Unexpected error uploading {local_path}: {e}")
            self.failed_files += 1
            return False

    def upload_folder(self, folder_path: str, s3_prefix: str = "") -> None:
        """
        Upload entire folder contents to S3.

        Args:
            folder_path: Local folder path to upload
            s3_prefix: Optional S3 key prefix (folder path in bucket)
        """
        folder = Path(folder_path)

        if not folder.exists():
            logger.error(f"Folder does not exist: {folder_path}")
            sys.exit(1)

        if not folder.is_dir():
            logger.error(f"Path is not a directory: {folder_path}")
            sys.exit(1)

        # Ensure prefix ends with / if provided
        if s3_prefix and not s3_prefix.endswith("/"):
            s3_prefix += "/"

        logger.info(
            f"Starting upload from {folder_path} to s3://{self.bucket_name}/{s3_prefix}"
        )
        logger.info("-" * 80)

        # Walk through all files in the folder
        all_files = []
        for root, dirs, files in os.walk(folder):
            for file in files:
                local_path = Path(root) / file
                all_files.append(local_path)

        if not all_files:
            logger.warning(f"No files found in {folder_path}")
            return

        logger.info(f"Found {len(all_files)} files to upload")

        # Upload each file
        for local_path in all_files:
            # Calculate relative path from the base folder
            rel_path = local_path.relative_to(folder)
            s3_key = s3_prefix + str(rel_path).replace(
                "\\", "/"
            )  # Ensure forward slashes

            self.upload_file(local_path, s3_key)

        # Print summary
        logger.info("-" * 80)
        logger.info("Upload complete!")
        logger.info(f"Successfully uploaded: {self.uploaded_files} files")
        if self.failed_files > 0:
            logger.warning(f"Failed uploads: {self.failed_files} files")
        logger.info(f"Destination: s3://{self.bucket_name}/{s3_prefix}")

    def _get_content_type(self, file_path: Path) -> str:
        """
        Determine content type based on file extension.

        Args:
            file_path: Path to the file

        Returns:
            MIME type string
        """
        extension_map = {
            ".txt": "text/plain",
            ".json": "application/json",
            ".csv": "text/csv",
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".xml": "application/xml",
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".zip": "application/zip",
            ".gz": "application/gzip",
            ".log": "text/plain",
            ".md": "text/markdown",
        }

        suffix = file_path.suffix.lower()
        return extension_map.get(suffix, "application/octet-stream")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Upload folder contents to S3 bucket",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload rag_storage folder to bucket root
  python upload_to_s3.py --folder ./rag_storage --bucket my-lightrag-bucket

  # Upload with S3 prefix (folder path in bucket)
  python upload_to_s3.py --folder ./rag_storage --bucket my-bucket --prefix backups/2024-01-15/

  # Upload from inputs folder to specific region
  python upload_to_s3.py --folder ./inputs --bucket my-bucket --region us-west-2

Environment Variables:
  AWS_ACCESS_KEY_ID     - AWS access key
  AWS_SECRET_ACCESS_KEY - AWS secret key
  AWS_DEFAULT_REGION    - Default AWS region
        """,
    )

    parser.add_argument(
        "--folder",
        required=True,
        help="Local folder path to upload",
    )
    parser.add_argument(
        "--bucket",
        required=True,
        help="S3 bucket name",
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="S3 key prefix (folder path in bucket, e.g., 'backups/2024-01-15/')",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region name (optional, uses default from AWS config if not specified)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        uploader = S3Uploader(bucket_name=args.bucket, region_name=args.region)
        uploader.upload_folder(folder_path=args.folder, s3_prefix=args.prefix)

        # Exit with error code if any uploads failed
        if uploader.failed_files > 0:
            sys.exit(1)

    except NoCredentialsError:
        logger.error("AWS credentials not found. Please configure AWS credentials:")
        logger.error(
            "  - Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables"
        )
        logger.error("  - Or configure using 'aws configure' command")
        logger.error("  - Or use IAM role (when running on AWS)")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
