"""
Run diff computation (Layer 2).

Aligns snapshots from two runs by node_id + sequence heuristic,
then computes field-level diffs for modified pairs.
"""

from __future__ import annotations

import json
import sys
import os
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../sdk"))
from forkpoint.models.events import (
    DiffSummary,
    FieldDiff,
    MatchType,
    RunDiff,
    Snapshot,
    SnapshotPair,
)


def compute_run_diff(
    run_a_id: str,
    run_b_id: str,
    snaps_a: list[Snapshot],
    snaps_b: list[Snapshot],
) -> RunDiff:
    """
    Align snapshots by node_id (stable across forks) and produce a RunDiff.
    Uses a greedy alignment: match A[i] to the first unmatched B[j] with the same node_id.
    """
    pairs: list[SnapshotPair] = []

    # Index B by node_id for O(n) alignment
    b_by_node: dict[str, list[Snapshot]] = {}
    for s in snaps_b:
        b_by_node.setdefault(s.node_id, []).append(s)
    b_used: set[str] = set()

    first_divergence: int | None = None

    for a in snaps_a:
        candidates = [s for s in b_by_node.get(a.node_id, []) if s.id not in b_used]
        if not candidates:
            pairs.append(SnapshotPair(
                snapshot_a_id=a.id,
                snapshot_b_id=None,
                node_id=a.node_id,
                match_type=MatchType.REMOVED,
            ))
            continue

        b = candidates[0]
        b_used.add(b.id)

        if a.id == b.id:
            pairs.append(SnapshotPair(
                snapshot_a_id=a.id,
                snapshot_b_id=b.id,
                node_id=a.node_id,
                match_type=MatchType.IDENTICAL,
            ))
        else:
            field_diffs = _diff_snapshots(a, b)
            match_type = MatchType.MODIFIED if field_diffs else MatchType.IDENTICAL
            if match_type == MatchType.MODIFIED and first_divergence is None:
                first_divergence = a.sequence_number
            pairs.append(SnapshotPair(
                snapshot_a_id=a.id,
                snapshot_b_id=b.id,
                node_id=a.node_id,
                match_type=match_type,
                field_diffs=field_diffs,
            ))

    # B snapshots not matched to any A are "added"
    for b in snaps_b:
        if b.id not in b_used:
            pairs.append(SnapshotPair(
                snapshot_a_id=None,
                snapshot_b_id=b.id,
                node_id=b.node_id,
                match_type=MatchType.ADDED,
            ))

    summary = DiffSummary(
        total_snapshots_a=len(snaps_a),
        total_snapshots_b=len(snaps_b),
        identical=sum(1 for p in pairs if p.match_type == MatchType.IDENTICAL),
        modified=sum(1 for p in pairs if p.match_type == MatchType.MODIFIED),
        added=sum(1 for p in pairs if p.match_type == MatchType.ADDED),
        removed=sum(1 for p in pairs if p.match_type == MatchType.REMOVED),
        first_divergence_sequence=first_divergence,
    )

    return RunDiff(
        run_a_id=run_a_id,
        run_b_id=run_b_id,
        snapshot_pairs=pairs,
        summary=summary,
    )


def _diff_snapshots(a: Snapshot, b: Snapshot) -> list[FieldDiff]:
    """Flat field-by-field comparison of two snapshots."""
    diffs: list[FieldDiff] = []
    fields = ["messages_in", "messages_out", "tool_calls", "tool_results", "agent_state", "model", "model_params"]
    a_dict = a.model_dump()
    b_dict = b.model_dump()
    for field in fields:
        va = a_dict.get(field)
        vb = b_dict.get(field)
        if va != vb:
            diffs.append(FieldDiff(field_path=field, value_a=va, value_b=vb))
    return diffs
