"""Database interaction logic using sqlite3."""

import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta # Added timedelta

from ..core.config import get_database_path
from ..core.exceptions import DatabaseError, ConfigurationError
from . import models # Import models from the same directory

# --- Connection Handling ---

_connections: Dict[str, sqlite3.Connection] = {}

def get_db_connection(workspace_id: str) -> sqlite3.Connection:
    """Gets or creates a database connection for the given workspace."""
    if workspace_id in _connections:
        return _connections[workspace_id]

    try:
        db_path = get_database_path(workspace_id)
        conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        conn.row_factory = sqlite3.Row # Access columns by name
        _connections[workspace_id] = conn
        initialize_database(conn) # Ensure tables exist
        return conn
    except ConfigurationError as e:
        raise DatabaseError(f"Configuration error getting DB path for {workspace_id}: {e}")
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to connect to database for {workspace_id} at {db_path}: {e}")

def close_db_connection(workspace_id: str):
    """Closes the database connection for the given workspace, if open."""
    if workspace_id in _connections:
        _connections[workspace_id].close()
        del _connections[workspace_id]

def close_all_connections():
    """Closes all active database connections."""
    for workspace_id in list(_connections.keys()):
        close_db_connection(workspace_id)

# --- Database Initialization ---

def initialize_database(conn: sqlite3.Connection):
    """Creates database tables if they don't exist."""
    cursor = conn.cursor()
    try:
        # Product Context (Single Row)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_context (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                content TEXT NOT NULL DEFAULT '{}'
            )
        """)
        # Ensure the single row exists
        cursor.execute("INSERT OR IGNORE INTO product_context (id, content) VALUES (1, '{}')")

        # Active Context (Single Row)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_context (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                content TEXT NOT NULL DEFAULT '{}'
            )
        """)
        # Ensure the single row exists
        cursor.execute("INSERT OR IGNORE INTO active_context (id, content) VALUES (1, '{}')")

        # Decisions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL,
                summary TEXT NOT NULL,
                rationale TEXT,
                implementation_details TEXT,
                tags TEXT -- JSON stringified list of tags
            )
        """)
        try:
            cursor.execute("ALTER TABLE decisions ADD COLUMN tags TEXT")
        except sqlite3.OperationalError as e:
            if "duplicate column name: tags" in str(e).lower(): # Or use a more specific error check if available
                pass # Column already exists, ignore
            else:
                raise # Re-raise other operational errors

        # FTS5 table for decisions
        cursor.execute("DROP TABLE IF EXISTS decisions_fts") # Drop to ensure recreation with new schema if needed
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS decisions_fts USING fts5(
                summary,
                rationale,
                implementation_details,
                tags, -- Ensure tags column is definitely part of FTS
                tokenize = 'porter unicode61'
            )
        """)

        # Triggers to keep decisions_fts synchronized with decisions table
        # Re-creating triggers to ensure they use the correct schema for decisions_fts
        cursor.execute("DROP TRIGGER IF EXISTS decisions_ai")
        cursor.execute("""
            CREATE TRIGGER decisions_ai AFTER INSERT ON decisions BEGIN
                INSERT INTO decisions_fts (rowid, summary, rationale, implementation_details, tags)
                VALUES (new.id, new.summary, new.rationale, new.implementation_details, new.tags);
            END;
        """)
        cursor.execute("DROP TRIGGER IF EXISTS decisions_ad")
        cursor.execute("""
            CREATE TRIGGER decisions_ad AFTER DELETE ON decisions BEGIN
                DELETE FROM decisions_fts WHERE rowid=old.id;
            END;
        """)
        cursor.execute("DROP TRIGGER IF EXISTS decisions_au")
        cursor.execute("""
            CREATE TRIGGER decisions_au AFTER UPDATE ON decisions BEGIN
                UPDATE decisions_fts SET
                    summary = new.summary,
                    rationale = new.rationale,
                    implementation_details = new.implementation_details,
                    tags = new.tags
                WHERE rowid=new.id;
            END;
        """)

        # Progress Entries
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS progress_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL,
                status TEXT NOT NULL,
                description TEXT NOT NULL,
                parent_id INTEGER,
                FOREIGN KEY (parent_id) REFERENCES progress_entries(id) ON DELETE SET NULL
            )
        """)

        # System Patterns
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                tags TEXT, -- JSON stringified list of tags
                timestamp_created DATETIME DEFAULT CURRENT_TIMESTAMP,
                timestamp_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            cursor.execute("ALTER TABLE system_patterns ADD COLUMN tags TEXT")
        except sqlite3.OperationalError as e:
            if "duplicate column name: tags" not in str(e).lower(): raise
        try:
            cursor.execute("ALTER TABLE system_patterns ADD COLUMN timestamp_created DATETIME DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError as e:
            if "duplicate column name: timestamp_created" not in str(e).lower(): raise
        try:
            cursor.execute("ALTER TABLE system_patterns ADD COLUMN timestamp_updated DATETIME DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError as e:
            if "duplicate column name: timestamp_updated" not in str(e).lower(): raise

        # Custom Data
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS custom_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL, -- Store as JSON string
                timestamp_created DATETIME DEFAULT CURRENT_TIMESTAMP,
                timestamp_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(category, key)
            )
        """)
        try:
            cursor.execute("ALTER TABLE custom_data ADD COLUMN timestamp_created DATETIME DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError as e:
            if "duplicate column name: timestamp_created" not in str(e).lower(): raise
        try:
            cursor.execute("ALTER TABLE custom_data ADD COLUMN timestamp_updated DATETIME DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError as e:
            if "duplicate column name: timestamp_updated" not in str(e).lower(): raise

        # General FTS5 table for custom_data
        # Drop any old glossary-specific triggers first
        cursor.execute("DROP TRIGGER IF EXISTS custom_data_glossary_ai")
        cursor.execute("DROP TRIGGER IF EXISTS custom_data_glossary_ad")
        cursor.execute("DROP TRIGGER IF EXISTS custom_data_glossary_au")
        cursor.execute("DROP TABLE IF EXISTS custom_data_fts") # Drop to ensure recreation
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS custom_data_fts USING fts5(
                category,
                key,
                value_text, -- Stores the content of custom_data.value for FTS
                tokenize = 'porter unicode61'
            )
        """)

        # Triggers to keep general custom_data_fts synchronized
        cursor.execute("DROP TRIGGER IF EXISTS custom_data_ai_generic")
        cursor.execute("""
            CREATE TRIGGER custom_data_ai_generic
            AFTER INSERT ON custom_data
            BEGIN
                INSERT INTO custom_data_fts (rowid, category, key, value_text)
                VALUES (new.id, new.category, new.key, new.value); -- new.value is JSON string, FTS will index its text content
            END;
        """)
        cursor.execute("DROP TRIGGER IF EXISTS custom_data_ad_generic")
        cursor.execute("""
            CREATE TRIGGER custom_data_ad_generic
            AFTER DELETE ON custom_data
            BEGIN
                DELETE FROM custom_data_fts WHERE rowid=old.id;
            END;
        """)
        cursor.execute("DROP TRIGGER IF EXISTS custom_data_au_generic")
        cursor.execute("""
            CREATE TRIGGER custom_data_au_generic
            AFTER UPDATE ON custom_data
            BEGIN
                UPDATE custom_data_fts SET
                    category = new.category,
                    key = new.key,
                    value_text = new.value
                WHERE rowid=new.id;
            END;
        """)

        # Context Links
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS context_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                workspace_id TEXT NOT NULL,
                source_item_type TEXT NOT NULL,
                source_item_id TEXT NOT NULL,
                target_item_type TEXT NOT NULL,
                target_item_id TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                description TEXT
            )
        """)

        # Product Context History
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_context_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL,
                version INTEGER NOT NULL,
                content TEXT NOT NULL,
                change_source TEXT
            )
        """)
        # Index on version for faster lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_product_context_history_version ON product_context_history (version)")

        # Active Context History
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_context_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL,
                version INTEGER NOT NULL,
                content TEXT NOT NULL,
                change_source TEXT
            )
        """)
        # Index on version for faster lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_context_history_version ON active_context_history (version)")

        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise DatabaseError(f"Failed to initialize database tables: {e}")
    finally:
        cursor.close()


# --- Helper functions for history ---

def _get_latest_context_version(cursor: sqlite3.Cursor, table_name: str) -> int:
    """Retrieves the latest version number from a history table."""
    try:
        cursor.execute(f"SELECT MAX(version) FROM {table_name}")
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else 0
    except sqlite3.Error as e:
        # Log this error appropriately in a real application
        print(f"Error getting latest version from {table_name}: {e}")
        return 0 # Default to 0 if error or no versions found

def _add_context_history_entry(
    cursor: sqlite3.Cursor,
    history_table_name: str,
    version: int,
    content_dict: Dict[str, Any],
    change_source: Optional[str]
) -> None:
    """Adds an entry to the specified context history table."""
    content_json = json.dumps(content_dict)
    timestamp = datetime.utcnow()
    try:
        cursor.execute(
            f"""
            INSERT INTO {history_table_name} (timestamp, version, content, change_source)
            VALUES (?, ?, ?, ?)
            """,
            (timestamp, version, content_json, change_source)
        )
    except sqlite3.Error as e:
        # This error should be handled by the calling function's rollback
        raise DatabaseError(f"Failed to add entry to {history_table_name}: {e}")


# --- CRUD Operations ---

def get_product_context(workspace_id: str) -> models.ProductContext:
    """Retrieves the product context."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, content FROM product_context WHERE id = 1")
        row = cursor.fetchone()
        if row:
            content_dict = json.loads(row['content'])
            return models.ProductContext(id=row['id'], content=content_dict)
        else:
            # Should not happen if initialized correctly, but handle defensively
            raise DatabaseError("Product context row not found.")
    except (sqlite3.Error, json.JSONDecodeError) as e:
        raise DatabaseError(f"Failed to retrieve product context: {e}")
    finally:
        cursor.close()

def update_product_context(workspace_id: str, update_args: models.UpdateContextArgs) -> None:
    """Updates the product context using either full content or a patch."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    try:
        # Fetch current content to log to history
        cursor.execute("SELECT content FROM product_context WHERE id = 1")
        current_row = cursor.fetchone()
        if not current_row:
            raise DatabaseError("Product context row not found for updating (cannot log history).")
        current_content_dict = json.loads(current_row['content'])

        # Determine new content
        new_final_content = {}
        if update_args.content is not None:
            new_final_content = update_args.content
        elif update_args.patch_content is not None:
            # Apply patch to a copy of current_content_dict for the new state
            new_final_content = current_content_dict.copy()
            # Iterate over patch_content to handle __DELETE__ sentinel
            for key, value in update_args.patch_content.items():
                if value == "__DELETE__":
                    new_final_content.pop(key, None)  # Remove key, do nothing if key not found
                else:
                    new_final_content[key] = value
        else:
            # This case should be prevented by Pydantic model validation, but handle defensively
            raise ValueError("No content or patch_content provided for update.")

        # Log previous version to history
        latest_version = _get_latest_context_version(cursor, "product_context_history")
        new_version = latest_version + 1
        _add_context_history_entry(
            cursor,
            "product_context_history",
            new_version,
            current_content_dict, # Log the content *before* the update
            "update_product_context" # Basic change source
        )

        # Update the main product_context table
        new_content_json = json.dumps(new_final_content)
        cursor.execute("UPDATE product_context SET content = ? WHERE id = 1", (new_content_json,))
        
        conn.commit()
        # No need to check rowcount here as history is logged regardless of content identity
    except (sqlite3.Error, TypeError, json.JSONDecodeError, DatabaseError) as e: # Added DatabaseError
        conn.rollback()
        raise DatabaseError(f"Failed to update product_context: {e}")
    finally:
        cursor.close()
def get_active_context(workspace_id: str) -> models.ActiveContext:
    """Retrieves the active context."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, content FROM active_context WHERE id = 1")
        row = cursor.fetchone()
        if row:
            content_dict = json.loads(row['content'])
            return models.ActiveContext(id=row['id'], content=content_dict)
        else:
            raise DatabaseError("Active context row not found.")
    except (sqlite3.Error, json.JSONDecodeError) as e:
        raise DatabaseError(f"Failed to retrieve active context: {e}")
    finally:
        cursor.close()

def update_active_context(workspace_id: str, update_args: models.UpdateContextArgs) -> None:
    """Updates the active context using either full content or a patch."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    try:
        # Fetch current content to log to history
        cursor.execute("SELECT content FROM active_context WHERE id = 1")
        current_row = cursor.fetchone()
        if not current_row:
            raise DatabaseError("Active context row not found for updating (cannot log history).")
        current_content_dict = json.loads(current_row['content'])

        # Determine new content
        new_final_content = {}
        if update_args.content is not None:
            new_final_content = update_args.content
        elif update_args.patch_content is not None:
            new_final_content = current_content_dict.copy()
            # Iterate over patch_content to handle __DELETE__ sentinel
            for key, value in update_args.patch_content.items():
                if value == "__DELETE__":
                    new_final_content.pop(key, None)  # Remove key, do nothing if key not found
                else:
                    new_final_content[key] = value
        else:
            # This case should be prevented by Pydantic model validation, but handle defensively
            raise ValueError("No content or patch_content provided for update.")

        # Log previous version to history
        latest_version = _get_latest_context_version(cursor, "active_context_history")
        new_version = latest_version + 1
        _add_context_history_entry(
            cursor,
            "active_context_history",
            new_version,
            current_content_dict, # Log the content *before* the update
            "update_active_context" # Basic change source
        )

        # Update the main active_context table
        new_content_json = json.dumps(new_final_content)
        cursor.execute("UPDATE active_context SET content = ? WHERE id = 1", (new_content_json,))
        
        conn.commit()
    except (sqlite3.Error, TypeError, json.JSONDecodeError, DatabaseError) as e: # Added DatabaseError
        conn.rollback()
        raise DatabaseError(f"Failed to update active context: {e}")
    finally:
        cursor.close()

# --- Add more CRUD functions for other models (ActiveContext, Decision, etc.) ---
# Example: log_decision
def log_decision(workspace_id: str, decision_data: models.Decision) -> models.Decision:
    """Logs a new decision."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    sql = """
        INSERT INTO decisions (timestamp, summary, rationale, implementation_details, tags)
        VALUES (?, ?, ?, ?, ?)
    """
    tags_json = json.dumps(decision_data.tags) if decision_data.tags is not None else None
    params = (
        decision_data.timestamp,
        decision_data.summary,
        decision_data.rationale,
        decision_data.implementation_details,
        tags_json
    )
    try:
        cursor.execute(sql, params)
        decision_id = cursor.lastrowid
        conn.commit()
        # Return the full decision object including the new ID
        decision_data.id = decision_id
        return decision_data
    except sqlite3.Error as e:
        conn.rollback()
        raise DatabaseError(f"Failed to log decision: {e}")
    finally:
        cursor.close()

def get_decisions(
    workspace_id: str,
    limit: Optional[int] = None,
    tags_filter_include_all: Optional[List[str]] = None,
    tags_filter_include_any: Optional[List[str]] = None
) -> List[models.Decision]:
    """Retrieves decisions, optionally limited, and filtered by tags."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    
    base_sql = "SELECT id, timestamp, summary, rationale, implementation_details, tags FROM decisions"
    conditions = []
    params_list: List[Any] = []

    # Pydantic model validation ensures only one of these is present.
    if tags_filter_include_any and len(tags_filter_include_any) > 0:
        placeholders = ", ".join(["?"] * len(tags_filter_include_any))
        # Ensure decisions.tags is not NULL and is a valid JSON array before json_each
        conditions.append(f"json_valid(decisions.tags) AND EXISTS (SELECT 1 FROM json_each(decisions.tags) WHERE json_each.value IN ({placeholders}))")
        params_list.extend(tags_filter_include_any)

    if tags_filter_include_all and len(tags_filter_include_all) > 0:
        # Using the COUNT DISTINCT approach
        placeholders = ", ".join(["?"] * len(tags_filter_include_all))
        # Ensure decisions.tags is not NULL and is a valid JSON array
        conditions.append(
            f"json_valid(decisions.tags) AND (SELECT COUNT(DISTINCT je.value) FROM json_each(decisions.tags) je WHERE je.value IN ({placeholders})) = ?"
        )
        params_list.extend(tags_filter_include_all)
        params_list.append(len(tags_filter_include_all))

    # ORDER BY must come before LIMIT
    order_by_clause = " ORDER BY timestamp DESC"
    
    limit_clause = ""
    if limit is not None and limit > 0:
        # Limit must be applied after all filtering.
        # If there are conditions, LIMIT is part of the main query.
        # If no conditions, it's added directly.
        pass # Limit will be added at the end of SQL construction

    # Construct the SQL query
    sql = base_sql
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    
    sql += order_by_clause
    
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params_list.append(limit)
        
    params_tuple = tuple(params_list)

    try:
        cursor.execute(sql, params_tuple)
        rows = cursor.fetchall()
        decisions = [
            models.Decision(
                id=row['id'],
                timestamp=row['timestamp'],
                summary=row['summary'],
                rationale=row['rationale'],
                implementation_details=row['implementation_details'],
                tags=json.loads(row['tags']) if row['tags'] else None
            ) for row in rows
        ]
        # Python-based filtering is now removed
        return decisions
    except (sqlite3.Error, json.JSONDecodeError) as e: # Added JSONDecodeError
        raise DatabaseError(f"Failed to retrieve decisions with SQL filtering: {e}")
    finally:
        cursor.close()

def search_decisions_fts(workspace_id: str, query_term: str, limit: Optional[int] = 10) -> List[models.Decision]:
    """Searches decisions using FTS5 for the given query term."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    # The MATCH operator is used for FTS queries.
    # We join back to the original 'decisions' table to get all columns.
    # 'rank' is an FTS5 auxiliary function that indicates relevance.
    sql = """
        SELECT d.id, d.timestamp, d.summary, d.rationale, d.implementation_details, d.tags
        FROM decisions_fts f
        JOIN decisions d ON f.rowid = d.id
        WHERE f.decisions_fts MATCH ? ORDER BY rank
    """
    params_list = [query_term]

    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params_list.append(limit)

    try:
        cursor.execute(sql, tuple(params_list))
        rows = cursor.fetchall()
        decisions_found = [
            models.Decision(
                id=row['id'],
                timestamp=row['timestamp'],
                summary=row['summary'],
                rationale=row['rationale'],
                implementation_details=row['implementation_details'],
                tags=json.loads(row['tags']) if row['tags'] else None
            ) for row in rows
        ]
        return decisions_found
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed FTS search on decisions for term '{query_term}': {e}")
    finally:
        cursor.close()

def delete_decision_by_id(workspace_id: str, decision_id: int) -> bool:
    """Deletes a decision by its ID. Returns True if deleted, False otherwise."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    sql = "DELETE FROM decisions WHERE id = ?"
    try:
        cursor.execute(sql, (decision_id,))
        # The FTS table 'decisions_fts' should be updated automatically by its AFTER DELETE trigger.
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        conn.rollback()
        raise DatabaseError(f"Failed to delete decision with ID {decision_id}: {e}")
    finally:
        cursor.close()

def log_progress(workspace_id: str, progress_data: models.ProgressEntry) -> models.ProgressEntry:
    """Logs a new progress entry."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    sql = """
        INSERT INTO progress_entries (timestamp, status, description, parent_id)
        VALUES (?, ?, ?, ?)
    """
    params = (
        progress_data.timestamp,
        progress_data.status,
        progress_data.description,
        progress_data.parent_id
    )
    try:
        cursor.execute(sql, params)
        progress_id = cursor.lastrowid
        conn.commit()
        progress_data.id = progress_id
        return progress_data
    except sqlite3.Error as e:
        conn.rollback()
        # Consider checking for foreign key constraint errors if parent_id is invalid
        raise DatabaseError(f"Failed to log progress entry: {e}")
    finally:
        cursor.close()
def get_progress(
    workspace_id: str,
    status_filter: Optional[str] = None,
    parent_id_filter: Optional[int] = None,
    limit: Optional[int] = None
) -> List[models.ProgressEntry]:
    """Retrieves progress entries, optionally filtered and limited."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    sql = "SELECT id, timestamp, status, description, parent_id FROM progress_entries"
    conditions = []
    params_list = []

    if status_filter:
        conditions.append("status = ?")
        params_list.append(status_filter)
    if parent_id_filter is not None: # Check for None explicitly as 0 could be a valid parent_id
        conditions.append("parent_id = ?")
        params_list.append(parent_id_filter)
    # Add more filters if needed (e.g., date range)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY timestamp DESC" # Default order: newest first

    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params_list.append(limit)

    params = tuple(params_list)

    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        progress_entries = [
            models.ProgressEntry(
                id=row['id'],
                timestamp=row['timestamp'],
                status=row['status'],
                description=row['description'],
                parent_id=row['parent_id']
            ) for row in rows
        ]
        # progress_entries.reverse() # Optional: uncomment to return oldest first
        return progress_entries
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to retrieve progress entries: {e}")
    finally:
        cursor.close()

def get_progress_entry_by_id(workspace_id: str, progress_id: int) -> Optional[models.ProgressEntry]:
    """Retrieves a specific progress entry by its ID."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    sql = "SELECT id, timestamp, status, description, parent_id FROM progress_entries WHERE id = ?"
    try:
        cursor.execute(sql, (progress_id,))
        row = cursor.fetchone()
        if row:
            return models.ProgressEntry(
                id=row['id'],
                timestamp=row['timestamp'],
                status=row['status'],
                description=row['description'],
                parent_id=row['parent_id']
            )
        else:
            return None # No entry found with that ID
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to retrieve progress entry with ID {progress_id}: {e}")
    finally:
        cursor.close()

def update_progress_entry(workspace_id: str, update_args: models.UpdateProgressArgs) -> bool:
    """
    Updates an existing progress entry by its ID.
    Returns True if the entry was found and updated, False otherwise.
    """
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    
    sql = "UPDATE progress_entries SET"
    updates = []
    params_list: List[Any] = []

    if update_args.status is not None:
        updates.append("status = ?")
        params_list.append(update_args.status)
    if update_args.description is not None:
        updates.append("description = ?")
        params_list.append(update_args.description)
    # Handle parent_id update, including setting to NULL if explicitly None is intended (though Pydantic allows Optional[int])
    # If parent_id is provided as 0 or a positive int, update it.
    # If parent_id is provided as None, set the DB column to NULL.
    # If parent_id is NOT provided in args (remains default None), do not include in update.
    # The Pydantic model check_at_least_one_field ensures at least one field is provided,
    # so we don't need to worry about an empty updates list here.
    if 'parent_id' in update_args.model_fields_set: # Check if parent_id was explicitly set in the input args
         updates.append("parent_id = ?")
         params_list.append(update_args.parent_id) # SQLite handles Python None as NULL

    if not updates:
         # This case should be prevented by Pydantic model validation, but as a safeguard
         raise ValueError("No fields provided for update.")

    sql += " " + ", ".join(updates) + " WHERE id = ?"
    params_list.append(update_args.progress_id)
    params = tuple(params_list)

    try:
        cursor.execute(sql, params)
        conn.commit()
        return cursor.rowcount > 0 # Return True if one row was updated
    except sqlite3.Error as e:
        conn.rollback()
        raise DatabaseError(f"Failed to update progress entry with ID {update_args.progress_id}: {e}")
    finally:
        cursor.close()

def delete_progress_entry_by_id(workspace_id: str, progress_id: int) -> bool:
    """
    Deletes a progress entry by its ID.
    Note: This will also set the parent_id of any child tasks to NULL due to FOREIGN KEY ON DELETE SET NULL.
    Returns True if deleted, False otherwise.
    """
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    sql = "DELETE FROM progress_entries WHERE id = ?"
    try:
        cursor.execute(sql, (progress_id,))
        conn.commit()
        return cursor.rowcount > 0 # Return True if one row was deleted
    except sqlite3.Error as e:
        conn.rollback()
        raise DatabaseError(f"Failed to delete progress entry with ID {progress_id}: {e}")
    finally:
        cursor.close()
def log_system_pattern(workspace_id: str, pattern_data: models.SystemPattern) -> models.SystemPattern:
    """Logs or updates a system pattern, managing timestamps correctly."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    tags_json = json.dumps(pattern_data.tags) if pattern_data.tags is not None else None
    current_time = datetime.utcnow()

    try:
        # Check if pattern already exists
        cursor.execute("SELECT id, timestamp_created FROM system_patterns WHERE name = ?", (pattern_data.name,))
        existing_pattern = cursor.fetchone()

        if existing_pattern:
            # Update existing pattern
            pattern_id = existing_pattern['id']
            timestamp_created = existing_pattern['timestamp_created'] # Keep original creation time
            sql_update = """
                UPDATE system_patterns
                SET description = ?, tags = ?, timestamp_updated = ?
                WHERE id = ?
            """
            params_update = (pattern_data.description, tags_json, current_time, pattern_id)
            cursor.execute(sql_update, params_update)
            pattern_data.id = pattern_id
            pattern_data.timestamp_created = timestamp_created
            pattern_data.timestamp_updated = current_time
        else:
            # Insert new pattern
            sql_insert = """
                INSERT INTO system_patterns (name, description, tags, timestamp_created, timestamp_updated)
                VALUES (?, ?, ?, ?, ?)
            """
            params_insert = (pattern_data.name, pattern_data.description, tags_json, current_time, current_time)
            cursor.execute(sql_insert, params_insert)
            pattern_data.id = cursor.lastrowid
            pattern_data.timestamp_created = current_time
            pattern_data.timestamp_updated = current_time
        
        conn.commit()
        return pattern_data
    except sqlite3.Error as e:
        conn.rollback()
        raise DatabaseError(f"Failed to log system pattern '{pattern_data.name}': {e}")
    finally:
        cursor.close()

def get_system_patterns(
    workspace_id: str,
    tags_filter_include_all: Optional[List[str]] = None,
    tags_filter_include_any: Optional[List[str]] = None
    # limit: Optional[int] = None, # Add if pagination is desired
) -> List[models.SystemPattern]:
    """Retrieves system patterns, optionally filtered by tags using SQL JSON1, including timestamps."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    
    base_sql = "SELECT id, name, description, tags, timestamp_created, timestamp_updated FROM system_patterns"
    conditions = []
    params_list: List[Any] = []

    # Pydantic model validation ensures only one of these is present.
    if tags_filter_include_any and len(tags_filter_include_any) > 0:
        placeholders = ", ".join(["?"] * len(tags_filter_include_any))
        # Ensure system_patterns.tags is not NULL and is a valid JSON array
        conditions.append(f"json_valid(system_patterns.tags) AND EXISTS (SELECT 1 FROM json_each(system_patterns.tags) WHERE json_each.value IN ({placeholders}))")
        params_list.extend(tags_filter_include_any)

    if tags_filter_include_all and len(tags_filter_include_all) > 0:
        placeholders = ", ".join(["?"] * len(tags_filter_include_all))
        # Ensure system_patterns.tags is not NULL and is a valid JSON array
        conditions.append(
            f"json_valid(system_patterns.tags) AND (SELECT COUNT(DISTINCT je.value) FROM json_each(system_patterns.tags) je WHERE je.value IN ({placeholders})) = ?"
        )
        params_list.extend(tags_filter_include_all)
        params_list.append(len(tags_filter_include_all))

    order_by_clause = " ORDER BY name ASC"
    # limit_clause handling can be added here if 'limit' parameter is introduced to this function
    # For now, no limit parameter is defined for get_system_patterns.

    sql = base_sql
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    
    sql += order_by_clause
    
    params_tuple = tuple(params_list)

    try:
        cursor.execute(sql, params_tuple)
        rows = cursor.fetchall()
        patterns = [
            models.SystemPattern(
                id=row['id'],
                name=row['name'],
                description=row['description'],
                tags=json.loads(row['tags']) if row['tags'] else None,
                timestamp_created=row['timestamp_created'],
                timestamp_updated=row['timestamp_updated']
            ) for row in rows
        ]
        # Python-based filtering is now removed
        return patterns
    except (sqlite3.Error, json.JSONDecodeError) as e: # Added JSONDecodeError
        raise DatabaseError(f"Failed to retrieve system patterns with SQL filtering: {e}")
    finally:
        cursor.close()

def delete_system_pattern_by_id(workspace_id: str, pattern_id: int) -> bool:
    """Deletes a system pattern by its ID. Returns True if deleted, False otherwise."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    sql = "DELETE FROM system_patterns WHERE id = ?"
    # Note: System patterns do not currently have an FTS table, so no trigger concerns here.
    try:
        cursor.execute(sql, (pattern_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        conn.rollback()
        raise DatabaseError(f"Failed to delete system pattern with ID {pattern_id}: {e}")
    finally:
        cursor.close()

def log_custom_data(workspace_id: str, data: models.CustomData) -> models.CustomData:
    """Logs or updates a custom data entry, managing timestamps correctly."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    current_time = datetime.utcnow()
    value_json = json.dumps(data.value) # Ensure value is serialized to JSON string

    try:
        # Check if custom data entry already exists
        cursor.execute("SELECT id, timestamp_created FROM custom_data WHERE category = ? AND key = ?", (data.category, data.key))
        existing_data = cursor.fetchone()

        if existing_data:
            # Update existing entry
            data_id = existing_data['id']
            timestamp_created = existing_data['timestamp_created'] # Keep original creation time
            sql_update = """
                UPDATE custom_data
                SET value = ?, timestamp_updated = ?
                WHERE id = ?
            """
            params_update = (value_json, current_time, data_id)
            cursor.execute(sql_update, params_update)
            data.id = data_id
            data.timestamp_created = timestamp_created
            data.timestamp_updated = current_time
        else:
            # Insert new entry
            sql_insert = """
                INSERT INTO custom_data (category, key, value, timestamp_created, timestamp_updated)
                VALUES (?, ?, ?, ?, ?)
            """
            params_insert = (data.category, data.key, value_json, current_time, current_time)
            cursor.execute(sql_insert, params_insert)
            data.id = cursor.lastrowid
            data.timestamp_created = current_time
            data.timestamp_updated = current_time
            
        conn.commit()
        return data
    except (sqlite3.Error, TypeError) as e: # TypeError for json.dumps
        conn.rollback()
        raise DatabaseError(f"Failed to log custom data for '{data.category}/{data.key}': {e}")
    finally:
        cursor.close()

def get_custom_data(
    workspace_id: str,
    category: Optional[str] = None,
    key: Optional[str] = None
) -> List[models.CustomData]:
    """Retrieves custom data entries, optionally filtered by category and/or key, including timestamps."""
    if key and not category:
        raise ValueError("Cannot filter by key without specifying a category.")

    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    sql = "SELECT id, category, key, value, timestamp_created, timestamp_updated FROM custom_data"
    conditions = []
    params_list = []

    if category:
        conditions.append("category = ?")
        params_list.append(category)
    if key: # We already ensured category is present if key is
        conditions.append("key = ?")
        params_list.append(key)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY category ASC, key ASC" # Consistent ordering
    params = tuple(params_list)

    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        custom_data_list = []
        for row in rows:
            try:
                # Deserialize value from JSON string
                value_data = json.loads(row['value'])
                custom_data_list.append(
                    models.CustomData(
                        id=row['id'],
                        category=row['category'],
                        key=row['key'],
                        value=value_data,
                        timestamp_created=row['timestamp_created'],
                        timestamp_updated=row['timestamp_updated']
                    )
                )
            except json.JSONDecodeError as e:
                # Log or handle error for specific row if JSON is invalid
                print(f"Warning: Failed to decode JSON for custom_data id={row['id']}: {e}") # Replace with proper logging
                continue # Skip this row
        return custom_data_list
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to retrieve custom data: {e}")
    finally:
        cursor.close()

def delete_custom_data(workspace_id: str, category: str, key: str) -> bool:
    """Deletes a specific custom data entry by category and key. Returns True if deleted, False otherwise."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    sql = "DELETE FROM custom_data WHERE category = ? AND key = ?"
    params = (category, key)
    try:
        cursor.execute(sql, params)
        conn.commit()
        return cursor.rowcount > 0 # Return True if one row was deleted
    except sqlite3.Error as e:
        conn.rollback()
        raise DatabaseError(f"Failed to delete custom data for '{category}/{key}': {e}")
    finally:
        cursor.close()

def log_context_link(workspace_id: str, link_data: models.ContextLink) -> models.ContextLink:
    """Logs a new context link."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    sql = """
        INSERT INTO context_links (
            workspace_id, source_item_type, source_item_id,
            target_item_type, target_item_id, relationship_type, description, timestamp
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    # Use link_data.timestamp if provided (e.g. from an import), else it defaults in DB
    # However, our Pydantic model ContextLink has default_factory=datetime.utcnow for timestamp
    # So, link_data.timestamp will always be populated.
    params = (
        workspace_id, # Storing workspace_id explicitly in the table
        link_data.source_item_type,
        str(link_data.source_item_id), # Ensure IDs are stored as text
        link_data.target_item_type,
        str(link_data.target_item_id), # Ensure IDs are stored as text
        link_data.relationship_type,
        link_data.description,
        link_data.timestamp # Pydantic model ensures this is set
    )
    try:
        cursor.execute(sql, params)
        link_id = cursor.lastrowid
        conn.commit()
        link_data.id = link_id
        # The timestamp from the DB default might be slightly different if we didn't pass it,
        # but since our Pydantic model sets it, what we have in link_data.timestamp is accurate.
        return link_data
    except sqlite3.Error as e:
        conn.rollback()
        raise DatabaseError(f"Failed to log context link: {e}")
    finally:
        cursor.close()

def get_context_links(
    workspace_id: str,
    item_type: str,
    item_id: str,
    relationship_type_filter: Optional[str] = None,
    linked_item_type_filter: Optional[str] = None,
    limit: Optional[int] = None
) -> List[models.ContextLink]:
    """
    Retrieves links for a given item, with optional filters.
    Finds links where the given item is EITHER the source OR the target.
    """
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    
    # Ensure item_id is treated as string for consistent querying with TEXT columns
    str_item_id = str(item_id)

    base_sql = """
        SELECT id, timestamp, workspace_id, source_item_type, source_item_id,
               target_item_type, target_item_id, relationship_type, description
        FROM context_links
    """
    conditions = []
    params_list = []

    # Main condition: item is either source or target
    conditions.append(
        "((source_item_type = ? AND source_item_id = ?) OR (target_item_type = ? AND target_item_id = ?))"
    )
    params_list.extend([item_type, str_item_id, item_type, str_item_id])
    
    # Add workspace_id filter for safety, though connection is already workspace-specific
    conditions.append("workspace_id = ?")
    params_list.append(workspace_id)

    if relationship_type_filter:
        conditions.append("relationship_type = ?")
        params_list.append(relationship_type_filter)
    
    if linked_item_type_filter:
        # This filter applies to the "other end" of the link
        conditions.append(
            "((source_item_type = ? AND source_item_id = ? AND target_item_type = ?) OR " +
            "(target_item_type = ? AND target_item_id = ? AND source_item_type = ?))"
        )
        params_list.extend([item_type, str_item_id, linked_item_type_filter,
                            item_type, str_item_id, linked_item_type_filter])

    if conditions:
        sql = base_sql + " WHERE " + " AND ".join(conditions)
    else: # Should not happen due to main condition and workspace_id
        sql = base_sql

    sql += " ORDER BY timestamp DESC"

    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params_list.append(limit)
    
    params = tuple(params_list)

    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        links = [
            models.ContextLink(
                id=row['id'],
                timestamp=row['timestamp'],
                # workspace_id=row['workspace_id'], # Not part of ContextLink Pydantic model
                source_item_type=row['source_item_type'],
                source_item_id=row['source_item_id'],
                target_item_type=row['target_item_type'],
                target_item_id=row['target_item_id'],
                relationship_type=row['relationship_type'],
                description=row['description']
            ) for row in rows
        ]
        return links
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to retrieve context links: {e}")
    finally:
        cursor.close()

def search_project_glossary_fts(workspace_id: str, query_term: str, limit: Optional[int] = 10) -> List[models.CustomData]:
    """Searches ProjectGlossary entries in custom_data using FTS5."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    # Updated to use the new general custom_data_fts table structure
    sql = """
        SELECT cd.id, cd.category, cd.key, cd.value
        FROM custom_data_fts fts
        JOIN custom_data cd ON fts.rowid = cd.id
        WHERE fts.custom_data_fts MATCH ? AND fts.category = 'ProjectGlossary'
        ORDER BY rank
    """
    # The MATCH query will search category, key, and value_text.
    # We explicitly filter for ProjectGlossary category after the FTS match.
    # Note: The MATCH query will search across 'term' and 'definition_text' columns in custom_data_fts
    params_list = [query_term]

    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params_list.append(limit)

    try:
        cursor.execute(sql, tuple(params_list))
        rows = cursor.fetchall()
        glossary_entries = []
        for row in rows:
            try:
                value_data = json.loads(row['value'])
                glossary_entries.append(
                    models.CustomData(
                        id=row['id'],
                        category=row['category'],
                        key=row['key'],
                        value=value_data
                    )
                )
            except json.JSONDecodeError as e:
                # Log or handle error for specific row if JSON is invalid
                print(f"Warning: Failed to decode JSON for glossary item id={row['id']}: {e}") # Replace with proper logging
                continue # Skip this row
        return glossary_entries
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed FTS search on ProjectGlossary for term '{query_term}': {e}")
    finally:
        cursor.close()

def search_custom_data_value_fts(
    workspace_id: str,
    query_term: str,
    category_filter: Optional[str] = None,
    limit: Optional[int] = 10
) -> List[models.CustomData]:
    """Searches all custom_data entries using FTS5 on category, key, and value.
       Optionally filters by category after FTS."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    
    sql = """
        SELECT cd.id, cd.category, cd.key, cd.value
        FROM custom_data_fts fts
        JOIN custom_data cd ON fts.rowid = cd.id
        WHERE fts.custom_data_fts MATCH ?
    """
    params_list = [query_term]

    if category_filter:
        sql += " AND fts.category = ?" # Filter by category on the FTS table
        params_list.append(category_filter)
        
    sql += " ORDER BY rank"

    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params_list.append(limit)

    try:
        cursor.execute(sql, tuple(params_list))
        rows = cursor.fetchall()
        results = []
        for row in rows:
            try:
                value_data = json.loads(row['value'])
                results.append(
                    models.CustomData(
                        id=row['id'],
                        category=row['category'],
                        key=row['key'],
                        value=value_data
                    )
                )
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to decode JSON for custom_data id={row['id']} (search_custom_data_value_fts): {e}")
                continue
        return results
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed FTS search on custom_data for term '{query_term}': {e}")
    finally:
        cursor.close()

def get_item_history(
    workspace_id: str,
    args: models.GetItemHistoryArgs
) -> List[Dict[str, Any]]: # Returning list of dicts for now, could be Pydantic models
    """Retrieves history for product_context or active_context."""
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()

    if args.item_type == "product_context":
        history_table_name = "product_context_history"
        # history_model = models.ProductContextHistory # If returning Pydantic models
    elif args.item_type == "active_context":
        history_table_name = "active_context_history"
        # history_model = models.ActiveContextHistory # If returning Pydantic models
    else:
        # This should be caught by Pydantic validation in GetItemHistoryArgs
        raise ValueError("Invalid item_type for history retrieval.")

    sql = f"SELECT id, timestamp, version, content, change_source FROM {history_table_name}"
    conditions = []
    params_list = []

    if args.version is not None:
        conditions.append("version = ?")
        params_list.append(args.version)
    if args.before_timestamp:
        conditions.append("timestamp < ?")
        params_list.append(args.before_timestamp)
    if args.after_timestamp:
        conditions.append("timestamp > ?")
        params_list.append(args.after_timestamp)
    
    # Add workspace_id filter if it were part of the history table (it's not currently)
    # conditions.append("workspace_id = ?")
    # params_list.append(workspace_id)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY version DESC, timestamp DESC" # Most recent version/timestamp first

    if args.limit is not None and args.limit > 0:
        sql += " LIMIT ?"
        params_list.append(args.limit)

    params = tuple(params_list)

    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        history_entries = []
        for row in rows:
            content_dict = json.loads(row['content'])
            history_entries.append({
                "id": row['id'],
                "timestamp": row['timestamp'], # Already datetime object
                "version": row['version'],
                "content": content_dict,
                "change_source": row['change_source']
            })
            # Or if using Pydantic models:
            # history_entries.append(history_model(id=row['id'], timestamp=row['timestamp'], ...))
        return history_entries
    except (sqlite3.Error, json.JSONDecodeError) as e:
        raise DatabaseError(f"Failed to retrieve history for {args.item_type}: {e}")
    finally:
        cursor.close()

# --- Recent Activity Summary ---

def get_recent_activity_summary_data(
workspace_id: str,
hours_ago: Optional[int] = None,
since_timestamp: Optional[datetime] = None,
limit_per_type: int = 5
) -> Dict[str, Any]:
    """
    Retrieves a summary of recent activity across various ConPort items.
    """
    conn = get_db_connection(workspace_id)
    cursor = conn.cursor()
    summary_results: Dict[str, Any] = {
        "recent_decisions": [],
        "recent_progress_entries": [],
            "recent_system_patterns": [], # Added
            "recent_custom_data": [],     # Added
        "recent_product_context_updates": [],
        "recent_active_context_updates": [],
        "recent_links_created": [],
        "notes": []
    }

    now_utc = datetime.utcnow()
    summary_results["summary_period_end"] = now_utc.isoformat()

    if since_timestamp:
        start_datetime = since_timestamp
    elif hours_ago:
        start_datetime = now_utc - timedelta(hours=hours_ago)
    else:
        start_datetime = now_utc - timedelta(hours=24) # Default to last 24 hours

    summary_results["summary_period_start"] = start_datetime.isoformat()

    try:
        # Recent Decisions
        cursor.execute(
            """
            SELECT id, timestamp, summary, rationale, implementation_details, tags
            FROM decisions WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?
            """,
            (start_datetime, limit_per_type)
        )
        rows = cursor.fetchall()
        summary_results["recent_decisions"] = [
            models.Decision(
                id=row['id'], timestamp=row['timestamp'], summary=row['summary'],
                rationale=row['rationale'], implementation_details=row['implementation_details'],
                tags=json.loads(row['tags']) if row['tags'] else None
            ).model_dump(mode='json') for row in rows
        ]

        # Recent Progress Entries
        cursor.execute(
            """
            SELECT id, timestamp, status, description, parent_id
            FROM progress_entries WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?
            """,
            (start_datetime, limit_per_type)
        )
        rows = cursor.fetchall()
        summary_results["recent_progress_entries"] = [
            models.ProgressEntry(
                id=row['id'], timestamp=row['timestamp'], status=row['status'],
                description=row['description'], parent_id=row['parent_id']
            ).model_dump(mode='json') for row in rows
        ]

        # Recent Product Context Updates (from history)
        cursor.execute(
            """
            SELECT id, timestamp, version, content, change_source
            FROM product_context_history WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?
            """,
            (start_datetime, limit_per_type)
        )
        rows = cursor.fetchall()
        summary_results["recent_product_context_updates"] = [
            models.ProductContextHistory(
                id=row['id'], timestamp=row['timestamp'], version=row['version'],
                content=json.loads(row['content']), change_source=row['change_source']
            ).model_dump(mode='json') for row in rows
        ]

        # Recent Active Context Updates (from history)
        cursor.execute(
            """
            SELECT id, timestamp, version, content, change_source
            FROM active_context_history WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?
            """,
            (start_datetime, limit_per_type)
        )
        rows = cursor.fetchall()
        summary_results["recent_active_context_updates"] = [
            models.ActiveContextHistory(
                id=row['id'], timestamp=row['timestamp'], version=row['version'],
                content=json.loads(row['content']), change_source=row['change_source']
            ).model_dump(mode='json') for row in rows
        ]
        
        # Recent Links Created
        cursor.execute(
            """
            SELECT id, timestamp, source_item_type, source_item_id, target_item_type, target_item_id, relationship_type, description
            FROM context_links WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?
            """,
            (start_datetime, limit_per_type)
        )
        rows = cursor.fetchall()
        summary_results["recent_links_created"] = [
            models.ContextLink(
                id=row['id'], timestamp=row['timestamp'], source_item_type=row['source_item_type'],
                source_item_id=row['source_item_id'], target_item_type=row['target_item_type'],
                target_item_id=row['target_item_id'], relationship_type=row['relationship_type'],
                description=row['description']
            ).model_dump(mode='json') for row in rows
        ]

        # Note about missing timestamps
        # Recent System Patterns
        cursor.execute(
            """
            SELECT id, name, description, tags, timestamp_created, timestamp_updated
            FROM system_patterns WHERE timestamp_updated >= ? ORDER BY timestamp_updated DESC LIMIT ?
            """,
            (start_datetime, limit_per_type)
        )
        rows = cursor.fetchall()
        summary_results["recent_system_patterns"] = [
            models.SystemPattern(
                id=row['id'], name=row['name'], description=row['description'],
                tags=json.loads(row['tags']) if row['tags'] else None,
                timestamp_created=row['timestamp_created'],
                timestamp_updated=row['timestamp_updated']
            ).model_dump(mode='json') for row in rows
        ]

        # Recent Custom Data
        cursor.execute(
            """
            SELECT id, category, key, value, timestamp_created, timestamp_updated
            FROM custom_data WHERE timestamp_updated >= ? ORDER BY timestamp_updated DESC LIMIT ?
            """,
            (start_datetime, limit_per_type)
        )
        rows = cursor.fetchall()
        custom_data_list = []
        for row in rows:
            try:
                value_data = json.loads(row['value'])
                custom_data_list.append(
                    models.CustomData(
                        id=row['id'], category=row['category'], key=row['key'], value=value_data,
                        timestamp_created=row['timestamp_created'],
                        timestamp_updated=row['timestamp_updated']
                    ).model_dump(mode='json')
                )
            except json.JSONDecodeError: # pragma: no cover
                # This might happen if data was somehow stored incorrectly before JSON enforcement
                # Or if a non-JSON string is stored despite model typing (e.g. direct DB manipulation)
                print(f"Warning: Could not decode JSON for custom_data ID {row['id']} in recent activity summary.")
        summary_results["recent_custom_data"] = custom_data_list
        
        # Clear or update notes if they are no longer relevant
        # For now, let's remove the old note since timestamps are added.
        # A more dynamic note system could be implemented if needed.
        # summary_results["notes"].append("...") # Add new notes if any

        return summary_results

    except (sqlite3.Error, json.JSONDecodeError) as e:
        raise DatabaseError(f"Failed to retrieve recent activity summary: {e}")
    finally:
        cursor.close()

# (All planned CRUD functions implemented)

# --- Cleanup ---
# Consider using a context manager or atexit to ensure connections are closed
import atexit
atexit.register(close_all_connections)