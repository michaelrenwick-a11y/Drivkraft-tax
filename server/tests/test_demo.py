"""Phase 10: hosted demo mode. Per-visitor sandboxes, scoping, rate limits, the spend cap,
the MCP invite gate and the per-visitor reset."""
from __future__ import annotations

import pytest

from server import demo, efile, sandbox, store, visitor
from server.errors import ToolFailure
from server.tools import load_all

T = load_all()


def call(_tool, *args, **kwargs):
    return T[_tool].fn(*args, **kwargs)


@pytest.fixture(scope="module", autouse=True)
def data_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    store.configure(root)
    demo.seed()
    yield root
    store._root = None


@pytest.fixture(autouse=True)
def demo_mode(monkeypatch):
    monkeypatch.setenv("DRIVKRAFT_DEMO", "1")
    monkeypatch.setenv("DRIVKRAFT_POOL_SIZE", "0")      # tests seed synchronously
    monkeypatch.setattr(efile, "QUEUE_S", 0)
    monkeypatch.setattr(efile, "ACK_S", 0)
    sandbox._hits.clear()


class As:
    """Run tool calls as one visitor."""
    def __init__(self, vid):
        self.vid = vid

    def __enter__(self):
        self.token = visitor.current.set(self.vid)
        return self

    def __exit__(self, *exc):
        visitor.current.reset(self.token)


@pytest.fixture(scope="module")
def two_visitors():
    a, b = sandbox.new_visitor_id(), sandbox.new_visitor_id()
    timing = efile.QUEUE_S, efile.ACK_S
    efile.QUEUE_S = efile.ACK_S = 0          # the Okafor seed's reject is visible at once
    try:
        sandbox.ensure(a)
        sandbox.ensure(b)
    finally:
        efile.QUEUE_S, efile.ACK_S = timing
    return a, b


def test_sandbox_has_three_seeded_cases(two_visitors):
    a, _ = two_visitors
    with As(a):
        cases = {c["name"]: c for c in call("list_cases")["cases"]}
        assert {"Reference K-1s", "Rivera household", "Chen · W-2 and one K-1", "Okafor · e-file rejected"} <= set(cases)
        rivera = cases["Rivera household"]
        assert rivera["status"] == "ready" and not rivera["read_only"]
        assert [n["sample"] for n in call("list_notes", rivera["id"])["notes"]] == ["rivera-planning"]
        okafor = call("efile_status", cases["Okafor · e-file rejected"]["id"])
        assert okafor["current"]["status"] == "rejected"
        rules = [r["rule"] for r in okafor["current"]["submission"]["rejects"]]
        assert rules == ["IND-031-04"]


def test_visitors_see_only_their_own_cases(two_visitors):
    a, b = two_visitors
    with As(a):
        mine = {c["id"] for c in call("list_cases")["cases"] if not c["read_only"]}
        rivera = next(c for c in call("list_cases")["cases"] if c["name"] == "Rivera household")
        note = call("list_notes", rivera["id"])["notes"][0]
    with As(b):
        theirs = {c["id"] for c in call("list_cases")["cases"] if not c["read_only"]}
        assert mine and theirs and not (mine & theirs)
        with pytest.raises(ToolFailure) as e:
            call("get_case_summary", rivera["id"])
        assert e.value.code == "case_not_found"
        with pytest.raises(ToolFailure):
            call("get_note", note["id"])
        assert all(n["case_id"] in theirs for n in call("list_notes")["notes"])
    # Unscoped (local, stdio) still sees everything.
    assert mine | theirs <= {c["id"] for c in call("list_cases")["cases"]}


def test_notes_to_inbox_is_one_click_and_private(two_visitors):
    a, b = two_visitors
    with As(a):
        rivera = next(c for c in call("list_cases")["cases"] if c["name"] == "Rivera household")
        note = call("list_notes", rivera["id"])["notes"][0]
        made = call("analyze_meeting", note["id"])["proposals"]
        assert made
        assert {p["id"] for p in call("list_proposals")["proposals"]} >= {p["id"] for p in made}
    with As(b):
        assert not {p["id"] for p in call("list_proposals")["proposals"]} & {p["id"] for p in made}


def test_saved_scenarios_need_your_own_case(two_visitors):
    a, _ = two_visitors
    with As(a):
        with pytest.raises(ToolFailure) as e:
            call("run_scenario", "ref-bench-82", {"filing_status": "hoh"}, name="mine")
        assert e.value.code == "case_read_only"
        call("run_scenario", "ref-bench-82", {"filing_status": "hoh"})      # unsaved what-ifs are fine


def test_rate_limit(monkeypatch):
    monkeypatch.setitem(sandbox.LIMITS, "write", (2, 60))
    vid = sandbox.new_visitor_id()
    sandbox.check_rate("write", vid)
    sandbox.check_rate("write", vid)
    with pytest.raises(ToolFailure) as e:
        sandbox.check_rate("write", vid)
    assert e.value.code == "rate_limited" and e.value.status == 429
    sandbox.check_rate("write", sandbox.new_visitor_id())     # per visitor


def test_spend_cap_and_own_key(monkeypatch):
    monkeypatch.setenv("DRIVKRAFT_MONTHLY_CAP_USD", "1")
    base = sandbox.month_spend_usd()
    store.log_ai_usage("chat_own_key", "claude-opus-5", {"input": 10_000_000})   # visitors' own keys don't count
    assert sandbox.month_spend_usd() == base
    store.log_ai_usage("chat", "claude-opus-5", {"input": 1_000_000})            # $5
    assert sandbox.cap_reached()
    with As(sandbox.new_visitor_id()):
        with pytest.raises(ToolFailure) as e:
            sandbox.check_ai("chat")
        assert e.value.code == "spend_cap_reached" and e.value.status == 402
        sandbox.check_ai("chat", own_key=True)


def test_pool_claim_is_instant(monkeypatch):
    monkeypatch.setenv("DRIVKRAFT_POOL_SIZE", "1")
    assert sandbox.refill_pool() == 1
    monkeypatch.setenv("DRIVKRAFT_POOL_SIZE", "0")      # no background refill after the claim
    vid = sandbox.new_visitor_id()
    sandbox.ensure(vid)
    assert store.query("SELECT COUNT(*) AS n FROM visitors WHERE kind = 'pool'")[0]["n"] == 0
    with As(vid):
        assert len([c for c in call("list_cases")["cases"] if not c["read_only"]]) == 3


def test_reset_visitor_only_touches_their_sandbox(two_visitors):
    a, b = two_visitors
    with As(b):
        before_b = {c["id"] for c in call("list_cases")["cases"]}
    with As(a):
        call("create_case", "Scratch", 2025, "single")
        old = {c["id"] for c in call("list_cases")["cases"] if not c["read_only"]}
    fresh = set(sandbox.reset_visitor(a))
    assert len(fresh) == 5 and not (old & fresh)       # 2 reference + 3 new seeds
    with As(b):
        assert {c["id"] for c in call("list_cases")["cases"]} == before_b


def test_nightly_reset_marks_visitors_for_reseed(two_visitors):
    a, _ = two_visitors
    assert sandbox.nightly_reset()
    assert {c["id"] for c in store.list_cases()} == {"ref-k1s", "ref-bench-82"}
    assert store.query("SELECT seeded FROM visitors WHERE id = ?", (a,))[0]["seeded"] == 0
    sandbox.ensure(a)
    with As(a):
        assert len(call("list_cases")["cases"]) == 5
    assert not sandbox.reset_due()


def test_http_cookie_mcp_gate_and_reset(monkeypatch):
    from fastapi.testclient import TestClient
    from server.app import build_http

    monkeypatch.setenv("DRIVKRAFT_INVITE_CODE", "letmein")
    monkeypatch.setenv("DRIVKRAFT_PUBLIC_HOSTS", "testserver")
    with TestClient(build_http()) as client:
        r = client.get("/api/cases")
        assert r.status_code == 200 and sandbox.COOKIE in r.cookies
        names = {c["name"] for c in r.json()["cases"]}
        assert "Rivera household" in names
        again = client.get("/api/cases").json()["cases"]        # same cookie → same sandbox
        assert {c["id"] for c in again} == {c["id"] for c in r.json()["cases"]}
        assert client.get("/api/demo").json()["demo"] is True
        # Reset data resets only this visitor's sandbox.
        out = client.post("/api/admin/reset", json={"confirm": "reset"}).json()
        assert len(out["cases"]) == 5
        # /mcp: no token → 401; the invite token passes the gate.
        assert client.post("/mcp", json={}).status_code == 401
        ok = client.post("/mcp", headers={"Authorization": "Bearer letmein",
                                          "Accept": "application/json, text/event-stream"},
                         json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                             "protocolVersion": "2025-06-18", "capabilities": {},
                             "clientInfo": {"name": "t", "version": "0"}}})
        assert ok.status_code == 200
        # A bad own-key header is refused before any model call.
        bad = client.post("/api/chat", json={"message": "hi"}, headers={"x-anthropic-key": "nope"})
        assert bad.status_code == 422


def test_new_visitors_per_ip_are_limited(monkeypatch):
    monkeypatch.setitem(sandbox.LIMITS, "new_visitor", (1, 3600))
    monkeypatch.setattr(sandbox, "seed_sandbox", lambda vid: [])
    sandbox.ensure(sandbox.new_visitor_id(), client_ip="203.0.113.9")
    with pytest.raises(ToolFailure) as e:
        sandbox.ensure(sandbox.new_visitor_id(), client_ip="203.0.113.9")
    assert e.value.code == "rate_limited"
    sandbox.ensure(sandbox.new_visitor_id(), client_ip="203.0.113.10")
