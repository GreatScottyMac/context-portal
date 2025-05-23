import sys
import uvicorn
from fastapi import FastAPI
import logging.handlers
import argparse
import os
from typing import Dict, Any, Optional, AsyncIterator, List, Annotated # Added AsyncIterator and List and Annotated
from datetime import datetime
from contextlib import asynccontextmanager # Added

# MCP SDK imports
from mcp.server.fastmcp import FastMCP, Context as MCPContext # Renamed Context to avoid clash
from pydantic import Field

# Local imports
try:
    from .handlers import mcp_handlers # We will adapt these
    from .db import database, models # models for tool argument types
    from .core import exceptions # For custom exceptions if FastMCP doesn't map them
except ImportError:
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from src.context_portal_mcp.handlers import mcp_handlers
    from src.context_portal_mcp.db import database, models
    from src.context_portal_mcp.core import exceptions

# Configure logging
log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO) # Default level for all handlers

# Console handler
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setFormatter(logging.Formatter(log_format))
root_logger.addHandler(console_handler)

log = logging.getLogger(__name__) # Get the module-specific logger

# --- Lifespan Management for FastMCP ---
@asynccontextmanager
async def conport_lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage application lifecycle for ConPort."""
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
CONPORT_VERSION = "0.1.0"

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

@conport_mcp.tool(name="get_product_context", description="Retrieves the overall project goals, features, and architecture.")
async def tool_get_product_context(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    ctx: MCPContext
) -> Dict[str, Any]:
    try:
        # Construct the Pydantic model for the handler
        pydantic_args = models.GetContextArgs(workspace_id=workspace_id)
        return mcp_handlers.handle_get_product_context(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in get_product_context handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for get_product_context: {e}. Received workspace_id: {workspace_id}")
        raise exceptions.ContextPortalError(f"Server error processing get_product_context: {type(e).__name__}")

@conport_mcp.tool(name="update_product_context", description="Updates the product context. Accepts full `content` (object) or `patch_content` (object) for partial updates (use `__DELETE__` as a value in patch to remove a key).")
async def tool_update_product_context(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    ctx: MCPContext, # MCPContext should typically be last, but let's keep other args grouped
    content: Annotated[Optional[Dict[str, Any]], Field(description="The full new context content as a dictionary. Overwrites existing.")] = None,
    patch_content: Annotated[Optional[Dict[str, Any]], Field(description="A dictionary of changes to apply to the existing context (add/update keys).")] = None
) -> Dict[str, Any]:
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
        log.error(f"Error in update_product_context handler: {e}")
        raise
    except ValueError as e: # Catch Pydantic validation errors from UpdateContextArgs
        log.error(f"Validation error for update_product_context: {e}. Args: workspace_id={workspace_id}, content_present={content is not None}, patch_content_present={patch_content is not None}")
        raise exceptions.ContextPortalError(f"Invalid arguments for update_product_context: {e}")
    except Exception as e:
        log.error(f"Error processing args for update_product_context: {e}. Args: workspace_id={workspace_id}, content_present={content is not None}, patch_content_present={patch_content is not None}")
        raise exceptions.ContextPortalError(f"Server error processing update_product_context: {type(e).__name__}")

@conport_mcp.tool(name="get_active_context", description="Retrieves the current working focus, recent changes, and open issues.")
async def tool_get_active_context(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    ctx: MCPContext
) -> Dict[str, Any]:
    try:
        pydantic_args = models.GetContextArgs(workspace_id=workspace_id)
        return mcp_handlers.handle_get_active_context(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in get_active_context handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for get_active_context: {e}. Received workspace_id: {workspace_id}")
        raise exceptions.ContextPortalError(f"Server error processing get_active_context: {type(e).__name__}")

@conport_mcp.tool(name="update_active_context", description="Updates the active context. Accepts full `content` (object) or `patch_content` (object) for partial updates (use `__DELETE__` as a value in patch to remove a key).")
async def tool_update_active_context(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    ctx: MCPContext,
    content: Annotated[Optional[Dict[str, Any]], Field(description="The full new context content as a dictionary. Overwrites existing.")] = None,
    patch_content: Annotated[Optional[Dict[str, Any]], Field(description="A dictionary of changes to apply to the existing context (add/update keys).")] = None
) -> Dict[str, Any]:
    try:
        pydantic_args = models.UpdateContextArgs(
            workspace_id=workspace_id,
            content=content,
            patch_content=patch_content
        )
        return mcp_handlers.handle_update_active_context(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in update_active_context handler: {e}")
        raise
    except ValueError as e: # Catch Pydantic validation errors from UpdateContextArgs
        log.error(f"Validation error for update_active_context: {e}. Args: workspace_id={workspace_id}, content_present={content is not None}, patch_content_present={patch_content is not None}")
        raise exceptions.ContextPortalError(f"Invalid arguments for update_active_context: {e}")
    except Exception as e:
        log.error(f"Error processing args for update_active_context: {e}. Args: workspace_id={workspace_id}, content_present={content is not None}, patch_content_present={patch_content is not None}")
        raise exceptions.ContextPortalError(f"Server error processing update_active_context: {type(e).__name__}")

@conport_mcp.tool(name="log_decision", description="Logs an architectural or implementation decision.")
async def tool_log_decision(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    summary: Annotated[str, Field(min_length=1, description="A concise summary of the decision")],
    ctx: MCPContext,
    rationale: Annotated[Optional[str], Field(description="The reasoning behind the decision")] = None,
    implementation_details: Annotated[Optional[str], Field(description="Details about how the decision will be/was implemented")] = None,
    tags: Annotated[Optional[List[str]], Field(description="Optional tags for categorization")] = None
) -> Dict[str, Any]:
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
        log.error(f"Error in log_decision handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for log_decision: {e}. Args: workspace_id={workspace_id}, summary='{summary}'")
        raise exceptions.ContextPortalError(f"Server error processing log_decision: {type(e).__name__}")

@conport_mcp.tool(name="get_decisions", description="Retrieves logged decisions.")
async def tool_get_decisions(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    ctx: MCPContext,
    limit: Annotated[Optional[int], Field(gt=0, description="Maximum number of decisions to return (most recent first)")] = None,
    tags_filter_include_all: Annotated[Optional[List[str]], Field(description="Filter: items must include ALL of these tags.")] = None,
    tags_filter_include_any: Annotated[Optional[List[str]], Field(description="Filter: items must include AT LEAST ONE of these tags.")] = None
) -> List[Dict[str, Any]]:
    try:
        # The model's own validator will check tag filter exclusivity.
        pydantic_args = models.GetDecisionsArgs(
            workspace_id=workspace_id,
            limit=limit,
            tags_filter_include_all=tags_filter_include_all,
            tags_filter_include_any=tags_filter_include_any
        )
        return mcp_handlers.handle_get_decisions(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in get_decisions handler: {e}")
        raise
    except ValueError as e: # Catch Pydantic validation errors
        log.error(f"Validation error for get_decisions: {e}. Args: workspace_id={workspace_id}, limit={limit}, tags_all={tags_filter_include_all}, tags_any={tags_filter_include_any}")
        raise exceptions.ContextPortalError(f"Invalid arguments for get_decisions: {e}")
    except Exception as e:
        log.error(f"Error processing args for get_decisions: {e}. Args: workspace_id={workspace_id}, limit={limit}, tags_all={tags_filter_include_all}, tags_any={tags_filter_include_any}")
        raise exceptions.ContextPortalError(f"Server error processing get_decisions: {type(e).__name__}")

@conport_mcp.tool(name="search_decisions_fts", description="Full-text search across decision fields (summary, rationale, details, tags).")
async def tool_search_decisions_fts(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    query_term: Annotated[str, Field(min_length=1, description="The term to search for in decisions.")],
    ctx: MCPContext,
    limit: Annotated[Optional[int], Field(default=10, gt=0, description="Maximum number of search results to return.")] = 10
) -> List[Dict[str, Any]]:
    try:
        pydantic_args = models.SearchDecisionsArgs(
            workspace_id=workspace_id,
            query_term=query_term,
            limit=limit
        )
        return mcp_handlers.handle_search_decisions_fts(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in search_decisions_fts handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for search_decisions_fts: {e}. Args: workspace_id={workspace_id}, query_term='{query_term}', limit={limit}")
        raise exceptions.ContextPortalError(f"Server error processing search_decisions_fts: {type(e).__name__}")

@conport_mcp.tool(name="log_progress", description="Logs a progress entry or task status.")
async def tool_log_progress(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    status: Annotated[str, Field(description="Current status (e.g., 'TODO', 'IN_PROGRESS', 'DONE')")],
    description: Annotated[str, Field(min_length=1, description="Description of the progress or task")],
    ctx: MCPContext,
    parent_id: Annotated[Optional[int], Field(description="ID of the parent task, if this is a subtask")] = None,
    linked_item_type: Annotated[Optional[str], Field(description="Optional: Type of the ConPort item this progress entry is linked to (e.g., 'decision', 'system_pattern')")] = None,
    linked_item_id: Annotated[Optional[str], Field(description="Optional: ID/key of the ConPort item this progress entry is linked to (requires linked_item_type)")] = None,
    link_relationship_type: Annotated[str, Field(description="Relationship type for the automatic link, defaults to 'relates_to_progress'")] = "relates_to_progress"
) -> Dict[str, Any]:
    try:
        # The model's own validator will check linked_item_type vs linked_item_id.
        pydantic_args = models.LogProgressArgs(
            workspace_id=workspace_id,
            status=status,
            description=description,
            parent_id=parent_id,
            linked_item_type=linked_item_type,
            linked_item_id=linked_item_id,
            link_relationship_type=link_relationship_type
        )
        return mcp_handlers.handle_log_progress(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in log_progress handler: {e}")
        raise
    except ValueError as e: # Catch Pydantic validation errors
        log.error(f"Validation error for log_progress: {e}. Args: workspace_id={workspace_id}, status='{status}'")
        raise exceptions.ContextPortalError(f"Invalid arguments for log_progress: {e}")
    except Exception as e:
        log.error(f"Error processing args for log_progress: {e}. Args: workspace_id={workspace_id}, status='{status}'")
        raise exceptions.ContextPortalError(f"Server error processing log_progress: {type(e).__name__}")

@conport_mcp.tool(name="get_progress", description="Retrieves progress entries.")
async def tool_get_progress(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    ctx: MCPContext,
    status_filter: Annotated[Optional[str], Field(description="Filter entries by status")] = None,
    parent_id_filter: Annotated[Optional[int], Field(description="Filter entries by parent task ID")] = None,
    limit: Annotated[Optional[int], Field(gt=0, description="Maximum number of entries to return (most recent first)")] = None
) -> List[Dict[str, Any]]:
    try:
        pydantic_args = models.GetProgressArgs(
            workspace_id=workspace_id,
            status_filter=status_filter,
            parent_id_filter=parent_id_filter,
            limit=limit
        )
        return mcp_handlers.handle_get_progress(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in get_progress handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for get_progress: {e}. Args: workspace_id={workspace_id}, status_filter='{status_filter}', parent_id_filter={parent_id_filter}, limit={limit}")
        raise exceptions.ContextPortalError(f"Server error processing get_progress: {type(e).__name__}")

@conport_mcp.tool(name="update_progress", description="Updates an existing progress entry.")
async def tool_update_progress(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    progress_id: Annotated[int, Field(gt=0, description="The ID of the progress entry to update.")],
    ctx: MCPContext,
    status: Annotated[Optional[str], Field(description="New status (e.g., 'TODO', 'IN_PROGRESS', 'DONE')")] = None,
    description: Annotated[Optional[str], Field(min_length=1, description="New description of the progress or task")] = None,
    parent_id: Annotated[Optional[int], Field(description="New ID of the parent task, if changing")] = None
) -> Dict[str, Any]:
    """
    MCP tool wrapper for update_progress.
    Validates arguments and calls the handler.
    """
    try:
        # The model's own validator will check at_least_one_field.
        pydantic_args = models.UpdateProgressArgs(
            workspace_id=workspace_id,
            progress_id=progress_id,
            status=status,
            description=description,
            parent_id=parent_id
        )
        return mcp_handlers.handle_update_progress(pydantic_args)
    except exceptions.ContextPortalError as e: # Specific app errors
        log.error(f"Error in update_progress handler: {e}")
        raise
    except ValueError as e: # Catch Pydantic validation errors from UpdateProgressArgs
        log.error(f"Validation error for update_progress: {e}. Args: workspace_id={workspace_id}, progress_id={progress_id}, status='{status}', description_present={description is not None}, parent_id={parent_id}")
        raise exceptions.ContextPortalError(f"Invalid arguments for update_progress: {e}")
    except Exception as e: # Catch-all for other unexpected errors
        log.error(f"Unexpected error processing args for update_progress: {e}. Args: workspace_id={workspace_id}, progress_id={progress_id}")
        raise exceptions.ContextPortalError(f"Server error processing update_progress: {type(e).__name__} - {e}")

@conport_mcp.tool(name="delete_progress_by_id", description="Deletes a progress entry by its ID.")
async def tool_delete_progress_by_id(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    progress_id: Annotated[int, Field(gt=0, description="The ID of the progress entry to delete.")],
    ctx: MCPContext
) -> Dict[str, Any]:
    """
    MCP tool wrapper for delete_progress_by_id.
    Validates arguments and calls the handler.
    """
    try:
        pydantic_args = models.DeleteProgressByIdArgs(
            workspace_id=workspace_id,
            progress_id=progress_id
        )
        return mcp_handlers.handle_delete_progress_by_id(pydantic_args)
    except exceptions.ContextPortalError as e: # Specific app errors
        log.error(f"Error in delete_progress_by_id handler: {e}")
        raise
    # No specific ValueError expected from this model's validation
    except Exception as e: # Catch-all for other unexpected errors
        log.error(f"Unexpected error processing args for delete_progress_by_id: {e}. Args: workspace_id={workspace_id}, progress_id={progress_id}")
        raise exceptions.ContextPortalError(f"Server error processing delete_progress_by_id: {type(e).__name__} - {e}")

@conport_mcp.tool(name="log_system_pattern", description="Logs or updates a system/coding pattern.")
async def tool_log_system_pattern(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    name: Annotated[str, Field(min_length=1, description="Unique name for the system pattern")],
    ctx: MCPContext,
    description: Annotated[Optional[str], Field(description="Description of the pattern")] = None,
    tags: Annotated[Optional[List[str]], Field(description="Optional tags for categorization")] = None
) -> Dict[str, Any]:
    try:
        pydantic_args = models.LogSystemPatternArgs(
            workspace_id=workspace_id,
            name=name,
            description=description,
            tags=tags
        )
        return mcp_handlers.handle_log_system_pattern(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in log_system_pattern handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for log_system_pattern: {e}. Args: workspace_id={workspace_id}, name='{name}'")
        raise exceptions.ContextPortalError(f"Server error processing log_system_pattern: {type(e).__name__}")

@conport_mcp.tool(name="get_system_patterns", description="Retrieves system patterns.")
async def tool_get_system_patterns(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    ctx: MCPContext,
    tags_filter_include_all: Annotated[Optional[List[str]], Field(description="Filter: items must include ALL of these tags.")] = None,
    tags_filter_include_any: Annotated[Optional[List[str]], Field(description="Filter: items must include AT LEAST ONE of these tags.")] = None
) -> List[Dict[str, Any]]:
    try:
        # The model's own validator will check tag filter exclusivity.
        pydantic_args = models.GetSystemPatternsArgs(
            workspace_id=workspace_id,
            tags_filter_include_all=tags_filter_include_all,
            tags_filter_include_any=tags_filter_include_any
        )
        return mcp_handlers.handle_get_system_patterns(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in get_system_patterns handler: {e}")
        raise
    except ValueError as e: # Catch Pydantic validation errors
        log.error(f"Validation error for get_system_patterns: {e}. Args: workspace_id={workspace_id}, tags_all={tags_filter_include_all}, tags_any={tags_filter_include_any}")
        raise exceptions.ContextPortalError(f"Invalid arguments for get_system_patterns: {e}")
    except Exception as e:
        log.error(f"Error processing args for get_system_patterns: {e}. Args: workspace_id={workspace_id}, tags_all={tags_filter_include_all}, tags_any={tags_filter_include_any}")
        raise exceptions.ContextPortalError(f"Server error processing get_system_patterns: {type(e).__name__}")

@conport_mcp.tool(name="log_custom_data", description="Stores/updates a custom key-value entry under a category. Value is JSON-serializable.")
async def tool_log_custom_data(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    category: Annotated[str, Field(min_length=1, description="Category for the custom data")],
    key: Annotated[str, Field(min_length=1, description="Key for the custom data (unique within category)")],
    value: Annotated[Any, Field(description="The custom data value (JSON serializable)")],
    ctx: MCPContext
) -> Dict[str, Any]:
    try:
        pydantic_args = models.LogCustomDataArgs(
            workspace_id=workspace_id,
            category=category,
            key=key,
            value=value
        )
        return mcp_handlers.handle_log_custom_data(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in log_custom_data handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for log_custom_data: {e}. Args: workspace_id={workspace_id}, category='{category}', key='{key}'")
        raise exceptions.ContextPortalError(f"Server error processing log_custom_data: {type(e).__name__}")

@conport_mcp.tool(name="get_custom_data", description="Retrieves custom data.")
async def tool_get_custom_data(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    ctx: MCPContext,
    category: Annotated[Optional[str], Field(description="Filter by category")] = None,
    key: Annotated[Optional[str], Field(description="Filter by key (requires category)")] = None
) -> List[Dict[str, Any]]:
    try:
        pydantic_args = models.GetCustomDataArgs(
            workspace_id=workspace_id,
            category=category,
            key=key
        )
        return mcp_handlers.handle_get_custom_data(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in get_custom_data handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for get_custom_data: {e}. Args: workspace_id={workspace_id}, category='{category}', key='{key}'")
        raise exceptions.ContextPortalError(f"Server error processing get_custom_data: {type(e).__name__}")

@conport_mcp.tool(name="delete_custom_data", description="Deletes a specific custom data entry.")
async def tool_delete_custom_data(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    category: Annotated[str, Field(min_length=1, description="Category of the data to delete")],
    key: Annotated[str, Field(min_length=1, description="Key of the data to delete")],
    ctx: MCPContext
) -> Dict[str, Any]:
    try:
        pydantic_args = models.DeleteCustomDataArgs(
            workspace_id=workspace_id,
            category=category,
            key=key
        )
        return mcp_handlers.handle_delete_custom_data(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in delete_custom_data handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for delete_custom_data: {e}. Args: workspace_id={workspace_id}, category='{category}', key='{key}'")
        raise exceptions.ContextPortalError(f"Server error processing delete_custom_data: {type(e).__name__}")
@conport_mcp.tool(name="search_project_glossary_fts", description="Full-text search within the 'ProjectGlossary' custom data category.")
async def tool_search_project_glossary_fts(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    query_term: Annotated[str, Field(min_length=1, description="The term to search for in the glossary.")],
    ctx: MCPContext,
    limit: Annotated[Optional[int], Field(default=10, gt=0, description="Maximum number of search results to return.")] = 10
) -> List[Dict[str, Any]]:
    try:
        pydantic_args = models.SearchProjectGlossaryArgs(
            workspace_id=workspace_id,
            query_term=query_term,
            limit=limit
        )
        return mcp_handlers.handle_search_project_glossary_fts(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in search_project_glossary_fts handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for search_project_glossary_fts: {e}. Args: workspace_id={workspace_id}, query_term='{query_term}', limit={limit}")
        raise exceptions.ContextPortalError(f"Server error processing search_project_glossary_fts: {type(e).__name__}")

@conport_mcp.tool(name="export_conport_to_markdown", description="Exports ConPort data to markdown files.")
async def tool_export_conport_to_markdown(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    ctx: MCPContext,
    output_path: Annotated[Optional[str], Field(description="Optional output directory path relative to workspace_id. Defaults to './conport_export/' if not provided.")] = None
) -> Dict[str, Any]:
    try:
        pydantic_args = models.ExportConportToMarkdownArgs(
            workspace_id=workspace_id,
            output_path=output_path
        )
        return mcp_handlers.handle_export_conport_to_markdown(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in export_conport_to_markdown handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for export_conport_to_markdown: {e}. Args: workspace_id={workspace_id}, output_path='{output_path}'")
        raise exceptions.ContextPortalError(f"Server error processing export_conport_to_markdown: {type(e).__name__}")

@conport_mcp.tool(name="import_markdown_to_conport", description="Imports data from markdown files into ConPort.")
async def tool_import_markdown_to_conport(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    ctx: MCPContext,
    input_path: Annotated[Optional[str], Field(description="Optional input directory path relative to workspace_id containing markdown files. Defaults to './conport_export/' if not provided.")] = None
) -> Dict[str, Any]:
    try:
        pydantic_args = models.ImportMarkdownToConportArgs(
            workspace_id=workspace_id,
            input_path=input_path
        )
        return mcp_handlers.handle_import_markdown_to_conport(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in import_markdown_to_conport handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for import_markdown_to_conport: {e}. Args: workspace_id={workspace_id}, input_path='{input_path}'")
        raise exceptions.ContextPortalError(f"Server error processing import_markdown_to_conport: {type(e).__name__}")

@conport_mcp.tool(name="link_conport_items", description="Creates a relationship link between two ConPort items, explicitly building out the project knowledge graph.")
async def tool_link_conport_items(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    source_item_type: Annotated[str, Field(description="Type of the source item")],
    source_item_id: Annotated[str, Field(description="ID or key of the source item")],
    target_item_type: Annotated[str, Field(description="Type of the target item")],
    target_item_id: Annotated[str, Field(description="ID or key of the target item")],
    relationship_type: Annotated[str, Field(description="Nature of the link")],
    ctx: MCPContext,
    description: Annotated[Optional[str], Field(description="Optional description for the link")] = None
) -> Dict[str, Any]:
    try:
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
        log.error(f"Error in link_conport_items handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for link_conport_items: {e}. Args: workspace_id={workspace_id}, source_type='{source_item_type}', source_id='{source_item_id}'")
        raise exceptions.ContextPortalError(f"Server error processing link_conport_items: {type(e).__name__}")

@conport_mcp.tool(name="get_linked_items", description="Retrieves items linked to a specific item.")
async def tool_get_linked_items(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    item_type: Annotated[str, Field(description="Type of the item to find links for (e.g., 'decision')")],
    item_id: Annotated[str, Field(description="ID or key of the item to find links for")],
    ctx: MCPContext,
    relationship_type_filter: Annotated[Optional[str], Field(description="Optional: Filter by relationship type")] = None,
    linked_item_type_filter: Annotated[Optional[str], Field(description="Optional: Filter by the type of the linked items")] = None,
    limit: Annotated[Optional[int], Field(gt=0, description="Maximum number of links to return")] = None
) -> List[Dict[str, Any]]:
    try:
        pydantic_args = models.GetLinkedItemsArgs(
            workspace_id=workspace_id,
            item_type=item_type,
            item_id=str(item_id), # Ensure string as per model
            relationship_type_filter=relationship_type_filter,
            linked_item_type_filter=linked_item_type_filter,
            limit=limit
        )
        return mcp_handlers.handle_get_linked_items(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in get_linked_items handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for get_linked_items: {e}. Args: workspace_id={workspace_id}, item_type='{item_type}', item_id='{item_id}'")
        raise exceptions.ContextPortalError(f"Server error processing get_linked_items: {type(e).__name__}")

@conport_mcp.tool(name="search_custom_data_value_fts", description="Full-text search across all custom data values, categories, and keys.")
async def tool_search_custom_data_value_fts(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    query_term: Annotated[str, Field(min_length=1, description="The term to search for in custom data (category, key, or value).")],
    ctx: MCPContext,
    category_filter: Annotated[Optional[str], Field(description="Optional: Filter results to this category after FTS.")] = None,
    limit: Annotated[Optional[int], Field(default=10, gt=0, description="Maximum number of search results to return.")] = 10
) -> List[Dict[str, Any]]:
    try:
        pydantic_args = models.SearchCustomDataValueArgs(
            workspace_id=workspace_id,
            query_term=query_term,
            category_filter=category_filter,
            limit=limit
        )
        return mcp_handlers.handle_search_custom_data_value_fts(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in search_custom_data_value_fts handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for search_custom_data_value_fts: {e}. Args: workspace_id={workspace_id}, query_term='{query_term}', category_filter='{category_filter}', limit={limit}")
        raise exceptions.ContextPortalError(f"Server error processing search_custom_data_value_fts: {type(e).__name__}")

@conport_mcp.tool(name="batch_log_items", description="Logs multiple items of the same type (e.g., decisions, progress entries) in a single call.")
async def tool_batch_log_items(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    item_type: Annotated[str, Field(description="Type of items to log (e.g., 'decision', 'progress_entry', 'system_pattern', 'custom_data')")],
    items: Annotated[List[Dict[str, Any]], Field(description="A list of dictionaries, each representing the arguments for a single item log.")],
    ctx: MCPContext
) -> Dict[str, Any]:
    try:
        # Basic validation for items being a list is handled by Pydantic/FastMCP.
        # More complex validation (e.g. structure of dicts within items) happens in the handler.
        pydantic_args = models.BatchLogItemsArgs(
            workspace_id=workspace_id,
            item_type=item_type,
            items=items
        )
        return mcp_handlers.handle_batch_log_items(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in batch_log_items handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for batch_log_items: {e}. Args: workspace_id={workspace_id}, item_type='{item_type}', num_items={len(items) if isinstance(items, list) else 'N/A'}")
        raise exceptions.ContextPortalError(f"Server error processing batch_log_items: {type(e).__name__}")

@conport_mcp.tool(name="get_item_history", description="Retrieves version history for Product or Active Context.")
async def tool_get_item_history(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    item_type: Annotated[str, Field(description="Type of the item: 'product_context' or 'active_context'")],
    ctx: MCPContext,
    limit: Annotated[Optional[int], Field(gt=0, description="Maximum number of history entries to return (most recent first)")] = None,
    before_timestamp: Annotated[Optional[datetime], Field(description="Return entries before this timestamp")] = None,
    after_timestamp: Annotated[Optional[datetime], Field(description="Return entries after this timestamp")] = None,
    version: Annotated[Optional[int], Field(gt=0, description="Return a specific version")] = None
) -> List[Dict[str, Any]]:
    try:
        # The model's own validator will check item_type.
        pydantic_args = models.GetItemHistoryArgs(
            workspace_id=workspace_id,
            item_type=item_type,
            limit=limit,
            before_timestamp=before_timestamp,
            after_timestamp=after_timestamp,
            version=version
        )
        return mcp_handlers.handle_get_item_history(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in get_item_history handler: {e}")
        raise
    except ValueError as e: # Catch Pydantic validation errors
        log.error(f"Validation error for get_item_history: {e}. Args: workspace_id={workspace_id}, item_type='{item_type}'")
        raise exceptions.ContextPortalError(f"Invalid arguments for get_item_history: {e}")
    except Exception as e:
        log.error(f"Error processing args for get_item_history: {e}. Args: workspace_id={workspace_id}, item_type='{item_type}'")
        raise exceptions.ContextPortalError(f"Server error processing get_item_history: {type(e).__name__}")

@conport_mcp.tool(name="delete_decision_by_id", description="Deletes a decision by its ID.")
async def tool_delete_decision_by_id(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    decision_id: Annotated[int, Field(gt=0, description="The ID of the decision to delete.")],
    ctx: MCPContext
) -> Dict[str, Any]:
    try:
        pydantic_args = models.DeleteDecisionByIdArgs(workspace_id=workspace_id, decision_id=decision_id)
        return mcp_handlers.handle_delete_decision_by_id(pydantic_args)
    except Exception as e:
        log.error(f"Error processing args for delete_decision_by_id: {e}. Args: workspace_id={workspace_id}, decision_id={decision_id}")
        raise exceptions.ContextPortalError(f"Server error processing delete_decision_by_id: {type(e).__name__}")

@conport_mcp.tool(name="delete_system_pattern_by_id", description="Deletes a system pattern by its ID.")
async def tool_delete_system_pattern_by_id(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    pattern_id: Annotated[int, Field(gt=0, description="The ID of the system pattern to delete.")],
    ctx: MCPContext
) -> Dict[str, Any]:
    try:
        pydantic_args = models.DeleteSystemPatternByIdArgs(workspace_id=workspace_id, pattern_id=pattern_id)
        return mcp_handlers.handle_delete_system_pattern_by_id(pydantic_args)
    except Exception as e:
        log.error(f"Error processing args for delete_system_pattern_by_id: {e}. Args: workspace_id={workspace_id}, pattern_id={pattern_id}")
        raise exceptions.ContextPortalError(f"Server error processing delete_system_pattern_by_id: {type(e).__name__}")

@conport_mcp.tool(name="get_conport_schema", description="Retrieves the schema of available ConPort tools and their arguments.")
async def tool_get_conport_schema(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    ctx: MCPContext
) -> Dict[str, Dict[str, Any]]:
    try:
        pydantic_args = models.GetConportSchemaArgs(workspace_id=workspace_id)
        return mcp_handlers.handle_get_conport_schema(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in get_conport_schema handler: {e}")
        raise
    except Exception as e:
        log.error(f"Error processing args for get_conport_schema: {e}. Args: workspace_id={workspace_id}")
        raise exceptions.ContextPortalError(f"Server error processing get_conport_schema: {type(e).__name__}")

@conport_mcp.tool(name="get_recent_activity_summary", description="Provides a summary of recent ConPort activity (new/updated items).")
async def tool_get_recent_activity_summary(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    ctx: MCPContext,
    hours_ago: Annotated[Optional[int], Field(gt=0, description="Look back this many hours for recent activity. Mutually exclusive with 'since_timestamp'.")] = None,
    since_timestamp: Annotated[Optional[datetime], Field(description="Look back for activity since this specific timestamp. Mutually exclusive with 'hours_ago'.")] = None,
    limit_per_type: Annotated[Optional[int], Field(default=5, gt=0, description="Maximum number of recent items to show per activity type (e.g., 5 most recent decisions).")] = 5
) -> Dict[str, Any]:
    try:
        # The model's own validator will check hours_ago vs since_timestamp.
        pydantic_args = models.GetRecentActivitySummaryArgs(
            workspace_id=workspace_id,
            hours_ago=hours_ago,
            since_timestamp=since_timestamp,
            limit_per_type=limit_per_type
        )
        return mcp_handlers.handle_get_recent_activity_summary(pydantic_args)
    except exceptions.ContextPortalError as e:
        log.error(f"Error in get_recent_activity_summary handler: {e}")
        raise
    except ValueError as e: # Catch Pydantic validation errors
        log.error(f"Validation error for get_recent_activity_summary: {e}. Args: workspace_id={workspace_id}, hours_ago={hours_ago}, since_timestamp={since_timestamp}")
        raise exceptions.ContextPortalError(f"Invalid arguments for get_recent_activity_summary: {e}")
    except Exception as e:
        log.error(f"Error processing args for get_recent_activity_summary: {e}. Args: workspace_id={workspace_id}, hours_ago={hours_ago}, since_timestamp={since_timestamp}")
        raise exceptions.ContextPortalError(f"Server error processing get_recent_activity_summary: {type(e).__name__}")

@conport_mcp.tool(name="semantic_search_conport", description="Performs a semantic search across ConPort data.")
async def tool_semantic_search_conport(
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")],
    query_text: Annotated[str, Field(min_length=1, description="The natural language query text for semantic search.")],
    ctx: MCPContext,
    top_k: Annotated[int, Field(default=5, ge=1, le=25, description="Number of top results to return.")] = 5,
    filter_item_types: Annotated[Optional[List[str]], Field(description="Optional list of item types to filter by (e.g., ['decision', 'custom_data']). Valid types: 'decision', 'system_pattern', 'custom_data', 'progress_entry'.")] = None,
    filter_tags_include_any: Annotated[Optional[List[str]], Field(description="Optional list of tags; results will include items matching any of these tags.")] = None,
    filter_tags_include_all: Annotated[Optional[List[str]], Field(description="Optional list of tags; results will include only items matching all of these tags.")] = None,
    filter_custom_data_categories: Annotated[Optional[List[str]], Field(description="Optional list of categories to filter by if 'custom_data' is in filter_item_types.")] = None
) -> List[Dict[str, Any]]:
    """
    MCP tool wrapper for semantic_search_conport.
    It validates arguments using SemanticSearchConportArgs Pydantic model and calls the handler.
    """
    try:
        # The model's own validators will check tag filters and custom_data_category_filter.
        pydantic_args = models.SemanticSearchConportArgs(
            workspace_id=workspace_id,
            query_text=query_text,
            top_k=top_k,
            filter_item_types=filter_item_types,
            filter_tags_include_any=filter_tags_include_any,
            filter_tags_include_all=filter_tags_include_all,
            filter_custom_data_categories=filter_custom_data_categories
        )
        # Ensure the handler is awaited if it's async
        return await mcp_handlers.handle_semantic_search_conport(pydantic_args)
    except exceptions.ContextPortalError as e: # Specific app errors
        log.error(f"Error in semantic_search_conport handler: {e}")
        raise
    except ValueError as e: # Catch Pydantic validation errors
        log.error(f"Validation error for semantic_search_conport: {e}. Args: workspace_id={workspace_id}, query_text='{query_text}'")
        raise exceptions.ContextPortalError(f"Invalid arguments for semantic_search_conport: {e}")
    except Exception as e: # Catch-all for other unexpected errors
        log.error(f"Unexpected error processing args for semantic_search_conport: {e}. Args: workspace_id={workspace_id}, query_text='{query_text}'")
        raise exceptions.ContextPortalError(f"Server error processing semantic_search_conport: {type(e).__name__} - {e}")

# Mount the FastMCP SSE app to the FastAPI app at the /mcp path
# This will handle GET for SSE and POST for JSON-RPC client requests
app.mount("/mcp", conport_mcp.sse_app())
log.info("Mounted FastMCP app at /mcp")

# Keep a simple root endpoint for health checks or basic info
@app.get("/")
async def read_root():
    return {"message": "ConPort MCP Server is running. MCP endpoint at /mcp"}


# Determine the absolute path to the root of the ConPort server project
# Assumes this script (main.py) is at src/context_portal_mcp/main.py
CONPORT_SERVER_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
log.info(f"ConPort Server Root Directory identified as: {CONPORT_SERVER_ROOT_DIR}")
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
    # --workspace_id is not directly used by uvicorn.run for the app itself,
    # but it's good for the CLI to accept it for consistency if an IDE launches it.
    # The actual workspace_id is handled per-request by FastMCP tools.
    parser.add_argument(
        "--workspace_id",
        type=str,
        required=False, # No longer strictly required for server startup itself
        help="Optional: Default workspace ID (primarily for IDE launch context, tool calls still need it)."
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
        default=None,
        help="Path to a file where logs should be written. If not provided, logs go to stderr."
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level."
    )

    args = parser.parse_args(args=sys_args)
    log.info(f"Parsed CLI args: {args}")

    # Set the root logger level based on CLI argument
    root_logger.setLevel(getattr(logging, args.log_level.upper()))

    # Add file handler if log_file is specified
    if args.log_file:
        try:
            # Ensure the directory exists
            log_dir = os.path.dirname(args.log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            # Use RotatingFileHandler to prevent log files from growing indefinitely
            file_handler = logging.handlers.RotatingFileHandler(
                args.log_file,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5              # Keep up to 5 backup files
            )
            file_handler.setFormatter(logging.Formatter(log_format))
            root_logger.addHandler(file_handler)
            log.info(f"Logging to file: {args.log_file}")
        except Exception as e:
            log.error(f"Failed to set up file logging to {args.log_file}: {e}")

    if args.mode == "http":
        log.info(f"Starting ConPort HTTP server (via FastMCP) on {args.host}:{args.port}")
        # The FastAPI `app` (with FastMCP mounted) is run by Uvicorn
        uvicorn.run(app, host=args.host, port=args.port)
    elif args.mode == "stdio":
        log.info(f"Starting ConPort in STDIO mode using FastMCP for initial CLI arg workspace_id: {args.workspace_id}")

        effective_workspace_id = args.workspace_id
        if args.workspace_id == "${workspaceFolder}":
            # import os # Moved to top-level imports
            current_cwd = os.getcwd()
            warning_msg = (
                f"MAIN.PY: WARNING - Workspace ID was literally '${{workspaceFolder}}'. "
                f"This variable was not expanded by the client IDE. "
                f"Falling back to current working directory as workspace_id: {current_cwd}. "
                f"Ensure CWD in MCP config ('{current_cwd}') is the correct project workspace."
            )
            log.warning(warning_msg)
            effective_workspace_id = current_cwd

        try:
            # from src.context_portal_mcp.core.config import get_database_path # Import happens at module level
            # get_database_path(effective_workspace_id) # EARLY VALIDATION REMOVED - Path validation and dir creation will occur on first DB access.

            if not effective_workspace_id or not os.path.isdir(effective_workspace_id): # Basic check if path is a directory
                 log.error(f"STDIO mode: effective_workspace_id ('{effective_workspace_id}') is not a valid directory. Please ensure client provides a correct absolute path or sets 'cwd' appropriately if using '${{workspaceFolder}}'.")
                 sys.exit(1)

            log.info(f"STDIO mode: Using effective_workspace_id '{effective_workspace_id}'. Database directory will be created on first actual DB use.")
        except Exception as e: # Catch any other unexpected errors during this initial workspace_id handling
            log.error(f"Unexpected error processing effective_workspace_id '{effective_workspace_id}' in STDIO mode setup: {e}")
            sys.exit(1)

        # Note: The `FastMCP.run()` method is synchronous and will block until the server stops.
        # It requires the `mcp[cli]` extra to be installed for `mcp.server.stdio.run_server_stdio`.
        try:
            # The `settings` attribute on FastMCP can be used to pass runtime config.
            # However, `workspace_id` is not a standard FastMCP setting for `run()`.
            # It's expected to be part of the tool call parameters.
            # The primary role of --workspace_id for stdio here is for the IDE's launch config.
            conport_mcp.run(transport="stdio")
        except Exception as e:
            log.exception("Error running FastMCP in STDIO mode")
            sys.exit(1)

    else:
        log.error(f"Unsupported mode: {args.mode}")
        sys.exit(1)

def cli_entry_point():
    """Entry point for the 'conport-server' command-line script."""
    log.info("ConPort MCP Server CLI entry point called.")
    main_logic()

if __name__ == "__main__":
    cli_entry_point()
