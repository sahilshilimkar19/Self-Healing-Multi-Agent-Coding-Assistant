"""Prompt loader — reads markdown prompts from disk once at import time."""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).parent

ARCHITECT: str = (_DIR / "architect.md").read_text(encoding="utf-8")
CODER: str = (_DIR / "coder.md").read_text(encoding="utf-8")
DEBUGGER: str = (_DIR / "debugger.md").read_text(encoding="utf-8")

__all__ = ["ARCHITECT", "CODER", "DEBUGGER"]
