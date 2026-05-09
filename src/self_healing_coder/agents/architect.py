"""Architect node: user_request -> spec.

LLM call site #1 — Langfuse span emitted via the callback attached at
``make_llm`` and at graph compile time.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from .. import prompts
from ..llm import cached_system, make_llm
from ..state import AgentState


def architect_node(state: AgentState) -> dict:
    llm = make_llm(temperature=0.1)
    messages = [
        cached_system(prompts.ARCHITECT),
        HumanMessage(content=state["user_request"]),
    ]
    response = llm.invoke(messages)
    spec = response.content if isinstance(response.content, str) else str(response.content)
    return {
        "spec": spec,
        "history": [{"node": "architect", "spec_chars": len(spec)}],
    }
