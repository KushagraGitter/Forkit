"""
SQLAlchemy ORM models. Mirrors the Pydantic models in the SDK.
Uses JSONB (PostgreSQL) / JSON (SQLite) for flexible state blobs.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RunModel(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    parent_run_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("runs.id"), nullable=True)
    fork_point_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    framework: Mapped[str] = mapped_column(String(32), default="raw")
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags: Mapped[str] = mapped_column(Text, default="{}")         # JSON
    metadata_: Mapped[str] = mapped_column("metadata", Text, default="{}")  # JSON
    error: Mapped[str | None] = mapped_column(Text, nullable=True)          # JSON
    root_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    terminal_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    snapshots: Mapped[list[SnapshotModel]] = relationship(
        "SnapshotModel", back_populates="run", lazy="noload"
    )
    forks_as_source: Mapped[list[ForkModel]] = relationship(
        "ForkModel", foreign_keys="ForkModel.source_run_id", back_populates="source_run", lazy="noload"
    )

    __table_args__ = (
        Index("ix_runs_agent_status", "agent_id", "status"),
        Index("ix_runs_started_at", "started_at"),
    )


class SnapshotModel(Base):
    __tablename__ = "snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id"), nullable=False)
    parent_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    node_id: Mapped[str] = mapped_column(String(256), nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    # Full snapshot payload stored as JSON
    data: Mapped[str] = mapped_column(Text, nullable=False)  # serialized Snapshot

    run: Mapped[RunModel] = relationship("RunModel", back_populates="snapshots")

    __table_args__ = (
        Index("ix_snapshots_run_seq", "run_id", "sequence_number"),
        Index("ix_snapshots_node", "run_id", "node_id"),
    )


class ForkModel(Base):
    __tablename__ = "forks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id"), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    forked_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    patch: Mapped[str | None] = mapped_column(Text, nullable=True)   # JSON StatePatch
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_run: Mapped[RunModel] = relationship(
        "RunModel", foreign_keys=[source_run_id], back_populates="forks_as_source"
    )

    __table_args__ = (
        Index("ix_forks_source_run", "source_run_id"),
    )


class CausalAnalysisModel(Base):
    __tablename__ = "causal_analyses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)  # serialized CausalAnalysis
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())


class DriftReportModel(Base):
    __tablename__ = "drift_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, unique=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)  # serialized DriftReport
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())


class GeneratedTestModel(Base):
    __tablename__ = "generated_tests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, unique=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)  # serialized GeneratedTestCase
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
