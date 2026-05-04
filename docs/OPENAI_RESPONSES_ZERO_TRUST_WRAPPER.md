# OpenAI Responses Zero Trust Wrapper

`zt_openai.responses` is the preferred OpenAI integration wrapper for this repo because OpenAI recommends the Responses API for new agentic workflows.

## Purpose

`ZeroTrustResponsesWrapper` wraps the Responses API function-calling loop:

1. Receive a Response object.
2. Inspect `response.output` for items whose `type` is `function_call`.
3. Decode the function `arguments`.
4. Map the function call to a zt-infra-v2 action string.
5. Call the local `POST /actions` policy decision API.
6. Execute the registered local tool only after an `allow` decision.
7. Append a `function_call_output` item with the same `call_id`.
8. Continue the response with `client.responses.create(...)`.

Denied calls are returned to the model as function-call outputs and local tool code is not invoked.

## Minimal Usage

```python
from openai import OpenAI

from zt_openai import ToolRegistry, ZeroTrustResponsesWrapper

client = OpenAI()
tools = ToolRegistry()


@tools.register("describe_instance")
def describe_instance(arguments):
    return {"instance_id": arguments["instance_id"], "state": "running"}


wrapper = ZeroTrustResponsesWrapper(
    openai_client=client,
    actor="demo-agent",
    tools=tools,
)

response = client.responses.create(
    model="gpt-5",
    input="Describe instance i-123 using the tool.",
    tools=[
        {
            "type": "function",
            "name": "describe_instance",
            "parameters": {
                "type": "object",
                "properties": {"instance_id": {"type": "string"}},
                "required": ["instance_id"],
            },
        }
    ],
)

next_response = wrapper.continue_response(response)
```

## Action Mapping

By default, function calls map to:

```text
openai.responses.function.<function_name>
```

For production, pass a resource-aware mapper:

```python
def action_mapper(function_name, arguments, function_call):
    if function_name == "terminate_instance":
        return "aws.ec2.terminate_instances"
    return f"openai.responses.function.{function_name}"
```

## Security Properties

- Policy enforcement happens before local function execution.
- Unregistered functions fail closed after policy evaluation.
- Malformed function arguments fail closed locally.
- Function-call outputs include the signed zero-trust decision payload.
- Reasoning and function-call items from the prior response are preserved in follow-up input.
- Tests use fake OpenAI and fake control-plane clients; no OpenAI API key is required.

## Current API Notes

OpenAI's function-calling guide says Responses API tool calls appear as `function_call` items in `response.output`, with `call_id`, `name`, and JSON-encoded `arguments`. It also notes apps should return tool results as `function_call_output` items and preserve reasoning items for reasoning models in subsequent turns.
