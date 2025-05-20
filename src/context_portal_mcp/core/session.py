import os
import pathlib
import random
import logging
import contextvars
from dataclasses import dataclass
from typing import Optional, Dict, Any
from starlette.requests import Request
from mcp.server.fastmcp import Context as MCPContext

log = logging.getLogger(__name__)

def get_session_id(ctx: MCPContext) -> str:
    """
    Get a consistent session ID from an MCP context regardless of transport.
    
    Args:
        ctx: The MCP context object
        
    Returns:
        A unique session identifier that persists for the duration of the session
    """
    if not ctx or not hasattr(ctx, 'session') or not ctx.session:
        raise ValueError("Invalid context - missing session")
        
    session = ctx.session
    
    # Check if we already assigned a session ID
    internal_attr_name = '__session_id'
    if hasattr(session, internal_attr_name):
        return getattr(session, internal_attr_name)
    
    session_id = f"s_{id(session):x}_{random.randint(0, 255):02x}"
    
    setattr(session, internal_attr_name, session_id)
        
    return session_id

@dataclass
class SessionState:
    """Per-session workspace context"""
    header_workspace_path: Optional[str] = None
    cli_workspace_path: Optional[str] = None
    explicit_workspace_path: Optional[str] = None
    
    def get_active_workspace(self) -> str:
        """
        HTTP Header > Explicitly set Workspace > CLI Arg > CWD
        """
        # 1. HTTP Header
        if self.header_workspace_path:
            return self.header_workspace_path
        # 2. Command-line argument
        if self.cli_workspace_path:
            return self.cli_workspace_path
        # 3. Explicitly set workspace path
        if self.explicit_workspace_path:
            return self.explicit_workspace_path
        # 4. CWD 
        return os.getcwd()

current_request_var = contextvars.ContextVar[Optional[Request]]("current_request", default=None)

_session_contexts: Dict[str, SessionState] = {}  # Store session data by session ID
default_context = SessionState()

def get_session_context(ctx: MCPContext) -> SessionState:
    """Get or create session context"""
    session_id = get_session_id(ctx)
    
    # Create new context if needed
    if session_id not in _session_contexts:
        header_workspace_path = None
        request = current_request_var.get()
        if (request):
            workspace_id = request.headers.get("X-Workspace-Id")
            if workspace_id:
                try:
                    workspace_path = str(pathlib.Path(workspace_id).resolve())
                    if os.path.isdir(workspace_path):
                        header_workspace_path = workspace_path
                    else:
                        log.warning(f"Invalid workspace path: {workspace_id}")
                except Exception as e:
                    log.error(f"Error processing workspace header: {e}")
        _session_contexts[session_id] = SessionState(
            cli_workspace_path=default_context.cli_workspace_path,
            header_workspace_path=header_workspace_path
            )
    
    return _session_contexts[session_id]