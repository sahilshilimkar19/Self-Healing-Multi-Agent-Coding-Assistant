"""Token + cost telemetry callback.

Captures usage from every Anthropic LLM call into a process-local accumulator
so the CLI can render a final cost summary. Costs are estimated from a small
hard-coded price table; update when Anthropic publishes new prices.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


# USD per 1M tokens. Approximate; update from Anthropic pricing as needed.
_PRICE_TABLE_USD_PER_M = {
    "claude-opus-4-7":   {"input": 15.0, "output": 75.0, "cache_read": 1.5,  "cache_write": 18.75},
    "claude-sonnet-4-6": {"input": 3.0,  "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku-4-5":  {"input": 0.80, "output": 4.0,  "cache_read": 0.08, "cache_write": 1.0},
}


def _price_for(model: str) -> dict[str, float]:
    for key, prices in _PRICE_TABLE_USD_PER_M.items():
        if key in model:
            return prices
    return {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75}


@dataclass
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    calls: int = 0
    by_model: dict[str, int] = field(default_factory=dict)

    @property
    def cost_usd(self) -> float:
        # Assume the dominant model dictates pricing. Good enough for a summary.
        if not self.by_model:
            model = "claude-sonnet-4-6"
        else:
            model = max(self.by_model, key=lambda k: self.by_model[k])
        p = _price_for(model)
        return (
            self.input_tokens * p["input"]
            + self.output_tokens * p["output"]
            + self.cache_read_tokens * p["cache_read"]
            + self.cache_write_tokens * p["cache_write"]
        ) / 1_000_000


class CostTrackerCallback(BaseCallbackHandler):
    """LangChain callback that accumulates Anthropic usage."""

    def __init__(self) -> None:
        self.totals = UsageTotals()
        self._lock = threading.Lock()

    def on_llm_end(self, response: Any, **_: Any) -> None:  # noqa: D401
        with self._lock:
            self.totals.calls += 1
            for gen_list in getattr(response, "generations", []) or []:
                for gen in gen_list:
                    msg = getattr(gen, "message", None)
                    meta = getattr(msg, "usage_metadata", None) or getattr(msg, "response_metadata", {})
                    if not meta:
                        continue
                    self._absorb(meta)

    def _absorb(self, meta: Any) -> None:
        # Anthropic via langchain-anthropic stores usage in usage_metadata as
        # {input_tokens, output_tokens, total_tokens, input_token_details: {cache_read, cache_creation}}
        if isinstance(meta, dict):
            it = int(meta.get("input_tokens") or 0)
            ot = int(meta.get("output_tokens") or 0)
            details = meta.get("input_token_details") or {}
            cr = int(details.get("cache_read") or 0)
            cw = int(details.get("cache_creation") or 0)
            model = meta.get("model_name") or meta.get("model") or "unknown"
        else:
            it = int(getattr(meta, "input_tokens", 0) or 0)
            ot = int(getattr(meta, "output_tokens", 0) or 0)
            details = getattr(meta, "input_token_details", {}) or {}
            cr = int((details or {}).get("cache_read") or 0) if isinstance(details, dict) else 0
            cw = int((details or {}).get("cache_creation") or 0) if isinstance(details, dict) else 0
            model = getattr(meta, "model_name", None) or "unknown"

        self.totals.input_tokens += max(it - cr - cw, 0)
        self.totals.output_tokens += ot
        self.totals.cache_read_tokens += cr
        self.totals.cache_write_tokens += cw
        self.totals.by_model[model] = self.totals.by_model.get(model, 0) + 1


# Process-wide tracker; reset() between runs if reusing process.
_TRACKER: CostTrackerCallback | None = None


def get_tracker() -> CostTrackerCallback:
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = CostTrackerCallback()
    return _TRACKER


def reset_tracker() -> None:
    global _TRACKER
    _TRACKER = CostTrackerCallback()
