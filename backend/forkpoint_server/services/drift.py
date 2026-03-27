"""
Semantic drift detection (Layer 4).

Monitors quality of inter-agent data handoffs by comparing the semantic
similarity of what one agent produced versus what the next agent received.
Flags handoffs where cosine similarity drops below a threshold — indicating
context degradation even when the JSON is technically valid.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../sdk"))
from forkpoint.models.events import DriftEdge, DriftReport, NodeType, Snapshot

_DRIFT_THRESHOLD = float(os.getenv("DRIFT_THRESHOLD", "0.75"))


async def detect_drift(run_id: str, snapshots: list[Snapshot]) -> DriftReport:
    """
    Walk the snapshot sequence and compare consecutive agent_message outputs
    against the next agent_start's input context.
    """
    edges_analyzed = 0
    flagged: list[DriftEdge] = []

    # Build a simple list of (output_snap, input_snap) pairs
    handoffs = _extract_handoffs(snapshots)

    # Get or lazily initialize embedder
    embedder = _get_embedder()

    for from_snap, to_snap in handoffs:
        edges_analyzed += 1
        from_text = _snap_to_text(from_snap)
        to_text = _snap_to_text(to_snap)

        if embedder is not None:
            score = _cosine_similarity(
                embedder.encode(from_text),
                embedder.encode(to_text),
            )
        else:
            # No embedder available — use a simple overlap heuristic
            score = _token_overlap(from_text, to_text)

        flagged_flag = score < _DRIFT_THRESHOLD
        edge = DriftEdge(
            from_node_id=from_snap.node_id,
            to_node_id=to_snap.node_id,
            from_snapshot_id=from_snap.id,
            to_snapshot_id=to_snap.id,
            expected_schema=None,
            actual_content_summary=to_text[:200],
            similarity_score=round(score, 4),
            flagged=flagged_flag,
            flag_reason=(
                f"Semantic similarity {score:.2f} below threshold {_DRIFT_THRESHOLD}"
                if flagged_flag
                else None
            ),
        )
        if flagged_flag:
            flagged.append(edge)

    total = edges_analyzed or 1
    unflagged = edges_analyzed - len(flagged)
    health = unflagged / total if total > 0 else 1.0

    return DriftReport(
        run_id=run_id,
        edges_analyzed=edges_analyzed,
        flagged_edges=flagged,
        overall_health_score=round(health, 4),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_handoffs(snapshots: list[Snapshot]) -> list[tuple[Snapshot, Snapshot]]:
    """Find consecutive pairs where one node ends and another begins."""
    pairs = []
    output_types = {NodeType.AGENT_MESSAGE, NodeType.LLM_CALL}
    input_types = {NodeType.AGENT_START, NodeType.LLM_CALL}

    last_output: Snapshot | None = None
    for snap in snapshots:
        if snap.node_type in output_types and snap.messages_out:
            last_output = snap
        elif snap.node_type in input_types and last_output is not None:
            if snap.node_id != last_output.node_id:
                pairs.append((last_output, snap))
                last_output = None
    return pairs


def _snap_to_text(snap: Snapshot) -> str:
    parts = []
    for msg in snap.messages_out or snap.messages_in or []:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        parts.append(content)
    return " ".join(parts)[:1000]


_embedder = None
_embedder_tried = False


def _get_embedder():
    global _embedder, _embedder_tried
    if _embedder_tried:
        return _embedder
    _embedder_tried = True
    try:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        _embedder = None
    return _embedder


def _cosine_similarity(a, b) -> float:
    import numpy as np
    a = np.array(a, dtype=float)
    b = np.array(b, dtype=float)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 1.0
    return float(np.dot(a, b) / denom)


def _token_overlap(a: str, b: str) -> float:
    """Simple Jaccard similarity as fallback when no embedder is available."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a and not tokens_b:
        return 1.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0
