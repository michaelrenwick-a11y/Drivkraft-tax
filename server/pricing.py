"""Estimated Anthropic API cost from logged token usage (Phase 9).

First-party list prices in USD per million tokens, as of 2026-06. Cache writes
(5-minute TTL) cost 1.25x input; cache reads are 0.1x input unless listed.
Estimates only: the invoice is the source of truth.
"""
from __future__ import annotations

PRICES_AS_OF = "2026-06"

# model id prefix → (input, output, cache read or None for 0.1x input)
PRICES: dict[str, tuple[float, float, float | None]] = {
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-fable-5": (10.0, 50.0, None),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, None),
    "claude-opus-4": (5.0, 25.0, None),
    "claude-sonnet-5": (2.0, 10.0, None),
    "claude-sonnet-4": (3.0, 15.0, None),
    "claude-haiku-4-5": (1.0, 5.0, None),
}


def rates(model: str | None) -> tuple[float, float, float, float] | None:
    """(input, output, cache_read, cache_write) per million tokens, or None if unknown."""
    m = (model or "").lower()
    # Longest prefix first, so claude-opus-5-5 doesn't match claude-opus-5.
    for prefix in sorted(PRICES, key=len, reverse=True):
        if m == prefix or m.startswith(prefix + "-") or m.startswith(prefix + "@"):
            inp, out, read = PRICES[prefix]
            return inp, out, read if read is not None else inp * 0.1, inp * 1.25
    return None


def cost_usd(model: str | None, usage: dict) -> float | None:
    """usage: {input, output, cache_read?, cache_write?} token counts."""
    r = rates(model)
    if r is None:
        return None
    inp, out, read, write = r
    total = (usage.get("input", 0) * inp + usage.get("output", 0) * out
             + usage.get("cache_read", 0) * read + usage.get("cache_write", 0) * write)
    return round(total / 1_000_000, 6)
