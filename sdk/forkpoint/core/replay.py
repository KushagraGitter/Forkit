"""
Deterministic replay engine.

Given a ReplayBundle (+ optional StatePatch), replays a run by substituting
all LLM and tool calls with their recorded stubs. The agent code runs for real
but touches no external services — perfect for test generation and fork-from-history.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Callable

from forkpoint.models.events import (
    LLMStub,
    Message,
    ReplayBundle,
    Snapshot,
    StatePatch,
    ToolStub,
)


class StubExhaustedError(RuntimeError):
    """Raised when more calls are made than stubs recorded."""


class ReplayContext:
    """
    Holds the stub queues for one replay session.
    Pass to your agent code as a way to intercept calls.
    """

    def __init__(self, bundle: ReplayBundle, patch: StatePatch | None = None) -> None:
        self._bundle = bundle
        self._patch = patch

        # Build ordered queues from the bundle
        self._tool_queues: dict[str, list[ToolStub]] = defaultdict(list)
        for name, stubs in bundle.tool_stubs.items():
            self._tool_queues[name] = list(stubs)

        self._llm_queues: dict[str, list[LLMStub]] = defaultdict(list)
        for model, stubs in bundle.llm_stubs.items():
            self._llm_queues[model] = list(stubs)

        # Apply tool_result_overrides from patch
        if patch and patch.tool_result_overrides:
            for tool_call_id, result in patch.tool_result_overrides.items():
                for stubs in self._tool_queues.values():
                    for stub in stubs:
                        if stub.tool_call_id == tool_call_id:
                            stub.result = result

    def call_tool(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        """Return the next stubbed result for this tool."""
        queue = self._tool_queues.get(tool_name, [])
        if not queue:
            raise StubExhaustedError(
                f"No more stubs for tool {tool_name!r}. "
                f"Did the replay call this tool more times than the original run?"
            )
        stub = queue.pop(0)
        if stub.error:
            raise RuntimeError(stub.error)
        return stub.result

    def call_llm(self, model: str, messages: list[Message], **params) -> Message:
        """Return the next stubbed LLM response for this model."""
        # Apply model_param_overrides from patch
        if self._patch and self._patch.model_param_overrides:
            params.update(self._patch.model_param_overrides)

        # Apply message_overrides from patch
        patched_messages = list(messages)
        if self._patch:
            for override in self._patch.message_overrides:
                if 0 <= override.index < len(patched_messages):
                    patched_messages[override.index] = override.message

        queue = self._llm_queues.get(model, [])
        if not queue:
            raise StubExhaustedError(
                f"No more stubs for model {model!r}. "
                f"Did the replay call this model more times than the original run?"
            )
        return queue.pop(0).response

    def get_initial_state(self) -> dict[str, Any]:
        """State at the fork point, with patch applied."""
        if not self._bundle.snapshots:
            return {}
        # Find the fork point snapshot if this is a fork
        fork_snapshot_id = self._bundle.run.fork_point_snapshot_id
        if fork_snapshot_id:
            snap = next(
                (s for s in self._bundle.snapshots if s.id == fork_snapshot_id), None
            )
            state = dict(snap.agent_state) if snap else {}
        else:
            # Start from the first snapshot's state
            state = dict(self._bundle.snapshots[0].agent_state)

        if self._patch and self._patch.state_overrides:
            state.update(self._patch.state_overrides)
        return state


def build_replay_context(
    bundle: ReplayBundle, patch: StatePatch | None = None
) -> ReplayContext:
    """Convenience factory."""
    return ReplayContext(bundle, patch)
