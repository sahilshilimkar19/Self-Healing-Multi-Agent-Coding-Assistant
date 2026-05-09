"""Debugger node: (code, run result) -> verdict + fix_instructions.

LLM call site #3 — uses ``with_structured_output`` so the verdict is a strict
Literal. The router on the next edge inspects ``state['verdict']`` only.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from .. import prompts
from ..llm import cached_system, make_llm
from ..state import AgentState, ExecutionResult


class DebugVerdict(BaseModel):
    """Structured output schema for the Debugger LLM."""

    verdict: Literal["retry", "success", "give_up"] = Field(
        description="Strict outcome label consumed by the graph router."
    )
    reason: str = Field(description="One-sentence justification for the verdict.")
    fix_instructions: str | None = Field(
        default=None,
        description="Concrete bullet-list fix guidance. Required when verdict == 'retry'.",
    )


def debugger_node(state: AgentState) -> dict:
    last: ExecutionResult | None = state.get("last_result")
    if last is None:
        last = ExecutionResult(error="no execution result present", exit_code=1)

    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 3)

    llm = make_llm(temperature=0.0).with_structured_output(DebugVerdict)
    user_payload = (
        f"Iteration {iteration} of {max_iter}.\n\n"
        f"## Code\n```python\n{state.get('code', '')}\n```\n\n"
        f"## stdout\n```\n{last.stdout or ''}\n```\n\n"
        f"## stderr\n```\n{last.stderr or ''}\n```\n\n"
        f"## error\n```\n{last.error or ''}\n```\n"
    )
    verdict: DebugVerdict = llm.invoke(  # type: ignore[assignment]
        [cached_system(prompts.DEBUGGER), HumanMessage(content=user_payload)]
    )

    # Hard cap: never let the LLM extend past the iteration budget.
    if verdict.verdict == "retry" and iteration >= max_iter:
        verdict = DebugVerdict(
            verdict="give_up",
            reason=f"iteration cap reached ({iteration}/{max_iter})",
            fix_instructions=None,
        )

    return {
        "verdict": verdict.verdict,
        "fix_instructions": verdict.fix_instructions if verdict.verdict == "retry" else None,
        "history": [
            {
                "node": "debugger",
                "iteration": iteration,
                "verdict": verdict.verdict,
                "reason": verdict.reason,
            }
        ],
    }
