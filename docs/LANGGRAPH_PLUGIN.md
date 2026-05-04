# LangGraph Plugin

This repo includes a small Python plugin package, `zt_langgraph`, that lets a LangGraph workflow call the deployed zt-infra-v2 control plane before executing an agent action.

## Why This Exists

LangGraph models agent workflows as graphs with shared state, nodes that perform work, and edges that determine what runs next. The zt-infra-v2 control plane already exposes `POST /actions` for policy decisions and signed audit records. The plugin connects those two pieces:

1. A LangGraph node submits `{actor, action}` to `/actions`.
2. The signed allow/deny decision is written back into graph state.
3. Conditional edges route `allow` to execution and `deny` to termination or remediation.
4. Optional guarded action wrappers prevent accidental execution unless the decision is explicitly `allow`.

## Install

The plugin itself uses only the Python standard library. LangGraph is optional for local tests but required to run the example graph:

```bash
pip install langgraph
```

## Minimal Usage

```python
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from zt_langgraph import (
    ControlPlaneClient,
    create_guarded_action_node,
    create_policy_decision_node,
    route_by_decision,
)


class State(TypedDict):
    actor: str
    action: str
    control_plane_decision: dict
    execution_skipped: bool


def dangerous_action(state: State) -> dict:
    return {"execution_result": "would execute only if allowed"}


client = ControlPlaneClient("http://127.0.0.1:3000")

builder = StateGraph(State)
builder.add_node("policy_gate", create_policy_decision_node(client))
builder.add_node("execute", create_guarded_action_node(dangerous_action))
builder.add_edge(START, "policy_gate")
builder.add_conditional_edges(
    "policy_gate",
    route_by_decision,
    {"allow": "execute", "deny": END},
)
builder.add_edge("execute", END)

graph = builder.compile()
result = graph.invoke({
    "actor": "demo-agent",
    "action": "aws.ec2.terminate_instances",
})
```

For the current MVP policy, `aws.ec2.terminate_instances` returns `deny`, includes a KMS signature and hash-chain fields, and never reaches the guarded execution node.

## Files

- `zt_langgraph/client.py`: HTTP client for `POST /actions`.
- `zt_langgraph/nodes.py`: LangGraph-compatible node factory, guarded action wrapper, and router.
- `zt_langgraph/types.py`: typed decision/state contracts.
- `examples/langgraph_control_plane_demo.py`: runnable example when `langgraph` is installed.

## Design Notes

- The plugin does not import LangGraph at package import time, so CI and local tests do not require the optional dependency.
- Nodes follow LangGraph's standard contract: read graph state and return a partial state update.
- Denied actions are intentionally represented as graph state, making them visible to downstream nodes, traces, logs, and demo output.
- The guarded action wrapper is defense-in-depth: even if a graph edge is wired incorrectly, execution still requires `decision == "allow"`.
