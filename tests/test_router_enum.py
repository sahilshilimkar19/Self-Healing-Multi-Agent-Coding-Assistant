"""Router maps every verdict to its expected branch; unknown -> recovery."""

from __future__ import annotations

import pytest

from self_healing_coder.graph.routers import route_after_debugger


@pytest.mark.parametrize(
    "verdict,expected",
    [
        ("retry", "retry"),
        ("success", "success"),
        ("give_up", "give_up"),
        (None, "recovery"),
        ("garbage", "recovery"),
        ("", "recovery"),
    ],
)
def test_route_after_debugger(verdict, expected):
    state = {"verdict": verdict} if verdict is not None else {}
    assert route_after_debugger(state) == expected  # type: ignore[arg-type]
