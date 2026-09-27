"""Hosted demo mode (Phase 10): per-visitor sandboxes, rate limits, the Anthropic
spending cap, the MCP invite gate and the nightly reset.

Off unless DRIVKRAFT_DEMO=1; local use is unchanged. In demo mode:

- Each browser gets a visitor id (cookie `dt_visitor`, set by the web's proxy or
  here). The first request seeds that visitor's sandbox: three writable cases
  owned by them. The store then shows them the reference cases plus their own
  (server/visitor.py). Remote MCP clients share one sandbox, `mcp-invite`.
- Writes, intakes, chat turns and live meeting analyses are rate limited per visitor.
- Chat and live analysis stop once this month's estimated Anthropic spend (ai_usage)
  reaches DRIVKRAFT_MONTHLY_CAP_USD, unless the visitor sends their own key.
- /mcp needs `Authorization: Bearer <DRIVKRAFT_INVITE_CODE>`; without an invite
  code configured, the remote MCP endpoint is off.
- Every night at DRIVKRAFT_RESET_HOUR_UTC all cases are wiped and re-seeded;
  visitors keep their id and get a fresh sandbox on their next request.
"""
from __future__ import annotations

import asyncio
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from . import demo, paths, store, visitor
from .errors import ToolFailure

COOKIE = "dt_visitor"
MCP_VISITOR = "mcp-invite"
VISITOR_ID = re.compile(r"v-[0-9a-f]{32}")

# Benchmark 82's W-2 has no employer address, which MeF export requires.
W2_ADDRESS = {"employer_address_line1": "200 Industrial Pkwy", "employer_address_city": "Springfield",
              "employer_address_state": "IL", "employer_address_zip": "62702"}

# bucket → (max calls, window seconds)
LIMITS: dict[str, tuple[int, int]] = {
    "write": (60, 60),          # W and P tools
    "intake": (6, 3600),        # PDF extraction runs the full upstream pipeline (~10 s of CPU)
    "chat": (20, 3600),         # chat turns (each can be several model calls)
    "analysis": (5, 86400),     # live analyze_meeting
    "new_visitor": (20, 3600),  # per client IP: a script dropping its cookie can't use up the daily cap alone
}


def enabled() -> bool:
    return os.environ.get("DRIVKRAFT_DEMO") == "1"


def monthly_cap_usd() -> float:
    return float(os.environ.get("DRIVKRAFT_MONTHLY_CAP_USD", "20"))


def max_new_visitors_per_day() -> int:
    return int(os.environ.get("DRIVKRAFT_MAX_VISITORS", "300"))


def reset_hour_utc() -> int:
    return int(os.environ.get("DRIVKRAFT_RESET_HOUR_UTC", "8"))


def new_visitor_id() -> str:
    return "v-" + secrets.token_hex(16)


def invite_code() -> str | None:
    return os.environ.get("DRIVKRAFT_INVITE_CODE") or None


# ── Visitors and their sandboxes ──────────────────────────────────────────

_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


def _lock_for(vid: str) -> threading.Lock:
    with _locks_guard:
        return _locks[vid]


def ensure(vid: str, kind: str = "web", client_ip: str | None = None) -> None:
    """Make sure the visitor exists and has a sandbox. Idempotent and safe to call
    concurrently for the same id (the web fires several requests on first load)."""
    with _lock_for(vid):
        row = next(iter(store.query("SELECT * FROM visitors WHERE id = ?", (vid,))), None)
        if row is None:
            if client_ip:
                check_rate("new_visitor", "ip:" + client_ip)
            today = store.now()[:10]
            made = store.query("SELECT COUNT(*) AS n FROM visitors WHERE created >= ? AND kind = 'web'", (today,))[0]["n"]
            if kind == "web" and made >= max_new_visitors_per_day():
                raise ToolFailure("demo_full", "The demo has hit today's visitor limit",
                                  "Try again tomorrow, or run it locally (see the README).", status=503)
            with store.connect() as db:
                db.execute("INSERT INTO visitors (id, kind, seeded, requests, created, last_seen) VALUES (?, ?, 0, 0, ?, ?)",
                           (vid, kind, store.now(), store.now()))
            row = {"seeded": 0}
        if not row["seeded"]:
            if not _claim_pooled(vid):
                seed_sandbox(vid)
            with store.connect() as db:
                db.execute("UPDATE visitors SET seeded = 1 WHERE id = ?", (vid,))
            refill_pool_async()
        with store.connect() as db:
            db.execute("UPDATE visitors SET requests = requests + 1, last_seen = ? WHERE id = ?", (store.now(), vid))


def seed_sandbox(vid: str) -> list[str]:
    """The visitor's three writable cases (planning/05 demo seeds):
    Rivera (Copperleaf K-1 approved + the sample planning call, so notes → Inbox is one
    click), Chen (W-2, 1099s and one K-1: a simple return, ready to file) and Okafor
    (the same shape, already submitted and rejected for a prior-year AGI mismatch)."""
    from .tools import load_all
    t = load_all()

    def call(name, *args, **kwargs):
        return t[name].fn(*args, **kwargs)

    token = visitor.current.set(vid)
    try:
        rivera = call("create_case", "Rivera household", 2025, "mfj")["case"]["id"]
        demo._seed_doc(rivera, store.new_id("k1"), "synthetic-k1", note="Reviewed in the demo seed")
        call("add_note", rivera, sample="rivera-planning")

        def simple(name: str, first: str, last: str) -> str:
            cid = call("create_case", name, 2025, "single")["case"]["id"]
            for node, data in demo.bench_82_inputs():
                store.insert_input(cid, node, {**data, **W2_ADDRESS} if node == "w2" else data, label="demo seed")
            demo._seed_doc(cid, store.new_id("k1"), "oak-ventures", note="Reviewed in the demo seed")
            call("efile_set_filer", cid, first, last)
            return cid

        chen = simple("Chen · W-2 and one K-1", "Mei", "Chen")
        okafor = simple("Okafor · e-file rejected", "Ada", "Okafor")
        f = call("efile_export", okafor)["filing"]
        f = call("efile_approve", f["id"])["filing"]
        on_file = call("efile_status", okafor)["efile_database"]["prior_year_agi"]
        f = call("efile_sign", f["id"], "24681", on_file + 3_150)["filing"]   # last year's AGI mistyped
        call("efile_submit", f["id"])
        return [rivera, chen, okafor]
    finally:
        visitor.current.reset(token)


# A few sandboxes are seeded ahead of time (~4 s each, mostly OpenTax runs for the
# e-file seed), so a first visit claims one instantly by changing the cases' owner.

_claim_guard = threading.Lock()
_refill_guard = threading.Lock()


def pool_size() -> int:
    return int(os.environ.get("DRIVKRAFT_POOL_SIZE", "3"))


def _claim_pooled(vid: str) -> bool:
    with _claim_guard:
        rows = store.query("SELECT id FROM visitors WHERE kind = 'pool' AND seeded = 1 ORDER BY created LIMIT 1")
        if not rows:
            return False
        pid = rows[0]["id"]
        with store.connect() as db:
            db.execute("UPDATE cases SET owner = ? WHERE owner = ?", (vid, pid))
            db.execute("DELETE FROM visitors WHERE id = ?", (pid,))
        return True


def refill_pool() -> int:
    """Seed pooled sandboxes until there are pool_size() ready. One refill at a time."""
    if not _refill_guard.acquire(blocking=False):
        return 0
    made = 0
    try:
        while store.query("SELECT COUNT(*) AS n FROM visitors WHERE kind = 'pool'")[0]["n"] < pool_size():
            pid = "pool-" + secrets.token_hex(8)
            with store.connect() as db:
                db.execute("INSERT INTO visitors (id, kind, seeded, requests, created, last_seen) VALUES (?, 'pool', 0, 0, ?, ?)",
                           (pid, store.now(), store.now()))
            seed_sandbox(pid)
            with store.connect() as db:
                db.execute("UPDATE visitors SET seeded = 1 WHERE id = ?", (pid,))
            made += 1
    finally:
        _refill_guard.release()
    return made


def refill_pool_async() -> None:
    if enabled():
        threading.Thread(target=refill_pool, name="sandbox-pool", daemon=True).start()


# ── Rate limits and the spending cap ──────────────────────────────────────

_hits: dict[tuple[str, str], deque] = defaultdict(deque)
_hits_guard = threading.Lock()


def check_rate(bucket: str, vid: str | None = None) -> None:
    """Count one call against the visitor's bucket; 429 once it's full. No-op outside demo mode."""
    vid = vid or visitor.current.get()
    if not enabled() or vid is None:
        return
    limit, window = LIMITS[bucket]
    now = time.monotonic()
    with _hits_guard:
        q = _hits[(vid, bucket)]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            wait = int(window - (now - q[0])) + 1
            raise ToolFailure("rate_limited", f"Demo limit reached: {limit} {bucket} calls per "
                              f"{_window_label(window)}", f"Try again in {_wait_label(wait)}.", status=429,
                              detail={"bucket": bucket, "retry_after_s": wait})
        q.append(now)


def _window_label(s: int) -> str:
    return {60: "minute", 3600: "hour", 86400: "day"}.get(s, f"{s} s")


def _wait_label(s: int) -> str:
    return f"{s} s" if s < 120 else f"{s // 60} min"


def month_spend_usd() -> float:
    start = datetime.now(timezone.utc).strftime("%Y-%m-01")
    rows = store.query("SELECT COALESCE(SUM(cost_usd), 0) AS usd FROM ai_usage WHERE created >= ? AND kind NOT LIKE '%own_key'",
                       (start,))
    return round(rows[0]["usd"], 4)


def cap_reached() -> bool:
    return enabled() and month_spend_usd() >= monthly_cap_usd()


def check_ai(bucket: str, own_key: bool = False) -> None:
    """Gate a paid Anthropic call: rate limit, then the monthly cap (skipped with the visitor's own key)."""
    check_rate(bucket)
    if not own_key and cap_reached():
        raise ToolFailure("spend_cap_reached", "The demo's AI budget for this month is used up",
                          "Add your own Anthropic key in the chat panel, or come back next month. "
                          "Everything else (K-1 review, the return, e-file) still works.", status=402)


def status() -> dict:
    return {"demo": enabled(), "monthly_cap_usd": monthly_cap_usd() if enabled() else None,
            "cap_reached": cap_reached(), "limits": {k: {"max": v[0], "window_s": v[1]} for k, v in LIMITS.items()},
            "mcp_remote": enabled() and invite_code() is not None, "reset_hour_utc": reset_hour_utc()}


def reset_visitor(vid: str) -> list[str]:
    """Reset data in demo mode: wipe only this visitor's sandbox (and case-less research) and re-seed it."""
    with _lock_for(vid):
        owned = [r["id"] for r in store.query("SELECT id FROM cases WHERE owner = ?", (vid,))]
        busy = store.query(f"SELECT 1 FROM documents WHERE status = 'extracting' AND case_id IN "
                           f"({','.join('?' * len(owned))}) LIMIT 1", tuple(owned)) if owned else []
        if busy:
            raise ToolFailure("busy", "A K-1 is still extracting", "Wait for extraction to finish, then reset.",
                              status=409)
        store.delete_cases(owned)
        with store.connect() as db:
            db.execute("DELETE FROM research WHERE case_id IS NULL AND owner = ?", (vid,))
            db.execute("UPDATE visitors SET seeded = 0 WHERE id = ?", (vid,))
    ensure(vid)
    token = visitor.current.set(vid)
    try:
        return [c["id"] for c in store.list_cases()]
    finally:
        visitor.current.reset(token)


# ── Nightly reset ─────────────────────────────────────────────────────────

def _stamp():
    return store.root() / "last_reset"


def reset_due(now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if now.hour < reset_hour_utc():
        return False
    last = _stamp().read_text().strip() if _stamp().exists() else ""
    return last != now.strftime("%Y-%m-%d")


def nightly_reset() -> bool:
    """Wipe every case, re-seed the reference cases, and mark every visitor for a fresh sandbox."""
    busy = store.query("SELECT 1 FROM documents WHERE status = 'extracting' LIMIT 1")
    if busy:
        return False
    store.reset()
    demo.seed()
    with store.connect() as db:
        db.execute("DELETE FROM visitors WHERE kind = 'pool'")
        db.execute("UPDATE visitors SET seeded = 0")
    _hits.clear()
    refill_pool_async()
    _stamp().write_text(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    return True


async def reset_loop(every_s: int = 600) -> None:
    from starlette.concurrency import run_in_threadpool
    if not _stamp().exists():   # a fresh volume: today's seed counts as today's reset
        _stamp().write_text(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    while True:
        if reset_due():
            await run_in_threadpool(nightly_reset)
        await asyncio.sleep(every_s)


paths.load_env()
