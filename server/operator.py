"""Operator view (Phase 9): what the app has done, what it cost, and whether the
pinned upstream tools are healthy. Everything is read from the store, the case
folders and the vendor checkout; nothing here writes.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import metadata
from pathlib import Path

from . import k1doc, paths, pricing, store

DAYS = 14                     # the tool-call chart's window


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


# ── Cases and K-1s ────────────────────────────────────────────────────────

def cases_and_k1s() -> dict:
    from .tools.cases import case_status
    cases = store.list_cases()
    docs = store.query("SELECT * FROM documents")
    by_case = defaultdict(list)
    for d in docs:
        by_case[d["case_id"]].append(d)
    statuses = Counter(case_status(by_case[c["id"]]) for c in cases if not c["read_only"])

    flag_codes, error_codes, unsupported, incomplete = Counter(), Counter(), Counter(), Counter()
    extraction_s = []
    for d in docs:
        bridge = k1doc.read_json(store.doc_dir(d["case_id"], d["id"]) / "bridge.json") or {}
        for f in bridge.get("flags", []):
            flag_codes[f["code"]] += 1
            if f["code"] == "calculation_incomplete" and f.get("path"):
                incomplete[f["path"]] += 1
        for e in bridge.get("errors", []):
            error_codes[e["code"]] += 1
        for e in bridge.get("ledger", []):
            if e.get("disposition") == "unsupported":
                unsupported[e["path"]] += 1
        prog = json.loads(d["progress"]) if d.get("progress") else None
        if d["source_kind"] == "pdf" and prog and prog.get("finished") and prog.get("started"):
            extraction_s.append((_ts(prog["finished"]) - _ts(prog["started"])).total_seconds())

    def boxes(counter: Counter) -> list[dict]:
        return [{"path": p, "box": k1doc.box_label(p), "count": n} for p, n in counter.most_common()]

    return {
        "cases": {"total": sum(1 for c in cases if not c["read_only"]),
                  "reference": sum(1 for c in cases if c["read_only"]),
                  "by_status": [{"status": s, "count": statuses.get(s, 0)}
                                for s in ("empty", "extracting", "in_review", "ready")]},
        "k1s": {"total": len(docs),
                "by_status": [{"status": s, "count": n} for s, n in Counter(d["status"] for d in docs).most_common()],
                "by_source": dict(Counter(d["source_kind"] for d in docs)),
                "edits": store.query("SELECT COUNT(*) AS n FROM edits")[0]["n"],
                "pdf_extraction_s": {"count": len(extraction_s), "p50": _pct(extraction_s, 0.5),
                                     "max": round(max(extraction_s), 1) if extraction_s else None}},
        "exceptions": {"flags": [{"code": c, "count": n} for c, n in flag_codes.most_common()],
                       "errors": [{"code": c, "count": n} for c, n in error_codes.most_common()]},
        "bridge": {"unsupported": boxes(unsupported), "not_in_calculation": boxes(incomplete)},
    }


def _ts(iso: str) -> datetime:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


# ── Tool calls ────────────────────────────────────────────────────────────

def tool_calls() -> dict:
    rows = store.query("SELECT tool, transport, ms, ok, error_code, created FROM events ORDER BY id")
    by_tool: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_tool[r["tool"]].append(r)
    tools = []
    for name, rs in by_tool.items():
        ms = [r["ms"] for r in rs]
        errs = [r for r in rs if not r["ok"]]
        tools.append({"tool": name, "calls": len(rs), "errors": len(errs), "error_rate": _rate(len(errs), len(rs)),
                      "p50_ms": _pct(ms, 0.5), "p95_ms": _pct(ms, 0.95),
                      "transports": dict(Counter(r["transport"] for r in rs)),
                      "last": rs[-1]["created"]})
    tools.sort(key=lambda t: -t["calls"])
    today = datetime.now(timezone.utc).date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(DAYS - 1, -1, -1)]
    per_day = Counter(r["created"][:10] for r in rows)
    err_day = Counter(r["created"][:10] for r in rows if not r["ok"])
    all_ms = [r["ms"] for r in rows]
    return {
        "total": len(rows), "errors": sum(1 for r in rows if not r["ok"]),
        "p50_ms": _pct(all_ms, 0.5), "p95_ms": _pct(all_ms, 0.95),
        "by_transport": dict(Counter(r["transport"] for r in rows)),
        "daily": [{"day": d, "calls": per_day.get(d, 0), "errors": err_day.get(d, 0)} for d in days],
        "tools": tools,
        "recent_errors": [{"tool": r["tool"], "transport": r["transport"], "code": r["error_code"], "at": r["created"]}
                          for r in reversed(rows) if not r["ok"]][:8],
    }


# ── Usage and cost ────────────────────────────────────────────────────────

def usage() -> dict:
    ai = store.query("SELECT kind, model, COUNT(*) AS calls, SUM(input_tokens) AS input,"
                     " SUM(output_tokens) AS output, SUM(cache_read_tokens) AS cache_read,"
                     " SUM(cache_write_tokens) AS cache_write, SUM(cost_usd) AS cost_usd,"
                     " SUM(cost_usd IS NULL) AS unpriced FROM ai_usage GROUP BY kind, model ORDER BY cost_usd DESC")
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    ai_month = store.query("SELECT COALESCE(SUM(cost_usd), 0) AS c FROM ai_usage WHERE created LIKE ?", (f"{month}%",))[0]["c"]
    notes = store.query("SELECT analysis FROM notes WHERE analysis IS NOT NULL")
    cached_analyses = sum(1 for n in notes if json.loads(n["analysis"]).get("cached"))
    research = store.query("SELECT mode, cached, COUNT(*) AS n, SUM(cost_usd) AS cost FROM research GROUP BY mode, cached")
    bizora = {"live": sum(r["n"] for r in research if not r["cached"]),
              "cached": sum(r["n"] for r in research if r["cached"]),
              "cost_usd": round(sum(r["cost"] or 0 for r in research), 2),
              "by_mode": [{"mode": r["mode"], "cached": bool(r["cached"]), "count": r["n"],
                           "cost_usd": round(r["cost"] or 0, 2)} for r in research]}
    anthropic_total = round(sum(r["cost_usd"] or 0 for r in ai), 4)
    return {
        "anthropic": {"total_usd": anthropic_total, "month_usd": round(ai_month, 4), "month": month,
                      "rows": [{**r, "cost_usd": round(r["cost_usd"] or 0, 4)} for r in ai],
                      "cached_meeting_analyses": cached_analyses,
                      "prices_as_of": pricing.PRICES_AS_OF,
                      "note": "Estimated from logged tokens at list prices; kept across Reset data."},
        "bizora": bizora,
        "total_usd": round(anthropic_total + bizora["cost_usd"], 2),
        "keys": {"anthropic": _configured("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"),
                 "bizora": _configured("BIZORA_API_KEY")},
    }


def _configured(*names: str) -> bool:
    return any(os.environ.get(n) for n in names)


# ── Proposals and e-file ──────────────────────────────────────────────────

def proposals() -> dict:
    rows = store.query("SELECT kind, status, origin, COUNT(*) AS n FROM proposals GROUP BY kind, status, origin")
    kinds: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        kinds[r["kind"]][r["status"]] += r["n"]
    out = []
    for k, c in sorted(kinds.items(), key=lambda kv: -sum(kv[1].values())):
        decided = c["accepted"] + c["rejected"]
        out.append({"kind": k, "pending": c["pending"], "accepted": c["accepted"], "rejected": c["rejected"],
                    "accept_rate": _rate(c["accepted"], decided)})
    acc = sum(o["accepted"] for o in out)
    dec = acc + sum(o["rejected"] for o in out)
    return {"by_kind": out, "accept_rate": _rate(acc, dec),
            "by_origin": dict(sum((Counter({r["origin"]: r["n"]}) for r in rows), Counter()))}


def efile() -> dict:
    rows = store.query("SELECT status, submission, checks FROM filings")
    rejects, engine = Counter(), Counter()
    for r in rows:
        sub = json.loads(r["submission"]) if r["submission"] else None
        if sub and r["status"] == "rejected":
            rejects.update(x["rule"] for x in sub["rejects"])
        chk = json.loads(r["checks"])
        engine.update(x["rule"] for x in chk.get("validator", {}).get("engine", []))
    statuses = Counter(r["status"] for r in rows)
    acked = statuses["accepted"] + statuses["rejected"]
    return {"submissions": len(rows),
            "by_status": [{"status": s, "count": n} for s, n in statuses.most_common()],
            "acceptance_rate": _rate(statuses["accepted"], acked),
            "rejects": [{"rule": k, "count": n} for k, n in rejects.most_common()],
            "engine_gaps": [{"rule": k, "count": n} for k, n in engine.most_common(10)]}


# ── Upstream and health ───────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _pins() -> dict[str, str]:
    text = (paths.ROOT / "scripts" / "bootstrap.sh").read_text()
    return dict(re.findall(r'^(OTD_PIN|OPENTAX_PIN|OPENTAX_TAG)="([^"]+)"', text, re.M))


def _git_head(repo: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True,
                           timeout=5)
        return r.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _opentax_version() -> str | None:
    try:
        r = subprocess.run([str(paths.OPENTAX_BIN), "version"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip().split()[-1] if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _pkg(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def upstream() -> dict:
    pins = _pins()
    otd = _git_head(paths.VENDOR / "otd-spec")
    ot = _git_head(paths.VENDOR / "opentax")
    binary = _opentax_version()
    tag = pins.get("OPENTAX_TAG", "").lstrip("v")
    return {
        "components": [
            {"name": "OTD spec", "pinned": pins.get("OTD_PIN"), "actual": otd,
             "ok": bool(otd) and otd.startswith(pins.get("OTD_PIN", "?")), "license": "CC BY 4.0"},
            {"name": "OpenTax source", "pinned": pins.get("OPENTAX_PIN"), "actual": ot,
             "ok": bool(ot) and ot.startswith(pins.get("OPENTAX_PIN", "?")), "license": "AGPL-3.0"},
            {"name": "opentax binary", "pinned": tag or None, "actual": binary,
             "ok": bool(binary) and (not tag or binary == tag), "license": "AGPL-3.0"},
        ],
        "packages": [{"name": n, "version": _pkg(n)} for n in ("mcp", "anthropic", "fastapi", "openpyxl", "fpdf2")],
    }


def smoke() -> dict | None:
    base = Path(paths.DATA) / "smoke"
    runs = sorted(base.glob("*/results.json")) if base.exists() else []
    if not runs:
        return None
    try:
        latest = json.loads(runs[-1].read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return {**latest, "runs": len(runs), "log_dir": str(runs[-1].parent.relative_to(paths.ROOT))
            if runs[-1].is_relative_to(paths.ROOT) else str(runs[-1].parent)}


def gather() -> dict:
    return {
        "generated": store.now(),
        **cases_and_k1s(),
        "tool_calls": tool_calls(),
        "usage": usage(),
        "proposals": proposals(),
        "efile": efile(),
        "upstream": upstream(),
        "smoke": smoke(),
        "visitors": {"tracked": False, "note": "Demo sandboxes arrive with demo mode (Phase 10)."},
    }
