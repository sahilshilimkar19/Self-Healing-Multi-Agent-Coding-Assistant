"""Executor node: deterministic, no LLM. Runs ``state['code']`` in E2B."""

from __future__ import annotations

from ..state import AgentState, ExecutionResult
from ..tools.e2b_executor import run_in_sandbox


def executor_node(state: AgentState) -> dict:
    code = state.get("code") or ""
    if not code.strip():
        return {
            "last_result": ExecutionResult(error="no code produced by Coder", exit_code=1),
            "history": [{"node": "executor", "exit_code": 1, "error": "no code"}],
        }

    artifacts_dir = state.get("artifacts_dir")

    try:
        result, saved = run_in_sandbox(code, artifacts_dir=artifacts_dir)
    except Exception as exc:  # noqa: BLE001 — boundary translation
        result = ExecutionResult(
            error=f"sandbox invocation failed: {type(exc).__name__}: {exc}",
            exit_code=1,
        )
        saved = []

    update: dict = {
        "last_result": result,
        "history": [
            {
                "node": "executor",
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
                "error": result.error,
                "artifacts_saved": len(saved),
            }
        ],
    }
    if saved:
        update["artifacts"] = saved
    return update
