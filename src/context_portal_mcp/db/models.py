"""Pydantic models for data validation and structure, mirroring the database schema."""

from pydantic import BaseModel, Field, Json, model_validator
from typing import Optional, Dict, Any, List, Annotated
from datetime import datetime

# --- Base Models ---

class BaseContextModel(BaseModel):
    """Base model for single-row context tables."""
    id: int = 1 # Assuming single row with ID 1
    content: Dict[str, Any] # Store actual data as a dictionary

# --- Table Models ---

class ProductContext(BaseContextModel):
    """Model for the product_context table."""
    pass # Inherits structure from BaseContextModel

class ActiveContext(BaseContextModel):
    """Model for the active_context table."""
    pass # Inherits structure from BaseContextModel

class Decision(BaseModel):
    """Model for the decisions table."""
    id: Optional[int] = None # Auto-incremented by DB
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    summary: str
    rationale: Optional[str] = None
    implementation_details: Optional[str] = None
    tags: Optional[List[str]] = Field(None, description="Optional tags for categorization")

class ProgressEntry(BaseModel):
    """Model for the progress_entries table."""
    id: Optional[int] = None # Auto-incremented by DB
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str # e.g., 'TODO', 'IN_PROGRESS', 'DONE'
    description: str
    parent_id: Optional[int] = None # For subtasks

class SystemPattern(BaseModel):
    """Model for the system_patterns table."""
    id: Optional[int] = None # Auto-incremented by DB
    name: str # Should be unique
    description: Optional[str] = None
    tags: Optional[List[str]] = Field(None, description="Optional tags for categorization")
    timestamp_created: datetime = Field(default_factory=datetime.utcnow)
    timestamp_updated: datetime = Field(default_factory=datetime.utcnow)

class CustomData(BaseModel):
    """Model for the custom_data table."""
    id: Optional[int] = None # Auto-incremented by DB
    category: str
    key: str
    value: Any # Store arbitrary JSON data (SQLAlchemy handles JSON str conversion for DB)
    timestamp_created: datetime = Field(default_factory=datetime.utcnow)
    timestamp_updated: datetime = Field(default_factory=datetime.utcnow)

# --- Context History Models ---

class ProductContextHistory(BaseModel):
    """Model for the product_context_history table."""
    id: Optional[int] = None # Auto-incremented by DB
    timestamp: datetime = Field(default_factory=datetime.utcnow) # When this history record was created
    version: int # Version number for this context, incremented on each change
    content: Dict[str, Any] # The content of ProductContext at this version
    change_source: Optional[str] = Field(None, description="Brief description of what triggered the change, e.g., tool name or user action")

class ActiveContextHistory(BaseModel):
    """Model for the active_context_history table."""
    id: Optional[int] = None # Auto-incremented by DB
    timestamp: datetime = Field(default_factory=datetime.utcnow) # When this history record was created
    version: int # Version number for this context, incremented on each change
    content: Dict[str, Any] # The content of ActiveContext at this version
    change_source: Optional[str] = Field(None, description="Brief description of what triggered the change, e.g., tool name or user action")

# --- MCP Tool Argument Models ---

class BaseArgs(BaseModel):
    """Base model for arguments requiring a workspace ID."""
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")]

# --- Context Tools ---

class GetContextArgs(BaseArgs):
    """Arguments for getting product or active context (only workspace_id needed)."""
    pass

class UpdateContextArgs(BaseArgs):
    """Arguments for updating product or active context.
    Provide either 'content' for a full update or 'patch_content' for a partial update.
    """
    content: Optional[Dict[str, Any]] = Field(None, description="The full new context content as a dictionary. Overwrites existing.")
    patch_content: Optional[Dict[str, Any]] = Field(None, description="A dictionary of changes to apply to the existing context (add/update keys).")

    @model_validator(mode='before')
    @classmethod
    def check_content_or_patch(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        content, patch_content = values.get('content'), values.get('patch_content')
        if content is None and patch_content is None:
            raise ValueError("Either 'content' or 'patch_content' must be provided.")
        if content is not None and patch_content is not None:
            raise ValueError("Provide either 'content' for a full update or 'patch_content' for a partial update, not both.")
        return values

# --- Decision Tools ---

class LogDecisionArgs(BaseArgs):
    """Arguments for logging a decision."""
    summary: str = Field(..., min_length=1, description="A concise summary of the decision")
    rationale: Optional[str] = Field(None, description="The reasoning behind the decision")
    implementation_details: Optional[str] = Field(None, description="Details about how the decision will be/was implemented")
    tags: Optional[List[str]] = Field(None, description="Optional tags for categorization")

class GetDecisionsArgs(BaseArgs):
    """Arguments for retrieving decisions."""
    limit: Optional[int] = Field(None, gt=0, description="Maximum number of decisions to return (most recent first)")
    tags_filter_include_all: Optional[List[str]] = Field(None, description="Filter: items must include ALL of these tags.")
    tags_filter_include_any: Optional[List[str]] = Field(None, description="Filter: items must include AT LEAST ONE of these tags.")

    @model_validator(mode='before')
    @classmethod
    def check_tag_filters(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if values.get('tags_filter_include_all') and values.get('tags_filter_include_any'):
            raise ValueError("Cannot use 'tags_filter_include_all' and 'tags_filter_include_any' simultaneously.")
        return values

class SearchDecisionsArgs(BaseArgs):
    """Arguments for searching decisions using FTS."""
    query_term: str = Field(..., min_length=1, description="The term to search for in decisions.")
    limit: Optional[int] = Field(10, gt=0, description="Maximum number of search results to return.")

class DeleteDecisionByIdArgs(BaseArgs):
    """Arguments for deleting a decision by its ID."""
    decision_id: int = Field(..., gt=0, description="The ID of the decision to delete.")

# --- Progress Tools ---

class LogProgressArgs(BaseArgs):
    """Arguments for logging a progress entry."""
    status: str = Field(..., description="Current status (e.g., 'TODO', 'IN_PROGRESS', 'DONE')")
    description: str = Field(..., min_length=1, description="Description of the progress or task")
    parent_id: Optional[int] = Field(None, description="ID of the parent task, if this is a subtask")
    linked_item_type: Optional[str] = Field(None, description="Optional: Type of the ConPort item this progress entry is linked to (e.g., 'decision', 'system_pattern')")
    linked_item_id: Optional[str] = Field(None, description="Optional: ID/key of the ConPort item this progress entry is linked to (requires linked_item_type)")
    # Default relationship type for progress links, can be made configurable if needed
    link_relationship_type: str = Field("relates_to_progress", description="Relationship type for the automatic link, defaults to 'relates_to_progress'")


    @model_validator(mode='before')
    @classmethod
    def check_linked_item_fields(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        linked_item_type, linked_item_id = values.get('linked_item_type'), values.get('linked_item_id')
        if (linked_item_type is None and linked_item_id is not None) or \
           (linked_item_type is not None and linked_item_id is None):
            raise ValueError("Both 'linked_item_type' and 'linked_item_id' must be provided together, or neither.")
        return values

class GetProgressArgs(BaseArgs):
    """Arguments for retrieving progress entries."""
    status_filter: Optional[str] = Field(None, description="Filter entries by status")
    parent_id_filter: Optional[int] = Field(None, description="Filter entries by parent task ID")
    limit: Optional[int] = Field(None, gt=0, description="Maximum number of entries to return (most recent first)")

# New model for updating a progress entry
class UpdateProgressArgs(BaseArgs):
    """Arguments for updating an existing progress entry."""
    progress_id: int = Field(..., gt=0, description="The ID of the progress entry to update.")
    status: Optional[str] = Field(None, description="New status (e.g., 'TODO', 'IN_PROGRESS', 'DONE')")
    description: Optional[str] = Field(None, min_length=1, description="New description of the progress or task")
    parent_id: Optional[int] = Field(None, description="New ID of the parent task, if changing") # Note: Setting to None might mean clearing parent

    @model_validator(mode='before')
    @classmethod
    def check_at_least_one_field(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        status, description, parent_id = values.get('status'), values.get('description'), values.get('parent_id')
        if status is None and description is None and parent_id is None:
            raise ValueError("At least one field ('status', 'description', or 'parent_id') must be provided for update.")
        return values

# New model for deleting a progress entry by ID
class DeleteProgressByIdArgs(BaseArgs):
    """Arguments for deleting a progress entry by its ID."""
    progress_id: int = Field(..., gt=0, description="The ID of the progress entry to delete.")

# --- System Pattern Tools ---

class LogSystemPatternArgs(BaseArgs):
    """Arguments for logging a system pattern."""
    name: str = Field(..., min_length=1, description="Unique name for the system pattern")
    description: Optional[str] = Field(None, description="Description of the pattern")
    tags: Optional[List[str]] = Field(None, description="Optional tags for categorization")

class GetSystemPatternsArgs(BaseArgs):
    """Arguments for retrieving system patterns."""
    tags_filter_include_all: Optional[List[str]] = Field(None, description="Filter: items must include ALL of these tags.")
    tags_filter_include_any: Optional[List[str]] = Field(None, description="Filter: items must include AT LEAST ONE of these tags.")

    @model_validator(mode='before')
    @classmethod
    def check_tag_filters(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if values.get('tags_filter_include_all') and values.get('tags_filter_include_any'):
            raise ValueError("Cannot use 'tags_filter_include_all' and 'tags_filter_include_any' simultaneously.")
        return values

class DeleteSystemPatternByIdArgs(BaseArgs):
    """Arguments for deleting a system pattern by its ID."""
    pattern_id: int = Field(..., gt=0, description="The ID of the system pattern to delete.")

# --- Custom Data Tools ---

class LogCustomDataArgs(BaseArgs):
    """Arguments for logging custom data."""
    category: str = Field(..., min_length=1, description="Category for the custom data")
    key: str = Field(..., min_length=1, description="Key for the custom data (unique within category)")
    value: Any = Field(..., description="The custom data value (JSON serializable)")

class GetCustomDataArgs(BaseArgs):
    """Arguments for retrieving custom data."""
    category: Optional[str] = Field(None, description="Filter by category")
    key: Optional[str] = Field(None, description="Filter by key (requires category)")

class DeleteCustomDataArgs(BaseArgs):
    """Arguments for deleting custom data."""
    category: str = Field(..., min_length=1, description="Category of the data to delete")
    key: str = Field(..., min_length=1, description="Key of the data to delete")

class SearchCustomDataValueArgs(BaseArgs):
    """Arguments for searching custom data values using FTS."""
    query_term: str = Field(..., min_length=1, description="The term to search for in custom data (category, key, or value).")
    category_filter: Optional[str] = Field(None, description="Optional: Filter results to this category after FTS.")
    limit: Optional[int] = Field(10, gt=0, description="Maximum number of search results to return.")

class SearchProjectGlossaryArgs(BaseArgs):
    """Arguments for searching the ProjectGlossary using FTS."""
    query_term: str = Field(..., min_length=1, description="The term to search for in the glossary.")
    limit: Optional[int] = Field(10, gt=0, description="Maximum number of search results to return.")

# --- Export Tool ---

class ExportConportToMarkdownArgs(BaseArgs):
    """Arguments for exporting ConPort data to markdown files."""
    output_path: Optional[str] = Field(None, description="Optional output directory path relative to workspace_id. Defaults to './conport_export/' if not provided.")

# --- Import Tool ---

class ImportMarkdownToConportArgs(BaseArgs):
    """Arguments for importing markdown files into ConPort data."""
    input_path: Optional[str] = Field(None, description="Optional input directory path relative to workspace_id containing markdown files. Defaults to './conport_export/' if not provided.")

# --- Knowledge Graph Link Tools ---

class ContextLink(BaseModel):
    """Model for the context_links table."""
    id: Optional[int] = None # Auto-incremented by DB
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source_item_type: str = Field(..., description="Type of the source item (e.g., 'decision', 'progress_entry')")
    source_item_id: str = Field(..., description="ID or key of the source item") # Using str to accommodate string keys from custom_data etc.
    target_item_type: str = Field(..., description="Type of the target item")
    target_item_id: str = Field(..., description="ID or key of the target item")
    relationship_type: str = Field(..., description="Nature of the link (e.g., 'implements', 'related_to')")
    description: Optional[str] = Field(None, description="Optional description for the link itself")

class LinkConportItemsArgs(BaseArgs):
    """Arguments for creating a link between two ConPort items."""
    source_item_type: str = Field(..., description="Type of the source item")
    source_item_id: str = Field(..., description="ID or key of the source item")
    target_item_type: str = Field(..., description="Type of the target item")
    target_item_id: str = Field(..., description="ID or key of the target item")
    relationship_type: str = Field(..., description="Nature of the link")
    description: Optional[str] = Field(None, description="Optional description for the link")

class GetLinkedItemsArgs(BaseArgs):
    """Arguments for retrieving links for a ConPort item."""
    item_type: str = Field(..., description="Type of the item to find links for (e.g., 'decision')")
    item_id: str = Field(..., description="ID or key of the item to find links for")
    relationship_type_filter: Optional[str] = Field(None, description="Optional: Filter by relationship type")
    # Optional filters for the other end of the link
    linked_item_type_filter: Optional[str] = Field(None, description="Optional: Filter by the type of the linked items")
    # direction_filter: Optional[str] = Field(None, description="Optional: 'source' or 'target' to get links where item_id is source or target. Default all.") # Future enhancement
    limit: Optional[int] = Field(None, gt=0, description="Maximum number of links to return")

# --- Batch Logging Tool ---

class BatchLogItemsArgs(BaseArgs):
    """Arguments for batch logging multiple items of the same type."""
    item_type: str = Field(..., description="Type of items to log (e.g., 'decision', 'progress_entry', 'system_pattern', 'custom_data')")
    items: List[Dict[str, Any]] = Field(..., description="A list of dictionaries, each representing the arguments for a single item log.")

# --- Context History Tool Args ---

class GetItemHistoryArgs(BaseArgs):
    """Arguments for retrieving history of a context item."""
    item_type: str = Field(..., description="Type of the item: 'product_context' or 'active_context'")
    limit: Optional[int] = Field(None, gt=0, description="Maximum number of history entries to return (most recent first)")
    before_timestamp: Optional[datetime] = Field(None, description="Return entries before this timestamp")
    after_timestamp: Optional[datetime] = Field(None, description="Return entries after this timestamp")
    version: Optional[int] = Field(None, gt=0, description="Return a specific version")

    @model_validator(mode='before')
    @classmethod
    def check_item_type(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        item_type = values.get('item_type')
        if item_type not in ['product_context', 'active_context']:
            raise ValueError("item_type must be 'product_context' or 'active_context'")
        return values

# --- ConPort Schema Tool Args ---

class GetConportSchemaArgs(BaseArgs):
    """Arguments for retrieving the ConPort tool schema."""
    pass

# --- Recent Activity Summary Tool Args ---

class GetRecentActivitySummaryArgs(BaseArgs):
    """Arguments for retrieving a summary of recent ConPort activity."""
    hours_ago: Optional[int] = Field(None, gt=0, description="Look back this many hours for recent activity. Mutually exclusive with 'since_timestamp'.")
    since_timestamp: Optional[datetime] = Field(None, description="Look back for activity since this specific timestamp. Mutually exclusive with 'hours_ago'.")
    limit_per_type: Optional[int] = Field(5, gt=0, description="Maximum number of recent items to show per activity type (e.g., 5 most recent decisions).")

    @model_validator(mode='before')
    @classmethod
    def check_timeframe_exclusive(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if values.get('hours_ago') is not None and values.get('since_timestamp') is not None:
            raise ValueError("Provide either 'hours_ago' or 'since_timestamp', not both.")
        if values.get('hours_ago') is None and values.get('since_timestamp') is None:
            # Default to a reasonable timeframe if neither is provided, e.g., last 24 hours
            # For now, let's require one or allow the handler to define a default if none are passed.
            # Or, make one of them have a default in Field. For now, let's assume handler can default if both are None.
            pass # Allow both to be None, handler can set a default (e.g. 24 hours)
        return values

# --- Semantic Search Tool Args ---

class SemanticSearchConportArgs(BaseArgs):
    """Arguments for performing a semantic search across ConPort data."""
    query_text: str = Field(..., min_length=1, description="The natural language query text for semantic search.")
    top_k: int = Field(default=5, ge=1, le=25, description="Number of top results to return.") # Max 25 for now
    filter_item_types: Optional[List[str]] = Field(default=None, description="Optional list of item types to filter by (e.g., ['decision', 'custom_data']). Valid types: 'decision', 'system_pattern', 'custom_data', 'progress_entry'.")
    filter_tags_include_any: Optional[List[str]] = Field(default=None, description="Optional list of tags; results will include items matching any of these tags.")
    filter_tags_include_all: Optional[List[str]] = Field(default=None, description="Optional list of tags; results will include only items matching all of these tags.")
    filter_custom_data_categories: Optional[List[str]] = Field(default=None, description="Optional list of categories to filter by if 'custom_data' is in filter_item_types.")

    @model_validator(mode='before')
    @classmethod
    def check_tag_filters(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if values.get('filter_tags_include_all') and values.get('filter_tags_include_any'):
            raise ValueError("Cannot use 'filter_tags_include_all' and 'filter_tags_include_any' simultaneously.")
        return values

    @model_validator(mode='before')
    @classmethod
    def check_custom_data_category_filter(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        item_types = values.get('filter_item_types')
        category_filter = values.get('filter_custom_data_categories')
        if category_filter and (not item_types or 'custom_data' not in item_types):
            raise ValueError("'filter_custom_data_categories' can only be used if 'custom_data' is included in 'filter_item_types'.")
        return values

# Dictionary mapping tool names to their expected argument models (for potential future use/validation)
# Note: The primary validation happens in the handler using these models.
TOOL_ARG_MODELS = {
    "get_product_context": GetContextArgs,
    "update_product_context": UpdateContextArgs,
    "get_active_context": GetContextArgs,
    "update_active_context": UpdateContextArgs,
    "log_decision": LogDecisionArgs,
    "get_decisions": GetDecisionsArgs,
    "search_decisions_fts": SearchDecisionsArgs,
    "delete_decision_by_id": DeleteDecisionByIdArgs,
    "log_progress": LogProgressArgs,
    "get_progress": GetProgressArgs,
    "log_system_pattern": LogSystemPatternArgs,
    "get_system_patterns": GetSystemPatternsArgs,
    "delete_system_pattern_by_id": DeleteSystemPatternByIdArgs,
    "log_custom_data": LogCustomDataArgs,
    "get_custom_data": GetCustomDataArgs,
    "delete_custom_data": DeleteCustomDataArgs,
    "search_custom_data_value_fts": SearchCustomDataValueArgs,
    "search_project_glossary_fts": SearchProjectGlossaryArgs,
    "export_conport_to_markdown": ExportConportToMarkdownArgs,
    "import_markdown_to_conport": ImportMarkdownToConportArgs,
    "link_conport_items": LinkConportItemsArgs,
    "get_linked_items": GetLinkedItemsArgs,
    "batch_log_items": BatchLogItemsArgs,
    "get_item_history": GetItemHistoryArgs,
    "get_conport_schema": GetConportSchemaArgs,
    "get_recent_activity_summary": GetRecentActivitySummaryArgs,
    "semantic_search_conport": SemanticSearchConportArgs, # New tool
    "update_progress": UpdateProgressArgs, # New tool
    "delete_progress_by_id": DeleteProgressByIdArgs, # New tool
}