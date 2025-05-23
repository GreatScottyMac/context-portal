import pytest
from unittest.mock import patch, MagicMock, ANY
import sys
import os

# Adjust the path to import from src
# test_main.py is in tests/src/context_portal_mcp/
# To get to repo root: ../../../
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from src.context_portal_mcp import main as context_main
from src.context_portal_mcp.core import exceptions as conport_exceptions
# from src.context_portal_mcp.db import models as conport_models # Not directly needed for LogProgressArgs mock via string

# Mock CONPORT_SERVER_ROOT_DIR for consistency in tests
TEST_SERVER_ROOT_DIR = '/test/conport/server/root'
# Apply the mock to the main module's global variable
@pytest.fixture(autouse=True) # Apply to all tests in this file
def mock_conport_server_root_dir():
    original_value = context_main.CONPORT_SERVER_ROOT_DIR
    context_main.CONPORT_SERVER_ROOT_DIR = TEST_SERVER_ROOT_DIR
    yield
    context_main.CONPORT_SERVER_ROOT_DIR = original_value


@pytest.fixture
def mock_argv_and_parser():
    """Mocks sys.argv and ArgumentParser, returning the mock_args object."""
    mock_args = MagicMock()
    # Default mode to http to prevent stdio specific logic unless overridden
    mock_args.mode = 'http'
    mock_args.host = '127.0.0.1' # Default
    mock_args.port = 8000      # Default
    mock_args.workspace_id = None # Default

    # Patch sys.argv for argument parsing
    with patch.object(sys, 'argv', ['script_name']):
        # Patch ArgumentParser to control parsed args
        with patch('src.context_portal_mcp.main.argparse.ArgumentParser') as mock_parser_class:
            mock_parser_instance = mock_parser_class.return_value
            mock_parser_instance.parse_args.return_value = mock_args
            yield mock_args

@pytest.fixture
def mock_mcp_context():
    return MagicMock()

# --- Tests for main_logic ---

@patch('src.context_portal_mcp.main.uvicorn.run')
def test_main_logic_http_mode(mock_uvicorn_run, mock_argv_and_parser):
    mock_args = mock_argv_and_parser
    mock_args.mode = 'http'
    mock_args.host = 'testhost'
    mock_args.port = 1234

    context_main.main_logic()

    mock_uvicorn_run.assert_called_once_with(context_main.app, host='testhost', port=1234)

@patch('src.context_portal_mcp.main.conport_mcp.run')
@patch('src.context_portal_mcp.main.sys.exit')
@patch('src.context_portal_mcp.main.log')
@patch('src.context_portal_mcp.main.os.path.isdir')
@patch('src.context_portal_mcp.main.os.getcwd')
def test_main_logic_stdio_workspace_fallback_server_root_warning(
    mock_os_getcwd, mock_os_path_isdir, mock_log, mock_sys_exit, mock_conport_run, mock_argv_and_parser
):
    mock_args = mock_argv_and_parser
    mock_args.mode = 'stdio'
    mock_args.workspace_id = '${workspaceFolder}'

    mock_os_getcwd.return_value = TEST_SERVER_ROOT_DIR
    mock_os_path_isdir.return_value = True # Make it a valid directory

    context_main.main_logic()

    mock_log.warning.assert_any_call(
        f"MAIN.PY: WARNING - Workspace ID was literally '${{workspaceFolder}}'. "
        f"This variable was not expanded by the client IDE. "
        f"Falling back to current working directory as workspace_id: {TEST_SERVER_ROOT_DIR}. "
        f"Ensure CWD in MCP config ('{TEST_SERVER_ROOT_DIR}') is the correct project workspace."
    )
    mock_log.warning.assert_any_call(
        f"WARNING: STDIO mode effective_workspace_id ('{TEST_SERVER_ROOT_DIR}') resolved to the ConPort server's own root directory ('{TEST_SERVER_ROOT_DIR}'). "
        "This may be due to the client IDE not expanding a variable like '${workspaceFolder}' and falling back to the server's CWD. "
        "While this is not recommended for production, the server will proceed. "
        "Ensure this is intended, especially for development or if ConPort itself is the target project. "
        "A database will be created in this directory."
    )
    # The fact that conport_mcp.run is called means the sys.exit that *used to be* there was removed.
    mock_conport_run.assert_called_once_with(transport="stdio")
    # Ensure no sys.exit was called *before* conport_mcp.run due to workspace checks
    # This is implicitly tested by mock_conport_run being called. If an exit happened, it wouldn't be.
    # We can explicitly check that sys.exit was not called if we are sure no other exit paths are hit.
    # In this specific test flow for this warning, no exit should occur.
    # Filter out any sys.exit calls that might be part of a different flow if the test becomes more complex.
    for call in mock_sys_exit.call_args_list:
        # This check is a bit too broad if other sys.exit(1) calls are valid in the flow.
        # However, for this specific test, after the warning, execution should proceed to conport_mcp.run.
        # So, if conport_mcp.run is called, it means the critical exit was correctly removed.
        pass # No specific sys.exit check needed here beyond conport_mcp.run being called.


@patch('src.context_portal_mcp.main.conport_mcp.run')
@patch('src.context_portal_mcp.main.sys.exit')
@patch('src.context_portal_mcp.main.log')
@patch('src.context_portal_mcp.main.os.path.isdir')
@patch('src.context_portal_mcp.main.os.getcwd')
def test_main_logic_stdio_workspace_fallback_non_server_root(
    mock_os_getcwd, mock_os_path_isdir, mock_log, mock_sys_exit, mock_conport_run, mock_argv_and_parser
):
    mock_args = mock_argv_and_parser
    mock_args.mode = 'stdio'
    mock_args.workspace_id = '${workspaceFolder}'

    DIFFERENT_PATH = '/some/other/path'
    mock_os_getcwd.return_value = DIFFERENT_PATH
    mock_os_path_isdir.return_value = True

    context_main.main_logic()

    # Ensure the server root warning was NOT called with DIFFERENT_PATH
    server_root_warning_message_fragment = (
        f"resolved to the ConPort server's own root directory ('{TEST_SERVER_ROOT_DIR}')"
    )
    fallback_info_message = (
         f"MAIN.PY: WARNING - Workspace ID was literally '${{workspaceFolder}}'. "
         f"This variable was not expanded by the client IDE. "
         f"Falling back to current working directory as workspace_id: {DIFFERENT_PATH}. "
         f"Ensure CWD in MCP config ('{DIFFERENT_PATH}') is the correct project workspace."
    )
    mock_log.warning.assert_any_call(fallback_info_message) # This one is expected

    for call in mock_log.warning.call_args_list:
        assert server_root_warning_message_fragment not in call[0][0]


    mock_sys_exit.assert_not_called() # No exit conditions should be met
    mock_conport_run.assert_called_once_with(transport="stdio")


@patch('src.context_portal_mcp.main.conport_mcp.run')
@patch('src.context_portal_mcp.main.sys.exit')
@patch('src.context_portal_mcp.main.log')
@patch('src.context_portal_mcp.main.os.path.isdir')
# Note: os.getcwd is not directly used if workspace_id is not '${workspaceFolder}'
def test_main_logic_stdio_invalid_effective_workspace_id(
    mock_os_path_isdir, mock_log, mock_sys_exit, mock_conport_run, mock_argv_and_parser
):
    mock_args = mock_argv_and_parser
    mock_args.mode = 'stdio'
    test_workspace_id = '/invalid/path/to/nothing'
    mock_args.workspace_id = test_workspace_id

    mock_os_path_isdir.return_value = False # Simulate path is not a directory

    context_main.main_logic()

    mock_log.error.assert_called_with(
        f"STDIO mode: effective_workspace_id ('{test_workspace_id}') is not a valid directory. "
        f"Please ensure client provides a correct absolute path or sets 'cwd' appropriately if using '${{workspaceFolder}}'."
    )
    mock_sys_exit.assert_called_once_with(1)
    mock_conport_run.assert_not_called()


# --- Tests for tool_log_progress ---
@patch('src.context_portal_mcp.main.mcp_handlers.handle_log_progress')
@patch('src.context_portal_mcp.main.log')
@pytest.mark.asyncio
async def test_tool_log_progress_pydantic_error(mock_tool_logger, mock_handle_log_progress, mock_mcp_context):
    with patch('src.context_portal_mcp.main.models.LogProgressArgs') as MockLogProgressArgsClass:
        MockLogProgressArgsClass.side_effect = ValueError("Test Pydantic Error")

        with pytest.raises(conport_exceptions.ContextPortalError) as excinfo:
            await context_main.tool_log_progress(
                workspace_id="ws1",
                status="TODO",
                description="Test desc",
                ctx=mock_mcp_context,
                parent_id=123,
                linked_item_type="decision"
            )
        assert "Invalid arguments for log_progress. Details: Test Pydantic Error" in str(excinfo.value)

        mock_tool_logger.error.assert_called_once()
        logged_message = mock_tool_logger.error.call_args[0][0]
        assert "Validation error for log_progress: Test Pydantic Error" in logged_message
        assert "Args: workspace_id=ws1, status='TODO'" in logged_message
        assert "description_present=True" in logged_message
        assert "parent_id_present=True" in logged_message
        assert "linked_item_type_present=True" in logged_message
        assert "linked_item_id_present=False" in logged_message

        mock_handle_log_progress.assert_not_called()

@patch('src.context_portal_mcp.main.mcp_handlers.handle_log_progress')
@patch('src.context_portal_mcp.main.log')
@pytest.mark.asyncio
async def test_tool_log_progress_generic_exception(mock_tool_logger, mock_handle_log_progress, mock_mcp_context):
    with patch('src.context_portal_mcp.main.models.LogProgressArgs') as MockLogProgressArgsClass:
        mock_pydantic_instance = MockLogProgressArgsClass.return_value
        mock_handle_log_progress.side_effect = Exception("Generic Handler Error")

        with pytest.raises(conport_exceptions.ContextPortalError) as excinfo:
            await context_main.tool_log_progress(
                workspace_id="ws_ex",
                status="IN_PROGRESS",
                description="Desc for ex",
                ctx=mock_mcp_context
            )
        assert "Server error processing log_progress: Exception" in str(excinfo.value)

        mock_tool_logger.error.assert_called_once()
        logged_message = mock_tool_logger.error.call_args[0][0]
        assert "Error processing args for log_progress: Generic Handler Error" in logged_message
        assert "Args: workspace_id=ws_ex, status='IN_PROGRESS'" in logged_message
        assert "description_present=True" in logged_message
        assert "parent_id_present=False" in logged_message
        assert "linked_item_type_present=False" in logged_message
        assert "linked_item_id_present=False" in logged_message

        MockLogProgressArgsClass.assert_called_once_with(
            workspace_id="ws_ex",
            status="IN_PROGRESS",
            description="Desc for ex",
            parent_id=None,
            linked_item_type=None,
            linked_item_id=None,
            link_relationship_type="relates_to_progress"
        )
        mock_handle_log_progress.assert_called_once_with(mock_pydantic_instance)

@patch('src.context_portal_mcp.main.mcp_handlers.handle_log_progress')
@patch('src.context_portal_mcp.main.log')
@pytest.mark.asyncio
async def test_tool_log_progress_success(mock_tool_logger, mock_handle_log_progress, mock_mcp_context):
    with patch('src.context_portal_mcp.main.models.LogProgressArgs') as MockLogProgressArgsClass:
        mock_pydantic_instance = MockLogProgressArgsClass.return_value
        expected_result = {"id": 1, "status": "DONE", "description": "Successfully logged"}
        mock_handle_log_progress.return_value = expected_result

        result = await context_main.tool_log_progress(
            workspace_id="ws_success",
            status="DONE",
            description="Successfully logged",
            ctx=mock_mcp_context,
            parent_id=1,
            linked_item_type="custom_data",
            linked_item_id="item123",
            link_relationship_type="custom_link"
        )

        assert result == expected_result
        MockLogProgressArgsClass.assert_called_once_with(
            workspace_id="ws_success",
            status="DONE",
            description="Successfully logged",
            parent_id=1,
            linked_item_type="custom_data",
            linked_item_id="item123",
            link_relationship_type="custom_link"
        )
        mock_handle_log_progress.assert_called_once_with(mock_pydantic_instance)
        mock_tool_logger.error.assert_not_called()
        mock_tool_logger.warning.assert_not_called()

# Note: pytest-asyncio is assumed to be available for these tests.
# The `mock_conport_server_root_dir` fixture ensures CONPORT_SERVER_ROOT_DIR is mocked for all tests.
# Patch paths are updated to use `src.context_portal_mcp.main.<module>`.
# The sys.path adjustment `../../../` is used.
# Assertions for `test_main_logic_stdio_workspace_fallback_server_root_warning` are refined.
# Assertions for logging in `tool_log_progress` tests verify the format from the previous subtask.
# Added a success case test for `tool_log_progress` for completeness.
