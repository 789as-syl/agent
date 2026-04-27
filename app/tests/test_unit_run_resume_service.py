from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.chat_run import ChatRun
from app.models.enums import RunStatus
from app.services.run_resume_service import RunResumeService


@pytest.mark.asyncio
async def test_run_resume_service_marks_legacy_checkpoint_tombstone_when_detected(monkeypatch):
    service = RunResumeService()
    run = ChatRun(
        id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        query="hello",
        status=RunStatus.INTERRUPTED,
        shell_state_json={},
    )

    async def _none(*args, **kwargs):
        return None

    async def _legacy(*args, **kwargs):
        return object()

    monkeypatch.setattr("app.services.run_resume_service.get_checkpoint_tuple", _none)
    monkeypatch.setattr("app.services.run_resume_service.get_legacy_run_checkpoint", _legacy)

    snapshot = await service.build_resume_snapshot(run)

    assert snapshot.resume_supported is False
    assert snapshot.legacy_checkpoint_detected is True
    assert snapshot.reason == "thread_key_migrated"


@pytest.mark.asyncio
async def test_run_resume_service_marks_missing_checkpoint_after_migration(monkeypatch):
    service = RunResumeService()
    run = ChatRun(
        id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        query="hello",
        status=RunStatus.INTERRUPTED,
        shell_state_json={},
    )

    async def _none(*args, **kwargs):
        return None

    monkeypatch.setattr("app.services.run_resume_service.get_checkpoint_tuple", _none)
    monkeypatch.setattr("app.services.run_resume_service.get_legacy_run_checkpoint", _none)

    snapshot = await service.build_resume_snapshot(run)

    assert snapshot.resume_supported is False
    assert snapshot.legacy_checkpoint_detected is False
    assert snapshot.reason == "checkpoint_missing_after_migration"
