"""Checkpointer factories.

Default = in-memory. ``sqlite_checkpointer(path)`` returns a SQLite-backed
saver so threads survive process restarts and can be resumed via
``self-healing-coder run --resume <thread_id>``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def sqlite_checkpointer(db_path: str | Path = ".checkpoints.sqlite") -> Any:
    """Return a SqliteSaver. Lazily imported so the dep is optional."""
    from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore[import-not-found]

    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver.from_conn_string(str(p))


def memory_checkpointer() -> Any:
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()
