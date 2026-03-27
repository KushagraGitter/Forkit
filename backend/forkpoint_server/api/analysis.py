"""
/api/v1/analysis — causal analysis (Layer 3), semantic drift (Layer 4), test generation (Layer 5).
"""

from __future__ import annotations

import hashlib
import json
import sys
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forkpoint_server.db.database import get_db
from forkpoint_server.db.models import (
    CausalAnalysisModel,
    DriftReportModel,
    GeneratedTestModel,
    SnapshotModel,
)
from forkpoint_server.services.causal import analyze_causal
from forkpoint_server.services.drift import detect_drift
from forkpoint_server.services.testgen import generate_test_case

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../sdk"))
from forkpoint.models.events import Snapshot

router = APIRouter(prefix="/analysis", tags=["analysis"])


# ---------------------------------------------------------------------------
# Causal analysis (Layer 3)
# ---------------------------------------------------------------------------


@router.post("/causal/{snapshot_id}", status_code=202)
async def trigger_causal(
    snapshot_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    snap_row = await db.get(SnapshotModel, snapshot_id)
    if snap_row is None:
        raise HTTPException(404, "Snapshot not found")
    background_tasks.add_task(_run_causal, snapshot_id, snap_row.run_id, snap_row.data)
    return {"status": "queued", "snapshot_id": snapshot_id}


@router.get("/causal/{snapshot_id}")
async def get_causal(snapshot_id: str, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            select(CausalAnalysisModel).where(CausalAnalysisModel.snapshot_id == snapshot_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Causal analysis not yet available")
    return json.loads(row.data)


# ---------------------------------------------------------------------------
# Semantic drift detection (Layer 4)
# ---------------------------------------------------------------------------


@router.post("/drift/{run_id}", status_code=202)
async def trigger_drift(
    run_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    snap_rows = (
        await db.execute(
            select(SnapshotModel)
            .where(SnapshotModel.run_id == run_id)
            .order_by(SnapshotModel.sequence_number)
        )
    ).scalars().all()
    if not snap_rows:
        raise HTTPException(404, "No snapshots for this run")
    snapshots_json = [s.data for s in snap_rows]
    background_tasks.add_task(_run_drift, run_id, snapshots_json)
    return {"status": "queued", "run_id": run_id}


@router.get("/drift/{run_id}")
async def get_drift(run_id: str, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            select(DriftReportModel).where(DriftReportModel.run_id == run_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Drift report not yet available")
    return json.loads(row.data)


# ---------------------------------------------------------------------------
# Test case generation (Layer 5)
# ---------------------------------------------------------------------------


@router.post("/testgen/{run_id}", status_code=202)
async def trigger_testgen(
    run_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    snap_rows = (
        await db.execute(
            select(SnapshotModel)
            .where(SnapshotModel.run_id == run_id)
            .order_by(SnapshotModel.sequence_number)
        )
    ).scalars().all()
    if not snap_rows:
        raise HTTPException(404, "No snapshots for this run")
    snapshots_json = [s.data for s in snap_rows]
    background_tasks.add_task(_run_testgen, run_id, snapshots_json)
    return {"status": "queued", "run_id": run_id}


@router.get("/testgen/{run_id}")
async def get_testgen(run_id: str, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            select(GeneratedTestModel).where(GeneratedTestModel.run_id == run_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Test case not yet generated")
    return json.loads(row.data)


# ---------------------------------------------------------------------------
# Background task runners (write results back to DB)
# ---------------------------------------------------------------------------


async def _run_causal(snapshot_id: str, run_id: str, snapshot_json: str) -> None:
    snap = Snapshot.model_validate_json(snapshot_json)
    result = await analyze_causal(snap)
    async with __import__("forkpoint_server.db.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as db:
        row_id = hashlib.sha256(snapshot_id.encode()).hexdigest()[:16]
        db.add(CausalAnalysisModel(id=row_id, snapshot_id=snapshot_id, run_id=run_id, data=result.model_dump_json()))
        await db.commit()


async def _run_drift(run_id: str, snapshots_json: list[str]) -> None:
    snapshots = [Snapshot.model_validate_json(s) for s in snapshots_json]
    report = await detect_drift(run_id, snapshots)
    async with __import__("forkpoint_server.db.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as db:
        row_id = hashlib.sha256(run_id.encode()).hexdigest()[:16]
        db.add(DriftReportModel(id=row_id, run_id=run_id, data=report.model_dump_json()))
        await db.commit()


async def _run_testgen(run_id: str, snapshots_json: list[str]) -> None:
    snapshots = [Snapshot.model_validate_json(s) for s in snapshots_json]
    test_case = await generate_test_case(run_id, snapshots)
    async with __import__("forkpoint_server.db.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as db:
        row_id = hashlib.sha256(run_id.encode()).hexdigest()[:16]
        db.add(GeneratedTestModel(id=row_id, run_id=run_id, data=test_case.model_dump_json()))
        await db.commit()
