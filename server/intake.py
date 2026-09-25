"""K-1 intake: bundled sample → OTD + artifacts, with named progress stages.

The PDF path runs upstream `run_demo.py` as-is (ground rule 4) into a fresh
run-<n> directory, and watches its per-stage logs to report progress
("Reading page text", "Matching Box 20 codes"…). The OTD path copies the
document in and goes straight to validation.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from . import k1doc, paths, store
from .samples import Sample

# Upstream stage ids (run_demo.py) → what the reviewer sees.
PDF_STAGES = [
    ("grammar-validation", "Loading the 2025 K-1 grammar"),
    ("pdf-text-extraction", "Reading page text"),
    ("template-fit", "Matching the K-1 face layout"),
    ("section-manifests", "Classifying pages and statements"),
    ("face-evidence", "Reading face boxes with highlights"),
    ("state-grid-attempt", "Checking state schedules"),
    ("line-item-details", "Matching statement line items"),
    ("evidence-projection", "Projecting evidence to OTD"),
    ("assembly", "Assembling the OTD document"),
    ("validation", "Validating against the taxonomy"),
    ("reconciliation", "Reconciling detail totals"),
]
OTD_STAGES = [("copy", "Loading the OTD document")]
BRIDGE_STAGE = ("bridge", "Bridging to OpenTax and building the ledger")
TIMEOUT_S = 300


def initial_progress(sample: Sample) -> dict:
    stages = (PDF_STAGES if sample.kind == "pdf" else OTD_STAGES) + [BRIDGE_STAGE]
    return {"started": store.now(), "finished": None, "error": None,
            "stages": [{"id": i, "label": label, "status": "pending"} for i, label in stages]}


def _set(progress: dict, stage_id: str, status: str, ms: float | None = None) -> None:
    for s in progress["stages"]:
        if s["id"] == stage_id:
            s["status"] = status
            if ms is not None:
                s["ms"] = round(ms)


def run(doc: dict, sample: Sample, on_bridge) -> None:
    """Run intake for `doc` (already inserted with status 'extracting'). Never raises."""
    ddir = store.doc_dir(doc["case_id"], doc["id"])
    progress = doc["progress"]
    try:
        if sample.kind == "pdf":
            _run_pdf(doc, sample, ddir, progress)
        else:
            _set(progress, "copy", "running")
            shutil.copyfile(sample.path, ddir / "original.otd.yaml")
            _set(progress, "copy", "done", 1)
        shutil.copyfile(ddir / "original.otd.yaml", ddir / "current.otd.yaml")
        _set(progress, "bridge", "running")
        store.update_document(doc["id"], progress=progress)
        t0 = time.monotonic()
        on_bridge(doc["id"])
        _set(progress, "bridge", "done", (time.monotonic() - t0) * 1000)
        progress["finished"] = store.now()
        store.update_document(doc["id"], progress=progress)
    except Exception as exc:  # surfaced to the reviewer as a failed stage, never a stack trace
        for s in progress["stages"]:
            if s["status"] == "running":
                s["status"] = "failed"
        progress["error"] = str(exc)[-1500:]
        progress["finished"] = store.now()
        store.update_document(doc["id"], status="failed", progress=progress)


def _run_pdf(doc: dict, sample: Sample, ddir: Path, progress: dict) -> None:
    shutil.copyfile(sample.path, ddir / "source.pdf")
    n = 1 + sum(1 for _ in (ddir / "artifacts").glob("run-*")) if (ddir / "artifacts").exists() else 1
    out, work = ddir / "artifacts" / f"run-{n}", ddir / "work" / f"run-{n}"
    out.parent.mkdir(parents=True, exist_ok=True)
    work.parent.mkdir(parents=True, exist_ok=True)
    runner = paths.OTD_SYNTHETIC / "run_demo.py"
    cmd = [str(paths.PYTHON), "-B", str(runner), "--pdf", str(ddir / "source.pdf"),
           "--out", str(out), "--work-dir", str(work), "--created", store.now()]
    log = open(ddir / f"intake-run-{n}.log", "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=paths.OTD_SPEC, stdout=log, stderr=subprocess.STDOUT)
    started, last = time.monotonic(), time.monotonic()
    done: set[str] = set()
    order = [s for s, _ in PDF_STAGES]
    _set(progress, order[0], "running")
    store.update_document(doc["id"], progress=progress)
    try:
        while True:
            finished = proc.poll() is not None
            for stage in order:
                if stage not in done and (work / "logs" / f"{stage}.log").exists():
                    done.add(stage)
                    now = time.monotonic()
                    _set(progress, stage, "done", (now - last) * 1000)
                    last = now
                    nxt = next((s for s in order if s not in done), None)
                    if nxt:
                        _set(progress, nxt, "running")
                    store.update_document(doc["id"], progress=progress)
            if finished:
                break
            if time.monotonic() - started > TIMEOUT_S:
                proc.kill()
                raise RuntimeError(f"extraction timed out after {TIMEOUT_S}s")
            time.sleep(0.15)
    finally:
        log.close()
    if proc.returncode:
        tail = (ddir / f"intake-run-{n}.log").read_text(encoding="utf-8", errors="replace")[-1200:]
        raise RuntimeError(f"extraction failed (exit {proc.returncode}): {tail}")
    for stage in order:
        if stage not in done:
            _set(progress, stage, "done")
    shutil.copyfile(out / "output.otd.yaml", ddir / "original.otd.yaml")
    face = k1doc.read_json(work / "evidence" / "face-page.json")
    if face:
        evidence = k1doc.build_evidence(face)
        info = k1doc.page_info(ddir / "source.pdf")
        evidence["pages"] = info
        k1doc.write_json(ddir / "evidence.json", evidence)
