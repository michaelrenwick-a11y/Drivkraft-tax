"""OTD → OpenTax bridge tests. Needs vendor/ (scripts/bootstrap.sh).

Regenerate goldens after an intended change:  UPDATE_GOLDENS=1 .venv/bin/python -m pytest server/tests
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from server import engine
from server.bridge import translator
from server.bridge.translator import bridge_k1
from server.paths import OTD_SCRIPTS, OTD_SPEC, PYTHON, VENDOR
from server.tests.fixtures import FIXTURES

GOLDEN = Path(__file__).with_name("golden")
PROOF = OTD_SPEC / "proof" / "proof-emitted.otd.yaml"
SYNTHETIC = OTD_SPEC / "examples" / "k1-1065-2025-synthetic" / "demonstration" / "output.otd.yaml"
BENCH_82 = FIXTURES / "bench-82-oak-ventures.otd.yaml"
BENCH_82_CASE = VENDOR / "opentax" / "benchmark" / "cases" / "f1040" / "2025" / "82-single-w2-k1-1099r-1099int-1099div"
NODE = "k1_partnership"


def _variant(tmp_path: Path, edit) -> Path:
    """Copy of the proof document with `edit(body)` applied."""
    doc = yaml.safe_load(PROOF.read_text())
    edit(doc["body"])
    out = tmp_path / "variant.otd.yaml"
    out.write_text(yaml.safe_dump(doc, sort_keys=False))
    return out


# ── Mapping completeness ──────────────────────────────────────────────────

def test_every_taxonomy_node_and_code_has_a_rule():
    missing = []
    for part in translator.PARTS:
        for key, node in translator.taxonomy()["nodes"][part]["children"].items():
            if node.get("type") == "coded":
                for code, c in node["codes"].items():
                    if c.get("status") != "reserved" and translator.rule_for(part, key, code) is None:
                        missing.append(f"{part}.{key}.{code}")
            elif translator.rule_for(part, key) is None:
                missing.append(f"{part}.{key}")
    assert not missing


def test_mapping_names_only_real_nodes_and_engine_fields():
    schema = engine.node_schema(NODE)
    tax = translator.taxonomy()["nodes"]
    for part in translator.PARTS:
        for key, rule in translator.mapping()[part].items():
            if key == "default":
                continue
            assert key in tax[part]["children"], f"mapping has unknown node {part}.{key}"
            rules = [rule] if "disposition" in rule else [rule.get("default") or {}, *(rule.get("codes") or {}).values()]
            for r in rules:
                assert not r or r["disposition"] in translator.DISPOSITIONS
                node_schema = engine.node_schema(r["node"]) if r.get("node") else schema
                for f in [r.get("field"), *(s["field"] for s in (r.get("statement") or {}).values())]:
                    assert f is None or f in node_schema, f"{part}.{key} → {f} not in the engine schema"
            for code in (rule.get("codes") or {}):
                assert code in tax[part]["children"][key]["codes"], f"mapping has unknown code {key}.{code}"


# ── Goldens ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,path", [("proof", PROOF), ("synthetic", SYNTHETIC), ("bench-82", BENCH_82)])
def test_golden(name, path):
    got = bridge_k1(path).to_dict()
    golden = GOLDEN / f"{name}.bridge.json"
    if os.environ.get("UPDATE_GOLDENS"):
        golden.write_text(json.dumps(got, indent=2, ensure_ascii=False) + "\n")
    assert got == json.loads(golden.read_text())
    assert got["status"] == "ok"
    assert all(r["ok"] for r in got["reconciliation"]["fields"].values())
    assert all(r["ok"] for r in got["reconciliation"]["boxes"].values())


def test_proof_flags_the_engine_traps():
    codes = {f["code"] for f in bridge_k1(PROOF).to_dict()["flags"]}
    assert {"calculation_incomplete", "engine_overrides_zero", "passive_inferred", "statement_review"} <= codes


def test_synthetic_unverified_blank_box_is_omitted_not_zeroed():
    r = bridge_k1(SYNTHETIC).to_dict()
    assert "box4c_total_guaranteed_payments" not in r["opentax"]["item"]
    assert {"code": "unverified_value", "path": "part_iii.box_4c"}.items() <= next(
        f for f in r["flags"] if f.get("path") == "part_iii.box_4c").items()


# ── Refusals ──────────────────────────────────────────────────────────────

def test_hostile_fixture_is_refused(tmp_path):
    out = tmp_path / "hostile.otd.yaml"
    subprocess.run([str(PYTHON), "-B", str(OTD_SCRIPTS / "assemble_otd.py"), "--fragments",
                    str(OTD_SPEC / "tests" / "fixtures" / "hostile-k1"), "--out", str(out),
                    "--created", "2026-07-30T00:00:00Z"], check=True, capture_output=True)
    r = bridge_k1(out)
    assert r.status == "refused" and r.item is None
    assert any("item_k3_requires_box20_x_statement" in e.message for e in r.errors)


def test_negative_interest_is_refused_not_clamped(tmp_path):
    r = bridge_k1(_variant(tmp_path, lambda b: b["part_iii"]["box_5"].update(value=-18500.0)))
    assert r.status == "refused" and r.item is None
    [err] = [e for e in r.errors if e.code == "engine_constraint"]
    assert "box5_interest" in err.message and err.path == "part_iii.box_5"


def test_guaranteed_payment_arithmetic_is_enforced(tmp_path):
    r = bridge_k1(_variant(tmp_path, lambda b: b["part_iii"]["box_4c"].update(value=99999.0)))
    # The upstream validator catches this first; the bridge's own check is defense in depth.
    assert r.status == "refused" and r.errors[0].path.startswith("part_iii.box_4")


def test_qualified_dividends_cannot_exceed_ordinary(tmp_path):
    r = bridge_k1(_variant(tmp_path, lambda b: b["part_iii"]["box_6b"].update(value=40000.0)))
    assert r.status == "refused" and r.errors[0].path == "part_iii.box_6b"


# ── null ≠ 0 ──────────────────────────────────────────────────────────────

def test_null_is_omitted_and_zero_is_sent(tmp_path):
    def edit(b):
        b["part_iii"]["box_7"]["value"] = None
        b["part_iii"]["box_3"]["value"] = 0.0
    item = bridge_k1(_variant(tmp_path, edit)).item
    assert "box7_royalties" not in item
    assert item["box3_other_rental"] == 0


def test_sstb_true_is_not_sent_and_flags(tmp_path):
    def edit(b):
        z = next(e for e in b["part_iii"]["box_20"]["entries"] if e["code"] == "Z")
        z["statement"]["content"]["sstb"] = True
    r = bridge_k1(_variant(tmp_path, edit))
    assert "box20_sstb" not in r.item
    assert any(f.path == "part_iii.box_20.Z.statement.sstb" for f in r.flags)


# ── Engine ────────────────────────────────────────────────────────────────

def test_engine_strips_unknown_fields(tmp_path):
    """Upstream behavior the bridge's allowlist exists for (planning/03, "To verify")."""
    ret = engine.Return.create(tmp_path, 2025)
    ret.add_form(NODE, {"partnership_name": "X", "partnership_ein": "12-3456789", "box1_ordinary_business": 1})
    forms = engine._run(["form", "list", "--returnId", ret.id], tmp_path)
    assert forms[0]["fields"] == {"partnership_name": "X", "box1_ordinary_business": 1}


@pytest.mark.parametrize("path", [PROOF, SYNTHETIC])
def test_engine_accepts_bridged_items(tmp_path, path):
    ret = engine.Return.create(tmp_path, 2025)
    ret.add_form(NODE, bridge_k1(path).to_dict()["opentax"]["item"])
    assert ret.get()["summary"]["line9_total_income"] > 0


def test_bench_82_fixture_reproduces_the_benchmark(tmp_path):
    """Swap benchmark 82's K-1 for the bridged OTD fixture; same $5 rule as upstream run_benchmark.ts."""
    item = bridge_k1(BENCH_82).to_dict()["opentax"]["item"]
    case = json.loads((BENCH_82_CASE / "input.json").read_text())
    [bench_k1] = [f["data"] for f in case["forms"] if f["node_type"] == NODE]
    assert item == {k: v for k, v in bench_k1.items() if k != "partnership_ein"}

    ret = engine.Return.create(tmp_path, case["year"])
    for f in case["forms"]:
        ret.add_form(f["node_type"], item if f["node_type"] == NODE else f["data"])
    summary = ret.get()["summary"]
    correct = json.loads((BENCH_82_CASE / "correct.json").read_text())["correct"]
    for k in ("line24_total_tax", "line35a_refund", "line37_amount_owed"):
        v = summary.get(k, 0)
        v = v[0] if isinstance(v, list) else v
        assert abs((v or 0) - correct[k]) <= 5, k
