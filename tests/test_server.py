"""FastAPI server smoke test."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="fastapi extra not installed")

from fastapi.testclient import TestClient  # noqa: E402

from self_healing_coder.server import app  # noqa: E402


def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_mermaid_endpoint_returns_text():
    client = TestClient(app)
    r = client.get("/graph/mermaid")
    assert r.status_code == 200
    body = r.text
    assert "architect" in body or "%% mermaid" in body
