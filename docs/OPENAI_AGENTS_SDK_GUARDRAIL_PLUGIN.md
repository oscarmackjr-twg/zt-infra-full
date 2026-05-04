# OpenAI Agents SDK Guardrail Plugin

`AgentsSDKGuardrailPlugin` adapts the zt-infra-v2 control plane to OpenAI Agents SDK tool guardrails.

## Why Tool Guardrails

OpenAI Agents SDK supports input guardrails, output guardrails, and tool guardrails. Tool guardrails are the right control point for this project because they run on every custom function-tool invocation before and after execution. The SDK exposes a pre-execution tool guardrail hook with access to `ToolContext.tool_name` and raw JSON `ToolContext.tool_arguments`.

The plugin maps each tool invocation to the local `/actions` policy API before the tool executes.

```text
OpenAI Agent -> function_tool input guardrail -> /actions -> allow/deny -> tool execution
```

## Minimal Usage

```python
from agents import Agent, Runner, function_tool
from zt_openai import AgentsSDKGuardrailPlugin

zt_guardrail = AgentsSDKGuardrailPlugin(actor="demo-agent")


@function_tool(**zt_guardrail.function_tool_options())
def create_pull_request(owner: str, repo: str, title: str) -> str:
    return "created"


agent = Agent(name="Demo Agent", tools=[create_pull_request])
result = Runner.run_sync(agent, "Create a pull request")
```

## Policy Mapping

By default:

```text
tool_namespace = github
tool_name      = create_pull_request
action         = openai.agents.tool.github.create_pull_request
resource       = owner/repo
```

If no namespace is present, the action is:

```text
openai.agents.tool.<tool_name>
```

Pass a custom `action_mapper` for production mappings:

```python
def action_mapper(tool_name, arguments, data):
    if tool_name == "terminate_instance":
        return "aws.ec2.terminate_instances", arguments["instance_id"]
    return f"openai.agents.tool.{tool_name}", ""
```

## Deny Behavior

The default deny behavior is `reject_content`, which prevents tool execution and returns the policy reason to the model. Set `deny_behavior="raise_exception"` if the workflow should halt immediately on a deny decision.

Control-plane outages fail closed and return a local denial with `audit.local_guardrail_only = true`.

## SDK Compatibility

When the `agents` package is installed, `create_tool_input_guardrail()` returns a native Agents SDK `ToolInputGuardrail` using the SDK's `tool_input_guardrail` decorator and `ToolGuardrailFunctionOutput`.

When the package is not installed, it returns a local compatible guardrail object so unit tests and static checks can run without OpenAI credentials or network access.

## Security Properties

- Policy enforcement runs before custom function-tool execution.
- Denied tools are skipped by the Agents SDK guardrail behavior.
- Actor, action, resource, decision, reason, previous hash, current hash, and KMS signature are preserved in `output_info.zero_trust` when the control plane is available.
- Malformed tool arguments fail closed without contacting downstream tools.
- Built-in hosted tools and handoff calls are not covered by Agents SDK tool guardrails; wrap those boundaries separately with MCP/A2A gateways or explicit application policy.
