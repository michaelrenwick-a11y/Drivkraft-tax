"""Tool-layer tests (Phase 1.5 + 2): seeded cases, intake, review, approval, MCP and HTTP adapters.

Needs vendor/ (scripts/bootstrap.sh). The PDF intake runs the real upstream
pipeline once per session (~10 s).
"""
from __future__ import annotations

import asyncio
import json

import pytest

from server import demo, store
from server.errors import ToolFailure
from server.paths import OPENTAX_BENCH
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


@pytest.fixture(scope="module")
def intake_case():
    case = call("create_case", "Rivera household", 2025, "mfj")["case"]
    doc = call("intake_k1", case["id"], "synthetic-k1")["document"]
    return case, doc


# ── Seeded reference cases (Phase 1.5) ────────────────────────────────────

def test_seed_is_idempotent_and_read_only():
    demo.seed()
    cases = {c["id"]: c for c in call("list_cases")["cases"]}
    assert cases["ref-k1s"]["k1s"] == {"approved": 3}
    assert cases["ref-k1s"]["read_only"]
    with pytest.raises(ToolFailure) as e:
        call("edit_k1_value", "ref-proof", "part_iii.box_1", 1, "test")
    assert e.value.code == "case_read_only" and e.value.fix_hint


def test_what_is_not_in_the_calculation_comes_from_bridge_k1_alone():
    """05-ux Phase 1.5 criterion, checked at the data level."""
    b = call("bridge_k1", "ref-synthetic")
    missing = {e["label"]: e["value"] for e in b["not_in_calculation"]}
    assert {"Box 9b", "Box 13 R", "Box 15 A", "Box 18 A", "Box 21"} <= set(missing)
    assert missing["Box 9b"] == 394600
    assert "Box 13 A" not in missing          # Phase 3: routed to Schedule A
    assert all(f["fix_hint"] for f in b["flags"])
    assert {s["ref"] for s in b["sources"]} >= {"k1://ref-synthetic/box/part_iii.box_9b"}


@pytest.mark.parametrize("box,code,path", [
    ("1", None, "part_iii.box_1"), ("Box 6a", None, "part_iii.box_6a"), ("11", "A", "part_iii.box_11.A"),
    ("11A", None, "part_iii.box_11.A"), ("B", None, "part_i.item_b"), ("K1", None, "part_ii.item_k1"),
    ("part_iii.box_20.Z.statement.qbi", None, "part_iii.box_20.Z.statement.qbi"),
])
def test_box_addressing(box, code, path):
    assert call("get_k1_box", "ref-synthetic", box, code)["path"] == path


def test_box_and_evidence():
    box = call("get_k1_box", "ref-synthetic", "1")
    [e] = box["entries"]
    assert e["value"] == 556000 and e["disposition"] == "mapped" and e["field"] == "box1_ordinary_business"
    ev = call("get_evidence", "ref-synthetic", "11", "A")
    assert ev["available"] and ev["page"] == 1 and ev["text"] == "A 600,700" and len(ev["bbox"]) == 4
    assert call("get_evidence", "ref-proof", "1")["available"] is False


def test_bad_box_is_a_structured_error():
    with pytest.raises(ToolFailure) as e:
        call("get_k1_box", "ref-synthetic", "99")
    assert e.value.code == "bad_box" and e.value.fix_hint


def test_calculate_reference_bench_82_matches_the_benchmark():
    out = call("calculate_return", "ref-bench-82")
    correct = json.loads((OPENTAX_BENCH / "82-single-w2-k1-1099r-1099int-1099div" / "correct.json").read_text())["correct"]
    lines = {l["key"]: l["value"] for l in out["lines"]}
    for k in ("line24_total_tax", "line35a_refund", "line37_amount_owed"):
        assert abs((lines.get(k) or 0) - correct[k]) <= 5, k
    assert [i["doc_id"] for i in out["included"]] == ["ref-bench-82-oak"]
    assert not out["engine_failures"] and not out["caveats"]


# ── Cases + intake + review (Phase 2) ─────────────────────────────────────

def test_create_case_validates():
    for kwargs, code in [({"name": " "}, "name_required"), ({"name": "x", "tax_year": 2024}, "unsupported_year"),
                         ({"name": "x", "filing_status": "married"}, "bad_filing_status")]:
        with pytest.raises(ToolFailure) as e:
            call("create_case", **kwargs)
        assert e.value.code == code


def test_pdf_intake_runs_named_stages_and_bridges(intake_case):
    case, doc = intake_case
    assert doc["status"] == "needs_review", doc.get("progress")
    stages = doc["progress"]["stages"]
    assert [s["status"] for s in stages] == ["done"] * len(stages)
    assert stages[1]["label"] == "Reading page text" and stages[-1]["id"] == "bridge"
    assert doc["has_pdf"] and doc["label"].startswith("COPPERLEAF")
    k1 = call("read_k1", doc["id"], "full")
    assert k1["bridge_status"] == "ok" and k1["reconciled"] and not k1["can_approve"]
    box1 = next(e for e in k1["entries"] if e["path"] == "part_iii.box_1")
    assert box1["evidence"]["page"] == 1
    assert k1["pages"]["count"] == 27


def test_unknown_sample_is_refused(intake_case):
    case, _ = intake_case
    with pytest.raises(ToolFailure) as e:
        call("intake_k1", case["id"], "my-own.pdf")
    assert e.value.code == "unknown_sample"


def test_edit_keeps_original_rebridges_and_needs_reason(intake_case):
    _, doc = intake_case
    with pytest.raises(ToolFailure) as e:
        call("edit_k1_value", doc["id"], "part_iii.box_1", "556,100", "  ")
    assert e.value.code == "reason_required"
    out = call("edit_k1_value", doc["id"], "part_iii.box_1", "556,100", "PDF shows 556,100")
    assert out["edit"]["old_value"] == 556000 and out["edit"]["new_value"] == 556100
    assert out["bridge_status"] == "ok"
    b = call("bridge_k1", doc["id"])
    assert b["opentax"]["item"]["box1_ordinary_business"] == 556100
    entry = call("get_k1_box", doc["id"], "1")["entries"][0]
    assert entry["edited"] and entry["original_value"] == 556000
    # Restoring the original clears the "edited" marker; the history keeps both edits.
    call("edit_k1_value", doc["id"], "part_iii.box_1", 556000, "Restored original")
    assert not call("get_k1_box", doc["id"], "1")["entries"][0]["edited"]
    assert len(call("read_k1", doc["id"], "full")["edits"]) == 2


def test_negative_amount_refuses_and_blocks_approval(intake_case):
    _, doc = intake_case
    out = call("edit_k1_value", doc["id"], "part_iii.box_5", "(10)", "sign test")
    assert out["bridge_status"] == "refused" and out["document"]["status"] == "blocked"
    assert any(e["code"] == "engine_constraint" and e["fix_hint"] for e in out["errors"])
    with pytest.raises(ToolFailure) as e:
        call("approve_k1", doc["id"])
    assert e.value.code == "refused_by_bridge"
    call("edit_k1_value", doc["id"], "part_iii.box_5", 434000, "Restored original")
    assert call("read_k1", doc["id"])["document"]["status"] == "needs_review"


def test_approval_requires_acknowledging_calculation_incomplete_flags(intake_case):
    case, doc = intake_case
    with pytest.raises(ToolFailure) as e:
        call("approve_k1", doc["id"])
    assert e.value.code == "unacknowledged_flags"
    pending = e.value.detail
    assert pending and all(p["path"] for p in pending)
    for p in pending:
        call("acknowledge_flag", doc["id"], p["path"], note="Not in the engine yet")
    assert call("read_k1", doc["id"])["can_approve"]
    out = call("approve_k1", doc["id"])
    assert out["document"]["status"] == "approved"
    assert call("get_case_summary", case["id"])["case"]["status"] == "ready"
    # Editing an approved K-1 sends it back to review.
    call("edit_k1_value", doc["id"], "part_iii.box_7", 900, "PDF shows 900")
    assert call("read_k1", doc["id"])["document"]["status"] == "needs_review"


# ── Adapters ──────────────────────────────────────────────────────────────

def test_mcp_exposes_every_tool_and_structured_errors():
    from mcp import Client
    from server.app import build_mcp

    async def go():
        async with Client(build_mcp()) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert set(tools) == set(T)
            assert tools["bridge_k1"].annotations.read_only_hint is True
            assert tools["approve_k1"].annotations.read_only_hint is False
            ok = await client.call_tool("get_k1_box", {"doc_id": "ref-synthetic", "box": "1"})
            assert not ok.is_error and "part_iii.box_1" in ok.content[0].text
            bad = await client.call_tool("get_k1_box", {"doc_id": "ref-synthetic", "box": "99"})
            err = json.loads(bad.content[0].text.split(": ", 1)[1])
            assert bad.is_error and err["code"] == "bad_box" and err["fix_hint"]
            res = await client.read_resource("k1://ref-synthetic/box/13")
            assert "part_iii.box_13.A" in res.contents[0].text
            prompt = await client.get_prompt("review_k1", {"doc_id": "ref-synthetic"})
            assert "bridge_k1" in prompt.messages[0].content.text

    asyncio.run(go())


def test_http_routes_share_the_same_functions():
    from fastapi.testclient import TestClient
    from server.app import build_http

    with TestClient(build_http()) as client:
        assert client.get("/api/cases").json()["cases"]
        r = client.get("/api/docs/ref-synthetic/box", params={"box": "11", "code": "A"})
        assert r.status_code == 200 and r.json()["entries"][0]["value"] == 600700
        r = client.post("/api/docs/ref-proof/edits", json={"path": "part_iii.box_1", "value": 1, "reason": "x"})
        assert r.status_code == 403 and r.json()["error"]["code"] == "case_read_only"
        png = client.get("/api/docs/ref-synthetic/pages/1.png")
        assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
        assert client.get("/api/docs/ref-proof/pages/1.png").status_code == 404

        # Data reset: HTTP only, confirmed, re-seeds the reference cases.
        assert "reset" not in {t for t in T}
        mine = client.post("/api/cases", json={"name": "Scratch"}).json()["case"]["id"]
        assert client.post("/api/admin/reset", json={}).status_code == 400
        r = client.post("/api/admin/reset", json={"confirm": "reset"})
        assert r.status_code == 200 and mine not in r.json()["cases"] and "ref-k1s" in r.json()["cases"]
        assert client.get(f"/api/cases/{mine}").status_code == 404
        assert client.get("/api/cases/ref-k1s").json()["case"]["k1s"] == {"approved": 3}
