"""SQLite + case folders (planning/02, "Case folder" and "SQLite tables").

SQLite holds the index (cases, documents, edits, events); files under
data/cases/<case_id>/ hold the artifacts. Both the stdio MCP process and the
HTTP server open the same database, so every write is a short transaction.
"""
from __future__ import annotations

import json
import secrets
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import paths
from .visitor import current as _visitor

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  tax_year INTEGER NOT NULL,
  filing_status TEXT NOT NULL,
  read_only INTEGER NOT NULL DEFAULT 0,
  description TEXT,
  owner TEXT,                      -- demo visitor id; NULL: reference case or local use
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id),
  kind TEXT NOT NULL,              -- k1
  sample TEXT,                     -- bundled sample id it came from
  source_kind TEXT NOT NULL,       -- pdf | otd
  label TEXT,                      -- partnership name once known
  status TEXT NOT NULL,            -- extracting | failed | needs_review | blocked | approved
  progress TEXT,                   -- JSON: intake stages
  acknowledged TEXT NOT NULL DEFAULT '{}',   -- JSON: flag path → {note, at}
  approved_at TEXT,
  created TEXT NOT NULL,
  updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id TEXT NOT NULL REFERENCES documents(id),
  path TEXT NOT NULL,
  old_value TEXT,                  -- JSON
  new_value TEXT,                  -- JSON
  reason TEXT NOT NULL,
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inputs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id TEXT NOT NULL REFERENCES cases(id),
  node_type TEXT NOT NULL,
  data TEXT NOT NULL,              -- JSON
  label TEXT,
  source_id TEXT,                  -- the dropped source document it came from (NULL: set_return_inputs)
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_docs (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id),
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  form TEXT,                       -- w2 | 1099-int | 1099-div | 1098 | k1-1065 | organizer (NULL when refused early)
  label TEXT,
  status TEXT NOT NULL,            -- added | k1 (see doc_id) | refused
  fields TEXT NOT NULL DEFAULT '[]',        -- JSON: [{box, label, value}] as read from the PDF
  warnings TEXT NOT NULL DEFAULT '[]',      -- JSON
  error TEXT,                      -- JSON: {code, message, fix_hint} when refused
  doc_id TEXT,                     -- the K-1 document a K-1 became
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenarios (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id),
  name TEXT NOT NULL,
  changes TEXT NOT NULL,           -- JSON: run_scenario changes
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proposals (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id),
  doc_id TEXT REFERENCES documents(id),     -- k1_edit only
  kind TEXT NOT NULL,              -- k1_edit | doc_request | scenario | research_question | follow_up
  path TEXT,                       -- k1_edit only
  old_value TEXT,                  -- JSON: value when proposed
  new_value TEXT,                  -- JSON
  payload TEXT NOT NULL DEFAULT '{}',       -- JSON: kind-specific fields (e.g. scenario changes)
  result TEXT,                     -- JSON: what an accept made (checklist id, scenario id, research id)
  note_id TEXT,                    -- the meeting note it came from
  rationale TEXT NOT NULL,
  citations TEXT NOT NULL DEFAULT '[]',     -- JSON: sources[] the proposal relies on
  origin TEXT NOT NULL,            -- chat | mcp | http
  status TEXT NOT NULL,            -- pending | accepted | rejected
  edit_id INTEGER,                 -- the edit an accept made
  created TEXT NOT NULL,
  resolved TEXT
);
CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id),
  kind TEXT NOT NULL,              -- typed | transcript | dictated
  title TEXT NOT NULL,
  meeting_date TEXT,               -- YYYY-MM-DD
  attendees TEXT NOT NULL DEFAULT '[]',     -- JSON
  text TEXT NOT NULL,
  segments TEXT NOT NULL,          -- JSON: [{i, t, speaker, text}], t in seconds or null
  sample TEXT,                     -- bundled sample transcript it came from
  analysis TEXT,                   -- JSON: the last analyze_meeting result
  analyzed_at TEXT,
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checklist (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id),
  item TEXT NOT NULL,
  detail TEXT,
  status TEXT NOT NULL,            -- open | received
  source_ref TEXT,                 -- e.g. note://…#t=…
  proposal_id TEXT,
  created TEXT NOT NULL,
  updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research (
  id TEXT PRIMARY KEY,
  case_id TEXT REFERENCES cases(id),   -- null: not tied to a case
  question TEXT NOT NULL,
  mode TEXT NOT NULL,              -- fast | deep
  answer TEXT NOT NULL,            -- markdown with [n] citation markers
  citations TEXT NOT NULL,         -- JSON: [{label, authority, url, snippet}]
  steps TEXT NOT NULL DEFAULT '[]',         -- JSON: Bizora's research steps
  cached INTEGER NOT NULL,         -- 1: answered from the demo cache
  cache_id TEXT,
  cost_usd REAL NOT NULL,
  origin TEXT NOT NULL,            -- mcp | http | chat
  owner TEXT,                      -- demo visitor id (research not tied to a case)
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outputs (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id),
  kind TEXT NOT NULL,              -- workpaper | packet
  version INTEGER NOT NULL,        -- per case and kind: v1, v2…
  file TEXT NOT NULL,              -- path under the case folder
  meta TEXT NOT NULL DEFAULT '{}', -- JSON: counts, fingerprint, sections
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS changesets (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id),
  workpaper_id TEXT NOT NULL,      -- the export the workbook came from
  filename TEXT,
  status TEXT NOT NULL,            -- pending | applied | discarded
  items TEXT NOT NULL,             -- JSON: cell-level changes (server/workpaper.py)
  warnings TEXT NOT NULL DEFAULT '[]',
  created TEXT NOT NULL,
  resolved TEXT
);
CREATE TABLE IF NOT EXISTS filings (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id),
  number INTEGER NOT NULL,         -- per case: submission 1, 2…
  status TEXT NOT NULL,            -- ready | approved | signed | queued | transmitted | accepted | rejected | void
  fingerprint TEXT NOT NULL,       -- the calculation's form set when exported (stale once it changes)
  xml_file TEXT NOT NULL,          -- path under the case folder (the signed XML once signed)
  sha256 TEXT NOT NULL,            -- of xml_file; locked at signing
  filer TEXT NOT NULL,             -- JSON: name, masked SSN, name control
  checks TEXT NOT NULL,            -- JSON: pre-checks and OpenTax validator findings (server/efile.py)
  signature TEXT,                  -- JSON: Form 8879 (masked PIN, prior-year AGI, signed_at)
  submission TEXT,                 -- JSON: FakeTransmitter manifest, acknowledgement and rejects
  timeline TEXT NOT NULL,          -- JSON: [{status, at, detail}]
  created TEXT NOT NULL,
  updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS efile_db (
  case_id TEXT PRIMARY KEY REFERENCES cases(id),   -- the fake IRS e-File database, one synthetic taxpayer per case
  ssn TEXT NOT NULL,
  name_control TEXT NOT NULL,
  prior_year_agi INTEGER NOT NULL,
  enrolled TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,              -- chat | meeting_analysis
  model TEXT,
  input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0,
  cache_write_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd REAL,                   -- estimate (server/pricing.py); null for an unknown model
  ref TEXT,                        -- conversation id or note id
  ok INTEGER NOT NULL,
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS visitors (
  id TEXT PRIMARY KEY,             -- demo visitor (cookie) or mcp-invite
  kind TEXT NOT NULL,              -- web | mcp
  seeded INTEGER NOT NULL DEFAULT 0,   -- 0 after a reset: the sandbox is re-seeded on the next request
  requests INTEGER NOT NULL DEFAULT 0,
  created TEXT NOT NULL,
  last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tool TEXT NOT NULL,
  transport TEXT NOT NULL,         -- mcp | http
  ms REAL NOT NULL,
  ok INTEGER NOT NULL,
  error_code TEXT,
  created TEXT NOT NULL
);
"""

_lock = threading.Lock()
_root: Path | None = None


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(3)}"


def configure(root: Path | None = None) -> Path:
    """Point the store at a data root (tests use a temp dir) and create the schema."""
    global _root
    _root = Path(root or paths.DATA)
    _root.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        _migrate_proposals(db)
        db.executescript(SCHEMA)
        for table in ("cases", "research"):      # Phase 10: owner column on older databases
            if "owner" not in {r[1] for r in db.execute(f"PRAGMA table_info({table})")}:
                db.execute(f"ALTER TABLE {table} ADD COLUMN owner TEXT")
        if "source_id" not in {r[1] for r in db.execute("PRAGMA table_info(inputs)")}:   # Phase 11
            db.execute("ALTER TABLE inputs ADD COLUMN source_id TEXT")
    return _root


def _migrate_proposals(db: sqlite3.Connection) -> None:
    """Phase 6 made proposals general (nullable doc_id/path, payload, result, note_id).
    SQLite can't drop NOT NULL in place, so an older table is rebuilt once."""
    cols = {r[1] for r in db.execute("PRAGMA table_info(proposals)")}
    if not cols or "payload" in cols:
        return
    db.execute("ALTER TABLE proposals RENAME TO proposals_v1")
    db.executescript(SCHEMA)
    db.execute("INSERT INTO proposals (id, case_id, doc_id, kind, path, old_value, new_value, rationale, citations,"
               " origin, status, edit_id, created, resolved) SELECT id, case_id, doc_id, kind, path, old_value,"
               " new_value, rationale, citations, origin, status, edit_id, created, resolved FROM proposals_v1")
    db.execute("DROP TABLE proposals_v1")


def root() -> Path:
    return _root if _root is not None else configure()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    base = _root if _root is not None else Path(paths.DATA)
    db = sqlite3.connect(base / "drivkraft-tax.sqlite3", timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    try:
        with _lock:
            yield db
            db.commit()
    finally:
        db.close()


def case_dir(case_id: str) -> Path:
    return root() / "cases" / case_id


def doc_dir(case_id: str, doc_id: str) -> Path:
    return case_dir(case_id) / "docs" / doc_id


# ── Rows ──────────────────────────────────────────────────────────────────

def _row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    for k in ("progress", "acknowledged", "old_value", "new_value", "data", "changes", "citations", "steps",
              "payload", "result", "attendees", "segments", "analysis", "meta", "items", "warnings",
              "filer", "checks", "signature", "submission", "timeline", "fields", "error"):
        if k in d and isinstance(d[k], str):
            d[k] = json.loads(d[k])
    if "cached" in d:
        d["cached"] = bool(d["cached"])
    if "read_only" in d:
        d["read_only"] = bool(d["read_only"])
    return d


# ── Visitor scope (demo mode) ─────────────────────────────────────────────
# With a visitor set (server/visitor.py), a visitor sees the reference cases
# (owner NULL) and their own; everything else behaves as if it didn't exist.

VISIBLE = "(owner IS NULL OR owner = ?)"
VISIBLE_CASE = f"case_id IN (SELECT id FROM cases WHERE {VISIBLE})"


def visible_case(case_id: str | None) -> bool:
    v = _visitor.get()
    if v is None or case_id is None:
        return True
    with connect() as db:
        return db.execute(f"SELECT 1 FROM cases WHERE id = ? AND {VISIBLE}", (case_id, v)).fetchone() is not None


def _scoped(row: dict | None) -> dict | None:
    return row if row is not None and visible_case(row.get("case_id")) else None


def get_case(case_id: str) -> dict | None:
    v = _visitor.get()
    with connect() as db:
        if v is None:
            return _row(db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone())
        return _row(db.execute(f"SELECT * FROM cases WHERE id = ? AND {VISIBLE}", (case_id, v)).fetchone())


def list_cases() -> list[dict]:
    v = _visitor.get()
    where, args = (f" WHERE {VISIBLE}", (v,)) if v is not None else ("", ())
    with connect() as db:
        return [_row(r) for r in db.execute(f"SELECT * FROM cases{where} ORDER BY read_only DESC, created DESC", args)]


def insert_case(case: dict) -> None:
    with connect() as db:
        db.execute(
            "INSERT INTO cases (id, name, tax_year, filing_status, read_only, description, owner, created)"
            " VALUES (:id, :name, :tax_year, :filing_status, :read_only, :description, :owner, :created)",
            {"description": None, "read_only": 0, "owner": _visitor.get(), **case},
        )
    case_dir(case["id"]).mkdir(parents=True, exist_ok=True)


def get_document(doc_id: str) -> dict | None:
    with connect() as db:
        row = _row(db.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone())
    return _scoped(row)


def list_documents(case_id: str) -> list[dict]:
    with connect() as db:
        return [_row(r) for r in db.execute("SELECT * FROM documents WHERE case_id = ? ORDER BY created", (case_id,))]


def insert_document(doc: dict) -> None:
    ts = now()
    row = {"sample": None, "label": None, "progress": None, "approved_at": None, "created": ts, "updated": ts, **doc}
    row["progress"] = json.dumps(row["progress"]) if row["progress"] is not None else None
    row["acknowledged"] = json.dumps(row.get("acknowledged") or {})
    with connect() as db:
        db.execute(
            "INSERT INTO documents (id, case_id, kind, sample, source_kind, label, status, progress, acknowledged,"
            " approved_at, created, updated) VALUES (:id, :case_id, :kind, :sample, :source_kind, :label, :status,"
            " :progress, :acknowledged, :approved_at, :created, :updated)",
            row,
        )


def update_document(doc_id: str, **fields: Any) -> None:
    for k in ("progress", "acknowledged"):
        if k in fields and fields[k] is not None:
            fields[k] = json.dumps(fields[k])
    fields["updated"] = now()
    cols = ", ".join(f"{k} = :{k}" for k in fields)
    with connect() as db:
        db.execute(f"UPDATE documents SET {cols} WHERE id = :_id", {**fields, "_id": doc_id})


def insert_edit(doc_id: str, path: str, old: Any, new: Any, reason: str) -> dict:
    ts = now()
    with connect() as db:
        cur = db.execute(
            "INSERT INTO edits (doc_id, path, old_value, new_value, reason, created) VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, path, json.dumps(old), json.dumps(new), reason, ts),
        )
        return {"id": cur.lastrowid, "doc_id": doc_id, "path": path, "old_value": old, "new_value": new,
                "reason": reason, "created": ts}


def list_edits(doc_id: str) -> list[dict]:
    with connect() as db:
        return [_row(r) for r in db.execute("SELECT * FROM edits WHERE doc_id = ? ORDER BY id", (doc_id,))]


def insert_input(case_id: str, node_type: str, data: dict, label: str | None = None,
                 source_id: str | None = None) -> int:
    with connect() as db:
        cur = db.execute("INSERT INTO inputs (case_id, node_type, data, label, source_id, created)"
                         " VALUES (?, ?, ?, ?, ?, ?)", (case_id, node_type, json.dumps(data), label, source_id, now()))
        return cur.lastrowid


def list_inputs(case_id: str) -> list[dict]:
    with connect() as db:
        return [_row(r) for r in db.execute("SELECT * FROM inputs WHERE case_id = ? ORDER BY id", (case_id,))]


def replace_inputs(case_id: str, rows: list[tuple[str, dict, str | None]]) -> list[int]:
    """Swap a case's hand-entered inputs in one transaction. Inputs that came from a
    dropped source document stay (remove the document to remove them)."""
    ts = now()
    with connect() as db:
        db.execute("DELETE FROM inputs WHERE case_id = ? AND source_id IS NULL", (case_id,))
        return [db.execute("INSERT INTO inputs (case_id, node_type, data, label, created) VALUES (?, ?, ?, ?, ?)",
                           (case_id, node, json.dumps(data), label, ts)).lastrowid for node, data, label in rows]


def insert_source(s: dict) -> dict:
    row = {"form": None, "label": None, "fields": [], "warnings": [], "error": None, "doc_id": None,
           "created": now(), **s}
    with connect() as db:
        db.execute("INSERT INTO source_docs (id, case_id, filename, sha256, form, label, status, fields, warnings,"
                   " error, doc_id, created) VALUES (:id, :case_id, :filename, :sha256, :form, :label, :status,"
                   " :fields, :warnings, :error, :doc_id, :created)",
                   {**row, "fields": json.dumps(row["fields"]), "warnings": json.dumps(row["warnings"]),
                    "error": None if row["error"] is None else json.dumps(row["error"])})
    return row


def get_source(source_id: str) -> dict | None:
    with connect() as db:
        row = _row(db.execute("SELECT * FROM source_docs WHERE id = ?", (source_id,)).fetchone())
    return _scoped(row)


def list_sources(case_id: str) -> list[dict]:
    with connect() as db:
        return [_row(r) for r in db.execute("SELECT * FROM source_docs WHERE case_id = ? ORDER BY created, rowid",
                                            (case_id,))]


def delete_source(source_id: str) -> None:
    """Delete a source document with the inputs it made (its K-1, if any, is the caller's)."""
    with connect() as db:
        db.execute("DELETE FROM inputs WHERE source_id = ?", (source_id,))
        db.execute("DELETE FROM source_docs WHERE id = ?", (source_id,))


def delete_document(doc_id: str) -> None:
    with connect() as db:
        db.execute("DELETE FROM edits WHERE doc_id = ?", (doc_id,))
        db.execute("DELETE FROM proposals WHERE doc_id = ?", (doc_id,))
        db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


def insert_scenario(case_id: str, name: str, changes: dict) -> dict:
    row = {"id": new_id("scn"), "case_id": case_id, "name": name, "changes": changes, "created": now()}
    with connect() as db:
        db.execute("INSERT INTO scenarios (id, case_id, name, changes, created) VALUES (?, ?, ?, ?, ?)",
                   (row["id"], case_id, name, json.dumps(changes), row["created"]))
    return row


def list_scenarios(case_id: str) -> list[dict]:
    with connect() as db:
        return [_row(r) for r in db.execute("SELECT * FROM scenarios WHERE case_id = ? ORDER BY created", (case_id,))]


def delete_scenario(scenario_id: str) -> bool:
    with connect() as db:
        if (v := _visitor.get()) is not None:
            return db.execute(f"DELETE FROM scenarios WHERE id = ? AND {VISIBLE_CASE}", (scenario_id, v)).rowcount > 0
        return db.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,)).rowcount > 0


def insert_proposal(p: dict) -> dict:
    row = {"status": "pending", "edit_id": None, "resolved": None, "created": now(), "doc_id": None, "path": None,
           "old_value": None, "new_value": None, "payload": {}, "result": None, "note_id": None, **p}
    enc = {**row, "old_value": json.dumps(row["old_value"]), "new_value": json.dumps(row["new_value"]),
           "citations": json.dumps(row["citations"]), "payload": json.dumps(row["payload"]),
           "result": None if row["result"] is None else json.dumps(row["result"])}
    with connect() as db:
        db.execute("INSERT INTO proposals (id, case_id, doc_id, kind, path, old_value, new_value, payload, result,"
                   " note_id, rationale, citations, origin, status, edit_id, created, resolved) VALUES (:id, :case_id,"
                   " :doc_id, :kind, :path, :old_value, :new_value, :payload, :result, :note_id, :rationale,"
                   " :citations, :origin, :status, :edit_id, :created, :resolved)", enc)
    return row


def get_proposal(proposal_id: str) -> dict | None:
    with connect() as db:
        row = _row(db.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone())
    return _scoped(row)


def list_proposals(case_id: str | None = None, status: str | None = None, note_id: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM proposals WHERE 1=1", []
    if (v := _visitor.get()) is not None:
        sql, args = sql + f" AND {VISIBLE_CASE}", [v]
    if case_id:
        sql, args = sql + " AND case_id = ?", [*args, case_id]
    if note_id:
        sql, args = sql + " AND note_id = ?", [*args, note_id]
    if status:
        sql, args = sql + " AND status = ?", [*args, status]
    with connect() as db:
        return [_row(r) for r in db.execute(sql + " ORDER BY created DESC, rowid DESC", args)]


def update_proposal(proposal_id: str, **fields: Any) -> None:
    if "result" in fields and fields["result"] is not None:
        fields["result"] = json.dumps(fields["result"])
    cols = ", ".join(f"{k} = :{k}" for k in fields)
    with connect() as db:
        db.execute(f"UPDATE proposals SET {cols} WHERE id = :_id", {**fields, "_id": proposal_id})


def delete_proposal(proposal_id: str) -> bool:
    with connect() as db:
        return db.execute("DELETE FROM proposals WHERE id = ?", (proposal_id,)).rowcount > 0


def insert_research(r: dict) -> dict:
    row = {"case_id": None, "steps": [], "cache_id": None, "created": now(), "owner": _visitor.get(), **r}
    with connect() as db:
        db.execute("INSERT INTO research (id, case_id, question, mode, answer, citations, steps, cached, cache_id,"
                   " cost_usd, origin, owner, created) VALUES (:id, :case_id, :question, :mode, :answer, :citations,"
                   " :steps, :cached, :cache_id, :cost_usd, :origin, :owner, :created)",
                   {**row, "citations": json.dumps(row["citations"]), "steps": json.dumps(row["steps"]),
                    "cached": int(row["cached"])})
    return row


def _research_visible(r: dict | None) -> dict | None:
    v = _visitor.get()
    if r is None or v is None:
        return r
    if r["case_id"] is None:
        return r if r.get("owner") in (None, v) else None
    return _scoped(r)


def get_research(research_id: str) -> dict | None:
    with connect() as db:
        row = _row(db.execute("SELECT * FROM research WHERE id = ?", (research_id,)).fetchone())
    return _research_visible(row)


def list_research(case_id: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM research WHERE 1=1", []
    if case_id:
        sql, args = sql + " AND case_id = ?", [case_id]
    if (v := _visitor.get()) is not None:
        sql += f" AND (({VISIBLE_CASE}) OR (case_id IS NULL AND {VISIBLE}))"
        args += [v, v]
    with connect() as db:
        return [_row(r) for r in db.execute(sql + " ORDER BY created DESC, rowid DESC", args)]


def delete_research(research_id: str) -> bool:
    with connect() as db:
        return db.execute("DELETE FROM research WHERE id = ?", (research_id,)).rowcount > 0


def insert_note(n: dict) -> dict:
    row = {"meeting_date": None, "attendees": [], "sample": None, "analysis": None, "analyzed_at": None,
           "created": now(), **n}
    with connect() as db:
        db.execute("INSERT INTO notes (id, case_id, kind, title, meeting_date, attendees, text, segments, sample,"
                   " analysis, analyzed_at, created) VALUES (:id, :case_id, :kind, :title, :meeting_date, :attendees,"
                   " :text, :segments, :sample, :analysis, :analyzed_at, :created)",
                   {**row, "attendees": json.dumps(row["attendees"]), "segments": json.dumps(row["segments"]),
                    "analysis": None if row["analysis"] is None else json.dumps(row["analysis"])})
    return row


def get_note(note_id: str) -> dict | None:
    with connect() as db:
        row = _row(db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone())
    return _scoped(row)


def list_notes(case_id: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM notes WHERE 1=1", []
    if case_id:
        sql, args = sql + " AND case_id = ?", [case_id]
    if (v := _visitor.get()) is not None:
        sql, args = sql + f" AND {VISIBLE_CASE}", [*args, v]
    with connect() as db:
        return [_row(r) for r in db.execute(sql + " ORDER BY COALESCE(meeting_date, created) DESC, created DESC", args)]


def update_note(note_id: str, **fields: Any) -> None:
    if "analysis" in fields and fields["analysis"] is not None:
        fields["analysis"] = json.dumps(fields["analysis"])
    cols = ", ".join(f"{k} = :{k}" for k in fields)
    with connect() as db:
        db.execute(f"UPDATE notes SET {cols} WHERE id = :_id", {**fields, "_id": note_id})


def delete_note(note_id: str) -> bool:
    with connect() as db:
        db.execute("DELETE FROM proposals WHERE note_id = ? AND status = 'pending'", (note_id,))
        return db.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount > 0


def insert_checklist(item: dict) -> dict:
    ts = now()
    row = {"detail": None, "status": "open", "source_ref": None, "proposal_id": None, "created": ts, "updated": ts,
           **item}
    with connect() as db:
        db.execute("INSERT INTO checklist (id, case_id, item, detail, status, source_ref, proposal_id, created,"
                   " updated) VALUES (:id, :case_id, :item, :detail, :status, :source_ref, :proposal_id, :created,"
                   " :updated)", row)
    return row


def get_checklist_item(item_id: str) -> dict | None:
    with connect() as db:
        row = _row(db.execute("SELECT * FROM checklist WHERE id = ?", (item_id,)).fetchone())
    return _scoped(row)


def list_checklist(case_id: str) -> list[dict]:
    with connect() as db:
        return [_row(r) for r in db.execute("SELECT * FROM checklist WHERE case_id = ? ORDER BY created, rowid",
                                            (case_id,))]


def update_checklist(item_id: str, **fields: Any) -> None:
    fields["updated"] = now()
    cols = ", ".join(f"{k} = :{k}" for k in fields)
    with connect() as db:
        db.execute(f"UPDATE checklist SET {cols} WHERE id = :_id", {**fields, "_id": item_id})


def delete_checklist(item_id: str) -> bool:
    with connect() as db:
        return db.execute("DELETE FROM checklist WHERE id = ?", (item_id,)).rowcount > 0


def insert_output(o: dict) -> dict:
    row = {"meta": {}, "created": now(), **o}
    with connect() as db:
        row["version"] = db.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM outputs WHERE case_id = ? AND kind = ?",
                                    (row["case_id"], row["kind"])).fetchone()[0]
        db.execute("INSERT INTO outputs (id, case_id, kind, version, file, meta, created) VALUES (:id, :case_id, :kind,"
                   " :version, :file, :meta, :created)", {**row, "meta": json.dumps(row["meta"])})
    return row


def get_output(output_id: str) -> dict | None:
    with connect() as db:
        row = _row(db.execute("SELECT * FROM outputs WHERE id = ?", (output_id,)).fetchone())
    return _scoped(row)


def list_outputs(case_id: str, kind: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM outputs WHERE case_id = ?", [case_id]
    if kind:
        sql, args = sql + " AND kind = ?", [*args, kind]
    with connect() as db:
        return [_row(r) for r in db.execute(sql + " ORDER BY created DESC, version DESC", args)]


def update_output(output_id: str, file: str, meta: dict) -> None:
    with connect() as db:
        db.execute("UPDATE outputs SET file = ?, meta = ? WHERE id = ?", (file, json.dumps(meta), output_id))


def insert_changeset(c: dict) -> dict:
    row = {"filename": None, "status": "pending", "warnings": [], "created": now(), "resolved": None, **c}
    with connect() as db:
        db.execute("INSERT INTO changesets (id, case_id, workpaper_id, filename, status, items, warnings, created,"
                   " resolved) VALUES (:id, :case_id, :workpaper_id, :filename, :status, :items, :warnings, :created,"
                   " :resolved)", {**row, "items": json.dumps(row["items"]), "warnings": json.dumps(row["warnings"])})
    return row


def get_changeset(changeset_id: str) -> dict | None:
    with connect() as db:
        row = _row(db.execute("SELECT * FROM changesets WHERE id = ?", (changeset_id,)).fetchone())
    return _scoped(row)


def list_changesets(case_id: str) -> list[dict]:
    with connect() as db:
        return [_row(r) for r in db.execute("SELECT * FROM changesets WHERE case_id = ? ORDER BY created DESC, rowid DESC",
                                            (case_id,))]


def update_changeset(changeset_id: str, **fields: Any) -> None:
    for k in ("items", "warnings"):
        if k in fields:
            fields[k] = json.dumps(fields[k])
    cols = ", ".join(f"{k} = :{k}" for k in fields)
    with connect() as db:
        db.execute(f"UPDATE changesets SET {cols} WHERE id = :_id", {**fields, "_id": changeset_id})


_FILING_JSON = ("filer", "checks", "signature", "submission", "timeline")


def insert_filing(f: dict) -> dict:
    row = {"signature": None, "submission": None, "created": now(), "updated": now(), **f}
    with connect() as db:
        row["number"] = db.execute("SELECT COALESCE(MAX(number), 0) + 1 FROM filings WHERE case_id = ?",
                                   (row["case_id"],)).fetchone()[0]
        db.execute("INSERT INTO filings (id, case_id, number, status, fingerprint, xml_file, sha256, filer, checks,"
                   " signature, submission, timeline, created, updated) VALUES (:id, :case_id, :number, :status,"
                   " :fingerprint, :xml_file, :sha256, :filer, :checks, :signature, :submission, :timeline, :created,"
                   " :updated)", {**row, **{k: json.dumps(row[k]) for k in _FILING_JSON}})
    return row


def get_filing(filing_id: str) -> dict | None:
    with connect() as db:
        row = _row(db.execute("SELECT * FROM filings WHERE id = ?", (filing_id,)).fetchone())
    return _scoped(row)


def list_filings(case_id: str) -> list[dict]:
    with connect() as db:
        return [_row(r) for r in db.execute("SELECT * FROM filings WHERE case_id = ? ORDER BY number DESC", (case_id,))]


def update_filing(filing_id: str, **fields: Any) -> None:
    for k in _FILING_JSON:
        if k in fields:
            fields[k] = json.dumps(fields[k])
    fields["updated"] = now()
    cols = ", ".join(f"{k} = :{k}" for k in fields)
    with connect() as db:
        db.execute(f"UPDATE filings SET {cols} WHERE id = :_id", {**fields, "_id": filing_id})


def get_efile_record(case_id: str) -> dict | None:
    with connect() as db:
        return _row(db.execute("SELECT * FROM efile_db WHERE case_id = ?", (case_id,)).fetchone())


def enroll_efile_record(case_id: str, ssn: str, name_control: str, prior_year_agi: int) -> dict:
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO efile_db (case_id, ssn, name_control, prior_year_agi, enrolled)"
                   " VALUES (?, ?, ?, ?, ?)", (case_id, ssn, name_control, prior_year_agi, now()))
    return get_efile_record(case_id)


def reset() -> None:
    """Delete every case, document, edit, input, scenario, note and event, and the case folders.
    The caller re-seeds the reference cases. ai_usage is kept: it's the spend record."""
    with connect() as db:
        for table in ("filings", "efile_db", "changesets", "outputs", "checklist", "notes", "research", "proposals", "edits", "inputs", "source_docs", "scenarios", "documents", "cases", "events"):
            db.execute(f"DELETE FROM {table}")
    shutil.rmtree(root() / "cases", ignore_errors=True)


def delete_cases(case_ids: list[str]) -> None:
    """Delete these cases with everything under them (a demo visitor's sandbox reset)."""
    if not case_ids:
        return
    marks = ",".join("?" * len(case_ids))
    with connect() as db:
        db.execute(f"DELETE FROM edits WHERE doc_id IN (SELECT id FROM documents WHERE case_id IN ({marks}))", case_ids)
        for table in ("filings", "efile_db", "changesets", "outputs", "checklist", "notes", "research", "proposals",
                      "inputs", "source_docs", "scenarios", "documents"):
            db.execute(f"DELETE FROM {table} WHERE case_id IN ({marks})", case_ids)
        db.execute(f"DELETE FROM cases WHERE id IN ({marks})", case_ids)
    for cid in case_ids:
        shutil.rmtree(case_dir(cid), ignore_errors=True)


def log_ai_usage(kind: str, model: str | None, usage: dict, ref: str | None = None, ok: bool = True) -> None:
    from .pricing import cost_usd
    try:
        with connect() as db:
            db.execute("INSERT INTO ai_usage (kind, model, input_tokens, output_tokens, cache_read_tokens,"
                       " cache_write_tokens, cost_usd, ref, ok, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (kind, model, usage.get("input", 0), usage.get("output", 0), usage.get("cache_read", 0),
                        usage.get("cache_write", 0), cost_usd(model, usage), ref, int(ok), now()))
    except sqlite3.Error:
        pass   # like the event log, usage logging must never break a call


def query(sql: str, args: tuple = ()) -> list[dict]:
    """Read-only aggregate queries for the operator page."""
    with connect() as db:
        return [dict(r) for r in db.execute(sql, args)]


def log_event(tool: str, transport: str, ms: float, ok: bool, error_code: str | None = None) -> None:
    try:
        with connect() as db:
            db.execute("INSERT INTO events (tool, transport, ms, ok, error_code, created) VALUES (?, ?, ?, ?, ?, ?)",
                       (tool, transport, round(ms, 1), int(ok), error_code, now()))
    except sqlite3.Error:
        pass   # the event log must never break a tool call


def update_input(input_id: int, data: dict) -> None:
    with connect() as db:
        db.execute("UPDATE inputs SET data = ? WHERE id = ?", (json.dumps(data), input_id))
