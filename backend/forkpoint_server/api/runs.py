"""
/api/v1/runs — CRUD for agent runs.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forkpoint_server.db.database import get_db
from forkpoint_server.db.models import ForkModel, RunModel, SnapshotModel
from forkpoint_server.ws import manager as ws_manager

# We import the Pydantic models from the SDK package (shared source of truth)
# In a deployed setup these come from the installed `forkpoint` package.
# For development they live in ../../../sdk/
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../sdk"))

from forkpoint.models.events import Fork, ReplayBundle, Run, RunStatus, Snapshot, StatePatch

router = APIRouter(prefix="/runs", tags=["runs"])


# ---------------------------------------------------------------------------
# List runs
# ---------------------------------------------------------------------------


@router.get("/", response_model=list[dict])
async def list_runs(
    agent_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(RunModel).order_by(RunModel.started_at.desc()).offset(offset).limit(limit)
    if agent_id:
        stmt = stmt.where(RunModel.agent_id == agent_id)
    if status:
        stmt = stmt.where(RunModel.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return [_run_model_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Get single run
# ---------------------------------------------------------------------------


@router.get("/{run_id}", response_model=dict)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await _get_run_or_404(run_id, db)
    return _run_model_to_dict(run)


# ---------------------------------------------------------------------------
# Get replay bundle
# ---------------------------------------------------------------------------


@router.get("/{run_id}/replay-bundle")
async def get_replay_bundle(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await _get_run_or_404(run_id, db)

    snap_rows = (
        await db.execute(
            select(SnapshotModel)
            .where(SnapshotModel.run_id == run_id)
            .order_by(SnapshotModel.sequence_number)
        )
    ).scalars().all()

    fork_rows = (
        await db.execute(select(ForkModel).where(ForkModel.source_run_id == run_id))
    ).scalars().all()

    run_obj = Run.model_validate(json.loads(_run_model_to_json(run)))
    snapshots = [Snapshot.model_validate_json(s.data) for s in snap_rows]
    forks = [Fork.model_validate_json(f.data) for f in fork_rows] if fork_rows else []

    bundle = ReplayBundle(run=run_obj, snapshots=snapshots, forks=forks)
    return bundle.model_dump()


# ---------------------------------------------------------------------------
# Fork a run
# ---------------------------------------------------------------------------


class ForkRequest(BaseModel):
    snapshot_id: str
    patch: dict | None = None
    reason: str | None = None


@router.post("/{run_id}/fork", response_model=dict)
async def fork_run(run_id: str, body: ForkRequest, db: AsyncSession = Depends(get_db)):
    await _get_run_or_404(run_id, db)

    # Build the new run
    from forkpoint.models.events import Framework
    import hashlib, datetime, timezone

    source_snap_row = await db.get(SnapshotModel, body.snapshot_id)
    if source_snap_row is None or source_snap_row.run_id != run_id:
        raise HTTPException(404, "Snapshot not found in this run")

    source_snap = Snapshot.model_validate_json(source_snap_row.data)
    patch = StatePatch.model_validate(body.patch) if body.patch else None

    # Create forked run record
    forked_run = Run.create(
        agent_id=f"fork-of-{run_id[:8]}",
        framework=Framework.RAW,
        parent_run_id=run_id,
        fork_point_snapshot_id=body.snapshot_id,
    )
    forked_run.status = RunStatus.REPLAYING

    fork_record = Fork.create(
        source_run_id=run_id,
        source_snapshot_id=body.snapshot_id,
        forked_run_id=forked_run.id,
        patch=patch,
        reason=body.reason,
    )

    db.add(RunModel(
        id=forked_run.id,
        agent_id=forked_run.agent_id,
        parent_run_id=run_id,
        fork_point_snapshot_id=body.snapshot_id,
        framework=forked_run.framework.value,
        status=forked_run.status.value,
        started_at=forked_run.started_at,
        tags=json.dumps(forked_run.tags),
        metadata_=json.dumps(forked_run.metadata),
    ))
    db.add(ForkModel(
        id=fork_record.id,
        source_run_id=run_id,
        source_snapshot_id=body.snapshot_id,
        forked_run_id=forked_run.id,
        patch=patch.model_dump_json() if patch else None,
        reason=body.reason,
    ))
    await db.commit()

    # Notify live clients
    await ws_manager.broadcast_run(run_id, {
        "type": "fork_created",
        "data": fork_record.model_dump(),
    })

    return {"fork": fork_record.model_dump(), "forked_run": forked_run.model_dump()}


# ---------------------------------------------------------------------------
# Delete run
# ---------------------------------------------------------------------------


@router.delete("/{run_id}", status_code=204)
async def delete_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await _get_run_or_404(run_id, db)
    # Cascade-delete snapshots
    snap_rows = (
        await db.execute(select(SnapshotModel).where(SnapshotModel.run_id == run_id))
    ).scalars().all()
    for s in snap_rows:
        await db.delete(s)
    await db.delete(run)
    await db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_run_or_404(run_id: str, db: AsyncSession) -> RunModel:
    run = await db.get(RunModel, run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id!r} not found")
    return run


def _run_model_to_dict(r: RunModel) -> dict:
    return {
        "id": r.id,
        "agent_id": r.agent_id,
        "parent_run_id": r.parent_run_id,
        "fork_point_snapshot_id": r.fork_point_snapshot_id,
        "framework": r.framework,
        "status": r.status,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "ended_at": r.ended_at.isoformat() if r.ended_at else None,
        "tags": json.loads(r.tags or "{}"),
        "metadata": json.loads(r.metadata_ or "{}"),
        "error": json.loads(r.error) if r.error else None,
        "root_snapshot_id": r.root_snapshot_id,
        "terminal_snapshot_id": r.terminal_snapshot_id,
    }


def _run_model_to_json(r: RunModel) -> str:
    return json.dumps(_run_model_to_dict(r))
