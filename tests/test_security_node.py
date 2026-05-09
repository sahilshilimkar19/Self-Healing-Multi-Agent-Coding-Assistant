"""Static security scan node — Bandit-driven blocker handling."""

from __future__ import annotations

import pytest

from self_healing_coder.agents.security import security_node
from self_healing_coder.graph.routers import route_after_security


bandit = pytest.importorskip("bandit", reason="bandit not installed")


def test_security_node_blocks_eval_call():
    """eval(...) on user input is a HIGH-severity Bandit finding."""
    code = "user = input('x: ')\nresult = eval(user)\nprint(result)\n"
    out = security_node({"code": code})
    assert out.get("last_result") is not None
    assert out["last_result"].exit_code == 2
    assert "BLOCKED" in (out["last_result"].error or "")


def test_security_node_passes_clean_code():
    out = security_node({"code": "print('hello world')\n"})
    assert "last_result" not in out
    assert out["history"][0]["blocked"] == 0


def test_router_skips_executor_when_blocked():
    from self_healing_coder.state import ExecutionResult

    blocked = {"last_result": ExecutionResult(error="BLOCKED by static security scan: ...", exit_code=2)}
    assert route_after_security(blocked) == "skip"  # type: ignore[arg-type]


def test_router_executes_when_clean():
    assert route_after_security({}) == "execute"  # type: ignore[arg-type]
