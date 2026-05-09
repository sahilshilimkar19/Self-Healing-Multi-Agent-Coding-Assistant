"""State contract: required keys, reducer behavior."""

from __future__ import annotations

from langgraph.graph import StateGraph

from self_healing_coder.state import AgentState, ExecutionResult, initial_state


def test_initial_state_keys():
    s = initial_state("do a thing", max_iterations=3)
    assert s["user_request"] == "do a thing"
    assert s["iteration"] == 0
    assert s["max_iterations"] == 3
    assert s["history"] == []


def test_execution_result_defaults():
    r = ExecutionResult()
    assert r.stdout == ""
    assert r.stderr == ""
    assert r.error is None
    assert r.exit_code == 0
    assert r.duration_ms == 0


def test_history_reducer_appends():
    """The Annotated list[dict] reducer should concatenate across node updates."""

    def node_a(_: AgentState) -> dict:
        return {"history": [{"node": "a"}]}

    def node_b(_: AgentState) -> dict:
        return {"history": [{"node": "b"}]}

    g: StateGraph = StateGraph(AgentState)
    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.set_entry_point("a")
    g.add_edge("a", "b")
    compiled = g.compile()

    final = compiled.invoke({"user_request": "x", "iteration": 0, "max_iterations": 3, "history": []})
    nodes_seen = [h["node"] for h in final["history"]]
    assert nodes_seen == ["a", "b"]
