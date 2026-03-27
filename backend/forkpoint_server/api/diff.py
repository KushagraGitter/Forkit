"""
/api/v1/diff — compute run and snapshot diffs.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forkpoint_server.db.database import get_db
from forkpoint_server.db.models import SnapshotModel
from forkpoint_server.services.diff import compute_run_diff

router = APIRouter(prefix="/diff", tags=["diff"])


@router.get("/")
async def diff_runs(
    run_a: str = Query(...),
    run_b: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    snaps_a = (
        await db.execute(
            select(SnapshotModel)
            .where(SnapshotModel.run_id == run_a)
            .order_by(SnapshotModel.sequence_number)
        )
    ).scalars().all()
    snaps_b = (
        await db.execute(
            select(SnapshotModel)
            .where(SnapshotModel.run_id == run_b)
            .order_by(SnapshotModel.sequence_number)
        )
    ).scalars().all()

    if not snaps_a:
        raise HTTPException(404, f"No snapshots for run {run_a!r}")
    if not snaps_b:
        raise HTTPException(404, f"No snapshots for run {run_b!r}")

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../sdk"))
    from forkpoint.models.events import Snapshot as FPSnapshot

    a = [FPSnapshot.model_validate_json(s.data) for s in snaps_a]
    b = [FPSnapshot.model_validate_json(s.data) for s in snaps_b]

    diff = compute_run_diff(run_a, run_b, a, b)
    return diff.model_dump()
