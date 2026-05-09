"""Thin, retrying wrapper around an E2B Code Interpreter sandbox.

Generated code is **never** executed on the host. Every call here spins up a
fresh Firecracker microVM, runs the snippet, and returns a normalized
``ExecutionResult``.
"""

from __future__ import annotations

import re
import shlex
import time
from typing import Iterable

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import get_settings
from ..state import ExecutionResult


_IMPORT_RE = re.compile(r"^\s*(?:from\s+([a-zA-Z_][\w]*)|import\s+([a-zA-Z_][\w]*))", re.MULTILINE)

# Modules that ship with CPython — never pip-install these.
_STDLIB_HINT = {
    "abc", "argparse", "ast", "asyncio", "base64", "collections", "contextlib",
    "copy", "csv", "dataclasses", "datetime", "decimal", "enum", "functools",
    "hashlib", "heapq", "io", "itertools", "json", "logging", "math", "os",
    "pathlib", "pickle", "random", "re", "shutil", "socket", "sqlite3",
    "statistics", "string", "subprocess", "sys", "tempfile", "textwrap",
    "threading", "time", "traceback", "typing", "unittest", "urllib", "uuid",
    "warnings", "xml", "zipfile",
}

# Common name -> pip package alias.
_PIP_ALIAS = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
}


class TransientSandboxError(RuntimeError):
    """Raised for retry-worthy sandbox failures (network blips, cold start)."""


_TRANSIENT = (TransientSandboxError, TimeoutError, ConnectionError)


def _extract_imports(code: str) -> list[str]:
    """Best-effort detection of third-party imports needing pip install."""
    found: set[str] = set()
    for m in _IMPORT_RE.finditer(code):
        name = m.group(1) or m.group(2)
        if not name or name in _STDLIB_HINT:
            continue
        found.add(_PIP_ALIAS.get(name, name))
    return sorted(found)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception_type(_TRANSIENT),
    reraise=True,
)
def run_in_sandbox(
    code: str,
    deps: Iterable[str] | None = None,
    timeout_s: int | None = None,
    artifacts_dir: str | None = None,
) -> tuple[ExecutionResult, list[str]]:
    """Execute ``code`` in a fresh E2B sandbox.

    Returns ``(result, saved_files)``. If ``artifacts_dir`` is provided, any
    new files created in the sandbox's working directory are downloaded.
    """

    # Imported lazily so unit tests can run without the package installed.
    from e2b_code_interpreter import Sandbox  # type: ignore[import-not-found]

    settings = get_settings()
    timeout = timeout_s or settings.sandbox_timeout_s
    pkgs = list(deps) if deps is not None else _extract_imports(code)
    saved: list[str] = []

    started = time.monotonic()
    try:
        with Sandbox(
            api_key=settings.e2b_api_key.get_secret_value(),
            timeout=timeout,
        ) as sbx:
            if pkgs:
                install_cmd = f"pip install --quiet {' '.join(shlex.quote(p) for p in pkgs)}"
                sbx.commands.run(install_cmd, timeout=timeout)
            execution = sbx.run_code(code)
            if artifacts_dir:
                saved = _download_artifacts(sbx, artifacts_dir)
    except _TRANSIENT:
        raise
    except Exception as exc:  # noqa: BLE001 — boundary translation
        return (
            ExecutionResult(
                stdout="",
                stderr="",
                error=f"{type(exc).__name__}: {exc}",
                exit_code=1,
                duration_ms=int((time.monotonic() - started) * 1000),
            ),
            [],
        )

    stdout = "\n".join(getattr(execution.logs, "stdout", []) or [])
    stderr = "\n".join(getattr(execution.logs, "stderr", []) or [])
    err = getattr(execution, "error", None)
    error_str = None
    if err is not None:
        name = getattr(err, "name", "") or ""
        value = getattr(err, "value", "") or str(err)
        error_str = f"{name}: {value}".strip(": ") or str(err)

    return (
        ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            error=error_str,
            exit_code=0 if error_str is None else 1,
            duration_ms=int((time.monotonic() - started) * 1000),
        ),
        saved,
    )


def _download_artifacts(sbx, dest_dir: str) -> list[str]:
    """Best-effort: list files in /home/user and copy them locally."""
    from pathlib import Path as _P

    saved: list[str] = []
    try:
        files = sbx.files.list("/home/user")
    except Exception:
        return saved

    out_root = _P(dest_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    for entry in files or []:
        name = getattr(entry, "name", None) or (entry.get("name") if isinstance(entry, dict) else None)
        is_dir = getattr(entry, "type", None) == "dir" or (
            isinstance(entry, dict) and entry.get("type") == "dir"
        )
        if not name or is_dir or name.startswith("."):
            continue
        try:
            data = sbx.files.read(f"/home/user/{name}", format="bytes")
        except Exception:
            continue
        target = out_root / name
        target.write_bytes(data if isinstance(data, (bytes, bytearray)) else bytes(data))
        saved.append(str(target))
    return saved
