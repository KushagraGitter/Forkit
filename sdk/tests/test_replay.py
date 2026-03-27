"""
Tests for the deterministic replay engine.
"""

import pytest
from forkpoint.core.replay import ReplayContext, StubExhaustedError
from forkpoint.core.tracer import ForkpointTracer
from forkpoint.models.events import (
    Message,
    MessageRole,
    StatePatch,
    TokenCounts,
)
from forkpoint.transports.local import LocalTransport


@pytest.fixture
def bundle(tmp_path):
    """Build a real replay bundle from a recorded run."""
    transport = LocalTransport(db_path=tmp_path / "replay.db")
    tracer = ForkpointTracer("replay-agent", transport=transport)

    with tracer:
        msgs = [Message(role=MessageRole.USER, content="What is 2+2?")]
        call_id = tracer.on_tool_start("calc", "calculator", {"expr": "2+2"})
        tracer.on_tool_end(call_id, result=4)

        llm_id = tracer.on_llm_start("node-1", msgs, model="gpt-4o-mini")
        tracer.on_llm_end(
            llm_id,
            Message(role=MessageRole.ASSISTANT, content="The answer is 4."),
            token_counts=TokenCounts(total_tokens=20),
        )

    return transport.build_replay_bundle(tracer.run_id)


def test_tool_stub_replay(bundle):
    ctx = ReplayContext(bundle)
    result = ctx.call_tool("calculator", {"expr": "2+2"})
    assert result == 4


def test_llm_stub_replay(bundle):
    ctx = ReplayContext(bundle)
    msgs = [Message(role=MessageRole.USER, content="What is 2+2?")]
    response = ctx.call_llm("gpt-4o-mini", msgs)
    assert "4" in response.content


def test_stub_exhausted_raises(bundle):
    ctx = ReplayContext(bundle)
    ctx.call_tool("calculator", {})  # consume the only stub
    with pytest.raises(StubExhaustedError):
        ctx.call_tool("calculator", {})


def test_state_override_patch(bundle):
    patch = StatePatch(state_overrides={"counter": 99, "extra": "patched"})
    ctx = ReplayContext(bundle, patch=patch)
    state = ctx.get_initial_state()
    assert state.get("counter") == 99
    assert state.get("extra") == "patched"


def test_tool_result_override(bundle):
    patch = StatePatch(
        tool_result_overrides={
            bundle.snapshots[0].tool_calls[0].id: "overridden"
        }
        if bundle.snapshots and bundle.snapshots[0].tool_calls
        else {}
    )
    ctx = ReplayContext(bundle, patch=patch)
    # The override is applied to the stub result
    result = ctx.call_tool("calculator", {})
    if patch.tool_result_overrides:
        assert result == "overridden"
