"""Source documents dropped on a case (Phase 11): synthetic PDF → OpenTax inputs.

The upstream k1-otd extractor only runs on the one synthetic K-1 it was built
for (it checks the PDF's hash), so dropped documents are read here instead,
from the PDF's text layer: every drawn box is a (label, value) pair, where the
label is the small print at the top of the box and the value is everything
larger. Tables (1099-B lots, the K-1's 199A statement) are read line by line.

What each form becomes:
    W-2, 1099-INT, 1099-DIV/B, 1098  → rows in the case's inputs (tagged with the source id)
    Schedule K-1 (1065)              → an OTD document, then the usual validate → bridge → review
    Client organizer                 → the start form (filer, spouse, dependents), Form 2441, Schedule A

Only synthetic documents are accepted (ground rule 1): the PDF must carry the
"SYNTHETIC" watermark or the "Fictional document" footer.
"""
from __future__ import annotations

import copy
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pdfplumber
import yaml

from .paths import OTD_PROOF

MAX_BYTES = 15 * 1024 * 1024       # the bundled synthetic K-1 package is ~10 MB
MAX_PAGES = 30
LABEL_MAX_SIZE = 8.0          # box labels are small print; values are larger
WATERMARK_MIN_SIZE = 30.0

FORM_TITLES = {"w2": "W-2", "1099-int": "1099-INT", "1099-div": "1099-DIV / 1099-B", "1098": "1098",
               "k1-1065": "Schedule K-1 (1065)", "organizer": "Client organizer"}


class Refused(Exception):
    """The document can't be accepted: code, message and a fix hint for the reviewer."""

    def __init__(self, code: str, message: str, fix_hint: str):
        super().__init__(message)
        self.code, self.message, self.fix_hint = code, message, fix_hint


@dataclass
class Box:
    label: str                 # "1 Wages, tips, other compensation"
    lines: list[str]           # value lines, top to bottom
    page: int
    bbox: list[float] = field(default_factory=list)   # PDF points, top-left origin (like upstream evidence)

    @property
    def value(self) -> str:
        return " ".join(self.lines).strip()


@dataclass
class Doc:
    boxes: list[Box]
    lines: list[str]           # every text line, in reading order
    words: list[dict]          # pdfplumber words with page numbers
    marker: bool               # carries a synthetic marker

    def box(self, pattern: str) -> Box | None:
        rx = re.compile(pattern, re.I)
        return next((b for b in self.boxes if rx.search(b.label)), None)

    def value(self, pattern: str) -> str | None:
        b = self.box(pattern)
        return b.value if b and b.value else None

    def amount(self, pattern: str) -> float | None:
        return money(self.value(pattern))


@dataclass
class Parsed:
    form: str
    label: str                                     # "W-2 · GREAT LAKES MOBILITY SYSTEMS INC"
    inputs: list[tuple[str, dict, str]] = field(default_factory=list)   # (node_type, data, label)
    fields: list[dict] = field(default_factory=list)                    # [{box, label, value}] as read
    warnings: list[str] = field(default_factory=list)
    k1: dict | None = None                         # K-1 values for the OTD builder


# ── Reading the text layer ────────────────────────────────────────────────

def money(s: str | None) -> float | None:
    """'1,234.56' → 1234.56 · '(2,500.00)' and '-545.30' → negative · blank or text → None."""
    if s is None:
        return None
    m = re.search(r"(\()?(-)?\$?\s*(\d[\d,]*(?:\.\d+)?)(\))?", s)
    if not m:
        return None
    v = float(m.group(3).replace(",", ""))
    return -v if (m.group(1) and m.group(4)) or m.group(2) else v


def iso_date(s: str | None) -> str | None:
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _inside(w: dict, r: dict) -> bool:
    cx, cy = (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2
    return r["x0"] <= cx <= r["x1"] and r["top"] <= cy <= r["bottom"]


def _join_lines(words: list[dict]) -> list[str]:
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and abs(rows[-1][0]["top"] - w["top"]) < 3:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [" ".join(x["text"] for x in sorted(r, key=lambda w: w["x0"])) for r in rows]


def read(path: Path) -> Doc:
    boxes: list[Box] = []
    lines: list[str] = []
    all_words: list[dict] = []
    big: list[dict] = []
    try:
        pdf = pdfplumber.open(path)
    except Exception as exc:
        raise Refused("unreadable_pdf", "That file isn't a readable PDF",
                      "Drop a PDF saved from the form (not a scan or a photo).") from exc
    with pdf:
        if len(pdf.pages) > MAX_PAGES:
            raise Refused("too_many_pages", f"PDFs are limited to {MAX_PAGES} pages", "Drop one form per file.")
        for n, page in enumerate(pdf.pages, 1):
            words = page.extract_words(extra_attrs=["fontname", "size"])
            big += [w for w in words if w["size"] >= WATERMARK_MIN_SIZE]
            words = [{**w, "page": n} for w in words if w["size"] < WATERMARK_MIN_SIZE]
            all_words += words
            lines += _join_lines(words)
            rects = [r for r in page.rects if r["width"] > 20 and r["height"] > 12]
            for r in rects:
                inner = [w for w in words if _inside(w, r)]
                # A rect that holds another rect's text is a container (e.g. box 12's frame); skip nested text.
                label = " ".join(_join_lines([w for w in inner if w["size"] <= LABEL_MAX_SIZE]))
                values = [w for w in inner if w["size"] > LABEL_MAX_SIZE]
                if label or values:
                    boxes.append(Box(re.sub(r"\s+", " ", label).strip(), _join_lines(values), n,
                                     [round(r["x0"], 1), round(r["top"], 1), round(r["x1"], 1), round(r["bottom"], 1)]))
    watermark = "".join(w["text"] for w in sorted(big, key=lambda w: w["x0"])).upper()
    text = " ".join(lines).lower()
    marker = "SYNTHETIC" in watermark or "fictional document" in text or "synthetic" in text
    if not all_words:
        raise Refused("no_text_layer", "This PDF has no text layer",
                      "Scans and photos need OCR, which this build doesn't do. Drop a PDF with selectable text.")
    return Doc(boxes, lines, all_words, marker)


def classify(doc: Doc) -> str | None:
    head = " ".join(doc.lines[:6]).lower()
    text = " ".join(doc.lines).lower()
    if "schedule k-1 (form 1065)" in head:
        return "k1-1065"
    if "wage and tax statement" in head:
        return "w2"
    if "1099-int" in head and "interest income" in head:
        return "1099-int"
    if "1099-div" in head or ("composite" in head and "1099" in head) or "dividends and distributions" in head:
        return "1099-div"
    if "mortgage interest statement" in head:
        return "1098"
    if "tax organizer" in head or ("organizer" in head and "filing status" in text):
        return "organizer"
    return None


# ── Per-form parsers ──────────────────────────────────────────────────────

def _field(p: Parsed, box: str, label: str, value: Any) -> None:
    if value not in (None, "", [], False):
        p.fields.append({"box": box, "label": label, "value": value})


def _put(data: dict, key: str, value: Any) -> None:
    if value is not None:
        data[key] = value


def _first_line(doc: Doc, pattern: str) -> str | None:
    b = doc.box(pattern)
    return b.lines[0].strip() if b and b.lines else None


def _checked(doc: Doc, label_word: str) -> bool:
    """A checkbox is checked when an 'X' sits on the same line just left of its label."""
    for w in doc.words:
        if w["text"].lower().startswith(label_word.lower()):
            if any(x["text"] == "X" and x["page"] == w["page"] and abs(x["top"] - w["top"]) < 4
                   and 0 < w["x0"] - x["x1"] < 16 for x in doc.words):
                return True
    return False


def parse_w2(doc: Doc) -> Parsed:
    employer = _first_line(doc, r"^c\b.*employer's name")
    p = Parsed("w2", f"W-2 · {employer or 'employer not read'}")
    d: dict[str, Any] = {}
    _put(d, "employer_name", employer)
    _put(d, "employer_ein", doc.value(r"^b\b.*employer identification"))
    box_c = doc.box(r"^c\b.*employer's name")
    if box_c and len(box_c.lines) >= 3:
        _put(d, "employer_address_line1", box_c.lines[1])
        m = re.match(r"(.+),\s*([A-Z]{2})\s+(\d{5})", box_c.lines[-1])
        if m:
            d.update(employer_address_city=m[1], employer_address_state=m[2], employer_address_zip=m[3])
    boxes = [("1", r"^1 wages", "box1_wages"), ("2", r"^2 federal income tax", "box2_fed_withheld"),
             ("3", r"^3 social security wages", "box3_ss_wages"), ("4", r"^4 social security tax", "box4_ss_withheld"),
             ("5", r"^5 medicare wages", "box5_medicare_wages"), ("6", r"^6 medicare tax", "box6_medicare_withheld"),
             ("7", r"^7 social security tips", "box7_ss_tips"), ("8", r"^8 allocated tips", "box8_allocated_tips"),
             ("10", r"^10 dependent care", "box10_dep_care"), ("11", r"^11 nonqualified", "box11_nonqual_plans"),
             ("16", r"^16 state wages", "box16_state_wages"), ("17", r"^17 state income tax", "box17_state_withheld"),
             ("18", r"^18 local wages", "box18_local_wages"), ("19", r"^19 local income tax", "box19_local_withheld")]
    for box, rx, key in boxes:
        v = doc.amount(rx)
        _put(d, key, v)
        _field(p, box, doc.box(rx).label if doc.box(rx) else key, v)
    for key in ("box1_wages", "box2_fed_withheld"):     # required by the engine
        if key not in d:
            p.warnings.append(f"{key.split('_')[0].replace('box', 'Box ')} wasn't read; entered as 0. Check the PDF.")
            d[key] = 0.0
    b12 = doc.box(r"^12 see instructions")
    entries = [{"code": c, "amount": money(a)} for c, a in re.findall(r"12[a-d]\s+([A-Z]{1,2})\s+([\d,]+\.\d{2})",
                                                                        " ".join(b12.lines if b12 else []))]
    if entries:
        d["box12_entries"] = entries
        _field(p, "12", "Box 12", ", ".join(f"{e['code']} {e['amount']:,.2f}" for e in entries))
    b14 = doc.value(r"^14 other")
    if b14:
        items = [{"description": desc.strip(), "amount": money(a),
                  "is_state_sdi_pfml": bool(re.search(r"\b(SDI|PFML|FLI|PFL)\b", desc, re.I))}
                 for desc, a in re.findall(r"([A-Za-z][A-Za-z0-9 /&-]*?)\s+([\d,]+\.\d{2})", b14)]
        if items:
            d["box14_entries"] = items
            _field(p, "14", "Box 14", b14)
    d["box13_retirement_plan"] = _checked(doc, "Retirement")
    if _checked(doc, "Statutory"):
        d["box13_statutory_employee"] = True
    if _checked(doc, "Third-party"):
        d["box13_third_party_sick"] = True
    _field(p, "13", "Retirement plan", "checked" if d["box13_retirement_plan"] else None)
    state = doc.value(r"^15 state")
    if state:
        d["box15_state"] = state.split()[0]
        _field(p, "15", "State", d["box15_state"])
    _put(d, "employee_ssn", doc.value(r"^a\b.*employee's social"))
    employee = _first_line(doc, r"employee's name")
    _field(p, "e", "Employee", employee)
    p.inputs.append(("w2", d, p.label + (f" ({employee.title()})" if employee else "")))
    return p


def parse_1099int(doc: Doc) -> Parsed:
    payer = _first_line(doc, r"^payer'?s name")
    p = Parsed("1099-int", f"1099-INT · {payer or 'payer not read'}")
    d: dict[str, Any] = {"payer_name": payer or "Unknown payer"}
    _put(d, "payer_tin", doc.value(r"^payer'?s tin"))
    for box, rx in (("1", r"^1 interest income"), ("2", r"^2 early withdrawal"), ("3", r"^3 interest on u\.?s"),
                    ("4", r"^4 federal income tax"), ("8", r"^8 tax-exempt interest"), ("9", r"^9 specified private")):
        v = doc.amount(rx)
        _put(d, f"box{box}", v)
        _field(p, box, doc.box(rx).label if doc.box(rx) else box, v)
    p.inputs.append(("f1099int", d, p.label))
    return p


LOT = re.compile(r"^(.+?)\s+(\d{2}/\d{2}/\d{4}|VARIOUS)\s+(\d{2}/\d{2}/\d{4})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})$")


def parse_1099div(doc: Doc) -> Parsed:
    payer = _first_line(doc, r"^payer'?s name")
    p = Parsed("1099-div", f"1099-DIV · {payer or 'payer not read'}")
    d: dict[str, Any] = {"payerName": payer or "Unknown payer", "isNominee": False, "box11": False}
    for box, rx in (("1a", r"^1a total ordinary"), ("1b", r"^1b qualified"), ("2a", r"^2a total capital gain"),
                    ("3", r"^3 nondividend"), ("4", r"^4 federal income tax"), ("5", r"^5 section 199a"),
                    ("7", r"^7 foreign tax paid"), ("12", r"^12 exempt-interest"), ("13", r"^13 specified private")):
        v = doc.amount(rx)
        _put(d, f"box{box}", v)
        _field(p, box, doc.box(rx).label if doc.box(rx) else box, v)
    country = doc.value(r"^8 foreign country")
    if country:
        d["box8"] = country
    d.setdefault("box1a", 0.0)
    if any(k != "box1a" and k.startswith("box") and isinstance(v, float) for k, v in d.items()) or d["box1a"]:
        p.inputs.append(("f1099div", d, p.label))

    # 1099-B lots: section headers name the term and the Form 8949 box.
    part, term, lots = None, None, []
    noncovered = any(re.search(r"noncovered security:\s*yes", l, re.I) for l in doc.lines)
    for line in doc.lines:
        head = re.search(r"(SHORT|LONG)-TERM", line)
        if head:
            term = head[1]
            box = re.search(r"8949 Box ([A-F])", line)
            part = box[1] if box else ("A" if term == "SHORT" else "D")
            continue
        m = LOT.match(line.strip())
        if m and part:
            desc, acq, sold, proceeds, cost, gain = m.groups()
            lot = {"part": part, "description": desc.strip(), "date_acquired": iso_date(acq) or "VARIOUS",
                   "date_sold": iso_date(sold), "proceeds": money(proceeds), "cost_basis": money(cost)}
            if noncovered:
                lot["noncovered_security"] = True
            if abs((lot["proceeds"] - lot["cost_basis"]) - money(gain)) > 0.01:
                p.warnings.append(f"{desc.strip()}: printed gain {gain} ≠ proceeds − cost; check for an adjustment.")
            lots.append(lot)
    if lots:
        p.label = f"1099-DIV / 1099-B · {payer or 'payer not read'}"
        wash = doc.amount(r"wash sale")
        if wash:
            p.warnings.append(f"Wash sale loss disallowed {wash:,.2f} is reported but not assigned to a lot; add it by hand.")
        for lot in lots:
            p.inputs.append(("f1099b", {**lot}, f"1099-B · {lot['description']}"))
        st = [l for l in lots if l["part"] in "ABC"]
        lt = [l for l in lots if l["part"] in "DEF"]
        for name, group in (("Short-term", st), ("Long-term", lt)):
            if group:
                net = sum(l["proceeds"] - l["cost_basis"] for l in group)
                _field(p, "1099-B", f"{name} lots ({len(group)})", round(net, 2))
    if not p.inputs:
        raise Refused("nothing_read", "No amounts were read from this 1099", "Check that it's a 1099-DIV or 1099-B.")
    return p


def parse_1098(doc: Doc) -> Parsed:
    lender = _first_line(doc, r"^(payer|recipient/lender|lender)'?s? name")
    p = Parsed("1098", f"1098 · {lender or 'lender not read'}")
    d: dict[str, Any] = {}
    _put(d, "lender_name", lender)
    interest = doc.amount(r"^1 mortgage interest")
    d["box1_mortgage_interest"] = interest or 0.0
    _field(p, "1", "Mortgage interest", interest)
    for box, rx, key in (("2", r"^2 outstanding mortgage principal", "box2_outstanding_principal"),
                         ("4", r"^4 refund of overpaid", "box4_refund_overpaid"),
                         ("5", r"^5 mortgage insurance", "box5_mip"), ("6", r"^6 points paid", "box6_points_paid")):
        v = doc.amount(rx)
        _put(d, key, v)
        _field(p, box, key.split("_", 1)[1].replace("_", " ").capitalize(), v)
    orig = iso_date(doc.value(r"^3 mortgage origination"))
    _put(d, "box3_origination_date", orig)
    _field(p, "3", "Origination date", orig)
    if (doc.value(r"^7 address of property") or "").upper().startswith("X"):
        d["box7_property_address_same"] = True
    n = doc.amount(r"^9 number of properties")
    if n:
        d["box9_number_of_properties"] = n
    b10 = doc.box(r"^10 other")
    if b10 and b10.value:
        d["box10_other"] = f"{b10.label.removeprefix('10').strip()} {b10.value}".strip()
    p.inputs.append(("f1098", d, p.label))
    # Box 10 often carries real estate taxes paid from escrow: they belong on Schedule A line 5b.
    if b10 and re.search(r"real estate tax|property tax", b10.label, re.I) and money(b10.value):
        tax = money(b10.value)
        p.inputs.append(("schedule_a", {"line_5b_real_estate_tax": tax}, f"Schedule A · real estate taxes ({lender})"))
        _field(p, "10", "Real estate taxes (Schedule A 5b)", tax)
    return p


# K-1 Part III: box label → OTD scalar key.
K1_SCALARS = {"1": "box_1", "2": "box_2", "3": "box_3", "4a": "box_4a", "4b": "box_4b", "4c": "box_4c", "5": "box_5",
              "6a": "box_6a", "6b": "box_6b", "6c": "box_6c", "7": "box_7", "8": "box_8", "9a": "box_9a",
              "9b": "box_9b", "9c": "box_9c", "10": "box_10", "12": "box_12", "21": "box_21"}
K1_CODED = {"11", "13", "14", "15", "17", "18", "19", "20"}
QBI_ROWS = {"ordinary business income": "qbi", "qbi": "qbi", "w-2 wages": "w2_wages", "ubia": "ubia",
            "section 199a dividends": "section_199a_dividends"}


def parse_k1(doc: Doc) -> Parsed:
    name_box = doc.box(r"^b partnership's name")
    partnership = name_box.lines[0] if name_box and name_box.lines else None
    p = Parsed("k1-1065", partnership or "K-1 · partnership not read")
    k1: dict[str, Any] = {"partnership": name_box.lines if name_box else [], "ein": doc.value(r"^a partnership's ein"),
                          "partner_tin": doc.value(r"^e partner's"), "partner": (doc.box(r"^f name") or Box("", [], 0)).lines,
                          "limited": "limited partner [x]" in " ".join(b.label.lower() for b in doc.boxes),
                          "scalars": {}, "coded": {}, "qbi": {}, "evidence": {}}

    def seen(path: str, b: Box | None) -> None:
        if b is not None and b.bbox:
            k1["evidence"][path] = {"page": b.page, "bbox": b.bbox, "status": "text_layer",
                                    "text": b.value or None, "method": "pdf-text-layer"}

    for item, rx in (("part_i.item_a", r"^a partnership's ein"), ("part_i.item_b", r"^b partnership's name"),
                     ("part_i.item_c", r"^c irs center"), ("part_ii.item_e", r"^e partner's"),
                     ("part_ii.item_f", r"^f name"), ("part_ii.item_g", r"^g general partner"),
                     ("part_ii.item_i1", r"^i1 what type"), ("part_ii.item_j", r"^j partner's share"),
                     ("part_ii.item_k1", r"^k1 share of liabilities"), ("part_ii.item_l", r"^l partner's capital"),
                     ("part_ii.item_m", r"^m did partner"), ("part_ii.item_n", r"^n net unrecognized")):
        seen(item, doc.box(rx))
    j = re.findall(r"([\d.]+)%", doc.value(r"^j partner's share") or "")
    if len(j) == 3:
        k1["share"] = [float(x) / 100 for x in j]
    cap = doc.box(r"^l partner's capital")
    if cap:
        vals = {k: money(v) for k, v in re.findall(r"(beginning|contributed|current yr income|withdrawals|ending)\D*?(\(?[\d,]+\.\d{2}\)?)",
                                                   " ".join(cap.lines), re.I)}
        k1["capital"] = {k.lower(): v for k, v in vals.items()}
    for b in doc.boxes:
        m = re.match(r"^(\d{1,2}[a-c]?)\s", b.label)
        if not m or b.page != 1:
            continue
        box = m[1]
        v = money(b.value) if b.value and b.value.upper() != "STMT" else None
        code = re.search(r"code ([A-Z]{1,2})\b", b.label, re.I)
        if box in K1_SCALARS and v is not None:
            k1["scalars"][K1_SCALARS[box]] = v
            seen(f"part_iii.{K1_SCALARS[box]}", b)
            _field(p, box, re.sub(r"^\S+\s+", "", b.label), v)
        elif box in K1_CODED and code and (v is not None or b.value.upper() == "STMT"):
            k1["coded"].setdefault(box, []).append({"code": code[1].upper(), "value": v, "statement": b.value.upper() == "STMT"})
            seen(f"part_iii.box_{box}", b)
            seen(f"part_iii.box_{box}.{code[1].upper()}", b)
            _field(p, f"{box}{code[1].upper()}", re.sub(r"^\S+\s+", "", b.label), v if v is not None else "see statement")
    for line in doc.lines:
        low = line.lower()
        for key, field_name in QBI_ROWS.items():
            if low.startswith(key):
                val = money(line[len(key):])
                if val is not None:
                    k1["qbi"][field_name] = val
        if low.startswith("sstb"):
            k1["qbi"]["sstb"] = "yes" in low.split("?", 1)[-1]
    if k1["qbi"]:
        _field(p, "20Z", "§199A statement", ", ".join(f"{k} {v:,.2f}" if isinstance(v, float) else f"{k} {v}"
                                                        for k, v in k1["qbi"].items()))
    if not k1["scalars"] and not k1["coded"]:
        raise Refused("nothing_read", "No Part III amounts were read from this K-1", "Check that Part III has values.")
    p.k1 = k1
    return p


RELATIONSHIPS = {"son", "daughter", "stepchild", "foster", "sibling", "stepsibling", "halfsibling", "grandchild",
                 "parent", "stepparent", "other"}
FILING = {"married filing jointly": "mfj", "married filing separately": "mfs", "single": "single",
          "head of household": "hoh", "qualifying surviving spouse": "qss"}
ORGANIZER_LABELS = ("Filing status", "Taxpayer", "Spouse", "Address", "Dependent", "Child care", "Dep. care FSA",
                    "Charitable - cash", "Charitable - noncash", "Estimated taxes", "Prior year", "HSA / IRA",
                    "Health coverage", "Crypto / digital assets", "Foreign accounts", "Direct deposit", "Anything else?")


def _organizer_rows(doc: Doc) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in doc.lines:
        hit = next((l for l in ORGANIZER_LABELS if line.startswith(l)), None)
        if hit:
            rest = line[len(hit):]
            num = re.match(r"\s*(\d+)\s", rest) if hit == "Dependent" else None
            rows.append((f"{hit} {num[1]}" if num else hit, (rest[num.end():] if num else rest).strip()))
        elif rows and not line.startswith(("2025 Client", "Completed by", "Organizer |", "Tax Year")):
            rows[-1] = (rows[-1][0], f"{rows[-1][1]} {line}".strip())
    return rows


def _person(text: str) -> dict:
    name = text.split(",")[0].split()
    out: dict[str, Any] = {"first_name": name[0], "last_name": name[-1]}
    if len(name) == 3 and len(name[1].rstrip(".")) == 1:
        out["middle_initial"] = name[1].rstrip(".")
    dob = re.search(r"DOB (\d{2}/\d{2}/\d{4})", text)
    if dob:
        out["dob"] = iso_date(dob[1])
    parts = [s.strip() for s in text.split(",")]
    if parts and not re.search(r"DOB|SSN|\d", parts[-1]):
        out["occupation"] = parts[-1]
    return out


def parse_organizer(doc: Doc) -> Parsed:
    p = Parsed("organizer", "Client organizer")
    general: dict[str, Any] = {}
    dependents, a, f2441 = [], {}, None
    for label, text in _organizer_rows(doc):
        low = text.lower()
        if label == "Filing status":
            fs = next((v for k, v in FILING.items() if k in low), None)
            if fs:
                general["filing_status"] = fs
            _field(p, "status", "Filing status", text)
        elif label in ("Taxpayer", "Spouse"):
            who = _person(text)
            pre = "taxpayer" if label == "Taxpayer" else "spouse"
            for k in ("first_name", "last_name", "middle_initial", "dob", "occupation"):
                if k in who:
                    general[f"{pre}_{k}"] = who[k]
            _field(p, pre, label, f"{who['first_name']} {who['last_name']}")
            p.label = f"Client organizer · {who['last_name']}" if label == "Taxpayer" else p.label
        elif label == "Address":
            m = re.match(r"(.+?),\s*(.+?),\s*([A-Z]{2})\s+(\d{5})", text)
            if m:
                general.update(address_line1=m[1], address_city=m[2], address_state=m[3], address_zip=m[4])
                _field(p, "address", "Address", f"{m[1]}, {m[2]}, {m[3]} {m[4]}")
        elif label.startswith("Dependent"):
            dep = _person(text)
            rel = next((r for r in RELATIONSHIPS if re.search(rf"\b{r}\b", low)), "other")
            months = re.search(r"(\d{1,2}) months", low)
            entry = {k: dep[k] for k in ("first_name", "last_name", "middle_initial", "dob") if k in dep}
            entry.update(relationship=rel, months_in_home=int(months[1]) if months else 12)
            if rel in ("son", "daughter", "stepchild", "foster", "grandchild"):
                entry["qualifying_child_for_ctc"] = True
            dependents.append(entry)
            _field(p, label.lower().replace(" ", ""), label, f"{dep['first_name']} {dep['last_name']} ({rel}, born {dep.get('dob')})")
        elif label == "Child care":
            amt = money(re.search(r"\$[\d,]+(?:\.\d{2})?", text)[0]) if "$" in text else None
            if amt:
                who = re.search(r"for (.+)$", text)
                count = len(re.split(r",| and ", who[1])) if who else 1
                f2441 = {"qualifying_expenses_paid": amt, "qualifying_person_count": count}
                for dep in dependents:
                    if who and dep["first_name"] in who[1]:
                        dep["child_care_months"] = 12
                _field(p, "2441", "Child care expenses", amt)
        elif label in ("Charitable - cash", "Charitable - noncash"):
            total = sum(money(x) or 0 for x in re.findall(r"\$[\d,]+(?:\.\d{2})?", text))
            if total:
                key = "line_11_cash_contributions" if label.endswith("cash") and "noncash" not in label else "line_12_noncash_contributions"
                a[key] = round(a.get(key, 0) + total, 2)
                _field(p, "A " + ("11" if key.startswith("line_11") else "12"), label.replace(" - ", ", "), total)
        elif label == "Crypto / digital assets":
            general["digital_assets"] = low.startswith("yes")
        elif label == "Estimated taxes" and re.search(r"\$\d", text):
            p.warnings.append(f"Estimated payments listed ({text}); enter them with set_return_inputs.")
        elif label in ("Prior year", "Direct deposit", "HSA / IRA", "Anything else?", "Dep. care FSA",
                       "Health coverage", "Foreign accounts"):
            if not re.fullmatch(r"(no|none)\.?", low):
                p.warnings.append(f"{label}: “{text}” is for the preparer; nothing was entered from it.")
    if "filing_status" not in general:
        raise Refused("nothing_read", "No filing status on this organizer", "The organizer needs a 'Filing status' row.")
    if dependents:
        general["dependents"] = dependents
    p.inputs.append(("start", {"general": general}, "Filing information (organizer)"))
    if f2441:
        p.inputs.append(("f2441", f2441, "Form 2441 · child care (organizer)"))
    if a:
        p.inputs.append(("schedule_a", a, "Schedule A · charity (organizer)"))
    return p


PARSERS = {"w2": parse_w2, "1099-int": parse_1099int, "1099-div": parse_1099div, "1098": parse_1098,
           "k1-1065": parse_k1, "organizer": parse_organizer}


def parse(path: Path) -> Parsed:
    doc = read(path)
    if not doc.marker:
        raise Refused("not_synthetic", "This doesn't look like a synthetic document",
                      "Only synthetic practice documents are accepted: the PDF must carry the SYNTHETIC watermark "
                      "or the 'Fictional document' footer. Never drop real taxpayer documents here.")
    form = classify(doc)
    if form is None:
        raise Refused("unsupported_form", "This form type isn't supported yet",
                      "Supported: W-2, 1099-INT, 1099-DIV/1099-B, 1098, Schedule K-1 (1065) and the client organizer.")
    return PARSERS[form](doc)


# ── K-1 → OTD ─────────────────────────────────────────────────────────────

def _template_entry(proof: dict, box_key: str, code: str) -> dict | None:
    for e in proof["body"]["part_iii"].get(box_key, {}).get("entries", []):
        if e.get("code") == code:
            return copy.deepcopy(e)
    return None


def otd_from_k1(k1: dict, created: str) -> dict:
    """An OTD K-1 document from parsed values, using the upstream proof document as the
    structural template (the same approach as the benchmark fixtures): every Part III
    amount starts null (blank on the form) and only what was read is filled in."""
    proof = yaml.safe_load(OTD_PROOF.read_text())
    doc = copy.deepcopy(proof)
    doc["otd"]["document_id"] = str(uuid.uuid4())
    doc["otd"]["created"] = created
    doc["otd"]["producer"] = {"name": "Drivkraft Tax source-document reader (text layer)", "version": "1"}
    body = doc["body"]
    ein = k1.get("ein") or ""
    body["part_i"]["item_a"]["value"] = ("XX-XXX" + ein[-4:]) if len(ein) >= 4 else None
    body["part_i"]["item_b"]["value"] = "\n".join(k1["partnership"]) or None
    body["part_i"]["item_c"]["value"] = "E-FILE"
    body["part_i"]["item_d"]["value"] = False
    ii = body["part_ii"]
    ii["item_e"]["value"] = k1.get("partner_tin")
    ii["item_f"]["value"] = "\n".join(k1["partner"]) or None
    ii["item_g"]["value"] = "limited_or_other_member" if k1["limited"] else "general_partner_or_llc_member_manager"
    ii["item_k3"]["value"] = False
    ii["item_m"]["value"] = False
    ii["item_m"].pop("statement", None)
    if k1.get("share"):
        p_, l_, c_ = k1["share"]
        ii["item_j"]["value"].update(profit_beginning=p_, profit_ending=p_, loss_beginning=l_, loss_ending=l_,
                                     capital_beginning=c_, capital_ending=c_)
    for key in ("nonrecourse", "qualified_nonrecourse", "recourse"):
        ii["item_k1"]["value"][f"{key}_beginning"] = 0.0
        ii["item_k1"]["value"][f"{key}_ending"] = 0.0
    cap = k1.get("capital") or {}
    if cap:
        ii["item_l"]["value"].update(beginning=cap.get("beginning"), contributions=cap.get("contributed", 0.0),
                                     current_year_increase_decrease=cap.get("current yr income"),
                                     other_increase_decrease=0.0, withdrawals=cap.get("withdrawals"),
                                     ending=cap.get("ending"))
    ii["item_n"]["value"] = {"beginning": 0.0, "ending": 0.0}
    for key, node in body["part_iii"].items():
        if node.get("type") == "coded":
            node["entries"] = []
        elif node.get("type") == "scalar":
            node["value"] = False if key in ("box_22", "box_23") else None
    for key, v in k1["scalars"].items():
        body["part_iii"][key]["value"] = v
    for box, entries in k1["coded"].items():
        key = f"box_{box}"
        for e in entries:
            node = _template_entry(proof, key, e["code"]) or {
                "code": e["code"], "semantic": {"id": f"{body['part_iii'][key]['semantic']['id']}.code_{e['code'].lower()}",
                                                "label": f"Code {e['code']}"}}
            node["value"] = e["value"]
            if box == "20" and e["code"] == "Z":
                content = node["statement"]["content"]
                q = k1.get("qbi") or {}
                content.update(qbi=q.get("qbi"), w2_wages=q.get("w2_wages"), ubia=q.get("ubia"),
                               sstb=q.get("sstb", False), business_name=(k1["partnership"] or [None])[0],
                               section_199a_dividends=q.get("section_199a_dividends"), patron_reduction=None)
            elif not e.get("statement"):
                node.pop("statement", None)
            body["part_iii"][key]["entries"].append(node)
    return doc
