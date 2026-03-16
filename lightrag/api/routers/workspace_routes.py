"""
Workspace Management API Routes

Provides endpoints for managing multiple workspaces with different
working directories and input directories.
"""

import os
from pathlib import Path
from typing import List, Optional, Callable

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
    global _rag_instance, _reload_rag_func
    _rag_instance = rag
    _reload_rag_func = reload_func
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
        # Validate directories exist or can be created
        working_path = Path(config.working_dir)
        input_path = Path(config.input_dir)

        # Create directories if they don't exist
        working_path.mkdir(parents=True, exist_ok=True)
        input_path.mkdir(parents=True, exist_ok=True)

        # Update environment variables
        os.environ["WORKING_DIR"] = config.working_dir
        os.environ["INPUT_DIR"] = config.input_dir
        os.environ["WORKSPACE_NAME"] = config.name

        # Update current workspace
        _current_workspace = config

        # Reload RAG instance if reload function is available
        if _reload_rag_func:
            try:
                logger.info(
                    f"Reloading RAG instance for workspace: {config.name}"
                )
                await _reload_rag_func(
                    working_dir=config.working_dir, workspace=config.name
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
        logger.info(f"  Working dir: {config.working_dir}")
        logger.info(f"  Input dir: {config.input_dir}")

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
    """
    try:
        working_dir = os.getenv("WORKING_DIR", "./rag_storage")
        working_path = Path(working_dir)

        workspaces = []
        discovered_workspace_names = set()

        # Discover workspaces from subdirectories in WORKING_DIR
        if working_path.exists() and working_path.is_dir():
            for item in working_path.iterdir():
                if item.is_dir():
                    workspace_name = item.name
                    discovered_workspace_names.add(workspace_name)

                    # Try to detect input dir relative to workspace
                    # Convention: input_dir in parent's INPUT_DIR or workspace-specific inputs
                    input_base = os.getenv("INPUT_DIR", "./inputs")
                    workspace_input_dir = os.path.join(input_base, workspace_name)

                    workspace_config = WorkspaceConfig(
                        name=workspace_name,
                        working_dir=str(item),
                        input_dir=workspace_input_dir,
                        description=f"Workspace: {workspace_name}",
                    )
                    workspaces.append(workspace_config)

        # Always include default workspace if not already discovered
        if "default" not in discovered_workspace_names:
            default_workspace = WorkspaceConfig(
                name="default",
                working_dir=working_dir,
                input_dir=os.getenv("INPUT_DIR", "./inputs"),
                description="Default workspace",
            )
            workspaces.append(default_workspace)

        # Sort by name for consistent ordering
        workspaces.sort(key=lambda w: w.name)

        logger.debug(
            f"Discovered {len(workspaces)} workspaces from {working_dir}: "
            f"{[w.name for w in workspaces]}"
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
