from __future__ import annotations

import pytest

from app.core import schema_guard


@pytest.mark.asyncio
async def test_ensure_database_schema_current_accepts_head_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schema_guard.settings, "database_require_head_revision", True)
    monkeypatch.setattr(schema_guard, "get_alembic_head_revisions", lambda: ("head-1",))

    async def _current() -> str | None:
        return "head-1"

    monkeypatch.setattr(schema_guard, "get_current_database_revision", _current)

    await schema_guard.ensure_database_schema_current()


@pytest.mark.asyncio
async def test_ensure_database_schema_current_raises_for_schema_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schema_guard.settings, "database_require_head_revision", True)
    monkeypatch.setattr(schema_guard, "get_alembic_head_revisions", lambda: ("head-2",))

    async def _current() -> str | None:
        return "head-1"

    monkeypatch.setattr(schema_guard, "get_current_database_revision", _current)

    with pytest.raises(RuntimeError, match="Database schema is out of date"):
        await schema_guard.ensure_database_schema_current()
