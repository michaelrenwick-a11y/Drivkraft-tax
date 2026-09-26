"""Tool registry. Each capability is a plain function registered once here;
server/app.py exposes every entry as an MCP tool and as a FastAPI route.

Kinds (planning/04): R read-only · W writes to the case · $ costs money · P proposal.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable

REGISTRY: dict[str, "ToolSpec"] = {}

# Which client is calling (mcp · http · chat). The web chat sets "chat" around its
# MCP calls so proposals and the events log can tell it apart from Claude Desktop.
channel: ContextVar[str] = ContextVar("channel", default="mcp")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    fn: Callable
    kind: str
    title: str
    # HTTP route: method + path template using the function's argument names.
    method: str
    route: str


def tool(kind: str, title: str, method: str, route: str):
    def register(fn: Callable) -> Callable:
        REGISTRY[fn.__name__] = ToolSpec(fn.__name__, fn, kind, title, method, route)
        return fn
    return register


def load_all() -> dict[str, ToolSpec]:
    from . import cases, k1, notes, proposals, research, returns  # noqa: F401  (registers on import)
    return REGISTRY
