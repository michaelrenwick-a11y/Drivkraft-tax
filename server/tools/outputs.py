"""Outputs (Phase 7): the Excel workpaper round-trip and the PDF review packet.

    export_workpaper → edit the yellow cells in Excel → import_workpaper (a changeset:
    one item per changed cell, conflicts marked) → apply_changeset(accept_ids)

Applying runs edit_k1_value for each accepted K-1 cell, with the cell reference in
the reason, so the K-1's history shows exactly where a change came from.
"""
from __future__ import annotations

import base64
import binascii
import re

from .. import k1doc, packet, snapshot, store, workpaper
from ..packet import money
from ..errors import ToolFailure, not_found
from . import tool
from .cases import require_case
from .k1 import MAX_REASON, edit_k1_value, source


def _url(o: dict) -> str:
    return f"/api/outputs/{o['id']}/download"


def filename(o: dict, case: dict | None = None) -> str:
    case = case or store.get_case(o["case_id"]) or {"name": o["case_id"]}
    slug = re.sub(r"[^A-Za-z0-9]+", "-", case["name"]).strip("-").lower() or "case"
    return f"{slug}-{'workpaper' if o['kind'] == 'workpaper' else 'review-packet'}-v{o['version']}." + \
        ("xlsx" if o["kind"] == "workpaper" else "pdf")


def _output_out(o: dict) -> dict:
    path = store.case_dir(o["case_id"]) / o["file"]
    return {"id": o["id"], "case_id": o["case_id"], "kind": o["kind"], "version": o["version"],
            "created": o["created"], "filename": filename(o), "url": _url(o), "path": str(path),
            "bytes": path.stat().st_size if path.exists() else None, **o["meta"]}


def _wp_source(o: dict) -> dict:
    return {"type": "workpaper", "ref": f"workpaper://{o['case_id']}/v{o['version']}",
            "label": f"Workpaper v{o['version']}"}


def require_output(output_id: str) -> dict:
    o = store.get_output(output_id)
    if o is None:
        raise not_found("output", output_id, "Call list_outputs(case_id) to see exported files.")
    return o


# ── Workpaper ─────────────────────────────────────────────────────────────

@tool("W", "Export a workpaper", "POST", "/cases/{case_id}/workpapers")
def export_workpaper(case_id: str) -> dict:
    """Export the case to an Excel workpaper: one sheet per K-1 (every box, its
    treatment, flags and original value), the 1040, the checklist, saved scenarios,
    meeting notes, research and approved follow-ups.

    Editable cells are yellow: a K-1's Value column and the checklist Status. Each
    export is a new version (v1, v2…) and records every editable cell's value, so
    import_workpaper can tell edits from changes made in the app since. Doesn't
    change the case; no cost. Returns a download url and the file's local path.
    """
    case = require_case(case_id)
    snap = snapshot.gather(case_id)
    out_id = store.new_id("wp")
    o = store.insert_output({"id": out_id, "case_id": case_id, "kind": "workpaper", "file": ""})
    data, meta = workpaper.build(snap, out_id, o["version"])
    rel = f"workpapers/case-v{o['version']}.xlsx"
    path = store.case_dir(case_id) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    k1_cells = sum(len(k["entries"]) for k in snap["k1s"])
    store.update_output(out_id, rel, {**meta, "k1_cells": k1_cells, "read_only_case": case["read_only"]})
    o = store.get_output(out_id)
    return {"workpaper": _output_out(o),
            "note": "Reference cases are read-only: this workbook can be read but not imported." if case["read_only"] else
                    "Edit the yellow cells, save as .xlsx, then import_workpaper.",
            "sources": [_wp_source(o)]}


def _k1_current(doc: dict) -> dict:
    return k1doc.load_otd(store.doc_dir(doc["case_id"], doc["id"]) / "current.otd.yaml")


def _diff(case: dict, parsed: dict) -> tuple[list[dict], list[str]]:
    items, warnings = [], []
    if parsed["missing_sheets"]:
        warnings.append("Sheet(s) not found, so their cells were skipped: " + ", ".join(parsed["missing_sheets"])
                        + ". Renamed sheets aren't read.")
    docs, currents = {}, {}
    checklist = {c["id"]: c for c in store.list_checklist(case["id"])}
    missing_rows = 0
    for b in parsed["baseline"]:
        if b["sheet"] in parsed["missing_sheets"]:
            continue
        cell = parsed["cells"].get((b["sheet"], b["key"]))
        if cell is None:
            missing_rows += 1
            continue
        item = {"sheet": b["sheet"], "cell": cell["cell"], "kind": b["kind"], "baseline": b["value"]}
        if b["kind"] == "k1_value":
            doc = docs.get(b["doc_id"]) or store.get_document(b["doc_id"])
            docs[b["doc_id"]] = doc
            if doc is None:
                if cell["value"] is not None and not workpaper.same(cell["value"], b["value"]):
                    warnings.append(f"{b['sheet']}: the K-1 was removed from the case, so its edits were skipped.")
                continue
            try:
                new = workpaper.parse_k1(cell["value"], b["value"]) if cell["error"] is None else None
                invalid = cell["error"]
            except ToolFailure as exc:
                new, invalid = cell["value"], f"{exc.message}. {exc.fix_hint}"
            if invalid is None and workpaper.same(new, b["value"]):
                continue
            if doc["id"] not in currents:
                currents[doc["id"]] = _k1_current(doc) if doc["status"] not in ("extracting", "failed") else None
            try:
                current = k1doc.get_value(currents[doc["id"]], b["key"]) if currents[doc["id"]] is not None else None
            except ToolFailure:
                current = None
            src = source(doc, b["key"])
            item.update(doc_id=doc["id"], path=b["key"], label=src["label"], box=k1doc.box_label(b["key"]),
                        partnership=snapshot.display_name(doc["label"]), new=new if invalid is None else cell["value"],
                        current=current, returns_to_review=doc["status"] == "approved", ref=src["ref"])
        else:
            c = checklist.get(b["key"])
            raw = cell["value"]
            new = raw.strip().lower() if isinstance(raw, str) else raw
            invalid = cell["error"] or (None if new in ("open", "received") else f"{raw!r} isn't a status. Use open or received.")
            if invalid is None and new == b["value"]:
                continue
            if c is None:
                warnings.append(f"Checklist item {b['key']} was deleted from the case, so its change was skipped.")
                continue
            item.update(checklist_id=c["id"], label=c["item"], box="Checklist", partnership=None,
                        new=new, current=c["status"], returns_to_review=False, ref=None)
        if invalid is None and workpaper.same(item["new"], item["current"]):
            continue      # the case already has this value (changed in the app the same way)
        item["invalid"] = invalid
        item["conflict"] = invalid is None and not workpaper.same(item["current"], b["value"])
        item["status"] = "pending"
        items.append(item)
    if missing_rows:
        warnings.append(f"{missing_rows} row(s) were deleted from the workbook; deleting a row doesn't clear a value "
                        "(empty the Value cell instead).")
    items.sort(key=lambda i: (not i["conflict"], i["invalid"] is None, 0))
    for n, i in enumerate(items, 1):
        i["id"] = f"c{n}"
    return items, warnings


def _changeset_out(c: dict) -> dict:
    wp = store.get_output(c["workpaper_id"])
    items = c["items"]
    count = lambda pred: sum(1 for i in items if pred(i))
    return {**c, "workpaper": wp and {"id": wp["id"], "version": wp["version"], "created": wp["created"]},
            "latest_version": max((o["version"] for o in store.list_outputs(c["case_id"], "workpaper")), default=None),
            "counts": {"changes": len(items), "conflicts": count(lambda i: i["conflict"]),
                       "invalid": count(lambda i: i["invalid"]),
                       "applied": count(lambda i: i["status"] == "applied"),
                       "failed": count(lambda i: i["status"] == "failed"),
                       "rejected": count(lambda i: i["status"] == "rejected")}}


@tool("P", "Import a workpaper", "POST", "/cases/{case_id}/changesets")
def import_workpaper(case_id: str, xlsx_base64: str, filename: str | None = None) -> dict:
    """Read an edited workpaper back and list every changed cell as a changeset.
    Nothing changes until apply_changeset.

    xlsx_base64 is the .xlsx file, base64-encoded (5 MB max); it must be a workbook
    export_workpaper made for this case. Each item has the cell (e.g. 'K-1 Copperleaf'!C19),
    the box, the value at export (baseline), in the case now (current) and in the
    workbook (new). conflict=true means the case changed that value after the export;
    invalid explains a cell that can't be applied (text in an amount, a formula).
    Read-only reference cases can't be imported into. No cost.
    """
    case = require_case(case_id, writable=True)
    try:
        data = base64.b64decode(xlsx_base64.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ToolFailure("bad_file", "The file isn't valid base64", "Send the .xlsx bytes base64-encoded.",
                          status=422) from exc
    parsed = workpaper.read(data)
    head = parsed["head"]
    if head.get("case_id") != case_id:
        other = store.get_case(head.get("case_id") or "")
        raise ToolFailure("wrong_case", f"This workpaper belongs to {other['name'] if other else head.get('case_id')!r}",
                          "Import it on that case, or export this case's workpaper.", status=409)
    wp = store.get_output(head.get("workpaper_id") or "")
    if wp is None:
        raise ToolFailure("unknown_workpaper", "This workpaper's export isn't on record (the data may have been reset)",
                          "Export a fresh workpaper and make the edits in that one.", status=409)
    items, warnings = _diff(case, parsed)
    cs_id = store.new_id("cs")
    rel = store.case_dir(case_id) / "changesets" / f"{cs_id}.xlsx"
    rel.parent.mkdir(parents=True, exist_ok=True)
    rel.write_bytes(data)
    name = re.sub(r"[^\w .()-]", "", filename or "")[:120] or None
    c = store.insert_changeset({"id": cs_id, "case_id": case_id, "workpaper_id": wp["id"], "filename": name,
                                "items": items, "warnings": warnings})
    return {"changeset": _changeset_out(c), "href": f"/cases/{case_id}/outputs/changesets/{cs_id}",
            "sources": [_wp_source(wp)] + [{"type": "workpaper_cell", "ref": f"workpaper://{case_id}/v{wp['version']}"
                                            f"#{i['sheet']}!{i['cell']}", "label": f"{i['sheet']}!{i['cell']}"}
                                           for i in items[:20]]}


def require_changeset(changeset_id: str) -> dict:
    c = store.get_changeset(changeset_id)
    if c is None:
        raise not_found("changeset", changeset_id, "import_workpaper returns the changeset id.")
    return c


@tool("R", "Get a changeset", "GET", "/changesets/{changeset_id}")
def get_changeset(changeset_id: str) -> dict:
    """One imported workpaper's changed cells, with conflicts, invalid cells and (once
    applied) what happened to each. Read-only."""
    c = require_changeset(changeset_id)
    case = require_case(c["case_id"])
    return {"changeset": _changeset_out(c), "case": {"id": case["id"], "name": case["name"],
                                                     "read_only": case["read_only"]}, "sources": []}


@tool("W", "Apply a changeset", "POST", "/changesets/{changeset_id}/apply")
def apply_changeset(changeset_id: str, accept_ids: list[str], reason: str | None = None) -> dict:
    """Apply the accepted cells of an imported workpaper; everything else is rejected.

    accept_ids are item ids from import_workpaper ('c1', 'c2'…). A conflict is only
    applied when its id is listed (the workbook value then replaces the app's). Each
    K-1 cell becomes an edit_k1_value whose reason names the workpaper version and cell
    (plus `reason`, if given); an approved K-1 returns to review. An item fails, and
    the rest still apply, if the value changed again after the import. Writes; no cost.
    """
    c = require_changeset(changeset_id)
    require_case(c["case_id"], writable=True)
    if c["status"] != "pending":
        raise ToolFailure("changeset_closed", f"This changeset is already {c['status']}",
                          "Import the workbook again to review it afresh.", status=409)
    accept = set(accept_ids or [])
    unknown = accept - {i["id"] for i in c["items"]}
    if unknown:
        raise ToolFailure("unknown_item", f"No item(s) {', '.join(sorted(unknown))} in this changeset",
                          "Use item ids from the changeset (c1, c2…).", status=422)
    bad = [i["id"] for i in c["items"] if i["id"] in accept and i["invalid"]]
    if bad:
        raise ToolFailure("invalid_items", f"Item(s) {', '.join(bad)} can't be applied as typed",
                          "Fix those cells in the workbook and import it again, or leave them out.", status=422)
    wp = store.get_output(c["workpaper_id"]) or {"version": "?"}
    extra = re.sub(r"\s+", " ", reason or "").strip()
    items, touched, sources = [], set(), []
    for i in c["items"]:
        i = dict(i)
        if i["id"] not in accept:
            i["status"] = "rejected"
            items.append(i)
            continue
        why = f"Workpaper v{wp['version']} import, {i['sheet']}!{i['cell']}" + (f": {extra}" if extra else "")
        try:
            if i["kind"] == "k1_value":
                doc = store.get_document(i["doc_id"])
                if doc is None:
                    raise ToolFailure("gone", "The K-1 was removed from the case")
                now = k1doc.get_value(_k1_current(doc), i["path"])
                if not workpaper.same(now, i["current"]):
                    raise ToolFailure("changed_since_import", f"Changed in the app after the import ({money(now)})")
                out = edit_k1_value(i["doc_id"], i["path"], i["new"], why[:MAX_REASON])
                i["edit_id"] = out["edit"]["id"]
                touched.add(i["doc_id"])
                sources += out["sources"]
            else:
                item = store.get_checklist_item(i["checklist_id"])
                if item is None:
                    raise ToolFailure("gone", "The checklist item was deleted")
                if item["status"] != i["current"]:
                    raise ToolFailure("changed_since_import", f"Changed in the app after the import ({item['status']})")
                store.update_checklist(item["id"], status=i["new"])
            i["status"] = "applied"
        except ToolFailure as exc:
            i["status"], i["error"] = "failed", exc.message
        items.append(i)
    store.update_changeset(changeset_id, items=items, status="applied", resolved=store.now())
    docs = [store.get_document(d) for d in sorted(touched)]
    return {"changeset": _changeset_out(require_changeset(changeset_id)),
            "k1s": [{"id": d["id"], "label": snapshot.display_name(d["label"]), "status": d["status"]} for d in docs if d],
            "sources": sources[:20]}


@tool("W", "Discard a changeset", "POST", "/changesets/{changeset_id}/discard")
def discard_changeset(changeset_id: str) -> dict:
    """Close an imported workpaper without applying anything. Writes; no cost."""
    c = require_changeset(changeset_id)
    if c["status"] != "pending":
        raise ToolFailure("changeset_closed", f"This changeset is already {c['status']}", "Nothing to discard.", status=409)
    items = [{**i, "status": "rejected"} for i in c["items"]]
    store.update_changeset(changeset_id, items=items, status="discarded", resolved=store.now())
    return {"changeset": _changeset_out(require_changeset(changeset_id)), "sources": []}


# ── Review packet ─────────────────────────────────────────────────────────

@tool("W", "Build a review packet", "POST", "/cases/{case_id}/packets")
def build_review_packet(case_id: str) -> dict:
    """Build the case's review packet as a PDF: return summary and 1040 lines; for each
    K-1, amounts not in the calculation, flags and acknowledgements, and every edit
    with its reason and PDF page; saved scenarios (re-run against the return); research
    answers with numbered citations (cached demo answers labeled); meeting notes with
    timestamped decisions; the requested-documents checklist; approved follow-up emails.
    Doesn't change the case; no cost; a few seconds when there are scenarios.
    """
    case = require_case(case_id)
    snap = snapshot.gather(case_id, with_scenarios=True)
    out_id = store.new_id("pkt")
    o = store.insert_output({"id": out_id, "case_id": case_id, "kind": "packet", "file": ""})
    data, meta = packet.build(snap, o["version"])
    rel = f"packets/review-packet-v{o['version']}.pdf"
    path = store.case_dir(case_id) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    store.update_output(out_id, rel, meta)
    o = store.get_output(out_id)
    return {"packet": _output_out(o), "sources": [{"type": "packet", "ref": f"packet://{case_id}/v{o['version']}",
                                                   "label": f"Review packet v{o['version']} · {case['name']}"}]}


@tool("R", "List outputs", "GET", "/cases/{case_id}/outputs")
def list_outputs(case_id: str) -> dict:
    """A case's exported workpapers, review packets and imported changesets, newest
    first, with download urls. Read-only."""
    require_case(case_id)
    outs = [_output_out(o) for o in store.list_outputs(case_id)]
    changesets = [{k: v for k, v in _changeset_out(c).items() if k != "items"} for c in store.list_changesets(case_id)]
    return {"workpapers": [o for o in outs if o["kind"] == "workpaper"],
            "packets": [o for o in outs if o["kind"] == "packet"],
            "changesets": changesets, "sources": []}
