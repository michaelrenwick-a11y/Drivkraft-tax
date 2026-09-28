"""E-file dry run (Phase 8): OpenTax MeF XML, pre-checks, and a FakeTransmitter.

    ready → approved → signed → queued → transmitted → accepted | rejected

Nothing leaves the machine. The XML comes from `opentax return export --type mef`;
OpenTax's own MeF business-rule validator supplies the pre-check findings. The
rules OpenTax can't check locally (it marks them alwaysPass) are the IRS e-File
database checks, and those are what the FakeTransmitter plays: it reads the signed
XML and compares it with a fake e-File database that enrolls each case's synthetic
taxpayer at its first export.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from . import calc, engine, k1doc, snapshot, store
from .errors import ToolFailure

NS = {"m": "http://www.irs.gov/efile"}
EFIN = "000000"                      # the dry run's placeholder EFIN
QUEUE_S, ACK_S = 2, 4                # queued → transmitted → acknowledged, seconds after submit

# Synthetic filer identity. 987-65-4320…4329 are the SSNs the SSA reserves for
# advertising, so they can never belong to a real person.
SYNTHETIC_SSN = "987654320"
SYNTHETIC_ADDRESS = {"address_line1": "100 Synthetic Way", "address_city": "Lansing", "address_state": "MI",
                     "address_zip": "48933"}

# ── Classifying OpenTax's validator findings ──────────────────────────────
# The export only flags reject-level rules for forms the return has, but in a dry
# run with synthetic data most of them aren't the preparer's to fix.

TRANSMITTER_RULES = {"IND-052", "IND-062", "IND-063", "IND-189", "R0000-060"}
PREPARER_RULES = {"IND-001-01"}
# A return with no amounts at all; the fix is to add something to the case.
EMPTY_RETURN_RULES = {"F1040-065-05"}

KIND_TEXT = {
    "transmitter": "Filled in by the transmitter at submission (manifest, IP address, timestamp, device id).",
    "preparer": "Preparer credentials are placeholders in a dry run.",
    "engine": "Comes from OpenTax's own computed output (not data you entered), so it's an engine gap: "
              "a real transmitter would reject it, the dry run lets it through.",
}


def classify(rule: dict) -> str:
    n, msg = rule["ruleNumber"], rule["message"]
    if n in TRANSMITTER_RULES or re.search(r"Submission Manifest|of the Transmitter|DeviceId", msg):
        return "transmitter"
    if n in PREPARER_RULES or re.search(r"Preparer|PTIN|EFIN", msg):
        return "preparer"
    if n in EMPTY_RETURN_RULES:
        return "fix"
    return "engine"


# ── Identity and the fake e-File database ────────────────────────────────

def name_control(last_name: str) -> str:
    """The IRS name control: the first four letters of the last name (OpenTax's rule)."""
    return re.sub(r"[^A-Z]", "", (last_name or "").upper())[:4]


def mask_ssn(ssn: str) -> str:
    return f"•••-••-{ssn[-4:]}" if ssn else ""


def start_input(case_id: str) -> dict | None:
    return next((i for i in store.list_inputs(case_id) if i["node_type"] == "start"), None)


def ensure_filer(case: dict) -> dict:
    """Give the case's start form a synthetic SSN and address if it has none (the MeF
    header needs both), creating the start form if the case has only defaults."""
    row = start_input(case["id"])
    data = row["data"] if row else {"general": {"filing_status": case["filing_status"], **calc.SYNTHETIC_TAXPAYER}}
    g = data.setdefault("general", {})
    before = dict(g)
    g.setdefault("taxpayer_first_name", calc.SYNTHETIC_TAXPAYER["taxpayer_first_name"])
    g.setdefault("taxpayer_last_name", calc.SYNTHETIC_TAXPAYER["taxpayer_last_name"])
    g.setdefault("taxpayer_ssn", SYNTHETIC_SSN)
    for k, v in SYNTHETIC_ADDRESS.items():
        g.setdefault(k, v)
    if row is None:
        store.insert_input(case["id"], "start", data, "Filing information")
    elif g != before:
        store.update_input(row["id"], data)
    return filer_out(g)


def filer_out(g: dict) -> dict:
    return {"first_name": g.get("taxpayer_first_name", ""), "last_name": g.get("taxpayer_last_name", ""),
            "ssn_masked": mask_ssn(g.get("taxpayer_ssn", "")), "name_control": name_control(g.get("taxpayer_last_name", "")),
            "address": ", ".join(str(g[k]) for k in ("address_line1", "address_city", "address_state", "address_zip")
                                 if g.get(k))}


def set_filer(case_id: str, first_name: str | None, last_name: str | None) -> dict:
    row = start_input(case_id)
    if row is None:
        raise ToolFailure("no_filer", "This case has no filing information yet",
                          "Call efile_export once; it sets up a synthetic filer.", status=409)
    g = row["data"].setdefault("general", {})
    for key, v in (("taxpayer_first_name", first_name), ("taxpayer_last_name", last_name)):
        if v is not None:
            v = re.sub(r"\s+", " ", v).strip()
            if not v or len(v) > 35 or not re.fullmatch(r"[A-Za-z][A-Za-z '\-]*", v):
                raise ToolFailure("bad_name", f"{v!r} isn't a name MeF accepts",
                                  "Use letters, spaces, hyphens or apostrophes (35 characters max).", status=422)
            g[key] = v
    store.update_input(row["id"], row["data"])
    return filer_out(g)


def enrollment(case_id: str, g: dict, agi: float) -> dict:
    """The fake e-File database's record for this case's taxpayer, enrolled at the
    first export: the SSN and name control as they are then, and a plausible
    prior-year AGI (what the taxpayer's last accepted return would show)."""
    rec = store.get_efile_record(case_id)
    if rec is None:
        prior = int(round(max(agi, 0) * 0.94, -2))
        rec = store.enroll_efile_record(case_id, g.get("taxpayer_ssn", ""), name_control(g.get("taxpayer_last_name", "")),
                                        prior)
    return rec


# ── Export and pre-checks ─────────────────────────────────────────────────

_W2_EXPORT = re.compile(r"W-2 (\d+) cannot be exported to MeF without (\w+)")


def build(case: dict, *, signature: dict | None = None) -> dict:
    """Run the case's calculation in an e-file workspace and export MeF XML.

    Returns {xml, fingerprint, rules (the export's reject-level findings, full text),
    export_error, result}. `signature` adds the Form 8879 fields to the start form."""
    contribs, included, skipped = calc.case_contributions(case["id"])
    fp = calc.fingerprint(case["tax_year"], calc.assemble(contribs))
    if signature:
        contribs[0].data.setdefault("general", {})["taxpayer_signature_pin"] = signature["pin"]
    forms = calc.assemble(contribs)
    work = store.case_dir(case["id"]) / "efile" / "work"
    try:
        session = calc._Session(work, case["tax_year"])
        result = session.run(forms)
        try:
            xml, flagged = session.ret.export_mef()
        except engine.EngineError as exc:
            return {"xml": None, "fingerprint": fp, "rules": [], "export_error": _first_line(exc.detail or str(exc)),
                    "result": result, "included": included, "skipped": skipped}
        entries = {e["ruleNumber"]: e for e in session.ret.validate()["entries"]}
    except engine.EngineError as exc:
        raise ToolFailure("engine_error", str(exc), exc.fix_hint, detail=exc.detail) from exc
    finally:
        shutil.rmtree(work / ".state", ignore_errors=True)
    rules = [entries.get(n) or {"ruleNumber": n, "severity": "reject", "category": "unknown", "message": "",
                                "formRef": ""} for n in dict.fromkeys(flagged)]
    if signature:
        xml = _add_prior_year_agi(xml, signature["prior_year_agi"])
    return {"xml": xml, "fingerprint": fp, "rules": rules, "export_error": None, "result": result,
            "included": included, "skipped": skipped}


def _first_line(text: str) -> str:
    return re.sub(r"^Error:\s*", "", (text or "").strip().splitlines()[0] if text else "")


def _add_prior_year_agi(xml: str, agi: int) -> str:
    """OpenTax reads taxpayer_prior_year_agi but doesn't write it to the header, so the
    signature's prior-year AGI (how a self-select PIN is verified) is added here."""
    return xml.replace("</ReturnHeader>", f"<PrimaryPriorYearAGIAmt>{int(agi)}</PrimaryPriorYearAGIAmt></ReturnHeader>", 1)


def checks(case: dict, built: dict) -> dict:
    """Pre-checks: `blocking` must be fixed before approval (each with a fix link);
    `warnings` don't block; `validator` groups OpenTax's reject-level findings."""
    cid = case["id"]
    blocking, warnings = [], []
    if built["export_error"]:
        m = _W2_EXPORT.search(built["export_error"])
        blocking.append({"code": "export_failed", "message": f"OpenTax can't build the MeF XML: {built['export_error']}.",
                         "fix": {"label": "Open the return inputs", "href": f"/cases/{cid}/return"},
                         "fix_hint": f"Add {m.group(2)} to W-2 #{m.group(1)} with set_return_inputs." if m else
                                     "Correct the input the message names with set_return_inputs."})
    for f in built["result"]["engine_failures"]:
        blocking.append({"code": "engine_node_failure", "message": f"OpenTax's {f['node']} node failed: {f['message']}.",
                         "fix": {"label": "Open the return", "href": f"/cases/{cid}/return"},
                         "fix_hint": "Remove or correct the input that triggers it."})
    docs = {d["id"]: d for d in store.list_documents(cid)}
    for s in built["skipped"]:
        blocking.append({"code": "k1_not_approved",
                         "message": f"{snapshot.display_name(s['label'])} isn't approved, so the return leaves it out.",
                         "fix": {"label": "Review the K-1", "href": f"/cases/{cid}/k1/{s['doc_id']}"},
                         "fix_hint": "Approve it (or remove it from the case) and export again."})
    for inc in built["included"]:
        paths = inc["not_in_calculation"]
        if paths:
            boxes = ", ".join(k1doc.box_label(p) for p in paths[:4]) + (f" and {len(paths) - 4} more" if len(paths) > 4 else "")
            warnings.append({"code": "not_in_calculation",
                             "message": f"{snapshot.display_name(inc['label'])}: {boxes} can't reach the return "
                                        "(OpenTax has no input for them), so the e-filed return leaves them out.",
                             "fix": {"label": "Open the K-1", "href": f"/cases/{cid}/k1/{inc['doc_id']}?box={paths[0]}"}})
    open_items = [c for c in store.list_checklist(cid) if c["status"] == "open" and c["type"] != "action"]
    if open_items:
        warnings.append({"code": "checklist_open", "message": f"{len(open_items)} requested document"
                                                              f"{'s are' if len(open_items) != 1 else ' is'} still open.",
                         "fix": {"label": "Open the checklist", "href": f"/cases/{cid}#checklist"}})
    validator = {"transmitter": [], "preparer": [], "engine": []}
    for r in built["rules"]:
        kind = classify(r)
        item = {"rule": r["ruleNumber"], "severity": r["severity"], "category": r["category"], "form": r["formRef"],
                "message": r["message"]}
        if kind == "fix":
            blocking.append({"code": r["ruleNumber"], "message": r["message"],
                             "fix": {"label": "Open the case", "href": f"/cases/{cid}"},
                             "fix_hint": "Approve a K-1 or add inputs so the return has income."})
        else:
            validator[kind].append(item)
    return {"blocking": blocking, "warnings": warnings, "validator": validator, "notes": KIND_TEXT}


def sha256(data: str | bytes) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def write_xml(case_id: str, filing_number: int, xml: str, suffix: str) -> str:
    rel = f"efile/submission-{filing_number}{suffix}.xml"
    p = store.case_dir(case_id) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(xml)
    return rel


def xml_path(filing: dict) -> Path:
    return store.case_dir(filing["case_id"]) / filing["xml_file"]


# ── FakeTransmitter ───────────────────────────────────────────────────────

def _header(xml: str) -> dict:
    root = ET.fromstring(xml)
    h = root.find("m:ReturnHeader", NS)
    text = lambda path: (h.findtext(path, default="", namespaces=NS) or "").strip()
    return {"ssn": text("m:Filer/m:PrimarySSN"), "name_control": text("m:Filer/m:PrimaryNameControlTxt"),
            "prior_year_agi": text("m:PrimaryPriorYearAGIAmt"), "tax_year": text("m:TaxYr")}


def submission_id(now: datetime) -> str:
    """MeF format: EFIN (6) + year and day of year (7) + 7 alphanumerics."""
    return f"{EFIN}{now:%Y%j}{secrets.token_hex(4)[:7]}".lower()


def transmit(filing: dict, xml: str) -> dict:
    """Queue the signed XML with the FakeTransmitter. It stamps the submission manifest
    (the header fields the validator said a transmitter fills), then plays the IRS
    side: the e-File database checks OpenTax can't run locally. The acknowledgement
    is decided now and revealed QUEUE_S + ACK_S seconds later (see advance)."""
    case_id = filing["case_id"]
    now = datetime.now(timezone.utc)
    h = _header(xml)
    rec = store.get_efile_record(case_id)
    rejects = []
    if rec is None or h["ssn"] != rec["ssn"] or h["name_control"] != rec["name_control"]:
        rejects.append({
            "rule": "R0000-500-01", "severity": "reject_and_stop",
            "message": "'PrimarySSN' and 'PrimaryNameControlTxt' in the Return Header must match the e-File database.",
            "detail": f"The return has name control {h['name_control']!r}; the e-File database has "
                      f"{rec['name_control'] if rec else 'no record'!r} for this SSN.",
            "field": "Taxpayer last name",
            "fix": {"label": "Correct the taxpayer's name", "href": f"/cases/{case_id}/efile?fix=filer"}})
    if rec is not None and h["prior_year_agi"] and int(float(h["prior_year_agi"])) != rec["prior_year_agi"]:
        rejects.append({
            "rule": "IND-031-04", "severity": "reject",
            "message": "'PrimaryPriorYearPIN' or 'PrimaryPriorYearAGIAmt' in the Return Header must match the e-File "
                       "database.",
            "detail": f"The signature used a prior-year AGI of ${int(float(h['prior_year_agi'])):,}; it doesn't match "
                      "last year's accepted return.",
            "field": "Prior-year AGI (Form 8879)",
            "fix": {"label": "Sign again with last year's AGI", "href": f"/cases/{case_id}/efile?fix=signature"}})
    dup = next((f for f in store.list_filings(case_id) if f["status"] == "accepted" and f["id"] != filing["id"]), None)
    if dup:
        rejects.append({
            "rule": "IND-515-01", "severity": "reject",
            "message": "The Primary SSN in the Return Header must not be the same as the Primary SSN in another return "
                       "filed for the same tax year.",
            "detail": f"Submission {dup['number']} for this taxpayer was already accepted. A change now needs an "
                      "amended return (1040-X), which the dry run doesn't build.",
            "field": None, "fix": None})
    return {
        "transmitter": "FakeTransmitter",
        "submission_id": submission_id(now),
        "manifest": {"efin": EFIN, "tin": h["ssn"][-4:].rjust(9, "•"), "tax_year": h["tax_year"],
                     "ip_address": "127.0.0.1", "device_id": secrets.token_hex(20).upper(),
                     "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "sha256": sha256(xml)},
        "queued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "transmitted_at": (now + timedelta(seconds=QUEUE_S)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ack_at": (now + timedelta(seconds=QUEUE_S + ACK_S)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "result": "rejected" if rejects else "accepted",
        "rejects": rejects,
    }


def advance(filing: dict) -> dict:
    """Move a queued submission along its timeline once its times have passed."""
    sub = filing["submission"]
    if filing["status"] not in ("queued", "transmitted") or not sub:
        return filing
    now = store.now()
    timeline = list(filing["timeline"])
    status = filing["status"]
    if status == "queued" and now >= sub["transmitted_at"]:
        status = "transmitted"
        timeline.append({"status": "transmitted", "at": sub["transmitted_at"],
                         "detail": f"Sent to the IRS as submission {sub['submission_id']} (simulated)."})
    if status == "transmitted" and now >= sub["ack_at"]:
        status = sub["result"]
        n = len(sub["rejects"])
        timeline.append({"status": status, "at": sub["ack_at"],
                         "detail": "Acknowledgement received: accepted." if status == "accepted" else
                                   f"Acknowledgement received: rejected with {n} error{'s' if n != 1 else ''}."})
    if status != filing["status"]:
        store.update_filing(filing["id"], status=status, timeline=timeline)
        filing = store.get_filing(filing["id"])
    return filing
