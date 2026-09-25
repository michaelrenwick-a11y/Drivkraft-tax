"""Read-only reference cases, seeded on first start (idempotent).

- `ref-k1s`: the three bundled K-1s (proof, synthetic PDF, benchmark 82 twin),
  already approved, so list_cases / read_k1 / bridge_k1 have something to show.
  The synthetic K-1 uses upstream's committed demonstration output and face
  evidence, so it has PDF highlights without running extraction.
- `ref-bench-82`: OpenTax benchmark 82 (W-2, 1099-INT/DIV/R) with its K-1
  swapped for the OTD twin. calculate_return reproduces the benchmark.
"""
from __future__ import annotations

import json
import shutil

from . import k1doc, paths, store
from .bridge import translator
from .samples import SAMPLES
from .tools import k1 as k1tools

BENCH_82 = paths.OPENTAX_BENCH / "82-single-w2-k1-1099r-1099int-1099div"


def _seed_doc(case_id: str, doc_id: str, sample_id: str) -> None:
    s = SAMPLES[sample_id]
    ddir = store.doc_dir(case_id, doc_id)
    ddir.mkdir(parents=True, exist_ok=True)
    if s.kind == "pdf":
        demo = paths.OTD_SYNTHETIC / "demonstration"
        shutil.copyfile(s.path, ddir / "source.pdf")
        shutil.copytree(demo, ddir / "artifacts" / "run-1", dirs_exist_ok=True)
        shutil.copyfile(demo / "output.otd.yaml", ddir / "original.otd.yaml")
        face = k1doc.read_json(paths.OTD_SYNTHETIC / "evidence" / "face-page.json")
        evidence = k1doc.build_evidence(face)
        evidence["pages"] = k1doc.page_info(ddir / "source.pdf")
        k1doc.write_json(ddir / "evidence.json", evidence)
    else:
        shutil.copyfile(s.path, ddir / "original.otd.yaml")
    store.insert_document({"id": doc_id, "case_id": case_id, "kind": "k1", "sample": s.id, "source_kind": s.kind,
                           "label": s.title, "status": "extracting"})
    result = k1tools.refresh(doc_id)
    acked = {k1tools.ack_key(f): {"note": "Seeded reference K-1", "at": store.now()}
             for f in result["flags"] if f["code"] in k1tools.ACK_REQUIRED}
    shutil.copyfile(ddir / "current.otd.yaml", ddir / "approved.otd.yaml")
    store.update_document(doc_id, status="approved", approved_at=store.now(), acknowledged=acked)


def seed() -> None:
    store.root()
    if not paths.OTD_SPEC.exists():
        return   # bootstrap hasn't run; the server still starts, lists nothing
    if store.get_case("ref-k1s") is None:
        store.insert_case({"id": "ref-k1s", "name": "Reference K-1s", "tax_year": 2025, "filing_status": "single",
                           "read_only": 1, "created": store.now(),
                           "description": "The three bundled synthetic K-1s, bridged and approved. Read-only."})
        for doc_id, sample in (("ref-synthetic", "synthetic-k1"), ("ref-proof", "proof-k1"),
                               ("ref-oak", "oak-ventures")):
            _seed_doc("ref-k1s", doc_id, sample)
    if store.get_case("ref-bench-82") is None and BENCH_82.exists():
        case = json.loads((BENCH_82 / "input.json").read_text())
        store.insert_case({"id": "ref-bench-82", "name": "Benchmark 82 · single filer", "tax_year": case["year"],
                           "filing_status": "single", "read_only": 1, "created": store.now(),
                           "description": "OpenTax benchmark 82 with its K-1 replaced by the OTD twin. "
                                          "calculate_return should match the benchmark within $5."})
        node = translator.mapping()["meta"]["opentax_node"]
        for f in case["forms"]:
            if f["node_type"] != node:
                store.insert_input("ref-bench-82", f["node_type"], f["data"], label="benchmark 82")
        _seed_doc("ref-bench-82", "ref-bench-82-oak", "oak-ventures")
