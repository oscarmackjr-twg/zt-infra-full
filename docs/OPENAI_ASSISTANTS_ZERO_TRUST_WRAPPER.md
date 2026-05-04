# OpenAI Assistants Zero Trust Wrapper

The OpenAI Assistants API is now deprecated in the official OpenAI docs and is scheduled to shut down on August 26, 2026. This wrapper exists for interoperability with existing Assistants deployments while keeping the policy boundary reusable for a future Responses API migration.

## Purpose

`zt_openai` wraps the Assistants function-calling handoff:

1. Receive a Run with `status == "requires_action"`.
2. Read `required_action.submit_tool_outputs.tool_calls`.
3. Map each function call to a control-plane action string.
4. Call the local zt-infra-v2 `POST /actions` policy decision API.
5. Execute the local tool only when the control plane returns `allow`.
6. Return a tool output payload containing the decision and audit proof.

Denied actions are never executed. Unregistered tools fail closed, even if policy allowed the action string.

## Minimal Usage

```python
from openai import OpenAI

from zt_openai import ToolRegistry, ZeroTrustAssistantsWrapper

openai_client = OpenAI()
tools = ToolRegistry()


@tools.register("describe_instance")
def describe_instance(arguments):
    return {"instance_id": arguments["instance_id"], "state": "running"}


wrapper = ZeroTrustAssistantsWrapper(
    openai_client=openai_client,
    actor="demo-agent",
    tools=tools,
)

# run is an Assistants API Run object whose status is requires_action.
wrapper.submit_tool_outputs(thread_id="thread_123", run=run)
```

## Action Mapping

By default, function calls map to:

```text
openai.assistants.function.<function_name>
```

For production, pass a stricter mapper that derives resource-specific actions from the function arguments:

```python
def action_mapper(function_name, arguments, tool_call):
    if function_name == "terminate_instance":
        return "aws.ec2.terminate_instances"
    return f"openai.assistants.function.{function_name}"
```

## Security Properties

- Policy enforcement happens before tool execution.
- Denied tool calls return a denial payload to the Assistant instead of invoking local code.
- The decision response includes the KMS-signed audit proof produced by `zt-provisioner`.
- Unknown or malformed tool calls fail closed locally.
- Tests use fake OpenAI and fake control-plane clients, so no OpenAI API key is needed for static validation.

## Current API Notes

The official Assistants docs describe function calls as Run `required_action` entries under `submit_tool_outputs.tool_calls`. The API reference also states that when a Run requires tool outputs, all outputs are submitted together to `submit_tool_outputs`.

Because OpenAI recommends new integrations use the Responses API instead of Assistants, keep new product work behind this wrapper boundary. The wrapper isolates the policy and audit contract from the OpenAI API transport, making a later Responses adapter smaller.
