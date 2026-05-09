"""Executor unit test with a mocked Sandbox.

Verifies that ``run_in_sandbox`` returns a normalized ``ExecutionResult``
without ever touching the host (no subprocess/exec).
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


def _install_fake_e2b(monkeypatch, *, stdout="hello\n", stderr="", error=None):
    """Inject a fake ``e2b_code_interpreter`` module before import."""
    fake_module = types.ModuleType("e2b_code_interpreter")

    class _FakeLogs:
        def __init__(self):
            self.stdout = [line for line in stdout.splitlines()]
            self.stderr = [line for line in stderr.splitlines()]

    class _FakeExecution:
        def __init__(self):
            self.logs = _FakeLogs()
            self.error = error

    class _FakeSandbox:
        def __init__(self, *args, **kwargs):
            self.commands = MagicMock()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def run_code(self, code: str):
            return _FakeExecution()

    fake_module.Sandbox = _FakeSandbox
    monkeypatch.setitem(sys.modules, "e2b_code_interpreter", fake_module)


def test_run_in_sandbox_happy_path(monkeypatch):
    _install_fake_e2b(monkeypatch, stdout="hi\n")
    # Re-import after patching so the lazy import inside the function picks it up.
    from self_healing_coder.tools.e2b_executor import run_in_sandbox

    result, saved = run_in_sandbox("print('hi')")
    assert result.exit_code == 0
    assert "hi" in result.stdout
    assert result.error is None
    assert saved == []


def test_run_in_sandbox_propagates_error(monkeypatch):
    fake_err = MagicMock(name="ZeroDivisionError", value="division by zero")
    _install_fake_e2b(monkeypatch, error=fake_err)
    from self_healing_coder.tools.e2b_executor import run_in_sandbox

    result, _ = run_in_sandbox("1/0")
    assert result.exit_code == 1
    assert result.error is not None
    assert "division by zero" in result.error


def test_executor_node_handles_empty_code():
    from self_healing_coder.agents.executor import executor_node

    out = executor_node({"user_request": "x", "iteration": 0, "max_iterations": 3})
    assert out["last_result"].exit_code == 1
    assert "no code produced" in (out["last_result"].error or "")


def test_extract_imports_skips_stdlib():
    from self_healing_coder.tools.e2b_executor import _extract_imports

    code = "import os\nimport requests\nfrom pandas import DataFrame\nimport json"
    deps = _extract_imports(code)
    assert "requests" in deps
    assert "pandas" in deps
    assert "os" not in deps
    assert "json" not in deps
