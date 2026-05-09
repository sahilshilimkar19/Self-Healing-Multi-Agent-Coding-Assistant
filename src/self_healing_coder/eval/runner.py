"""Evaluation harness.

Runs the full pipeline against every task in ``TASKS`` and reports:
- pass-rate
- mean / median iterations
- mean cost (USD)
- per-task breakdown

Usage::

    self-healing-coder eval                  # run all tasks
    self-healing-coder eval --task primes_10 # one task
    self-healing-coder eval --report eval.md # write a markdown report
"""

from __future__ import annotations

import json
import statistics
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from ..graph.builder import build_graph
from ..observability import get_callbacks
from ..state import initial_state
from ..telemetry import get_tracker, reset_tracker
from .tasks import TASKS, EvalTask


@dataclass
class TaskResult:
    task_id: str
    passed: bool
    verdict: str
    iterations: int
    duration_s: float
    cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    error: str | None
    stdout_excerpt: str


def _matches(stdout: str, expected: Iterable[str]) -> bool:
    return all(token in stdout for token in expected)


def evaluate(tasks: Iterable[EvalTask] | None = None, max_iter: int = 3) -> list[TaskResult]:
    targets = list(tasks) if tasks is not None else TASKS
    results: list[TaskResult] = []
    graph = build_graph()

    for task in targets:
        reset_tracker()
        tracker = get_tracker()
        start = time.monotonic()
        config = {
            "configurable": {"thread_id": f"eval-{task.id}-{uuid.uuid4()}"},
            "callbacks": get_callbacks(),
            "recursion_limit": 50,
        }
        try:
            final = graph.invoke(initial_state(task.request, max_iterations=max_iter), config=config)
            verdict = str(final.get("verdict") or "unknown")
            stdout = (final.get("last_result").stdout if final.get("last_result") else "") or ""
            error = final.get("last_result").error if final.get("last_result") else None
            iterations = int(final.get("iteration", 0))
        except Exception as exc:  # noqa: BLE001
            verdict = "error"
            stdout = ""
            error = f"{type(exc).__name__}: {exc}"
            iterations = 0

        duration = time.monotonic() - start
        passed = verdict == "success" and _matches(stdout, task.expected)

        results.append(
            TaskResult(
                task_id=task.id,
                passed=passed,
                verdict=verdict,
                iterations=iterations,
                duration_s=round(duration, 2),
                cost_usd=round(tracker.totals.cost_usd, 5),
                input_tokens=tracker.totals.input_tokens,
                output_tokens=tracker.totals.output_tokens,
                cache_read_tokens=tracker.totals.cache_read_tokens,
                error=error,
                stdout_excerpt=stdout[:200],
            )
        )

    return results


def summarize(results: list[TaskResult]) -> dict:
    if not results:
        return {}
    passed = [r for r in results if r.passed]
    return {
        "n": len(results),
        "passed": len(passed),
        "pass_rate": round(len(passed) / len(results), 3),
        "mean_iterations": round(statistics.mean(r.iterations for r in results), 2),
        "median_iterations": int(statistics.median(r.iterations for r in results)),
        "mean_duration_s": round(statistics.mean(r.duration_s for r in results), 2),
        "total_cost_usd": round(sum(r.cost_usd for r in results), 5),
        "mean_cost_usd": round(statistics.mean(r.cost_usd for r in results), 5),
    }


def render_markdown(results: list[TaskResult], summary: dict) -> str:
    lines = [
        "# Self-Healing Coder — Evaluation Report",
        "",
        "## Summary",
        "",
        f"- Tasks: **{summary.get('n', 0)}**",
        f"- Passed: **{summary.get('passed', 0)}** "
        f"({summary.get('pass_rate', 0) * 100:.1f}%)",
        f"- Mean iterations: **{summary.get('mean_iterations', 0)}**  "
        f"(median {summary.get('median_iterations', 0)})",
        f"- Mean duration: **{summary.get('mean_duration_s', 0)}s**",
        f"- Total cost: **${summary.get('total_cost_usd', 0):.4f}**  "
        f"(mean ${summary.get('mean_cost_usd', 0):.4f}/task)",
        "",
        "## Per-task breakdown",
        "",
        "| task | passed | verdict | iters | dur (s) | cost ($) | tokens (in/out/cache) |",
        "|------|--------|---------|-------|---------|----------|-----------------------|",
    ]
    for r in results:
        check = "✅" if r.passed else "❌"
        lines.append(
            f"| {r.task_id} | {check} | {r.verdict} | {r.iterations} | "
            f"{r.duration_s} | {r.cost_usd:.4f} | "
            f"{r.input_tokens}/{r.output_tokens}/{r.cache_read_tokens} |"
        )
    return "\n".join(lines) + "\n"


def write_report(results: list[TaskResult], path: str | Path) -> Path:
    summary = summarize(results)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".json":
        out.write_text(
            json.dumps(
                {"summary": summary, "results": [asdict(r) for r in results]},
                indent=2,
            ),
            encoding="utf-8",
        )
    else:
        out.write_text(render_markdown(results, summary), encoding="utf-8")
    return out
