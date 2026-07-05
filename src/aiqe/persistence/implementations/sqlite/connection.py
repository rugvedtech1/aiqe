"""
SQLite async connection management for AIQE local/CLI mode.

Uses SQLAlchemy Core with aiosqlite for async SQLite access.
One engine instance per AIQE process — connection pooling
is handled by SQLAlchemy's StaticPool for SQLite.

Why StaticPool for SQLite?
    SQLite does not support concurrent writes from multiple
    connections to the same file. SQLAlchemy's StaticPool
    reuses a single connection, which matches SQLite's
    single-writer model and prevents "database is locked" errors.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from aiqe.shared.logging import get_logger
from aiqe.persistence.models import metadata

logger = get_logger(__name__)

_engine: AsyncEngine | None = None


async def get_sqlite_engine(db_path: Path | str) -> AsyncEngine:
    """
    Get or create the SQLite async engine singleton.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        SQLAlchemy AsyncEngine configured for SQLite.
    """
    global _engine
    if _engine is not None:
        return _engine

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    url = f"sqlite+aiosqlite:///{db_path}"

    _engine = create_async_engine(
        url,
        echo=False,
        poolclass=StaticPool,
        connect_args={
            "check_same_thread": False,
            # Enable WAL mode for better concurrent read performance
            # even with SQLite's single-writer limitation
        },
    )

    logger.info(
        "sqlite_engine_created",
        db_path=str(db_path),
    )

    return _engine


async def create_tables(engine: AsyncEngine) -> None:
    """
    Create all AIQE tables if they do not exist.

    Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS.
    Called at application startup before any repository operations.

    Args:
        engine: The SQLAlchemy async engine.
    """
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    logger.info("sqlite_tables_created_or_verified")


async def dispose_engine() -> None:
    """
    Dispose the engine and close all connections.

    Called at application shutdown.
    """
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("sqlite_engine_disposed")
