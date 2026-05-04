from typing import Any, Callable, Mapping

from zt_langgraph.client import ControlPlaneClient
from zt_langgraph.types import ActionDecision

State = Mapping[str, Any]
StateUpdate = dict[str, Any]
ActionCallable = Callable[[State], StateUpdate]


def create_policy_decision_node(
    client: ControlPlaneClient,
    *,
    actor_key: str = "actor",
    action_key: str = "action",
    output_key: str = "control_plane_decision",
) -> Callable[[State], StateUpdate]:
    """Return a LangGraph-compatible node that calls the zt-infra-v2 control plane.

    LangGraph nodes receive graph state and return a partial state update. This node
    reads `actor` and `action`, calls `/actions`, and writes the signed decision
    payload back to the graph state.
    """

    def policy_decision_node(state: State) -> StateUpdate:
        actor = _required_string(state, actor_key)
        action = _required_string(state, action_key)
        return {output_key: client.decide(actor=actor, action=action)}

    return policy_decision_node


def create_guarded_action_node(
    action_node: ActionCallable,
    *,
    decision_key: str = "control_plane_decision",
    skipped_key: str = "execution_skipped",
) -> Callable[[State], StateUpdate]:
    """Wrap an action node so it only runs after an explicit allow decision."""

    def guarded_action_node(state: State) -> StateUpdate:
        decision = _decision(state, decision_key)
        if decision["decision"] != "allow":
            return {skipped_key: True}
        result = action_node(state)
        result.setdefault(skipped_key, False)
        return result

    return guarded_action_node


def route_by_decision(state: State, *, decision_key: str = "control_plane_decision") -> str:
    """LangGraph conditional-edge router.

    Use with `add_conditional_edges(..., route_by_decision, {"allow": ..., "deny": ...})`.
    """

    return _decision(state, decision_key)["decision"]


def _required_string(state: State, key: str) -> str:
    value = str(state.get(key, "")).strip()
    if not value:
        raise ValueError(f"state['{key}'] is required")
    return value


def _decision(state: State, key: str) -> ActionDecision:
    decision = state.get(key)
    if not isinstance(decision, dict):
        raise ValueError(f"state['{key}'] must contain a control-plane decision")
    if decision.get("decision") not in {"allow", "deny"}:
        raise ValueError(f"state['{key}'].decision must be allow or deny")
    return decision  # type: ignore[return-value]
