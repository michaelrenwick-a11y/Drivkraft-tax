"""The review packet (Phase 7): one PDF a reviewer can read start to finish.

Sections: summary, the 1040, each K-1 (what's not in the calculation, flags and
their acknowledgements, every edit with its reason and PDF page), saved scenarios,
research answers with numbered citations, meeting notes with timestamped
decisions, the requested-documents checklist, and approved follow-up emails.
Geist (SIL OFL, server/fonts) keeps it in the app's type.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

FONTS = Path(__file__).parent / "fonts"
INK, MUTED, LINE, FAINT = (15, 23, 42), (71, 85, 105), (203, 213, 225), (241, 245, 249)
WARN, ERR, OK, SKY, VIOLET = (180, 83, 9), (190, 18, 60), (21, 128, 61), (3, 105, 161), (109, 40, 217)
FS_LABELS = {"single": "Single", "mfj": "Married filing jointly", "mfs": "Married filing separately",
             "hoh": "Head of household", "qss": "Qualifying surviving spouse"}
HEADLINE_LABELS = {"line11_agi": "Adjusted gross income", "line15_taxable_income": "Taxable income",
                   "line24_total_tax": "Total tax", "line33_total_payments": "Total payments",
                   "line35a_refund": "Refund", "line37_amount_owed": "Amount owed"}
DISPOSITION = {"mapped": "In calculation", "collapsed": "In calculation (combined)", "derived": "Derived",
               "unsupported": "Not in calculation", "informational": "Information only"}


def money(v: Any, cents: bool = False) -> str:
    """K-1 amounts are whole dollars; 1040 lines carry cents (cents=True keeps a column aligned)."""
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (int, float)):
        s = f"{abs(v):,.0f}" if float(v).is_integer() and not cents else f"{abs(v):,.2f}"
        return f"({s})" if v < 0 else s
    return str(v).split("\n")[0]


def when(ts: str | None) -> str:
    return (ts or "").replace("T", " ").removesuffix("Z")[:16] + (" UTC" if ts else "")


def plain(md: str) -> list[tuple[str, str]]:
    """Markdown → (kind, text) blocks: heading, bullet or para. Bold markers are kept for fpdf's markdown."""
    out: list[tuple[str, str]] = []
    para: list[str] = []

    def flush():
        if para:
            out.append(("para", " ".join(para)))
            para.clear()

    for line in md.splitlines():
        s = line.strip()
        if not s:
            flush()
        elif m := re.match(r"#{1,6}\s+(.*)", s):
            flush()
            out.append(("heading", m[1].replace("**", "")))
        elif m := re.match(r"(?:[-*•]|\d+[.)])\s+(.*)", s):
            flush()
            out.append(("bullet", m[1]))
        else:
            para.append(s)
    flush()
    return out


class Packet(FPDF):
    def __init__(self, case: dict, version: int):
        super().__init__(format="letter", unit="pt")
        self.case, self.version = case, version
        self.add_font("Geist", "", FONTS / "Geist-Regular.ttf")
        self.add_font("Geist", "B", FONTS / "Geist-SemiBold.ttf")
        self.add_font("Mono", "", FONTS / "GeistMono-Regular.ttf")
        self.set_margins(54, 60, 54)
        self.set_auto_page_break(True, 54)
        self.set_title(f"{case['name']} · review packet v{version}")
        self.set_author("Drivkraft Tax (practice build)")
        self.set_creator("Drivkraft Tax")
        self.alias_nb_pages()

    # page furniture
    def header(self):
        self.set_y(28)
        self.set_font("Geist", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 10, f"{self.case['name']} · Review packet v{self.version}", new_x=XPos.LEFT)
        self.cell(0, 10, "Synthetic data · practice build", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*LINE)
        self.line(self.l_margin, 42, self.w - self.r_margin, 42)
        self.set_y(60)

    def footer(self):
        self.set_y(-36)
        self.set_font("Geist", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 10, f"Page {self.page_no()} of {{nb}}", align="C")

    # building blocks
    @property
    def width(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def h1(self, text: str):
        self.add_page()
        self.set_font("Geist", "B", 16)
        self.set_text_color(*INK)
        self.cell(0, 22, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)

    def h2(self, text: str, *, gap: float = 10):
        if self.get_y() > self.h - 140:
            self.add_page()
        self.ln(gap)
        self.set_font("Geist", "B", 11.5)
        self.set_text_color(*INK)
        self.multi_cell(0, 15, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def para(self, s: str, *, size: float = 9.5, color=MUTED, md: bool = False, indent: float = 0, h: float = 13.5):
        self.set_font("Geist", "", size)
        self.set_text_color(*color)
        self.set_x(self.l_margin + indent)
        self.multi_cell(self.width - indent, h, s, markdown=md, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def label_value(self, rows: list[tuple[str, str]]):
        for k, v in rows:
            self.set_font("Geist", "", 9)
            self.set_text_color(*MUTED)
            self.cell(120, 14, k)
            self.set_text_color(*INK)
            self.multi_cell(self.width - 120, 14, v, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def pill(self, text: str, color):
        self.set_font("Geist", "B", 8)
        self.set_text_color(*color)
        self.set_draw_color(*color)
        w = self.get_string_width(text) + 12
        self.cell(w, 14, text, border=1, align="C", new_x=XPos.RIGHT)
        self.cell(6, 14, "")

    def grid(self, head: list[str], rows: list[list[str]], widths: tuple, align: str | tuple = "LEFT",
             mono_cols: tuple = ()):
        if not rows:
            return
        self.set_font("Geist", "", 8.5)
        self.set_text_color(*INK)
        self.set_draw_color(*LINE)
        aligns = align if isinstance(align, tuple) else tuple(align for _ in head)
        with self.table(col_widths=widths, text_align=aligns, line_height=12, padding=(3, 4),
                        borders_layout="HORIZONTAL_LINES", headings_style=FontFace("Geist", "B", 8.5, MUTED, FAINT),
                        first_row_as_headings=True, width=self.width) as t:
            t.row(head)
            for r in rows:
                row = t.row()
                for i, v in enumerate(r):
                    row.cell(v, style=FontFace("Mono", "", 8) if i in mono_cols else None)
        self.ln(4)


# ── Sections ──────────────────────────────────────────────────────────────

def build(snap: dict, version: int) -> tuple[bytes, dict]:
    case = snap["case"]
    pdf = Packet(case, version)
    sections: list[str] = []

    # Cover
    pdf.add_page()
    pdf.set_font("Geist", "B", 22)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 28, case["name"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.para(f"Review packet v{version} · Tax year {case['tax_year']} · {FS_LABELS.get(case['filing_status'], case['filing_status'])}",
             size=11)
    pdf.ln(10)
    k1s = snap["k1s"]
    approved = sum(1 for k in k1s if k["status"] == "approved")
    edits = sum(len(k["edits"]) for k in k1s)
    open_docs = sum(1 for c in snap["checklist"] if c["status"] == "open")
    pdf.label_value([
        ("Generated", when(snap["generated"])),
        ("K-1s", f"{len(k1s)} ({approved} approved)" + (f", {len(snap['skipped'])} still extracting or failed" if snap["skipped"] else "")),
        ("Edits", f"{edits} value{'s' if edits != 1 else ''} corrected by a reviewer"),
        ("Scenarios", str(len(snap["scenarios"]))),
        ("Research", f"{len(snap['research'])} question{'s' if len(snap['research']) != 1 else ''}"),
        ("Meetings", f"{len(snap['notes'])} note{'s' if len(snap['notes']) != 1 else ''}"),
        ("Requested documents", f"{len(snap['checklist'])} ({open_docs} open)"),
    ])
    pdf.ln(12)
    pdf.set_draw_color(*LINE)
    pdf.set_fill_color(*FAINT)
    pdf.set_font("Geist", "", 8.5)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 12, "Synthetic data only. Drivkraft Tax is a practice build that joins the open-source OTD "
                          "K-1 extractor to the OpenTax 1040 engine. It is not tax software, and nothing here is advice. "
                          "Cached research answers were written for the demo and are labeled as such.",
                   border=1, fill=True, padding=8, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    ret = snap["return"]
    # The 1040
    pdf.h1("Return summary")
    sections.append("return")
    if ret:
        hl = [[HEADLINE_LABELS[k], money(v, True)] for k, v in ret["headline"].items() if k in HEADLINE_LABELS]
        pdf.grid(["", "Amount"], hl, (3, 1), align=("LEFT", "RIGHT"))
        for cv in ret["caveats"]:
            color = {"error": ERR, "warning": WARN}.get(cv["severity"], SKY)
            pdf.para(f"**{cv['message']}** {cv['fix_hint']}", color=color, md=True)
        if ret["included"]:
            k1_names = "; ".join(snap_name(i["label"]).rstrip(".") if i["label"] else i["doc_id"] for i in ret["included"])
            others = "; ".join(i["label"] for i in ret["other_inputs"])
            pdf.para(f"Included: {k1_names}." + (f" Other inputs: {others}." if others else ""), size=8.5)
        pdf.h2("Form 1040 lines")
        pdf.grid(["Line", "Description", "Amount"], [[l["line"], l["label"], money(l["value"], True)] for l in ret["lines"]],
                 (1, 6, 2), align=("LEFT", "LEFT", "RIGHT"))
    else:
        pdf.para(f"No calculation: {snap['return_error'] or 'nothing approved yet'}.")

    # K-1s
    for k in k1s:
        pdf.h1(k["name"])
        sections.append(f"k1:{k['id']}")
        pdf.set_x(pdf.l_margin)
        st = {"approved": ("Approved", OK), "needs_review": ("In review", SKY), "blocked": ("Blocked", ERR)}.get(
            k["status"], (k["status"], MUTED))
        pdf.pill(*st)
        if k["bridge_status"] == "refused":
            pdf.pill("Bridge refused", ERR)
        pdf.ln(20)
        pdf.label_value([("Document", k["id"] + (" · PDF intake" if k["source_kind"] == "pdf" else " · OTD document")),
                         ("Approved", when(k["approved_at"]) if k["approved_at"] else "Not yet")])
        for e in k["errors"]:
            pdf.para(f"**Error at {e.get('path') or 'document'}:** {e['message']}", color=ERR, md=True)

        missing = [e for e in k["entries"] if e["disposition"] == "unsupported" and e["value"] not in (None, False, 0)]
        if missing:
            pdf.h2("Not in the calculation")
            pdf.para("OpenTax has no input for these amounts, so the 1040 leaves them out.", size=8.5)
            pdf.grid(["Box", "Description", "Amount", "PDF"],
                     [[e["label"], e["description"] or "", money(e["value"]), f"p. {e['page']}" if e["page"] else "—"]
                      for e in missing], (2, 6, 2, 1), align=("LEFT", "LEFT", "RIGHT", "RIGHT"))

        flags = [f for f in k["flags"]]
        if flags:
            pdf.h2("Reviewer flags")
            rows = []
            for f in flags:
                ack = f["acknowledged"]
                status = f"Acknowledged {when(ack['at'])}" + (f": {ack['note']}" if ack and ack.get("note") else "") \
                    if ack else ("Needs acknowledging" if f["ack_required"] else "For information")
                rows.append([f.get("path") and label_of(k, f["path"]) or "Document", f["message"], status])
            pdf.grid(["Box", "Flag", "Status"], rows, (2, 6, 3))

        pdf.h2("Edits")
        if k["edits"]:
            pages = {e["path"]: e["page"] for e in k["entries"]}
            pdf.grid(["Box", "From", "To", "Reason", "When", "PDF"],
                     [[label_of(k, e["path"]), money(e["old_value"]), money(e["new_value"]), e["reason"],
                       when(e["created"]), f"p. {pages[e['path']]}" if pages.get(e["path"]) else "—"] for e in k["edits"]],
                     (2, 2, 2, 5, 2.4, 1), align=("LEFT", "RIGHT", "RIGHT", "LEFT", "LEFT", "RIGHT"))
        else:
            pdf.para("No edits: every value is as extracted.")

        present = [e for e in k["entries"] if e["path"].startswith("part_iii") and e["value"] not in (None, False)]
        if present:
            pdf.h2("Part III values")
            pdf.grid(["Box", "Description", "Amount", "Treatment"],
                     [[e["label"] + (" *" if e["edited"] else ""), e["description"] or "", money(e["value"]),
                       DISPOSITION.get(e["disposition"], e["disposition"])] for e in present],
                     (2, 6, 2, 3), align=("LEFT", "LEFT", "RIGHT", "LEFT"))
            if any(e["edited"] for e in present):
                pdf.para("* Edited by a reviewer (see Edits).", size=8)

    # Scenarios
    if snap["scenarios"]:
        pdf.h1("Scenarios")
        sections.append("scenarios")
        for s in snap["scenarios"]:
            pdf.h2(s["name"], gap=4)
            if s.get("applied"):
                pdf.para("; ".join(a["label"] for a in s["applied"]) + ".", size=8.5)
            if s.get("error"):
                pdf.para(s["error"], color=WARN)
            rows = [[r["line"], r["label"], money(r["base"], True), money(r["scenario"], True),
                     ("+" if r["delta"] > 0 else "") + money(r["delta"], True)] for r in s.get("lines") or []]
            pdf.grid(["Line", "Description", "Return", "Scenario", "Change"], rows, (1, 5, 2, 2, 2),
                     align=("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT"))

    # Research
    if snap["research"]:
        pdf.h1("Research")
        sections.append("research")
        for q in snap["research"]:
            pdf.h2(q["question"], gap=4)
            pdf.set_x(pdf.l_margin)
            if q["cached"]:
                pdf.pill("Cached · written for this demo", VIOLET)
            else:
                pdf.pill(f"Live Bizora · ${q['cost_usd']:.2f}", SKY)
            pdf.pill(q["mode"], MUTED)
            pdf.ln(20)
            for kind, s in plain(q["answer"]):
                if kind == "heading":
                    pdf.para(f"**{s}**", color=INK, md=True)
                elif kind == "bullet":
                    pdf.para(f"•  {s}", color=INK, md=True, indent=10)
                else:
                    pdf.para(s, color=INK, md=True)
                pdf.ln(2)
            if q["citations"]:
                pdf.para("**Citations**", color=INK, md=True, size=9)
                for i, c in enumerate(q["citations"], 1):
                    line = f"[{i}] {c['label']}" + (f" · {c['authority']}" if c.get("authority") and c["authority"] not in c["label"] else "")
                    pdf.para(line, size=8.5, indent=4)
                    if c.get("url"):
                        pdf.set_font("Geist", "", 8)
                        pdf.set_text_color(*SKY)
                        pdf.set_x(pdf.l_margin + 18)
                        pdf.multi_cell(pdf.width - 18, 11, c["url"], link=c["url"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            if q["cached"]:
                pdf.para("Cached demo answer written for this practice build, not a live Bizora response. Check the "
                         "linked authorities before relying on it.", size=8, color=VIOLET)

    # Meeting notes
    if snap["notes"]:
        pdf.h1("Meeting notes")
        sections.append("notes")
        for n in snap["notes"]:
            pdf.h2(n["title"], gap=4)
            meta = " · ".join(x for x in (n["meeting_date"], ", ".join(n["attendees"])) if x)
            if meta:
                pdf.para(meta, size=8.5)
            if not n["analyzed"]:
                pdf.para("Not analyzed yet.")
                continue
            if n["summary"]:
                pdf.para(n["summary"], color=INK)
            if n["decisions"]:
                pdf.ln(2)
                timed = all(d["at"] and ":" in d["at"] for d in n["decisions"])
                ds = sorted(n["decisions"], key=lambda d: d["at"].zfill(8)) if timed else n["decisions"]
                pdf.grid(["At", "Decision"], [[d["at"] or "—", d["text"]] for d in ds], (1, 8),
                         mono_cols=(0,))

    # Checklist
    if snap["checklist"]:
        pdf.h1("Requested documents")
        sections.append("checklist")
        pdf.grid(["Document", "Status", "Requested in"],
                 [[c["item"] + (f"\n{c['detail']}" if c["detail"] else ""), "Received" if c["status"] == "received" else "Open",
                   c["from"] or "—"] for c in snap["checklist"]], (6, 1.5, 3.5))

    # Follow-ups
    if snap["follow_ups"]:
        pdf.h1("Follow-up emails")
        sections.append("follow_ups")
        for f in snap["follow_ups"]:
            pdf.h2(f["subject"] or "Follow-up", gap=4)
            pdf.para(" · ".join(x for x in (f"From {f['note']}" if f["note"] else None,
                                            f"approved {when(f['approved'])}" if f["approved"] else None) if x), size=8.5)
            pdf.ln(2)
            pdf.para(f["body"] or "", color=INK)

    return bytes(pdf.output()), {"sections": sections, "pages": pdf.page_no()}


def snap_name(label: str) -> str:
    from .snapshot import display_name
    return display_name(label)


def label_of(k1: dict, path: str) -> str:
    from . import k1doc
    try:
        return k1doc.box_label(path)
    except Exception:
        return path
