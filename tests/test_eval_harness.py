"""Eval harness shape and reporting."""

from __future__ import annotations

import json
from pathlib import Path

from self_healing_coder.eval.runner import TaskResult, render_markdown, summarize, write_report


def _row(task_id: str, passed: bool, iters: int = 1, cost: float = 0.01) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        passed=passed,
        verdict="success" if passed else "give_up",
        iterations=iters,
        duration_s=0.5,
        cost_usd=cost,
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=0,
        error=None,
        stdout_excerpt="ok",
    )


def test_summarize_pass_rate_and_cost():
    rows = [_row("a", True, 1, 0.01), _row("b", False, 3, 0.05), _row("c", True, 2, 0.02)]
    s = summarize(rows)
    assert s["n"] == 3
    assert s["passed"] == 2
    assert s["pass_rate"] == round(2 / 3, 3)
    assert s["mean_iterations"] == 2.0
    assert abs(s["total_cost_usd"] - 0.08) < 1e-9


def test_render_markdown_contains_table_header():
    rows = [_row("x", True)]
    out = render_markdown(rows, summarize(rows))
    assert "# Self-Healing Coder" in out
    assert "| task |" in out
    assert "x" in out


def test_write_report_json(tmp_path: Path):
    rows = [_row("x", True), _row("y", False)]
    target = tmp_path / "out.json"
    write_report(rows, target)
    payload = json.loads(target.read_text())
    assert payload["summary"]["n"] == 2
    assert {r["task_id"] for r in payload["results"]} == {"x", "y"}
