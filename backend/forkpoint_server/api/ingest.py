"""
/api/v1/ingest — SDK → backend event ingestion endpoints.
Called by HttpTransport in the SDK.
"""

from __future__ import annotations

import json
import sys
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from forkpoint_server.db.database import get_db
from forkpoint_server.db.models import ForkModel, RunModel, SnapshotModel
from forkpoint_server.ws import manager as ws_manager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../sdk"))
from forkpoint.models.events import Fork, Run, Snapshot, SnapshotEvent

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/run/start", status_code=201)
async def ingest_run_start(run_data: dict, db: AsyncSession = Depends(get_db)):
    run = Run.model_validate(run_data)
    db.add(RunModel(
        id=run.id,
        agent_id=run.agent_id,
        parent_run_id=run.parent_run_id,
        fork_point_snapshot_id=run.fork_point_snapshot_id,
        framework=run.framework.value,
        status=run.status.value,
        started_at=run.started_at,
        tags=json.dumps(run.tags),
        metadata_=json.dumps(run.metadata),
        root_snapshot_id=run.root_snapshot_id,
        terminal_snapshot_id=run.terminal_snapshot_id,
    ))
    await db.commit()
    await ws_manager.broadcast_run(run.id, {
        "type": "run_status_changed",
        "data": {"run_id": run.id, "status": run.status.value},
    })
    return {"run_id": run.id}


@router.post("/run/end")
async def ingest_run_end(run_data: dict, db: AsyncSession = Depends(get_db)):
    run = Run.model_validate(run_data)
    existing = await db.get(RunModel, run.id)
    if existing is None:
        raise HTTPException(404, f"Run {run.id!r} not found")
    existing.status = run.status.value
    existing.ended_at = run.ended_at
    existing.terminal_snapshot_id = run.terminal_snapshot_id
    existing.error = run.error.model_dump_json() if run.error else None
    await db.commit()
    await ws_manager.broadcast_run(run.id, {
        "type": "run_status_changed",
        "data": {"run_id": run.id, "status": run.status.value},
    })
    return {"ok": True}


@router.post("/events", status_code=201)
async def ingest_events(events: list[dict], db: AsyncSession = Depends(get_db)):
    """Batch ingest of SnapshotEvents from the SDK."""
    created = 0
    for raw in events:
        event = SnapshotEvent.model_validate(raw)
        if event.event_type == "snapshot_created":
            snap = Snapshot.model_validate(event.payload)
            existing = await db.get(SnapshotModel, snap.id)
            if existing is None:
                db.add(SnapshotModel(
                    id=snap.id,
                    run_id=snap.run_id,
                    parent_snapshot_id=snap.parent_snapshot_id,
                    sequence_number=snap.sequence_number,
                    node_id=snap.node_id,
                    node_type=snap.node_type.value,
                    timestamp=snap.timestamp,
                    data=snap.model_dump_json(),
                ))
                created += 1
                await ws_manager.broadcast_run(snap.run_id, {
                    "type": "snapshot_created",
                    "data": snap.model_dump(),
                })
    await db.commit()
    return {"created": created}


@router.post("/fork")
async def ingest_fork(fork_data: dict, db: AsyncSession = Depends(get_db)):
    fork = Fork.model_validate(fork_data)
    existing = await db.get(ForkModel, fork.id)
    if existing is None:
        db.add(ForkModel(
            id=fork.id,
            source_run_id=fork.source_run_id,
            source_snapshot_id=fork.source_snapshot_id,
            forked_run_id=fork.forked_run_id,
            patch=fork.patch.model_dump_json() if fork.patch else None,
            reason=fork.reason,
        ))
        await db.commit()
    return {"fork_id": fork.id}
