"""
LocalTransport — writes to SQLite. Zero-infrastructure mode.

Developers can use this without running any server. When they're ready for the
full UI, they switch to HttpTransport or export a ReplayBundle.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from forkpoint.models.events import Fork, ReplayBundle, Run, RunStatus, Snapshot


_DEFAULT_DB = Path.home() / ".forkpoint" / "local.db"


class LocalTransport:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    # ------------------------------------------------------------------
    # Transport protocol
    # ------------------------------------------------------------------

    def start_run(self, run: Run) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO runs (id, data, status, agent_id, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run.id, run.model_dump_json(), run.status.value, run.agent_id, run.started_at.isoformat()),
        )
        self._conn.commit()

    def end_run(self, run: Run) -> None:
        self._conn.execute(
            "UPDATE runs SET data = ?, status = ?, ended_at = ? WHERE id = ?",
            (
                run.model_dump_json(),
                run.status.value,
                run.ended_at.isoformat() if run.ended_at else None,
                run.id,
            ),
        )
        self._conn.commit()

    def emit_snapshot(self, snapshot: Snapshot) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO snapshots (id, run_id, sequence_number, node_id, node_type, data)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.id,
                snapshot.run_id,
                snapshot.sequence_number,
                snapshot.node_id,
                snapshot.node_type.value,
                snapshot.model_dump_json(),
            ),
        )
        self._conn.commit()

    def record_fork(self, fork: Fork) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO forks (id, source_run_id, forked_run_id, data) VALUES (?, ?, ?, ?)",
            (fork.id, fork.source_run_id, fork.forked_run_id, fork.model_dump_json()),
        )
        self._conn.commit()

    def flush(self) -> None:
        self._conn.commit()

    def build_replay_bundle(self, run_id: str) -> ReplayBundle:
        run_row = self._conn.execute("SELECT data FROM runs WHERE id = ?", (run_id,)).fetchone()
        if run_row is None:
            raise ValueError(f"Run {run_id!r} not found in local storage")
        run = Run.model_validate_json(run_row["data"])

        snap_rows = self._conn.execute(
            "SELECT data FROM snapshots WHERE run_id = ? ORDER BY sequence_number",
            (run_id,),
        ).fetchall()
        snapshots = [Snapshot.model_validate_json(r["data"]) for r in snap_rows]

        fork_rows = self._conn.execute(
            "SELECT data FROM forks WHERE source_run_id = ?", (run_id,)
        ).fetchall()
        forks = [Fork.model_validate_json(r["data"]) for r in fork_rows]

        # Build tool/LLM stubs from recorded snapshots
        tool_stubs: dict[str, list[Any]] = {}
        llm_stubs: dict[str, list[Any]] = {}

        from forkpoint.models.events import LLMStub, ToolStub
        import hashlib

        for snap in snapshots:
            for tc, tr in zip(snap.tool_calls, snap.tool_results):
                stub = ToolStub(
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    result=tr.result,
                    error=tr.error,
                )
                tool_stubs.setdefault(tc.name, []).append(stub)

            if snap.messages_in and snap.messages_out and snap.model:
                msg_hash = hashlib.sha256(
                    snap.model_dump_json(include={"messages_in"}).encode()
                ).hexdigest()
                stub = LLMStub(
                    call_id=snap.id,
                    model=snap.model,
                    messages_hash=msg_hash,
                    response=snap.messages_out[0],
                    logprobs=snap.logprobs,
                    token_counts=snap.token_counts,
                )
                llm_stubs.setdefault(snap.model, []).append(stub)

        return ReplayBundle(
            run=run,
            snapshots=snapshots,
            forks=forks,
            tool_stubs=tool_stubs,
            llm_stubs=llm_stubs,
        )

    # ------------------------------------------------------------------
    # Query helpers (used by CLI / local UI dev)
    # ------------------------------------------------------------------

    def list_runs(self, agent_id: str | None = None, limit: int = 50) -> list[Run]:
        if agent_id:
            rows = self._conn.execute(
                "SELECT data FROM runs WHERE agent_id = ? ORDER BY started_at DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT data FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Run.model_validate_json(r["data"]) for r in rows]

    def get_snapshots(self, run_id: str) -> list[Snapshot]:
        rows = self._conn.execute(
            "SELECT data FROM snapshots WHERE run_id = ? ORDER BY sequence_number",
            (run_id,),
        ).fetchall()
        return [Snapshot.model_validate_json(r["data"]) for r in rows]

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id          TEXT PRIMARY KEY,
                agent_id    TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'running',
                started_at  TEXT,
                ended_at    TEXT,
                data        TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                id              TEXT PRIMARY KEY,
                run_id          TEXT NOT NULL,
                sequence_number INTEGER NOT NULL,
                node_id         TEXT NOT NULL,
                node_type       TEXT NOT NULL,
                data            TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            );
            CREATE INDEX IF NOT EXISTS idx_snapshots_run ON snapshots(run_id, sequence_number);

            CREATE TABLE IF NOT EXISTS forks (
                id              TEXT PRIMARY KEY,
                source_run_id   TEXT NOT NULL,
                forked_run_id   TEXT NOT NULL,
                data            TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_forks_source ON forks(source_run_id);
            """
        )
        self._conn.commit()
