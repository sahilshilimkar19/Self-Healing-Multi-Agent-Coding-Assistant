"""End-to-end happy-path test with mocked LLMs and a fake sandbox.

If ``E2B_API_KEY`` is set to something other than ``test-e2b`` we still mock
the sandbox to keep the test offline by default.
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock

import pytest


class _FakeAIMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChatLLM:
    """Minimal stand-in for ChatAnthropic supporting ``invoke`` and ``with_structured_output``."""

    def __init__(self, queue: list[Any]):
        self._queue = queue

    def invoke(self, _messages):  # noqa: D401
        if not self._queue:
            raise AssertionError("FakeChatLLM ran out of canned responses")
        return self._queue.pop(0)

    def with_structured_output(self, schema):
        # Return an object whose .invoke yields the next queued item, expected to
        # already be an instance of ``schema``.
        outer = self

        class _Bound:
            def invoke(self, _msgs):
                return outer.invoke(_msgs)

        return _Bound()


def _install_fake_sandbox(monkeypatch):
    fake_module = types.ModuleType("e2b_code_interpreter")

    class _Logs:
        stdout = ["2 3 5 7 11 13 17 19 23 29"]
        stderr: list[str] = []

    class _Execution:
        logs = _Logs()
        error = None

    class _Files:
        def list(self, _path):
            return []

        def read(self, _path, format="bytes"):
            return b""

    class _Sandbox:
        def __init__(self, *a, **kw):
            self.commands = MagicMock()
            self.files = _Files()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def run_code(self, code: str):
            return _Execution()

    fake_module.Sandbox = _Sandbox
    monkeypatch.setitem(sys.modules, "e2b_code_interpreter", fake_module)


def test_happy_path_runs_to_success(monkeypatch):
    _install_fake_sandbox(monkeypatch)

    from self_healing_coder.agents import architect as arch_mod
    from self_healing_coder.agents import coder as coder_mod
    from self_healing_coder.agents import debugger as dbg_mod
    from self_healing_coder.agents.debugger import DebugVerdict
    from self_healing_coder.graph.builder import build_graph
    from self_healing_coder.state import initial_state

    architect_llm = _FakeChatLLM([_FakeAIMessage("## Goal\nPrint 10 primes.\n## Requirements\n1. Print them.")])
    coder_llm = _FakeChatLLM(
        [
            _FakeAIMessage(
                "Sure.\n\n```python\n"
                "primes = [2,3,5,7,11,13,17,19,23,29]\n"
                "print(' '.join(str(p) for p in primes))\n"
                "```\n"
            )
        ]
    )
    debugger_llm = _FakeChatLLM(
        [DebugVerdict(verdict="success", reason="Output matches spec.", fix_instructions=None)]
    )

    monkeypatch.setattr(arch_mod, "make_llm", lambda *a, **kw: architect_llm)
    monkeypatch.setattr(coder_mod, "make_llm", lambda *a, **kw: coder_llm)
    monkeypatch.setattr(dbg_mod, "make_llm", lambda *a, **kw: debugger_llm)

    graph = build_graph()
    final = graph.invoke(
        initial_state("Print the first 10 primes.", max_iterations=3),
        config={"configurable": {"thread_id": "t1"}},
    )

    assert final["verdict"] == "success"
    assert final["iteration"] == 1
    assert "primes" in final["code"]
    nodes = [h["node"] for h in final["history"]]
    assert nodes[0] == "architect"
    assert nodes[1] == "coder"
    assert "executor" in nodes
    assert nodes[-1] == "debugger"


def test_retry_loop_terminates_at_max_iterations(monkeypatch):
    """Force every Debugger verdict to 'retry' and confirm the cap clamps to give_up."""
    _install_fake_sandbox(monkeypatch)

    from self_healing_coder.agents import architect as arch_mod
    from self_healing_coder.agents import coder as coder_mod
    from self_healing_coder.agents import debugger as dbg_mod
    from self_healing_coder.agents.debugger import DebugVerdict
    from self_healing_coder.graph.builder import build_graph
    from self_healing_coder.state import initial_state

    spec_msg = _FakeAIMessage("## Goal\nDo a thing.")
    code_msg = lambda: _FakeAIMessage("```python\nprint('x')\n```")

    architect_llm = _FakeChatLLM([spec_msg])
    coder_llm = _FakeChatLLM([code_msg() for _ in range(5)])
    debugger_llm = _FakeChatLLM(
        [
            DebugVerdict(verdict="retry", reason="not done", fix_instructions="try harder"),
            DebugVerdict(verdict="retry", reason="still not done", fix_instructions="try harder"),
            DebugVerdict(verdict="retry", reason="last try", fix_instructions="try harder"),
        ]
    )

    monkeypatch.setattr(arch_mod, "make_llm", lambda *a, **kw: architect_llm)
    monkeypatch.setattr(coder_mod, "make_llm", lambda *a, **kw: coder_llm)
    monkeypatch.setattr(dbg_mod, "make_llm", lambda *a, **kw: debugger_llm)

    graph = build_graph()
    final = graph.invoke(
        initial_state("Do a thing.", max_iterations=3),
        config={"configurable": {"thread_id": "t2"}, "recursion_limit": 50},
    )

    assert final["verdict"] == "give_up"
    assert final["iteration"] == 3


def test_parse_failure_routes_to_retry(monkeypatch):
    """Coder output without a ```python fence sets verdict=retry-style behavior via fix_instructions."""
    from self_healing_coder.agents.coder import coder_node

    class _NoFenceLLM:
        def invoke(self, _msgs):
            return _FakeAIMessage("here is some prose without a fenced block")

    from self_healing_coder.agents import coder as coder_mod

    monkeypatch.setattr(coder_mod, "make_llm", lambda *a, **kw: _NoFenceLLM())

    out = coder_node({"spec": "x", "iteration": 0, "max_iterations": 3, "user_request": "x"})
    assert "code" not in out
    assert out["iteration"] == 1
    assert "fix_instructions" in out and "fenced" in out["fix_instructions"].lower()
