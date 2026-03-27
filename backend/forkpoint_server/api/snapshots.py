"""
/api/v1/snapshots and /api/v1/runs/{run_id}/snapshots
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forkpoint_server.db.database import get_db
from forkpoint_server.db.models import SnapshotModel

router = APIRouter(tags=["snapshots"])


@router.get("/runs/{run_id}/snapshots")
async def list_snapshots(
    run_id: str,
    node_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(SnapshotModel)
        .where(SnapshotModel.run_id == run_id)
        .order_by(SnapshotModel.sequence_number)
    )
    if node_type:
        stmt = stmt.where(SnapshotModel.node_type == node_type)
    rows = (await db.execute(stmt)).scalars().all()
    return [json.loads(r.data) for r in rows]


@router.get("/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(SnapshotModel, snapshot_id)
    if row is None:
        raise HTTPException(404, f"Snapshot {snapshot_id!r} not found")
    return json.loads(row.data)
