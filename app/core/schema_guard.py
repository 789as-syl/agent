"""Database schema drift guards for startup/readiness."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import settings
from app.models.engine import get_async_engine


def get_alembic_head_revisions() -> tuple[str, ...]:
    """Return Alembic head revisions declared in this workspace."""
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    script = ScriptDirectory.from_config(config)
    return tuple(script.get_heads())


async def get_current_database_revision() -> str | None:
    """Return the current database Alembic revision, if available."""
    engine = get_async_engine()
    async with engine.connect() as conn:
        try:
            return cast(str | None, await conn.scalar(text("select version_num from alembic_version")))
        except Exception:
            return None


async def ensure_database_schema_current() -> None:
    """Raise if the connected database schema is behind the current Alembic heads."""
    if not settings.database_require_head_revision:
        return

    current_revision = await get_current_database_revision()
    head_revisions = get_alembic_head_revisions()

    if not head_revisions:
        return

    if current_revision not in head_revisions:
        expected = ", ".join(head_revisions)
        current = current_revision or "<none>"
        raise RuntimeError(
            "Database schema is out of date. "
            f"Current revision: {current}. Expected head: {expected}. "
            "Run `alembic upgrade head` before starting the API."
        )
