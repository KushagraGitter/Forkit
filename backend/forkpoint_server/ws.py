"""
WebSocket hub — live streaming of run events to connected clients.

WS /ws/runs/{run_id}  — subscribe to live events for one run.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Tracks all active WebSocket connections, keyed by run_id."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, run_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[run_id].append(ws)

    def disconnect(self, run_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(run_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast_run(self, run_id: str, message: dict[str, Any]) -> None:
        """Send a message to all clients watching this run."""
        dead = []
        for ws in list(self._connections.get(run_id, [])):
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(run_id, ws)

    async def broadcast_all(self, message: dict[str, Any]) -> None:
        """Send a message to all connected clients (e.g. new run created)."""
        all_ws = [ws for conns in self._connections.values() for ws in conns]
        dead = []
        for ws in all_ws:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(ws)


manager = ConnectionManager()


@router.websocket("/ws/runs/{run_id}")
async def websocket_run(ws: WebSocket, run_id: str) -> None:
    await manager.connect(run_id, ws)
    try:
        # Send a connection-established message
        await ws.send_text(json.dumps({
            "type": "connected",
            "data": {"run_id": run_id},
        }))
        # Keep alive — client messages are ping/pong only
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(run_id, ws)
