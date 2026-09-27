"""One K-1 document on disk: OTD versions, edits, evidence and page images.

    docs/<doc_id>/
      source.pdf              (PDF intake only)
      artifacts/run-<n>/      upstream run_demo.py output, untouched
      work/run-<n>/           upstream intermediates; evidence/face-page.json lives here
      original.otd.yaml       the OTD as extracted (never modified)
      current.otd.yaml        original + edits.jsonl applied
      edits.jsonl             one JSON line per edit (also in SQLite)
      evidence.json           face evidence re-keyed by OTD path
      bridge.json             bridge result for current.otd.yaml
      approved.otd.yaml       frozen copy at approval
      pages/p<n>.png          rendered pages (lazily)

OTD paths are the canonical reference everywhere: `part_iii.box_1`,
`part_iii.box_11.A`, `part_iii.box_11.A[1]` (second A entry),
`part_iii.box_20.Z.statement.qbi`, `part_i.item_b`.
"""
from __future__ import annotations

import copy
import json
import re
import threading
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from .bridge import translator
from .errors import ToolFailure

PAGE_SCALE = 2.0            # rendered PNG pixels per PDF point
PATH_RE = re.compile(r"^(part_i{1,3})\.(\w+)(?:\.([A-Z]{1,2}|\*)(?:\[(\d+)\])?)?(?:\.statement\.(\w+))?$")


# ── Paths ─────────────────────────────────────────────────────────────────

def parse_path(path: str) -> tuple[str, str, str | None, int, str | None]:
    """(part, key, code, occurrence, statement_key) for an OTD path, or a located error."""
    m = PATH_RE.match(path.strip())
    if not m:
        raise ToolFailure("bad_path", f"{path!r} isn't an OTD path",
                          "Use a path like part_iii.box_1, part_iii.box_11.A or part_i.item_b (see read_k1).")
    part, key, code, occ, skey = m.groups()
    if translator.taxonomy_node(part, key) is None:
        raise ToolFailure("bad_path", f"{part}.{key} is not in the K-1 taxonomy",
                          "Check the box name; read_k1 lists every box on this K-1.")
    return part, key, code, int(occ or 0), skey


def normalize_box(box: str, code: str | None = None) -> str:
    """Accept '1', 'Box 11', 'box_11', '11A', 'B', 'item_b' or a full OTD path; return an OTD path."""
    b = box.strip()
    if b.startswith("part_"):
        return b if not code else f"{b}.{code.upper()}"
    b = re.sub(r"^(box|item)\s*_?", "", b, flags=re.I).strip()
    m = re.fullmatch(r"(\d{1,2})([a-c])?\s*([A-Z]{1,2})?", b, flags=re.I)
    if m:
        num, suffix, c = m.group(1), (m.group(2) or "").lower(), (m.group(3) or "")
        if suffix and not translator.taxonomy_node("part_iii", f"box_{num}{suffix}"):
            num, c = num, suffix + c          # "11A" is Box 11 code A; "6a" is Box 6a
        else:
            num += suffix
        c = code or c
        if translator.taxonomy_node("part_iii", f"box_{num}"):
            return f"part_iii.box_{num}" + (f".{c.upper()}" if c else "")
    item = f"item_{b.lower()}"
    for part in ("part_i", "part_ii"):
        if translator.taxonomy_node(part, item):
            return f"{part}.{item}"
    raise ToolFailure("bad_box", f"{box!r} isn't a K-1 box or item",
                      "Use a box number like 1, 6a or 20 (with code Z), or an item letter like B or K1.")


def box_label(path: str) -> str:
    """Human label for a path: 'Box 11 A', 'Item B', 'Box 20 Z · qbi'."""
    part, key, code, occ, skey = parse_path(path)
    base = f"Item {key.removeprefix('item_').upper()}" if key.startswith("item_") else f"Box {key.removeprefix('box_')}"
    if code:
        base += f" {code}" + (f" (#{occ + 1})" if occ else "")
    if skey:
        base += f" · {skey.replace('_', ' ')}"
    return base


# ── OTD documents and edits ───────────────────────────────────────────────

def load_otd(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump_otd(doc: dict, path: Path) -> None:
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _locate(doc: dict, path: str) -> tuple[dict, str]:
    """(container, key) holding the value at `path` in an OTD document."""
    part, key, code, occ, skey = parse_path(path)
    node = ((doc.get("body") or {}).get(part) or {}).get(key)
    if node is None:
        raise ToolFailure("path_not_on_k1", f"{part}.{key} isn't on this K-1",
                          "Only boxes present on the extracted K-1 can be edited. Check read_k1 for what's there.",
                          status=404)
    if node.get("type") == "coded":
        if not code:
            raise ToolFailure("code_required", f"{box_label(path)} is a coded box; name the code",
                              f"Use a path like {part}.{key}.A.")
        matches = [e for e in node.get("entries") or [] if str(e.get("code")) == code]
        if occ >= len(matches):
            raise ToolFailure("path_not_on_k1", f"{box_label(path)} has no entry at {path}",
                              "Check read_k1 for the codes present in this box.", status=404)
        entry = matches[occ]
        if skey:
            content = (entry.get("statement") or {}).get("content")
            if not isinstance(content, dict) or skey not in content:
                raise ToolFailure("path_not_on_k1", f"No statement field {skey!r} at {path}",
                                  "Check read_k1 for this entry's statement fields.", status=404)
            return content, skey
        return entry, "value"
    if code or skey:
        raise ToolFailure("bad_path", f"{part}.{key} is not a coded box", f"Use {part}.{key} without a code.")
    return node, "checked" if node.get("type") == "reference" else "value"


def get_value(doc: dict, path: str) -> Any:
    container, k = _locate(doc, path)
    return container.get(k)


def coerce(value: Any, current: Any) -> Any:
    """Parse an edited value the way the K-1 means it: '1,250' → 1250, '(300)' → -300, 'null' → None."""
    if value is None or (isinstance(value, str) and value.strip().lower() in ("", "null", "none")):
        return None
    if isinstance(current, bool) or isinstance(value, bool):
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in ("true", "yes", "x", "checked"):
            return True
        if s in ("false", "no", "unchecked"):
            return False
        raise ToolFailure("not_boolean", f"{value!r} isn't true/false", "This box is a checkbox; send true or false.")
    if isinstance(current, str) and not _looks_numeric(value):
        return str(value)
    if isinstance(value, (int, float)):
        return _num(Decimal(str(value)))
    s = str(value).strip().replace(",", "").replace("$", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        d = Decimal(s)
    except InvalidOperation:
        if current is None or isinstance(current, str):
            return str(value)
        raise ToolFailure("not_numeric", f"{value!r} isn't an amount", "Send a number such as 1250 or (300) for a loss.")
    return _num(-d if neg else d)


def _looks_numeric(v: Any) -> bool:
    return bool(re.fullmatch(r"\s*\(?-?\$?[\d,]+(\.\d+)?\)?\s*", str(v)))


def _num(d: Decimal) -> int | float:
    return int(d) if d == d.to_integral_value() else float(d)


def apply_edits(original: dict, edits: list[dict]) -> dict:
    doc = copy.deepcopy(original)
    for e in edits:
        container, k = _locate(doc, e["path"])
        container[k] = e["new_value"]
        # A human edit verifies the value: drop the extractor's unverified markers on that node.
        holder = container if k in ("value", "checked") else None
        if holder is not None:
            for mk in [m for m in holder if str(m).startswith("_unverified")]:
                holder.pop(mk)
    return doc


# ── Evidence ──────────────────────────────────────────────────────────────

def _face_key_to_path(key: str) -> str | None:
    if key.startswith("box_"):
        return f"part_iii.{key}"
    if key.startswith("item_") and "." not in key:
        for part in ("part_i", "part_ii"):
            if translator.taxonomy_node(part, key):
                return f"{part}.{key}"
    return None


def build_evidence(face: dict) -> dict:
    """Re-key upstream face evidence (face-page.json) by OTD path.

    Coded rows get their own entry per code (`part_iii.box_11.A`) with the row's
    bbox; the box itself keeps the whole-box bbox. Coordinates stay in PDF
    points with a top-left origin, as upstream emits them.
    """
    out: dict[str, dict] = {}
    for key, f in (face.get("fields") or {}).items():
        path = _face_key_to_path(key)
        if not path:
            continue
        base = {"page": f.get("page"), "bbox": f.get("bbox"), "status": f.get("status"),
                "text": f.get("raw_text") if f.get("raw_text") != "interior_verified_empty" else None,
                "method": f.get("method")}
        out[path] = base
        rows = f.get("normalized_value")
        if isinstance(rows, list):
            seen: dict[str, int] = {}
            for r in rows:
                code = str(r.get("code"))
                if code == "*":
                    continue
                n = seen.get(code, 0)
                seen[code] = n + 1
                out[f"{path}.{code}" + (f"[{n}]" if n else "")] = {
                    **base, "bbox": r.get("bbox") or base["bbox"], "text": r.get("raw_text")}
    pages = {"count": None, "size": None}
    return {"coordinate_frame": "pdf_top_left_origin_points", "pages": pages, "fields": out}


def evidence_for(evidence: dict, path: str) -> dict | None:
    """Evidence for a path. `match` says how close it is: exact, entry (a statement
    field or repeated code falls back to its entry) or box (the code isn't on the
    face, so this is the whole box, usually a "* STMT" pointer)."""
    fields = evidence.get("fields") or {}
    if path in fields:
        return {**fields[path], "match": "exact"}
    p = re.sub(r"\[\d+\]$", "", path.split(".statement.")[0])
    if p in fields:
        return {**fields[p], "match": "entry"}
    box = ".".join(p.split(".")[:2])
    return {**fields[box], "match": "box"} if box in fields else None


# PDFium isn't thread-safe: two threads in it at once (page renders, demo sandbox
# seeding in the background) crash the process. Every call goes through this lock,
# and pages/bitmaps are closed inside it rather than left to the garbage collector.
_PDFIUM = threading.Lock()


def page_info(pdf: Path) -> dict:
    import pypdfium2 as pdfium
    with _PDFIUM:
        pdf_doc = pdfium.PdfDocument(str(pdf))
        try:
            sizes = []
            for i in range(len(pdf_doc)):
                pg = pdf_doc[i]
                sizes.append(list(pg.get_size()))
                pg.close()          # closed here, not by a finalizer in some other thread later
        finally:
            pdf_doc.close()
    return {"count": len(sizes), "sizes": sizes}


def render_page(pdf: Path, page: int, out_dir: Path) -> Path:
    """PNG of one page (1-based), cached on disk."""
    out = out_dir / f"p{page}.png"
    if out.exists():
        return out
    import pypdfium2 as pdfium
    with _PDFIUM:
        pdf_doc = pdfium.PdfDocument(str(pdf))
        try:
            if not 1 <= page <= len(pdf_doc):
                raise ToolFailure("page_out_of_range", f"Page {page} doesn't exist (the PDF has {len(pdf_doc)})",
                                  "Pages are numbered from 1.", status=404)
            pg = pdf_doc[page - 1]
            bitmap = pg.render(scale=PAGE_SCALE)
            img = bitmap.to_pil().copy()     # to_pil shares the bitmap's memory; copy before freeing it
            bitmap.close()
            pg.close()
        finally:
            pdf_doc.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.png")
    img.save(tmp, optimize=True)
    tmp.replace(out)
    return out


def read_json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)
