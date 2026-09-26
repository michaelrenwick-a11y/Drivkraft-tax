"""Phase 9: operator stats, AI usage logging and cost estimates."""
from __future__ import annotations

import json

import pytest

from server import demo, operator, pricing, store
from server.tools import load_all

T = load_all()


def call(_tool, *args, **kwargs):
    return T[_tool].fn(*args, **kwargs)


@pytest.fixture(scope="module", autouse=True)
def data_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    store.configure(root)
    demo.seed()
    yield root
    store._root = None


def test_pricing():
    assert pricing.rates("claude-opus-5") == (5.0, 25.0, 0.5, 6.25)
    assert pricing.rates("claude-opus-5-5")[:3] == (4.0, 20.0, 0.20)          # not matched as opus-5
    assert pricing.rates("claude-fable-5-1")[2] == 0.25
    assert pricing.rates("claude-opus-4-8")[0] == 5.0
    assert pricing.rates("gpt-5") is None and pricing.cost_usd("gpt-5", {"input": 1}) is None
    cost = pricing.cost_usd("claude-sonnet-5", {"input": 1_000_000, "output": 100_000, "cache_read": 1_000_000})
    assert cost == pytest.approx(2.0 + 1.0 + 0.2)


def test_stats_cover_every_section():
    case = call("create_case", "Operator case", 2025, "single")["case"]
    doc = call("intake_k1", case["id"], "oak-ventures")["document"]
    store.log_event("list_cases", "mcp", 20.0, True)
    store.log_event("list_cases", "http", 12.0, False, "boom")
    store.log_ai_usage("meeting_analysis", "claude-opus-5", {"input": 1000, "output": 500}, "note-x")
    store.log_ai_usage("chat", "mystery-model", {"input": 10, "output": 10}, "chat-x")
    s = call("get_operator_stats")
    assert s["cases"]["total"] == 1 and s["cases"]["reference"] == 2
    assert {"status": "in_review", "count": 1} in s["cases"]["by_status"]
    assert s["k1s"]["total"] >= 4 and s["k1s"]["by_source"]["otd"] >= 1
    assert any(f["code"] == "calculation_incomplete" for f in s["exceptions"]["flags"])
    assert any(b["box"] == "Box 9b" for b in s["bridge"]["unsupported"])
    tc = s["tool_calls"]
    lc = next(t for t in tc["tools"] if t["tool"] == "list_cases")
    assert lc["calls"] >= 2 and lc["errors"] >= 1 and lc["p50_ms"] is not None
    assert len(tc["daily"]) == operator.DAYS and tc["daily"][-1]["calls"] >= 2
    assert tc["recent_errors"][0]["code"] == "boom"
    ai = s["usage"]["anthropic"]
    assert ai["total_usd"] == pytest.approx(0.0175)        # 1000 × $5 + 500 × $25 per 1M
    assert next(r for r in ai["rows"] if r["model"] == "mystery-model")["unpriced"] == 1
    assert s["usage"]["bizora"]["cost_usd"] == 0
    assert {c["name"] for c in s["upstream"]["components"]} == {"OTD spec", "OpenTax source", "opentax binary"}
    assert s["visitors"]["tracked"] is False
    json.dumps(s)   # the HTTP route serializes it
    assert doc["id"]


def test_usage_survives_reset():
    store.log_ai_usage("chat", "claude-opus-5", {"input": 1, "output": 1})
    n = store.query("SELECT COUNT(*) AS n FROM ai_usage")[0]["n"]
    store.reset()
    demo.seed()
    assert store.query("SELECT COUNT(*) AS n FROM ai_usage")[0]["n"] == n


def test_proposals_and_efile_sections():
    s = call("get_operator_stats")
    assert s["proposals"]["by_kind"] == [] and s["proposals"]["accept_rate"] is None
    assert s["efile"]["submissions"] == 0 and s["efile"]["acceptance_rate"] is None
