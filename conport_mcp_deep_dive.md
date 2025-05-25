# Context Portal (ConPort) MCP Server Documentation

Version: 0.1.0

## 1. Introduction & Overview

### Purpose
The Context Portal (ConPort) MCP server is designed to manage and provide structured project context for AI assistants, particularly within Integrated Development Environments (IDEs). Its primary goal is to enhance an AI's contextual understanding of a specific software project by maintaining a queryable, persistent, and workspace-specific **knowledge graph**. This structured knowledge base is designed to serve as a powerful backend for **Retrieval Augmented Generation (RAG)**, enabling AI assistants to access precise, up-to-date information. This approach provides a structured alternative to simpler, file-based context systems.

### Core Technologies
*   **Language/Framework:** Python, utilizing the FastAPI framework for robust web server capabilities and Pydantic for data validation and modeling.
*   **MCP Integration:** Leverages the `FastMCP` library from the `mcp.py` SDK to expose its functionalities as Model Context Protocol (MCP) tools.
*   **Database:** SQLite is used as the backend database, with a separate database file created and managed for each distinct workspace. This ensures data isolation between projects.

### Key Architectural Concepts
*   **Workspace-Specific Context:** All data managed by ConPort is tied to a `workspace_id` (typically the absolute path to a project directory). This ensures that context remains relevant to the specific project being worked on.
*   **Dual Communication Modes:** The server can operate in two modes:
    *   **STDIO (Standard Input/Output):** For direct, local communication with an MCP client (e.g., an IDE extension like Roo Code). This mode is efficient for local inter-process communication.
    *   **HTTP (Hypertext Transfer Protocol):** The server can also run as an HTTP service (using Uvicorn and FastAPI), exposing its MCP tools via an HTTP endpoint (typically `/mcp`). This allows for broader accessibility from clients that prefer or require HTTP communication.
*   **Structured Data Management:** ConPort defines several core data entities (see Section 2) to structure project knowledge, such as decisions, progress, system patterns, and custom data.
*   **Tool-Based Interaction:** AI assistants interact with ConPort by calling its defined MCP tools, each designed for a specific operation (e.g., logging a decision, retrieving active context).
*   **Knowledge Graph Construction:** ConPort facilitates the creation of a project-specific knowledge graph by storing structured entities (decisions, code patterns, glossary terms) and allowing explicit, queryable relationships to be defined between them using tools like `link_conport_items`.
*   **Vector Embeddings & Semantic Search:** ConPort generates and stores vector embeddings for key text content within various entities, enabling semantic similarity search.
*   **RAG Enablement:** The system is designed to be a core component for Retrieval Augmented Generation (RAG) workflows. Its rich querying capabilities (FTS, semantic search, direct retrieval, graph traversal) allow AI agents to fetch relevant context to augment their generative tasks, leading to more accurate and grounded outputs.
## 2. Core Data Entities & Database Schema

ConPort utilizes an SQLite database, specific to each workspace, to store its structured context. The key data entities and their corresponding database tables are:

1.  **Product Context (`product_context`)**
    *   **Purpose:** Stores high-level, relatively static information about the project (e.g., overall goals, architecture, key features).
    *   **Schema:** Single row table.
        *   `id` (INTEGER, PK, fixed at 1)
        *   `content` (TEXT): Stores a JSON string representing a dictionary of product context information.
    *   **History:** Changes are versioned in `product_context_history`.

2.  **Active Context (`active_context`)**
    *   **Purpose:** Stores dynamic, short-term context relevant to the current task or session (e.g., current focus, recent changes, open questions, next steps).
    *   **Schema:** Single row table.
        *   `id` (INTEGER, PK, fixed at 1)
        *   `content` (TEXT): Stores a JSON string representing a dictionary of active context information.
    *   **History:** Changes are versioned in `active_context_history`.

3.  **Decisions (`decisions`)**
    *   **Purpose:** Logs significant architectural or implementation decisions made during the project.
    *   **Schema:**
        *   `id` (INTEGER, PK, AUTOINCREMENT)
        *   `timestamp` (TIMESTAMP): When the decision was logged.
        *   `summary` (TEXT, NOT NULL): Concise summary of the decision.
        *   `rationale` (TEXT): Reasoning behind the decision.
        *   `implementation_details` (TEXT): How the decision will be/was implemented.
        *   `tags` (TEXT): JSON stringified list of tags for categorization.
    *   **Search:** Supported by an FTS5 virtual table `decisions_fts` (searches summary, rationale, implementation_details, tags).

4.  **Progress Entries (`progress_entries`)**
    *   **Purpose:** Tracks tasks, their status, and hierarchy.
    *   **Schema:**
        *   `id` (INTEGER, PK, AUTOINCREMENT)
        *   `timestamp` (TIMESTAMP): When the progress entry was logged/updated.
        *   `status` (TEXT, NOT NULL): e.g., "TODO", "IN_PROGRESS", "DONE".
        *   `description` (TEXT, NOT NULL): Description of the task or progress.
        *   `parent_id` (INTEGER, FK to `progress_entries.id`): For subtasks.

5.  **System Patterns (`system_patterns`)**
    *   **Purpose:** Documents recurring architectural or design patterns observed or used in the project.
    *   **Schema:**
        *   `id` (INTEGER, PK, AUTOINCREMENT)
        *   `name` (TEXT, UNIQUE, NOT NULL): Unique name for the pattern.
        *   `description` (TEXT): Description of the pattern.
        *   `tags` (TEXT): JSON stringified list of tags.

6.  **Custom Data (`custom_data`)**
    *   **Purpose:** Stores arbitrary key-value data, categorized by the user. Useful for project glossaries, configuration snippets, notes, etc.
    *   **Schema:**
        *   `id` (INTEGER, PK, AUTOINCREMENT)
        *   `category` (TEXT, NOT NULL)
        *   `key` (TEXT, NOT NULL): Unique within its category.
        *   `value` (TEXT): Stores a JSON string representing the arbitrary data.
    *   **Search:** Supported by an FTS5 virtual table `custom_data_fts` (searches category, key, and the text content of the value).

7.  **Context Links (`context_links`)**
    *   **Purpose:** Establishes explicit, queryable relationships between different ConPort data entities (e.g., a decision is implemented by a system pattern, a progress item tracks a decision), forming the edges of the **project knowledge graph**.
    *   **Schema:**
        *   `id` (INTEGER, PK, AUTOINCREMENT)
        *   `timestamp` (TIMESTAMP): When the link was created.
        *   `workspace_id` (TEXT, NOT NULL): The workspace this link belongs to.
        *   `source_item_type` (TEXT, NOT NULL): Type of the source item (e.g., "decision").
        *   `source_item_id` (TEXT, NOT NULL): ID/key of the source item.
        *   `target_item_type` (TEXT, NOT NULL): Type of the target item.
        *   `target_item_id` (TEXT, NOT NULL): ID/key of the target item.
        *   `relationship_type` (TEXT, NOT NULL): Nature of the link (e.g., "implements", "related_to").
        *   `description` (TEXT): Optional description for the link itself.

8.  **Context History (`product_context_history`, `active_context_history`)**
    *   **Purpose:** Tracks changes over time to Product Context and Active Context.
    *   **Schema (for each history table):**
        *   `id` (INTEGER, PK, AUTOINCREMENT)
        *   `timestamp` (TIMESTAMP): When this historical version was saved.
        *   `version` (INTEGER, NOT NULL): Version number for the context.
        *   `content` (TEXT, NOT NULL): The JSON string content of the context at this version.
        *   `change_source` (TEXT): Brief description of what triggered the change (e.g., tool name).

9. **Vector Store (ChromaDB)**
    *   **Purpose:** Stores vector embeddings generated from text content of various ConPort entities (Decisions, Progress, Custom Data, etc.) to enable semantic similarity search.
    *   **Location:** Stored on disk within the workspace's ConPort data directory, separate from the SQLite file but managed alongside it.
    *   **Integration:** Linked to SQLite data via item type and ID metadata stored alongside the vectors.

9. **Vector Store (ChromaDB)**
    *   **Purpose:** Stores vector embeddings generated from text content of various ConPort entities (Decisions, Progress, Custom Data, etc.) to enable semantic similarity search.
    *   **Location:** Stored on disk within the workspace's ConPort data directory, separate from the SQLite file but managed alongside it.
    *   **Integration:** Linked to SQLite data via item type and ID metadata stored alongside the vectors.

9. **Vector Store (ChromaDB)**
    *   **Purpose:** Stores vector embeddings generated from text content of various ConPort entities (Decisions, Progress, Custom Data, etc.) to enable semantic similarity search.
    *   **Location:** Stored on disk within the workspace's ConPort data directory, separate from the SQLite file but managed alongside it.
    *   **Integration:** Linked to SQLite data via item type and ID metadata stored alongside the vectors.

Pydantic models defined in `src/context_portal_mcp/db/models.py` mirror these table structures and are used for data validation and serialization/deserialization within the server.
## 3. MCP Tool Reference

The ConPort server exposes the following MCP tools. These tools allow AI agents to interact with and build upon the **project knowledge graph**, and to retrieve specific information crucial for **Retrieval Augmented Generation (RAG)**. All tools require a `workspace_id` argument, which is an identifier for the workspace (e.g., absolute path) to ensure data operations are performed in the correct context.

### 3.1 Product Context Tools

#### 3.1.1 `get_product_context`
*   **Description:** Arguments for getting product or active context (only workspace_id needed).
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
*   **Pydantic Model:** `GetContextArgs`

#### 3.1.2 `update_product_context`
*   **Description:** Arguments for updating product or active context. Provide either 'content' for a full update or 'patch_content' for a partial update.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `content` (object, optional): The full new context content as a dictionary. Overwrites existing. (Default: null)
    *   `patch_content` (object, optional): A dictionary of changes to apply (add/update keys). Use a value of `\"__DELETE__\"` to remove a key. (Default: null)
*   **Pydantic Model:** `UpdateContextArgs`

### 3.2 Active Context Tools

#### 3.2.1 `get_active_context`
*   **Description:** Arguments for getting product or active context (only workspace_id needed).
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
*   **Pydantic Model:** `GetContextArgs`

#### 3.2.2 `update_active_context`
*   **Description:** Arguments for updating product or active context. Provide either 'content' for a full update or 'patch_content' for a partial update.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `content` (object, optional): The full new context content as a dictionary. Overwrites existing. (Default: null)
    *   `patch_content` (object, optional): A dictionary of changes to apply (add/update keys). Use a value of `\"__DELETE__\"` to remove a key. (Default: null)
*   **Pydantic Model:** `UpdateContextArgs`

### 3.3 Decision Logging Tools

#### 3.3.1 `log_decision`
*   **Description:** Arguments for logging a decision.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `summary` (string): A concise summary of the decision (Required: Yes)
    *   `rationale` (string, optional): The reasoning behind the decision (Default: null)
    *   `implementation_details` (string, optional): Details about how the decision will be/was implemented (Default: null)
    *   `tags` (array of strings, optional): Optional tags for categorization (Default: null)
*   **Pydantic Model:** `LogDecisionArgs`

#### 3.3.2 `get_decisions`
*   **Description:** Arguments for retrieving decisions.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `limit` (integer, optional): Maximum number of decisions to return (most recent first) (Default: null)
    *   `tags_filter_include_all` (array of strings, optional): Filter: items must include ALL of these tags. (Default: null)
    *   `tags_filter_include_any` (array of strings, optional): Filter: items must include AT LEAST ONE of these tags. (Default: null)
*   **Pydantic Model:** `GetDecisionsArgs`

#### 3.3.3 `search_decisions_fts`
*   **Description:** Arguments for searching decisions using FTS.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `query_term` (string): The term to search for in decisions. (Required: Yes)
    *   `limit` (integer, optional): Maximum number of search results to return. (Default: 10)
*   **Pydantic Model:** `SearchDecisionsArgs`

#### 3.3.4 `delete_decision_by_id`
*   **Description:** Arguments for deleting a decision by its ID.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `decision_id` (integer): The ID of the decision to delete. (Required: Yes)
    *   `Pydantic Model`: `DeleteDecisionByIdArgs`

### 3.4 Progress Tracking Tools

#### 3.4.1 `log_progress`
*   **Description:** Arguments for logging a progress entry.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `status` (string): Current status (e.g., 'TODO', 'IN_PROGRESS', 'DONE') (Required: Yes)
    *   `description` (string): Description of the progress or task (Required: Yes)
    *   `parent_id` (integer, optional): ID of the parent task, if this is a subtask (Default: null)
    *   `linked_item_type` (string, optional): Optional: Type of the ConPort item this progress entry is linked to (e.g., 'decision', 'system_pattern') (Default: null)
    *   `linked_item_id` (string, optional): Optional: ID/key of the ConPort item this progress entry is linked to (requires linked_item_type) (Default: null)
    *   `link_relationship_type` (string, optional): Relationship type for the automatic link if `linked_item_type` and `linked_item_id` are provided (e.g., "tracks_decision"). (Default: "relates_to_progress")
*   **Pydantic Model:** `LogProgressArgs`

#### 3.4.2 `get_progress`
*   **Description:** Arguments for retrieving progress entries.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `status_filter` (string, optional): Filter entries by status (Default: null)
    *   `parent_id_filter` (integer, optional): Filter entries by parent task ID (Default: null)
    *   `limit` (integer, optional): Maximum number of entries to return (most recent first) (Default: null)
*   **Pydantic Model:** `GetProgressArgs`

#### 3.4.3 `update_progress`
*   **Description:** Arguments for updating an existing progress entry.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `progress_id` (integer): The ID of the progress entry to update. (Required: Yes)
    *   `status` (string, optional): New status (e.g., 'TODO', 'IN_PROGRESS', 'DONE') (Default: null)
    *   `description` (string, optional): New description of the progress or task (Default: null)
    *   `parent_id` (integer, optional): New ID of the parent task, if changing (Default: null)
*   **Pydantic Model:** `UpdateProgressArgs`

#### 3.4.4 `delete_progress_by_id`
*   **Description:** Arguments for deleting a progress entry by its ID.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `progress_id` (integer): The ID of the progress entry to delete. (Required: Yes)
*   **Pydantic Model:** `DeleteProgressByIdArgs`

### 3.5 System Pattern Tools

#### 3.5.1 `log_system_pattern`
*   **Description:** Arguments for logging a system pattern.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `name` (string): Unique name for the system pattern (Required: Yes)
    *   `description` (string, optional): Description of the pattern (Default: null)
    *   `tags` (array of strings, optional): Optional tags for categorization (Default: null)
*   **Pydantic Model:** `LogSystemPatternArgs`

#### 3.5.2 `get_system_patterns`
*   **Description:** Arguments for retrieving system patterns.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `tags_filter_include_all` (array of strings, optional): Filter: items must include ALL of these tags. (Default: null)
    *   `tags_filter_include_any` (array of strings, optional): Filter: items must include AT LEAST ONE of these tags. (Default: null)
*   **Pydantic Model:** `GetSystemPatternsArgs`

#### 3.5.3 `delete_system_pattern_by_id`
*   **Description:** Arguments for deleting a system pattern by its ID.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `pattern_id` (integer): The ID of the system pattern to delete. (Required: Yes)
*   **Pydantic Model:** `DeleteSystemPatternByIdArgs`

### 3.6 Custom Data Tools

#### 3.6.1 `log_custom_data`
*   **Description:** Arguments for logging custom data.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `category` (string): Category for the custom data (Required: Yes)
    *   `key` (string): Key for the custom data (unique within category) (Required: Yes)
    *   `value` (any): The custom data value (JSON serializable) (Required: Yes)
*   **Pydantic Model:** `LogCustomDataArgs`

#### 3.6.2 `get_custom_data`
*   **Description:** Arguments for retrieving custom data.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `category` (string, optional): Filter by category (Default: null)
    *   `key` (string, optional): Filter by key (requires category) (Default: null)
*   **Pydantic Model:** `GetCustomDataArgs`

#### 3.6.3 `delete_custom_data`
*   **Description:** Arguments for deleting custom data.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `category` (string): Category of the data to delete (Required: Yes)
    *   `key` (string): Key of the data to delete (Required: Yes)
*   **Pydantic Model:** `DeleteCustomDataArgs`

#### 3.6.4 `search_custom_data_value_fts`
*   **Description:** Arguments for searching custom data values using FTS.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `query_term` (string): The term to search for in custom data (category, key, or value). (Required: Yes)
    *   `category_filter` (string, optional): Optional: Filter results to this category after FTS. (Default: null)
    *   `limit` (integer, optional): Maximum number of search results to return. (Default: 10)
*   **Pydantic Model:** `SearchCustomDataValueArgs`

#### 3.6.5 `search_project_glossary_fts`
*   **Description:** Arguments for searching the ProjectGlossary using FTS. (Note: ProjectGlossary is a specific category within custom_data).
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `query_term` (string): The term to search for in the glossary. (Required: Yes)
    *   `limit` (integer, optional): Maximum number of search results to return. (Default: 10)
*   **Pydantic Model:** `SearchProjectGlossaryArgs`

### 3.7 Import/Export Tools

#### 3.7.1 `export_conport_to_markdown`
*   **Description:** Arguments for exporting ConPort data to markdown files.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `output_path` (string, optional): Optional output directory path relative to workspace_id. (Default: './conport_export/')
*   **Pydantic Model:** `ExportConportToMarkdownArgs`

#### 3.7.2 `import_markdown_to_conport`
*   **Description:** Arguments for importing markdown files into ConPort data.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `input_path` (string, optional): Optional input directory path relative to workspace_id containing markdown files. (Default: './conport_export/')
*   **Pydantic Model:** `ImportMarkdownToConportArgs`

### 3.8 Knowledge Graph / Linking Tools

#### 3.8.1 `link_conport_items`
*   **Description:** Arguments for creating an explicit, typed link between two ConPort items, thereby enriching the **project knowledge graph**.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `source_item_type` (string): Type of the source item (Required: Yes)
    *   `source_item_id` (string): ID or key of the source item (Required: Yes)
    *   `target_item_type` (string): Type of the target item (Required: Yes)
    *   `target_item_id` (string): ID or key of the target item (Required: Yes)
    *   `relationship_type` (string): Nature of the link (Required: Yes)
    *   `description` (string, optional): Optional description for the link (Default: null)
*   **Pydantic Model:** `LinkConportItemsArgs`

#### 3.8.2 `get_linked_items`
*   **Description:** Arguments for retrieving links connected to a specific ConPort item, allowing traversal of the **project knowledge graph**.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `item_type` (string): Type of the item to find links for (e.g., 'decision') (Required: Yes)
    *   `item_id` (string): ID or key of the item to find links for (Required: Yes)
    *   `relationship_type_filter` (string, optional): Optional: Filter by relationship type (Default: null)
    *   `linked_item_type_filter` (string, optional): Optional: Filter by the type of the linked items (Default: null)
    *   `limit` (integer, optional): Maximum number of links to return (Default: null)
*   **Pydantic Model:** `GetLinkedItemsArgs`

### 3.9 Batch Operations

#### 3.9.1 `batch_log_items`
*   **Description:** Arguments for batch logging multiple items of the same type.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `item_type` (string): Type of items to log (e.g., 'decision', 'progress_entry', 'system_pattern', 'custom_data') (Required: Yes)
    *   `items` (array of objects): A list of dictionaries, each representing the arguments for a single item log. (Required: Yes)
*   **Pydantic Model:** `BatchLogItemsArgs`

### 3.10 History & Meta Tools

#### 3.10.1 `get_item_history`
*   **Description:** Arguments for retrieving history of a context item.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `item_type` (string): Type of the item: 'product_context' or 'active_context' (Required: Yes)
    *   `limit` (integer, optional): Maximum number of history entries to return (most recent first) (Default: null)
    *   `before_timestamp` (string, format: date-time, optional): Return entries before this timestamp (Default: null)
    *   `after_timestamp` (string, format: date-time, optional): Return entries after this timestamp (Default: null)
    *   `version` (integer, optional): Return a specific version (Default: null)
*   **Pydantic Model:** `GetItemHistoryArgs`

#### 3.10.2 `get_conport_schema`
*   **Description:** Arguments for retrieving the ConPort tool schema.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `Pydantic Model`: `GetConportSchemaArgs`

#### 3.10.3 `get_recent_activity_summary`
*   **Description:** Arguments for retrieving a summary of recent ConPort activity.
*   **Arguments:**
    *   `workspace_id` (string): Identifier for the workspace (e.g., absolute path) (Required: Yes)
    *   `hours_ago` (integer, optional): Look back this many hours for recent activity. Mutually exclusive with 'since_timestamp'. (Default: null)
    *   `since_timestamp` (string, format: date-time, optional): Look back for activity since this specific timestamp. Mutually exclusive with 'hours_ago'. (Default: null)
    *   `limit_per_type` (integer, optional): Maximum number of recent items to show per activity type (e.g., 5 most recent decisions). (Default: 5)
    *   `Pydantic Model`: `GetRecentActivitySummaryArgs`
## 4. Implementation Details & Guidelines

### 4.1 Project Structure
The server code is primarily located within the `src/context_portal_mcp/` directory:
*   `main.py`: Entry point for the server. Handles CLI argument parsing, sets up the FastAPI and FastMCP instances, registers MCP tools, and defines the server lifecycle.
*   `handlers/mcp_handlers.py`: Contains the core logic for each MCP tool. These functions are called by the tool wrappers in `main.py`.
*   `db/database.py`: Manages all interactions with the SQLite database, including connection handling, schema initialization, and CRUD operations for all data entities.
*   `db/models.py`: Defines Pydantic models for:
    *   Representing the structure of data stored in database tables (e.g., `Decision`, `ProductContext`).
    *   Validating and structuring the arguments passed to MCP tools (e.g., `LogDecisionArgs`, `UpdateContextArgs`).
*   `core/config.py`: Handles configuration aspects, notably determining the database path based on the `workspace_id`.
*   `core/exceptions.py`: Defines custom exception classes used throughout the server (e.g., `DatabaseError`, `ToolArgumentError`).

### 4.2 Running the Server

The server can be run in two primary modes:

#### STDIO Mode
This mode is intended for direct use by local MCP clients (like IDE extensions), and the `FastMCP` library handles the STDIO communication transport.
    *   Command (from project root):
        ```bash
        python src/context_portal_mcp/main.py --mode stdio --workspace_id "/path/to/your/workspace"
        ```
    *   Or using the CLI entry point:
        ```bash
        conport --mode stdio --workspace_id "/path/to/your/workspace"
        ```
    *   **Note on `workspace_id` in STDIO mode:** The server includes logic to detect if `${workspaceFolder}` is passed literally (i.e., not expanded by the client) and will fall back to using the current working directory as the `workspace_id` in such cases, with a warning.

#### HTTP Mode
The server can also be run as an HTTP service using Uvicorn:
    ```bash
    uvicorn src.context_portal_mcp.main:app --host 127.0.0.1 --port 8000
    ```
Or using the CLI entry point:
    ```bash
    conport --mode http --host 127.0.0.1 --port 8000
    ```
In this mode, the MCP endpoint is typically available at `/mcp`.

### 4.3 Dependencies
Key Python dependencies are managed via `requirements.txt` (or would be in a `pyproject.toml` if using Poetry/PDM). These include:
*   `fastapi`: For the web server framework.
*   `uvicorn[standard]`: As the ASGI server to run FastAPI in HTTP mode.
*   `pydantic`: For data validation and settings management.
*   `mcp[cli]` (or `mcp.py`): The Model Context Protocol SDK, specifically `FastMCP` for server implementation.
*   `sqlite3` is part of the Python standard library.

### 4.4 Database Location
The SQLite database file for each workspace is typically created at:
`<workspace_id>/context_portal/context.db`
This path is determined by the `get_database_path` function in `core/config.py`.

### 4.5 Adding New Tools
To add a new MCP tool:
1.  **Define Argument Model:** Create a new Pydantic model in `db/models.py` inheriting from `BaseArgs` (or directly from `BaseModel` if `workspace_id` isn't needed, though it usually is). This model defines the expected arguments for the new tool.
2.  **Implement Handler Logic:** Add a new handler function in `handlers/mcp_handlers.py`. This function will take the validated Pydantic argument model as input and perform the core logic, likely interacting with `db/database.py`.
3.  **Register Tool in `main.py`:**
    *   Import the new argument model and handler function.
    *   Use the `@conport_mcp.tool(name="your_new_tool_name", description="...")` decorator on a new async wrapper function.
    *   This wrapper function will:
        *   Receive arguments from client as `Dict[str, Any]` and `ctx: MCPContext`.
        *   Extract necessary arguments
        *   Instantiate your Pydantic argument model using the received parameters.
        *   Call your handler function from `mcp_handlers.py` with the Pydantic model instance.
        *   Return the result from the handler.
4.  **Update `TOOL_ARG_MODELS`:** Add your new tool name and its argument model to the `TOOL_ARG_MODELS` dictionary in `db/models.py` (used by `get_conport_schema`).
5.  **Database Schema (if needed):** If the new tool requires changes to the database schema (new tables, columns), update `db/database.py`'s `initialize_database` function accordingly, including any necessary `ALTER TABLE` statements for migration.
## 5. Future Development & Considerations

### 5.1 Enhanced Querying & Filtering
*   More sophisticated filtering options for `get_decisions`, `get_progress`, etc. (e.g., date ranges, multiple status filters for progress).
*   Full-text search capabilities for System Patterns.
*   More advanced querying for `context_links` (e.g., graph traversal queries, finding items with no links).

### 5.2 Enhanced Progress Management
*   Added tools for updating (`update_progress`) and deleting (`delete_progress_by_id`) individual progress entries by their ID, providing more granular control over progress tracking data.

### 5.2 Enhanced Progress Management
*   Added tools for updating (`update_progress`) and deleting (`delete_progress_by_id`) individual progress entries by their ID, providing more granular control over progress tracking data.

### 5.3 Collaboration Features (if shifting to a multi-user model)
*   User identification for logged items.
*   Permissions and access control if data is shared.
*   Real-time updates/notifications if a multi-user model were adopted for the same ConPort instance.

### 5.3 Richer Data Types for Custom Data
*   While `value` in `custom_data` is `Any` (JSON serializable), providing explicit support or validation for common structured types (e.g., lists of specific objects, typed dictionaries) could be beneficial.

### 5.4 Enhanced Retrieval for RAG (Retrieval-Augmented Generation)
### 5.4 Enhanced Retrieval for RAG (Retrieval-Augmented Generation)
ConPort functions as a key component in a RAG system by enabling the construction and querying of a **project-specific knowledge graph**. Its capabilities, now including **vector embeddings** and **semantic search**, serve as the "Retrieval" mechanism.

*   **Vector Embeddings & Semantic Search:** ConPort integrates vector embeddings for text content within various entities (Decisions, Progress, Custom Data, System Patterns). This allows for finding conceptually similar items beyond keyword matches using the `semantic_search_conport` tool, significantly improving the quality of retrieved context for LLM augmentation. This is powered by a dedicated vector store (ChromaDB) managed alongside the SQLite database.
*   **Hybrid Search:** The system supports combining keyword-based FTS with semantic search to leverage the strengths of both approaches for more robust and relevant retrieval.
*   **Context Chunking for LLMs:** (Future Consideration) Introduce a tool or mechanism to retrieve specific ConPort data items (or parts of them, like a long decision rationale) in "chunks" optimized for LLM context windows. This would help in feeding manageable pieces of relevant information to the LLM.
*   **Automated Context Suggestion:** (Future Consideration) Develop tools within ConPort that, based on a query or a summary of the current task (perhaps provided by the LLM), could proactively suggest relevant ConPort items (decisions, patterns, glossary terms) that the LLM might want to retrieve to augment its generation. This could use a combination of FTS, semantic search, and knowledge graph traversal (`get_linked_items`).

### 5.5 More Granular History
*   Currently, only Product and Active Context have explicit history tables. Consider if versioning/history for other entities like Decisions or System Patterns would be valuable.

### 5.6 Configuration & Usability
*   Explore more dynamic ways to manage `workspace_id` or allow aliasing for long workspace paths.

### 5.7 Alternative Communication Modes (SSE/HTTP)
*   While STDIO is primary for local IDE integration, developing an alternative HTTP-based communication mode (potentially using Server-Sent Events for streaming if applicable) could broaden ConPort's accessibility to web-based clients or other tools that prefer HTTP over STDIO. This would leverage the existing FastAPI framework.

### 5.8 Flexible Database Storage & Identification
*   Building upon the 'Configuration & Usability' point for `workspace_id`, implement the 'Flexible Database Storage (DatabaseID)' model (Decision ID 52). This would allow users to store ConPort databases in locations outside the workspace root (e.g., a centralized local directory or true remote storage). It involves assigning a unique `DatabaseID` to each workspace's context, which clients use for identification, while the ConPort server maps this ID to the actual database location and connection details. The local workspace path would still be relevant for resolving file references within the context data.

### 5.9 Integration with Other Developer Tools
*   Direct integration with issue trackers, version control systems (beyond simple linking), or CI/CD pipelines to automatically log context or make it available.

### 5.10 Backup and Restore Enhancements
*   While Markdown export/import exists, more robust backup/restore mechanisms (e.g., direct SQLite backup/restore tools, cloud synchronization options) could be considered for critical data.

### 5.11 Schema Evolution and Migration
*   The current `ALTER TABLE` approach for adding columns is basic. A more formal database migration system (like Alembic) might be needed if the schema undergoes frequent or complex changes.

These considerations depend on the evolving goals and use cases for the ConPort server. The current architecture provides a solid foundation for many of these potential enhancements.

## Prompt Caching Integration

ConPort plays a crucial role in enabling AI assistants to effectively utilize **prompt caching** with compatible LLM providers (such as Google Gemini, Anthropic Claude, and OpenAI). By providing structured, queryable project context, ConPort supplies the stable, frequently used information that forms the basis for caching.

**How ConPort Supports Prompt Caching:**

1.  **Structured Context as Cacheable Content:** ConPort stores key project information (Product Context, System Patterns, Custom Data like glossaries or specifications) in a structured database. This allows AI assistants to reliably retrieve specific, often large, blocks of text that are ideal candidates for inclusion in the cacheable prefix of prompts sent to LLMs.
2.  **User-Defined Cache Hints:** The `custom_data` entity (and potentially others if extended) supports a `metadata` field. Users can add hints (e.g., `{"cache_hint": true}`) to this metadata to explicitly flag content that should be prioritized for prompt caching by the AI assistant.
3.  **AI Assistant Strategy Guidance:** The custom instruction files for AI assistants (like those in `conport-custom-instructions/`) are updated to include a `prompt_caching_strategies` section. This section, which can be included directly in the prompt or referenced from a central file (`context_portal/prompt_caching_strategy.yml`), guides the AI on:
    *   Identifying suitable cacheable content from ConPort based on heuristics and user hints.
    *   Structuring prompts according to the specific requirements of the target LLM provider's caching mechanism (implicit for Gemini/OpenAI, explicit breakpoints for Anthropic).
    *   Notifying the user when a prompt is structured for potential caching.

**Mechanism:**

The AI assistant, upon receiving a user request, identifies necessary context from ConPort using tools like `get_product_context`, `get_custom_data`, etc. Based on the retrieved content and the defined prompt caching strategy, the assistant constructs the prompt sent to the LLM API. For providers with implicit caching, the cacheable ConPort content is placed at the beginning. For providers with explicit caching, the content is included with the necessary markers.

This integration ensures that the valuable, structured knowledge stored in ConPort is actively used to improve the efficiency and cost-effectiveness of AI interactions through prompt caching.