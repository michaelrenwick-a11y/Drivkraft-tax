"""K-1 documents: intake, read, evidence, validate, bridge, edit, acknowledge, approve."""
from __future__ import annotations

import json
import threading
from typing import Any

from .. import intake, k1doc, store
from ..bridge import otd, translator
from ..errors import ToolFailure, not_found, with_hint
from ..samples import SAMPLES
from . import tool
from .cases import require_case

ACK_REQUIRED = {"calculation_incomplete"}
MAX_REASON = 500


# ── Helpers ───────────────────────────────────────────────────────────────

def require_doc(doc_id: str, *, writable: bool = False) -> dict:
    doc = store.get_document(doc_id)
    if doc is None:
        raise not_found("document", doc_id, "Call list_documents(case_id) to see the document ids.")
    if writable:
        require_case(doc["case_id"], writable=True)
        if doc["status"] == "extracting":
            raise ToolFailure("still_extracting", "This K-1 is still being extracted",
                              "Wait for intake to finish (read_k1 shows the stages).", status=409)
        if doc["status"] == "failed":
            raise ToolFailure("extraction_failed", "Extraction failed for this K-1, so there's nothing to edit",
                              "Intake the sample again with intake_k1.", status=409)
    return doc


def _dir(doc: dict):
    return store.doc_dir(doc["case_id"], doc["id"])


def _bridge(doc: dict) -> dict | None:
    return k1doc.read_json(_dir(doc) / "bridge.json")


def _evidence(doc: dict) -> dict | None:
    return k1doc.read_json(_dir(doc) / "evidence.json")


def ack_key(flag: dict) -> str:
    return f"{flag['code']}@{flag.get('path') or ''}"


def _pending_acks(doc: dict, bridge: dict | None) -> list[dict]:
    acked = doc.get("acknowledged") or {}
    return [f for f in (bridge or {}).get("flags", []) if f["code"] in ACK_REQUIRED and ack_key(f) not in acked]


def _partnership(bridge: dict | None) -> str | None:
    item = ((bridge or {}).get("opentax") or {}).get("item") or {}
    if item.get("partnership_name"):
        return item["partnership_name"]
    for e in (bridge or {}).get("ledger", []):
        if e["path"] == "part_i.item_b" and isinstance(e.get("value"), str):
            return translator._first_line(e["value"])
    return None


def source(doc: dict, path: str, label: str | None = None) -> dict:
    who = doc.get("label") or doc["id"]
    try:
        lbl = k1doc.box_label(path)
    except ToolFailure:
        lbl = path
    return {"type": "k1_box", "ref": f"k1://{doc['id']}/box/{path}", "label": f"{label or lbl} · {who}"}


def doc_out(doc: dict) -> dict:
    """Compact document summary used in lists."""
    bridge = _bridge(doc)
    flags = (bridge or {}).get("flags", [])
    out = {
        "id": doc["id"], "case_id": doc["case_id"], "kind": doc["kind"], "label": doc["label"],
        "status": doc["status"], "source_kind": doc["source_kind"], "sample": doc["sample"],
        "has_pdf": (_dir(doc) / "source.pdf").exists(),
        "bridge_status": (bridge or {}).get("status"),
        "calculation_incomplete": (bridge or {}).get("calculation_incomplete", False),
        "errors": len((bridge or {}).get("errors", [])),
        "flags": {"total": len(flags), "to_acknowledge": len(_pending_acks(doc, bridge))},
        "edits": len(store.list_edits(doc["id"])),
        "approved_at": doc["approved_at"], "updated": doc["updated"],
    }
    if doc["status"] in ("extracting", "failed") or doc.get("progress"):
        out["progress"] = doc.get("progress")
    return out


def refresh(doc_id: str) -> dict:
    """Re-apply edits, re-validate and re-bridge; store bridge.json and the review status."""
    doc = store.get_document(doc_id)
    ddir = _dir(doc)
    original = k1doc.load_otd(ddir / "original.otd.yaml")
    edits = store.list_edits(doc_id)
    current = k1doc.apply_edits(original, edits) if edits else original
    k1doc.dump_otd(current, ddir / "current.otd.yaml")
    result = translator.bridge_k1(ddir / "current.otd.yaml").to_dict()
    k1doc.write_json(ddir / "bridge.json", result)
    status = "needs_review" if result["status"] == "ok" else "blocked"
    fields: dict[str, Any] = {"status": status, "label": _partnership(result) or doc["label"]}
    if doc["status"] == "approved":
        fields["approved_at"] = None
        (ddir / "approved.otd.yaml").unlink(missing_ok=True)
    store.update_document(doc_id, **fields)
    return result


# ── Listing and intake ────────────────────────────────────────────────────

@tool("R", "List documents", "GET", "/cases/{case_id}/documents")
def list_documents(case_id: str) -> dict:
    """List a case's source documents (K-1s) with review status, error and flag counts.

    Status: extracting → needs_review (bridged ok) or blocked (refused) → approved;
    failed means extraction failed. Read-only and free.
    """
    require_case(case_id)
    return {"documents": [doc_out(d) for d in store.list_documents(case_id)], "sources": []}


@tool("W", "Intake a K-1", "POST", "/cases/{case_id}/k1")
def intake_k1(case_id: str, sample: str = "synthetic-k1", wait: bool = True) -> dict:
    """Add a K-1 to a case from a bundled synthetic sample and extract it.

    sample: an id from list_k1_samples ('synthetic-k1' runs the 27-page PDF
    through the upstream k1-otd pipeline, about 10 s; 'proof-k1' and
    'oak-ventures' start from OTD). Only bundled synthetic samples are accepted.
    The result has the doc id, the named extraction stages and the bridge
    status. wait=false returns immediately and extraction continues in the
    background (poll read_k1). Writes to the case; no cost.
    """
    require_case(case_id, writable=True)
    s = SAMPLES.get(sample)
    if s is None:
        raise ToolFailure("unknown_sample", f"No bundled sample {sample!r}",
                          f"Use one of: {', '.join(SAMPLES)} (list_k1_samples describes them).")
    if not s.path.exists():
        raise ToolFailure("sample_missing", f"Sample file for {sample!r} is missing", "Run scripts/bootstrap.sh.")
    doc = {"id": store.new_id("k1"), "case_id": case_id, "kind": "k1", "sample": s.id, "source_kind": s.kind,
           "label": s.title, "status": "extracting", "progress": intake.initial_progress(s)}
    k1doc.write_json(store.doc_dir(case_id, doc["id"]) / "meta.json", {"sample": s.id})
    store.insert_document(doc)
    if wait:
        intake.run(doc, s, refresh)
    else:
        threading.Thread(target=intake.run, args=(doc, s, refresh), daemon=True).start()
    return {"document": doc_out(store.get_document(doc["id"])), "sources": []}


# ── Reading ───────────────────────────────────────────────────────────────

def _entry_out(doc: dict, e: dict, evidence: dict | None, edits: dict, flags: dict) -> dict:
    ev = k1doc.evidence_for(evidence, e["path"]) if evidence else None
    out = {
        "path": e["path"], "label": k1doc.box_label(e["path"]), "box": e["box"], "code": e.get("code"),
        "description": e.get("label"), "semantic_id": e.get("semantic_id"),
        "value": e.get("value"), "disposition": e["disposition"], "field": e.get("field"),
        "note": e.get("note"), "statement": e.get("statement"),
        "flags": flags.get(e["path"], []),
        "edited": e["path"] in edits,
        "evidence": None if not ev else {"page": ev["page"], "bbox": ev["bbox"], "text": ev.get("text"),
                                         "status": ev.get("status")},
    }
    if e["path"] in edits:
        out["original_value"] = edits[e["path"]]["original"]
        out["edit_reason"] = edits[e["path"]]["reason"]
    return out


def _edits_by_path(doc: dict) -> dict:
    by: dict[str, dict] = {}
    for e in store.list_edits(doc["id"]):
        if e["path"] not in by:
            by[e["path"]] = {"original": e["old_value"], "reason": e["reason"]}
        else:
            by[e["path"]]["reason"] = e["reason"]
    # An edit back to the original value isn't an edit any more.
    doc_current = k1doc.load_otd(_dir(doc) / "current.otd.yaml") if by else None
    for p in list(by):
        try:
            if doc_current is not None and k1doc.get_value(doc_current, p) == by[p]["original"]:
                by.pop(p)
        except ToolFailure:
            pass
    return by


@tool("R", "Read a K-1", "GET", "/docs/{doc_id}")
def read_k1(doc_id: str, detail: str = "compact") -> dict:
    """Summary of one K-1: partnership, review status, every box with a value
    and how the bridge disposed of it (mapped, collapsed, derived, unsupported,
    informational), plus errors and flags with fix hints.

    detail='full' also returns empty boxes, per-box PDF evidence (page + bbox),
    edits and acknowledgements (what the review screen uses). While extracting,
    shows the named intake stages. Read-only and free.
    """
    doc = require_doc(doc_id)
    out: dict[str, Any] = {"document": doc_out(doc)}
    bridge = _bridge(doc)
    if bridge is None:
        return {**out, "sources": []}
    evidence = _evidence(doc)
    edits = _edits_by_path(doc)
    flags_by_path: dict[str, list[str]] = {}
    for f in bridge["flags"] + bridge["errors"]:
        if f.get("path"):
            flags_by_path.setdefault(f["path"], []).append(f["code"])
    full = detail == "full"
    entries = [_entry_out(doc, e, evidence, edits, flags_by_path) for e in bridge["ledger"]
               if full or e.get("value") not in (None, False) or e["path"] in flags_by_path]
    acked = doc.get("acknowledged") or {}
    flags = [{**f, "ack_required": f["code"] in ACK_REQUIRED, "acknowledged": acked.get(ack_key(f))}
             for f in bridge["flags"]]
    out.update(
        bridge_status=bridge["status"],
        calculation_incomplete=bridge["calculation_incomplete"],
        summary=bridge["summary"],
        errors=bridge["errors"],
        flags=flags,
        entries=entries,
        opentax=bridge["opentax"],
        reconciled=all(r["ok"] for r in bridge["reconciliation"].get("fields", {}).values())
        and all(r["ok"] for r in bridge["reconciliation"].get("boxes", {}).values()),
        can_approve=bridge["status"] == "ok" and not _pending_acks(doc, bridge) and doc["status"] != "approved",
    )
    if full:
        out["edits"] = store.list_edits(doc_id)
        out["pages"] = (evidence or {}).get("pages")
        out["case"] = require_case(doc["case_id"])
    out["sources"] = [source(doc, e["path"]) for e in entries
                      if isinstance(e["value"], (int, float)) and not isinstance(e["value"], bool) and e["value"]][:40]
    return out


def _entries_at(bridge: dict, path: str) -> list[dict]:
    """Ledger entries at a path; a box path matches its codes and statement fields too."""
    exact = [e for e in bridge["ledger"] if e["path"] == path]
    if exact:
        return exact
    return [e for e in bridge["ledger"] if e["path"].startswith(path + ".") or e["path"].startswith(path + "[")]


@tool("R", "Get one K-1 box", "GET", "/docs/{doc_id}/box")
def get_k1_box(doc_id: str, box: str, code: str | None = None) -> dict:
    """One box (or one code within a coded box) of a K-1: value, OTD semantic id,
    disposition, the OpenTax field it feeds, any attached statement, flags, and
    the PDF evidence reference.

    box accepts '1', '6a', '20' (with code 'Z'), '11A', 'B' / 'K1' for Part I–II
    items, or a full OTD path like part_iii.box_20.Z.statement.qbi. Read-only and free.
    """
    doc = require_doc(doc_id)
    bridge = _bridge(doc)
    if bridge is None:
        raise ToolFailure("not_ready", "This K-1 hasn't been bridged yet", "Wait for intake to finish.", status=409)
    path = k1doc.normalize_box(box, code)
    k1doc.parse_path(path)
    evidence = _evidence(doc)
    edits = _edits_by_path(doc)
    flags_by_path: dict[str, list[str]] = {}
    for f in bridge["flags"] + bridge["errors"]:
        if f.get("path"):
            flags_by_path.setdefault(f["path"], []).append(f["code"])
    entries = [_entry_out(doc, e, evidence, edits, flags_by_path) for e in _entries_at(bridge, path)]
    if not entries:
        return {"path": path, "label": k1doc.box_label(path), "present": False, "entries": [],
                "note": "Not on this K-1 (absent from the OTD document).", "sources": []}
    issues = [with_hint(f) if "fix_hint" not in f else f for f in bridge["flags"] + bridge["errors"]
              if (f.get("path") or "").startswith(path)]
    return {"path": path, "label": k1doc.box_label(path), "present": True, "entries": entries, "issues": issues,
            "sources": [source(doc, e["path"]) for e in entries]}


@tool("R", "Get PDF evidence for a box", "GET", "/docs/{doc_id}/evidence")
def get_evidence(doc_id: str, box: str, code: str | None = None) -> dict:
    """Where a K-1 box was read on the source PDF: page number, bounding box
    (PDF points, top-left origin), the text the extractor read, and a page
    image URL for highlighting.

    Only PDF intakes have evidence; OTD samples report available=false.
    Statement values point at their face-page entry. Read-only and free.
    """
    doc = require_doc(doc_id)
    path = k1doc.normalize_box(box, code)
    k1doc.parse_path(path)
    evidence = _evidence(doc)
    if not evidence:
        return {"path": path, "available": False,
                "reason": "This K-1 came in as an OTD document, so there's no PDF to point at.", "sources": []}
    ev = k1doc.evidence_for(evidence, path)
    if not ev or not ev.get("page"):
        return {"path": path, "available": False,
                "reason": "The extractor recorded no location for this box (it may be absent from the face).",
                "sources": []}
    sizes = (evidence.get("pages") or {}).get("sizes") or []
    page_size = sizes[ev["page"] - 1] if ev["page"] - 1 < len(sizes) else None
    return {"path": path, "label": k1doc.box_label(path), "available": True, "page": ev["page"],
            "bbox": ev["bbox"], "text": ev.get("text"), "status": ev.get("status"), "page_size": page_size,
            "coordinate_frame": evidence["coordinate_frame"],
            "image_url": f"/api/docs/{doc_id}/pages/{ev['page']}.png",
            "sources": [source(doc, path)]}


@tool("R", "Validate OTD", "GET", "/docs/{doc_id}/validate")
def validate_otd(doc_id: str) -> dict:
    """Run the upstream OTD validator on the K-1's current version (with edits).

    Returns pass/fail, errors located to OTD paths, warnings, and the paths the
    extractor marked for human review. Read-only and free; takes about a second.
    """
    doc = require_doc(doc_id)
    path = _dir(doc) / "current.otd.yaml"
    if not path.exists():
        raise ToolFailure("not_ready", "This K-1 has no OTD document yet", "Wait for intake to finish.", status=409)
    v = otd.validate(path)
    if v.validator_error:
        raise ToolFailure("validator_error", f"OTD validator could not run: {v.validator_error}")
    unverified = [p.removeprefix("body.") for p in v.unverified_paths]
    return {"passes": v.passes,
            "errors": [{"message": m, "path": translator._located(m)} for m in v.errors],
            "warnings": v.warnings, "unverified_paths": unverified,
            "sources": [source(doc, p) for p in unverified]}


@tool("R", "Bridge a K-1 to OpenTax", "GET", "/docs/{doc_id}/bridge")
def bridge_k1(doc_id: str, include_ledger: bool = False) -> dict:
    """The OTD → OpenTax bridge result for a K-1: status ok/refused, the exact
    k1_partnership item OpenTax receives, refusal errors, reviewer flags (each
    with a fix_hint), the disposition summary and the reconciliation.

    Use this to answer "what on this K-1 isn't in the calculation?": every
    calculation_incomplete flag names a box whose amount OpenTax can't take.
    include_ledger=true adds all ~70 ledger entries. Read-only and free.
    """
    doc = require_doc(doc_id)
    bridge = _bridge(doc)
    if bridge is None:
        raise ToolFailure("not_ready", "This K-1 hasn't been bridged yet", "Wait for intake to finish.", status=409)
    out = dict(bridge)
    if not include_ledger:
        out.pop("ledger")
        out["not_in_calculation"] = [
            {"path": e["path"], "label": k1doc.box_label(e["path"]), "description": e.get("label"),
             "value": e["value"], "note": e.get("note")}
            for e in bridge["ledger"] if e["disposition"] == "unsupported" and e.get("value") not in (None, False)]
    paths = [f["path"] for f in bridge["flags"] + bridge["errors"] if f.get("path")]
    out["sources"] = [source(doc, p) for p in dict.fromkeys(paths)]
    return out


# ── Review actions ────────────────────────────────────────────────────────

@tool("W", "Edit a K-1 value", "POST", "/docs/{doc_id}/edits")
def edit_k1_value(doc_id: str, path: str, value: Any, reason: str) -> dict:
    """Correct one value on a K-1. The extracted original is kept, the reason is
    required, and the K-1 re-validates and re-bridges immediately.

    path is an OTD path (part_iii.box_1, part_iii.box_11.A,
    part_iii.box_20.Z.statement.qbi, part_i.item_b). value is the corrected
    amount ('1,250' and '(300)' are understood), text, true/false, or null to
    clear it. Editing an approved K-1 returns it to review. Writes; no cost.
    """
    doc = require_doc(doc_id, writable=True)
    reason = (reason or "").strip()
    if not reason:
        raise ToolFailure("reason_required", "Every edit needs a reason",
                          "Say why, e.g. \"PDF shows 556,100; extractor dropped a digit\".")
    if len(reason) > MAX_REASON:
        raise ToolFailure("reason_too_long", f"Reasons are limited to {MAX_REASON} characters", "Shorten the reason.")
    ddir = _dir(doc)
    current = k1doc.load_otd(ddir / "current.otd.yaml")
    path = path.strip()
    old = k1doc.get_value(current, path)
    new = k1doc.coerce(value, old)
    if new == old and not _is_unverified(current, path):
        raise ToolFailure("no_change", f"{k1doc.box_label(path)} is already {old!r}",
                          "Nothing to save. To verify an unverified value, edit it; otherwise leave it.")
    edit = store.insert_edit(doc_id, path, old, new, reason)
    with open(ddir / "edits.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(edit, default=str) + "\n")
    # Acknowledgements on the edited path no longer apply.
    acked = {k: v for k, v in (doc.get("acknowledged") or {}).items() if not k.split("@", 1)[1].startswith(path)}
    store.update_document(doc_id, acknowledged=acked)
    result = refresh(doc_id)
    doc = store.get_document(doc_id)
    return {"edit": edit, "document": doc_out(doc), "bridge_status": result["status"],
            "errors": result["errors"], "flags_at_path": [f for f in result["flags"] if (f.get("path") or "").startswith(path)],
            "sources": [source(doc, path)]}


def _is_unverified(doc: dict, path: str) -> bool:
    try:
        container, k = k1doc._locate(doc, path)
    except ToolFailure:
        return False
    return k in ("value", "checked") and any(str(m).startswith("_unverified") for m in container)


@tool("W", "Acknowledge a flag", "POST", "/docs/{doc_id}/acknowledgements")
def acknowledge_flag(doc_id: str, path: str, code: str = "calculation_incomplete", note: str = "",
                     undo: bool = False) -> dict:
    """Record that a reviewer has seen a bridge flag (for example, Box 13 A isn't
    in the calculation). Every calculation_incomplete flag must be acknowledged
    before approve_k1. undo=true removes the acknowledgement. Writes; no cost.
    """
    doc = require_doc(doc_id, writable=True)
    bridge = _bridge(doc) or {}
    path = path.strip()
    flag = next((f for f in bridge.get("flags", []) if f["code"] == code and f.get("path") == path), None)
    if flag is None:
        raise ToolFailure("flag_not_found", f"No {code} flag at {path}",
                          "read_k1 lists the flags; pass the flag's path and code exactly.", status=404)
    acked = dict(doc.get("acknowledged") or {})
    key = ack_key(flag)
    if undo:
        acked.pop(key, None)
    else:
        acked[key] = {"note": note.strip()[:MAX_REASON], "at": store.now()}
    store.update_document(doc_id, acknowledged=acked)
    doc = store.get_document(doc_id)
    return {"document": doc_out(doc), "acknowledged": not undo,
            "remaining": [{"path": f["path"], "message": f["message"]} for f in _pending_acks(doc, bridge)],
            "sources": [source(doc, path)]}


@tool("W", "Approve a K-1", "POST", "/docs/{doc_id}/approve")
def approve_k1(doc_id: str) -> dict:
    """Approve a reviewed K-1 so the return calculation uses it.

    Requires bridge status ok (no refusal errors) and every
    calculation_incomplete flag acknowledged (acknowledge_flag). Freezes the
    current version as approved.otd.yaml. Writes; no cost.
    """
    doc = require_doc(doc_id, writable=True)
    bridge = _bridge(doc) or {}
    if doc["status"] == "approved":
        return {"document": doc_out(doc), "already_approved": True, "sources": []}
    if bridge.get("status") != "ok":
        errs = bridge.get("errors", [])
        raise ToolFailure("refused_by_bridge", f"{len(errs)} error(s) block approval",
                          "Fix each error at its OTD path with edit_k1_value; the first is: "
                          + (errs[0]["message"] if errs else "unknown"), status=409,
                          detail=[{"path": e.get("path"), "code": e["code"]} for e in errs])
    pending = _pending_acks(doc, bridge)
    if pending:
        raise ToolFailure("unacknowledged_flags", f"{len(pending)} flag(s) still need acknowledging",
                          "Call acknowledge_flag for each path listed in detail, then approve again.", status=409,
                          detail=[{"path": f["path"], "message": f["message"]} for f in pending])
    ddir = _dir(doc)
    (ddir / "approved.otd.yaml").write_bytes((ddir / "current.otd.yaml").read_bytes())
    store.update_document(doc_id, status="approved", approved_at=store.now())
    doc = store.get_document(doc_id)
    return {"document": doc_out(doc), "already_approved": False, "sources": []}
