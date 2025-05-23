import pytest
from unittest.mock import patch, MagicMock, ANY
from datetime import datetime

# Adjust path to import from src
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../')))

from src.context_portal_mcp.handlers import mcp_handlers
from src.context_portal_mcp.db import models
from src.context_portal_mcp.core.exceptions import ContextPortalError, ToolArgumentError


# --- Tests for handle_update_progress ---

@pytest.mark.asyncio # Assuming handlers can be async if they interact with async services like embedding
async def test_handle_update_progress_success_with_vector_update():
    workspace_id = "test_ws_hup"
    progress_id_to_update = 1

    args = models.UpdateProgressArgs(
        workspace_id=workspace_id,
        progress_id=progress_id_to_update,
        status="DONE",
        description="Updated description"
    )

    # Mock for db.update_progress_entry
    with patch('src.context_portal_mcp.handlers.mcp_handlers.db.update_progress_entry') as mock_db_update:
        mock_db_update.return_value = True # Simulate successful DB update

        # Mock for db.get_progress_entry_by_id
        mock_updated_entry = models.ProgressEntry(
            id=progress_id_to_update,
            status="DONE",
            description="Updated description",
            timestamp=datetime.utcnow(), # Should be set by DB ideally, but mock it here
            parent_id=None
        )
        with patch('src.context_portal_mcp.handlers.mcp_handlers.db.get_progress_entry_by_id') as mock_db_get_by_id:
            mock_db_get_by_id.return_value = mock_updated_entry

            # Mock for embedding_service.get_embedding
            mock_vector = [0.1, 0.2, 0.3]
            with patch('src.context_portal_mcp.handlers.mcp_handlers.embedding_service.get_embedding') as mock_get_embedding:
                mock_get_embedding.return_value = mock_vector

                # Mock for vector_store_service.upsert_item_embedding
                with patch('src.context_portal_mcp.handlers.mcp_handlers.vector_store_service.upsert_item_embedding') as mock_upsert_embedding:
                    # Mock for log
                    with patch('src.context_portal_mcp.handlers.mcp_handlers.log') as mock_log:
                        
                        response = mcp_handlers.handle_update_progress(args)

                        # Assertions
                        mock_db_update.assert_called_once_with(workspace_id, args)
                        mock_db_get_by_id.assert_called_once_with(workspace_id, progress_id_to_update)
                        
                        expected_text_to_embed = f"Progress: {mock_updated_entry.status} - {mock_updated_entry.description}"
                        mock_get_embedding.assert_called_once_with(expected_text_to_embed.strip())
                        
                        expected_metadata = {
                            "conport_item_id": str(mock_updated_entry.id),
                            "conport_item_type": "progress_entry",
                            "status": mock_updated_entry.status,
                            "description_snippet": mock_updated_entry.description[:100],
                            "timestamp_created": mock_updated_entry.timestamp.isoformat(),
                            "parent_id": None # Based on mock_updated_entry
                        }
                        mock_upsert_embedding.assert_called_once_with(
                            workspace_id=workspace_id,
                            item_type="progress_entry",
                            item_id=str(mock_updated_entry.id),
                            vector=mock_vector,
                            metadata=expected_metadata
                        )
                        
                        mock_log.info.assert_any_call(f"Successfully updated embedding for progress entry ID {mock_updated_entry.id}")
                        # Ensure the old warning is NOT called
                        for call_args in mock_log.warning.call_args_list:
                            assert "Vector store update skipped for progress entry ID" not in call_args[0][0]

                        assert response["status"] == "success"
                        assert response["message"] == f"Progress entry ID {progress_id_to_update} updated successfully."

@pytest.mark.asyncio
async def test_handle_update_progress_db_update_fails_to_find():
    workspace_id = "test_ws_hup_nf"
    progress_id_to_update = 2
    args = models.UpdateProgressArgs(workspace_id=workspace_id, progress_id=progress_id_to_update, status="ARCHIVED")

    with patch('src.context_portal_mcp.handlers.mcp_handlers.db.update_progress_entry') as mock_db_update:
        mock_db_update.return_value = False # Simulate DB record not found or not updated

        with patch('src.context_portal_mcp.handlers.mcp_handlers.db.get_progress_entry_by_id') as mock_db_get_by_id:
            with patch('src.context_portal_mcp.handlers.mcp_handlers.vector_store_service.upsert_item_embedding') as mock_upsert_embedding:
                response = mcp_handlers.handle_update_progress(args)

                mock_db_update.assert_called_once_with(workspace_id, args)
                mock_db_get_by_id.assert_not_called() # Should not be called if update_progress_entry returns False
                mock_upsert_embedding.assert_not_called() # Vector store should not be updated

                assert response["status"] == "success" # Current handler returns "success" even if not found
                assert response["message"] == f"Progress entry ID {progress_id_to_update} not found for update."

@pytest.mark.asyncio
async def test_handle_update_progress_embedding_fails():
    workspace_id = "test_ws_hup_ef"
    progress_id_to_update = 3
    args = models.UpdateProgressArgs(workspace_id=workspace_id, progress_id=progress_id_to_update, description="Embedding fail test")

    mock_updated_entry = models.ProgressEntry(id=progress_id_to_update, status="TODO", description="Embedding fail test", timestamp=datetime.utcnow())

    with patch('src.context_portal_mcp.handlers.mcp_handlers.db.update_progress_entry', return_value=True):
        with patch('src.context_portal_mcp.handlers.mcp_handlers.db.get_progress_entry_by_id', return_value=mock_updated_entry):
            with patch('src.context_portal_mcp.handlers.mcp_handlers.embedding_service.get_embedding', side_effect=RuntimeError("Embedding service error")):
                with patch('src.context_portal_mcp.handlers.mcp_handlers.vector_store_service.upsert_item_embedding') as mock_upsert_embedding:
                    with patch('src.context_portal_mcp.handlers.mcp_handlers.log') as mock_log:
                        
                        response = mcp_handlers.handle_update_progress(args)

                        mock_log.error.assert_any_call(
                            f"Failed to update embedding for progress entry ID {mock_updated_entry.id}: RuntimeError('Embedding service error')", 
                            exc_info=True
                        )
                        mock_upsert_embedding.assert_not_called() # Upsert should not be called if embedding fails
                        
                        assert response["status"] == "success" # Operation is still success from DB perspective
                        assert response["message"] == f"Progress entry ID {progress_id_to_update} updated successfully."
                        # The error about embedding is logged, but does not change the success response of the main operation.

@pytest.mark.asyncio
async def test_handle_update_progress_db_get_fails_after_update():
    workspace_id = "test_ws_hup_dbgetfail"
    progress_id_to_update = 4
    args = models.UpdateProgressArgs(workspace_id=workspace_id, progress_id=progress_id_to_update, description="DB get fail test")

    with patch('src.context_portal_mcp.handlers.mcp_handlers.db.update_progress_entry', return_value=True):
        # Simulate db.get_progress_entry_by_id returning None even after update_progress_entry reported success
        with patch('src.context_portal_mcp.handlers.mcp_handlers.db.get_progress_entry_by_id', return_value=None):
            with patch('src.context_portal_mcp.handlers.mcp_handlers.embedding_service.get_embedding') as mock_get_embedding:
                 with patch('src.context_portal_mcp.handlers.mcp_handlers.log') as mock_log:
                    response = mcp_handlers.handle_update_progress(args)

                    mock_get_embedding.assert_not_called() # Should not be called if entry is None
                    mock_log.warning.assert_any_call(
                        f"Progress entry ID {args.progress_id} was reportedly updated in DB, but could not be re-fetched for embedding update."
                    )
                    assert response["status"] == "success"
                    assert response["message"] == f"Progress entry ID {progress_id_to_update} updated successfully."

# Placeholder for more handler tests if needed for other subtasks or full coverage.
# For now, focusing on the specific request for handle_update_progress.

# Ensure that ToolArgumentError and ContextPortalError are correctly raised by handlers
# (These are more general tests, not specific to recent changes but good for coverage)

@pytest.mark.asyncio
async def test_handle_get_decisions_db_error():
    workspace_id = "ws_db_error"
    args = models.GetDecisionsArgs(workspace_id=workspace_id)
    with patch('src.context_portal_mcp.handlers.mcp_handlers.db.get_decisions', side_effect=DatabaseError("Test DB Error")):
        with pytest.raises(ContextPortalError) as excinfo:
            mcp_handlers.handle_get_decisions(args)
        assert "Database error getting decisions: Test DB Error" in str(excinfo.value)

# This simple test can be a template for other handlers' error paths.
# The path adjustment in this file assumes it's at tests/src/context_portal_mcp/handlers/test_mcp_handlers.py
# `../../../../../` should correctly point to the repo root.

# The `handle_update_progress` in mcp_handlers.py uses `log.warning` and `log.info`.
# We need to patch `src.context_portal_mcp.handlers.mcp_handlers.log` for these tests.
# The `log` object is `logging.getLogger(__name__)` where `__name__` is `src.context_portal_mcp.handlers.mcp_handlers`.
# So, patching `'src.context_portal_mcp.handlers.mcp_handlers.log'` is correct.

# `datetime.utcnow()` is naive. `timestamp.isoformat()` on a naive datetime does not include 'Z' or timezone offset.
# This is fine as long as it's consistent. The metadata for vector store will have naive ISO timestamps.
# If timezone-aware datetimes were needed, `datetime.now(timezone.utc)` would be used.
# The Pydantic models use `default_factory=datetime.utcnow`, so they are naive.
# The database stores them as TEXT, and SQLite's `detect_types` converts them back to naive datetime objects.
# Consistency is key.

# The test `test_handle_update_progress_embedding_fails` has `exc_info=True` for the log.error.
# This is good practice for logging exceptions.
# The test `test_handle_update_progress_db_get_fails_after_update` checks the specific warning log.
# All looks reasonable for testing the handler logic.Okay, I have created `tests/src/context_portal_mcp/handlers/test_mcp_handlers.py` and implemented the tests for `handle_update_progress` focusing on the vector store update logic. I also added a sample error handling test for another handler.

Now, I will update `tests/src/context_portal_mcp/test_main.py` with tests for the dynamic version loading of `CONPORT_VERSION`.
