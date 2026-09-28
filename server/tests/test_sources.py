"""Phase 11: dropped source documents → return inputs (and an OTD K-1), checked
against the Holloway answer key (fixtures/sources, made by scripts/make_source_docs.py)."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from fpdf import FPDF

from server import demo, sourcedocs, store
from server.errors import ToolFailure
from server.tools import load_all

T = load_all()
SRC = Path(__file__).parent / "fixtures" / "sources"
KEY = json.loads((SRC / "holloway-opentax-input.json").read_text())


def call(_tool, *args, **kwargs):
    return T[_tool].fn(*args, **kwargs)


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def key_forms(node: str) -> list[dict]:
    return [f["data"] for f in KEY["forms"] if f["node_type"] == node]


@pytest.fixture(scope="module", autouse=True)
def data_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    store.configure(root)
    demo.seed()
    yield root
    store._root = None


@pytest.fixture(scope="module")
def holloway():
    case = call("create_case", "Holloway household", 2025, "mfj")["case"]
    added = {f.name: call("add_source_document", case["id"], b64(f), f.name)["source"] for f in sorted(SRC.glob("*.pdf"))}
    return case, added


# ── Parsing, against the answer key ───────────────────────────────────────

def parsed(name: str) -> sourcedocs.Parsed:
    return sourcedocs.parse(SRC / name)


def test_w2s_match_the_answer_key():
    for name, want in zip(["01-W2-Daniel-GreatLakesMobility.pdf", "02-W2-Priya-HuronValleyHealth.pdf"], key_forms("w2")):
        [(node, got, _)] = parsed(name).inputs
        assert node == "w2"
        for k, v in want.items():
            assert got[k] == v, (name, k)
        assert got["employee_ssn"].startswith("XXX-XX-")


def test_1099s_and_1098_match_the_answer_key():
    [(_, i, _)] = parsed("03-1099-INT-LakeshoreCreditUnion.pdf").inputs
    assert i["box1"] == key_forms("f1099int")[0]["box1"]
    div = parsed("04-1099-Composite-NorthpointBrokerage.pdf")
    d = next(x for n, x, _ in div.inputs if n == "f1099div")
    for k, v in key_forms("f1099div")[0].items():
        assert d[k] == v, k
    lots = [x for n, x, _ in div.inputs if n == "f1099b"]
    want = key_forms("f1099b")
    assert [(l["proceeds"], l["cost_basis"], l["part"] in "DEF") for l in lots] == \
           [(w["proceeds"], w["cost_basis"], w["is_long_term"]) for w in want]
    assert all(l["date_sold"].startswith("2025-") for l in lots)
    m = parsed("05-1098-WolverineHomeLending.pdf")
    f1098 = next(x for n, x, _ in m.inputs if n == "f1098")
    assert f1098["box1_mortgage_interest"] == 11862.40 and f1098["box3_origination_date"] == "2021-06-14"
    assert ("schedule_a", {"line_5b_real_estate_tax": 6214.0}) in [(n, x) for n, x, _ in m.inputs]


def test_organizer_fills_filing_info_dependents_and_deductions():
    p = parsed("00-Client-Organizer-Holloway.pdf")
    by = {n: x for n, x, _ in p.inputs}
    g = by["start"]["general"]
    assert g["filing_status"] == "mfj" and g["taxpayer_first_name"] == "Daniel" and g["spouse_first_name"] == "Priya"
    assert [(d["first_name"], d["relationship"], d["dob"]) for d in g["dependents"]] == \
           [("Maya", "daughter", "2016-07-15"), ("Theo", "son", "2021-03-02")]
    assert by["f2441"] == {"qualifying_expenses_paid": 7800.0, "qualifying_person_count": 1}
    assert by["schedule_a"] == {"line_11_cash_contributions": 3600.0, "line_12_noncash_contributions": 420.0}
    assert any("Direct deposit" in w for w in p.warnings)      # read, but left to the preparer


def test_k1_becomes_valid_otd_that_bridges_to_the_answer_key(tmp_path):
    import yaml
    from server.bridge import translator
    p = parsed("06-K1-1065-RiverbendGrowthPartners.pdf")
    path = tmp_path / "k1.otd.yaml"
    path.write_text(yaml.safe_dump(sourcedocs.otd_from_k1(p.k1, "2026-09-28T00:00:00Z"), sort_keys=False))
    r = translator.bridge_k1(path)
    assert r.status == "ok", [e.message for e in r.errors]
    (_, item), *_ = r.forms()
    want = key_forms("k1_partnership")[0]
    for k in ("box1_ordinary_business", "box5_interest", "box6a_ordinary_dividends", "box6b_qualified_dividends",
              "box9a_net_lt_cap_gain"):
        assert item[k] == want[k], k
    assert item["box20z_qbi"] == 4210.0 and item["box20_w2_wages"] == 12940.0 and item["box20_ubia"] == 38500.0


# ── Refusals ──────────────────────────────────────────────────────────────

def _plain_pdf(tmp_path: Path, title: str) -> Path:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.cell(0, 10, title)
    out = tmp_path / "plain.pdf"
    pdf.output(out)
    return out


def test_a_document_without_the_synthetic_marker_is_refused_and_not_stored(tmp_path):
    case = call("create_case", "Refusals", 2025, "single")["case"]
    out = call("add_source_document", case["id"], b64(_plain_pdf(tmp_path, "Form W-2 Wage and Tax Statement")), "real.pdf")
    assert out["refused"] and out["source"]["error"]["code"] == "not_synthetic"
    assert not out["source"]["has_pdf"] and store.list_inputs(case["id"]) == []


def test_non_pdf_unsupported_and_read_only_cases_are_refused(tmp_path):
    case = call("create_case", "Refusals 2", 2025, "single")["case"]
    with pytest.raises(ToolFailure) as e:
        call("add_source_document", case["id"], base64.b64encode(b"hello").decode(), "x.pdf")
    assert e.value.code == "not_a_pdf"
    out = call("add_source_document", case["id"], b64(_plain_pdf(tmp_path, "SYNTHETIC grocery list")), "list.pdf")
    assert out["source"]["error"]["code"] == "unsupported_form"
    with pytest.raises(ToolFailure) as e:
        call("add_source_document", "ref-bench-82", b64(SRC / "03-1099-INT-LakeshoreCreditUnion.pdf"), "i.pdf")
    assert e.value.code == "case_read_only"


# ── The case, end to end ──────────────────────────────────────────────────

def test_dropping_the_packet_fills_the_case(holloway):
    case, added = holloway
    assert all(s["status"] == "added" for n, s in added.items() if "K1" not in n)
    k1 = added["06-K1-1065-RiverbendGrowthPartners.pdf"]
    assert k1["status"] == "k1" and k1["document"]["status"] == "needs_review" and k1["document"]["has_pdf"]
    ev = call("get_evidence", k1["doc_id"], "1")          # text-layer box locations, like upstream evidence
    assert ev["available"] and ev["page"] == 1 and ev["text"] == "4,210.00"
    assert call("read_k1", k1["doc_id"], "full")["pages"]["count"] == 2
    nodes = sorted(i["node_type"] for i in store.list_inputs(case["id"]))
    assert nodes == sorted(["start", "f2441", "schedule_a", "w2", "w2", "f1099int", "f1099div", "f1099b", "f1099b",
                            "f1099b", "f1099b", "f1098", "schedule_a"])
    summary = call("get_case_summary", case["id"])
    assert summary["source_documents"] == 7 and summary["inputs"] == 13


def test_duplicates_are_refused(holloway):
    case, _ = holloway
    with pytest.raises(ToolFailure) as e:
        call("add_source_document", case["id"], b64(SRC / "03-1099-INT-LakeshoreCreditUnion.pdf"), "again.pdf")
    assert e.value.code == "duplicate"


def test_return_matches_the_documents_and_flags_engine_gaps(holloway):
    case, added = holloway
    doc_id = added["06-K1-1065-RiverbendGrowthPartners.pdf"]["doc_id"]
    for f in call("read_k1", doc_id)["flags"]:
        if f["ack_required"]:
            call("acknowledge_flag", doc_id, f["path"])
    call("approve_k1", doc_id)
    r = call("calculate_return", case["id"])
    lines = {l["key"]: l["value"] for l in r["lines"]}
    assert lines["line1a_wages"] == 204_700
    assert lines["line2b_taxable_interest"] == pytest.approx(1184.22 + 86)
    assert lines["line3b_ordinary_dividends"] == pytest.approx(3412.87 + 212)
    # ST −104.75 + LT 6,725.65 + capital gain distributions 488 + K-1 box 9a 1,140
    assert lines["line7_capital_gain"] == pytest.approx(8248.90)
    assert lines["line25a_w2_withheld"] == 16_850 + 7_940
    codes = {c["code"] for c in r["caveats"]}
    # Known OpenTax gaps at the pinned version, reported rather than patched:
    assert {"excess_ss_across_spouses", "itemized_below_standard", "qualified_dividends_mismatch"} <= codes


def test_set_return_inputs_keeps_document_inputs_and_remove_takes_them_away(holloway):
    case, added = holloway
    before = len(store.list_inputs(case["id"]))
    call("set_return_inputs", case["id"], [{"node_type": "f1098e", "data": {"box1_student_loan_interest": 500}}])
    assert len(store.list_inputs(case["id"])) == before + 1
    call("set_return_inputs", case["id"], [])
    src = added["04-1099-Composite-NorthpointBrokerage.pdf"]
    call("remove_source_document", src["id"])
    assert len(store.list_inputs(case["id"])) == before - 5
    k1 = added["06-K1-1065-RiverbendGrowthPartners.pdf"]
    call("remove_source_document", k1["id"])
    assert store.get_document(k1["doc_id"]) is None
    assert {s["id"] for s in call("list_source_documents", case["id"])["source_documents"]}.isdisjoint({src["id"], k1["id"]})


def test_the_bundled_synthetic_k1_runs_the_upstream_extractor():
    from server.samples import SAMPLES
    case = call("create_case", "Copperleaf drop", 2025, "single")["case"]
    out = call("add_source_document", case["id"], b64(SAMPLES["synthetic-k1"].path), "synthetic-k1.pdf")["source"]
    assert out["status"] == "k1" and out["document"]["sample"] == "synthetic-k1"
    assert out["document"]["status"] in ("needs_review", "blocked")
