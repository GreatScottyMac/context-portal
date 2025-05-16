# ConPort MCP Session Context and Workspace Resolution

## Overview

This document summarizes the session context management and workspace resolution mechanisms implemented in ConPort MCP. This analysis is based on examination of `src/context_portal_mcp/core/session.py`, `src/context_portal_mcp/main.py`, and the design outlined in `reference/dynamic-workspace-plan.md`.

## Session Middleware Design

ConPort uses a middleware pattern to capture HTTP request context and maintain session stickiness, particularly for workspace path resolution.

### Key Components

1. **Middleware Implementation** (`main.py`):
```python
@app.middleware("http")
async def store_request_middleware(request: Request, call_next):
    token = current_request_var.set(request)
    response = await call_next(request)
    current_request_var.reset(token)
    return response
```

2. **Session State** (`session.py`):
```python
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
        # Priority resolution logic
```

3. **Session Context Management** (`session.py`):
```python
current_request_var = contextvars.ContextVar[Optional[Request]]("current_request", default=None)
_session_contexts: Dict[str, SessionState] = {}  # Store session data by session ID
```

## Workflow Analysis

### HTTP Request Flow

1. When an HTTP request arrives at the server:
   - The `store_request_middleware` captures the `Request` object in `current_request_var`
   - The middleware passes control to the next handler, which might invoke MCP tools
   - After response generation, the middleware resets the context variable

2. When an MCP tool is invoked:
   - Tool receives an MCP Context (`ctx`) parameter
   - Tool calls `session.get_session_context(ctx)` to retrieve session-specific state
   - Internally, this function:
     - Generates a stable session ID from `ctx.session`
     - Checks if the ID exists in `_session_contexts`
     - If new session, initializes with defaults and X-Workspace-Id header from `current_request_var`
   - Tool uses `get_active_workspace()` to resolve the appropriate workspace path

### SSE Connection Behavior

For Server-Sent Events (SSE) connections:
1. Initial HTTP request establishes connection with headers including potential X-Workspace-Id
2. Middleware captures this initial request context
3. Session state is created based on this initial request
4. As long as `ctx.session` remains the same for subsequent events on this SSE connection, the same session state is used

## Workspace Resolution

Workspace path resolution follows this hierarchy:
1. HTTP Header (`X-Workspace-Id`) if present
2. Explicitly set workspace (via `set_workspace_id` tool)
3. Command-line argument (`--workspace-id`)
4. Current Working Directory

## Implementation Considerations

### Strengths
- Clean separation of concerns between request handling and workspace resolution
- Consistent session state maintained throughout a connection
- Support for multiple workspace sources with sensible priority hierarchy
- Works with both HTTP and SSE connection types

### Potential Concerns
- Session ID generation has limited entropy (memory address + small random number)
- No mechanism to clean up old sessions from `_session_contexts`
- No synchronization for the global dictionary in concurrent scenarios

## Conclusion

The middleware and session context mechanism effectively implements the design described in the dynamic workspace plan. It maintains session stickiness by associating persistent state with each session ID, and supports accessing the request context (particularly headers) when initializing new session state.

This approach enables a single ConPort server instance to handle multiple workspaces concurrently, with each client connection maintaining its own workspace context.