from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.runtime.native_checkpoint import (
    CheckpointRuntimeCompatibilityError,
    is_psycopg_async_runtime_compatible,
)
from app.main import app, lifespan


def test_psycopg_async_runtime_detects_windows_proactor_incompatibility(monkeypatch: pytest.MonkeyPatch) -> None:
    ProactorEventLoop = type("ProactorEventLoop", (), {})
    proactor_loop = ProactorEventLoop()

    monkeypatch.setattr("app.agents.runtime.native_checkpoint.sys.platform", "win32")
    monkeypatch.setattr("app.agents.runtime.native_checkpoint.asyncio.get_running_loop", lambda: proactor_loop)

    assert is_psycopg_async_runtime_compatible() is False


@pytest.mark.asyncio
async def test_lifespan_continues_when_checkpoint_runtime_is_incompatible() -> None:
    fake_dashscope = SimpleNamespace(api_key="")

    with (
        patch("app.main.setup_logging"),
        patch("app.models.init_db", AsyncMock()),
        patch("app.core.schema_guard.ensure_database_schema_current", AsyncMock()),
        patch("app.core.redis.init_redis", AsyncMock()),
        patch("app.core.minio.init_minio", AsyncMock()),
        patch("app.core.langsmith.configure_langsmith", return_value=False),
        patch(
            "app.services.document_processing.get_document_runtime_readiness",
            return_value={"missing_types": [], "docling_runtime_ready": True, "docling_pdf_runtime_ready": True},
        ),
        patch("app.main.is_docling_runtime_available", return_value=True),
        patch("app.main.is_docling_pdf_runtime_available", return_value=True),
        patch(
            "app.agents.runtime.native_checkpoint.get_native_checkpointer",
            AsyncMock(side_effect=CheckpointRuntimeCompatibilityError("loop mismatch")),
        ),
        patch("app.agents.runtime.native_checkpoint.close_native_checkpointer", AsyncMock()),
        patch("app.core.redis.close_redis", AsyncMock()),
        patch("app.models.close_db", AsyncMock()),
        patch("app.main.logger.warning") as mock_warning,
        patch.dict("sys.modules", {"dashscope": fake_dashscope}),
    ):
        async with lifespan(app):
            pass

    mock_warning.assert_any_call(
        "Native LangGraph checkpointer disabled for this runtime",
        error="loop mismatch",
    )
