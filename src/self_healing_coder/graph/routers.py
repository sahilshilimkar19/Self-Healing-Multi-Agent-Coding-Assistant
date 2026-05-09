"""Pure routing functions.

Routers MUST be pure: read state, return a routing label. No mutation, no
side effects, no state increments. The only place ``iteration`` advances is
the Coder node.
"""

from __future__ import annotations

from typing import Literal

from ..state import AgentState

RouteLabel = Literal["retry", "success", "give_up", "recovery"]

_VALID = {"retry", "success", "give_up"}


def route_after_debugger(state: AgentState) -> RouteLabel:
    """Map ``state['verdict']`` to a graph branch.

    Any unexpected / missing verdict routes to ``recovery`` rather than
    silently defaulting to a real branch.
    """
    verdict = state.get("verdict")
    if verdict in _VALID:
        return verdict  # type: ignore[return-value]
    return "recovery"


def route_after_security(state: AgentState) -> Literal["execute", "skip"]:
    """If the security scan injected a blocker into ``last_result``, skip the executor."""
    result = state.get("last_result")
    if result is not None and result.exit_code == 2 and (result.error or "").startswith("BLOCKED"):
        return "skip"
    return "execute"
