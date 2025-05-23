import pytest
import sqlite3
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

# Adjust path to import from src
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../')))

from src.context_portal_mcp.db import database as db_module
from src.context_portal_mcp.db import models
from src.context_portal_mcp.core.exceptions import DatabaseError

# Fixture for in-memory database connection
@pytest.fixture
def memory_db():
    db_module._connections = {} # Clear any cached connections from other tests
    # Use a unique name for the in-memory database to ensure true isolation if tests run in parallel (though pytest usually serializes)
    # However, for :memory:, each connection is distinct anyway.
    conn = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    db_module.initialize_database(conn) # Initialize schema
    
    # This workspace_id will be used by tests using this fixture.
    # If a test needs a different workspace_id with the same in-memory db,
    # it would need to manipulate db_module._connections itself.
    default_workspace_id_for_fixture = "test_workspace"
    db_module._connections[default_workspace_id_for_fixture] = conn
    
    yield conn 

    conn.close()
    if default_workspace_id_for_fixture in db_module._connections:
        del db_module._connections[default_workspace_id_for_fixture]


# --- Timestamp Tests ---

def test_log_system_pattern_timestamps(memory_db):
    workspace_id = "test_workspace" # Use the one setup by memory_db fixture
    pattern_name = "TestPattern"
    
    # Initial log
    pattern_data_initial = models.SystemPattern(name=pattern_name, description="Initial version", tags=["tag1"])
    logged_pattern_initial = db_module.log_system_pattern(workspace_id, pattern_data_initial)

    assert logged_pattern_initial.id is not None
    assert logged_pattern_initial.timestamp_created is not None
    assert logged_pattern_initial.timestamp_updated is not None
    assert abs((logged_pattern_initial.timestamp_updated - logged_pattern_initial.timestamp_created).total_seconds()) < 0.1 # Should be very close

    # Simulate time passing
    time.sleep(0.02) # Increased sleep time slightly

    # Update (log again with same name)
    pattern_data_updated = models.SystemPattern(name=pattern_name, description="Updated version", tags=["tag1", "tag2"])
    logged_pattern_updated = db_module.log_system_pattern(workspace_id, pattern_data_updated)

    assert logged_pattern_updated.id == logged_pattern_initial.id
    assert logged_pattern_updated.timestamp_created == logged_pattern_initial.timestamp_created 
    assert logged_pattern_updated.timestamp_updated > logged_pattern_initial.timestamp_updated

    retrieved_patterns = db_module.get_system_patterns(workspace_id)
    assert len(retrieved_patterns) == 1
    retrieved_pattern = retrieved_patterns[0]
    assert retrieved_pattern.name == pattern_name
    assert retrieved_pattern.timestamp_created == logged_pattern_initial.timestamp_created
    assert retrieved_pattern.timestamp_updated == logged_pattern_updated.timestamp_updated


def test_log_custom_data_timestamps(memory_db):
    workspace_id = "test_workspace"
    category = "TestCategory"
    key = "TestKey"

    custom_data_initial = models.CustomData(category=category, key=key, value={"data": "initial"})
    logged_data_initial = db_module.log_custom_data(workspace_id, custom_data_initial)

    assert logged_data_initial.id is not None
    assert logged_data_initial.timestamp_created is not None
    assert logged_data_initial.timestamp_updated is not None
    assert abs((logged_data_initial.timestamp_updated - logged_data_initial.timestamp_created).total_seconds()) < 0.1

    time.sleep(0.02)

    custom_data_updated = models.CustomData(category=category, key=key, value={"data": "updated"})
    logged_data_updated = db_module.log_custom_data(workspace_id, custom_data_updated)

    assert logged_data_updated.id == logged_data_initial.id
    assert logged_data_updated.timestamp_created == logged_data_initial.timestamp_created
    assert logged_data_updated.timestamp_updated > logged_data_initial.timestamp_updated

    retrieved_data_list = db_module.get_custom_data(workspace_id, category=category, key=key)
    assert len(retrieved_data_list) == 1
    retrieved_data = retrieved_data_list[0]
    assert retrieved_data.category == category
    assert retrieved_data.key == key
    assert retrieved_data.timestamp_created == logged_data_initial.timestamp_created
    assert retrieved_data.timestamp_updated == logged_data_updated.timestamp_updated

# --- get_progress_entry_by_id Tests ---

def test_get_progress_entry_by_id_exists(memory_db):
    workspace_id = "test_workspace"
    # Timestamps are naive from utcnow by default in Pydantic model
    progress_data = models.ProgressEntry(status="TODO", description="Test task", timestamp=datetime.utcnow()) 
    logged_entry = db_module.log_progress(workspace_id, progress_data)
    assert logged_entry.id is not None
        
    retrieved_entry = db_module.get_progress_entry_by_id(workspace_id, logged_entry.id)

    assert retrieved_entry is not None
    assert retrieved_entry.id == logged_entry.id
    assert retrieved_entry.description == "Test task"
    assert retrieved_entry.status == "TODO"
    # Compare timestamps with tolerance or by converting to a common format if one is naive and other is aware
    assert abs((retrieved_entry.timestamp - logged_entry.timestamp).total_seconds()) < 0.1


def test_get_progress_entry_by_id_not_exists(memory_db):
    workspace_id = "test_workspace"
    retrieved_entry = db_module.get_progress_entry_by_id(workspace_id, 999) # Non-existent ID
    assert retrieved_entry is None

# --- get_recent_activity_summary_data Tests ---
def test_get_recent_activity_summary_data_includes_new_items(memory_db):
    workspace_id = "test_workspace"
    now = datetime.utcnow() # Use naive UTC datetime consistently
    
    # Decisions
    db_module.log_decision(workspace_id, models.Decision(summary="Recent Decision", timestamp=now - timedelta(hours=1)))
    db_module.log_decision(workspace_id, models.Decision(summary="Old Decision", timestamp=now - timedelta(hours=48)))

    # Progress Entries
    db_module.log_progress(workspace_id, models.ProgressEntry(status="DONE", description="Recent Progress", timestamp=now - timedelta(hours=2)))
    
    # System Patterns
    db_module.log_system_pattern(workspace_id, models.SystemPattern(name="RecentPattern", description="RP", timestamp_created=now - timedelta(hours=3), timestamp_updated=now - timedelta(hours=3)))
    db_module.log_system_pattern(workspace_id, models.SystemPattern(name="OldPattern", description="OP", timestamp_created=now - timedelta(hours=50), timestamp_updated=now - timedelta(hours=50)))
    time.sleep(0.01) 
    # Update "OldPattern" to make its timestamp_updated recent
    db_module.log_system_pattern(workspace_id, models.SystemPattern(name="OldPattern", description="OP Updated", timestamp_created=now - timedelta(hours=50)))


    # Custom Data
    db_module.log_custom_data(workspace_id, models.CustomData(category="TestCat", key="RecentKey", value="RV", timestamp_created=now - timedelta(hours=4), timestamp_updated=now - timedelta(hours=4)))
    db_module.log_custom_data(workspace_id, models.CustomData(category="TestCat", key="OldKey", value="OV", timestamp_created=now - timedelta(hours=52), timestamp_updated=now - timedelta(hours=52)))
    time.sleep(0.01)
    # Update "OldKey"
    db_module.log_custom_data(workspace_id, models.CustomData(category="TestCat", key="OldKey", value="OV Updated", timestamp_created=now - timedelta(hours=52)))

    # Context History (Product)
    # Need to ensure update_product_context correctly uses the mocked connection
    # The fixture memory_db should handle this if db_module._connections is correctly managed.
    db_module.update_product_context(workspace_id, models.UpdateContextArgs(content={"new_data": "initial for history"}, workspace_id=workspace_id))
    time.sleep(0.01) # Ensure timestamp difference
    db_module.update_product_context(workspace_id, models.UpdateContextArgs(content={"new_data": "recent update"}, workspace_id=workspace_id))
    
    summary = db_module.get_recent_activity_summary_data(workspace_id, hours_ago=24, limit_per_type=5)

    assert len(summary["recent_decisions"]) == 1
    assert summary["recent_decisions"][0]["summary"] == "Recent Decision"
    
    assert len(summary["recent_progress_entries"]) == 1
    assert summary["recent_progress_entries"][0]["description"] == "Recent Progress"

    assert len(summary["recent_system_patterns"]) == 2 
    pattern_names = {p["name"] for p in summary["recent_system_patterns"]}
    assert "RecentPattern" in pattern_names
    assert "OldPattern" in pattern_names # Updated "OldPattern"
    
    assert len(summary["recent_custom_data"]) == 2
    custom_keys = {cd["key"] for cd in summary["recent_custom_data"]}
    assert "RecentKey" in custom_keys
    assert "OldKey" in custom_keys # Updated "OldKey"

    assert len(summary["recent_product_context_updates"]) == 1 # Only the latest update within 24h
    assert summary["recent_product_context_updates"][0]["content"]["new_data"] == "initial for history" # History logs the *previous* state
    
    assert not any("System Patterns and general Custom Data entries are not included" in note for note in summary["notes"])


# --- SQL-based Tag Filtering Tests ---

def setup_tag_test_data_decisions(conn): # Removed workspace_id, conn is already workspace specific from fixture
    cursor = conn.cursor()
    decisions_data = [
        (datetime.utcnow(), "Decision A", json.dumps(["tag1", "tag2"])),       
        (datetime.utcnow(), "Decision B", json.dumps(["tag2", "tag3"])),       
        (datetime.utcnow(), "Decision C", json.dumps(["tag1"])),               
        (datetime.utcnow(), "Decision D", json.dumps(["tag3", "tag4"])),       
        (datetime.utcnow(), "Decision E", json.dumps(["tag1", "tag2", "tag3"])),
        (datetime.utcnow(), "Decision F", None),                             
        (datetime.utcnow(), "Decision G", json.dumps([])),                   
        (datetime.utcnow(), "Decision H", json.dumps(["tag5"])),
        (datetime.utcnow(), "Decision I", "not a valid json array"), # Invalid JSON
    ]
    cursor.executemany("INSERT INTO decisions (timestamp, summary, tags) VALUES (?, ?, ?)", decisions_data)
    conn.commit()
    # Return expected IDs (adjust if insertion order changes or IDs are not sequential starting at 1)
    return list(range(1, len(decisions_data) + 1))


def setup_tag_test_data_system_patterns(conn):
    cursor = conn.cursor()
    patterns_data = [
        ("Pattern A", json.dumps(["tag1", "tag2"]), datetime.utcnow(), datetime.utcnow()),      
        ("Pattern B", json.dumps(["tag2", "tag3"]), datetime.utcnow(), datetime.utcnow()),      
        ("Pattern C", json.dumps(["tag1"]), datetime.utcnow(), datetime.utcnow()),              
        ("Pattern D", json.dumps(["tag3", "tag4"]), datetime.utcnow(), datetime.utcnow()),      
        ("Pattern E", json.dumps(["tag1", "tag2", "tag3"]), datetime.utcnow(), datetime.utcnow()),
        ("Pattern F", None, datetime.utcnow(), datetime.utcnow()),                            
        ("Pattern G", json.dumps([]), datetime.utcnow(), datetime.utcnow()),                  
        ("Pattern H", json.dumps(["tag5"]), datetime.utcnow(), datetime.utcnow()),
        ("Pattern I", "not valid json", datetime.utcnow(), datetime.utcnow()), # Invalid JSON
    ]
    cursor.executemany("INSERT INTO system_patterns (name, tags, timestamp_created, timestamp_updated) VALUES (?, ?, ?, ?)", patterns_data)
    conn.commit()
    return list(range(1, len(patterns_data) + 1))


@pytest.mark.parametrize("filter_type, tags_to_filter, expected_indices", [
    ("any", ["tag1"], [0, 2, 4]), # Corresponds to IDs 1, 3, 5
    ("any", ["tag2", "tag4"], [0, 1, 3, 4]), # IDs 1, 2, 4, 5
    ("any", ["tag5"], [7]), # ID 8
    ("any", ["tag_nonexistent"], []),
    ("any", [], []), 
    ("any", None, [0,1,2,3,4,5,6,7,8]), # All valid items
    ("all", ["tag1", "tag2"], [0, 4]), # IDs 1, 5
    ("all", ["tag1", "tag2", "tag3"], [4]), # ID 5
    ("all", ["tag1", "tag_nonexistent"], []),
    ("all", ["tag1"], [0, 2, 4]), # IDs 1, 3, 5
    ("all", [], []), 
    ("all", None, [0,1,2,3,4,5,6,7,8]), # All valid items
])
def test_get_decisions_sql_tag_filtering(memory_db, filter_type, tags_to_filter, expected_indices):
    workspace_id = "test_workspace"
    all_ids = setup_tag_test_data_decisions(memory_db)
    # Filter out the ID of the item with invalid JSON for tag field if it affects expected results
    # The SQL json_valid() should handle it, but Python json.loads() in model creation might fail
    # For this test, we assume items with invalid JSON in `tags` are not returned or processed by json_each.
    # The `json_valid(decisions.tags)` in SQL query handles this.
    
    args_all = None
    args_any = None
    if filter_type == "any":
        args_any = tags_to_filter
    elif filter_type == "all":
        args_all = tags_to_filter

    decisions = db_module.get_decisions(
        workspace_id,
        tags_filter_include_any=args_any,
        tags_filter_include_all=args_all
    )
    
    retrieved_ids = sorted([d.id for d in decisions if d.id is not None])
    # Map expected_indices to actual IDs. If all_ids from setup is [1,2,3,4,5,6,7,8,9]
    # and expected_indices is [0,2,4], then expected_db_ids = [all_ids[0], all_ids[2], all_ids[4]] = [1,3,5]
    expected_db_ids = sorted([all_ids[i] for i in expected_indices if i < len(all_ids)])
    # If None filter, we expect all items with valid (or null/empty list) tags.
    # Item with "not a valid json array" will be filtered by json_valid() in SQL.
    if tags_to_filter is None:
        expected_db_ids = sorted([id_ for id_ in all_ids if id_ != all_ids[8]]) # Exclude item with invalid JSON

    assert retrieved_ids == expected_db_ids


@pytest.mark.parametrize("filter_type, tags_to_filter, expected_indices", [
    ("any", ["tag1"], [0, 2, 4]),
    ("any", ["tag2", "tag4"], [0, 1, 3, 4]),
    ("any", ["tag5"], [7]),
    ("any", ["tag_nonexistent"], []),
    ("any", [], []),
    ("any", None, [0,1,2,3,4,5,6,7,8]),
    ("all", ["tag1", "tag2"], [0, 4]),
    ("all", ["tag1", "tag2", "tag3"], [4]),
    ("all", ["tag1", "tag_nonexistent"], []),
    ("all", ["tag1"], [0, 2, 4]),
    ("all", [], []),
    ("all", None, [0,1,2,3,4,5,6,7,8]),
])
def test_get_system_patterns_sql_tag_filtering(memory_db, filter_type, tags_to_filter, expected_indices):
    workspace_id = "test_workspace"
    all_ids = setup_tag_test_data_system_patterns(memory_db)
        
    args_all = None
    args_any = None
    if filter_type == "any":
        args_any = tags_to_filter
    elif filter_type == "all":
        args_all = tags_to_filter

    patterns = db_module.get_system_patterns(
        workspace_id,
        tags_filter_include_any=args_any,
        tags_filter_include_all=args_all
    )
    
    retrieved_ids = sorted([p.id for p in patterns if p.id is not None])
    expected_db_ids = sorted([all_ids[i] for i in expected_indices if i < len(all_ids)])
    if tags_to_filter is None:
         expected_db_ids = sorted([id_ for id_ in all_ids if id_ != all_ids[8]]) # Exclude item with invalid JSON

    assert retrieved_ids == expected_db_ids

# Note: The memory_db fixture was updated to manage _connections more cleanly.
# Timestamps in tests are now consistently using datetime.utcnow() for naive UTC datetimes.
# Tag filtering tests adjusted expected_ids to be indices for clarity with setup data.
# Addressed potential issue with invalid JSON in tags column by relying on json_valid() in SQL
# and ensuring test expectations for `None` filter correctly exclude items that would fail `json_valid`.
# Increased sleep time slightly in timestamp tests for more reliable differentiation.
# Corrected fixture usage in timestamp tests to use the workspace_id setup by the fixture.
# Updated the `setup_tag_test_data_decisions` and `setup_tag_test_data_system_patterns` to return the list of generated IDs.
# Adjusted assertions in tag filtering tests to map indices to these actual generated IDs.
# For `None` filter (no tags specified), all items whose `tags` column passes `json_valid()` should be returned.
# This means items with `NULL`, `[]`, or valid JSON arrays of tags are returned. Items with malformed JSON text are not.
# This is correctly handled by the `if tags_to_filter is None:` block in the test assertions.
# `get_recent_activity_summary_data` product context history check was refined. History logs the *previous* state.
# This means the *second to last* update's content will appear as the content of the most recent history entry.
# The `log_progress` function in `db_module` uses `progress_data.timestamp` which is set by Pydantic's `default_factory`.
# This means when testing `get_progress_entry_by_id`, the retrieved entry's timestamp should be very close to this.
# Added `timestamp=datetime.utcnow()` to `ProgressEntry` creation in its test for clarity.Okay, I have created `tests/src/context_portal_mcp/db/test_database.py` and implemented the database tests for timestamps, `get_progress_entry_by_id`, `get_recent_activity_summary_data`, and SQL-based tag filtering.

Now, I will create `tests/src/context_portal_mcp/handlers/test_mcp_handlers.py` and implement the handler tests, starting with `handle_update_progress`.
