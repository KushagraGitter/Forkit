"""
All event and core data types for Forkpoint.
These Pydantic models are the canonical source of truth — backend ORM and frontend
TypeScript types are derived from these.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Framework(str, Enum):
    LANGGRAPH = "langgraph"
    CREWAI = "crewai"
    AUTOGEN = "autogen"
    RAW = "raw"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REPLAYING = "replaying"
    PAUSED = "paused"


class NodeType(str, Enum):
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    AGENT_MESSAGE = "agent_message"
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    HUMAN_INPUT = "human_input"
    FORK_POINT = "fork_point"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FUNCTION = "function"


class MatchType(str, Enum):
    IDENTICAL = "identical"
    MODIFIED = "modified"
    ADDED = "added"
    REMOVED = "removed"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class Message(BaseModel):
    role: MessageRole
    content: str | list[dict[str, Any]]  # string or content blocks
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolResult(BaseModel):
    tool_call_id: str
    name: str
    result: Any
    error: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TokenCounts(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LogprobEntry(BaseModel):
    token: str
    logprob: float
    top_logprobs: list[dict[str, float]] = Field(default_factory=list)


class AlternativeDecision(BaseModel):
    """Captured alternative paths the agent could have taken (Layer 3 — causal analysis)."""
    node_id: str
    description: str
    probability: float | None = None
    logprob_delta: float | None = None
    why_not_chosen: str | None = None  # filled by secondary LLM analysis


class ErrorInfo(BaseModel):
    type: str
    message: str
    traceback: str | None = None


class TokenCounts(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


# ---------------------------------------------------------------------------
# Core primitives
# ---------------------------------------------------------------------------


class Run(BaseModel):
    """
    A Run is the top-level container for one agent execution. Analogous to a git commit.
    The id is content-addressable: sha256(agent_id + start_time_iso + seed).
    """

    id: str
    parent_run_id: str | None = None
    fork_point_snapshot_id: str | None = None
    agent_id: str
    framework: Framework = Framework.RAW
    status: RunStatus = RunStatus.RUNNING
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    root_snapshot_id: str | None = None
    terminal_snapshot_id: str | None = None
    error: ErrorInfo | None = None
    seed: str = ""

    @classmethod
    def create(
        cls,
        agent_id: str,
        framework: Framework = Framework.RAW,
        parent_run_id: str | None = None,
        fork_point_snapshot_id: str | None = None,
        tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        seed: str = "",
    ) -> "Run":
        now = datetime.now(timezone.utc)
        raw = f"{agent_id}:{now.isoformat()}:{seed}"
        run_id = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return cls(
            id=run_id,
            agent_id=agent_id,
            framework=framework,
            parent_run_id=parent_run_id,
            fork_point_snapshot_id=fork_point_snapshot_id,
            started_at=now,
            tags=tags or {},
            metadata=metadata or {},
            seed=seed,
        )


class Snapshot(BaseModel):
    """
    An immutable snapshot of the agent system at one discrete execution point.
    Analogous to a git tree entry — content-addressable, deduplicated automatically.
    """

    id: str
    run_id: str
    parent_snapshot_id: str | None = None
    sequence_number: int
    node_id: str
    node_type: NodeType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Full state for replay
    messages_in: list[Message] = Field(default_factory=list)
    messages_out: list[Message] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    agent_state: dict[str, Any] = Field(default_factory=dict)

    # Execution metadata
    model: str | None = None
    model_params: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | None = None
    token_counts: TokenCounts | None = None

    # Causal analysis (Layer 3)
    logprobs: list[LogprobEntry] | None = None
    alternatives_considered: list[AlternativeDecision] | None = None

    @classmethod
    def create(
        cls,
        run_id: str,
        node_id: str,
        node_type: NodeType,
        sequence_number: int,
        parent_snapshot_id: str | None = None,
        **kwargs: Any,
    ) -> "Snapshot":
        now = datetime.now(timezone.utc)
        # Content-addressable ID
        content = json.dumps(
            {
                "run_id": run_id,
                "node_id": node_id,
                "seq": sequence_number,
                "ts": now.isoformat(),
            },
            sort_keys=True,
        )
        snap_id = hashlib.sha256(content.encode()).hexdigest()[:24]
        return cls(
            id=snap_id,
            run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            sequence_number=sequence_number,
            parent_snapshot_id=parent_snapshot_id,
            timestamp=now,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Fork and replay primitives
# ---------------------------------------------------------------------------


class MessageOverride(BaseModel):
    """Replace a specific message in the replay by index."""
    index: int
    message: Message


class StatePatch(BaseModel):
    """
    JSON-Merge-Patch style modifications applied to a snapshot before replay.
    Enables 'edit state then replay' — the core fork primitive.
    """

    message_overrides: list[MessageOverride] = Field(default_factory=list)
    state_overrides: dict[str, Any] = Field(default_factory=dict)
    tool_result_overrides: dict[str, Any] = Field(default_factory=dict)  # tool_call_id -> result
    model_param_overrides: dict[str, Any] = Field(default_factory=dict)


class Fork(BaseModel):
    """
    Records the lineage of a forked run. Analogous to a git branch pointer.
    """

    id: str
    source_run_id: str
    source_snapshot_id: str
    forked_run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    patch: StatePatch | None = None
    reason: str | None = None

    @classmethod
    def create(
        cls,
        source_run_id: str,
        source_snapshot_id: str,
        forked_run_id: str,
        patch: StatePatch | None = None,
        reason: str | None = None,
    ) -> "Fork":
        raw = f"{source_run_id}:{source_snapshot_id}:{forked_run_id}"
        fork_id = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return cls(
            id=fork_id,
            source_run_id=source_run_id,
            source_snapshot_id=source_snapshot_id,
            forked_run_id=forked_run_id,
            patch=patch,
            reason=reason,
        )


# ---------------------------------------------------------------------------
# Replay bundle — self-contained deterministic re-execution package
# ---------------------------------------------------------------------------


class ToolStub(BaseModel):
    """A canned tool response for deterministic replay."""
    tool_call_id: str
    tool_name: str
    result: Any
    error: str | None = None


class LLMStub(BaseModel):
    """A canned LLM completion for deterministic replay."""
    call_id: str
    model: str
    messages_hash: str  # sha256 of serialized input messages
    response: Message
    logprobs: list[LogprobEntry] | None = None
    token_counts: TokenCounts | None = None


class ReplayBundle(BaseModel):
    """
    Everything needed to re-execute a run deterministically with no external dependencies.
    Can be exported, archived, shared, and used to generate test cases (Layer 5).
    """

    schema_version: str = "1.0"
    run: Run
    snapshots: list[Snapshot]  # ordered by sequence_number
    forks: list[Fork] = Field(default_factory=list)
    tool_stubs: dict[str, list[ToolStub]] = Field(default_factory=dict)  # tool_name -> stubs
    llm_stubs: dict[str, list[LLMStub]] = Field(default_factory=dict)  # model -> stubs


# ---------------------------------------------------------------------------
# Diff models (Layer 2 — side-by-side run comparison)
# ---------------------------------------------------------------------------


class FieldDiff(BaseModel):
    field_path: str  # e.g. "messages_out[0].content"
    value_a: Any
    value_b: Any


class SnapshotPair(BaseModel):
    snapshot_a_id: str | None
    snapshot_b_id: str | None
    node_id: str
    match_type: MatchType
    field_diffs: list[FieldDiff] = Field(default_factory=list)


class DiffSummary(BaseModel):
    total_snapshots_a: int
    total_snapshots_b: int
    identical: int
    modified: int
    added: int
    removed: int
    first_divergence_sequence: int | None = None


class RunDiff(BaseModel):
    run_a_id: str
    run_b_id: str
    common_ancestor_snapshot_id: str | None = None
    snapshot_pairs: list[SnapshotPair] = Field(default_factory=list)
    summary: DiffSummary


# ---------------------------------------------------------------------------
# Ingest event envelope (SDK → backend transport)
# ---------------------------------------------------------------------------


class SnapshotEvent(BaseModel):
    """Envelope sent by the SDK transport to the backend ingest endpoint."""
    event_type: str  # "snapshot_created" | "run_started" | "run_ended"
    run_id: str
    agent_id: str
    payload: dict[str, Any]  # serialized Snapshot, Run, etc.
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Analysis models (Layers 3, 4, 5)
# ---------------------------------------------------------------------------


class CausalAnalysis(BaseModel):
    """Why the agent chose path A over B at a decision node (Layer 3)."""
    snapshot_id: str
    run_id: str
    node_id: str
    chosen_path_summary: str
    alternatives: list[AlternativeDecision]
    reasoning: str  # secondary LLM explanation
    confidence: float  # 0.0–1.0
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DriftReport(BaseModel):
    """Semantic quality of inter-agent data handoffs (Layer 4)."""
    run_id: str
    edges_analyzed: int
    flagged_edges: list[DriftEdge]
    overall_health_score: float  # 0.0–1.0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DriftEdge(BaseModel):
    from_node_id: str
    to_node_id: str
    from_snapshot_id: str
    to_snapshot_id: str
    expected_schema: dict[str, Any] | None
    actual_content_summary: str
    similarity_score: float  # cosine similarity of embeddings
    flagged: bool
    flag_reason: str | None = None


class GeneratedTestCase(BaseModel):
    """Pytest test case auto-generated from a production failure (Layer 5)."""
    run_id: str
    test_file_content: str  # rendered Python source
    num_tool_stubs: int
    num_llm_stubs: int
    failure_summary: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
