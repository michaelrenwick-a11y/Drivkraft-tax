"""Return calculation (Phase 3): engine gaps, Schedule A routing, inputs, scenarios, attribution.

Uses the seeded reference cases, so no PDF intake is needed.
"""
from __future__ import annotations

import pytest

from server import calc, demo, store
from server.errors import ToolFailure
from server.tools import load_all

T = load_all()


def call(_tool, *args, **kwargs):
    return T[_tool].fn(*args, **kwargs)


def line(out: dict, key: str) -> float:
    return next((l["value"] for l in out["lines"] if l["key"] == key), 0)


@pytest.fixture(scope="module", autouse=True)
def data_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    store.configure(root)
    demo.seed()
    yield root
    store._root = None


def test_collectibles_gain_no_longer_zeroes_income_tax():
    """Box 9b made OpenTax 2.0.4 fail income_tax_calculation (tax 0). The bridge now holds it back."""
    out = call("calculate_return", "ref-k1s")
    assert not out["engine_failures"]
    assert line(out, "line16_income_tax") > 100_000
    copperleaf = next(i for i in out["included"] if i["doc_id"] == "ref-synthetic")
    assert "part_iii.box_9b" in copperleaf["not_in_calculation"]
    assert "schedule_a" in copperleaf["forms"]


def test_engine_node_failures_are_reported():
    got = calc.parse({"summary": {}, "lines": {"line16_income_tax": [0, 0]}, "warnings": [
        "plain warning",
        '[EXECUTOR_NODE_FAILURE] income_tax_calculation: Zod validation failed for node "x": '
        '[{"code": "invalid_type", "path": ["rate_28_gain"], "message": "Expected number, received array"}]']})
    assert got["warnings"] == ["plain warning"]
    assert got["engine_failures"] == [{"node": "income_tax_calculation",
                                       "message": "rate_28_gain: Expected number, received array"}]


def test_box_13_reaches_schedule_a_merged_with_case_inputs():
    """Singletons are merged: OpenTax counts only one schedule_a entry."""
    a = calc.Contribution("input:1", "schedule_a", {"line_11_cash_contributions": 1000, "force_itemized": True}, {})
    b = calc.Contribution("k1:x", "k1_partnership", {"partnership_name": "X"}, {},
                          extra=[("schedule_a", {"line_11_cash_contributions": 500.5, "line_9_investment_interest": 7})])
    forms = calc.assemble([a, b])
    assert forms["schedule_a"] == ("schedule_a", {"line_11_cash_contributions": 1500.5, "force_itemized": True,
                                                  "line_9_investment_interest": 7})
    out = call("calculate_return", "ref-k1s")
    assert line(out, "line12e_itemized_deductions") > 0


def test_set_return_inputs_checks_the_engine_schema():
    case = call("create_case", "Inputs test", 2025, "single")["case"]
    with pytest.raises(ToolFailure) as e:
        call("set_return_inputs", case["id"], [{"node_type": "w2", "data": {"box1_wage": 1}}])
    assert e.value.code == "unknown_field" and "box1_wages" in e.value.fix_hint
    for bad, code in [({"node_type": "k1_partnership", "data": {}}, "bad_input"),
                      ({"node_type": "nope", "data": {}}, "unknown_node_type"), ({"data": {}}, "bad_input")]:
        with pytest.raises(ToolFailure) as e:
            call("set_return_inputs", case["id"], [bad])
        assert e.value.code == code
    with pytest.raises(ToolFailure) as e:
        call("set_return_inputs", "ref-k1s", [])
    assert e.value.code == "case_read_only"
    with pytest.raises(ToolFailure) as e:
        call("calculate_return", case["id"])
    assert e.value.code == "nothing_to_calculate"

    w2 = {"box1_wages": 100000, "box2_fed_withheld": 12000, "employer_name": "ACME", "employer_ein": "12-3456789"}
    out = call("set_return_inputs", case["id"], [{"node_type": "w2", "data": w2}])
    assert [i["node_type"] for i in out["inputs"]] == ["w2"]
    calc_out = call("calculate_return", case["id"])
    assert line(calc_out, "line1a_wages") == 100000 and calc_out["other_inputs"][0]["label"] == "W-2 · ACME"
    call("set_return_inputs", case["id"], [{"node_type": "w2", "data": {**w2, "box1_wages": 90000}}])
    assert line(call("calculate_return", case["id"]), "line1a_wages") == 90000   # cache follows inputs


def test_get_return_lines_by_number_and_section():
    out = call("get_return_lines", "ref-bench-82", lines="15, line24_total_tax")
    assert [l["key"] for l in out["lines"]] == ["line15_taxable_income", "line24_total_tax"]
    assert out["lines"][0]["label"] == "Taxable income" and out["lines"][0]["ref"].startswith("return://")
    assert {l["section"] for l in call("get_return_lines", "ref-bench-82", section="payments")["lines"]} == {"payments"}
    with pytest.raises(ToolFailure) as e:
        call("get_return_lines", "ref-bench-82", lines="99")
    assert e.value.code == "unknown_line"


def test_explain_line_attributes_to_k1s_and_boxes():
    out = call("explain_line", "ref-bench-82", "line11_agi")
    k1 = next(c for c in out["contributions"] if c["kind"] == "k1")
    # The K-1's AGI effect is linear: its boxes add up to the K-1.
    assert k1["contribution"] == pytest.approx(53885, abs=1)
    assert sum(b["contribution"] for b in k1["boxes"]) == pytest.approx(k1["contribution"], abs=1)
    assert k1["interaction"] == pytest.approx(0, abs=1)
    # Not additive overall: without the W-2, AGI falls under the student-loan phase-out,
    # so the 1098-E's $2,500 deduction reappears. That's what `unattributed` reports.
    assert out["unattributed"] == pytest.approx(-2500, abs=1)
    box1 = next(b for b in k1["boxes"] if b["path"] == "part_iii.box_1")
    assert box1["contribution"] == 29265 and box1["source"]["ref"] == "k1://ref-bench-82-oak/box/part_iii.box_1"
    assert {c["label"] for c in out["contributions"]} >= {"W-2 · ACME INDUSTRIES INC", "1099-INT · FIRST NATIONAL BANK"}


def test_scenarios_compare_without_changing_the_case():
    before = call("calculate_return", "ref-bench-82")["fingerprint"]
    out = call("run_scenario", "ref-bench-82", {"exclude": ["ref-bench-82-oak"]})
    agi = next(r for r in out["lines"] if r["key"] == "line11_agi")
    assert agi["delta"] == pytest.approx(-53885, abs=1)
    assert call("calculate_return", "ref-bench-82")["fingerprint"] == before

    out = call("run_scenario", "ref-k1s", {"filing_status": "mfj",
                                           "k1_values": {"ref-synthetic": {"part_iii.box_9b": 1, "part_iii.box_1": 0}}})
    assert [i["path"] for i in out["ignored"]] == ["part_iii.box_9b"]
    assert [a["change"] for a in out["applied"]] == ["filing_status", "k1_value"]
    assert next(r for r in out["lines"] if r["key"] == "line11_agi")["delta"] == pytest.approx(-556000, abs=1)

    for changes, code in [({}, "empty_scenario"), ({"nope": 1}, "bad_scenario"),
                          ({"exclude": ["zzz"]}, "bad_scenario"),
                          ({"k1_values": {"ref-synthetic": {"part_iii.box_99": 1}}}, "bad_scenario")]:
        with pytest.raises(ToolFailure) as e:
            call("run_scenario", "ref-k1s", changes)
        assert e.value.code == code


def test_saved_scenarios():
    saved = call("run_scenario", "ref-bench-82", {"filing_status": "mfj"}, name="Married filing jointly")["scenario"]
    assert [s["name"] for s in call("list_scenarios", "ref-bench-82")["scenarios"]] == ["Married filing jointly"]
    call("delete_scenario", saved["id"])
    assert call("list_scenarios", "ref-bench-82")["scenarios"] == []
    with pytest.raises(ToolFailure):
        call("delete_scenario", saved["id"])
