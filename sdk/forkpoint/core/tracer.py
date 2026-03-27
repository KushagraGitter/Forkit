"""
ForkpointTracer — the central event bus and SDK public API.

One tracer per run. Integrations (LangGraph, CrewAI, raw) call the on_* hooks;
the tracer serializes every state transition into an immutable Snapshot and ships
it to the configured Transport.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

from forkpoint.models.events import (
    AlternativeDecision,
    ErrorInfo,
    Fork,
    Framework,
    LogprobEntry,
    Message,
    MessageRole,
    NodeType,
    ReplayBundle,
    Run,
    RunStatus,
    Snapshot,
    StatePatch,
    TokenCounts,
    ToolCall,
    ToolResult,
)
from forkpoint.transports.base import Transport
from forkpoint.transports.local import LocalTransport


class _PendingCall:
    """Tracks an in-flight LLM or tool call between on_*_start and on_*_end."""

    __slots__ = ("call_id", "node_id", "node_type", "started_at", "extra")

    def __init__(self, call_id: str, node_id: str, node_type: NodeType, extra: dict):
        self.call_id = call_id
        self.node_id = node_id
        self.node_type = node_type
        self.started_at = time.monotonic()
        self.extra = extra


class ForkpointTracer:
    """
    Core tracer. Wraps one agent run — captures every LLM call, tool call,
    and agent message as an immutable Snapshot.

    Usage::

        with ForkpointTracer(agent_id="my-pipeline") as tracer:
            result = my_agent.run(inputs)

        # or pass to an integration:
        graph = instrument_langgraph(graph, tracer=tracer)
    """

    def __init__(
        self,
        agent_id: str,
        transport: Transport | None = None,
        framework: Framework = Framework.RAW,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        fork_point_snapshot_id: str | None = None,
        tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        seed: str = "",
    ) -> None:
        self.transport = transport or LocalTransport()
        self._run = Run.create(
            agent_id=agent_id,
            framework=framework,
            parent_run_id=parent_run_id,
            fork_point_snapshot_id=fork_point_snapshot_id,
            tags=tags or {},
            metadata=metadata or {},
            seed=seed,
        )
        if run_id:
            # Allow callers to supply a stable ID (e.g. when replaying)
            self._run.id = run_id

        self._snapshots: list[Snapshot] = []
        self._pending: dict[str, _PendingCall] = {}  # call_id -> pending
        self._seq = 0
        self._agent_state: dict[str, Any] = {}
        self._closed = False

    # ------------------------------------------------------------------
    # Context manager interface
    # ------------------------------------------------------------------

    def __enter__(self) -> "ForkpointTracer":
        self.transport.start_run(self._run)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            import traceback as tb
            self._run.error = ErrorInfo(
                type=exc_type.__name__,
                message=str(exc_val),
                traceback="".join(tb.format_tb(exc_tb)),
            )
            self._run.status = RunStatus.FAILED
        else:
            self._run.status = RunStatus.COMPLETED
        self._run.ended_at = datetime.now(timezone.utc)
        self.transport.end_run(self._run)
        self.transport.flush()
        self._closed = True

    # ------------------------------------------------------------------
    # Agent lifecycle hooks
    # ------------------------------------------------------------------

    def on_agent_start(self, node_id: str, state: dict[str, Any]) -> Snapshot:
        self._agent_state = dict(state)
        snap = self._emit(
            node_id=node_id,
            node_type=NodeType.AGENT_START,
            agent_state=state,
        )
        if self._run.root_snapshot_id is None:
            self._run.root_snapshot_id = snap.id
        return snap

    def on_agent_end(
        self,
        node_id: str,
        state: dict[str, Any],
        error: Exception | None = None,
    ) -> Snapshot:
        self._agent_state = dict(state)
        snap = self._emit(
            node_id=node_id,
            node_type=NodeType.AGENT_END,
            agent_state=state,
        )
        self._run.terminal_snapshot_id = snap.id
        return snap

    def on_agent_message(self, node_id: str, message: Message) -> Snapshot:
        return self._emit(
            node_id=node_id,
            node_type=NodeType.AGENT_MESSAGE,
            messages_out=[message],
            agent_state=dict(self._agent_state),
        )

    # ------------------------------------------------------------------
    # LLM call hooks
    # ------------------------------------------------------------------

    def on_llm_start(
        self,
        node_id: str,
        messages: list[Message],
        model: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Returns call_id to pass to on_llm_end."""
        call_id = uuid.uuid4().hex
        self._pending[call_id] = _PendingCall(
            call_id=call_id,
            node_id=node_id,
            node_type=NodeType.LLM_CALL,
            extra={"messages_in": messages, "model": model, "params": params or {}},
        )
        return call_id

    def on_llm_end(
        self,
        call_id: str,
        response: Message,
        logprobs: list[LogprobEntry] | None = None,
        token_counts: TokenCounts | None = None,
    ) -> Snapshot:
        pending = self._pending.pop(call_id, None)
        if pending is None:
            raise ValueError(f"Unknown call_id: {call_id!r}")
        latency_ms = int((time.monotonic() - pending.started_at) * 1000)
        return self._emit(
            node_id=pending.node_id,
            node_type=NodeType.LLM_CALL,
            messages_in=pending.extra["messages_in"],
            messages_out=[response],
            model=pending.extra["model"],
            model_params=pending.extra["params"],
            latency_ms=latency_ms,
            token_counts=token_counts,
            logprobs=logprobs,
            agent_state=dict(self._agent_state),
        )

    # ------------------------------------------------------------------
    # Tool call hooks
    # ------------------------------------------------------------------

    def on_tool_start(
        self,
        node_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> str:
        """Returns call_id to pass to on_tool_end."""
        call_id = uuid.uuid4().hex
        tool_call = ToolCall(id=call_id, name=tool_name, arguments=tool_input)
        self._pending[call_id] = _PendingCall(
            call_id=call_id,
            node_id=node_id,
            node_type=NodeType.TOOL_CALL,
            extra={"tool_call": tool_call},
        )
        return call_id

    def on_tool_end(
        self,
        call_id: str,
        result: Any,
        error: Exception | None = None,
    ) -> Snapshot:
        pending = self._pending.pop(call_id, None)
        if pending is None:
            raise ValueError(f"Unknown call_id: {call_id!r}")
        latency_ms = int((time.monotonic() - pending.started_at) * 1000)
        tool_call: ToolCall = pending.extra["tool_call"]
        tool_result = ToolResult(
            tool_call_id=call_id,
            name=tool_call.name,
            result=result,
            error=str(error) if error else None,
        )
        return self._emit(
            node_id=pending.node_id,
            node_type=NodeType.TOOL_CALL,
            tool_calls=[tool_call],
            tool_results=[tool_result],
            latency_ms=latency_ms,
            agent_state=dict(self._agent_state),
        )

    # ------------------------------------------------------------------
    # State update hook (called by integrations on any state change)
    # ------------------------------------------------------------------

    def update_state(self, state: dict[str, Any]) -> None:
        self._agent_state = dict(state)

    # ------------------------------------------------------------------
    # Fork
    # ------------------------------------------------------------------

    def fork(
        self,
        from_snapshot_id: str,
        patch: StatePatch | None = None,
        reason: str | None = None,
    ) -> "ForkpointTracer":
        """
        Create a new tracer that branches from a historical snapshot.
        The new tracer starts with the patched state from that snapshot.
        Returns the child tracer (not yet started — caller must use as context manager).
        """
        # Find the snapshot locally if we have it
        source_snap = next(
            (s for s in self._snapshots if s.id == from_snapshot_id), None
        )

        child = ForkpointTracer(
            agent_id=self._run.agent_id,
            transport=self.transport,
            framework=self._run.framework,
            parent_run_id=self._run.id,
            fork_point_snapshot_id=from_snapshot_id,
            tags=dict(self._run.tags),
            metadata=dict(self._run.metadata),
        )

        # Apply patch to initial state
        if source_snap is not None:
            child._agent_state = dict(source_snap.agent_state)
            if patch and patch.state_overrides:
                child._agent_state.update(patch.state_overrides)

        # Record the fork lineage
        fork_record = Fork.create(
            source_run_id=self._run.id,
            source_snapshot_id=from_snapshot_id,
            forked_run_id=child._run.id,
            patch=patch,
            reason=reason,
        )
        self.transport.record_fork(fork_record)

        return child

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def run(self) -> Run:
        return self._run

    @property
    def run_id(self) -> str:
        return self._run.id

    @property
    def snapshots(self) -> list[Snapshot]:
        return list(self._snapshots)

    def get_replay_bundle(self) -> ReplayBundle:
        return self.transport.build_replay_bundle(self._run.id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _emit(self, node_id: str, node_type: NodeType, **kwargs: Any) -> Snapshot:
        parent_id = self._snapshots[-1].id if self._snapshots else None
        snap = Snapshot.create(
            run_id=self._run.id,
            node_id=node_id,
            node_type=node_type,
            sequence_number=self._next_seq(),
            parent_snapshot_id=parent_id,
            **kwargs,
        )
        self._snapshots.append(snap)
        self.transport.emit_snapshot(snap)
        return snap


# ---------------------------------------------------------------------------
# Convenience decorator
# ---------------------------------------------------------------------------


def trace(agent_id: str, framework: Framework = Framework.RAW, **tracer_kwargs):
    """
    Decorator that wraps a function in a ForkpointTracer context.

    Usage::

        @trace(agent_id="my-pipeline")
        def run_my_agent(inputs):
            ...
    """

    def decorator(fn):
        import functools

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with ForkpointTracer(agent_id=agent_id, framework=framework, **tracer_kwargs):
                return fn(*args, **kwargs)

        return wrapper

    return decorator
