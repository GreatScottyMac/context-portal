"""Functions implementing the logic for each MCP tool."""

import logging
import os
from pathlib import Path
import json
import re # For markdown parsing
from typing import Dict, Any, List, Optional
from datetime import datetime # Added missing import

from pydantic import ValidationError

from ..db import database as db
from ..db import models
from ..core.exceptions import ToolArgumentError, DatabaseError, ContextPortalError
from ..core import embedding_service # Added for semantic search
from ..db import vector_store_service # Added for semantic search

log = logging.getLogger(__name__)

# --- Tool Handler Functions ---

def handle_get_product_context(args: models.GetContextArgs) -> Dict[str, Any]:
    """
    Handles the 'get_product_context' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    """
    try:
        context_model = db.get_product_context(args.workspace_id)
        return context_model.content
    except DatabaseError as e:
        raise ContextPortalError(f"Database error getting product context: {e}")
    except Exception as e:
        # Log the full error for debugging if it's truly unexpected
        log.exception(f"Unexpected error in get_product_context for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in get_product_context: {e}")

def handle_update_product_context(args: models.UpdateContextArgs) -> Dict[str, Any]:
    """
    Handles the 'update_product_context' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns a success message dictionary.
    """
    try:
        # The Pydantic model 'args' (UpdateContextArgs) now handles validation
        # for 'content' vs 'patch_content'.
        # The database function 'db.update_product_context' now expects UpdateContextArgs.
        db.update_product_context(args.workspace_id, args)
        # FastMCP expects direct results. A status message is a reasonable result.
        return {"status": "success", "message": "Product context updated successfully."}
    except ValidationError as e: # Should not happen if FastMCP validates schema, but good for direct calls
         raise ToolArgumentError(f"Invalid content structure: {e}")
    except DatabaseError as e:
        raise ContextPortalError(f"Database error updating product context: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in update_product_context for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in update_product_context: {e}")

def handle_log_decision(args: models.LogDecisionArgs) -> Dict[str, Any]:
    """
    Handles the 'log_decision' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns the logged decision as a dictionary.
    """
    try:
        decision_to_log = models.Decision(
            summary=args.summary,
            rationale=args.rationale,
            implementation_details=args.implementation_details,
            tags=args.tags
            # Timestamp is added automatically by the Pydantic model's default_factory
        )
        logged_decision = db.log_decision(args.workspace_id, decision_to_log)

        # --- Add to Vector Store ---
        if logged_decision and logged_decision.id is not None:
            try:
                text_to_embed = f"Decision Summary: {logged_decision.summary}\n"
                if logged_decision.rationale:
                    text_to_embed += f"Rationale: {logged_decision.rationale}\n"
                if logged_decision.implementation_details:
                    text_to_embed += f"Implementation Details: {logged_decision.implementation_details}"
                
                vector = embedding_service.get_embedding(text_to_embed.strip())
                
                metadata_for_vector = {
                    "conport_item_id": str(logged_decision.id),
                    "conport_item_type": "decision",
                    "summary": logged_decision.summary,
                    "timestamp_created": logged_decision.timestamp.isoformat(),
                    "tags": logged_decision.tags if logged_decision.tags else []
                }
                vector_store_service.upsert_item_embedding(
                    workspace_id=args.workspace_id,
                    item_type="decision",
                    item_id=str(logged_decision.id),
                    vector=vector,
                    metadata=metadata_for_vector
                )
                log.info(f"Successfully generated and stored embedding for decision ID {logged_decision.id}")
            except Exception as e_embed:
                log.error(f"Failed to generate/store embedding for decision ID {logged_decision.id}: {e_embed}", exc_info=True)
        # --- End Add to Vector Store ---
        
        return logged_decision.model_dump(mode='json')
    except DatabaseError as e:
        raise ContextPortalError(f"Database error logging decision: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in log_decision for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in log_decision: {e}")

# --- Added handlers --- # This comment might be outdated, these are just more handlers

def handle_get_decisions(args: models.GetDecisionsArgs) -> List[Dict[str, Any]]:
    """
    Handles the 'get_decisions' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns a list of decision dictionaries.
    """
    try:
        decisions_list = db.get_decisions(
            args.workspace_id,
            limit=args.limit,
            tags_filter_include_all=args.tags_filter_include_all,
            tags_filter_include_any=args.tags_filter_include_any
        )
        return [d.model_dump(mode='json') for d in decisions_list]
    except DatabaseError as e:
        raise ContextPortalError(f"Database error getting decisions: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in get_decisions for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in get_decisions: {e}")

def handle_search_decisions_fts(args: models.SearchDecisionsArgs) -> List[Dict[str, Any]]:
    """
    Handles the 'search_decisions_fts' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns a list of decision dictionaries.
    """
    try:
        decisions_list = db.search_decisions_fts(
            args.workspace_id,
            query_term=args.query_term,
            limit=args.limit
        )
        return [d.model_dump(mode='json') for d in decisions_list]
    except DatabaseError as e:
        raise ContextPortalError(f"Database error searching decisions: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in search_decisions_fts for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in search_decisions_fts: {e}")

def handle_get_active_context(args: models.GetContextArgs) -> Dict[str, Any]:
    """
    Handles the 'get_active_context' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    """
    try:
        context_model = db.get_active_context(args.workspace_id)
        return context_model.content
    except DatabaseError as e:
        raise ContextPortalError(f"Database error getting active context: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in get_active_context for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in get_active_context: {e}")

def handle_update_active_context(args: models.UpdateContextArgs) -> Dict[str, Any]:
    """
    Handles the 'update_active_context' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns a success message dictionary.
    """
    try:
        # The Pydantic model 'args' (UpdateContextArgs) now handles validation
        # for 'content' vs 'patch_content'.
        # The database function 'db.update_active_context' now expects UpdateContextArgs.
        db.update_active_context(args.workspace_id, args)
        return {"status": "success", "message": "Active context updated successfully."}
    except ValidationError as e: # Should not happen if FastMCP validates
         raise ToolArgumentError(f"Invalid content structure: {e}")
    except DatabaseError as e:
        raise ContextPortalError(f"Database error updating active context: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in update_active_context for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in update_active_context: {e}")

def handle_log_progress(args: models.LogProgressArgs) -> Dict[str, Any]:
    """
    Handles the 'log_progress' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns the logged progress entry as a dictionary.
    """
    try:
        progress_to_log = models.ProgressEntry(
            status=args.status,
            description=args.description,
            parent_id=args.parent_id
            # linked_item_type and linked_item_id are not part of ProgressEntry model itself
        )
        logged_progress = db.log_progress(args.workspace_id, progress_to_log)

        # If linking information is provided, create the link
        if args.linked_item_type and args.linked_item_id and logged_progress.id is not None:
            try:
                link_to_create = models.ContextLink(
                    source_item_type="progress_entry", # The progress entry is the source
                    source_item_id=str(logged_progress.id), # ID of the newly created progress entry
                    target_item_type=args.linked_item_type,
                    target_item_id=args.linked_item_id,
                    relationship_type=args.link_relationship_type, # Use the relationship type from args
                    description=f"Progress entry '{logged_progress.description[:30]}...' automatically linked."
                )
                db.log_context_link(args.workspace_id, link_to_create)
                log.info(f"Automatically linked progress entry ID {logged_progress.id} to {args.linked_item_type} ID {args.linked_item_id}")
            except Exception as link_e:
                # Log the linking error but don't let it fail the whole progress logging
                log.error(f"Failed to automatically link progress entry ID {logged_progress.id} for workspace {args.workspace_id}: {link_e}")
                # Optionally, add this error to the response if the MCP tool schema supports it

        # --- Add to Vector Store ---
        if logged_progress and logged_progress.id is not None:
            try:
                text_to_embed = f"Progress: {logged_progress.status} - {logged_progress.description}"
                
                vector = embedding_service.get_embedding(text_to_embed.strip())
                
                metadata_for_vector = {
                    "conport_item_id": str(logged_progress.id),
                    "conport_item_type": "progress_entry",
                    "status": logged_progress.status,
                    "description_snippet": logged_progress.description[:100], # Snippet for quick view
                    "timestamp_created": logged_progress.timestamp.isoformat(),
                    "parent_id": str(logged_progress.parent_id) if logged_progress.parent_id else None
                }
                vector_store_service.upsert_item_embedding(
                    workspace_id=args.workspace_id,
                    item_type="progress_entry",
                    item_id=str(logged_progress.id),
                    vector=vector,
                    metadata=metadata_for_vector
                )
                log.info(f"Successfully generated and stored embedding for progress entry ID {logged_progress.id}")
            except Exception as e_embed:
                log.error(f"Failed to generate/store embedding for progress entry ID {logged_progress.id}: {e_embed}", exc_info=True)
        # --- End Add to Vector Store ---

        return logged_progress.model_dump(mode='json')
    except DatabaseError as e:
        raise ContextPortalError(f"Database error logging progress: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in log_progress for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in log_progress: {e}")

def handle_get_progress(args: models.GetProgressArgs) -> List[Dict[str, Any]]:
    """
    Handles the 'get_progress' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns a list of progress entry dictionaries.
    """
    try:
        progress_list = db.get_progress(
            args.workspace_id,
            status_filter=args.status_filter,
            parent_id_filter=args.parent_id_filter,
            limit=args.limit
        )
        return [p.model_dump(mode='json') for p in progress_list]
    except DatabaseError as e:
        raise ContextPortalError(f"Database error getting progress: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in get_progress for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in get_progress: {e}")

def handle_update_progress(args: models.UpdateProgressArgs) -> Dict[str, Any]:
    """
    Handles the 'update_progress' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns a status message dictionary.
    """
    try:
        updated = db.update_progress_entry(args.workspace_id, args)

        if updated:
            # --- Update Vector Store ---
            # --- Update Vector Store ---
            updated_entry = db.get_progress_entry_by_id(args.workspace_id, args.progress_id)
            if updated_entry:
                try:
                    text_to_embed = f"Progress: {updated_entry.status} - {updated_entry.description}"
                    vector = embedding_service.get_embedding(text_to_embed.strip())
                    
                    metadata_for_vector = {
                        "conport_item_id": str(updated_entry.id),
                        "conport_item_type": "progress_entry",
                        "status": updated_entry.status,
                        "description_snippet": updated_entry.description[:100],
                        "timestamp_created": updated_entry.timestamp.isoformat(), # Using existing timestamp as created_at for simplicity
                        "parent_id": str(updated_entry.parent_id) if updated_entry.parent_id else None
                    }
                    vector_store_service.upsert_item_embedding(
                        workspace_id=args.workspace_id,
                        item_type="progress_entry",
                        item_id=str(updated_entry.id),
                        vector=vector,
                        metadata=metadata_for_vector
                    )
                    log.info(f"Successfully updated embedding for progress entry ID {updated_entry.id}")
                except Exception as e_embed_update:
                    log.error(f"Failed to update embedding for progress entry ID {updated_entry.id}: {e_embed_update}", exc_info=True)
                    # Do not let embedding failure make the whole operation fail, but log it.
            else:
                # This case should ideally not be reached if 'updated' is true.
                log.warning(f"Progress entry ID {args.progress_id} was reportedly updated in DB, but could not be re-fetched for embedding update.")
            # --- End Update Vector Store ---

            return {"status": "success", "message": f"Progress entry ID {args.progress_id} updated successfully."}
        else:
            return {"status": "success", "message": f"Progress entry ID {args.progress_id} not found for update."}
    except ValueError as e: # Catch validation errors from the handler/db call
         raise ToolArgumentError(str(e))
    except DatabaseError as e:
        raise ContextPortalError(f"Database error updating progress entry ID {args.progress_id}: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in handle_update_progress for workspace {args.workspace_id}, ID {args.progress_id}")
        raise ContextPortalError(f"Unexpected error updating progress entry: {e}")

def handle_delete_progress_by_id(args: models.DeleteProgressByIdArgs) -> Dict[str, Any]:
    """
    Handles the 'delete_progress_by_id' MCP tool.
    Deletes a progress entry by its ID.
    """
    try:
        deleted_from_db = db.delete_progress_entry_by_id(args.workspace_id, args.progress_id)

        if deleted_from_db:
            try:
                # --- Delete from Vector Store ---
                vector_store_service.delete_item_embedding(
                    workspace_id=args.workspace_id,
                    item_type="progress_entry",
                    item_id=str(args.progress_id)
                )
                log.info(f"Successfully deleted embedding for progress entry ID {args.progress_id}")
                # --- End Delete from Vector Store ---
                return {"status": "success", "message": f"Progress entry ID {args.progress_id} and its embedding deleted successfully."}
            except Exception as e_vec_del:
                log.error(f"Failed to delete embedding for progress entry ID {args.progress_id} (DB record was deleted): {e_vec_del}", exc_info=True)
                # Return success for DB deletion but acknowledge embedding deletion failure.
                return {
                    "status": "partial_success",
                    "message": f"Progress entry ID {args.progress_id} deleted from database, but failed to delete its embedding: {e_vec_del}"
                }
        else:
            # This case means the ID was valid (e.g. integer) but not found in DB.
            # No need to attempt vector deletion if not found in DB.
            return {"status": "success", "message": f"Progress entry ID {args.progress_id} not found in database."}
    except DatabaseError as e:
        raise ContextPortalError(f"Database error deleting progress entry ID {args.progress_id}: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in handle_delete_progress_by_id for workspace {args.workspace_id}, ID {args.progress_id}")
        raise ContextPortalError(f"Unexpected error deleting progress entry: {e}")

def handle_log_system_pattern(args: models.LogSystemPatternArgs) -> Dict[str, Any]:
    """
    Handles the 'log_system_pattern' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns the logged system pattern as a dictionary.
    """
    try:
        pattern_to_log = models.SystemPattern(name=args.name, description=args.description, tags=args.tags)
        logged_pattern = db.log_system_pattern(args.workspace_id, pattern_to_log)

        # --- Add to Vector Store ---
        if logged_pattern and logged_pattern.id is not None:
            try:
                text_to_embed = f"System Pattern: {logged_pattern.name}\nDescription: {logged_pattern.description if logged_pattern.description else ''}"
                
                vector = embedding_service.get_embedding(text_to_embed.strip())
                
                metadata_for_vector = {
                    "conport_item_id": str(logged_pattern.id),
                    "conport_item_type": "system_pattern",
                    "name": logged_pattern.name,
                    "timestamp_created": logged_pattern.timestamp.isoformat(), # Assuming SystemPattern has a timestamp
                    "tags": logged_pattern.tags if logged_pattern.tags else []
                }
                vector_store_service.upsert_item_embedding(
                    workspace_id=args.workspace_id,
                    item_type="system_pattern",
                    item_id=str(logged_pattern.id),
                    vector=vector,
                    metadata=metadata_for_vector
                )
                log.info(f"Successfully generated and stored embedding for system pattern ID {logged_pattern.id}")
            except Exception as e_embed:
                log.error(f"Failed to generate/store embedding for system pattern ID {logged_pattern.id}: {e_embed}", exc_info=True)
        # --- End Add to Vector Store ---

        return logged_pattern.model_dump(mode='json')
    except DatabaseError as e:
        raise ContextPortalError(f"Database error logging system pattern: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in log_system_pattern for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in log_system_pattern: {e}")

def handle_get_system_patterns(args: models.GetSystemPatternsArgs) -> List[Dict[str, Any]]:
    """
    Handles the 'get_system_patterns' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns a list of system pattern dictionaries.
    """
    try:
        patterns_list = db.get_system_patterns(
            args.workspace_id,
            tags_filter_include_all=args.tags_filter_include_all,
            tags_filter_include_any=args.tags_filter_include_any
        )
        return [p.model_dump(mode='json') for p in patterns_list]
    except DatabaseError as e:
        raise ContextPortalError(f"Database error getting system patterns: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in get_system_patterns for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in get_system_patterns: {e}")

def handle_get_conport_schema(args: models.GetConportSchemaArgs) -> Dict[str, Dict[str, Any]]:
    """
    Handles the 'get_conport_schema' MCP tool.
    Retrieves the JSON schema for all registered ConPort tools.
    Assumes 'args' is an already validated Pydantic model instance.
    """
    try:
        log.info(f"Handling get_conport_schema for workspace {args.workspace_id}")
        tool_schemas: Dict[str, Dict[str, Any]] = {}
        for tool_name, model_class in models.TOOL_ARG_MODELS.items():
            # Ensure model_class is a Pydantic BaseModel before calling model_json_schema
            if hasattr(model_class, 'model_json_schema') and callable(model_class.model_json_schema):
                tool_schemas[tool_name] = model_class.model_json_schema()
            else:
                # This case should ideally not happen if TOOL_ARG_MODELS is correctly populated
                log.warning(f"Model class for tool '{tool_name}' is not a Pydantic model or does not have 'model_json_schema' method.")
                tool_schemas[tool_name] = {"error": "Schema not available"}
        
        return tool_schemas
    except Exception as e:
        log.exception(f"Unexpected error in get_conport_schema for workspace {args.workspace_id}")
        # Return a more structured error if possible, or a generic one
        raise ContextPortalError(f"Unexpected error retrieving ConPort schema: {e}")

def handle_get_recent_activity_summary(args: models.GetRecentActivitySummaryArgs) -> Dict[str, Any]:
    """
    Handles the 'get_recent_activity_summary' MCP tool.
    Retrieves a summary of recent activity from the database.
    """
    try:
        log.info(f"Handling get_recent_activity_summary for workspace {args.workspace_id} with args: {args.model_dump_json()}")
        summary_data = db.get_recent_activity_summary_data(
            workspace_id=args.workspace_id,
            hours_ago=args.hours_ago,
            since_timestamp=args.since_timestamp,
            limit_per_type=args.limit_per_type if args.limit_per_type is not None else 5 # Ensure default if None
        )
        return summary_data
    except DatabaseError as e:
        log.error(f"Database error in get_recent_activity_summary for workspace {args.workspace_id}: {e}")
        raise ContextPortalError(f"Database error retrieving recent activity: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in get_recent_activity_summary for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error retrieving recent activity: {e}")

def handle_log_custom_data(args: models.LogCustomDataArgs) -> Dict[str, Any]:
    """
    Handles the 'log_custom_data' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns the logged custom data entry as a dictionary.
    """
    try:
        data_to_log = models.CustomData(category=args.category, key=args.key, value=args.value)
        # Assuming CustomData model has a metadata field, or we add it if needed for cache_hint
        # For now, the LogCustomDataArgs does not have metadata.
        # If it did: data_to_log = models.CustomData(category=args.category, key=args.key, value=args.value, metadata=args.metadata)
        
        logged_data = db.log_custom_data(args.workspace_id, data_to_log)

        # --- Add to Vector Store ---
        if logged_data and logged_data.id is not None:
            # Only embed if value is string-like or can be reasonably converted to text
            text_to_embed = None
            if isinstance(logged_data.value, str):
                text_to_embed = logged_data.value
            elif isinstance(logged_data.value, (dict, list)):
                try:
                    # Simple JSON string representation for dict/list
                    text_to_embed = json.dumps(logged_data.value)
                except TypeError:
                    log.warning(f"Custom data value for {logged_data.category}/{logged_data.key} is not JSON serializable for embedding.")
            
            if text_to_embed:
                # Add category and key to text for better contextual embedding
                contextual_text_to_embed = f"Category: {logged_data.category}\nKey: {logged_data.key}\nValue: {text_to_embed}"
                try:
                    vector = embedding_service.get_embedding(contextual_text_to_embed.strip())
                    
                    metadata_for_vector = {
                        "conport_item_id": str(logged_data.id),
                        "conport_item_type": "custom_data",
                        "category": logged_data.category,
                        "key": logged_data.key,
                        "timestamp_created": logged_data.timestamp.isoformat(),
                        # "value_type": str(type(logged_data.value).__name__) # Could be useful metadata
                    }
                    # Add metadata from CustomData if it exists and is simple
                    if hasattr(logged_data, 'metadata') and isinstance(logged_data.metadata, dict):
                         for k, v in logged_data.metadata.items():
                            if isinstance(v, (str, int, float, bool)): # Only simple types for Chroma metadata
                                metadata_for_vector[f"custom_meta_{k}"] = v


                    vector_store_service.upsert_item_embedding(
                        workspace_id=args.workspace_id,
                        item_type="custom_data",
                        item_id=str(logged_data.id), # Using internal DB ID as part of Chroma ID
                        vector=vector,
                        metadata=metadata_for_vector
                    )
                    log.info(f"Successfully generated and stored embedding for custom_data ID {logged_data.id} ({logged_data.category}/{logged_data.key})")
                except Exception as e_embed:
                    log.error(f"Failed to generate/store embedding for custom_data ID {logged_data.id} ({logged_data.category}/{logged_data.key}): {e_embed}", exc_info=True)
            else:
                log.debug(f"Skipping embedding for custom_data ID {logged_data.id} ({logged_data.category}/{logged_data.key}) as value is not text-like.")
        # --- End Add to Vector Store ---
        
        return logged_data.model_dump(mode='json')
    except DatabaseError as e:
        raise ContextPortalError(f"Database error logging custom data: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in log_custom_data for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in log_custom_data: {e}")

def handle_get_custom_data(args: models.GetCustomDataArgs) -> List[Dict[str, Any]]:
    """
    Handles the 'get_custom_data' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns a list of custom data entry dictionaries.
    """
    try:
        data_list = db.get_custom_data(args.workspace_id, category=args.category, key=args.key)
        return [d.model_dump(mode='json') for d in data_list]
    except ValueError as e: # From db function if key w/o category, or other validation
         raise ToolArgumentError(str(e)) # Pass specific error message
    except DatabaseError as e:
        raise ContextPortalError(f"Database error getting custom data: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in get_custom_data for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in get_custom_data: {e}")

def handle_delete_custom_data(args: models.DeleteCustomDataArgs) -> Dict[str, Any]:
    """
    Handles the 'delete_custom_data' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns a status message dictionary.
    """
    try:
        deleted = db.delete_custom_data(args.workspace_id, category=args.category, key=args.key)
        if deleted:
            return {"status": "success", "message": f"Custom data '{args.category}/{args.key}' deleted."}
        else:
            return {"status": "success", "message": f"Custom data '{args.category}/{args.key}' not found for deletion."}
    except DatabaseError as e:
        raise ContextPortalError(f"Database error deleting custom data: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in delete_custom_data for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in delete_custom_data: {e}")

def handle_search_project_glossary_fts(args: models.SearchProjectGlossaryArgs) -> List[Dict[str, Any]]:
    """
    Handles the 'search_project_glossary_fts' MCP tool.
    Assumes 'args' is an already validated Pydantic model instance.
    Returns a list of glossary entry dictionaries.
    """
    try:
        glossary_entries = db.search_project_glossary_fts(
            args.workspace_id,
            query_term=args.query_term,
            limit=args.limit
        )
        return [entry.model_dump(mode='json') for entry in glossary_entries]
    except DatabaseError as e:
        raise ContextPortalError(f"Database error searching project glossary: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in search_project_glossary_fts for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error in search_project_glossary_fts: {e}")

def handle_search_custom_data_value_fts(args: models.SearchCustomDataValueArgs) -> List[Dict[str, Any]]:
    """
    Handles the 'search_custom_data_value_fts' MCP tool.
    Searches custom data entries using FTS, optionally filtered by category.
    """
    try:
        results = db.search_custom_data_value_fts(
            args.workspace_id,
            query_term=args.query_term,
            category_filter=args.category_filter,
            limit=args.limit
        )
        return [item.model_dump(mode='json') for item in results]
    except DatabaseError as e:
        raise ContextPortalError(f"Database error searching custom data values: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in search_custom_data_value_fts for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error searching custom data values: {e}")

# --- Semantic Search Handler ---

async def handle_semantic_search_conport(args: models.SemanticSearchConportArgs) -> List[Dict[str, Any]]:
    """
    Handles the 'semantic_search_conport' MCP tool.
    Performs a semantic search using embeddings and vector store, with optional metadata filters.
    """
    try:
        log.info(f"Handling semantic_search_conport for workspace {args.workspace_id} with query: '{args.query_text[:50]}...'")

        query_vector = embedding_service.get_embedding(args.query_text)

        # Construct ChromaDB filters
        chroma_filters = {}
        and_conditions = []

        if args.filter_item_types:
            and_conditions.append({"conport_item_type": {"$in": args.filter_item_types}})
        
        if args.filter_tags_include_all:
            # For $all behavior with $contains, we need an $and for each tag
            tag_all_conditions = [{"tags": {"$contains": tag}} for tag in args.filter_tags_include_all]
            if tag_all_conditions:
                and_conditions.append({"$and": tag_all_conditions})
        
        if args.filter_tags_include_any:
            # For $or behavior with $contains
            tag_any_conditions = [{"tags": {"$contains": tag}} for tag in args.filter_tags_include_any]
            if tag_any_conditions:
                and_conditions.append({"$or": tag_any_conditions})
        
        if args.filter_custom_data_categories:
            # This filter is only meaningful if 'custom_data' is in item_types or no item_types are specified
            category_condition = {"category": {"$in": args.filter_custom_data_categories}}
            if args.filter_item_types and 'custom_data' in args.filter_item_types:
                and_conditions.append(category_condition)
            elif not args.filter_item_types: # If no item_type filter, apply category filter broadly (might hit non-custom_data items if they had 'category' metadata)
                 and_conditions.append(category_condition)


        if and_conditions:
            if len(and_conditions) == 1:
                chroma_filters = and_conditions[0]
            else:
                chroma_filters = {"$and": and_conditions}
        
        log.debug(f"ChromaDB query filters: {chroma_filters}")

        search_results = vector_store_service.query_vector_store(
            workspace_id=args.workspace_id,
            query_vector=query_vector,
            top_k=args.top_k,
            filters=chroma_filters if chroma_filters else None
        )

        # Process results: search_results is List[Dict] with 'chroma_doc_id', 'distance', 'metadata'
        # We need to potentially fetch full items from SQLite based on metadata.conport_item_id and conport_item_type
        # For now, just return the direct results from vector store, which includes metadata.
        # A more advanced version would re-hydrate with full SQLite objects.
        
        # Example of enriching results (conceptual, actual DB calls would be needed)
        enriched_results = []
        for res in search_results:
            meta = res.get("metadata", {})
            item_id = meta.get("conport_item_id")
            item_type = meta.get("conport_item_type")
            
            # Here you could fetch the full item from SQLite using item_id and item_type
            # For example:
            # if item_type == "decision" and item_id:
            #     full_item = db.get_decision_by_id(args.workspace_id, int(item_id)) # Assuming get_decision_by_id exists
            #     res["full_item_data"] = full_item.model_dump(mode='json') if full_item else None
            # else if item_type == "custom_data" and item_id:
            #     # For custom_data, ID is internal. Key and Category are in metadata.
            #     full_item_list = db.get_custom_data(args.workspace_id, category=meta.get("category"), key=meta.get("key"))
            #     if full_item_list:
            #         res["full_item_data"] = full_item_list[0].model_dump(mode='json')


            enriched_results.append(res) # For now, just pass through

        return enriched_results

    except RuntimeError as re: # Catch errors from embedding or vector store service
        log.error(f"Runtime error during semantic search: {re}", exc_info=True)
        raise ContextPortalError(f"Error during semantic search operation: {re}")
    except DatabaseError as dbe: # Catch errors from SQLite if enriching results
        log.error(f"Database error during semantic search result enrichment: {dbe}", exc_info=True)
        raise ContextPortalError(f"Database error processing semantic search results: {dbe}")
    except Exception as e:
        log.exception(f"Unexpected error in handle_semantic_search_conport for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error during semantic search: {type(e).__name__}")

# --- Export Tool Handler ---

def _format_product_context_md(data: Dict[str, Any]) -> str:
    lines = ["# Product Context\n"]
    for key, value in data.items():
        heading = key.replace("_", " ").title()
        lines.append(f"## {heading}\n")
        if isinstance(value, str):
            lines.append(value.strip() + "\n")
        elif isinstance(value, list):
            for item in value:
                lines.append(f"*   {item}\n")
        else: # Fallback for other types
            lines.append(str(value) + "\n")
        lines.append("\n")
    return "".join(lines)

def _format_active_context_md(data: Dict[str, Any]) -> str:
    lines = ["# Active Context\n"]
    # Expected keys: introduction, currentFocus, recentChanges, openQuestionsIssues
    if data.get("introduction"):
        lines.append(data["introduction"].strip() + "\n\n")
    
    if data.get("currentFocus"):
        lines.append("## Current Focus\n")
        lines.append(data["currentFocus"].strip() + "\n\n")
    
    if data.get("recentChanges"):
        lines.append("## Recent Changes\n")
        if isinstance(data["recentChanges"], list):
            for item in data["recentChanges"]:
                lines.append(f"*   {str(item).strip()}\n")
            lines.append("\n")
        elif isinstance(data["recentChanges"], str):
            lines.append(data["recentChanges"].strip() + "\n\n")
        else:
            lines.append(str(data["recentChanges"]) + "\n\n")

    if data.get("openQuestionsIssues"):
        lines.append("## Open Questions/Issues\n")
        if isinstance(data["openQuestionsIssues"], list):
            for item in data["openQuestionsIssues"]:
                lines.append(f"*   {str(item).strip()}\n")
            lines.append("\n")
        elif isinstance(data["openQuestionsIssues"], str):
            lines.append(data["openQuestionsIssues"].strip() + "\n\n")
        else:
            lines.append(str(data["openQuestionsIssues"]) + "\n\n")
    return "".join(lines)

def _format_decisions_md(decisions: List[models.Decision]) -> str:
    lines = ["# Decision Log\n"]
    for dec in sorted(decisions, key=lambda x: x.timestamp, reverse=True):
        lines.append("\n---\n")
        lines.append("## Decision\n")
        lines.append(f"*   [{dec.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {dec.summary}\n")
        if dec.rationale:
            lines.append("\n## Rationale\n")
            lines.append(f"*   {dec.rationale}\n")
        if dec.implementation_details:
            lines.append("\n## Implementation Details\n")
            lines.append(f"*   {dec.implementation_details}\n")
    return "".join(lines)

def _format_progress_md(progress_entries: List[models.ProgressEntry]) -> str:
    lines = ["# Progress Log\n"]
    status_map = {"DONE": [], "IN_PROGRESS": [], "TODO": []}
    for entry in sorted(progress_entries, key=lambda x: x.timestamp, reverse=True):
        status_map.get(entry.status, status_map["TODO"]).append(entry)

    if status_map["DONE"]:
        lines.append("\n## Completed Tasks\n")
        for entry in status_map["DONE"]:
            lines.append(f"*   [{entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {entry.description}\n")
    if status_map["IN_PROGRESS"]:
        lines.append("\n## In Progress Tasks\n")
        for entry in status_map["IN_PROGRESS"]:
            lines.append(f"*   [{entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {entry.description}\n")
    if status_map["TODO"]:
        lines.append("\n## TODO Tasks\n")
        for entry in status_map["TODO"]:
            lines.append(f"*   [{entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {entry.description}\n")
    return "".join(lines)

def _format_system_patterns_md(patterns: List[models.SystemPattern]) -> str:
    lines = ["# System Patterns\n"]
    for pattern in sorted(patterns, key=lambda x: x.name):
        lines.append(f"\n## {pattern.name}\n")
        if pattern.description:
            lines.append(f"{pattern.description}\n")
    return "".join(lines)

def handle_export_conport_to_markdown(args: models.ExportConportToMarkdownArgs) -> Dict[str, Any]:
    """
    Exports all ConPort data for a workspace to markdown files.
    Assumes 'args' is an already validated Pydantic model instance.
    """
    workspace_path = Path(args.workspace_id)
    output_dir_name = args.output_path if args.output_path else "conport_export"
    output_path = workspace_path / output_dir_name

    try:
        output_path.mkdir(parents=True, exist_ok=True)
        log.info(f"Exporting ConPort data for workspace '{args.workspace_id}' to '{output_path}'")

        files_created = []

        # Product Context
        product_ctx_data = db.get_product_context(args.workspace_id).content
        if product_ctx_data:
            (output_path / "product_context.md").write_text(_format_product_context_md(product_ctx_data))
            files_created.append("product_context.md")

        # Active Context
        active_ctx_data = db.get_active_context(args.workspace_id).content
        if active_ctx_data:
            (output_path / "active_context.md").write_text(_format_active_context_md(active_ctx_data))
            files_created.append("active_context.md")
        
        # Decisions
        decisions = db.get_decisions(args.workspace_id, limit=None) # Get all
        if decisions:
            (output_path / "decision_log.md").write_text(_format_decisions_md(decisions))
            files_created.append("decision_log.md")

        # Progress
        progress_entries = db.get_progress(args.workspace_id, limit=None) # Get all
        if progress_entries:
            (output_path / "progress_log.md").write_text(_format_progress_md(progress_entries))
            files_created.append("progress_log.md")

        # System Patterns
        system_patterns = db.get_system_patterns(args.workspace_id)
        if system_patterns:
            (output_path / "system_patterns.md").write_text(_format_system_patterns_md(system_patterns))
            files_created.append("system_patterns.md")

        # Custom Data
        custom_data_entries = db.get_custom_data(args.workspace_id)
        if custom_data_entries:
            custom_data_path = output_path / "custom_data"
            custom_data_path.mkdir(exist_ok=True)
            categories: Dict[str, List[str]] = {}
            for item in custom_data_entries:
                if item.category not in categories:
                    categories[item.category] = []
                
                value_str = json.dumps(item.value, indent=2) if not isinstance(item.value, str) else item.value
                categories[item.category].append(f"### {item.key}\n\n```json\n{value_str}\n```\n")
            
            for category_name_from_loop, items_md in categories.items(): # Renamed category to avoid clash
                cat_file_name = "".join(c if c.isalnum() else "_" for c in category_name_from_loop) + ".md"
                (custom_data_path / cat_file_name).write_text(f"# Custom Data: {category_name_from_loop}\n\n" + "\n---\n".join(items_md))
                files_created.append(f"custom_data/{cat_file_name}")
        
        return {"status": "success", "message": f"ConPort data exported to '{output_path}'. Files created: {', '.join(files_created)}"}

    except DatabaseError as e:
        raise ContextPortalError(f"Database error during export: {e}")
    except IOError as e:
        raise ContextPortalError(f"File system error during export to '{output_path}': {e}")
    except Exception as e:
        log.exception(f"Unexpected error in export_conport_to_markdown for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error during export: {e}")

# --- Import Tool Handler ---

def _parse_key_value_markdown_section(section_content: str) -> str:
    """Helper to extract content from a simple markdown section."""
    lines = [line.strip() for line in section_content.strip().split('\n') if line.strip()]
    # Remove potential list markers like '* '
    cleaned_lines = [re.sub(r"^\*   ", "", line) for line in lines]
    return "\n".join(cleaned_lines).strip()

def _parse_product_or_active_context_md(content: str) -> Dict[str, Any]:
    """Parses product_context.md or active_context.md content."""
    data = {}
    # Split by '## ' to get sections, ignoring the initial '# Title' part
    sections = re.split(r'\n## ', content)[1:]
    
    # First section is usually an introduction before the first '## '
    intro_match = re.match(r'^#\s\w+\sContext\n+(.*?)\n## ', content, re.DOTALL | re.MULTILINE)
    if intro_match:
        data["introduction"] = intro_match.group(1).strip()

    for section in sections:
        parts = section.split('\n', 1)
        heading_full = parts[0].strip()
        section_content = parts[1] if len(parts) > 1 else ""
        
        # Create a key from the heading (e.g., "Project Goal" -> "projectGoal")
        key = heading_full.replace(" ", "")
        key = key[0].lower() + key[1:] if key else ""

        if key: # Ensure key is not empty
             # For "Recent Changes", we expect a list-like structure.
            if "Recent Changes" in heading_full:
                 data[key] = _parse_key_value_markdown_section(section_content) # Keep as single string
            else:
                data[key] = _parse_key_value_markdown_section(section_content)
    return data

def _parse_decisions_md(content: str) -> List[Dict[str, str]]:
    """Parses decision_log.md content."""
    decisions = []
    # Split by '---' separator, then process each decision block
    decision_blocks = content.split('\n---\n')
    for block in decision_blocks:
        if not block.strip() or "## Decision" not in block :
            continue
        
        summary_match = re.search(r"## Decision\n\*\s*\[.*?\]\s*(.+)", block, re.DOTALL)
        summary = summary_match.group(1).strip() if summary_match else "N/A"
        
        rationale_match = re.search(r"## Rationale\n\*\s*(.+)", block, re.DOTALL)
        rationale = rationale_match.group(1).strip() if rationale_match else None
        # Handle multi-line rationale
        if rationale_match and '\n*' in rationale: # crude check for multi-bullet rationale
            rationale = "\n".join([line.strip().lstrip('*').strip() for line in rationale.split('\n')])


        impl_details_match = re.search(r"## Implementation Details\n\*\s*(.+)", block, re.DOTALL)
        impl_details = impl_details_match.group(1).strip() if impl_details_match else None
        if impl_details_match and '\n*' in impl_details: # crude check for multi-bullet details
            impl_details = "\n".join([line.strip().lstrip('*').strip() for line in impl_details.split('\n')])

        decisions.append({
            "summary": summary,
            "rationale": rationale,
            "implementation_details": impl_details
        })
    return decisions

def _parse_progress_md(content: str) -> List[Dict[str, str]]:
    """Parses progress_log.md content."""
    progress_items = []
    current_status = "TODO" # Default
    
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith("## Completed Tasks"):
            current_status = "DONE"
        elif line.startswith("## In Progress Tasks") or line.startswith("## Current Tasks"):
            current_status = "IN_PROGRESS"
        elif line.startswith("## TODO Tasks") or line.startswith("## Next Steps"):
            current_status = "TODO"
        elif line.startswith("*"):
            description = re.sub(r"^\*\s*(\[.*?\]\s*)?", "", line).strip()
            if description:
                progress_items.append({"status": current_status, "description": description})
    return progress_items

def _parse_system_patterns_md(content: str) -> List[Dict[str, str]]:
    """Parses system_patterns.md content."""
    patterns = []
    current_name = None
    current_desc_lines = []

    for line in content.split('\n'):
        line = line.strip()
        if line.startswith("## "):
            if current_name: # Save previous pattern
                patterns.append({"name": current_name, "description": "\n".join(current_desc_lines).strip() or None})
                current_desc_lines = []
            current_name = line[3:].strip()
        elif current_name and line and not line.startswith("#"):
            current_desc_lines.append(line)
    
    if current_name: # Save the last pattern
        patterns.append({"name": current_name, "description": "\n".join(current_desc_lines).strip() or None})
    return patterns

def _parse_custom_data_category_md(content: str, category_name: str) -> List[Dict[str, Any]]:
    """Parses a custom_data category markdown file."""
    items = []
    # Split by '### ' for keys, then parse the JSON block
    key_blocks = re.split(r'\n### ', content)
    for block in key_blocks:
        if not block.strip() or "```json" not in block:
            continue
        
        key_match = re.match(r"(.+?)\n+```json\n(.*?)\n```", block.strip(), re.DOTALL | re.MULTILINE)
        if key_match:
            key = key_match.group(1).strip()
            json_str_value = key_match.group(2).strip()
            try:
                value = json.loads(json_str_value)
                items.append({"category": category_name, "key": key, "value": value})
            except json.JSONDecodeError as e:
                log.warning(f"Could not parse JSON for custom data {category_name}/{key}: {e}. Value: '{json_str_value}'")
    return items


def handle_import_markdown_to_conport(args: models.ImportMarkdownToConportArgs) -> Dict[str, Any]:
    """
    Imports data from markdown files into ConPort for a workspace.
    Assumes 'args' is an already validated Pydantic model instance.
    """
    workspace_path = Path(args.workspace_id)
    input_dir_name = args.input_path if args.input_path else "conport_export"
    input_path = workspace_path / input_dir_name

    if not input_path.is_dir():
        raise ToolArgumentError(f"Input directory not found: {input_path}")

    log.info(f"Importing ConPort data for workspace '{args.workspace_id}' from '{input_path}'")
    summary_report = {"status": "success", "message": "Import process initiated.", "files_processed": [], "items_logged": {}, "errors": []}

    # This handler will be called by a tool wrapper in main.py.
    # It calls other refactored handlers in this file.
    
    # Define which handler and Pydantic model to use for each file type
    file_processing_map = {
        "product_context.md": (_parse_product_or_active_context_md, handle_update_product_context, models.UpdateContextArgs),
        "active_context.md": (_parse_product_or_active_context_md, handle_update_active_context, models.UpdateContextArgs),
        "decision_log.md": (_parse_decisions_md, handle_log_decision, models.LogDecisionArgs),
        "progress_log.md": (_parse_progress_md, handle_log_progress, models.LogProgressArgs),
        "system_patterns.md": (_parse_system_patterns_md, handle_log_system_pattern, models.LogSystemPatternArgs),
    }

    for filename, (parser_func, target_handler_func, pydantic_arg_model) in file_processing_map.items():
        file_to_import = input_path / filename
        if file_to_import.is_file():
            try:
                content_str = file_to_import.read_text(encoding="utf-8")
                parsed_data = parser_func(content_str)
                summary_report["files_processed"].append(filename)
                
                item_type_key = filename.split('.')[0] # Define item_type_key

                if item_type_key in ["product_context", "active_context"]:
                    # For these, parsed_data is the content dict itself
                    handler_call_args = pydantic_arg_model(workspace_id=args.workspace_id, content=parsed_data)
                    target_handler_func(handler_call_args)
                    summary_report["items_logged"][item_type_key] = summary_report["items_logged"].get(item_type_key, 0) + 1
                else: # List based items (decisions, progress, system_patterns)
                    for item_data in parsed_data: # parsed_data is a list of dicts
                        handler_call_args = pydantic_arg_model(workspace_id=args.workspace_id, **item_data)
                        target_handler_func(handler_call_args)
                        summary_report["items_logged"][item_type_key] = summary_report["items_logged"].get(item_type_key, 0) + 1
            except Exception as e:
                log.error(f"Error processing file {filename}: {e}")
                summary_report["errors"].append(f"Error processing {filename}: {str(e)}")
        else:
            log.warning(f"File not found for import: {file_to_import}")
            summary_report["errors"].append(f"File not found: {filename}")
            
    # Custom Data
    custom_data_dir = input_path / "custom_data"
    if custom_data_dir.is_dir():
        summary_report["files_processed"].append("custom_data/*")
        for category_md_file in custom_data_dir.glob("*.md"): # Renamed variable
            try:
                category_name = category_md_file.stem.replace("_", " ")
                content_str = category_md_file.read_text(encoding="utf-8")
                parsed_custom_items = _parse_custom_data_category_md(content_str, category_name)
                for item_data in parsed_custom_items:
                    # item_data already contains 'category', 'key', 'value'
                    handler_args = models.LogCustomDataArgs(workspace_id=args.workspace_id, **item_data)
                    handle_log_custom_data(handler_args)
                    summary_report["items_logged"]["custom_data"] = summary_report["items_logged"].get("custom_data", 0) + 1
            except Exception as e:
                log.error(f"Error processing custom data file {category_md_file.name}: {e}")
                summary_report["errors"].append(f"Error processing {category_md_file.name}: {str(e)}")
    
    summary_report["message"] = f"ConPort data import from '{input_path}' complete. See details."
    return summary_report

def handle_link_conport_items(args: models.LinkConportItemsArgs) -> Dict[str, Any]:
    """
    Handles the 'link_conport_items' MCP tool.
    Creates a link between two ConPort items.
    """
    try:
        link_to_create = models.ContextLink(
            source_item_type=args.source_item_type,
            source_item_id=args.source_item_id,
            target_item_type=args.target_item_type,
            target_item_id=args.target_item_id,
            relationship_type=args.relationship_type,
            description=args.description
            # workspace_id is handled by the db function based on connection
            # timestamp is handled by Pydantic model default_factory
        )
        logged_link = db.log_context_link(args.workspace_id, link_to_create)
        return logged_link.model_dump(mode='json')
    except DatabaseError as e:
        raise ContextPortalError(f"Database error linking ConPort items: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in link_conport_items for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error linking ConPort items: {e}")

def handle_get_linked_items(args: models.GetLinkedItemsArgs) -> List[Dict[str, Any]]:
    """
    Handles the 'get_linked_items' MCP tool.
    Retrieves links for a given ConPort item, with optional filters.
    """
    try:
        links_list = db.get_context_links(
            workspace_id=args.workspace_id,
            item_type=args.item_type,
            item_id=args.item_id,
            relationship_type_filter=args.relationship_type_filter,
            linked_item_type_filter=args.linked_item_type_filter,
            limit=args.limit
        )
        return [link.model_dump(mode='json') for link in links_list]
    except DatabaseError as e:
        raise ContextPortalError(f"Database error retrieving context links: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in get_linked_items for workspace {args.workspace_id}")
        raise ContextPortalError(f"Unexpected error retrieving context links: {e}")

def handle_get_item_history(args: models.GetItemHistoryArgs) -> List[Dict[str, Any]]:
    """
    Handles the 'get_item_history' MCP tool.
    Retrieves history for product_context or active_context.
    """
    try:
        # Pydantic model GetItemHistoryArgs already validates item_type
        history_entries = db.get_item_history(args.workspace_id, args)
        # The db.get_item_history function already returns a list of dicts
        # where content is a dict and timestamp is a datetime object.
        # We need to ensure timestamps are JSON serializable for the MCP response.
        
        serializable_history = []
        for entry in history_entries:
            entry_copy = entry.copy() # Avoid modifying the original dict from db
            if isinstance(entry_copy.get("timestamp"), datetime):
                entry_copy["timestamp"] = entry_copy["timestamp"].isoformat()
            serializable_history.append(entry_copy)
            
        return serializable_history
    except ValueError as e: # From db function if item_type is somehow invalid post-Pydantic
         raise ToolArgumentError(str(e))
    except DatabaseError as e:
        raise ContextPortalError(f"Database error retrieving item history for {args.item_type}: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in get_item_history for workspace {args.workspace_id}, item_type {args.item_type}")
        raise ContextPortalError(f"Unexpected error retrieving item history: {e}")

# --- Batch Logging Handler ---

_SINGLE_ITEM_HANDLERS_MAP = {
    "decision": (handle_log_decision, models.LogDecisionArgs),
    "progress_entry": (handle_log_progress, models.LogProgressArgs),
    "system_pattern": (handle_log_system_pattern, models.LogSystemPatternArgs),
    "custom_data": (handle_log_custom_data, models.LogCustomDataArgs),
    # Add other loggable item types here if needed
}

def handle_batch_log_items(args: models.BatchLogItemsArgs) -> Dict[str, Any]:
    """
    Handles the 'batch_log_items' MCP tool.
    Logs multiple items of a specified type.
    """
    if args.item_type not in _SINGLE_ITEM_HANDLERS_MAP:
        raise ToolArgumentError(f"Unsupported item_type for batch logging: {args.item_type}. Supported types: {list(_SINGLE_ITEM_HANDLERS_MAP.keys())}")

    handler_func, pydantic_model = _SINGLE_ITEM_HANDLERS_MAP[args.item_type]
    
    results = []
    errors = []
    success_count = 0
    failure_count = 0

    for i, item_data_dict in enumerate(args.items):
        try:
            # Each item_data_dict needs workspace_id for the Pydantic model
            item_args_with_ws = {"workspace_id": args.workspace_id, **item_data_dict}
            validated_item_args = pydantic_model(**item_args_with_ws)
            result = handler_func(validated_item_args)
            results.append(result)
            success_count += 1
        except ValidationError as ve:
            log.error(f"Validation error for item {i} in batch_log_items ({args.item_type}): {ve}")
            errors.append({"item_index": i, "error": str(ve), "data": item_data_dict})
            failure_count += 1
        except ContextPortalError as cpe:
            log.error(f"ContextPortalError for item {i} in batch_log_items ({args.item_type}): {cpe}")
            errors.append({"item_index": i, "error": str(cpe), "data": item_data_dict})
            failure_count += 1
        except Exception as e:
            log.exception(f"Unexpected error for item {i} in batch_log_items ({args.item_type})")
            errors.append({"item_index": i, "error": f"Unexpected server error: {type(e).__name__}", "data": item_data_dict})
            failure_count += 1
            
    return {
        "status": "partial_success" if success_count > 0 and failure_count > 0 else ("success" if failure_count == 0 else "failure"),
        "message": f"Batch log for '{args.item_type}': {success_count} succeeded, {failure_count} failed.",
        "successful_items": results,
        "failed_items": errors
    }

# --- Deletion Tool Handlers ---

def handle_delete_decision_by_id(args: models.DeleteDecisionByIdArgs) -> Dict[str, Any]:
    """
    Handles the 'delete_decision_by_id' MCP tool.
    Deletes a decision by its ID.
    """
    try:
        deleted_from_db = db.delete_decision_by_id(args.workspace_id, args.decision_id)
        
        if deleted_from_db:
            try:
                vector_store_service.delete_item_embedding(
                    workspace_id=args.workspace_id,
                    item_type="decision",
                    item_id=str(args.decision_id)
                )
                log.info(f"Successfully deleted embedding for decision ID {args.decision_id}")
                return {"status": "success", "message": f"Decision ID {args.decision_id} and its embedding deleted successfully."}
            except Exception as e_vec_del:
                log.error(f"Failed to delete embedding for decision ID {args.decision_id} (DB record was deleted): {e_vec_del}", exc_info=True)
                # Return success for DB deletion but acknowledge embedding deletion failure.
                return {
                    "status": "partial_success",
                    "message": f"Decision ID {args.decision_id} deleted from database, but failed to delete its embedding: {e_vec_del}"
                }
        else:
            # This case means the ID was valid (e.g. integer) but not found in DB.
            # No need to attempt vector deletion if not found in DB.
            return {"status": "success", "message": f"Decision ID {args.decision_id} not found in database."}
    except DatabaseError as e:
        raise ContextPortalError(f"Database error deleting decision ID {args.decision_id}: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in delete_decision_by_id for workspace {args.workspace_id}, decision ID {args.decision_id}")
        raise ContextPortalError(f"Unexpected error deleting decision: {e}")

def handle_delete_system_pattern_by_id(args: models.DeleteSystemPatternByIdArgs) -> Dict[str, Any]:
    """
    Handles the 'delete_system_pattern_by_id' MCP tool.
    Deletes a system pattern by its ID.
    """
    try:
        deleted_from_db = db.delete_system_pattern_by_id(args.workspace_id, args.pattern_id)
        
        if deleted_from_db:
            try:
                vector_store_service.delete_item_embedding(
                    workspace_id=args.workspace_id,
                    item_type="system_pattern",
                    item_id=str(args.pattern_id)
                )
                log.info(f"Successfully deleted embedding for system pattern ID {args.pattern_id}")
                return {"status": "success", "message": f"System pattern ID {args.pattern_id} and its embedding deleted successfully."}
            except Exception as e_vec_del:
                log.error(f"Failed to delete embedding for system pattern ID {args.pattern_id} (DB record was deleted): {e_vec_del}", exc_info=True)
                return {
                    "status": "partial_success",
                    "message": f"System pattern ID {args.pattern_id} deleted from database, but failed to delete its embedding: {e_vec_del}"
                }
        else:
            return {"status": "success", "message": f"System pattern ID {args.pattern_id} not found in database."}
    except DatabaseError as e:
        raise ContextPortalError(f"Database error deleting system pattern ID {args.pattern_id}: {e}")
    except Exception as e:
        log.exception(f"Unexpected error in delete_system_pattern_by_id for workspace {args.workspace_id}, pattern ID {args.pattern_id}")
        raise ContextPortalError(f"Unexpected error deleting system pattern: {e}")

# --- Obsolete MCP Dispatcher Logic ---
# The following (TOOL_DESCRIPTIONS, handle_list_tools, TOOL_HANDLERS, dispatch_tool)
# are now obsolete as FastMCP handles tool registration, listing, and dispatch.
# They are removed to prevent confusion and ensure the new FastMCP mechanism is used.