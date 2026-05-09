"""Shared state container for the multi-agent graph.

A single ``AgentState`` TypedDict is the only shape that flows between nodes.
Nodes return *partial* dict updates; LangGraph merges them through reducers
declared via ``Annotated`` (see ``history``).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field

Verdict = Literal["retry", "success", "give_up"]


class ExecutionResult(BaseModel):
    """Normalized result of a single sandbox run."""

    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    exit_code: int = 0
    duration_ms: int = 0


class AgentState(TypedDict, total=False):
    """The single state object shared across every node in the graph."""

    user_request: str
    spec: str
    code: str
    fix_instructions: Optional[str]
    last_result: Optional[ExecutionResult]
    iteration: int
    max_iterations: int
    verdict: Optional[Verdict]
    run_id: str
    artifacts_dir: Optional[str]
    artifacts: Annotated[list[str], operator.add]
    history: Annotated[list[dict[str, Any]], operator.add]


def initial_state(
    user_request: str,
    max_iterations: int = 3,
    run_id: Optional[str] = None,
    artifacts_dir: Optional[str] = None,
) -> AgentState:
    """Build a fresh state for a new run."""
    return {
        "user_request": user_request,
        "iteration": 0,
        "max_iterations": max_iterations,
        "run_id": run_id or "",
        "artifacts_dir": artifacts_dir,
        "artifacts": [],
        "history": [],
    }
