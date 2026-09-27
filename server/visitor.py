"""Who is calling, for the hosted demo's per-visitor sandboxes (Phase 10).

None means unscoped: local use, stdio MCP, tests and internal jobs see every case.
The HTTP server sets it per request in demo mode (server/sandbox.py), and the store
then shows a visitor only the reference cases (owner NULL) and their own.
"""
from __future__ import annotations

from contextvars import ContextVar

current: ContextVar[str | None] = ContextVar("visitor", default=None)
