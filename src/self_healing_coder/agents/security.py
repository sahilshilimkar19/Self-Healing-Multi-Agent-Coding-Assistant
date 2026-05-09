"""Static security scan node — runs Bandit on generated code BEFORE executing it.

Defense in depth: the sandbox already isolates execution, but a static scan
catches obvious red flags (eval/exec, raw shell calls, hard-coded secrets,
``os.system`` etc.) and either blocks or annotates the run.

We use Bandit's Python API rather than spawning a subprocess. Bandit is
listed as an optional dep; if it's not installed the node degrades to a
permissive no-op so unit tests still run.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

from ..state import AgentState, ExecutionResult


# Findings at or above this severity short-circuit execution.
_BLOCK_SEVERITY = {"HIGH"}


def _run_bandit(code: str) -> tuple[list[dict], str]:
    """Return (findings, raw_text). Empty list if Bandit isn't installed."""
    try:
        from bandit.core import config as b_config
        from bandit.core import manager as b_manager
    except Exception:
        return [], "(bandit not installed; scan skipped)"

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "snippet.py"
        path.write_text(code, encoding="utf-8")
        cfg = b_config.BanditConfig()
        mgr = b_manager.BanditManager(cfg, "file")
        mgr.discover_files([str(path)])
        mgr.run_tests()

        findings: list[dict] = []
        for issue in mgr.get_issue_list():
            findings.append(
                {
                    "severity": issue.severity,
                    "confidence": issue.confidence,
                    "test_id": issue.test_id,
                    "text": issue.text,
                    "line": issue.lineno,
                }
            )

    summary_lines = [
        f"  [{f['severity']}/{f['confidence']}] {f['test_id']} line {f['line']}: {f['text']}"
        for f in findings
    ]
    return findings, "\n".join(summary_lines) if summary_lines else "(no findings)"


def security_node(state: AgentState) -> dict:
    code = state.get("code") or ""
    if not code.strip():
        return {"history": [{"node": "security", "skipped": "no code"}]}

    findings, summary = _run_bandit(code)
    blockers = [f for f in findings if f["severity"] in _BLOCK_SEVERITY]

    history_entry = {
        "node": "security",
        "findings": len(findings),
        "blocked": len(blockers),
    }

    if blockers:
        # Short-circuit: synthesize an ExecutionResult so the Debugger sees the
        # scan failure as if it were a runtime error.
        joined = "; ".join(
            f"{f['test_id']} (line {f['line']}): {f['text']}" for f in blockers
        )
        result = ExecutionResult(
            stdout="",
            stderr=summary,
            error=f"BLOCKED by static security scan: {joined}",
            exit_code=2,
        )
        return {
            "last_result": result,
            "verdict": None,  # let the debugger decide retry vs give_up
            "history": [history_entry | {"summary": summary}],
        }

    return {"history": [history_entry]}
