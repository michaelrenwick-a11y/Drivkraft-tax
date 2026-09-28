"""Source documents dropped on a case (Phase 11): add, list, remove.

A dropped PDF is read from its text layer (server/sourcedocs.py). W-2s, 1099s,
the 1098 and the client organizer become the case's inputs straight away; a
K-1 becomes an OTD document that goes through the usual review. The bundled
synthetic K-1 package is recognized by its hash and runs the upstream k1-otd
extraction instead.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import shutil
import tempfile
import threading
from pathlib import Path

import yaml

from .. import intake, k1doc, sourcedocs, store
from ..errors import ToolFailure, not_found
from ..samples import SAMPLES, Sample
from . import tool
from .cases import require_case
from .k1 import doc_out, intake_k1, refresh

PARSE_STAGE = {"id": "parse", "label": "Reading the K-1 PDF's text layer", "status": "done"}


def _pdf_path(s: dict) -> Path:
    return store.case_dir(s["case_id"]) / "sources" / f"{s['id']}.pdf"


def _sample_sha(sample_id: str) -> str | None:
    s = SAMPLES.get(sample_id)
    return hashlib.sha256(s.path.read_bytes()).hexdigest() if s and s.path.exists() else None


def source_out(s: dict) -> dict:
    inputs = [{"id": i["id"], "node_type": i["node_type"], "label": i["label"]}
              for i in store.list_inputs(s["case_id"]) if i.get("source_id") == s["id"]]
    out = {"id": s["id"], "case_id": s["case_id"], "filename": s["filename"], "form": s["form"],
           "form_title": sourcedocs.FORM_TITLES.get(s["form"] or "", "Unknown form"), "label": s["label"],
           "status": s["status"], "fields": s["fields"], "warnings": s["warnings"], "error": s["error"],
           "inputs": inputs, "doc_id": s["doc_id"], "has_pdf": _pdf_path(s).exists(), "created": s["created"]}
    if s["doc_id"]:
        doc = store.get_document(s["doc_id"])
        out["document"] = doc_out(doc) if doc else None
    return out


def require_source(source_id: str, *, writable: bool = False) -> dict:
    s = store.get_source(source_id)
    if s is None:
        raise not_found("source document", source_id, "Call list_source_documents(case_id) to see the ids.")
    require_case(s["case_id"], writable=writable)
    return s


def _decode(pdf_base64: str) -> bytes:
    try:
        raw = base64.b64decode(pdf_base64 or "", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ToolFailure("bad_file", "The file isn't valid base64", "Send the PDF's bytes base64-encoded.") from exc
    if not raw:
        raise ToolFailure("bad_file", "The file is empty", "Drop a PDF.")
    if len(raw) > sourcedocs.MAX_BYTES:
        raise ToolFailure("file_too_large", f"PDFs are limited to {sourcedocs.MAX_BYTES // (1024 * 1024)} MB",
                          "Drop one form per file.", status=413)
    if not raw.startswith(b"%PDF"):
        raise ToolFailure("not_a_pdf", "That file isn't a PDF",
                          "Drop the PDF of a W-2, 1099, 1098, K-1 or client organizer.", status=415)
    return raw


def _start_k1(case_id: str, source: dict, parsed: sourcedocs.Parsed, pdf: Path, wait: bool) -> str:
    """Parsed K-1 → OTD document in a new K-1 doc, then validate + bridge via the normal intake."""
    doc_id = store.new_id("k1")
    ddir = store.doc_dir(case_id, doc_id)
    ddir.mkdir(parents=True, exist_ok=True)
    otd_path = ddir / "parsed.otd.yaml"
    otd_path.write_text("# Built by server/sourcedocs.py from the dropped PDF's text layer.\n"
                        + yaml.safe_dump(sourcedocs.otd_from_k1(parsed.k1, store.now()), sort_keys=False,
                                         allow_unicode=True))
    shutil.copyfile(pdf, ddir / "source.pdf")
    # Box locations from the text layer, in the same shape as upstream evidence, so review shows highlights.
    k1doc.write_json(ddir / "evidence.json", {"coordinate_frame": "pdf_top_left_origin_points",
                                              "pages": k1doc.page_info(ddir / "source.pdf"),
                                              "fields": parsed.k1.get("evidence") or {}})
    sample = Sample("upload", "otd", parsed.label, source["filename"], otd_path)
    progress = intake.initial_progress(sample)
    progress["stages"].insert(0, dict(PARSE_STAGE))
    doc = {"id": doc_id, "case_id": case_id, "kind": "k1", "sample": None, "source_kind": "pdf",
           "label": parsed.label, "status": "extracting", "progress": progress}
    k1doc.write_json(ddir / "meta.json", {"source_id": source["id"], "filename": source["filename"]})
    store.insert_document(doc)
    if wait:
        intake.run(doc, sample, refresh)
    else:
        threading.Thread(target=intake.run, args=(doc, sample, refresh), daemon=True).start()
    return doc_id


@tool("W", "Add a source document", "POST", "/cases/{case_id}/sources")
def add_source_document(case_id: str, pdf_base64: str, filename: str = "document.pdf", wait: bool = True) -> dict:
    """Add a synthetic source document (PDF, base64) to a case: W-2, 1099-INT,
    1099-DIV/1099-B, 1098, Schedule K-1 (1065) or the client organizer.

    It's read from the PDF's text layer. W-2s, 1099s, the 1098 and the organizer
    become return inputs right away (each tagged with this document, and removed
    with it). A K-1 becomes an OTD document that goes through review and approval
    like any other. Only synthetic documents are accepted (SYNTHETIC watermark or
    'Fictional document' footer); anything else comes back refused with the reason
    and nothing is stored. Writes to the case; no cost.
    """
    require_case(case_id, writable=True)
    filename = (Path(filename or "document.pdf").name or "document.pdf")[:120]
    raw = _decode(pdf_base64)
    sha = hashlib.sha256(raw).hexdigest()
    dup = next((s for s in store.list_sources(case_id) if s["sha256"] == sha and s["status"] != "refused"), None)
    if dup:
        raise ToolFailure("duplicate", f"{filename} is already on this case ({dup['label'] or dup['filename']})",
                          "Remove the existing copy first if you want to add it again.", status=409)
    sid = store.new_id("src")
    base = {"id": sid, "case_id": case_id, "filename": filename, "sha256": sha}

    if sha == _sample_sha("synthetic-k1"):        # the bundled package: run the upstream extractor
        out = intake_k1(case_id, "synthetic-k1", wait)
        store.insert_source({**base, "form": "k1-1065", "label": out["document"]["label"], "status": "k1",
                             "doc_id": out["document"]["id"],
                             "warnings": ["Recognized the bundled synthetic K-1 package, so it ran the upstream "
                                          "k1-otd extraction (with box-level PDF evidence)."]})
        return {"source": source_out(store.get_source(sid)), "sources": []}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_pdf = Path(tmp) / "in.pdf"
        tmp_pdf.write_bytes(raw)
        try:
            parsed = sourcedocs.parse(tmp_pdf)
        except sourcedocs.Refused as exc:
            store.insert_source({**base, "status": "refused",
                                 "error": {"code": exc.code, "message": exc.message, "fix_hint": exc.fix_hint}})
            return {"source": source_out(store.get_source(sid)), "refused": True, "sources": []}
        pdf = _pdf_path(base)
        pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tmp_pdf, pdf)

    warnings = list(parsed.warnings)
    case = store.get_case(case_id)
    start = next((d for n, d, _ in parsed.inputs if n == "start"), None)
    if start:
        fs = start["general"].get("filing_status")
        if fs and fs != case["filing_status"]:
            warnings.insert(0, f"The organizer says {fs.upper()}; the case was created as {case['filing_status'].upper()}. "
                               "The return uses the organizer's filing status.")
        others = [i for i in store.list_inputs(case_id) if i["node_type"] == "start"]
        if others:
            warnings.insert(0, "This case already has filing information; the first one entered is used. "
                               "Remove the older organizer to use this one.")
    store.insert_source({**base, "form": parsed.form, "label": parsed.label, "status": "added" if parsed.k1 is None else "k1",
                         "fields": parsed.fields, "warnings": warnings})
    if parsed.k1 is not None:
        doc_id = _start_k1(case_id, {**base}, parsed, pdf, wait)
        with store.connect() as db:
            db.execute("UPDATE source_docs SET doc_id = ? WHERE id = ?", (doc_id, sid))
    else:
        for node, data, label in parsed.inputs:
            store.insert_input(case_id, node, data, label, source_id=sid)
    return {"source": source_out(store.get_source(sid)), "sources": [
        {"type": "source_document", "ref": f"source://{sid}", "label": f"{parsed.label} · {filename}"}]}


@tool("R", "List source documents", "GET", "/cases/{case_id}/sources")
def list_source_documents(case_id: str) -> dict:
    """The source documents dropped on a case: what each was read as, the values
    read (box by box), the return inputs it made, warnings, and for K-1s the
    review status of the K-1 it became. Refused drops are listed with the reason.
    Read-only and free.
    """
    require_case(case_id)
    return {"source_documents": [source_out(s) for s in store.list_sources(case_id)], "sources": []}


@tool("W", "Remove a source document", "POST", "/sources/{source_id}/delete")
def remove_source_document(source_id: str) -> dict:
    """Remove a dropped source document and everything it added: its return inputs,
    or the K-1 it became (with that K-1's edits). Writes; no cost.
    """
    s = require_source(source_id, writable=True)
    if s["doc_id"]:
        doc = store.get_document(s["doc_id"])
        if doc and doc["status"] == "extracting":
            raise ToolFailure("still_extracting", "This K-1 is still being extracted",
                              "Wait for intake to finish, then remove it.", status=409)
        if doc:
            store.delete_document(doc["id"])
            shutil.rmtree(store.doc_dir(s["case_id"], doc["id"]), ignore_errors=True)
    _pdf_path(s).unlink(missing_ok=True)
    store.delete_source(source_id)
    return {"removed": source_id, "case_id": s["case_id"], "sources": []}
