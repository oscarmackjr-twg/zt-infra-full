import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from zt_langgraph.types import ActionDecision


class ControlPlaneError(RuntimeError):
    """Raised when the zt-infra-v2 control plane cannot return a decision."""


Transport = Callable[[Request, float], Any]


@dataclass(frozen=True)
class ControlPlaneClient:
    """Small stdlib HTTP client for the zt-provisioner `/actions` API."""

    base_url: str = "http://127.0.0.1:3000"
    timeout_seconds: float = 5.0
    transport: Transport = urlopen

    def decide(self, actor: str, action: str, resource: str | None = None) -> ActionDecision:
        body = {"actor": actor, "action": action}
        if resource:
            body["resource"] = resource
        payload = json.dumps(body).encode("utf-8")
        request = Request(
            f"{self.base_url.rstrip('/')}/actions",
            data=payload,
            headers={"content-type": "application/json", "accept": "application/json"},
            method="POST",
        )

        try:
            response = self.transport(request, self.timeout_seconds)
            raw = response.read().decode("utf-8")
        except HTTPError as error:
            # The control plane intentionally returns 403 for denied actions.
            if error.code == 403:
                raw = error.read().decode("utf-8")
            else:
                raise ControlPlaneError(f"control plane HTTP error {error.code}: {error.reason}") from error
        except URLError as error:
            raise ControlPlaneError(f"control plane unavailable: {error.reason}") from error

        try:
            decision = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ControlPlaneError("control plane returned non-JSON response") from error

        self._validate_decision(decision)
        return decision

    @staticmethod
    def _validate_decision(decision: dict[str, Any]) -> None:
        missing = [key for key in ("actor", "action", "decision", "reason", "audit") if key not in decision]
        if missing:
            raise ControlPlaneError(f"control plane response missing keys: {', '.join(missing)}")
        if decision["decision"] not in {"allow", "deny"}:
            raise ControlPlaneError(f"unsupported control plane decision: {decision['decision']}")
