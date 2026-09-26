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

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  tax_year INTEGER NOT NULL,
  filing_status TEXT NOT NULL,
  read_only INTEGER NOT NULL DEFAULT 0,
  description TEXT,
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
  doc_id TEXT NOT NULL REFERENCES documents(id),
  kind TEXT NOT NULL,              -- k1_edit
  path TEXT NOT NULL,
  old_value TEXT,                  -- JSON: value when proposed
  new_value TEXT,                  -- JSON
  rationale TEXT NOT NULL,
  citations TEXT NOT NULL DEFAULT '[]',     -- JSON: sources[] the proposal relies on
  origin TEXT NOT NULL,            -- chat | mcp | http
  status TEXT NOT NULL,            -- pending | accepted | rejected
  edit_id INTEGER,                 -- the edit an accept made
  created TEXT NOT NULL,
  resolved TEXT
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
  created TEXT NOT NULL
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
        db.executescript(SCHEMA)
    return _root


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
    for k in ("progress", "acknowledged", "old_value", "new_value", "data", "changes", "citations", "steps"):
        if k in d and isinstance(d[k], str):
            d[k] = json.loads(d[k])
    if "cached" in d:
        d["cached"] = bool(d["cached"])
    if "read_only" in d:
        d["read_only"] = bool(d["read_only"])
    return d


def get_case(case_id: str) -> dict | None:
    with connect() as db:
        return _row(db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone())


def list_cases() -> list[dict]:
    with connect() as db:
        return [_row(r) for r in db.execute("SELECT * FROM cases ORDER BY read_only DESC, created DESC")]


def insert_case(case: dict) -> None:
    with connect() as db:
        db.execute(
            "INSERT INTO cases (id, name, tax_year, filing_status, read_only, description, created)"
            " VALUES (:id, :name, :tax_year, :filing_status, :read_only, :description, :created)",
            {"description": None, "read_only": 0, **case},
        )
    case_dir(case["id"]).mkdir(parents=True, exist_ok=True)


def get_document(doc_id: str) -> dict | None:
    with connect() as db:
        return _row(db.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone())


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


def insert_input(case_id: str, node_type: str, data: dict, label: str | None = None) -> int:
    with connect() as db:
        cur = db.execute("INSERT INTO inputs (case_id, node_type, data, label, created) VALUES (?, ?, ?, ?, ?)",
                         (case_id, node_type, json.dumps(data), label, now()))
        return cur.lastrowid


def list_inputs(case_id: str) -> list[dict]:
    with connect() as db:
        return [_row(r) for r in db.execute("SELECT * FROM inputs WHERE case_id = ? ORDER BY id", (case_id,))]


def replace_inputs(case_id: str, rows: list[tuple[str, dict, str | None]]) -> list[int]:
    """Swap all of a case's inputs in one transaction."""
    ts = now()
    with connect() as db:
        db.execute("DELETE FROM inputs WHERE case_id = ?", (case_id,))
        return [db.execute("INSERT INTO inputs (case_id, node_type, data, label, created) VALUES (?, ?, ?, ?, ?)",
                           (case_id, node, json.dumps(data), label, ts)).lastrowid for node, data, label in rows]


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
        return db.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,)).rowcount > 0


def insert_proposal(p: dict) -> dict:
    row = {"status": "pending", "edit_id": None, "resolved": None, "created": now(), **p}
    enc = {**row, "old_value": json.dumps(row["old_value"]), "new_value": json.dumps(row["new_value"]),
           "citations": json.dumps(row["citations"])}
    with connect() as db:
        db.execute("INSERT INTO proposals (id, case_id, doc_id, kind, path, old_value, new_value, rationale, citations,"
                   " origin, status, edit_id, created, resolved) VALUES (:id, :case_id, :doc_id, :kind, :path,"
                   " :old_value, :new_value, :rationale, :citations, :origin, :status, :edit_id, :created, :resolved)",
                   enc)
    return row


def get_proposal(proposal_id: str) -> dict | None:
    with connect() as db:
        return _row(db.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone())


def list_proposals(case_id: str | None = None, status: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM proposals WHERE 1=1", []
    if case_id:
        sql, args = sql + " AND case_id = ?", [*args, case_id]
    if status:
        sql, args = sql + " AND status = ?", [*args, status]
    with connect() as db:
        return [_row(r) for r in db.execute(sql + " ORDER BY created DESC, rowid DESC", args)]


def update_proposal(proposal_id: str, **fields: Any) -> None:
    cols = ", ".join(f"{k} = :{k}" for k in fields)
    with connect() as db:
        db.execute(f"UPDATE proposals SET {cols} WHERE id = :_id", {**fields, "_id": proposal_id})


def insert_research(r: dict) -> dict:
    row = {"case_id": None, "steps": [], "cache_id": None, "created": now(), **r}
    with connect() as db:
        db.execute("INSERT INTO research (id, case_id, question, mode, answer, citations, steps, cached, cache_id,"
                   " cost_usd, origin, created) VALUES (:id, :case_id, :question, :mode, :answer, :citations, :steps,"
                   " :cached, :cache_id, :cost_usd, :origin, :created)",
                   {**row, "citations": json.dumps(row["citations"]), "steps": json.dumps(row["steps"]),
                    "cached": int(row["cached"])})
    return row


def get_research(research_id: str) -> dict | None:
    with connect() as db:
        return _row(db.execute("SELECT * FROM research WHERE id = ?", (research_id,)).fetchone())


def list_research(case_id: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM research", []
    if case_id:
        sql, args = sql + " WHERE case_id = ?", [case_id]
    with connect() as db:
        return [_row(r) for r in db.execute(sql + " ORDER BY created DESC, rowid DESC", args)]


def delete_research(research_id: str) -> bool:
    with connect() as db:
        return db.execute("DELETE FROM research WHERE id = ?", (research_id,)).rowcount > 0


def reset() -> None:
    """Delete every case, document, edit, input, scenario and event, and the case folders.
    The caller re-seeds the reference cases."""
    with connect() as db:
        for table in ("research", "proposals", "edits", "inputs", "scenarios", "documents", "cases", "events"):
            db.execute(f"DELETE FROM {table}")
    shutil.rmtree(root() / "cases", ignore_errors=True)


def log_event(tool: str, transport: str, ms: float, ok: bool, error_code: str | None = None) -> None:
    try:
        with connect() as db:
            db.execute("INSERT INTO events (tool, transport, ms, ok, error_code, created) VALUES (?, ?, ?, ?, ?, ?)",
                       (tool, transport, round(ms, 1), int(ok), error_code, now()))
    except sqlite3.Error:
        pass   # the event log must never break a tool call
