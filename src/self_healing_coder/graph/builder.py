"""Assemble and compile the LangGraph state machine."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from ..agents.architect import architect_node
from ..agents.coder import coder_node
from ..agents.debugger import debugger_node
from ..agents.executor import executor_node
from ..agents.security import security_node
from ..state import AgentState
from .routers import route_after_debugger, route_after_security


def recovery_node(state: AgentState) -> dict:
    """Terminal recovery branch for unrecognized debugger verdicts."""
    return {
        "verdict": "give_up",
        "history": [
            {
                "node": "recovery",
                "reason": "router received unrecognized verdict; terminating safely",
            }
        ],
    }


def build_graph(checkpointer=None):
    """Build and compile the self-healing coder graph.

    ``checkpointer`` defaults to in-memory; pass an SQLite or Postgres saver
    to enable cross-process resumption.
    """
    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()

    g: StateGraph = StateGraph(AgentState)

    g.add_node("architect", architect_node)
    g.add_node("coder", coder_node)
    g.add_node("security", security_node)
    g.add_node("executor", executor_node)
    g.add_node("debugger", debugger_node)
    g.add_node("recovery", recovery_node)

    g.set_entry_point("architect")
    g.add_edge("architect", "coder")
    g.add_edge("coder", "security")
    g.add_conditional_edges(
        "security",
        route_after_security,
        {"execute": "executor", "skip": "debugger"},
    )
    g.add_edge("executor", "debugger")

    g.add_conditional_edges(
        "debugger",
        route_after_debugger,
        {
            "retry": "coder",
            "success": END,
            "give_up": END,
            "recovery": "recovery",
        },
    )
    g.add_edge("recovery", END)

    return g.compile(checkpointer=checkpointer)


def render_mermaid() -> str:
    """Return a Mermaid diagram of the compiled graph."""
    graph = build_graph()
    try:
        return graph.get_graph().draw_mermaid()
    except Exception as exc:  # noqa: BLE001
        return f"%% mermaid render failed: {exc}"
