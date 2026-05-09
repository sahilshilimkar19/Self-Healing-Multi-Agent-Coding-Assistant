"""Typer CLI entry point.

Streams graph events with ``stream_mode="updates"`` and pretty-prints each
node's partial state update via rich. Also exposes ``eval`` and ``graph``
subcommands.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from .config import get_settings
from .eval.runner import evaluate, render_markdown, summarize, write_report
from .eval.tasks import TASKS
from .graph.builder import build_graph, render_mermaid
from .observability import get_callbacks
from .state import ExecutionResult, initial_state
from .telemetry import get_tracker, reset_tracker

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


def _render_patch(node: str, patch: dict[str, Any]) -> None:
    console.rule(f"[bold cyan]{node}[/]")
    for key, value in patch.items():
        if key == "history":
            for entry in value:
                console.print(f"[dim]history:[/] {entry}")
            continue
        if key == "code" and isinstance(value, str):
            console.print(Panel(Syntax(value, "python", line_numbers=False), title="code"))
            continue
        if key == "spec" and isinstance(value, str):
            console.print(Panel(value, title="spec", border_style="green"))
            continue
        if key == "last_result" and isinstance(value, ExecutionResult):
            console.print(
                Panel(
                    f"exit_code={value.exit_code}  duration_ms={value.duration_ms}\n"
                    f"[bold]error:[/] {value.error or '(none)'}\n"
                    f"[bold]stdout:[/]\n{value.stdout or '(empty)'}\n"
                    f"[bold]stderr:[/]\n{value.stderr or '(empty)'}",
                    title="execution result",
                    border_style="yellow" if value.error else "green",
                )
            )
            continue
        if key == "verdict":
            color = {"success": "green", "retry": "yellow", "give_up": "red"}.get(str(value), "white")
            console.print(f"[bold {color}]verdict:[/] {value}")
            continue
        if key == "artifacts" and isinstance(value, list):
            for path in value:
                console.print(f"[bold]artifact:[/] {path}")
            continue
        console.print(f"[bold]{key}:[/] {value}")


def _print_cost_summary() -> None:
    totals = get_tracker().totals
    table = Table(title="run cost", show_header=True, header_style="bold magenta")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("LLM calls", str(totals.calls))
    table.add_row("input tokens", f"{totals.input_tokens:,}")
    table.add_row("output tokens", f"{totals.output_tokens:,}")
    table.add_row("cache read tokens", f"{totals.cache_read_tokens:,}")
    table.add_row("cache write tokens", f"{totals.cache_write_tokens:,}")
    table.add_row("estimated cost (USD)", f"${totals.cost_usd:.5f}")
    console.print(table)


@app.command()
def run(
    request: str = typer.Argument(..., help="Natural-language coding request."),
    max_iter: int | None = typer.Option(None, "--max-iter", "-n", help="Override max retry iterations."),
    artifacts: str | None = typer.Option(None, "--artifacts", "-a", help="Directory to save sandbox-produced files."),
    thread_id: str | None = typer.Option(None, "--thread-id", help="Stable thread id (enables --resume)."),
    sqlite: str | None = typer.Option(None, "--sqlite", help="SQLite checkpoint file (enables resumption)."),
) -> None:
    """Run the self-healing coding loop on REQUEST."""
    reset_tracker()
    settings = get_settings()
    iters = max_iter or settings.max_iterations

    if sqlite:
        from .persistence import sqlite_checkpointer

        checkpointer = sqlite_checkpointer(sqlite)
    else:
        checkpointer = None

    graph = build_graph(checkpointer=checkpointer)
    tid = thread_id or str(uuid.uuid4())
    artifacts_dir = artifacts
    if artifacts_dir:
        Path(artifacts_dir).mkdir(parents=True, exist_ok=True)

    state = initial_state(request, max_iterations=iters, run_id=tid, artifacts_dir=artifacts_dir)
    config = {
        "configurable": {"thread_id": tid},
        "callbacks": get_callbacks(),
        "recursion_limit": 50,
    }

    console.print(
        Panel(
            f"[bold]request:[/] {request}\n"
            f"[bold]thread_id:[/] {tid}\n"
            f"[bold]max_iterations:[/] {iters}\n"
            f"[bold]artifacts_dir:[/] {artifacts_dir or '(none)'}",
            title="self-healing coder",
            border_style="cyan",
        )
    )

    started = time.monotonic()
    final_verdict: str | None = None
    for chunk in graph.stream(state, config=config, stream_mode="updates"):
        for node, patch in chunk.items():
            _render_patch(node, patch)
            if isinstance(patch, dict) and "verdict" in patch:
                final_verdict = patch["verdict"]
    elapsed = time.monotonic() - started

    console.rule("[bold]done[/]")
    _print_cost_summary()
    console.print(f"[dim]elapsed: {elapsed:.2f}s[/]")
    if final_verdict == "success":
        console.print("[bold green]final verdict: success[/]")
        raise typer.Exit(code=0)
    console.print(f"[bold red]final verdict: {final_verdict or 'unknown'}[/]")
    raise typer.Exit(code=1)


@app.command()
def resume(
    thread_id: str = typer.Argument(..., help="Thread id from a prior --sqlite run."),
    sqlite: str = typer.Option(".checkpoints.sqlite", "--sqlite", help="SQLite checkpoint file."),
) -> None:
    """Resume a previously interrupted run from its SQLite checkpoint."""
    from .persistence import sqlite_checkpointer

    reset_tracker()
    graph = build_graph(checkpointer=sqlite_checkpointer(sqlite))
    config = {"configurable": {"thread_id": thread_id}, "callbacks": get_callbacks()}

    console.print(Panel(f"[bold]resuming thread:[/] {thread_id}", border_style="cyan"))
    final_verdict: str | None = None
    for chunk in graph.stream(None, config=config, stream_mode="updates"):
        for node, patch in chunk.items():
            _render_patch(node, patch)
            if isinstance(patch, dict) and "verdict" in patch:
                final_verdict = patch["verdict"]
    console.rule("[bold]resume done[/]")
    _print_cost_summary()
    raise typer.Exit(code=0 if final_verdict == "success" else 1)


eval_app = typer.Typer(help="Run the benchmark evaluation suite.")
app.add_typer(eval_app, name="eval")


@eval_app.callback(invoke_without_command=True)
def eval_main(
    task_id: str | None = typer.Option(None, "--task", "-t", help="Run only one task by id."),
    max_iter: int = typer.Option(3, "--max-iter", "-n"),
    report: str | None = typer.Option(None, "--report", "-r", help="Output path (.md or .json)."),
) -> None:
    """Evaluate the agent against the benchmark suite."""
    selected = [t for t in TASKS if task_id is None or t.id == task_id]
    if not selected:
        console.print(f"[red]no task with id={task_id}[/]")
        raise typer.Exit(code=2)

    console.print(f"[bold]running {len(selected)} task(s)...[/]")
    results = evaluate(selected, max_iter=max_iter)
    summary = summarize(results)

    table = Table(title="eval summary", header_style="bold magenta")
    for k, v in summary.items():
        table.add_row(str(k), str(v))
    console.print(table)

    rows = Table(title="per-task", header_style="bold cyan")
    rows.add_column("task")
    rows.add_column("pass")
    rows.add_column("verdict")
    rows.add_column("iters", justify="right")
    rows.add_column("dur (s)", justify="right")
    rows.add_column("$", justify="right")
    for r in results:
        rows.add_row(
            r.task_id,
            "✅" if r.passed else "❌",
            r.verdict,
            str(r.iterations),
            f"{r.duration_s:.2f}",
            f"{r.cost_usd:.4f}",
        )
    console.print(rows)

    if report:
        path = write_report(results, report)
        console.print(f"[green]report written:[/] {path}")


graph_app = typer.Typer(help="Inspect the compiled graph.")
app.add_typer(graph_app, name="graph")


@graph_app.command("mermaid")
def graph_mermaid(
    output: str | None = typer.Option(None, "--output", "-o", help="Write to file instead of stdout."),
) -> None:
    """Print the Mermaid diagram of the compiled graph."""
    diagram = render_mermaid()
    if output:
        Path(output).write_text(diagram, encoding="utf-8")
        console.print(f"[green]wrote {output}[/]")
    else:
        console.print(diagram)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Start the FastAPI server."""
    import uvicorn

    uvicorn.run("self_healing_coder.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
