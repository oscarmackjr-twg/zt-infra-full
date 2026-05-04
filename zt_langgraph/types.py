from typing import Any, NotRequired, TypedDict


class KmsSignature(TypedDict, total=False):
    algorithm: str
    key_id: str
    signature: str


class AuditProof(TypedDict, total=False):
    timestamp: str
    previous_hash: str
    current_hash: str
    kms_signature: KmsSignature


class ActionDecision(TypedDict):
    ok: bool
    actor: str
    action: str
    resource: NotRequired[str]
    decision: str
    reason: str
    audit: AuditProof


class AgentActionState(TypedDict):
    actor: str
    action: str
    control_plane_decision: NotRequired[ActionDecision]
    execution_result: NotRequired[Any]
    execution_skipped: NotRequired[bool]
