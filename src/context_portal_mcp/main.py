# pylint: disable=too-many-lines,too-many-arguments,too-many-positional-arguments,too-many-statements,import-outside-toplevel
"""
ConPort MCP Server Main Module.
"""
import argparse
import logging.handlers
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, AsyncIterator, Dict, List, Optional, Union

import uvicorn
from fastapi import FastAPI
from fastmcp import Context, FastMCP
from pydantic import Field

# Local imports
try:
    from .handlers import mcp_handlers  # We will adapt these
    from .db import database, models  # models for tool argument types
    from .core import exceptions  # For custom exceptions if FastMCP doesn't map them
    from .core.workspace_detector import (
        resolve_workspace_id,
        WorkspaceDetector
    )  # Import workspace detection
except ImportError:
    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..')
    ))
    from src.context_portal_mcp.handlers import mcp_handlers
    from src.context_portal_mcp.db import database, models
    from src.context_portal_mcp.core import exceptions
    from src.context_portal_mcp.core.workspace_detector import (
        resolve_workspace_id,
        WorkspaceDetector
    )

log = logging.getLogger(__name__)

def setup_logging(args: argparse.Namespace):
    """Configures logging based on command-line arguments."""
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    root_logger = logging.getLogger()
    # Clear any existing handlers to avoid duplicates
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.setLevel(getattr(logging, args.log_level.upper()))

    # Add file handler if specified and workspace_id is available
    if args.log_file and args.workspace_id:
        try:
            log_file_path = args.log_file
            if not os.path.isabs(log_file_path):
                # This is a bit of a chicken-and-egg problem. We need the config to know
                # the base path, but the config isn't fully set up yet. We can read the
                # args directly.
                if args.base_path:
                    base_path = Path(args.base_path).expanduser()
                    sanitized_workspace_id = args.workspace_id.replace(
                        '/', '_'
                    ).replace('\\', '_')
                    log_dir = base_path / sanitized_workspace_id / "logs"
                    log_file_path = log_dir / os.path.basename(args.log_file)
                else:
                    base_path = args.workspace_id
                    log_file_path = os.path.join(base_path, "context_portal", log_file_path)

            log_dir = os.path.dirname(log_file_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                log_file_path,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5
            )
            file_handler.setFormatter(logging.Formatter(log_format))
            root_logger.addHandler(file_handler)
            log.info("File logging configured to: %s", log_file_path)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Use a temporary basic config to log this error
            logging.basicConfig()
            log.error("Failed to set up file logging to %s: %s", args.log_file, e)
    elif args.log_file:
        log.warning(
            "Log file '%s' requested, but no --workspace_id provided at startup. "
            "File logging will be deferred.",
            args.log_file
        )

    # Only add console handler if not in stdio mode
    if args.mode != "stdio":
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(logging.Formatter(log_format))
        root_logger.addHandler(console_handler)
        log.info("Console logging configured.")

# --- Lifespan Management for FastMCP ---
@asynccontextmanager
async def conport_lifespan(_server: FastMCP) -> AsyncIterator[None]:
    """Manage application lifecycle for ConPort."""
    # server is required by FastMCP lifespan signature
    log.info("ConPort FastMCP server lifespan starting.")
    # Database initialization is handled by get_db_connection on first access per workspace.
    # No explicit global startup needed for DB here unless we want to pre-connect to a default.
    try:
        yield None  # Server runs
    finally:
        log.info("ConPort FastMCP server lifespan shutting down. Closing all DB connections.")
        database.close_all_connections()

# --- FastMCP Server Instance ---
# Version from pyproject.toml would be ideal here, or define centrally
CONPORT_VERSION = "0.3.10"

conport_mcp = FastMCP(
    name="ConPort", # Pass name directly
    lifespan=conport_lifespan
)

# --- FastAPI App ---
# The FastAPI app will be the main ASGI app, and FastMCP will be mounted onto it.
# We keep our own FastAPI app instance in case we want to add other non-MCP HTTP endpoints later.
app = FastAPI(title="ConPort MCP Server Wrapper", version=CONPORT_VERSION)

# --- Adapt and Register Tools with FastMCP ---
# We use our Pydantic models as input_schema for robust validation.

@conport_mcp.tool(
    name="get_product_context",
    description="Retrieves the overall project goals, features, and architecture."
)
async def tool_get_product_context(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )]
) -> Dict[str, Any]:
    """
    Retrieves the product context for the specified workspace.

    Args:
        workspace_id: The identifier for the workspace.

    Returns:
        A dictionary containing the product context.
    """
    try:
        # Construct the Pydantic model for the handler
        pydantic_args = models.GetContextArgs(workspace_id=workspace_id)
        return mcp_handlers.handle_get_product_context(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in get_product_context handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for get_product_context: %s. Received workspace_id: %s",
            e, workspace_id
        )
        raise exceptions.ContextPortalError(
            f"Server error processing get_product_context: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="update_product_context",
    description="Updates the product context. Accepts full `content` (object) or "
                "`patch_content` (object) for partial updates "
                "(use `__DELETE__` as a value in patch to remove a key)."
)
async def tool_update_product_context(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    content: Annotated[Optional[Dict[str, Any]], Field(
        description="The full new context content as a dictionary. Overwrites existing."
    )] = None,
    patch_content: Annotated[Optional[Dict[str, Any]], Field(
        description="A dictionary of changes to apply to the existing context (add/update keys)."
    )] = None
) -> Dict[str, Any]:
    """
    Updates the product context for the specified workspace.

    Args:
        workspace_id: The identifier for the workspace.
        content: Optional full content to replace the existing context.
        patch_content: Optional partial content to update the existing context.

    Returns:
        A dictionary containing the updated product context.
    """
    try:
        # Pydantic model UpdateContextArgs will be validated by FastMCP based on annotations.
        # We still need to construct it for the handler.
        # The model's own validator will check 'content' vs 'patch_content'.
        pydantic_args = models.UpdateContextArgs(
            workspace_id=workspace_id,
            content=content,
            patch_content=patch_content
        )
        return mcp_handlers.handle_update_product_context(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in update_product_context handler: %s", e)
        raise
    except ValueError as e: # Catch Pydantic validation errors from UpdateContextArgs
        log.error(
            "Validation error for update_product_context: %s. "
            "Args: workspace_id=%s, content_present=%s, patch_content_present=%s",
            e, workspace_id, content is not None, patch_content is not None
        )
        raise exceptions.ContextPortalError(f"Invalid arguments for update_product_context: {e}")
    except Exception as e:
        log.error(
            "Error processing args for update_product_context: %s. "
            "Args: workspace_id=%s, content_present=%s, patch_content_present=%s",
            e, workspace_id, content is not None, patch_content is not None
        )
        raise exceptions.ContextPortalError(
            f"Server error processing update_product_context: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="get_active_context",
    description="Retrieves the current working focus, recent changes, and open issues."
)
async def tool_get_active_context(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )]
) -> Dict[str, Any]:
    """
    Retrieves the active context for the specified workspace.

    Args:
        workspace_id: The identifier for the workspace.

    Returns:
        A dictionary containing the active context.
    """
    try:
        pydantic_args = models.GetContextArgs(workspace_id=workspace_id)
        return mcp_handlers.handle_get_active_context(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in get_active_context handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for get_active_context: %s. Received workspace_id: %s",
            e, workspace_id
        )
        raise exceptions.ContextPortalError(
            f"Server error processing get_active_context: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="update_active_context",
    description="Updates the active context. Accepts full `content` (object) or "
                "`patch_content` (object) for partial updates "
                "(use `__DELETE__` as a value in patch to remove a key)."
)
async def tool_update_active_context(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    content: Annotated[Optional[Dict[str, Any]], Field(
        description="The full new context content as a dictionary. Overwrites existing."
    )] = None,
    patch_content: Annotated[Optional[Dict[str, Any]], Field(
        description="A dictionary of changes to apply to the existing context (add/update keys)."
    )] = None
) -> Dict[str, Any]:
    """
    Updates the active context for the specified workspace.

    Args:
        workspace_id: The identifier for the workspace.
        content: Optional full content to replace the existing context.
        patch_content: Optional partial content to update the existing context.

    Returns:
        A dictionary containing the updated active context.
    """
    try:
        pydantic_args = models.UpdateContextArgs(
            workspace_id=workspace_id,
            content=content,
            patch_content=patch_content
        )
        return mcp_handlers.handle_update_active_context(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in update_active_context handler: %s", e)
        raise
    except ValueError as e: # Catch Pydantic validation errors from UpdateContextArgs
        log.error(
            "Validation error for update_active_context: %s. "
            "Args: workspace_id=%s, content_present=%s, patch_content_present=%s",
            e, workspace_id, content is not None, patch_content is not None
        )
        raise exceptions.ContextPortalError(f"Invalid arguments for update_active_context: {e}")
    except Exception as e:
        log.error(
            "Error processing args for update_active_context: %s. "
            "Args: workspace_id=%s, content_present=%s, patch_content_present=%s",
            e, workspace_id, content is not None, patch_content is not None
        )
        raise exceptions.ContextPortalError(
            f"Server error processing update_active_context: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="log_decision",
    description="Logs an architectural or implementation decision."
)
async def tool_log_decision(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    summary: Annotated[str, Field(
        min_length=1, description="A concise summary of the decision"
    )],
    rationale: Annotated[Optional[str], Field(
        description="The reasoning behind the decision"
    )] = None,
    implementation_details: Annotated[Optional[str], Field(
        description="Details about how the decision will be/was implemented"
    )] = None,
    tags: Annotated[Optional[List[str]], Field(
        description="Optional tags for categorization"
    )] = None
) -> Dict[str, Any]:
    """
    Logs a new decision for the specified workspace.

    Args:
        workspace_id: The identifier for the workspace.
        summary: A concise summary of the decision.
        rationale: Optional reasoning behind the decision.
        implementation_details: Optional implementation details.
        tags: Optional list of tags.

    Returns:
        A dictionary containing the logged decision.
    """
    try:
        pydantic_args = models.LogDecisionArgs(
            workspace_id=workspace_id,
            summary=summary,
            rationale=rationale,
            implementation_details=implementation_details,
            tags=tags
        )
        return mcp_handlers.handle_log_decision(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in log_decision handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for log_decision: %s. Args: workspace_id=%s, summary='%s'",
            e, workspace_id, summary
        )
        raise exceptions.ContextPortalError(
            f"Server error processing log_decision: {type(e).__name__}"
        )

@conport_mcp.tool(name="get_decisions", description="Retrieves logged decisions.")
async def tool_get_decisions(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    ctx: Context,
    limit: Annotated[Optional[Union[int, str]], Field(
        description="Maximum number of decisions to return (most recent first)"
    )] = None,
    tags_filter_include_all: Annotated[Optional[List[str]], Field(
        description="Filter: items must include ALL of these tags."
    )] = None,
    tags_filter_include_any: Annotated[Optional[List[str]], Field(
        description="Filter: items must include AT LEAST ONE of these tags."
    )] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves decisions for the specified workspace.

    Args:
        workspace_id: The identifier for the workspace.
        ctx: The MCP context.
        limit: Optional maximum number of decisions to return.
        tags_filter_include_all: Optional list of tags that must all be present.
        tags_filter_include_any: Optional list of tags where at least one must be present.

    Returns:
        A list of dictionaries containing the decisions.
    """
    try:
        _ = ctx
        # The model's own validator will check tag filter exclusivity.
        pydantic_args = models.GetDecisionsArgs(
            workspace_id=workspace_id,
            limit=int(limit) if limit is not None else None,
            tags_filter_include_all=tags_filter_include_all,
            tags_filter_include_any=tags_filter_include_any
        )
        return mcp_handlers.handle_get_decisions(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in get_decisions handler: %s", e)
        raise
    except ValueError as e: # Catch Pydantic validation errors
        log.error(
            "Validation error for get_decisions: %s. "
            "Args: workspace_id=%s, limit=%s, tags_all=%s, tags_any=%s",
            e, workspace_id, limit, tags_filter_include_all, tags_filter_include_any
        )
        raise exceptions.ContextPortalError(f"Invalid arguments for get_decisions: {e}")
    except Exception as e:
        log.error(
            "Error processing args for get_decisions: %s. "
            "Args: workspace_id=%s, limit=%s, tags_all=%s, tags_any=%s",
            e, workspace_id, limit, tags_filter_include_all, tags_filter_include_any
        )
        raise exceptions.ContextPortalError(
            f"Server error processing get_decisions: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="search_decisions_fts",
    description="Full-text search across decision fields (summary, rationale, details, tags)."
)
async def tool_search_decisions_fts(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    query_term: Annotated[str, Field(
        min_length=1, description="The term to search for in decisions."
    )],
    ctx: Context,
    limit: Annotated[Optional[Union[int, str]], Field(
        default=10, ge=1, description="Maximum number of search results to return."
    )] = 10
) -> List[Dict[str, Any]]:
    """
    Performs a full-text search on decisions.

    Args:
        workspace_id: The identifier for the workspace.
        query_term: The term to search for.
        ctx: The MCP context.
        limit: Optional maximum number of results to return.

    Returns:
        A list of dictionaries containing the matching decisions.
    """
    try:
        _ = ctx
        pydantic_args = models.SearchDecisionsArgs(
            workspace_id=workspace_id,
            query_term=query_term,
            limit=int(limit) if limit is not None else None
        )
        return mcp_handlers.handle_search_decisions_fts(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in search_decisions_fts handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for search_decisions_fts: %s. "
            "Args: workspace_id=%s, query_term='%s', limit=%s",
            e, workspace_id, query_term, limit
        )
        raise exceptions.ContextPortalError(
            f"Server error processing search_decisions_fts: {type(e).__name__}"
        )

@conport_mcp.tool(name="log_progress", description="Logs a progress entry or task status.")
async def tool_log_progress(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    status: Annotated[str, Field(
        description="Current status (e.g., 'TODO', 'IN_PROGRESS', 'DONE')"
    )],
    description: Annotated[str, Field(
        min_length=1, description="Description of the progress or task"
    )],
    ctx: Context,
    parent_id: Annotated[Optional[Union[int, str]], Field(
        description="ID of the parent task, if this is a subtask"
    )] = None,
    linked_item_type: Annotated[Optional[str], Field(
        description="Optional: Type of the ConPort item this progress entry is linked to "
                    "(e.g., 'decision', 'system_pattern')"
    )] = None,
    linked_item_id: Annotated[Optional[str], Field(
        description="Optional: ID/key of the ConPort item this progress entry is linked to "
                    "(requires linked_item_type)"
    )] = None,
    link_relationship_type: Annotated[str, Field(
        description="Relationship type for the automatic link, defaults to 'relates_to_progress'"
    )] = "relates_to_progress"
) -> Dict[str, Any]:
    """
    Logs a progress entry for the specified workspace.

    Args:
        workspace_id: The identifier for the workspace.
        status: The current status of the task.
        description: A description of the progress or task.
        ctx: The MCP context.
        parent_id: Optional ID of the parent task.
        linked_item_type: Optional type of linked item.
        linked_item_id: Optional ID of linked item.
        link_relationship_type: Relationship type for the link.

    Returns:
        A dictionary containing the logged progress entry.
    """
    try:
        _ = ctx
        # The model's own validator will check linked_item_type vs linked_item_id.
        pydantic_args = models.LogProgressArgs(
            workspace_id=workspace_id,
            status=status,
            description=description,
            parent_id=int(parent_id) if parent_id is not None else None,
            linked_item_type=linked_item_type,
            linked_item_id=linked_item_id,
            link_relationship_type=link_relationship_type
        )
        return mcp_handlers.handle_log_progress(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in log_progress handler: %s", e)
        raise
    except ValueError as e: # Catch Pydantic validation errors
        log.error(
            "Validation error for log_progress: %s. Args: workspace_id=%s, status='%s'",
            e, workspace_id, status
        )
        raise exceptions.ContextPortalError(f"Invalid arguments for log_progress: {e}")
    except Exception as e:
        log.error(
            "Error processing args for log_progress: %s. Args: workspace_id=%s, status='%s'",
            e, workspace_id, status
        )
        raise exceptions.ContextPortalError(
            f"Server error processing log_progress: {type(e).__name__}"
        )

@conport_mcp.tool(name="get_progress", description="Retrieves progress entries.")
async def tool_get_progress(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    ctx: Context,
    status_filter: Annotated[Optional[str], Field(
        description="Filter entries by status"
    )] = None,
    parent_id_filter: Annotated[Optional[Union[int, str]], Field(
        description="Filter entries by parent task ID"
    )] = None,
    limit: Annotated[Optional[Union[int, str]], Field(
        description="Maximum number of entries to return (most recent first)"
    )] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves progress entries for the specified workspace.

    Args:
        workspace_id: The identifier for the workspace.
        ctx: The MCP context.
        status_filter: Optional filter by status.
        parent_id_filter: Optional filter by parent task ID.
        limit: Optional maximum number of entries to return.

    Returns:
        A list of dictionaries containing the progress entries.
    """
    try:
        _ = ctx
        pydantic_args = models.GetProgressArgs(
            workspace_id=workspace_id,
            status_filter=status_filter,
            parent_id_filter=int(parent_id_filter) if parent_id_filter is not None else None,
            limit=int(limit) if limit is not None else None
        )
        return mcp_handlers.handle_get_progress(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in get_progress handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for get_progress: %s. "
            "Args: workspace_id=%s, status_filter='%s', parent_id_filter=%s, limit=%s",
            e, workspace_id, status_filter, parent_id_filter, limit
        )
        raise exceptions.ContextPortalError(
            f"Server error processing get_progress: {type(e).__name__}"
        )

@conport_mcp.tool(name="update_progress", description="Updates an existing progress entry.")
async def tool_update_progress(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    progress_id: Annotated[Union[int, str], Field(
        description="The ID of the progress entry to update."
    )],
    ctx: Context,
    status: Annotated[Optional[str], Field(
        description="New status (e.g., 'TODO', 'IN_PROGRESS', 'DONE')"
    )] = None,
    description: Annotated[Optional[str], Field(
        min_length=1, description="New description of the progress or task"
    )] = None,
    parent_id: Annotated[Optional[Union[int, str]], Field(
        description="New ID of the parent task, if changing"
    )] = None
) -> Dict[str, Any]:
    """
    Updates an existing progress entry.

    Args:
        workspace_id: The identifier for the workspace.
        progress_id: The ID of the progress entry to update.
        ctx: The MCP context.
        status: Optional new status.
        description: Optional new description.
        parent_id: Optional new parent task ID.

    Returns:
        A dictionary containing the updated progress entry.
    """
    try:
        _ = ctx
        # The model's own validator will check at_least_one_field.
        pydantic_args = models.UpdateProgressArgs(
            workspace_id=workspace_id,
            progress_id=int(progress_id),
            status=status,
            description=description,
            parent_id=int(parent_id) if parent_id is not None else None
        )
        return mcp_handlers.handle_update_progress(pydantic_args)
    except exceptions.ContextPortalError as e: # Specific app errors
        log.error("Error in update_progress handler: %s", e)
        raise
    except ValueError as e: # Catch Pydantic validation errors from UpdateProgressArgs
        log.error(
            "Validation error for update_progress: %s. "
            "Args: workspace_id=%s, progress_id=%s, status='%s', "
            "description_present=%s, parent_id=%s",
            e, workspace_id, progress_id, status, description is not None, parent_id
        )
        raise exceptions.ContextPortalError(f"Invalid arguments for update_progress: {e}")
    except Exception as e: # Catch-all for other unexpected errors
        log.error(
            "Unexpected error processing args for update_progress: %s. "
            "Args: workspace_id=%s, progress_id=%s",
            e, workspace_id, progress_id
        )
        raise exceptions.ContextPortalError(
            f"Server error processing update_progress: {type(e).__name__} - {e}"
        )

@conport_mcp.tool(name="delete_progress_by_id", description="Deletes a progress entry by its ID.")
async def tool_delete_progress_by_id(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    progress_id: Annotated[Union[int, str], Field(
        description="The ID of the progress entry to delete."
    )],
    ctx: Context
) -> Dict[str, Any]:
    """
    Deletes a progress entry by its ID.

    Args:
        workspace_id: The identifier for the workspace.
        progress_id: The ID of the progress entry to delete.
        ctx: The MCP context.

    Returns:
        A dictionary confirming the deletion.
    """
    try:
        _ = ctx
        pydantic_args = models.DeleteProgressByIdArgs(
            workspace_id=workspace_id,
            progress_id=int(progress_id)
        )
        return mcp_handlers.handle_delete_progress_by_id(pydantic_args)
    except exceptions.ContextPortalError as e: # Specific app errors
        log.error("Error in delete_progress_by_id handler: %s", e)
        raise
    # No specific ValueError expected from this model's validation
    except Exception as e: # Catch-all for other unexpected errors
        log.error(
            "Unexpected error processing args for delete_progress_by_id: %s. "
            "Args: workspace_id=%s, progress_id=%s",
            e, workspace_id, progress_id
        )
        raise exceptions.ContextPortalError(
            f"Server error processing delete_progress_by_id: {type(e).__name__} - {e}"
        )

@conport_mcp.tool(name="log_system_pattern", description="Logs or updates a system/coding pattern.")
async def tool_log_system_pattern(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    name: Annotated[str, Field(
        min_length=1, description="Unique name for the system pattern"
    )],
    ctx: Context,
    description: Annotated[Optional[str], Field(
        description="Description of the pattern"
    )] = None,
    tags: Annotated[Optional[List[str]], Field(
        description="Optional tags for categorization"
    )] = None
) -> Dict[str, Any]:
    """
    Logs a system pattern for the specified workspace.

    Args:
        workspace_id: The identifier for the workspace.
        name: The name of the pattern.
        ctx: The MCP context.
        description: Optional description of the pattern.
        tags: Optional list of tags.

    Returns:
        A dictionary containing the logged system pattern.
    """
    try:
        _ = ctx
        pydantic_args = models.LogSystemPatternArgs(
            workspace_id=workspace_id,
            name=name,
            description=description,
            tags=tags
        )
        return mcp_handlers.handle_log_system_pattern(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in log_system_pattern handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for log_system_pattern: %s. Args: workspace_id=%s, name='%s'",
            e, workspace_id, name
        )
        raise exceptions.ContextPortalError(
            f"Server error processing log_system_pattern: {type(e).__name__}"
        )

@conport_mcp.tool(name="get_system_patterns", description="Retrieves system patterns.")
async def tool_get_system_patterns(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    ctx: Context,
    limit: Annotated[Optional[Union[int, str]], Field(
        description="Maximum number of patterns to return"
    )] = None,
    tags_filter_include_all: Annotated[Optional[List[str]], Field(
        description="Filter: items must include ALL of these tags."
    )] = None,
    tags_filter_include_any: Annotated[Optional[List[str]], Field(
        description="Filter: items must include AT LEAST ONE of these tags."
    )] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves system patterns for the specified workspace.

    Args:
        workspace_id: The identifier for the workspace.
        ctx: The MCP context.
        limit: Optional maximum number of patterns to return.
        tags_filter_include_all: Optional list of tags that must all be present.
        tags_filter_include_any: Optional list of tags where at least one must be present.

    Returns:
        A list of dictionaries containing the system patterns.
    """
    try:
        _ = ctx
        # The model's own validator will check tag filter exclusivity.
        pydantic_args = models.GetSystemPatternsArgs(
            workspace_id=workspace_id,
            limit=int(limit) if limit is not None else None,
            tags_filter_include_all=tags_filter_include_all,
            tags_filter_include_any=tags_filter_include_any
        )
        return mcp_handlers.handle_get_system_patterns(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in get_system_patterns handler: %s", e)
        raise
    except ValueError as e: # Catch Pydantic validation errors
        log.error(
            "Validation error for get_system_patterns: %s. "
            "Args: workspace_id=%s, tags_all=%s, tags_any=%s",
            e, workspace_id, tags_filter_include_all, tags_filter_include_any
        )
        raise exceptions.ContextPortalError(f"Invalid arguments for get_system_patterns: {e}")
    except Exception as e:
        log.error(
            "Error processing args for get_system_patterns: %s. "
            "Args: workspace_id=%s, tags_all=%s, tags_any=%s",
            e, workspace_id, tags_filter_include_all, tags_filter_include_any
        )
        raise exceptions.ContextPortalError(
            f"Server error processing get_system_patterns: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="log_custom_data",
    description="Stores/updates a custom key-value entry under a category. "
                "Value is JSON-serializable."
)
async def tool_log_custom_data(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    category: Annotated[str, Field(
        min_length=1, description="Category for the custom data"
    )],
    key: Annotated[str, Field(
        min_length=1, description="Key for the custom data (unique within category)"
    )],
    value: Annotated[Any, Field(
        description="The custom data value (JSON serializable)"
    )],
    ctx: Context
) -> Dict[str, Any]:
    """
    Logs custom data for the specified workspace.

    Args:
        workspace_id: The identifier for the workspace.
        category: The category for the data.
        key: The key for the data.
        value: The value to store.
        ctx: The MCP context.

    Returns:
        A dictionary containing the logged custom data.
    """
    try:
        _ = ctx
        pydantic_args = models.LogCustomDataArgs(
            workspace_id=workspace_id,
            category=category,
            key=key,
            value=value
        )
        return mcp_handlers.handle_log_custom_data(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in log_custom_data handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for log_custom_data: %s. "
            "Args: workspace_id=%s, category='%s', key='%s'",
            e, workspace_id, category, key
        )
        raise exceptions.ContextPortalError(
            f"Server error processing log_custom_data: {type(e).__name__}"
        )

@conport_mcp.tool(name="get_custom_data", description="Retrieves custom data.")
async def tool_get_custom_data(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    ctx: Context,
    category: Annotated[Optional[str], Field(
        description="Filter by category"
    )] = None,
    key: Annotated[Optional[str], Field(
        description="Filter by key (requires category)"
    )] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves custom data for the specified workspace.

    Args:
        workspace_id: The identifier for the workspace.
        ctx: The MCP context.
        category: Optional category filter.
        key: Optional key filter.

    Returns:
        A list of dictionaries containing the custom data.
    """
    try:
        _ = ctx
        pydantic_args = models.GetCustomDataArgs(
            workspace_id=workspace_id,
            category=category,
            key=key
        )
        return mcp_handlers.handle_get_custom_data(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in get_custom_data handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for get_custom_data: %s. "
            "Args: workspace_id=%s, category='%s', key='%s'",
            e, workspace_id, category, key
        )
        raise exceptions.ContextPortalError(
            f"Server error processing get_custom_data: {type(e).__name__}"
        )

@conport_mcp.tool(name="delete_custom_data", description="Deletes a specific custom data entry.")
async def tool_delete_custom_data(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    category: Annotated[str, Field(
        min_length=1, description="Category of the data to delete"
    )],
    key: Annotated[str, Field(
        min_length=1, description="Key of the data to delete"
    )],
    ctx: Context
) -> Dict[str, Any]:
    """
    Deletes a custom data entry.

    Args:
        workspace_id: The identifier for the workspace.
        category: The category of the data.
        key: The key of the data.
        ctx: The MCP context.

    Returns:
        A dictionary confirming the deletion.
    """
    try:
        _ = ctx
        pydantic_args = models.DeleteCustomDataArgs(
            workspace_id=workspace_id,
            category=category,
            key=key
        )
        return mcp_handlers.handle_delete_custom_data(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in delete_custom_data handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for delete_custom_data: %s. "
            "Args: workspace_id=%s, category='%s', key='%s'",
            e, workspace_id, category, key
        )
        raise exceptions.ContextPortalError(
            f"Server error processing delete_custom_data: {type(e).__name__}"
        )
@conport_mcp.tool(
    name="search_project_glossary_fts",
    description="Full-text search within the 'ProjectGlossary' custom data category."
)
async def tool_search_project_glossary_fts(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    query_term: Annotated[str, Field(
        min_length=1, description="The term to search for in the glossary."
    )],
    ctx: Context,
    limit: Annotated[Optional[Union[int, str]], Field(
        default=10, description="Maximum number of search results to return."
    )] = 10
) -> List[Dict[str, Any]]:
    """
    Searches the project glossary.

    Args:
        workspace_id: The identifier for the workspace.
        query_term: The term to search for.
        ctx: The MCP context.
        limit: Optional maximum number of results to return.

    Returns:
        A list of dictionaries containing the matching glossary entries.
    """
    try:
        _ = ctx
        pydantic_args = models.SearchProjectGlossaryArgs(
            workspace_id=workspace_id,
            query_term=query_term,
            limit=int(limit) if limit is not None else None
        )
        return mcp_handlers.handle_search_project_glossary_fts(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in search_project_glossary_fts handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for search_project_glossary_fts: %s. "
            "Args: workspace_id=%s, query_term='%s', limit=%s",
            e, workspace_id, query_term, limit
        )
        raise exceptions.ContextPortalError(
            f"Server error processing search_project_glossary_fts: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="export_conport_to_markdown",
    description="Exports ConPort data to markdown files."
)
async def tool_export_conport_to_markdown(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    ctx: Context,
    output_path: Annotated[Optional[str], Field(
        description="Optional output directory path relative to workspace_id. "
                    "Defaults to './conport_export/' if not provided."
    )] = None
) -> Dict[str, Any]:
    """
    Exports ConPort data to markdown files.

    Args:
        workspace_id: The identifier for the workspace.
        ctx: The MCP context.
        output_path: Optional output directory path.

    Returns:
        A dictionary confirming the export.
    """
    try:
        _ = ctx
        pydantic_args = models.ExportConportToMarkdownArgs(
            workspace_id=workspace_id,
            output_path=output_path
        )
        return mcp_handlers.handle_export_conport_to_markdown(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in export_conport_to_markdown handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for export_conport_to_markdown: %s. "
            "Args: workspace_id=%s, output_path='%s'",
            e, workspace_id, output_path
        )
        raise exceptions.ContextPortalError(
            f"Server error processing export_conport_to_markdown: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="import_markdown_to_conport",
    description="Imports data from markdown files into ConPort."
)
async def tool_import_markdown_to_conport(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    ctx: Context,
    input_path: Annotated[Optional[str], Field(
        description="Optional input directory path relative to workspace_id "
                    "containing markdown files. "
                    "Defaults to './conport_export/' if not provided."
    )] = None
) -> Dict[str, Any]:
    """
    Imports data from markdown files into ConPort.

    Args:
        workspace_id: The identifier for the workspace.
        ctx: The MCP context.
        input_path: Optional input directory path.

    Returns:
        A dictionary confirming the import.
    """
    try:
        _ = ctx
        pydantic_args = models.ImportMarkdownToConportArgs(
            workspace_id=workspace_id,
            input_path=input_path
        )
        return mcp_handlers.handle_import_markdown_to_conport(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in import_markdown_to_conport handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for import_markdown_to_conport: %s. "
            "Args: workspace_id=%s, input_path='%s'",
            e, workspace_id, input_path
        )
        raise exceptions.ContextPortalError(
            f"Server error processing import_markdown_to_conport: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="link_conport_items",
    description="Creates a relationship link between two ConPort items, "
                "explicitly building out the project knowledge graph."
)
async def tool_link_conport_items(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    source_item_type: Annotated[str, Field(description="Type of the source item")],
    source_item_id: Annotated[str, Field(description="ID or key of the source item")],
    target_item_type: Annotated[str, Field(description="Type of the target item")],
    target_item_id: Annotated[str, Field(description="ID or key of the target item")],
    relationship_type: Annotated[str, Field(description="Nature of the link")],
    ctx: Context,
    description: Annotated[Optional[str], Field(
        description="Optional description for the link"
    )] = None
) -> Dict[str, Any]:
    """
    Creates a link between two ConPort items.

    Args:
        workspace_id: The identifier for the workspace.
        source_item_type: Type of the source item.
        source_item_id: ID of the source item.
        target_item_type: Type of the target item.
        target_item_id: ID of the target item.
        relationship_type: Nature of the link.
        ctx: The MCP context.
        description: Optional description for the link.

    Returns:
        A dictionary containing the created link.
    """
    try:
        _ = ctx
        pydantic_args = models.LinkConportItemsArgs(
            workspace_id=workspace_id,
            source_item_type=source_item_type,
            source_item_id=str(source_item_id), # Ensure string as per model
            target_item_type=target_item_type,
            target_item_id=str(target_item_id), # Ensure string as per model
            relationship_type=relationship_type,
            description=description
        )
        return mcp_handlers.handle_link_conport_items(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in link_conport_items handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for link_conport_items: %s. "
            "Args: workspace_id=%s, source_type='%s', source_id='%s'",
            e, workspace_id, source_item_type, source_item_id
        )
        raise exceptions.ContextPortalError(
            f"Server error processing link_conport_items: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="get_linked_items",
    description="Retrieves items linked to a specific item."
)
async def tool_get_linked_items(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    item_type: Annotated[str, Field(
        description="Type of the item to find links for (e.g., 'decision')"
    )],
    item_id: Annotated[str, Field(
        description="ID or key of the item to find links for"
    )],
    ctx: Context,
    relationship_type_filter: Annotated[Optional[str], Field(
        description="Optional: Filter by relationship type"
    )] = None,
    linked_item_type_filter: Annotated[Optional[str], Field(
        description="Optional: Filter by the type of the linked items"
    )] = None,
    limit: Annotated[Optional[Union[int, str]], Field(
        description="Maximum number of links to return"
    )] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves linked items for a specific item.

    Args:
        workspace_id: The identifier for the workspace.
        item_type: Type of the item.
        item_id: ID of the item.
        ctx: The MCP context.
        relationship_type_filter: Optional filter by relationship type.
        linked_item_type_filter: Optional filter by linked item type.
        limit: Optional maximum number of links to return.

    Returns:
        A list of dictionaries containing the linked items.
    """
    try:
        _ = ctx
        pydantic_args = models.GetLinkedItemsArgs(
            workspace_id=workspace_id,
            item_type=item_type,
            item_id=str(item_id), # Ensure string as per model
            relationship_type_filter=relationship_type_filter,
            linked_item_type_filter=linked_item_type_filter,
            limit=int(limit) if limit is not None else None
        )
        return mcp_handlers.handle_get_linked_items(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in get_linked_items handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for get_linked_items: %s. "
            "Args: workspace_id=%s, item_type='%s', item_id='%s'",
            e, workspace_id, item_type, item_id
        )
        raise exceptions.ContextPortalError(
            f"Server error processing get_linked_items: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="search_custom_data_value_fts",
    description="Full-text search across all custom data values, categories, and keys."
)
async def tool_search_custom_data_value_fts(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    query_term: Annotated[str, Field(
        min_length=1,
        description="The term to search for in custom data (category, key, or value)."
    )],
    ctx: Context,
    category_filter: Annotated[Optional[str], Field(
        description="Optional: Filter results to this category after FTS."
    )] = None,
    limit: Annotated[Optional[Union[int, str]], Field(
        default=10, ge=1, description="Maximum number of search results to return."
    )] = 10
) -> List[Dict[str, Any]]:
    """
    Performs a full-text search on custom data values.

    Args:
        workspace_id: The identifier for the workspace.
        query_term: The term to search for.
        ctx: The MCP context.
        category_filter: Optional category filter.
        limit: Optional maximum number of results to return.

    Returns:
        A list of dictionaries containing the matching custom data.
    """
    try:
        _ = ctx
        pydantic_args = models.SearchCustomDataValueArgs(
            workspace_id=workspace_id,
            query_term=query_term,
            category_filter=category_filter,
            limit=int(limit) if limit is not None else None
        )
        return mcp_handlers.handle_search_custom_data_value_fts(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in search_custom_data_value_fts handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for search_custom_data_value_fts: %s. "
            "Args: workspace_id=%s, query_term='%s', category_filter='%s', limit=%s",
            e, workspace_id, query_term, category_filter, limit
        )
        raise exceptions.ContextPortalError(
            f"Server error processing search_custom_data_value_fts: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="batch_log_items",
    description="Logs multiple items of the same type "
                "(e.g., decisions, progress entries) in a single call."
)
async def tool_batch_log_items(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    item_type: Annotated[str, Field(
        description="Type of items to log "
                    "(e.g., 'decision', 'progress_entry', 'system_pattern', 'custom_data')"
    )],
    items: Annotated[List[Dict[str, Any]], Field(
        description="A list of dictionaries, each representing the arguments for a single item log."
    )],
    ctx: Context
) -> Dict[str, Any]:
    """
    Logs multiple items in a batch.

    Args:
        workspace_id: The identifier for the workspace.
        item_type: The type of items to log.
        items: A list of item dictionaries.
        ctx: The MCP context.

    Returns:
        A dictionary confirming the batch log.
    """
    try:
        _ = ctx
        # Basic validation for items being a list is handled by Pydantic/FastMCP.
        # More complex validation (e.g. structure of dicts within items) happens in the handler.
        pydantic_args = models.BatchLogItemsArgs(
            workspace_id=workspace_id,
            item_type=item_type,
            items=items
        )
        return mcp_handlers.handle_batch_log_items(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in batch_log_items handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for batch_log_items: %s. "
            "Args: workspace_id=%s, item_type='%s', num_items=%s",
            e, workspace_id, item_type, len(items) if isinstance(items, list) else 'N/A'
        )
        raise exceptions.ContextPortalError(
            f"Server error processing batch_log_items: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="get_item_history",
    description="Retrieves version history for Product or Active Context."
)
async def tool_get_item_history(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    item_type: Annotated[str, Field(
        description="Type of the item: 'product_context' or 'active_context'"
    )],
    ctx: Context,
    limit: Annotated[Optional[Union[int, str]], Field(
        description="Maximum number of history entries to return (most recent first)"
    )] = None,
    before_timestamp: Annotated[Optional[datetime], Field(
        description="Return entries before this timestamp"
    )] = None,
    after_timestamp: Annotated[Optional[datetime], Field(
        description="Return entries after this timestamp"
    )] = None,
    version: Annotated[Optional[Union[int, str]], Field(
        description="Return a specific version"
    )] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves the history of a context item.

    Args:
        workspace_id: The identifier for the workspace.
        item_type: The type of item (product_context or active_context).
        ctx: The MCP context.
        limit: Optional maximum number of entries.
        before_timestamp: Optional timestamp filter.
        after_timestamp: Optional timestamp filter.
        version: Optional version number.

    Returns:
        A list of dictionaries containing the history entries.
    """
    try:
        _ = ctx
        # The model's own validator will check item_type.
        pydantic_args = models.GetItemHistoryArgs(
            workspace_id=workspace_id,
            item_type=item_type,
            limit=int(limit) if limit is not None else None,
            before_timestamp=before_timestamp,
            after_timestamp=after_timestamp,
            version=int(version) if version is not None else None
        )
        return mcp_handlers.handle_get_item_history(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in get_item_history handler: %s", e)
        raise
    except ValueError as e: # Catch Pydantic validation errors
        log.error(
            "Validation error for get_item_history: %s. Args: workspace_id=%s, item_type='%s'",
            e, workspace_id, item_type
        )
        raise exceptions.ContextPortalError(f"Invalid arguments for get_item_history: {e}")
    except Exception as e:
        log.error(
            "Error processing args for get_item_history: %s. Args: workspace_id=%s, item_type='%s'",
            e, workspace_id, item_type
        )
        raise exceptions.ContextPortalError(
            f"Server error processing get_item_history: {type(e).__name__}"
        )

@conport_mcp.tool(name="delete_decision_by_id", description="Deletes a decision by its ID.")
async def tool_delete_decision_by_id(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    decision_id: Annotated[Union[int, str], Field(
        description="The ID of the decision to delete."
    )],
    ctx: Context
) -> Dict[str, Any]:
    """
    Deletes a decision by its ID.

    Args:
        workspace_id: The identifier for the workspace.
        decision_id: The ID of the decision to delete.
        ctx: The MCP context.

    Returns:
        A dictionary confirming the deletion.
    """
    try:
        _ = ctx
        pydantic_args = models.DeleteDecisionByIdArgs(
            workspace_id=workspace_id,
            decision_id=int(decision_id)
        )
        return mcp_handlers.handle_delete_decision_by_id(pydantic_args)
    except Exception as e:
        log.error(
            "Error processing args for delete_decision_by_id: %s. "
            "Args: workspace_id=%s, decision_id=%s",
            e, workspace_id, decision_id
        )
        raise exceptions.ContextPortalError(
            f"Server error processing delete_decision_by_id: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="delete_system_pattern_by_id",
    description="Deletes a system pattern by its ID."
)
async def tool_delete_system_pattern_by_id(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    pattern_id: Annotated[Union[int, str], Field(
        description="The ID of the system pattern to delete."
    )],
    ctx: Context
) -> Dict[str, Any]:
    """
    Deletes a system pattern by its ID.

    Args:
        workspace_id: The identifier for the workspace.
        pattern_id: The ID of the system pattern to delete.
        ctx: The MCP context.

    Returns:
        A dictionary confirming the deletion.
    """
    try:
        _ = ctx
        pydantic_args = models.DeleteSystemPatternByIdArgs(
            workspace_id=workspace_id,
            pattern_id=int(pattern_id)
        )
        return mcp_handlers.handle_delete_system_pattern_by_id(pydantic_args)
    except Exception as e:
        log.error(
            "Error processing args for delete_system_pattern_by_id: %s. "
            "Args: workspace_id=%s, pattern_id=%s",
            e, workspace_id, pattern_id
        )
        raise exceptions.ContextPortalError(
            f"Server error processing delete_system_pattern_by_id: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="get_conport_schema",
    description="Retrieves the schema of available ConPort tools and their arguments."
)
async def tool_get_conport_schema(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    ctx: Context
) -> Dict[str, Dict[str, Any]]:
    """
    Retrieves the ConPort tool schema.

    Args:
        workspace_id: The identifier for the workspace.
        ctx: The MCP context.

    Returns:
        A dictionary containing the tool schema.
    """
    try:
        _ = ctx
        pydantic_args = models.GetConportSchemaArgs(workspace_id=workspace_id)
        return mcp_handlers.handle_get_conport_schema(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in get_conport_schema handler: %s", e)
        raise
    except Exception as e:
        log.error(
            "Error processing args for get_conport_schema: %s. Args: workspace_id=%s",
            e, workspace_id
        )
        raise exceptions.ContextPortalError(
            f"Server error processing get_conport_schema: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="get_recent_activity_summary",
    description="Provides a summary of recent ConPort activity (new/updated items)."
)
async def tool_get_recent_activity_summary(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    ctx: Context,
    hours_ago: Annotated[Optional[Union[int, str]], Field(
        description="Look back this many hours for recent activity. "
                    "Mutually exclusive with 'since_timestamp'."
    )] = None,
    since_timestamp: Annotated[Optional[datetime], Field(
        description="Look back for activity since this specific timestamp. "
                    "Mutually exclusive with 'hours_ago'."
    )] = None,
    limit_per_type: Annotated[Optional[Union[int, str]], Field(
        default=5,
        description="Maximum number of recent items to show per activity type "
                    "(e.g., 5 most recent decisions)."
    )] = 5
) -> Dict[str, Any]:
    """
    Retrieves a summary of recent activity.

    Args:
        workspace_id: The identifier for the workspace.
        ctx: The MCP context.
        hours_ago: Optional hours to look back.
        since_timestamp: Optional timestamp to look back from.
        limit_per_type: Optional limit per item type.

    Returns:
        A dictionary containing the activity summary.
    """
    try:
        _ = ctx
        # The model's own validator will check hours_ago vs since_timestamp.
        pydantic_args = models.GetRecentActivitySummaryArgs(
            workspace_id=workspace_id,
            hours_ago=int(hours_ago) if hours_ago is not None else None,
            since_timestamp=since_timestamp,
            limit_per_type=int(limit_per_type) if limit_per_type is not None else None
        )
        return mcp_handlers.handle_get_recent_activity_summary(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error("Error in get_recent_activity_summary handler: %s", e)
        raise
    except ValueError as e: # Catch Pydantic validation errors
        log.error(
            "Validation error for get_recent_activity_summary: %s. "
            "Args: workspace_id=%s, hours_ago=%s, since_timestamp=%s",
            e, workspace_id, hours_ago, since_timestamp
        )
        raise exceptions.ContextPortalError(
            f"Invalid arguments for get_recent_activity_summary: {e}"
        )
    except Exception as e:
        log.error(
            "Error processing args for get_recent_activity_summary: %s. "
            "Args: workspace_id=%s, hours_ago=%s, since_timestamp=%s",
            e, workspace_id, hours_ago, since_timestamp
        )
        raise exceptions.ContextPortalError(
            f"Server error processing get_recent_activity_summary: {type(e).__name__}"
        )

@conport_mcp.tool(
    name="semantic_search_conport",
    description="Performs a semantic search across ConPort data."
)
async def tool_semantic_search_conport(
    workspace_id: Annotated[str, Field(
        description="Identifier for the workspace (e.g., absolute path)"
    )],
    query_text: Annotated[str, Field(
        min_length=1, description="The natural language query text for semantic search."
    )],
    ctx: Context,
    top_k: Annotated[Union[int, str], Field(
        default=5, le=25, description="Number of top results to return."
    )] = 5,
    filter_item_types: Annotated[Optional[List[str]], Field(
        description="Optional list of item types to filter by "
                    "(e.g., ['decision', 'custom_data']). "
                    "Valid types: 'decision', 'system_pattern', 'custom_data', 'progress_entry'."
    )] = None,
    filter_tags_include_any: Annotated[Optional[List[str]], Field(
        description="Optional list of tags; results will include items matching any of these tags."
    )] = None,
    filter_tags_include_all: Annotated[Optional[List[str]], Field(
        description="Optional list of tags; "
                    "results will include only items matching all of these tags."
    )] = None,
    filter_custom_data_categories: Annotated[Optional[List[str]], Field(
        description="Optional list of categories to filter by "
                    "if 'custom_data' is in filter_item_types."
    )] = None
) -> List[Dict[str, Any]]:
    """
    Performs a semantic search across ConPort data.

    Args:
        workspace_id: The identifier for the workspace.
        query_text: The query text.
        ctx: The MCP context.
        top_k: Number of results to return.
        filter_item_types: Optional list of item types to filter by.
        filter_tags_include_any: Optional list of tags (any).
        filter_tags_include_all: Optional list of tags (all).
        filter_custom_data_categories: Optional list of custom data categories.

    Returns:
        A list of dictionaries containing the search results.
    """
    try:
        _ = ctx
        # The model's own validators will check tag filters and custom_data_category_filter.
        pydantic_args = models.SemanticSearchConportArgs(
            workspace_id=workspace_id,
            query_text=query_text,
            top_k=int(top_k),
            filter_item_types=filter_item_types,
            filter_tags_include_any=filter_tags_include_any,
            filter_tags_include_all=filter_tags_include_all,
            filter_custom_data_categories=filter_custom_data_categories
        )
        # Ensure the handler is awaited if it's async
        return await mcp_handlers.handle_semantic_search_conport(pydantic_args)
    except exceptions.ContextPortalError as e: # Specific app errors
        log.error("Error in semantic_search_conport handler: %s", e)
        raise
    except ValueError as e: # Catch Pydantic validation errors
        log.error(
            "Validation error for semantic_search_conport: %s. "
            "Args: workspace_id=%s, query_text='%s'",
            e, workspace_id, query_text
        )
        raise exceptions.ContextPortalError(f"Invalid arguments for semantic_search_conport: {e}")
    except Exception as e: # Catch-all for other unexpected errors
        log.error(
            "Unexpected error processing args for semantic_search_conport: %s. "
            "Args: workspace_id=%s, query_text='%s'",
            e, workspace_id, query_text
        )
        raise exceptions.ContextPortalError(
            f"Server error processing semantic_search_conport: {type(e).__name__} - {e}"
        )

@conport_mcp.tool(
    name="get_workspace_detection_info",
    description="Provides detailed information about workspace detection "
                "for debugging and verification."
)
async def tool_get_workspace_detection_info(
    ctx: Context,
    start_path: Annotated[Optional[str], Field(
        description="Starting directory for detection analysis (default: current directory)"
    )] = None
) -> Dict[str, Any]:
    """
    MCP tool for getting workspace detection information.
    This tool helps debug workspace detection issues and verify the detection process.

    Args:
        ctx: The MCP context.
        start_path: Optional starting path for detection.

    Returns:
        A dictionary containing detection info.
    """
    try:
        _ = ctx
        detector = WorkspaceDetector(start_path)
        detection_info = detector.get_detection_info()

        # Add additional runtime information
        detection_info.update({
            'server_version': CONPORT_VERSION,
            'detection_timestamp': datetime.now().isoformat(),
            'auto_detection_available': True,
            'mcp_context_workspace': detector.detect_from_mcp_context()
        })

        return detection_info
    except Exception as e:  # pylint: disable=broad-exception-caught
        log.error("Error in get_workspace_detection_info: %s", e)
        raise exceptions.ContextPortalError(
            f"Server error getting workspace detection info: {type(e).__name__} - {e}"
        )

# Mount the FastMCP HTTP app to the FastAPI app at the /mcp path
# This will handle both GET and POST requests using modern HTTP transport
app.mount("/mcp", conport_mcp.http_app())
log.info("Mounted FastMCP HTTP app at /mcp")

# Keep a simple root endpoint for health checks or basic info
@app.get("/")
async def read_root():
    """Root endpoint for health check."""
    return {"message": "ConPort MCP Server is running. MCP endpoint at /mcp"}


# Determine the absolute path to the root of the ConPort server project
# Assumes this script (main.py) is at src/context_portal_mcp/main.py
CONPORT_SERVER_ROOT_DIR = Path(os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
))
log.info("ConPort Server Root Directory identified as: %s", CONPORT_SERVER_ROOT_DIR)
def main_logic(sys_args=None):
    """
    Configures and runs the ConPort server (HTTP mode via Uvicorn).
    The actual MCP logic is handled by the FastMCP instance mounted on the FastAPI app.
    """
    parser = argparse.ArgumentParser(description="ConPort MCP Server (FastMCP/HTTP)")
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind the HTTP server to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the HTTP server to (default: 8000)"
    )
    # Enhanced workspace_id parameter with auto-detection support
    parser.add_argument(
        "--workspace_id",
        type=str,
        required=False, # No longer strictly required for server startup itself
        help="Workspace ID. If not provided, will auto-detect from current directory "
             "or MCP client context."
    )

    # New auto-detection parameters
    parser.add_argument(
        "--auto-detect-workspace",
        action="store_true",
        default=True,
        help="Automatically detect workspace from current directory (default: True)"
    )

    parser.add_argument(
        "--workspace-search-start",
        help="Starting directory for workspace detection (default: current directory)"
    )

    parser.add_argument(
        "--no-auto-detect",
        action="store_true",
        help="Disable automatic workspace detection"
    )
    # The --mode argument might be deprecated if FastMCP only runs HTTP this way,
    # or we add a condition here to call conport_mcp.run(transport="stdio")
    parser.add_argument(
        "--mode",
        choices=["http", "stdio"], # Add http, stdio might be handled by FastMCP directly
        default="http",
        help="Server communication mode (default: http for FastMCP mounted app)"
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default="logs/conport.log",
        help="Path to a file where logs should be written, relative to the "
             "context_portal directory. Defaults to 'logs/conport.log'."
    )
    parser.add_argument(
        "--db-path",
        type=str,
        required=False,
        help="Custom database file path (absolute or relative to workspace). "
             "Defaults to 'context_portal/context.db' in workspace."
    )
    parser.add_argument(
        "--base-path",
        type=str,
        required=False,
        help="Base path for storing all workspace-specific data. "
             "A subdirectory will be created for each workspace."
    )
    parser.add_argument(
        "--db-filename",
        type=str,
        default="context.db",
        help="The name of the context database file. Defaults to 'context.db'."
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level."
    )

    args = parser.parse_args(args=sys_args)

    # Configure logging based on the parsed arguments
    setup_logging(args)

    # Set custom database path if provided
    if args.db_path:
        from .core import config
        config.set_custom_db_path(args.db_path)
        log.info("Using custom database path: %s", args.db_path)

    if args.base_path:
        from .core import config
        config.set_base_path(args.base_path)
        log.info("Using base path: %s", args.base_path)

    if args.db_filename:
        from .core import config
        config.set_db_filename(args.db_filename)
        log.info("Using database filename: %s", args.db_filename)

    log.info("Parsed CLI args: %s", args)

    # In stdio mode, we should not configure the console handler,
    # as it can interfere with MCP communication.
    # FastMCP handles stdio, so we only add console logging for http mode.
    if args.mode == "http":
        log.info("Starting ConPort HTTP server (via FastMCP) on %s:%s", args.host, args.port)
        # The FastAPI `app` (with FastMCP mounted) is run by Uvicorn
        uvicorn.run(app, host=args.host, port=args.port)
    elif args.mode == "stdio":
        log.info("Starting ConPort in STDIO mode with workspace detection enabled")

        # Resolve workspace ID using the new detection system
        auto_detect_enabled = args.auto_detect_workspace and not args.no_auto_detect
        effective_workspace_id = resolve_workspace_id(
            provided_workspace_id=args.workspace_id,
            auto_detect=auto_detect_enabled,
            start_path=args.workspace_search_start
        )

        # Log detection details for debugging
        if auto_detect_enabled:
            detector = WorkspaceDetector(args.workspace_search_start)
            detection_info = detector.get_detection_info()
            log.info("Workspace detection details: %s", detection_info)

        log.info("Effective workspace ID: %s", effective_workspace_id)

        # Pre-warm the database connection to trigger one-time initialization (e.g., migrations)
        # before the MCP transport starts. This prevents timeouts on the client's first tool call.
        if effective_workspace_id:
            try:
                log.info(
                    "Pre-warming database connection for workspace: %s",
                    effective_workspace_id
                )
                database.get_db_connection(effective_workspace_id)
                log.info("Database connection pre-warmed successfully.")
            except Exception as e:  # pylint: disable=broad-exception-caught
                log.error(
                    "Failed to pre-warm database connection for workspace '%s': %s",
                    effective_workspace_id, e
                )
                # If the DB is essential, exiting is safer than continuing in a broken state.
                sys.exit(1)
        else:
            log.warning(
                "No effective_workspace_id available at startup. "
                "Database initialization will be deferred to the first tool call."
            )

        # Note: The `FastMCP.run()` method is synchronous and will block until the server stops.
        # It requires the `mcp[cli]` extra to be installed for `mcp.server.stdio.run_server_stdio`.
        try:
            # The `settings` attribute on FastMCP can be used to pass runtime config.
            # However, `workspace_id` is not a standard FastMCP setting for `run()`.
            # It's expected to be part of the tool call parameters.
            # The primary role of --workspace_id for stdio here is for the IDE's launch config.
            conport_mcp.run(transport="stdio")
        except Exception:  # pylint: disable=broad-exception-caught
            log.exception("Error running FastMCP in STDIO mode")
            sys.exit(1)

    else:
        log.error("Unsupported mode: %s", args.mode)
        sys.exit(1)

def cli_entry_point():
    """Entry point for the 'conport-server' command-line script."""
    log.info("ConPort MCP Server CLI entry point called.")
    main_logic()

if __name__ == "__main__":
    cli_entry_point()
