# MCP Zero Trust Gateway

The MCP Zero Trust Gateway sits between an MCP client and a real MCP server:

```text
agent -> MCP client -> Zero Trust MCP Gateway -> policy decision -> real MCP tool
```

It enforces the same zt-infra-v2 control-plane contract used by the LangGraph and OpenAI wrappers.

## Why MCP

Model Context Protocol tools are model-controlled: an LLM-facing client can discover tools and invoke them based on context. The MCP tools specification also calls out trust and safety responsibilities such as access controls, confirmation for sensitive operations, timeouts, validation, and audit logging. That makes MCP the right protocol boundary for this product.

## Protocol Behavior

The gateway handles JSON-RPC 2.0 MCP messages.

- Non-tool messages such as `tools/list` are forwarded to the downstream MCP server.
- `tools/call` requests are intercepted before execution.
- Malformed `tools/call` requests return JSON-RPC `-32602` invalid-params errors.
- Denied tool calls return an MCP tool result with `isError: true`.
- Allowed tool calls are forwarded unchanged to the real MCP server.
- If the control plane is unavailable, the gateway fails closed and does not forward the call.

## Policy Mapping

By default:

```text
server_name = github
tool_name   = create_pull_request
action      = mcp.github.create_pull_request
```

Resource extraction checks common argument shapes:

```json
{"owner":"octo","repo":"repo"}
{"repository":"octo/repo"}
{"resource":"octo/repo"}
```

## Denial Shape

A denied MCP tool call returns a standard JSON-RPC result whose tool output is marked as an error:

```json
{
  "jsonrpc": "2.0",
  "id": "call-1",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"actor\":\"claude-desktop\",\"action\":\"mcp.github.create_pull_request\",\"resource\":\"octo/repo\",\"decision\":\"deny\"}"
      }
    ],
    "structuredContent": {
      "actor": "claude-desktop",
      "action": "mcp.github.create_pull_request",
      "resource": "octo/repo",
      "decision": "deny",
      "reason": "action is not in the allow list",
      "audit": {
        "previous_hash": "...",
        "current_hash": "...",
        "kms_signature": {
          "algorithm": "ECDSA_SHA_256",
          "key_id": "...",
          "signature": "..."
        }
      }
    },
    "isError": true
  }
}
```

Returning denial as a tool result lets the model see actionable feedback and self-correct, while still preventing execution.

## Minimal Usage

```python
from zt_mcp import MCPZeroTrustGateway


def downstream_mcp_server(message):
    # Send JSON-RPC message to the real MCP server over stdio, HTTP, or SSE.
    return real_mcp_transport.send(message)


gateway = MCPZeroTrustGateway(
    downstream=downstream_mcp_server,
    actor="claude-desktop",
    server_name="github",
)

response = gateway.handle_message({
    "jsonrpc": "2.0",
    "id": "call-1",
    "method": "tools/call",
    "params": {
        "name": "create_pull_request",
        "arguments": {"owner": "octo", "repo": "repo", "title": "demo"}
    }
})
```

## Security Properties

- Policy decision happens before MCP tool execution.
- Denied calls are never forwarded to the real MCP server.
- Audit evidence includes actor, action, resource, decision, reason, previous hash, current hash, and KMS signature when the control plane is available.
- Control-plane outages fail closed.
- Tool annotations from MCP servers are not trusted for policy.
- The gateway is transport-neutral; stdio, HTTP, and SSE adapters can use the same enforcement core.
