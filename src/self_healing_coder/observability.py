"""Langfuse v3 callback handler — a single shared instance per process.

The handler is attached at two levels:
1. ``ChatAnthropic(callbacks=[handler])`` inside ``llm.make_llm`` so every LLM
   call is captured even if invoked outside a graph.
2. ``graph.stream(..., config={"callbacks": [handler]})`` so the LangGraph
   trace becomes the parent of the LLM spans.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .config import get_settings


@lru_cache(maxsize=1)
def build_langfuse_handler() -> Any | None:
    """Return a configured Langfuse v3 LangChain callback, or ``None`` if disabled."""
    settings = get_settings()
    if not settings.langfuse_enabled:
        return None

    # Imported lazily so the package still imports if Langfuse env vars are absent.
    from langfuse import Langfuse  # type: ignore[import-not-found]
    from langfuse.langchain import CallbackHandler  # type: ignore[import-not-found]

    Langfuse(
        public_key=settings.langfuse_public_key.get_secret_value(),  # type: ignore[union-attr]
        secret_key=settings.langfuse_secret_key.get_secret_value(),  # type: ignore[union-attr]
        host=settings.langfuse_host,
    )
    return CallbackHandler()


def get_callbacks() -> list[Any]:
    """Return the callback list to attach to LLMs and graph runs."""
    from .telemetry import get_tracker

    callbacks: list[Any] = [get_tracker()]
    handler = build_langfuse_handler()
    if handler is not None:
        callbacks.append(handler)
    return callbacks
