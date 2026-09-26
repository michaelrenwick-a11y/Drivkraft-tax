"""Operator view (Phase 9): one read-only tool behind the /operator page."""
from __future__ import annotations

from .. import operator
from . import tool


@tool("R", "Operator stats", "GET", "/operator")
def get_operator_stats() -> dict:
    """App-wide activity and health: cases by status, K-1s processed, bridge flag
    and error codes, boxes OpenTax doesn't take, tool-call counts and latency
    (p50/p95, per tool and per day), Anthropic usage with estimated cost, Bizora
    spend (cached vs live), proposal accept rates, e-file results and reject codes,
    upstream pins vs what's installed, and the last smoke-test run. Read-only; no cost.
    """
    return {**operator.gather(), "sources": []}
