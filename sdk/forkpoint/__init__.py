"""
Forkpoint — Runtime debugger for multi-agent AI systems.
Treat agent runs like git commits.
"""

from forkpoint.core.tracer import ForkpointTracer, trace
from forkpoint.core.replay import ReplayContext, build_replay_context
from forkpoint.transports.local import LocalTransport
from forkpoint.transports.http import HttpTransport
from forkpoint.models.events import (
    Run,
    Snapshot,
    Fork,
    StatePatch,
    ReplayBundle,
    RunDiff,
    Message,
    MessageRole,
    NodeType,
    Framework,
    RunStatus,
)

__version__ = "0.1.0"
__all__ = [
    "ForkpointTracer",
    "trace",
    "ReplayContext",
    "build_replay_context",
    "LocalTransport",
    "HttpTransport",
    "Run",
    "Snapshot",
    "Fork",
    "StatePatch",
    "ReplayBundle",
    "RunDiff",
    "Message",
    "MessageRole",
    "NodeType",
    "Framework",
    "RunStatus",
]


def instrument_langgraph(graph, agent_id: str, **kwargs):
    from forkpoint.integrations.langgraph import instrument_langgraph as _impl
    return _impl(graph, agent_id, **kwargs)
