"""Cost / token telemetry callback."""

from __future__ import annotations

from types import SimpleNamespace

from self_healing_coder.telemetry import CostTrackerCallback, _price_for, reset_tracker


def _fake_response(input_tokens: int, output_tokens: int, cache_read: int = 0):
    msg = SimpleNamespace(
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_token_details": {"cache_read": cache_read, "cache_creation": 0},
            "model_name": "claude-sonnet-4-6",
        }
    )
    return SimpleNamespace(generations=[[SimpleNamespace(message=msg)]])


def test_tracker_accumulates_usage():
    cb = CostTrackerCallback()
    cb.on_llm_end(_fake_response(100, 50))
    cb.on_llm_end(_fake_response(200, 75, cache_read=180))
    assert cb.totals.calls == 2
    assert cb.totals.output_tokens == 125
    assert cb.totals.cache_read_tokens == 180
    # 2nd call: 200 input - 180 cache_read => 20 fresh input tokens.
    assert cb.totals.input_tokens == 100 + 20


def test_cost_estimate_nonzero():
    cb = CostTrackerCallback()
    cb.on_llm_end(_fake_response(1_000_000, 100_000))
    cost = cb.totals.cost_usd
    p = _price_for("claude-sonnet-4-6")
    expected = (1_000_000 * p["input"] + 100_000 * p["output"]) / 1_000_000
    assert abs(cost - expected) < 1e-9


def test_reset_tracker_creates_fresh_instance():
    reset_tracker()
    from self_healing_coder.telemetry import get_tracker

    a = get_tracker()
    a.totals.calls = 5
    reset_tracker()
    b = get_tracker()
    assert b.totals.calls == 0
    assert a is not b
