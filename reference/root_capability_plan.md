# Multi-Workspace Support Plan for ConPort

This document outlines the plan to implement multi-workspace support in the `ConPort` MCP server, properly leveraging the MCP Roots capability.

## High-Level Design

### Background and Context

**Model Context Protocol (MCP)** is a standardized protocol that enables AI models and applications to interact with external tools, data sources, and resources. The protocol defines mechanisms for declaring capabilities and exchanging structured messages between clients and servers.

**Roots Capability** is a specific MCP feature that enables clients to declare filesystem boundaries where servers can operate. This is a security-focused mechanism that provides context about which directories/files are accessible to the server.

### Design Goals and Principles

1. **Standards Compliance**: Implement proper MCP Roots capability support while maintaining backward compatibility.
2. **Flexible Context Management**: Enable the ConPort server to operate on multiple workspaces without requiring separate server instances.
3. **Intuitive Developer Experience**: Provide sensible defaults and clear error messages that guide users toward correct usage.
4. **Deployment Flexibility**: Support both HTTP and STDIO transports with appropriate configuration methods for each.
5. **Security**: Respect declared roots and validate workspace paths to prevent unauthorized filesystem access.

### Architectural Decisions

#### 1. Workspace Identification Hierarchy

We've established a clear hierarchy for determining the active workspace:

```
HTTP Header > Explicit Setting (CLI/Tool) > Single Root > CWD (STDIO mode) > Error
```

**Rationale**: This hierarchy prioritizes explicit user intent (header, CLI arg, tool call) over implicit defaults, while still providing sensible fallbacks when intention is unambiguous (single root) or when operating in a traditional command-line context (CWD in STDIO mode).

#### 2. Separation of Workspace Selection from Database Path Resolution

The design separates two concerns:
- **Workspace Selection**: Determining which workspace is active (a high-level concern)
- **Database Path Resolution**: Constructing the specific database path for a given workspace (a low-level concern)

**Rationale**: This separation allows for cleaner code, easier testing, and maintains the single responsibility principle. The `get_database_path` function remains focused solely on constructing a valid database path from a validated workspace path.

#### 3. Central Workspace State Management

The server maintains a central state for active workspace, declared roots, transport type, and server CWD.

**Rationale**: Having a central state simplifies access patterns and ensures consistency across different parts of the application. It also allows for efficient caching of workspace selection decisions.

#### 4. Validation at Boundaries

Workspace paths are validated both:
- When first received (header, CLI arg, tool call)
- When actually used in operations

**Rationale**: Early validation provides immediate feedback to users, while validation at usage time ensures continuous safety even if state changes between selection and usage.

### Trade-offs and Considerations

#### 1. CWD as Default in STDIO Mode

**Trade-off**: Using CWD as a default when in STDIO mode provides convenience but could potentially lead to unexpected behavior if users aren't aware of this default.

**Mitigation**: The server logs the active workspace path during initialization to make the behavior transparent.

#### 2. Validation Against Declared Roots

**Trade-off**: Strictly validating selected workspaces against declared roots improves security but may be restrictive in certain development scenarios.

**Mitigation**: The validation only occurs if roots are actually declared by the client. If no roots are declared, the validation is bypassed, allowing for more flexibility during development.

#### 3. Workspace State Management in Multi-User Environments

**Trade-off**: The current design uses a single global state for the active workspace, which could be problematic in HTTP mode with multiple concurrent users.

**Mitigation**: In HTTP mode, workspace selection is primarily handled through request-specific state (via the X-Workspace-Id header), mitigating the need for a global active workspace state.

### Security Considerations

1. **Path Validation**: All workspace paths are validated to ensure they exist and are directories.
2. **URI Validation**: All workspace URIs from `set_workspace_id` are validated for proper format and converted safely.
3. **Roots Compliance**: If roots are declared, the selected workspace is validated against these roots.
4. **Error Isolation**: Errors in workspace operations are handled gracefully to prevent information leakage.

## Implementation Plan

### 1. Support MCP Roots Capability

Declare support for the MCP Roots capability during server initialization. This allows clients to inform the server about available filesystem roots.

```python
# In server initialization code
mcp_server = FastMCP("ConPort", 
                     capabilities={"roots": True})  # Exact syntax may vary based on SDK
```

### 2. Workspace Selection Methods

#### A. HTTP Header: X-Workspace-Id (for HTTP transport)

When using HTTP transport, clients can set the workspace via a header. This is crucial for configuring workspace context per-session without relying on LLM behavior.

```python
# In HTTP middleware or request handler
async def http_middleware(request, call_next):
    # Extract workspace ID from header if present
    workspace_id = request.headers.get("X-Workspace-Id")
    if workspace_id:
        # Store in session or request state
        request.state.workspace_id = workspace_id
        
        # Optionally validate and convert to absolute path
        # This could also be done when the workspace is actually used
        try:
            workspace_path = str(pathlib.Path(workspace_id).resolve())
            if os.path.isdir(workspace_path):
                request.state.workspace_path = workspace_path
            else:
                # Log warning but don't fail the request
                print(f"Warning: Workspace path from header doesn't exist: {workspace_id}")
        except Exception as e:
            print(f"Error processing workspace header: {str(e)}")
    
    response = await call_next(request)
    return response

# In FastAPI ASGI application setup
app = FastAPI()
app.middleware("http")(http_middleware)
app.mount("/", mcp_server.sse_app())  # Mount MCP server as SSE app
```

#### B. Command-line Argument (for explicit initialization)

```python
# In argument parsing code
parser.add_argument("--workspace-id", help="Initial workspace path")

# During initialization
if args.workspace_id:
    workspace_path = str(pathlib.Path(args.workspace_id).resolve())
    if os.path.isdir(workspace_path):
        active_workspace_path = workspace_path
    else:
        print(f"Warning: Provided workspace path doesn't exist: {args.workspace_id}")
```

#### C. Current Working Directory (CWD) Default for STDIO Mode

When running in STDIO mode and no other workspace has been set, use the CWD as a sensible default:

```python
# In server initialization
def init_server(args, transport_type="stdio"):
    global active_workspace_path, server_cwd
    
    # First priority: explicit command line arg
    if args.workspace_id:
        workspace_path = str(pathlib.Path(args.workspace_id).resolve())
        if os.path.isdir(workspace_path):
            active_workspace_path = workspace_path
            print(f"Workspace set to command line argument: {active_workspace_path}")
            return
        else:
            print(f"Warning: Provided workspace path doesn't exist: {args.workspace_id}")
    
    # For STDIO mode, capture CWD as fallback default
    if transport_type == "stdio":
        server_cwd = str(pathlib.Path.cwd().resolve())
        print(f"Using current working directory as default workspace: {server_cwd}")
```

#### D. `set_workspace_id` Tool (for runtime changes with both transports)

```python
@mcp_server.tool()
def set_workspace_id(workspace_uri: str) -> str:
    """Set the active workspace path from a file:// URI.
    
    Args:
        workspace_uri: A file:// URI to a workspace root
    
    Returns:
        Success message or error
    """
    global active_workspace_path, declared_roots
    
    # Validate URI format
    if not workspace_uri.startswith("file://"):
        return "Error: workspace_uri must be a file:// URI"
    
    # Convert URI to path
    try:
        workspace_path = uri_to_path(workspace_uri)
    except Exception as e:
        return f"Error: Invalid URI format: {str(e)}"
    
    # Validate path exists
    if not os.path.isdir(workspace_path):
        return f"Error: Workspace path does not exist: {workspace_path}"
    
    # If roots are declared by client, validate against them
    if declared_roots:
        if not any(root["uri"] == workspace_uri for root in declared_roots):
            available = ", ".join(r.get("name", r["uri"]) for r in declared_roots)
            return f"Error: Workspace URI not in declared roots. Available: {available}"
    
    # Set as active workspace
    active_workspace_path = workspace_path
    return f"Workspace set to: {workspace_path}"
```

### 3. Simplify `get_database_path` in `config.py`

```python
def get_database_path(workspace_path: str) -> pathlib.Path:
    """Get database path for a workspace.
    
    Args:
        workspace_path: Absolute path to the workspace
        
    Returns:
        Path to the SQLite database file
        
    Raises:
        ValueError: If workspace_path is invalid
    """
    if not workspace_path:
        raise ValueError("Workspace path cannot be empty")
        
    path_obj = pathlib.Path(workspace_path)
    if not path_obj.is_dir():
        raise ValueError(f"Invalid workspace path: {workspace_path}")
        
    db_dir = path_obj / "context_portal"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "context.db"
```

### 4. Internal Workspace State Management

```python
# In main.py or a dedicated state module
import pathlib
import os
from typing import Optional

# Server state
active_workspace_path: Optional[str] = None
server_cwd: Optional[str] = None  # For STDIO default
declared_roots = []  # Will store roots declared by client
transport_type = "stdio"  # Default, can be changed to "http" during initialization

# Handler for MCP roots/list message
def handle_roots_list(roots_list):
    global declared_roots
    declared_roots = roots_list
    
    # If only one root is declared and no workspace is set yet, use it automatically
    if len(declared_roots) == 1 and not active_workspace_path:
        root_uri = declared_roots[0]["uri"]
        try:
            path = uri_to_path(root_uri)
            if os.path.isdir(path):
                global active_workspace_path
                active_workspace_path = path
        except Exception:
            pass  # Ignore automatic setting if conversion fails
```

### 5. Workspace Resolution Logic

The workspace resolution follows this hierarchy:

1. HTTP Header (`X-Workspace-Id`) if present and using HTTP transport
2. Command-line argument (`--workspace-id`) or active workspace set via `set_workspace_id` tool
3. Automatically use the single declared root if available
4. Use CWD if in STDIO mode
5. Error if multiple roots are available but none selected
6. Error if no roots are available and not in STDIO mode

```python
def get_active_workspace(request=None) -> str:
    """Get the currently active workspace path or raise an error.
    
    Args:
        request: Optional HTTP request object when using HTTP transport
        
    Returns:
        The absolute path to the active workspace
        
    Raises:
        ValueError: If no workspace is active or available
    """
    # 1. Check request state for HTTP header if request object provided
    if request and hasattr(request.state, "workspace_path"):
        return request.state.workspace_path
    
    # 2. Check globally set workspace (from CLI arg or set_workspace_id tool)
    global active_workspace_path, declared_roots, server_cwd, transport_type
    if active_workspace_path:
        return active_workspace_path
        
    # 3. If exactly one root exists and no explicit selection made
    if len(declared_roots) == 1:
        root_uri = declared_roots[0]["uri"]
        # Convert file:// URI to path
        path = uri_to_path(root_uri)
        if os.path.isdir(path):
            active_workspace_path = path
            return active_workspace_path
        else:
            raise ValueError(f"Declared root path does not exist: {path}")
    
    # 4. For STDIO mode, use CWD as fallback default
    if transport_type == "stdio" and server_cwd:
        return server_cwd
        
    # 5. Handle ambiguous case
    if len(declared_roots) > 1:
        available = ", ".join(r.get("name", r["uri"]) for r in declared_roots)
        raise ValueError(f"Multiple workspaces available. Please select one using set_workspace_id tool or X-Workspace-Id header. Available: {available}")
    
    # 6. Handle no roots case
    raise ValueError("No workspace available. Please set one using set_workspace_id tool, X-Workspace-Id header, or restart with --workspace-id")
```

### 6. Tool Implementation Pattern

All tools that require a workspace context should follow this pattern:

```python
@mcp_server.tool()
def example_workspace_tool(param: str, ctx=None) -> str:
    """Example tool that uses workspace context."""
    try:
        # Pass request to get_active_workspace if available (HTTP context)
        request = getattr(ctx, "request", None) if ctx else None
        workspace_path = get_active_workspace(request)
        
        db_path = get_database_path(workspace_path)
        # Use db_path for workspace-specific operations
        return f"Operated on workspace: {workspace_path}"
    except ValueError as e:
        return f"Error: {str(e)}"
```

## Helper Functions

```python
def uri_to_path(uri: str) -> str:
    """Convert a file:// URI to a local filesystem path."""
    if not uri.startswith("file://"):
        raise ValueError("URI must start with file://")
        
    # Handle both file:///C:/path (Windows) and file:///path (Unix)
    path = uri[7:]  # Remove 'file://'
    
    # On Windows, handle drive letters
    if os.name == 'nt' and path.startswith('/'):
        path = path[1:]  # Remove leading slash before drive letter
        
    return os.path.normpath(urllib.parse.unquote(path))
```

## Main Execution Flow for STDIO Mode

```python
def main():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", help="Initial workspace path")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio", help="Transport type")
    args = parser.parse_args()
    
    global transport_type
    transport_type = args.transport
    
    # Initialize server with appropriate transport
    init_server(args, transport_type)
    
    # Start server based on transport
    if transport_type == "stdio":
        # STDIO server
        asyncio.run(mcp_server.serve_stdio())
    else:
        # HTTP server
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
```

## Error Handling Approach

1. **Clear Guidance**: When a workspace is required but not set, provide specific error messages that guide the user to:
   - Use `set_workspace_id` if roots are available
   - Use `X-Workspace-Id` header when connecting via HTTP
   - Specify which workspaces are available if multiple roots exist
   - Restart with `--workspace-id` if needed

2. **Automatic Selection**: 
   - If only one root is declared by the client and no workspace has been explicitly set, automatically use that root as the workspace.
   - If in STDIO mode and no other workspace is set, use the Current Working Directory as a sensible default.

3. **Validation**: Always validate that:
   - Selected workspaces exist as directories
   - If roots are declared, the selected workspace is among those roots
   - URIs have the correct format and can be converted to filesystem paths

This approach provides a straightforward, predictable user experience with intelligent defaults while maintaining standards compliance and flexibility across different connection methods.