"""Shared pytest fixtures.

We populate dummy env vars for ``Settings`` so importing modules that depend
on it works without a real ``.env`` file. Real keys override these via the
host environment.
"""

from __future__ import annotations

import os

# Provide dummy values so ``Settings()`` instantiation doesn't fail in CI.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic")
os.environ.setdefault("E2B_API_KEY", "test-e2b")
# Langfuse keys are optional; leave unset so tests don't try to hit Langfuse.

# Reset the cached settings so the env-var injection above is honored.
from self_healing_coder.config import get_settings  # noqa: E402

get_settings.cache_clear()
