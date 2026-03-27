"""
Tests for ForkpointTracer — the core SDK API.
"""

import pytest
from forkpoint.core.tracer import ForkpointTracer
from forkpoint.models.events import (
    Framework,
    Message,
    MessageRole,
    NodeType,
    RunStatus,
    TokenCounts,
)
from forkpoint.transports.local import LocalTransport


@pytest.fixture
def tmp_tracer(tmp_path):
    transport = LocalTransport(db_path=tmp_path / "test.db")
    tracer = ForkpointTracer(
        agent_id="test-agent",
        transport=transport,
        framework=Framework.RAW,
    )
    return tracer, transport


def test_run_lifecycle(tmp_tracer):
    tracer, transport = tmp_tracer
    with tracer:
        tracer.on_agent_start("planner", {"step": 0})
        tracer.on_agent_end("planner", {"step": 1})

    assert tracer.run.status == RunStatus.COMPLETED
    assert tracer.run.ended_at is not None
    assert tracer.run.root_snapshot_id is not None


def test_llm_call_roundtrip(tmp_tracer):
    tracer, _ = tmp_tracer
    with tracer:
        msgs = [Message(role=MessageRole.USER, content="hello")]
        call_id = tracer.on_llm_start("node-a", msgs, model="gpt-4o")
        response = Message(role=MessageRole.ASSISTANT, content="world")
        snap = tracer.on_llm_end(call_id, response, token_counts=TokenCounts(total_tokens=10))

    assert snap.node_type == NodeType.LLM_CALL
    assert snap.model == "gpt-4o"
    assert snap.messages_out[0].content == "world"
    assert snap.token_counts.total_tokens == 10


def test_tool_call_roundtrip(tmp_tracer):
    tracer, _ = tmp_tracer
    with tracer:
        call_id = tracer.on_tool_start("search", "search_web", {"query": "test"})
        snap = tracer.on_tool_end(call_id, result={"hits": ["a", "b"]})

    assert snap.node_type == NodeType.TOOL_CALL
    assert snap.tool_calls[0].name == "search_web"
    assert snap.tool_results[0].result == {"hits": ["a", "b"]}


def test_snapshot_sequence_numbers(tmp_tracer):
    tracer, _ = tmp_tracer
    with tracer:
        tracer.on_agent_start("a", {})
        msgs = [Message(role=MessageRole.USER, content="hi")]
        cid = tracer.on_llm_start("a", msgs, model="gpt-4o-mini")
        tracer.on_llm_end(cid, Message(role=MessageRole.ASSISTANT, content="ok"))
        tracer.on_agent_end("a", {})

    seqs = [s.sequence_number for s in tracer.snapshots]
    assert seqs == sorted(seqs)
    assert seqs[0] == 1


def test_error_captured_on_exception(tmp_tracer):
    tracer, _ = tmp_tracer
    with pytest.raises(ValueError):
        with tracer:
            raise ValueError("deliberate failure")

    assert tracer.run.status == RunStatus.FAILED
    assert tracer.run.error is not None
    assert "deliberate" in tracer.run.error.message


def test_replay_bundle(tmp_tracer):
    tracer, transport = tmp_tracer
    with tracer:
        msgs = [Message(role=MessageRole.USER, content="ping")]
        cid = tracer.on_llm_start("n1", msgs, model="gpt-4o")
        tracer.on_llm_end(cid, Message(role=MessageRole.ASSISTANT, content="pong"))

    bundle = transport.build_replay_bundle(tracer.run_id)
    assert bundle.run.id == tracer.run_id
    assert len(bundle.snapshots) == 1
    assert "gpt-4o" in bundle.llm_stubs
    assert len(bundle.llm_stubs["gpt-4o"]) == 1


def test_fork_creates_child_tracer(tmp_tracer):
    tracer, transport = tmp_tracer
    snap_id = None
    with tracer:
        tracer.on_agent_start("root", {"counter": 0})
        snap = tracer.snapshots[-1]
        snap_id = snap.id

    child = tracer.fork(snap_id, reason="test fork")
    assert child.run.parent_run_id == tracer.run_id
    assert child.run.fork_point_snapshot_id == snap_id


def test_local_transport_persistence(tmp_path):
    db = tmp_path / "persist.db"
    t1 = LocalTransport(db_path=db)
    tracer = ForkpointTracer("persist-agent", transport=t1)
    with tracer:
        tracer.on_agent_start("n", {})

    # New connection, same file
    t2 = LocalTransport(db_path=db)
    runs = t2.list_runs()
    assert any(r.id == tracer.run_id for r in runs)
    snaps = t2.get_snapshots(tracer.run_id)
    assert len(snaps) == 1
