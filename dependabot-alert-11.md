Model Context Protocol (MCP) Python SDK does not enable DNS rebinding protection by default #11
 Open Opened 13 hours ago on mcp (pip) · requirements.txt
Dependabot cannot update to the required version
One or more other dependencies require a version that is incompatible with this update.

Transitive dependency mcp 1.22.0 is introduced via
context-portal-mcp 0.3.9  mcp 1.22.0
context-portal-mcp 0.3.9  ...  mcp 1.22.0
fastmcp 2.13.3  mcp 1.22.0
Package
Affected versions
Patched version
mcp
(pip)
< 1.23.0
1.23.0
Description
The Model Context Protocol (MCP) Python SDK does not enable DNS rebinding protection by default for HTTP-based servers. When an HTTP-based MCP server is run on localhost without authentication using FastMCP with streamable HTTP or SSE transport, and has not configured TransportSecuritySettings, a malicious website could exploit DNS rebinding to bypass same-origin policy restrictions and send requests to the local MCP server. This could allow an attacker to invoke tools or access resources exposed by the MCP server on behalf of the user in those limited circumstances.

Note that running HTTP-based MCP servers locally without authentication is not recommended per MCP security best practices. This issue does not affect servers using stdio transport.

Servers created via FastMCP() now have DNS rebinding protection enabled by default when the host parameter is 127.0.0.1 or localhost. Users are advised to update to version 1.23.0 to receive this automatic protection. Users with custom low-level server configurations using StreamableHTTPSessionManager or SseServerTransport directly should explicitly configure TransportSecuritySettings when running an unauthenticated server on localhost.