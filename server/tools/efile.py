"""E-file dry run (Phase 8): export → approve → sign → submit → status.

Each efile_export starts a new submission; a rejected one is fixed and exported
again. The return hash is locked at signing: if the case's calculation changes
after that, the submission can't be transmitted and must be exported again.

Phase 13 adds a batch queue over the same per-case flow: batch_efile_candidates
lists every eligible case with its status; batch_efile_push runs export/approve/sign
per case (a fresh self-select PIN, the prior-year AGI already on file); batch_efile_submit
transmits the ones that are signed. Each stops at the first problem for that case and
reports why, without touching the others. Federal returns only — this build has no
state e-file or extension support.
"""
from __future__ import annotations

import re
import secrets

from .. import efile, store
from ..errors import ToolFailure, not_found
from . import tool
from .cases import require_case

OPEN = ("ready", "approved", "signed")
NEXT_STEP = {
    "ready": "Approve it (efile_approve) once the pre-checks pass.",
    "approved": "Have the taxpayer sign Form 8879 (efile_sign).",
    "signed": "Transmit it (efile_submit).",
    "queued": "Waiting for the FakeTransmitter; check efile_status in a few seconds.",
    "transmitted": "Waiting for the IRS acknowledgement (simulated); check efile_status in a few seconds.",
    "accepted": "Done. The return was accepted (in the dry run).",
    "rejected": "Fix each reject (its fix link says where), then efile_export again.",
    "void": "Replaced by a later export.",
}


def _current_fp(case: dict) -> str:
    from .. import calc
    contribs, _, _ = calc.case_contributions(case["id"])
    return calc.fingerprint(case["tax_year"], calc.assemble(contribs))


def _filing_out(f: dict, case: dict, fp: str | None = None) -> dict:
    f = efile.advance(f)
    path = efile.xml_path(f) if f["xml_file"] else None
    has_xml = path is not None and path.is_file()
    stale = f["status"] in OPEN and fp is not None and fp != f["fingerprint"]
    return {
        "id": f["id"], "case_id": f["case_id"], "number": f["number"], "status": f["status"],
        "stale": stale, "next_step": "The return changed after this export. Export again." if stale else NEXT_STEP[f["status"]],
        "sha256": f["sha256"], "hash_locked": f["signature"] is not None,
        "xml_url": f"/api/filings/{f['id']}/xml" if has_xml else None, "xml_bytes": path.stat().st_size if has_xml else None,
        "filer": f["filer"], "checks": f["checks"],
        "signature": f["signature"] and {k: v for k, v in f["signature"].items() if k != "pin"},
        "submission": _submission_out(f),
        "timeline": f["timeline"], "created": f["created"], "updated": f["updated"],
    }


def _submission_out(f: dict) -> dict | None:
    """The FakeTransmitter's record; the result and rejects only once acknowledged."""
    sub = f["submission"]
    if not sub:
        return None
    acked = f["status"] in ("accepted", "rejected")
    return {**{k: v for k, v in sub.items() if k not in ("result", "rejects")},
            "result": sub["result"] if acked else None, "rejects": sub["rejects"] if acked else []}


def _source(f: dict) -> dict:
    return {"type": "filing", "ref": f"filing://{f['case_id']}/{f['number']}", "label": f"E-file submission {f['number']}"}


def require_filing(filing_id: str) -> dict:
    f = store.get_filing(filing_id)
    if f is None:
        raise not_found("filing", filing_id, "Call efile_status(case_id) to list the case's submissions.")
    return f


def _step(f: dict, want: str, verb: str) -> tuple[dict, dict]:
    case = require_case(f["case_id"], writable=True)
    f = efile.advance(f)
    if f["status"] != want:
        raise ToolFailure("wrong_state", f"Submission {f['number']} is {f['status']}, so it can't be {verb}",
                          NEXT_STEP[f["status"]], status=409)
    if _current_fp(case) != f["fingerprint"]:
        raise ToolFailure("stale_export", "The return changed after this export",
                          "Call efile_export to build a fresh submission.", status=409)
    return case, f


@tool("W", "Export for e-file", "POST", "/cases/{case_id}/efile/exports")
def efile_export(case_id: str) -> dict:
    """Build the case's MeF XML with OpenTax and pre-check it; starts a new e-file
    submission at `ready` (any earlier unsent one is voided).

    The first export gives the case a synthetic filer (SSN 987-65-4320, an SSA
    advertising number, and a placeholder address) and enrolls that taxpayer in the
    fake IRS e-File database. Pre-checks: `blocking` items (an unapproved K-1, an
    input MeF can't carry) must be fixed before approval, each with a fix link;
    `warnings` don't block; `validator` groups OpenTax's reject-level MeF rule
    findings by who owns them. Nothing is sent anywhere. Writes; no cost; a few seconds.
    """
    case = require_case(case_id, writable=True)
    efile.ensure_filer(case)
    built = efile.build(case)
    g = (efile.start_input(case_id) or {"data": {}})["data"].get("general", {})
    for old in store.list_filings(case_id):
        if old["status"] in OPEN:
            store.update_filing(old["id"], status="void", timeline=old["timeline"] + [
                {"status": "void", "at": store.now(), "detail": "Replaced by a new export."}])
    chk = efile.checks(case, built)
    chk["agi"] = built["result"]["lines"].get("line11_agi", 0)     # enrolls the fake e-File record at approval
    fid = store.new_id("efl")
    nb = len(chk["blocking"])
    detail = ("MeF XML built by OpenTax. " + (f"{nb} pre-check{'s' if nb != 1 else ''} to fix first." if nb else
                                              "Pre-checks passed.")) if built["xml"] else "OpenTax couldn't build the MeF XML."
    f = store.insert_filing({"id": fid, "case_id": case_id, "status": "ready", "fingerprint": built["fingerprint"],
                             "xml_file": "", "sha256": "", "filer": efile.filer_out(g), "checks": chk,
                             "timeline": [{"status": "ready", "at": store.now(), "detail": detail}]})
    if built["xml"]:
        rel = efile.write_xml(case_id, f["number"], built["xml"], "")
        store.update_filing(fid, xml_file=rel, sha256=efile.sha256(built["xml"]))
    f = store.get_filing(fid)
    return {"filing": _filing_out(f, case, built["fingerprint"]), "sources": [_source(f)]}


@tool("W", "Approve for e-file", "POST", "/filings/{filing_id}/approve")
def efile_approve(filing_id: str) -> dict:
    """Preparer sign-off on a `ready` submission. Refused while it has blocking
    pre-checks or the return has changed since the export. Writes; no cost."""
    case, f = _step(require_filing(filing_id), "ready", "approved")
    if f["checks"]["blocking"]:
        raise ToolFailure("blocking_checks", f"{len(f['checks']['blocking'])} pre-check(s) still block this submission",
                          "Fix each one (its fix link says where), then efile_export again.", status=409)
    g = (efile.start_input(case["id"]) or {"data": {}})["data"].get("general", {})
    efile.enrollment(case["id"], g, f["checks"].get("agi", 0))
    store.update_filing(f["id"], status="approved", timeline=f["timeline"] + [
        {"status": "approved", "at": store.now(), "detail": "Approved by the preparer."}])
    f = store.get_filing(f["id"])
    return {"filing": _filing_out(f, case, f["fingerprint"]), "sources": [_source(f)]}


@tool("W", "Sign for e-file", "POST", "/filings/{filing_id}/sign")
def efile_sign(filing_id: str, taxpayer_pin: str, prior_year_agi: float) -> dict:
    """The taxpayer's Form 8879 signature on an `approved` submission, which locks
    the return's hash.

    taxpayer_pin: a self-select PIN, five digits, not all zeros. prior_year_agi: the
    AGI on last year's return, which the IRS uses to verify the PIN (a mismatch is
    rejected as IND-031-04; efile_status shows the value on file in the fake e-File
    database). The XML is exported again with the signature and its SHA-256 is
    locked. Writes; no cost.
    """
    case, f = _step(require_filing(filing_id), "approved", "signed")
    pin = (taxpayer_pin or "").strip()
    if not re.fullmatch(r"\d{5}", pin) or pin == "00000":
        raise ToolFailure("bad_pin", "The PIN must be five digits, not all zeros", "Pick any five digits, e.g. 24681.",
                          status=422)
    if prior_year_agi is None or prior_year_agi < 0 or prior_year_agi > 1e10:
        raise ToolFailure("bad_agi", "Prior-year AGI must be zero or more", "Enter last year's AGI in whole dollars.",
                          status=422)
    agi = int(round(prior_year_agi))
    built = efile.build(case, signature={"pin": pin, "prior_year_agi": agi})
    if not built["xml"] or built["fingerprint"] != f["fingerprint"]:
        raise ToolFailure("stale_export", "The return changed while signing", "Call efile_export again.", status=409)
    rel = efile.write_xml(case["id"], f["number"], built["xml"], "-signed")
    digest = efile.sha256(built["xml"])
    sig = {"pin": pin, "pin_masked": "•••" + pin[-2:], "prior_year_agi": agi, "form": "8879",
           "signed_at": store.now(), "sha256": digest}
    store.update_filing(f["id"], status="signed", xml_file=rel, sha256=digest, signature=sig, timeline=f["timeline"] + [
        {"status": "signed", "at": sig["signed_at"], "detail": f"Form 8879 signed with a self-select PIN. "
                                                               f"Return hash locked: {digest[:12]}…"}])
    f = store.get_filing(f["id"])
    return {"filing": _filing_out(f, case, f["fingerprint"]), "sources": [_source(f)]}


@tool("W", "Transmit (dry run)", "POST", "/filings/{filing_id}/submit")
def efile_submit(filing_id: str) -> dict:
    """Transmit a `signed` submission to the FakeTransmitter. Nothing is sent to the
    IRS. The signed XML's hash must still match the one locked at signing. The
    submission is queued, transmitted ~2 s later and acknowledged ~4 s after that;
    call efile_status to see the result. The FakeTransmitter checks what OpenTax
    can't locally: SSN + name control (R0000-500-01), the signature's prior-year AGI
    (IND-031-04) and duplicates (IND-515-01). Writes; no cost.
    """
    case, f = _step(require_filing(filing_id), "signed", "transmitted")
    path = efile.xml_path(f)
    xml = path.read_text() if path.exists() else ""
    if efile.sha256(xml) != f["signature"]["sha256"]:
        raise ToolFailure("hash_mismatch", "The signed XML doesn't match the hash locked at signing",
                          "Export and sign again.", status=409)
    sub = efile.transmit(f, xml)
    store.update_filing(f["id"], status="queued", submission=sub, timeline=f["timeline"] + [
        {"status": "queued", "at": sub["queued_at"], "detail": "Queued with the FakeTransmitter; manifest stamped "
                                                               "(IP address, device id, timestamp)."}])
    f = store.get_filing(f["id"])
    return {"filing": _filing_out(f, case, f["fingerprint"]), "sources": [_source(f)]}


@tool("R", "E-file status", "GET", "/cases/{case_id}/efile")
def efile_status(case_id: str) -> dict:
    """A case's e-file submissions, newest first: each one's timeline, pre-checks, hash,
    and (once acknowledged) the rejects, each with the field and a fix link. Also the
    filer and the fake e-File database's record for them. Read-only."""
    case = require_case(case_id)
    filings = store.list_filings(case_id)
    fp = _current_fp(case) if any(f["status"] in OPEN for f in filings) else None
    out = [_filing_out(f, case, fp) for f in filings]
    g = (efile.start_input(case_id) or {"data": {}})["data"].get("general", {})
    rec = store.get_efile_record(case_id)
    return {"case_id": case_id, "read_only": case["read_only"], "filings": out,
            "current": out[0] if out else None,
            "filer": efile.filer_out(g) if g.get("taxpayer_ssn") else None,
            "efile_database": rec and {"ssn_masked": efile.mask_ssn(rec["ssn"]), "name_control": rec["name_control"],
                                       "prior_year_agi": rec["prior_year_agi"], "enrolled": rec["enrolled"],
                                       "note": "Synthetic: the fake IRS e-File database the FakeTransmitter checks."},
            "sources": [_source(f) for f in filings[:5]]}


@tool("W", "Set the e-file filer name", "POST", "/cases/{case_id}/efile/filer")
def efile_set_filer(case_id: str, first_name: str | None = None, last_name: str | None = None) -> dict:
    """Correct the taxpayer's name on the case's filing information (the fix for an
    R0000-500-01 name control reject). The SSN stays synthetic. Export again
    afterwards. Writes; no cost."""
    require_case(case_id, writable=True)
    return {"filer": efile.set_filer(case_id, first_name, last_name),
            "next_step": "Call efile_export to build a new submission with the corrected name.",
            "sources": [{"type": "case", "ref": f"case://{case_id}", "label": "Filing information"}]}


# ── Batch queue ─────────────────────────────────────────────────────────────

SUBMITTED = ("queued", "transmitted", "accepted")


def _eligible(case: dict) -> bool:
    docs = store.list_documents(case["id"])
    return any(d["status"] == "approved" for d in docs) or bool(store.list_inputs(case["id"]))


@tool("R", "Batch e-file candidates", "GET", "/efile/batch")
def batch_efile_candidates() -> dict:
    """Every writable case ready to calculate (an approved K-1 or set inputs), with
    its latest e-file status, for the batch queue. Federal returns only — no state
    or extension filing in this build. Read-only and free."""
    out = []
    for case in store.list_cases():
        if case["read_only"] or not _eligible(case):
            continue
        filings = store.list_filings(case["id"])
        f = efile.advance(filings[0]) if filings else None
        out.append({
            "case_id": case["id"], "case_name": case["name"], "tax_year": case["tax_year"],
            "status": f["status"] if f else None,
            "stale": bool(f) and f["status"] in OPEN and _current_fp(case) != f["fingerprint"],
            "blocking": len(f["checks"]["blocking"]) if f and f["status"] == "ready" else 0,
        })
    out.sort(key=lambda c: c["case_name"])
    return {"cases": out, "sources": []}


def _push_one(case_id: str) -> dict:
    case = require_case(case_id, writable=True)
    filings = store.list_filings(case_id)
    f = efile.advance(filings[0]) if filings else None
    if f and f["status"] not in OPEN and f["status"] != "rejected":
        return {"ok": f["status"] in SUBMITTED, "status": f["status"]}     # already past pushing, or void
    if f is None or f["status"] == "rejected" or (f["status"] in OPEN and _current_fp(case) != f["fingerprint"]):
        f = store.get_filing(efile_export(case_id)["filing"]["id"])
    if f["status"] == "ready":
        if f["checks"]["blocking"]:
            return {"ok": False, "status": "ready", "blocking": len(f["checks"]["blocking"])}
        f = store.get_filing(efile_approve(f["id"])["filing"]["id"])
    if f["status"] == "approved":
        rec = store.get_efile_record(case_id)
        pin = f"{secrets.randbelow(90000) + 10000}"      # a fresh self-select PIN; nothing checks it against a prior one
        f = store.get_filing(efile_sign(f["id"], pin, rec["prior_year_agi"] if rec else 0)["filing"]["id"])
    return {"ok": f["status"] == "signed", "status": f["status"]}


@tool("W", "Batch push for e-file", "POST", "/efile/batch/push")
def batch_efile_push(case_ids: list[str]) -> dict:
    """Prepare each case to file: export (if it has none, or the return changed
    since), approve (refused while pre-checks block), and sign with a fresh
    self-select PIN and the prior-year AGI already on file in the fake e-File
    database. A case already queued, transmitted or accepted is left alone. Each
    case stops at its first problem and reports why; the rest still run. Writes;
    no cost.
    """
    results = []
    for case_id in case_ids or []:
        try:
            results.append({"case_id": case_id, **_push_one(case_id)})
        except ToolFailure as exc:
            results.append({"case_id": case_id, "ok": False, "status": None, "error": exc.to_dict()})
    return {"results": results, "sources": []}


def _submit_one(case_id: str) -> dict:
    case = require_case(case_id, writable=True)
    filings = store.list_filings(case_id)
    f = efile.advance(filings[0]) if filings else None
    if f is None:
        return {"ok": False, "status": None}
    if f["status"] != "signed":
        return {"ok": f["status"] in SUBMITTED, "status": f["status"]}
    f = store.get_filing(efile_submit(f["id"])["filing"]["id"])
    return {"ok": True, "status": f["status"]}


@tool("W", "Batch submit for e-file", "POST", "/efile/batch/submit")
def batch_efile_submit(case_ids: list[str]) -> dict:
    """Transmit each case's signed submission to the FakeTransmitter (efile_submit).
    A case that isn't signed yet is left unchanged and reported as such — push it
    first. Writes; no cost.
    """
    results = []
    for case_id in case_ids or []:
        try:
            results.append({"case_id": case_id, **_submit_one(case_id)})
        except ToolFailure as exc:
            results.append({"case_id": case_id, "ok": False, "status": None, "error": exc.to_dict()})
    return {"results": results, "sources": []}
