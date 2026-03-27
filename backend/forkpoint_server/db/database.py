"""
Database session factory. Supports both PostgreSQL (production) and SQLite (dev/test).
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forkpoint_server.db.models import Base

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./forkpoint_dev.db",
)

# Convert postgres:// to postgresql+asyncpg:// if needed
if _DATABASE_URL.startswith("postgres://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif _DATABASE_URL.startswith("postgresql://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

_connect_args = {}
if "sqlite" in _DATABASE_URL:
    _connect_args = {"check_same_thread": False}

engine = create_async_engine(
    _DATABASE_URL,
    connect_args=_connect_args,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create all tables. Called on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI dependency that yields an async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
