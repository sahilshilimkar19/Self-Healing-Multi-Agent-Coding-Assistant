"""FastAPI server exposing the graph over HTTP + Server-Sent Events.

Endpoints:
- ``POST /run``           — synchronous run; returns final state JSON.
- ``POST /run/stream``    — SSE stream of node updates as they happen.
- ``GET  /health``        — liveness check.
- ``GET  /graph/mermaid`` — Mermaid diagram of the compiled graph.

Run with::

    uvicorn self_healing_coder.server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from .graph.builder import build_graph, render_mermaid
from .observability import get_callbacks
from .state import ExecutionResult, initial_state
from .telemetry import get_tracker, reset_tracker

app = FastAPI(title="self-healing-coder", version="0.1.0")


class RunRequest(BaseModel):
    request: str = Field(..., description="Natural-language coding task.")
    max_iterations: int = Field(3, ge=1, le=10)
    artifacts_dir: str | None = None


def _sanitize(state: dict[str, Any]) -> dict[str, Any]:
    """Make a state patch JSON-serializable for SSE."""
    out: dict[str, Any] = {}
    for k, v in state.items():
        if isinstance(v, ExecutionResult):
            out[k] = v.model_dump()
        elif hasattr(v, "model_dump"):
            out[k] = v.model_dump()
        else:
            out[k] = v
    return out


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/graph/mermaid", response_class=PlainTextResponse)
def graph_mermaid() -> str:
    return render_mermaid()


@app.post("/run")
def run(req: RunRequest) -> JSONResponse:
    reset_tracker()
    graph = build_graph()
    state = initial_state(req.request, max_iterations=req.max_iterations, artifacts_dir=req.artifacts_dir)
    config = {
        "configurable": {"thread_id": str(uuid.uuid4())},
        "callbacks": get_callbacks(),
        "recursion_limit": 50,
    }
    final = graph.invoke(state, config=config)
    payload = _sanitize(dict(final))
    payload["cost"] = {
        "usd": round(get_tracker().totals.cost_usd, 5),
        "input_tokens": get_tracker().totals.input_tokens,
        "output_tokens": get_tracker().totals.output_tokens,
        "cache_read_tokens": get_tracker().totals.cache_read_tokens,
        "calls": get_tracker().totals.calls,
    }
    return JSONResponse(payload)


@app.post("/run/stream")
async def run_stream(req: RunRequest) -> StreamingResponse:
    reset_tracker()
    graph = build_graph()
    state = initial_state(req.request, max_iterations=req.max_iterations, artifacts_dir=req.artifacts_dir)
    config = {
        "configurable": {"thread_id": str(uuid.uuid4())},
        "callbacks": get_callbacks(),
        "recursion_limit": 50,
    }

    async def event_source():
        loop = asyncio.get_running_loop()
        # graph.stream is sync; iterate it in a thread to avoid blocking the event loop.
        queue: asyncio.Queue = asyncio.Queue()
        DONE = object()

        def producer():
            try:
                for chunk in graph.stream(state, config=config, stream_mode="updates"):
                    asyncio.run_coroutine_threadsafe(queue.put(chunk), loop).result()
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(DONE), loop).result()

        loop.run_in_executor(None, producer)

        while True:
            chunk = await queue.get()
            if chunk is DONE:
                break
            for node, patch in chunk.items():
                payload = {"node": node, "patch": _sanitize(patch)}
                yield f"event: update\ndata: {json.dumps(payload, default=str)}\n\n"

        totals = get_tracker().totals
        final_payload = {
            "cost_usd": round(totals.cost_usd, 5),
            "input_tokens": totals.input_tokens,
            "output_tokens": totals.output_tokens,
            "cache_read_tokens": totals.cache_read_tokens,
            "calls": totals.calls,
        }
        yield f"event: done\ndata: {json.dumps(final_payload)}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
