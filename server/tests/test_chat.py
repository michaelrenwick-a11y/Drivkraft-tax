"""Phase 4: proposals (the only way chat changes data) and the chat loop over MCP.

The chat tests script a fake Anthropic client, so they run without a key and
check our side of the loop: tool calls go through MCP, write tools are refused,
sources are collected, and the SSE stream has the right shape.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace as NS

import pytest

from server import chat, demo, store
from server.errors import ToolFailure
from server.tools import load_all

T = load_all()


def call(_tool, *args, **kwargs):
    return T[_tool].fn(*args, **kwargs)


@pytest.fixture(scope="module", autouse=True)
def data_root(tmp_path_factory):
    store.configure(tmp_path_factory.mktemp("data"))
    demo.seed()
    yield
    store._root = None


@pytest.fixture(scope="module")
def oak():
    case = call("create_case", "Oak household", 2025, "single")["case"]
    doc = call("intake_k1", case["id"], "oak-ventures")["document"]
    return case, doc


# ── Proposals ─────────────────────────────────────────────────────────────

def test_proposals_need_an_editable_case():
    with pytest.raises(ToolFailure) as e:
        call("propose_edit", "ref-proof", "part_iii.box_1", 1, "test")
    assert e.value.code == "case_read_only"


def test_proposal_accept_undo_reject(oak):
    case, doc = oak
    before = call("get_k1_box", doc["id"], "1")["entries"][0]["value"]
    out = call("propose_edit", doc["id"], "part_iii.box_1", before + 1000, "PDF shows a higher amount",
               citations=[f"k1://{doc['id']}/box/part_iii.box_1", "made-up://x"])
    p = out["proposal"]
    assert p["status"] == "pending" and p["old_value"] == before and p["note"]
    assert p["citations"][0]["type"] == "k1_box" and p["citations"][1]["type"] == "other"
    # Nothing changed yet; a repeat is recognised as a duplicate.
    assert call("get_k1_box", doc["id"], "1")["entries"][0]["value"] == before
    assert call("propose_edit", doc["id"], "part_iii.box_1", before + 1000, "again")["duplicate"]
    assert call("list_proposals", case["id"])["counts"]["pending"] == 1

    acc = call("accept_proposal", p["id"])
    assert acc["proposal"]["status"] == "accepted" and acc["edit"]["reason"].startswith("Accepted proposal")
    assert call("get_k1_box", doc["id"], "1")["entries"][0]["value"] == before + 1000
    with pytest.raises(ToolFailure) as e:
        call("accept_proposal", p["id"])
    assert e.value.code == "not_pending"

    assert call("undo_proposal", p["id"])["proposal"]["status"] == "pending"
    assert call("get_k1_box", doc["id"], "1")["entries"][0]["value"] == before
    assert len(store.list_edits(doc["id"])) == 2       # history kept: the edit and its undo

    assert call("reject_proposal", p["id"])["proposal"]["status"] == "rejected"
    assert call("undo_proposal", p["id"])["proposal"]["status"] == "pending"


def test_stale_proposal_is_refused(oak):
    _, doc = oak
    p = call("propose_edit", doc["id"], "part_iii.box_2", 1234, "stale test")["proposal"]
    call("edit_k1_value", doc["id"], "part_iii.box_2", 999, "changed by hand")
    with pytest.raises(ToolFailure) as e:
        call("accept_proposal", p["id"])
    assert e.value.code == "stale_proposal"
    call("reject_proposal", p["id"])


# ── Chat loop (fake client) ───────────────────────────────────────────────

class FakeStream:
    def __init__(self, message):
        self.message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for b in self.message.content:
                yield NS(type="content_block_start", content_block=b)
                if b.type == "text":
                    for i in range(0, len(b.text), 20):
                        yield NS(type="content_block_delta", delta=NS(type="text_delta", text=b.text[i:i + 20]))
        return gen()

    async def get_final_message(self):
        return self.message


class FakeClient:
    """Plays back scripted assistant turns and records each request."""

    def __init__(self, turns):
        self.turns, self.requests = list(turns), []
        self.beta = NS(messages=NS(stream=self._stream))

    def _stream(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return FakeStream(self.turns.pop(0))


def tool_use(id_, name, input_):
    return NS(type="tool_use", id=id_, name=name, input=input_)


def turn(*blocks, stop="end_turn"):
    return NS(content=list(blocks), stop_reason=stop,
              usage=NS(input_tokens=10, output_tokens=5, cache_read_input_tokens=0))


def run(client, message, cid=None, path=None):
    from server.app import build_mcp

    async def go():
        out = []
        async for chunk in chat.run_turn(build_mcp(), message, cid, path, client=client):
            for frame in chunk.decode().strip().split("\n\n"):
                ev, data = frame.split("\n", 1)
                out.append((ev.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
        return out

    return asyncio.run(go())


def test_chat_tools_are_read_only_plus_proposals():
    from server.app import build_mcp

    tools = {t["name"]: t for t in asyncio.run(chat.anthropic_tools(build_mcp()))}
    assert {"get_k1_box", "explain_line", "propose_edit", "run_scenario"} <= set(tools)
    assert not {"edit_k1_value", "approve_k1", "acknowledge_flag", "accept_proposal", "create_case"} & set(tools)
    assert "name" not in tools["run_scenario"]["input_schema"]["properties"]
    assert all(t["eager_input_streaming"] for t in tools.values())


def test_chat_turn_calls_tools_over_mcp_and_streams_citations(oak):
    case, doc = oak
    ref = "k1://ref-proof/box/part_iii.box_1"
    client = FakeClient([
        turn(tool_use("t1", "get_k1_box", {"doc_id": "ref-proof", "box": "1"}),
             tool_use("t2", "edit_k1_value", {"doc_id": doc["id"], "path": "part_iii.box_1", "value": 1, "reason": "x"}),
             stop="tool_use"),
        turn(NS(type="text", text=f"Box 1 is on the proof K-1 [[{ref}]].")),
    ])
    events = run(client, "What's in Box 1?", path=f"/cases/{case['id']}/k1/{doc['id']}")
    kinds = [e for e, _ in events]
    assert kinds[0] == "conversation" and kinds[-1] == "done" and "error" not in kinds
    ends = {d["id"]: d for e, d in events if e == "tool_end"}
    assert ends["t1"]["ok"] and not ends["t2"]["ok"] and ends["t2"]["error"]["code"] == "not_allowed"
    labels = [d["label"] for e, d in events if e == "tool_start" and d.get("input")]
    assert "Reading K-1 Box 1" in labels
    srcs = [s["ref"] for e, d in events if e == "sources" for s in d["sources"]]
    assert ref in srcs
    assert "".join(d["text"] for e, d in events if e == "text").endswith(f"[[{ref}]].")
    # The page context rides along with the user's message; tool results go back as one user turn.
    first = client.requests[0]["messages"][-1]["content"]
    assert doc["id"] in first[0]["text"] and first[1]["text"] == "What's in Box 1?"
    second = client.requests[1]["messages"]
    assert [b["type"] for b in second[-1]["content"]] == ["tool_result", "tool_result"]
    assert client.requests[0]["fallbacks"] == "default"
    # A follow-up in the same conversation sends the whole history, unchanged.
    cid = events[0][1]["id"]
    client2 = FakeClient([turn(NS(type="text", text="Yes."))])
    run(client2, "Thanks", cid)
    assert client2.requests[0]["messages"][:len(second) + 1][:len(second)] == second


def test_chat_proposal_is_tagged_and_scenario_never_saved(oak):
    case, doc = oak
    client = FakeClient([
        turn(tool_use("p1", "propose_edit", {"doc_id": doc["id"], "path": "part_iii.box_5", "value": 4321,
                                             "rationale": "Chat test"}),
             tool_use("s1", "run_scenario", {"case_id": "ref-bench-82", "changes": {"filing_status": "mfj"},
                                             "name": "should not save"}),
             stop="tool_use"),
        turn(NS(type="text", text="Proposed.")),
    ])
    events = run(client, "Fix Box 5")
    ends = {d["id"]: d for e, d in events if e == "tool_end"}
    assert ends["p1"]["ok"] and ends["s1"]["ok"], ends
    props = [p for p in store.list_proposals(case["id"], "pending") if p["path"] == "part_iii.box_5"]
    assert props and props[0]["origin"] == "chat"
    assert call("list_scenarios", "ref-bench-82")["scenarios"] == []
    assert any(s["type"] == "proposal" for e, d in events if e == "sources" for s in d["sources"])


def test_chat_without_credentials_says_how_to_configure(monkeypatch):
    monkeypatch.setattr(chat, "configured", lambda: False)
    from server.app import build_mcp

    async def go():
        return [c async for c in chat.run_turn(build_mcp(), "hi", None, None)]

    frames = b"".join(asyncio.run(go())).decode()
    assert "event: error" in frames and "not_configured" in frames and ".env" in frames
