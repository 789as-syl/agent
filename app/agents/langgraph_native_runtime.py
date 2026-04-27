"""Native-only create_agent runtime entrypoint."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.native_agent_factory import create_native_agent_graph


async def build_native_runtime(db_session: AsyncSession) -> Any:
    return await create_native_agent_graph(db_session)


__all__ = ["build_native_runtime"]
