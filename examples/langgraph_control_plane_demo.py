"""Example LangGraph workflow guarded by the zt-infra-v2 control plane.

Install optional dependency first:

    pip install langgraph

Run against a deployed zt-provisioner reachable at localhost or through an
operator tunnel to the host:

    python examples/langgraph_control_plane_demo.py
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from zt_langgraph import (
    AgentActionState,
    ControlPlaneClient,
    create_guarded_action_node,
    create_policy_decision_node,
    route_by_decision,
)


class State(AgentActionState, TypedDict):
    pass


def dangerous_action(_state: State) -> dict:
    # This is intentionally never reached for the demo terminate action.
    return {"execution_result": "terminated"}


client = ControlPlaneClient("http://127.0.0.1:3000")
builder = StateGraph(State)
builder.add_node("policy_gate", create_policy_decision_node(client))
builder.add_node("execute", create_guarded_action_node(dangerous_action))
builder.add_edge(START, "policy_gate")
builder.add_conditional_edges("policy_gate", route_by_decision, {"allow": "execute", "deny": END})
builder.add_edge("execute", END)

graph = builder.compile()

if __name__ == "__main__":
    result = graph.invoke({"actor": "demo-agent", "action": "aws.ec2.terminate_instances"})
    print(result)
