<div align="center">

# Context Portal MCP (ConPort)
## (It's a memory bank!)

<br>

  <img src="assets/images/roo-logo.png" alt="Roo Code Logo" height="40"/>&nbsp;&nbsp;&nbsp;
  <img src="assets/images/cline.png" alt="CLine Logo" height="40"/>&nbsp;&nbsp;&nbsp;
  <img src="assets/images/windsurf.png" alt="Windsurf Cascade Logo" height="40"/>&nbsp;&nbsp;&nbsp;
  <img src="assets/images/cursor.png" alt="Cursor IDE Logo" height="40"/>

<br>

A database-backed Model Context Protocol (MCP) server for managing structured project context, designed to be used by AI assistants and developer tools within IDEs and other interfaces.

</div>

<br>

## TLDR: What is ConPort?

Context Portal (ConPort) is your project's **memory bank**. It's a tool that helps AI assistants understand your specific software project better by storing important information like decisions, tasks, and architectural patterns in a structured way. Think of it as building a project-specific knowledge base that the AI can easily access and use to give you more accurate and helpful responses.

**What it does:**

*   Keeps track of project decisions, progress, and system designs.
*   Stores custom project data (like glossaries or specs).
*   Helps AI find relevant project information quickly (like a smart search).
*   Enables AI to use project context for better responses (RAG).
*   More efficient for managing, searching, and updating context compared to simple text file-based memory banks.

**Basic Installation:**

1.  Clone the Git repository.
2.  Use `uv` (recommended) or `venv` to create a Python virtual environment.
3.  Install dependencies using `uv pip install -r requirements.txt` or `pip install -r requirements.txt`.
4.  Configure your IDE/client to run the ConPort server in STDIO mode, pointing it to your project workspace.

This structured memory helps your AI assistant stay informed about your project's history and details.

## Overview

This project is the **Context Portal MCP server (ConPort)**. ConPort provides a robust and structured way for AI assistants to store, retrieve, and manage various types of project context. It effectively builds a **project-specific knowledge graph**, capturing entities like decisions, progress, and architecture, along with their relationships. This structured knowledge base, enhanced by **vector embeddings** for semantic search, then serves as a powerful backend for **Retrieval Augmented Generation (RAG)**, enabling AI assistants to access precise, up-to-date information for more context-aware and accurate responses.

It replaces older file-based context management systems by offering a more reliable and queryable database backend (SQLite per workspace). ConPort is designed to be a generic context backend, compatible with various IDEs and client interfaces that support MCP.

Key features include:
*   Structured context storage using SQLite (one DB per workspace, automatically created).
*   MCP server (`context_portal_mcp`) built with Python/FastAPI.
*   A comprehensive suite of defined MCP tools for interaction (see "Available ConPort Tools" below).
*   Multi-workspace support via `workspace_id`.
*   Primary deployment mode: STDIO for tight IDE integration.
*   Enables building a dynamic **project knowledge graph** with explicit relationships between context items.
*   Includes **vector data storage** and **semantic search** capabilities to power advanced RAG.
*   Serves as an ideal backend for **Retrieval Augmented Generation (RAG)**, providing AI with precise, queryable project memory.
*   Provides structured context that AI assistants can leverage for **prompt caching** with compatible LLM providers.

## Prerequisites

Before you begin, ensure you have the following installed:

*   **Git:** For cloning the repository.
    *   [Download and Install Git](https://git-scm.com/downloads)
*   **Python:** Version 3.8 or higher is recommended.
    *   [Download Python](https://www.python.org/downloads/)
    *   Ensure Python is added to your system's PATH during installation (especially on Windows).
*   **uv:** (Highly Recommended) A fast Python environment and package manager. Using `uv` significantly simplifies virtual environment creation and dependency installation.
    *   [Install uv](https://github.com/astral-sh/uv#installation)
    *   If you choose not to use `uv`, you can use standard Python `venv` and `pip`, but `uv` is preferred for this project.

## Installation from Git Repository

These instructions guide you through setting up ConPort by cloning its Git repository and installing dependencies. Using a virtual environment is crucial.

1.  **Clone the Repository:**
    Open your terminal or command prompt and run:
    ```bash
    git clone https://github.com/GreatScottyMac/context-portal.git
    cd context-portal
    ```

2.  **Create and Activate a Virtual Environment:**

    *   **Using `uv` (recommended):**
        In the `context-portal` directory:
        ```bash
        uv venv
        ```
        *   **Activate the environment:**
            *   **Linux/macOS (bash/zsh):**
                ```bash
                source .venv/bin/activate
                ```
            *   **Windows (Command Prompt):**
                ```cmd
                .venv\Scripts\activate.bat
                ```
            *   **Windows (PowerShell):**
                ```powershell
                .venv\Scripts\Activate.ps1
                ```
                (If you encounter execution policy issues in PowerShell, you might need to run `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` first.)

    *   **Using standard `venv` (if not using `uv`):**
        In the `context-portal` directory:
        ```bash
        python3 -m venv .venv  # Or 'python -m venv .venv'
        ```
        *   Activation commands are the same as for `uv` above.

3.  **Install Dependencies:**
    With your virtual environment activated:

    *   **Using `uv` (recommended):**
        ```bash
        uv pip install -r requirements.txt
        ```
        *Note: `uv` can often detect and use the `.venv` in the current directory even without explicit activation for `uv pip install` commands. However, activation is still good practice, especially if you intend to run Python scripts directly.*

    *   **Using standard `pip`:**
        ```bash
        pip install -r requirements.txt
        ```

4.  **Verify Installation (Optional):**
    Ensure your virtual environment is activated.
    *   **Using `uv`:**
        ```bash
        uv run python src/context_portal_mcp/main.py --help
        ```
    *   **Using standard `python`:**
        ```bash
        python src/context_portal_mcp/main.py --help
        ```
    This should output the command-line help for the ConPort server.

## Running the ConPort Server (STDIO Mode)

STDIO mode is recommended for IDE integration, allowing the IDE to manage the server process for the current workspace.

*   **Command Structure:**
    The IDE will typically construct and run a command similar to this:
    ```bash
    uv run python /path/to/your/context-portal/src/context_portal_mcp/main.py --mode stdio --workspace_id "/actual/path/to/your/project_workspace"
    ```
    *   `/path/to/your/context-portal/` is the absolute path where you cloned the `context-portal` repository.
    *   `"/actual/path/to/your/project_workspace"` is the absolute path to the root of the project whose context ConPort will manage (e.g., `${workspaceFolder}` in VS Code).
    *   ConPort automatically creates its database at `your_project_workspace/context_portal/context.db`.

## Client Configuration (STDIO Mode)

Configure your MCP client (e.g., IDE extension) to connect to ConPort. This example is for a VS Code-like `mcp.json` or user-level MCP settings.

**Recommended Configuration (Direct Python Invocation):**

This configuration directly invokes the Python interpreter from the `context-portal` virtual environment. It's a reliable method that does not depend on `uv` being the command or the client supporting a `cwd` field for the server process.

**Important:**
*   You **MUST** replace placeholder paths with the **absolute paths** corresponding to where you have cloned and set up your `context-portal` repository.
*   The `"${workspaceFolder}"` variable for the `--workspace_id` argument is a common IDE placeholder that should expand to the absolute path of your current project workspace.

**Linux/macOS Example:**

Imagine your `context-portal` repository is cloned at `/home/youruser/projects/context-portal`.

```json
{
  "mcpServers": {
    "conport": {
      "command": "/home/youruser/projects/context-portal/.venv/bin/python",
      "args": [
        "/home/youruser/projects/context-portal/src/context_portal_mcp/main.py",
        "--mode",
        "stdio",
        "--workspace_id",
        "${workspaceFolder}"
      ]
    }
  }
}
```

**Windows Example:**

Imagine your `context-portal` repository is cloned at `C:\Users\YourUser\Projects\context-portal`.
Note the use of double backslashes `\\` for paths in JSON strings.

```json
{
  "mcpServers": {
    "conport": {
      "command": "C:\\Users\\YourUser\\Projects\\context-portal\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\YourUser\\Projects\\context-portal\\src\\context_portal_mcp\\main.py",
        "--mode",
        "stdio",
        "--workspace_id",
        "${workspaceFolder}"
      ]
    }
  }
}
```
*   **`command`**: This must be the absolute path to the `python` (or `python.exe` on Windows) executable within the `.venv` of your `context-portal` installation.
*   **First argument in `args`**: This must be the absolute path to the `main.py` script within your `context-portal` installation.
*   **`--workspace_id "${workspaceFolder}"`**: This tells ConPort which project's context to manage. `${workspaceFolder}` should be resolved by your IDE to the current project's root path.

**Key Takeaway:** For STDIO mode, ConPort critically relies on an accurate `--workspace_id` to identify the target project. Ensure this argument correctly resolves to the absolute path of your project workspace, either through IDE variables like `${workspaceFolder}` or by providing a direct absolute path.

## Usage with LLM Agents (Custom Instructions)

ConPort's effectiveness with LLM agents is significantly enhanced by providing specific custom instructions or system prompts to the LLM. This repository includes tailored strategy files for different environments:

*   **For Roo Code:**
    *   [`roo_code_conport_strategy`](https://github.com/GreatScottyMac/context-portal/blob/main/conport-custom-instructions/roo_code_conport_strategy): Contains detailed instructions for LLMs operating within the Roo Code IDE, guiding them on how to use ConPort tools for context management.
*   **For CLine:**
    *   [`cline_conport_strategy`](https://github.com/GreatScottyMac/context-portal/blob/main/conport-custom-instructions/cline_conport_strategy): Instructions optimized for LLMs interacting via a command-line interface that supports ConPort.
*   **For Windsurf Cascade:**
    *   [`cascade_conport_strategy`](https://github.com/GreatScottyMac/context-portal/blob/main/conport-custom-instructions/cascade_conport_strategy): Specific guidance for LLMs integrated with the Windsurf Cascade environment. *Important*: When initiating a session in Cascade, it is necessary to explicity tell the LLM `Initialize according to custom instructions.`
*   **For General/Platform-Agnostic Use:**
    *   [`generic_conport_strategy`](https://github.com/GreatScottyMac/context-portal/blob/main/conport-custom-instructions/generic_conport_strategy): Provides a platform-agnostic set of instructions for any MCP-capable LLM. It emphasizes using ConPort's `get_conport_schema` operation to dynamically discover the exact ConPort tool names and their parameters, guiding the LLM on *when* and *why* to perform conceptual interactions (like logging a decision or updating product context) rather than hardcoding specific tool invocation details.

**How to Use These Strategy Files:**

1.  Identify the strategy file relevant to your LLM agent's environment.
2.  Copy the **entire content** of that file.
3.  Paste it into your LLM's custom instructions or system prompt area. The method varies by LLM platform (IDE extension settings, web UI, API configuration).

These instructions equip the LLM with the knowledge to:
*   Initialize and load context from ConPort.
*   Update ConPort with new information (decisions, progress, etc.).
*   Manage custom data and relationships.
*   Understand the importance of `workspace_id`.
**Important Tip for Starting Sessions:**
To ensure the LLM agent correctly initializes and loads context, especially in interfaces that might not always strictly adhere to custom instructions on the first message, it's a good practice to start your interaction with a clear directive like:
`Initialize according to custom instructions.`
This can help prompt the agent to perform its ConPort initialization sequence as defined in its strategy file.

## Initial ConPort Usage in a Workspace

When you first start using ConPort in a new or existing project workspace, the ConPort database (`context_portal/context.db`) will be automatically created by the server if it doesn't exist. To help bootstrap the initial project context, especially the **Product Context**, consider the following:

### Using a `projectBrief.md` File (Recommended)

1.  **Create `projectBrief.md`:** In the root directory of your project workspace, create a file named `projectBrief.md`.
2.  **Add Content:** Populate this file with a high-level overview of your project. This could include:
    *   The main goal or purpose of the project.
    *   Key features or components.
    *   Target audience or users.
    *   Overall architectural style or key technologies (if known).
    *   Any other foundational information that defines the project.
3.  **Automatic Prompt for Import:** When an LLM agent using one of the provided ConPort custom instruction sets (e.g., `roo_code_conport_strategy`) initializes in the workspace, it is designed to:
    *   Check for the existence of `projectBrief.md`.
    *   If found, it will read the file and ask you if you'd like to import its content into the ConPort **Product Context**.
    *   If you agree, the content will be added to ConPort, providing an immediate baseline for the project's Product Context.

### Manual Initialization

If `projectBrief.md` is not found, or if you choose not to import it:
*   The LLM agent (guided by its custom instructions) will typically inform you that the ConPort Product Context appears uninitialized.
*   It may offer to help you define the Product Context manually, potentially by listing other files in your workspace to gather relevant information.
*   You can then use the `update_product_context` tool (via the LLM) to populate this information.

By providing initial context, either through `projectBrief.md` or manual entry, you enable ConPort and the connected LLM agent to have a better foundational understanding of your project from the start.

## Available ConPort Tools

The ConPort server exposes the following tools via MCP, allowing interaction with the underlying **project knowledge graph**. This includes tools for **semantic search** powered by **vector data storage**. These tools facilitate the **Retrieval** aspect crucial for **Augmented Generation (RAG)** by AI agents. All tools require a `workspace_id` argument (string, required) to specify the target project workspace.

*   **Product Context Management:**
    *   `get_product_context`: Retrieves the overall project goals, features, and architecture.
    *   `update_product_context`: Updates the product context. Accepts full `content` (object) or `patch_content` (object) for partial updates (use `__DELETE__` as a value in patch to remove a key).
*   **Active Context Management:**
    *   `get_active_context`: Retrieves the current working focus, recent changes, and open issues.
    *   `update_active_context`: Updates the active context. Accepts full `content` (object) or `patch_content` (object) for partial updates (use `__DELETE__` as a value in patch to remove a key).
*   **Decision Logging:**
    *   `log_decision`: Logs an architectural or implementation decision.
        *   Args: `summary` (str, req), `rationale` (str, opt), `implementation_details` (str, opt), `tags` (list[str], opt).
    *   `get_decisions`: Retrieves logged decisions.
        *   Args: `limit` (int, opt), `tags_filter_include_all` (list[str], opt), `tags_filter_include_any` (list[str], opt).
    *   `search_decisions_fts`: Full-text search across decision fields (summary, rationale, details, tags).
        *   Args: `query_term` (str, req), `limit` (int, opt).
    *   `delete_decision_by_id`: Deletes a decision by its ID.
        *   Args: `decision_id` (int, req).
*   **Progress Tracking:**
    *   `log_progress`: Logs a progress entry or task status.
        *   Args: `status` (str, req), `description` (str, req), `parent_id` (int, opt), `linked_item_type` (str, opt), `linked_item_id` (str, opt).
    *   `get_progress`: Retrieves progress entries.
        *   Args: `status_filter` (str, opt), `parent_id_filter` (int, opt), `limit` (int, opt).
    *   `update_progress`: Updates an existing progress entry.
        *   Args: `progress_id` (int, req), `status` (str, opt), `description` (str, opt), `parent_id` (int, opt).
    *   `delete_progress_by_id`: Deletes a progress entry by its ID.
        *   Args: `progress_id` (int, req).
*   **System Pattern Management:**
    *   `log_system_pattern`: Logs or updates a system/coding pattern.
        *   Args: `name` (str, req), `description` (str, opt), `tags` (list[str], opt).
    *   `get_system_patterns`: Retrieves system patterns.
        *   Args: `tags_filter_include_all` (list[str], opt), `tags_filter_include_any` (list[str], opt).
    *   `delete_system_pattern_by_id`: Deletes a system pattern by its ID.
        *   Args: `pattern_id` (int, req).
*   **Custom Data Management:**
    *   `log_custom_data`: Stores/updates a custom key-value entry under a category. Value is JSON-serializable.
        *   Args: `category` (str, req), `key` (str, req), `value` (any, req).
    *   `get_custom_data`: Retrieves custom data.
        *   Args: `category` (str, opt), `key` (str, opt).
    *   `delete_custom_data`: Deletes a specific custom data entry.
        *   Args: `category` (str, req), `key` (str, req).
    *   `search_project_glossary_fts`: Full-text search within the 'ProjectGlossary' custom data category.
        *   Args: `query_term` (str, req), `limit` (int, opt).
    *   `search_custom_data_value_fts`: Full-text search across all custom data values, categories, and keys.
        *   Args: `query_term` (str, req), `category_filter` (str, opt), `limit` (int, opt).
*   **Context Linking:**
    *   `link_conport_items`: Creates a relationship link between two ConPort items, explicitly building out the **project knowledge graph**.
        *   Args: `source_item_type` (str, req), `source_item_id` (str, req), `target_item_type` (str, req), `target_item_id` (str, req), `relationship_type` (str, req), `description` (str, opt).
    *   `get_linked_items`: Retrieves items linked to a specific item.
        *   Args: `item_type` (str, req), `item_id` (str, req), `relationship_type_filter` (str, opt), `linked_item_type_filter` (str, opt), `limit` (int, opt).
*   **History & Meta Tools:**
    *   `get_item_history`: Retrieves version history for Product or Active Context.
        *   Args: `item_type` ("product_context" | "active_context", req), `version` (int, opt), `before_timestamp` (datetime, opt), `after_timestamp` (datetime, opt), `limit` (int, opt).
    *   `get_recent_activity_summary`: Provides a summary of recent ConPort activity.
        *   Args: `hours_ago` (int, opt), `since_timestamp` (datetime, opt), `limit_per_type` (int, opt, default: 5).
    *   `get_conport_schema`: Retrieves the schema of available ConPort tools and their arguments.
*   **Import/Export:**
    *   `export_conport_to_markdown`: Exports ConPort data to markdown files.
        *   Args: `output_path` (str, opt, default: "./conport_export/").
    *   `import_markdown_to_conport`: Imports data from markdown files into ConPort.
        *   Args: `input_path` (str, opt, default: "./conport_export/").
*   **Batch Operations:**
    *   `batch_log_items`: Logs multiple items of the same type (e.g., decisions, progress entries) in a single call.
        *   Args: `item_type` (str, req - e.g., "decision", "progress_entry"), `items` (list[dict], req - list of Pydantic model dicts for the item type).

## Prompt Caching Strategy

ConPort can be used to provide structured context (including **vector data** for semantic search) that AI assistants can leverage for **prompt caching** with compatible LLM providers (like Google Gemini, Anthropic Claude, and OpenAI). Prompt caching reduces token costs and latency by reusing frequently used parts of prompts.

This repository includes a detailed strategy file (`context_portal/prompt_caching_strategy.yml`) that defines how an LLM assistant should identify cacheable content from ConPort and structure prompts for different providers.

**Key aspects of the strategy include:**

*   **Identifying Cacheable Content:** Prioritizing large, stable context like Product Context, detailed System Patterns, or specific Custom Data entries (especially those flagged with a `cache_hint: true` metadata).
*   **Provider-Specific Interaction:**
    *   **Implicit Caching (Gemini, OpenAI):** Structure prompts by placing cacheable ConPort content at the absolute beginning of the prompt. The LLM provider automatically handles caching.
    *   **Explicit Caching (Anthropic):** Insert a `cache_control` breakpoint after the cacheable ConPort content within the prompt payload.
*   **User Hints:** ConPort's Custom Data can include metadata like `cache_hint: true` to explicitly guide the LLM assistant on content prioritization for caching.
*   **LLM Assistant Notification:** The LLM assistant is instructed to notify the user when it structures a prompt for potential caching (e.g., `[INFO: Structuring prompt for caching]`).

By using ConPort to manage your project's knowledge and providing the LLM assistant with this prompt caching strategy, you can enhance the efficiency and cost-effectiveness of your AI interactions.

## Further Reading

For a more in-depth understanding of ConPort's design, architecture, and advanced usage patterns, please refer to:
*   [`conport_mcp_deep_dive.md`](https://github.com/GreatScottyMac/context-portal/blob/main/conport_mcp_deep_dive.md)

## Contributing

Details on contributing to the ConPort project will be added here in the future.


## License

This project is licensed under the [Apache-2.0 license](https://github.com/GreatScottyMac/context-portal#).