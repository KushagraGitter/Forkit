"""
Forkpoint server — FastAPI entry point.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from forkpoint_server.db.database import init_db
from forkpoint_server.api import runs, snapshots, ingest, diff, analysis
from forkpoint_server.ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Forkpoint",
    description="Runtime debugger for multi-agent AI systems — treat agent runs like git commits.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the frontend dev server
_CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routes
app.include_router(runs.router, prefix="/api/v1")
app.include_router(snapshots.router, prefix="/api/v1")
app.include_router(ingest.router, prefix="/api/v1")
app.include_router(diff.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")

# WebSocket
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "forkpoint"}
