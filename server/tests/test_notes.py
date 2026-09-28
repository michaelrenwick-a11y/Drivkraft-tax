"""Phase 6: meeting notes, analysis → proposals of every kind, the checklist, and
the proposals-table migration. Live analysis runs against a scripted fake client."""
from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace as NS

import pytest

from server import demo, notes, store
from server.errors import ToolFailure
from server.tools import load_all
from server.tools.proposals import source_href

T = load_all()


def call(_tool, *args, **kwargs):
    return T[_tool].fn(*args, **kwargs)


@pytest.fixture(scope="module", autouse=True)
def data_root(tmp_path_factory):
    store.configure(tmp_path_factory.mktemp("data"))
    demo.seed()
    yield
    store._root = None


@pytest.fixture(scope="module")
def rivera():
    case = call("create_case", "Rivera household", 2025, "single")["case"]
    doc = call("intake_k1", case["id"], "proof-k1")["document"]      # carries Box 13 H
    try:
        call("approve_k1", doc["id"])
    except ToolFailure as e:           # acknowledge what the engine can't take, then approve
        assert e.code == "unacknowledged_flags"
        for f in e.detail:
            call("acknowledge_flag", doc["id"], f["path"], note="test")
        call("approve_k1", doc["id"])
    return case, doc


# ── Parsing ───────────────────────────────────────────────────────────────

def test_parse_formats():
    segs = notes.parse("[00:01:05] Dana: first\nstill Dana\nLuis (1:02:03): second\n(0:07) third")
    assert [(s["t"], s["speaker"]) for s in segs] == [(65, "Dana"), (3723, "Luis"), (7, None)]
    assert segs[0]["text"] == "first still Dana"
    untimed = notes.parse("One paragraph\nwrapped.\n\nAnother.")
    assert [s["t"] for s in untimed] == [None, None] and untimed[0]["text"] == "One paragraph wrapped."
    assert notes.clock(65) == "01:05" and notes.clock(3723) == "1:02:03"


# ── Notes ─────────────────────────────────────────────────────────────────

def test_notes_need_an_editable_case():
    with pytest.raises(ToolFailure) as e:
        call("add_note", "ref-k1s", "some notes here")
    assert e.value.code == "case_read_only"


def test_add_search_and_sources(rivera):
    case, _ = rivera
    n = call("add_note", case["id"], sample="rivera-planning")["note"]
    assert n["sample"] == "rivera-planning" and n["timed"] and n["segments"] == 13 and n["duration_s"] == 305
    hits = call("search_notes", "harbor point", case["id"])
    assert hits["total"] >= 2 and hits["matches"][0]["ref"].startswith(f"note://{n['id']}#t=")
    ref = hits["matches"][0]["ref"]
    assert source_href(ref) == f"/cases/{case['id']}/notes?note={n['id']}&t={hits['matches'][0]['t']}"
    full = call("get_note", n["id"])["note"]
    assert full["segments"][4]["clock"] == "01:32" and full["analysis"] is None
    # A pasted copy of the sample is recognised, so its cached analysis applies.
    pasted = call("add_note", case["id"], notes.samples()["rivera-planning"]["transcript"], kind="transcript")["note"]
    assert pasted["sample"] == "rivera-planning"
    call("delete_note", pasted["id"])


def _rivera_note(case_id: str) -> dict:
    return next(n for n in call("list_notes", case_id)["notes"] if n["sample"] == "rivera-planning")


def test_cached_analysis_makes_proposals(rivera):
    case, doc = rivera
    n = _rivera_note(case["id"])
    out = call("analyze_meeting", n["id"])
    assert out["analysis"]["cached"] and len(out["analysis"]["decisions"]) == 3
    assert out["analysis"]["decisions"][0]["source"]["label"].endswith("@ 03:18")
    kinds = [p["kind"] for p in out["proposals"]]
    assert kinds.count("doc_request") == 2 and kinds.count("decision") == 3 and kinds.count("scenario") == 2
    assert kinds.count("research_question") == 2 and kinds.count("follow_up") == 1
    box13 = next(p for p in out["proposals"] if p["kind"] == "scenario" and "13 H" in p["label"])
    assert box13["payload"]["changes"] == {"k1_values": {doc["id"]: {"part_iii.box_13.H": None}}}
    assert all(p["status"] == "pending" and p["note_title"] for p in out["proposals"])
    assert out["proposals"][0]["citations"][0]["href"].startswith(f"/cases/{case['id']}/notes?note=")
    # Analyzing again returns the same proposals; refresh replaces the pending ones.
    again = call("analyze_meeting", n["id"])
    assert again["already_analyzed"] and len(again["proposals"]) == 10
    fresh = call("analyze_meeting", n["id"], refresh=True)
    assert not fresh["already_analyzed"] and len(call("list_proposals", case["id"])["proposals"]) == 10


def _pending(case_id: str, kind: str, contains: str = "") -> dict:
    return next(p for p in call("list_proposals", case_id)["proposals"]
                if p["kind"] == kind and contains in p["label"])


def test_accept_doc_request_adds_checklist(rivera):
    case, _ = rivera
    p = _pending(case["id"], "doc_request", "Harbor Point")
    acc = call("accept_proposal", p["id"])
    items = call("list_checklist", case["id"])
    assert acc["proposal"]["status"] == "accepted" and items["open"] == 1
    item = items["items"][0]
    assert item["item"].startswith("2025 Schedule K-1") and item["source"]["label"].endswith("@ 00:48")
    assert any(o["kind"] == "document_request" for o in call("get_case_summary", case["id"])["open_items"])
    assert call("update_checklist_item", item["id"], "received")["item"]["status"] == "received"
    call("undo_proposal", p["id"])
    assert call("list_checklist", case["id"])["items"] == []


def test_accept_decision_adds_todo(rivera):
    case, _ = rivera
    p = _pending(case["id"], "decision")
    acc = call("accept_proposal", p["id"])
    items = call("list_checklist", case["id"])
    assert acc["proposal"]["status"] == "accepted"
    item = next(i for i in items["items"] if i["id"] == acc["result"]["checklist_id"])
    assert item["type"] == "action" and item["status"] == "open"
    assert any(o["kind"] == "to_do" for o in call("get_case_summary", case["id"])["open_items"])
    assert call("update_checklist_item", item["id"], "received")["item"]["status"] == "received"
    call("undo_proposal", p["id"])
    assert not any(i["id"] == item["id"] for i in call("list_checklist", case["id"])["items"])


def test_accept_scenario_saves_it(rivera):
    case, _ = rivera
    p = _pending(case["id"], "scenario", "File jointly")
    acc = call("accept_proposal", p["id"])
    sid = acc["result"]["scenario_id"]
    assert acc["scenario"]["applied"][0]["change"] == "filing_status"
    assert [s["id"] for s in call("list_scenarios", case["id"])["scenarios"]] == [sid]
    call("undo_proposal", p["id"])
    assert call("list_scenarios", case["id"])["scenarios"] == []


def test_research_questions_never_spend(rivera):
    case, _ = rivera
    cached = _pending(case["id"], "research_question", "Box 13 code H")
    acc = call("accept_proposal", cached["id"])
    assert acc["result"]["cached"] and acc["research"]["cached"]
    assert len(store.list_research(case["id"])) == 1
    call("undo_proposal", cached["id"])
    assert store.list_research(case["id"]) == []

    live = _pending(case["id"], "research_question", "home office")
    acc = call("accept_proposal", live["id"])
    assert acc["result"]["research_id"] is None and acc["research_href"].startswith("/research?q=")
    assert f"case={case['id']}" in acc["research_href"] and store.list_research(case["id"]) == []


def test_follow_up_and_reject(rivera):
    case, _ = rivera
    fu = _pending(case["id"], "follow_up")
    assert fu["payload"]["body"].startswith("Hi Luis and Maria")
    assert call("accept_proposal", fu["id"])["result"] == {"approved": True}
    rq = _pending(case["id"], "doc_request", "1099-B")
    assert call("reject_proposal", rq["id"])["proposal"]["status"] == "rejected"


# ── Live analysis (fake client) ───────────────────────────────────────────

class FakeAnthropic:
    def __init__(self, payload):
        self.payload, self.requests = payload, []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return NS(content=[NS(type="text", text=json.dumps(self.payload))], stop_reason="end_turn",
                  model="claude-opus-5", usage=NS(input_tokens=900, output_tokens=300))


def test_live_analysis(rivera, monkeypatch):
    case, doc = rivera
    n = call("add_note", case["id"], "Client says the Oak K-1 is late.\n\nWe agreed to wait for it.",
             title="Quick call", meeting_date="2026-04-01")["note"]
    monkeypatch.setattr(notes, "configured", lambda: False)
    with pytest.raises(ToolFailure) as e:
        call("analyze_meeting", n["id"])
    assert e.value.code == "analysis_not_configured"

    fake = FakeAnthropic({
        "summary": "Short call about a late K-1.",
        "decisions": [{"text": "Wait for the Oak K-1.", "segment": 1}],
        "doc_requests": [{"item": "2025 K-1 from Oak", "detail": "Late.", "segment": 0}],
        "scenarios": [{"name": "No 13 H", "rationale": "x", "filing_status": None, "segment": 0,
                       "k1_box_values": [{"doc_id": doc["id"], "path": "part_iii.box_13.H", "value": None}]},
                      {"name": "Unexpressible", "rationale": "y", "filing_status": None, "k1_box_values": [],
                       "segment": 0}],
        "research_questions": [], "follow_up": None,
    })
    monkeypatch.setattr(notes, "configured", lambda: True)
    monkeypatch.setattr(notes, "make_client", lambda: fake)
    out = call("analyze_meeting", n["id"])
    req = fake.requests[0]
    assert req["output_config"]["format"]["type"] == "json_schema" and doc["id"] in req["messages"][0]["content"]
    assert "[i=1]" in req["messages"][0]["content"]
    assert not out["analysis"]["cached"] and out["analysis"]["usage"] == {"input": 900, "output": 300}
    assert out["analysis"]["skipped_scenarios"] == ["Unexpressible"]
    assert sorted(p["kind"] for p in out["proposals"]) == ["decision", "doc_request", "scenario"]
    assert out["proposals"][0]["citations"][0]["ref"] == f"note://{n['id']}#p=0"


# ── Migration ─────────────────────────────────────────────────────────────

def test_old_proposals_table_is_rebuilt(tmp_path):
    db = sqlite3.connect(tmp_path / "drivkraft-tax.sqlite3")
    db.executescript("""
      CREATE TABLE cases (id TEXT PRIMARY KEY, name TEXT NOT NULL, tax_year INTEGER NOT NULL,
        filing_status TEXT NOT NULL, read_only INTEGER NOT NULL DEFAULT 0, description TEXT, created TEXT NOT NULL);
      CREATE TABLE proposals (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, doc_id TEXT NOT NULL, kind TEXT NOT NULL,
        path TEXT NOT NULL, old_value TEXT, new_value TEXT, rationale TEXT NOT NULL, citations TEXT NOT NULL DEFAULT '[]',
        origin TEXT NOT NULL, status TEXT NOT NULL, edit_id INTEGER, created TEXT NOT NULL, resolved TEXT);
      INSERT INTO proposals VALUES ('prop-1', 'c', 'd', 'k1_edit', 'part_iii.box_1', '1', '2', 'why', '[]', 'chat',
        'pending', NULL, '2026-01-01T00:00:00Z', NULL);
    """)
    db.commit()
    db.close()
    prev = store._root
    try:
        store.configure(tmp_path)
        p = store.get_proposal("prop-1")
        assert p["payload"] == {} and p["new_value"] == 2 and p["path"] == "part_iii.box_1"
        store.insert_proposal({"id": "prop-2", "case_id": "c", "kind": "follow_up", "payload": {"subject": "s"},
                               "rationale": "r", "citations": [], "origin": "mcp"})
        assert store.get_proposal("prop-2")["doc_id"] is None
    finally:
        store._root = prev
