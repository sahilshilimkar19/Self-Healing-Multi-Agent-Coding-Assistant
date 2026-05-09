"""LLM model factory.

The provider is intentionally swappable: every node calls ``make_llm`` and
receives a LangChain ``BaseChatModel``. To switch providers, replace the body
of ``make_llm`` — no node code needs to change.

Prompt caching: ``cached_system(text)`` builds a SystemMessage whose content
carries ``cache_control={"type": "ephemeral"}``. Anthropic then writes the
prompt to its 5-minute cache on the first call and reads it on subsequent
calls at ~10% of the input price.
"""

from __future__ import annotations

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage

from .config import get_settings
from .observability import get_callbacks


def make_llm(temperature: float = 0.0, max_tokens: int = 4096) -> ChatAnthropic:
    settings = get_settings()
    return ChatAnthropic(
        model=settings.model_name,  # type: ignore[call-arg]
        api_key=settings.anthropic_api_key.get_secret_value(),  # type: ignore[arg-type]
        temperature=temperature,
        max_tokens=max_tokens,
        callbacks=get_callbacks(),
    )


def cached_system(text: str) -> SystemMessage:
    """Build a SystemMessage with Anthropic ephemeral prompt caching enabled."""
    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    return SystemMessage(content=blocks)
