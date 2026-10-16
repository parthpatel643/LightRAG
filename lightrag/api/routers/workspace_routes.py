"""
Workspace Management API Routes

Provides endpoints for managing multiple workspaces with different
working directories and input directories.
"""

import asyncio
import os
from pathlib import Path
from typing import Callable, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lightrag.api.utils_api import get_combined_auth_dependency
from lightrag.utils import logger

# The handlers below carry no auth of their own: use create_workspace_routes(),
# which wraps them in the server's combined authentication dependency. (They
# used to take ``Depends(get_combined_auth_dependency)``, which hands FastAPI
# the dependency *factory* instead of a dependency, so nothing was enforced.)
_router = APIRouter(prefix="/workspace", tags=["workspace"])


def create_workspace_routes(api_key: Optional[str] = None) -> APIRouter:
    """Workspace management router, protected like every other API router."""
    secured = APIRouter(dependencies=[Depends(get_combined_auth_dependency(api_key))])
    secured.include_router(_router)
    return secured

# A workspace name becomes a directory name and a storage prefix.
_WORKSPACE_NAME_PATTERN = r"^[A-Za-z0-9_]{1,64}$"

# Serialises switches: the switch rewires the one shared LightRAG instance.
_switch_lock = asyncio.Lock()


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class WorkspaceConfig(BaseModel):
    """Workspace configuration model"""

    name: str = Field(
        ..., pattern=_WORKSPACE_NAME_PATTERN, description="Unique workspace name"
    )
    working_dir: str = Field(..., description="Directory where RAG data is stored")
    input_dir: str = Field(
        ..., description="Directory where source documents are located"
    )
    description: Optional[str] = Field(
        None, description="Optional workspace description"
    )


class WorkspaceResponse(BaseModel):
    """Workspace response model"""

    status: str
    message: str
    workspace: Optional[WorkspaceConfig] = None


# Global variable to track current workspace
# In production, this should be stored in a database or session
_current_workspace: Optional[WorkspaceConfig] = None
_rag_instance = None
_reload_rag_func: Optional[Callable] = None
# Store the root working directory for workspace discovery (don't change this when switching workspaces)
_root_working_dir: Optional[str] = None
_root_input_dir: Optional[str] = None


def get_current_workspace_config() -> WorkspaceConfig:
    """Get the current workspace configuration"""
    global _current_workspace

    if _current_workspace is None:
        # Initialize with default workspace: what the running instance serves,
        # else the environment.
        _current_workspace = WorkspaceConfig(
            name=(getattr(_rag_instance, "workspace", "") or "")
            or os.getenv("WORKSPACE_NAME", "default"),
            working_dir=os.getenv("WORKING_DIR", "./rag_storage"),
            input_dir=os.getenv("INPUT_DIR", "./inputs"),
            description="Default workspace",
        )

    return _current_workspace


def set_rag_instance_and_reload_func(rag, reload_func: Callable):
    """
    Set the RAG instance and reload function for workspace switching.

    Args:
        rag: LightRAG instance
        reload_func: Async function to reload RAG with new workspace
    """
    global _rag_instance, _reload_rag_func, _root_working_dir, _root_input_dir
    _rag_instance = rag
    _reload_rag_func = reload_func

    # Store the root working directory on first initialization
    if _root_working_dir is None:
        _root_working_dir = os.getenv("WORKING_DIR", "./rag_storage")
        _root_input_dir = os.getenv("INPUT_DIR", "./inputs")
        logger.debug(f"Initialized root working directory: {_root_working_dir}")

    logger.debug("RAG instance and reload function registered for workspace management")


def _input_root() -> Path:
    """Directory holding every workspace's input folder. A workspace-specific
    INPUT_DIR (``inputs/<WORKSPACE>``) contributes its parent, which is where
    /workspace/list places the other workspaces' input directories."""
    root = Path(_root_input_dir or os.getenv("INPUT_DIR", "./inputs"))
    workspace = os.getenv("WORKSPACE") or os.getenv("WORKSPACE_NAME", "")
    if workspace and root.name == workspace:
        return root.parent
    return root


def _validated_dirs(config: WorkspaceConfig) -> tuple[Path, Path]:
    """Return the requested directories after checking they sit under the
    configured root directories; anything else is refused instead of created."""
    root_working = Path(_root_working_dir or os.getenv("WORKING_DIR", "./rag_storage"))
    root_input = _input_root()
    working_path = Path(config.working_dir)
    input_path = Path(config.input_dir)
    if not _within(working_path, root_working) or not _within(input_path, root_input):
        raise HTTPException(
            status_code=400,
            detail="working_dir and input_dir must be inside the server's "
            "WORKING_DIR and INPUT_DIR",
        )
    return working_path, input_path


async def _ensure_pipeline_idle() -> None:
    """Refuse a switch while documents are being processed (best effort)."""
    if _rag_instance is None:
        return
    from lightrag.kg.shared_storage import get_namespace_data

    status = await get_namespace_data(
        "pipeline_status", workspace=getattr(_rag_instance, "workspace", "")
    )
    if status.get("busy"):
        raise HTTPException(
            status_code=409,
            detail="The document pipeline is busy; switch workspaces when it is idle.",
        )


@_router.post("/switch", response_model=WorkspaceResponse)
async def switch_workspace(config: WorkspaceConfig):
    """
    Switch to a different workspace configuration.

    This updates the working directory and input directory for the LightRAG instance
    and reloads all storage backends to load data from the new workspace. The one
    LightRAG instance is shared by every client, so the switch is serialised and
    refused while the pipeline is busy.
    """
    global _current_workspace

    async with _switch_lock:
        try:
            await _ensure_pipeline_idle()

            # Use cached root directories for storage isolation.
            # Storage backends already incorporate `workspace` into their on-disk paths,
            # so passing a workspace-specific working_dir would create nested paths like
            # <root>/<workspace>/<workspace>/..., resulting in stale/empty data.
            global _root_working_dir, _root_input_dir
            root_working_dir = _root_working_dir or os.getenv(
                "WORKING_DIR", "./rag_storage"
            )
            root_input_dir = _root_input_dir or os.getenv("INPUT_DIR", "./inputs")

            # Only directories under the configured roots may be created.
            working_path, input_path = _validated_dirs(config)
            working_path.mkdir(parents=True, exist_ok=True)
            input_path.mkdir(parents=True, exist_ok=True)

            # Keep WORKING_DIR/INPUT_DIR pointing at ROOT dirs; workspace name determines isolation.
            os.environ["WORKING_DIR"] = root_working_dir
            os.environ["INPUT_DIR"] = root_input_dir
            os.environ["WORKSPACE_NAME"] = config.name

            # Reload RAG instance if reload function is available
            if _reload_rag_func:
                try:
                    logger.info(f"Reloading RAG instance for workspace: {config.name}")
                    await _reload_rag_func(
                        working_dir=root_working_dir, workspace=config.name
                    )
                    logger.info(
                        f"Successfully reloaded RAG instance for workspace: {config.name}"
                    )
                except Exception as reload_error:
                    logger.error(
                        f"Failed to reload RAG instance for workspace {config.name}: {reload_error}"
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to reload RAG for workspace: {str(reload_error)}",
                    )
            else:
                logger.warning(
                    "Reload function not available. Workspace switching may not properly load graph data."
                )

            # Only now is the switch real; recording it earlier left the
            # reported workspace ahead of the loaded one when the reload failed.
            _current_workspace = config

            logger.info(f"Switched to workspace: {config.name}")
            logger.info(f"  Root working dir: {root_working_dir}")
            logger.info(f"  Root input dir: {root_input_dir}")

            return WorkspaceResponse(
                status="success",
                message=f"Switched to workspace: {config.name}",
                workspace=config,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to switch workspace: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to switch workspace: {str(e)}"
            )


@_router.get("/current", response_model=WorkspaceConfig)
async def get_current_workspace():
    """
    Get the current workspace configuration.
    """
    try:
        config = get_current_workspace_config()
        return config
    except Exception as e:
        logger.error(f"Failed to get current workspace: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get current workspace: {str(e)}"
        )


@_router.get("/list", response_model=List[WorkspaceConfig])
async def list_workspaces():
    """
    List all available workspaces discovered from WORKING_DIR.

    Scans the WORKING_DIR for workspace subdirectories and returns their configurations.
    If no subdirectories exist, returns the root workspace based on WORKING_DIR.
    The first workspace in the returned list is considered the default.
    """
    try:
        # Use root working directory for discovery, not the current workspace directory
        # This ensures all workspaces are discovered even after switching
        global _root_working_dir, _root_input_dir

        # If root directories not initialized, use environment variables
        working_dir = _root_working_dir or os.getenv("WORKING_DIR", "./rag_storage")
        input_dir = _root_input_dir or os.getenv("INPUT_DIR", "./inputs")

        # Check both WORKSPACE and WORKSPACE_NAME for compatibility
        workspace_name = os.getenv("WORKSPACE") or os.getenv(
            "WORKSPACE_NAME", "default"
        )
        working_path = Path(working_dir)

        workspaces = []

        # Discover workspace names from subdirectories in the ROOT working dir.
        # IMPORTANT: returned `working_dir` should remain the ROOT directory.
        # Storage backends already incorporate workspace into paths.
        if working_path.exists() and working_path.is_dir():
            for item in working_path.iterdir():
                if item.is_dir():
                    try:
                        subdir_name = item.name

                        # Skip hidden directories (starting with .)
                        if subdir_name.startswith("."):
                            continue

                        # Try to detect input dir relative to workspace
                        # If root input_dir is workspace-specific (from env), extract parent directory
                        # Otherwise use root input_dir as the base
                        input_path = Path(input_dir)

                        if input_path.is_absolute() and workspace_name in str(
                            input_path
                        ):
                            # Root INPUT_DIR is workspace-specific, use parent as base for all workspaces
                            input_parent = input_path.parent
                            workspace_input_dir = str(input_parent / subdir_name)
                        else:
                            # INPUT_DIR is generic or relative, join with workspace name
                            workspace_input_dir = os.path.join(input_dir, subdir_name)

                        workspace_config = WorkspaceConfig(
                            name=subdir_name,
                            working_dir=str(working_path),
                            input_dir=workspace_input_dir,
                            description=f"Workspace: {subdir_name}",
                        )
                        workspaces.append(workspace_config)
                        logger.debug(f"Discovered workspace: {subdir_name}")
                    except Exception as item_error:
                        logger.warning(
                            f"Failed to process workspace directory {item.name}: {item_error}"
                        )
                        continue

        # If no subdirectory workspaces found, return the root workspace as configured
        if not workspaces:
            root_workspace = WorkspaceConfig(
                name=workspace_name,
                working_dir=working_dir,
                input_dir=input_dir,
                description=f"Main workspace: {workspace_name}",
            )
            workspaces.append(root_workspace)
        else:
            # Sort discovered workspaces by name - first one becomes the default
            workspaces.sort(key=lambda w: w.name)

        logger.debug(
            f"Discovered {len(workspaces)} workspaces from {working_dir}: "
            f"{[w.name for w in workspaces]}"
        )

        if len(workspaces) == 0:
            logger.warning(
                f"No workspace subdirectories found in {working_dir}, returning root workspace"
            )

        return workspaces

    except Exception as e:
        logger.error(f"Failed to list workspaces: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list workspaces: {str(e)}"
        )


@_router.post("/create", response_model=WorkspaceResponse)
async def create_workspace(config: WorkspaceConfig):
    """
    Create a new workspace.

    This creates the necessary directories for the workspace.
    """
    try:
        # Only directories under the configured roots may be created.
        working_path, input_path = _validated_dirs(config)

        # Check if directories already exist
        if working_path.exists() and any(working_path.iterdir()):
            logger.warning(
                f"Working directory already exists and is not empty: {config.working_dir}"
            )

        # Create directories
        working_path.mkdir(parents=True, exist_ok=True)
        input_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Created workspace: {config.name}")
        logger.info(f"  Working dir: {config.working_dir}")
        logger.info(f"  Input dir: {config.input_dir}")

        return WorkspaceResponse(
            status="success",
            message=f"Workspace created: {config.name}",
            workspace=config,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create workspace: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create workspace: {str(e)}"
        )


# Made with Bob
