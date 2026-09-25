"""Build OTD fixtures from OpenTax benchmark K-1s (for the Phase 3 benchmark check).

Takes the upstream OTD proof document as the structural template, clears every
Part III amount to null (blank on the form), then fills in the benchmark K-1's
boxes. The result must pass the upstream validator and bridge back to exactly
the benchmark's `k1_partnership` input (minus `partnership_ein`, which the
engine strips anyway).

    .venv/bin/python -m server.tests.fixtures.build_bench_fixtures
"""
from __future__ import annotations

import copy
import json
import uuid

import yaml

from ...paths import OTD_SPEC, VENDOR
from . import FIXTURES

BENCH = VENDOR / "opentax" / "benchmark" / "cases" / "f1040" / "2025"
CASES = {"82-single-w2-k1-1099r-1099int-1099div": "bench-82-oak-ventures.otd.yaml"}

# OpenTax field → OTD Part III scalar box (only the boxes the benchmarks use).
FIELD_TO_BOX = {
    "box1_ordinary_business": "box_1", "box2_rental_re": "box_2", "box3_other_rental": "box_3",
    "box5_interest": "box_5", "box6a_ordinary_dividends": "box_6a", "box6b_qualified_dividends": "box_6b",
    "box7_royalties": "box_7", "box8_net_st_cap_gain": "box_8", "box9a_net_lt_cap_gain": "box_9a",
}


def build(case: str) -> dict:
    inp = json.loads((BENCH / case / "input.json").read_text())
    k1s = [f["data"] for f in inp["forms"] if f["node_type"] == "k1_partnership"]
    assert len(k1s) == 1, f"{case}: expected one K-1, got {len(k1s)}"
    k1 = k1s[0]
    unknown = set(k1) - set(FIELD_TO_BOX) - {"partnership_name", "partnership_ein"}
    assert not unknown, f"{case}: add FIELD_TO_BOX entries for {unknown}"

    doc = yaml.safe_load((OTD_SPEC / "proof" / "proof-emitted.otd.yaml").read_text())
    meta = doc["otd"]
    meta["document_id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"drivkraft-tax/bench/{case}"))
    meta["created"] = "2026-09-25T00:00:00Z"
    meta["producer"] = {"name": "Drivkraft Tax benchmark fixture", "version": "1"}

    body = doc["body"]
    body["part_i"]["item_a"]["value"] = "XX-XXX" + k1["partnership_ein"][-4:]
    body["part_i"]["item_b"]["value"] = k1["partnership_name"]
    body["part_ii"]["item_f"]["value"] = "Synthetic Partner (OpenTax benchmark " + case[:2] + ")"
    # No payment obligations or built-in gain on this K-1, so no statements are required.
    body["part_ii"]["item_k3"]["value"] = False
    body["part_ii"]["item_m"]["value"] = False
    body["part_ii"]["item_m"].pop("statement", None)

    for key, node in body["part_iii"].items():
        if node.get("type") == "coded":
            node["entries"] = []
        elif node.get("type") == "scalar":
            node["value"] = False if key in ("box_22", "box_23") else None
    for f, box in FIELD_TO_BOX.items():
        if f in k1:
            body["part_iii"][box]["value"] = k1[f]
    return doc


def main() -> None:
    for case, name in CASES.items():
        out = FIXTURES / name
        header = (f"# Synthetic OTD K-1 built from OpenTax benchmark {case} by build_bench_fixtures.py.\n"
                  "# Regenerate rather than hand-edit.\n")
        out.write_text(header + yaml.safe_dump(copy.deepcopy(build(case)), sort_keys=False, allow_unicode=True))
        print(f"wrote {out.relative_to(FIXTURES.parent.parent.parent)}")


if __name__ == "__main__":
    main()
