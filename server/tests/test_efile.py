"""Phase 8: e-file dry run. export → approve → sign (hash locked) → submit → acknowledgement."""
from __future__ import annotations

import pytest

from server import demo, efile, store
from server.errors import ToolFailure
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


@pytest.fixture(autouse=True)
def instant_acks(monkeypatch):
    monkeypatch.setattr(efile, "QUEUE_S", 0)
    monkeypatch.setattr(efile, "ACK_S", 0)


def approve_all(doc_id):
    for f in call("read_k1", doc_id)["flags"]:
        if f["ack_required"]:
            call("acknowledge_flag", doc_id, f["path"])
    call("approve_k1", doc_id)


def case_with_k1(name):
    case = call("create_case", name, 2025, "single")["case"]
    doc = call("intake_k1", case["id"], "oak-ventures")["document"]
    return case, doc


def to_signed(case_id, agi=None):
    f = call("efile_export", case_id)["filing"]
    f = call("efile_approve", f["id"])["filing"]
    on_file = call("efile_status", case_id)["efile_database"]["prior_year_agi"]
    return call("efile_sign", f["id"], "24681", on_file if agi is None else agi)["filing"]


def test_blocking_prechecks_until_k1_approved():
    case, doc = case_with_k1("Blocked filer")
    f = call("efile_export", case["id"])["filing"]
    assert f["status"] == "ready" and f["xml_url"]
    codes = [b["code"] for b in f["checks"]["blocking"]]
    assert "k1_not_approved" in codes
    k1 = next(b for b in f["checks"]["blocking"] if b["code"] == "k1_not_approved")
    assert k1["fix"]["href"] == f"/cases/{case['id']}/k1/{doc['id']}"
    with pytest.raises(ToolFailure) as e:
        call("efile_approve", f["id"])
    assert e.value.code == "blocking_checks"
    # The fake e-File database only enrolls the taxpayer at approval.
    assert call("efile_status", case["id"])["efile_database"] is None
    # A synthetic filer (SSA advertising SSN) was added to the case.
    assert call("efile_status", case["id"])["filer"]["ssn_masked"].endswith("4320")


def test_accepted_with_hash_locked_and_timeline():
    case, doc = case_with_k1("Accepted filer")
    approve_all(doc["id"])
    f = call("efile_export", case["id"])["filing"]
    assert f["checks"]["blocking"] == []
    v = f["checks"]["validator"]
    assert "IND-052" in [r["rule"] for r in v["transmitter"]] and "IND-001-01" in [r["rule"] for r in v["preparer"]]
    unsigned = f["sha256"]
    f = call("efile_approve", f["id"])["filing"]
    rec = call("efile_status", case["id"])["efile_database"]
    assert rec["name_control"] == "CLIE" and rec["prior_year_agi"] > 0
    f = call("efile_sign", f["id"], "24681", rec["prior_year_agi"])["filing"]
    assert f["hash_locked"] and f["sha256"] != unsigned and "pin" not in f["signature"]
    xml = efile.xml_path(store.get_filing(f["id"])).read_text()
    assert f"<PrimaryPriorYearAGIAmt>{rec['prior_year_agi']}</PrimaryPriorYearAGIAmt>" in xml
    assert efile.sha256(xml) == f["sha256"]
    f = call("efile_submit", f["id"])["filing"]
    f = call("efile_status", case["id"])["current"]
    assert f["status"] == "accepted" and f["submission"]["result"] == "accepted"
    assert [t["status"] for t in f["timeline"]] == ["ready", "approved", "signed", "queued", "transmitted", "accepted"]
    sid = f["submission"]["submission_id"]
    assert len(sid) == 20 and sid.startswith(efile.EFIN)


def test_prior_year_agi_reject_then_refile():
    case, doc = case_with_k1("AGI reject")
    approve_all(doc["id"])
    f = to_signed(case["id"], agi=1234)
    call("efile_submit", f["id"])
    f = call("efile_status", case["id"])["current"]
    assert f["status"] == "rejected"
    [r] = f["submission"]["rejects"]
    assert r["rule"] == "IND-031-04" and r["fix"]["href"].endswith("/efile?fix=signature")
    f2 = to_signed(case["id"])
    call("efile_submit", f2["id"])
    st = call("efile_status", case["id"])
    assert [x["number"] for x in st["filings"]] == [2, 1]
    assert st["current"]["status"] == "accepted"


def test_name_control_reject_routes_to_filer():
    case, doc = case_with_k1("Name reject")
    approve_all(doc["id"])
    f = to_signed(case["id"])
    call("efile_set_filer", case["id"], last_name="Rivera")
    # Changing the name changes the start form, so the signed export is stale.
    with pytest.raises(ToolFailure) as e:
        call("efile_submit", f["id"])
    assert e.value.code == "stale_export"
    assert call("efile_status", case["id"])["current"]["stale"]
    f = to_signed(case["id"])
    assert f["filer"]["name_control"] == "RIVE"
    call("efile_submit", f["id"])
    f = call("efile_status", case["id"])["current"]
    [r] = f["submission"]["rejects"]
    assert r["rule"] == "R0000-500-01" and r["fix"]["href"].endswith("/efile?fix=filer") and "'CLIE'" in r["detail"]
    with pytest.raises(ToolFailure):
        call("efile_set_filer", case["id"], last_name="R0bert")


def test_stale_after_k1_edit_and_duplicate_after_accept():
    case, doc = case_with_k1("Dup filer")
    approve_all(doc["id"])
    f = to_signed(case["id"])
    call("efile_submit", f["id"])
    assert call("efile_status", case["id"])["current"]["status"] == "accepted"
    f = to_signed(case["id"])
    call("efile_submit", f["id"])
    [r] = call("efile_status", case["id"])["current"]["submission"]["rejects"]
    assert r["rule"] == "IND-515-01" and r["fix"] is None
    # A K-1 edit after signing returns the K-1 to review: the signed return is stale.
    f = to_signed(case["id"])
    call("edit_k1_value", doc["id"], "part_iii.box_1", 1.0, "test edit")
    with pytest.raises(ToolFailure) as e:
        call("efile_submit", f["id"])
    assert e.value.code == "stale_export"


def test_state_and_input_refusals():
    case, doc = case_with_k1("Refusals")
    approve_all(doc["id"])
    f = call("efile_export", case["id"])["filing"]
    with pytest.raises(ToolFailure) as e:
        call("efile_sign", f["id"], "24681", 0)
    assert e.value.code == "wrong_state"
    call("efile_approve", f["id"])
    for pin in ("1234", "00000", "abcde"):
        with pytest.raises(ToolFailure) as e:
            call("efile_sign", f["id"], pin, 0)
        assert e.value.code == "bad_pin"
    # A new export voids the open one.
    call("efile_export", case["id"])
    assert store.get_filing(f["id"])["status"] == "void"
    with pytest.raises(ToolFailure) as e:
        call("efile_export", "ref-k1s")
    assert e.value.code == "case_read_only"


def test_w2_without_address_blocks_export():
    case = call("create_case", "W-2 filer", 2025, "single")["case"]
    call("set_return_inputs", case["id"], [{"node_type": "w2", "data": {"employer_name": "Acme", "box1_wages": 50000,
                                                                          "box2_fed_withheld": 4000}}])
    f = call("efile_export", case["id"])["filing"]
    [b] = f["checks"]["blocking"]
    assert b["code"] == "export_failed" and "to W-2 #1" in b["fix_hint"] and f["xml_url"] is None


def test_classify():
    rule = lambda n, msg="": {"ruleNumber": n, "message": msg}
    assert efile.classify(rule("IND-062")) == "transmitter"
    assert efile.classify(rule("X-1", "The TIN in the IRS Submission Manifest must…")) == "transmitter"
    assert efile.classify(rule("IND-001-01")) == "preparer"
    assert efile.classify(rule("F1040-065-05")) == "fix"
    assert efile.classify(rule("F8960-007", "Form 8960, Line 8 must equal…")) == "engine"
    assert efile.name_control("O'Brien-Smith") == "OBRI"


def test_http_xml_download():
    from fastapi.testclient import TestClient
    from server.app import build_http

    case, doc = case_with_k1("HTTP filer")
    approve_all(doc["id"])
    with TestClient(build_http()) as client:
        f = client.post(f"/api/cases/{case['id']}/efile/exports").json()["filing"]
        r = client.get(f["xml_url"])
        assert r.status_code == 200 and r.text.startswith("<Return") and "attachment" in r.headers["content-disposition"]
        assert client.get("/api/filings/nope/xml").json()["error"]["code"] == "filing_not_found"
