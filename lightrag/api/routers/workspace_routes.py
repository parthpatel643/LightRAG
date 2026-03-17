"""
Workspace Management API Routes

Provides endpoints for managing multiple workspaces with different
working directories and input directories.
"""

import os
from pathlib import Path
from typing import Callable, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lightrag.api.utils_api import get_combined_auth_dependency
from lightrag.utils import logger

router = APIRouter(prefix="/workspace", tags=["workspace"])


class WorkspaceConfig(BaseModel):
    """Workspace configuration model"""

    name: str = Field(..., description="Unique workspace name")
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
        # Initialize with default workspace from environment
        _current_workspace = WorkspaceConfig(
            name=os.getenv("WORKSPACE_NAME", "default"),
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


@router.post("/switch", response_model=WorkspaceResponse)
async def switch_workspace(
    config: WorkspaceConfig, _auth=Depends(get_combined_auth_dependency)
):
    """
    Switch to a different workspace configuration.

    This updates the working directory and input directory for the LightRAG instance
    and reloads all storage backends to load data from the new workspace.
    """
    global _current_workspace

    try:
        # Use cached root directories for storage isolation.
        # Storage backends already incorporate `workspace` into their on-disk paths,
        # so passing a workspace-specific working_dir would create nested paths like
        # <root>/<workspace>/<workspace>/..., resulting in stale/empty data.
        global _root_working_dir, _root_input_dir
        root_working_dir = _root_working_dir or os.getenv("WORKING_DIR", "./rag_storage")
        root_input_dir = _root_input_dir or os.getenv("INPUT_DIR", "./inputs")

        # Validate directories exist or can be created
        # Note: We still create the directories referenced by the requested config
        # so existing clients relying on these paths won't break.
        working_path = Path(config.working_dir)
        input_path = Path(config.input_dir)

        # Create directories if they don't exist
        working_path.mkdir(parents=True, exist_ok=True)
        input_path.mkdir(parents=True, exist_ok=True)

        # Update environment variables.
        # Keep WORKING_DIR/INPUT_DIR pointing at ROOT dirs; workspace name determines isolation.
        os.environ["WORKING_DIR"] = root_working_dir
        os.environ["INPUT_DIR"] = root_input_dir
        os.environ["WORKSPACE_NAME"] = config.name

        # Update current workspace
        _current_workspace = config

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

        logger.info(f"Switched to workspace: {config.name}")
        logger.info(f"  Root working dir: {root_working_dir}")
        logger.info(f"  Root input dir: {root_input_dir}")
        logger.info(f"  Requested working dir: {config.working_dir}")
        logger.info(f"  Requested input dir: {config.input_dir}")

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


@router.get("/current", response_model=WorkspaceConfig)
async def get_current_workspace(_auth=Depends(get_combined_auth_dependency)):
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


@router.get("/list", response_model=List[WorkspaceConfig])
async def list_workspaces(_auth=Depends(get_combined_auth_dependency)):
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
                        if subdir_name.startswith('.'):
                            continue

                        # Try to detect input dir relative to workspace
                        # If root input_dir is workspace-specific (from env), extract parent directory
                        # Otherwise use root input_dir as the base
                        input_path = Path(input_dir)
                        
                        if input_path.is_absolute() and workspace_name in str(input_path):
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
                        logger.warning(f"Failed to process workspace directory {item.name}: {item_error}")
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


@router.post("/create", response_model=WorkspaceResponse)
async def create_workspace(
    config: WorkspaceConfig, _auth=Depends(get_combined_auth_dependency)
):
    """
    Create a new workspace.

    This creates the necessary directories for the workspace.
    """
    try:
        # Validate and create directories
        working_path = Path(config.working_dir)
        input_path = Path(config.input_dir)

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

    except Exception as e:
        logger.error(f"Failed to create workspace: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create workspace: {str(e)}"
        )


# Made with Bob
