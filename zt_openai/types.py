from typing import Any, Protocol, TypedDict

from zt_langgraph.types import ActionDecision


class ToolHandler(Protocol):
    def __call__(self, arguments: dict[str, Any]) -> Any:
        ...


class ToolOutput(TypedDict):
    tool_call_id: str
    output: str


class WrappedToolResult(TypedDict):
    ok: bool
    zero_trust: ActionDecision | dict[str, Any]
    result: Any
