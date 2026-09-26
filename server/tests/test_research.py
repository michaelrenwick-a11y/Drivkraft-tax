"""Phase 5: tax research. Cached answers, the cost gate, Bizora stream parsing, chat limits."""
from __future__ import annotations

import asyncio
import json

import pytest

from server import chat, demo, research, store
from server.errors import ToolFailure
from server.tools import channel, load_all
from server.tools.proposals import _citation, source_href

T = load_all()


def call(_tool, *args, **kwargs):
    return T[_tool].fn(*args, **kwargs)


@pytest.fixture(scope="module", autouse=True)
def data_root(tmp_path_factory):
    store.configure(tmp_path_factory.mktemp("data"))
    demo.seed()
    yield
    store._root = None


@pytest.fixture(autouse=True)
def no_bizora(monkeypatch):
    monkeypatch.delenv("BIZORA_API_KEY", raising=False)
    monkeypatch.delenv("DRIVKRAFT_INVITE_CODE", raising=False)


def test_cache_entries_are_well_formed():
    for e in research.cache_entries():
        markers = {int(n) for n in __import__("re").findall(r"\[(\d+)\]", e["answer"])}
        assert markers == set(range(1, len(e["citations"]) + 1)), e["id"]
        assert all(c["url"].startswith("https://") and c["label"] and c["snippet"] for c in e["citations"])
        assert research.match_cache(e["question"])["id"] == e["id"]
        for a in e.get("aliases", []):
            assert research.match_cache(a)["id"] == e["id"], a


def test_quote_is_free_when_cached_and_priced_when_live():
    q = call("quote_research", "how are collectibles gains taxed?")
    assert q["cached"] and q["cost_usd"] == 0
    q = call("quote_research", "Can a partner deduct guaranteed payments for health insurance?", "deep")
    assert not q["cached"] and q["cost_usd"] == 1.50 and not q["live_available"]
    with pytest.raises(ToolFailure) as e:
        call("quote_research", "x", "fast")
    assert e.value.code == "question_required"
    with pytest.raises(ToolFailure) as e:
        call("quote_research", "How are collectibles taxed?", "slow")
    assert e.value.code == "bad_mode"


def test_cached_research_saves_on_the_case_with_related_boxes():
    case = call("create_case", "Research household", 2025, "single")["case"]
    call("intake_k1", case["id"], "proof-k1")
    out = call("tax_research", "How is Box 13 H investment interest limited?", case_id=case["id"])
    r = out["research"]
    assert r["cached"] and r["cost_usd"] == 0 and r["case_id"] == case["id"]
    assert [c["n"] for c in r["citations"]] == list(range(1, len(r["citations"]) + 1))
    assert r["related_boxes"] and [b["path"] for b in r["related_boxes"]] == ["part_iii.box_13.H"]
    assert "not a live Bizora response" in r["note"]
    refs = [s["ref"] for s in out["sources"]]
    assert refs[0] == f"research://{r['id']}" and refs[1] == f"research://{r['id']}/cite/1"
    listing = call("list_research", case["id"])
    assert listing["research"][0]["id"] == r["id"] and listing["total_cost_usd"] == 0
    assert len(listing["cached_questions"]) == 3
    assert call("get_research", r["id"])["research"]["answer"] == r["answer"]
    assert source_href(refs[1]) == f"/research?entry={r['id']}#cite-1"
    assert _citation(refs[1])["label"] == r["citations"][0]["label"]
    call("delete_research", r["id"])
    with pytest.raises(ToolFailure) as e:
        call("get_research", r["id"])
    assert e.value.code == "research_not_found"


def test_live_research_is_gated(monkeypatch):
    q = "Can a partner deduct guaranteed payments for health insurance?"
    with pytest.raises(ToolFailure) as e:
        call("tax_research", q)
    assert e.value.code == "research_not_configured" and e.value.detail["cached_questions"]

    monkeypatch.setenv("BIZORA_API_KEY", "sk_test")
    calls = []
    monkeypatch.setattr(research, "ask_bizora",
                        lambda *a: calls.append(a) or research.LiveAnswer("Yes, above the line [1].",
                                                                          [{"label": "IRC §162(l)"}], []))
    with pytest.raises(ToolFailure) as e:
        call("tax_research", q, "deep")
    assert e.value.code == "cost_confirmation_required" and e.value.detail["cost_usd"] == 1.50
    with pytest.raises(ToolFailure) as e:
        call("tax_research", q, "deep", confirm_cost_usd=0.24)
    assert e.value.code == "cost_confirmation_required"

    monkeypatch.setenv("DRIVKRAFT_INVITE_CODE", "letmein")
    with pytest.raises(ToolFailure) as e:
        call("tax_research", q, "fast", confirm_cost_usd=0.24)
    assert e.value.code == "invite_required"
    assert not calls

    r = call("tax_research", q, "fast", confirm_cost_usd=0.24, invite_code="letmein")["research"]
    assert not r["cached"] and r["cost_usd"] == 0.24 and calls[0][1] == "fast"

    token = channel.set("chat")
    try:
        with pytest.raises(ToolFailure) as e:
            call("tax_research", q, "fast", confirm_cost_usd=0.24, invite_code="letmein")
        assert e.value.code == "live_research_not_in_chat"
        assert call("tax_research", "How is Box 13 H investment interest limited?")["research"]["origin"] == "chat"
    finally:
        channel.reset(token)


def test_parse_stream_renumbers_citations_and_collects_steps():
    a, b = "8a4b9bf1-7940-4c49-a913-807fa1244966", "11111111-2222-3333-4444-555555555555"
    chunks = [
        {"custom_data": {"type": "step_message", "title": "Federal", "description": "Searching §179"}},
        {"choices": [{"delta": {"custom_data": [{"type": "source_message", "content": [
            {"node_id": a, "tool": "taxes_federal_internal_revenue_code", "s3_file_path": "https://x/usc26.xml",
             "text": "Section 179(b)(1) limits the aggregate cost…", "page_label": "1"},
            {"node_id": b, "tool": "irs_publications", "text": "Pub 946"}]}]}}]},
        {"choices": [{"delta": {"content": f"The limit is $1,220,000 [{b}]"}}]},
        {"choices": [{"delta": {"content": f" and phases out [{a}][{b}] [deadbeef-0000-0000-0000-000000000000]."}}]},
    ]
    lines = [f"data: {json.dumps(c)}" for c in chunks] + ["", "data: [DONE]", "data: ignored"]
    out = research.parse_stream(lines)
    assert out.answer == ("The limit is $1,220,000 [1] and phases out [2][1] "
                          "[deadbeef-0000-0000-0000-000000000000].")
    assert [c["label"] for c in out.citations] == ["Irs publications", "Federal internal revenue code · §179(b)(1) · p. 1"]
    assert out.steps == ["Federal: Searching §179"]


def test_chat_offers_cached_research_without_the_cost_arguments():
    from server.app import build_mcp

    tools = {t["name"]: t for t in asyncio.run(chat.anthropic_tools(build_mcp()))}
    assert {"tax_research", "quote_research", "list_research", "get_research"} <= set(tools)
    assert "delete_research" not in tools
    props = tools["tax_research"]["input_schema"]["properties"]
    assert "confirm_cost_usd" not in props and "invite_code" not in props
