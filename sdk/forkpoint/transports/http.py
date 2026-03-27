"""
HttpTransport — batches events and POSTs them to the Forkpoint backend.
Falls back to in-memory queue if the server is unreachable; flushes on close.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from typing import Any

import httpx

from forkpoint.models.events import Fork, ReplayBundle, Run, Snapshot, SnapshotEvent
from forkpoint.transports.local import LocalTransport


class HttpTransport:
    """
    Ships events to the Forkpoint server over HTTP.
    Uses a background thread to batch and send without blocking the agent.
    Falls back to LocalTransport for ReplayBundle construction.
    """

    def __init__(
        self,
        server_url: str,
        api_key: str | None = None,
        batch_size: int = 20,
        flush_interval_s: float = 2.0,
        timeout_s: float = 10.0,
        local_fallback_path: str | None = None,
    ) -> None:
        self._url = server_url.rstrip("/")
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._batch_size = batch_size
        self._flush_interval = flush_interval_s
        self._client = httpx.Client(timeout=timeout_s, headers=self._headers)
        self._queue: deque[SnapshotEvent] = deque()
        self._lock = threading.Lock()
        self._local = LocalTransport(local_fallback_path)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Transport protocol
    # ------------------------------------------------------------------

    def start_run(self, run: Run) -> None:
        self._local.start_run(run)
        self._post_nowait("/api/v1/ingest/run/start", run.model_dump())

    def end_run(self, run: Run) -> None:
        self._local.end_run(run)
        self._post_nowait("/api/v1/ingest/run/end", run.model_dump())

    def emit_snapshot(self, snapshot: Snapshot) -> None:
        self._local.emit_snapshot(snapshot)
        event = SnapshotEvent(
            event_type="snapshot_created",
            run_id=snapshot.run_id,
            agent_id="",  # filled by server from run
            payload=snapshot.model_dump(),
        )
        with self._lock:
            self._queue.append(event)
        if len(self._queue) >= self._batch_size:
            self._drain()

    def record_fork(self, fork: Fork) -> None:
        self._local.record_fork(fork)
        self._post_nowait("/api/v1/ingest/fork", fork.model_dump())

    def flush(self) -> None:
        self._drain()
        self._stop.set()
        self._thread.join(timeout=5)
        self._client.close()
        self._local.flush()

    def build_replay_bundle(self, run_id: str) -> ReplayBundle:
        return self._local.build_replay_bundle(run_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _flush_loop(self) -> None:
        while not self._stop.wait(self._flush_interval):
            self._drain()

    def _drain(self) -> None:
        with self._lock:
            batch = list(self._queue)
            self._queue.clear()
        if not batch:
            return
        try:
            payload = [e.model_dump() for e in batch]
            self._client.post(f"{self._url}/api/v1/ingest/events", json=payload)
        except Exception:
            # Re-queue on failure (best-effort; already persisted locally)
            with self._lock:
                self._queue.extendleft(reversed(batch))

    def _post_nowait(self, path: str, data: dict) -> None:
        try:
            self._client.post(f"{self._url}{path}", json=data)
        except Exception:
            pass  # local already captured it
