"""Async database engine and session helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from threading import Lock

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

async_engine: AsyncEngine | None = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None
_init_lock: Lock | None = None


def _get_init_lock() -> Lock:
    """Return the process-local initialization lock."""
    global _init_lock
    if _init_lock is None:
        _init_lock = Lock()
    return _init_lock


def init_db_engine() -> None:
    """Initialize the shared async engine and session factory exactly once."""
    global async_engine, async_session_factory

    if async_engine is not None and async_session_factory is not None:
        return

    with _get_init_lock():
        if async_engine is not None and async_session_factory is not None:
            return

        async_engine = create_async_engine(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=settings.debug,
        )
        async_session_factory = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )


def get_async_engine() -> AsyncEngine:
    """Return the shared async engine, initializing it on first use."""
    if async_engine is None:
        init_db_engine()
    assert async_engine is not None
    return async_engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared async session factory, initializing it on first use."""
    if async_session_factory is None:
        init_db_engine()
    assert async_session_factory is not None
    return async_session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides one transactional async session per request."""
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db() -> None:
    """Dispose the shared engine and reset exported globals."""
    global async_engine, async_session_factory

    if async_engine is None:
        return

    await async_engine.dispose()
    async_engine = None
    async_session_factory = None


@asynccontextmanager
async def get_celery_session() -> AsyncIterator[AsyncSession]:
    """Yield an independent async session for Celery workers."""
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
