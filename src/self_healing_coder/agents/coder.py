"""Coder node: spec [+ fix_instructions] -> code.

- LLM call site #2 (Langfuse span via callback).
- Strict regex extractor enforces the ```python fenced-block contract.
- ``iteration`` is incremented here, never in the router.
"""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage

from .. import prompts
from ..llm import cached_system, make_llm
from ..state import AgentState


_FENCE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)


def _extract_python_block(text: str) -> str | None:
    m = _FENCE.search(text)
    return m.group(1).strip() if m else None


def coder_node(state: AgentState) -> dict:
    llm = make_llm(temperature=0.0)
    user_payload = (
        f"## Spec\n{state.get('spec', '')}\n\n"
        f"## Previous code\n```python\n{state.get('code') or '(none)'}\n```\n\n"
        f"## Fix instructions\n{state.get('fix_instructions') or '(none)'}\n\n"
        "Now output the fenced ```python block."
    )
    response = llm.invoke([cached_system(prompts.CODER), HumanMessage(content=user_payload)])
    raw = response.content if isinstance(response.content, str) else str(response.content)
    code = _extract_python_block(raw)
    next_iter = state.get("iteration", 0) + 1

    if code is None:
        return {
            "iteration": next_iter,
            "fix_instructions": (
                "Output a SINGLE fenced ```python ... ``` block. "
                "The previous response had no parseable Python block."
            ),
            "history": [{"node": "coder", "iteration": next_iter, "parse_failed": True}],
        }

    return {
        "code": code,
        "iteration": next_iter,
        # Clear stale fix instructions once they've been incorporated.
        "fix_instructions": None,
        "history": [{"node": "coder", "iteration": next_iter, "code_chars": len(code)}],
    }
