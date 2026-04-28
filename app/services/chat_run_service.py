"""Service layer for chat-run lifecycle and minimal shell metadata."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.log_config import get_logger
from app.models.chat_run import ChatRun
from app.models.conversation import Conversation
from app.models.enums import RunStatus
from app.repositories.conversation_repo import ConversationRepository

logger = get_logger(__name__)
ACTIVE_RUN_STATUSES = {RunStatus.PENDING, RunStatus.RUNNING}


def build_client_message_shell_state(client_message_id: str | None) -> dict[str, Any]:
    if client_message_id is None:
        return {}
    normalized = str(client_message_id).strip()
    if not normalized:
        return {}
    return {"client_message_id": normalized}


def get_run_client_message_id(run: ChatRun) -> str | None:
    state_json = run.shell_state_json if isinstance(run.shell_state_json, dict) else {}
    value = state_json.get("client_message_id")
    return value if isinstance(value, str) and value.strip() else None


class ChatRunService:
    """Manage chat-run rows while keeping runtime truth inside LangGraph checkpoints."""

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.conversation_repo = ConversationRepository(db_session)

    async def create_run(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        query: str,
        client_message_id: str | None = None,
    ) -> ChatRun:
        await self.ensure_conversation_access(conversation_id=conversation_id, user_id=user_id)
        await self._lock_conversation(conversation_id)
        await self.ensure_no_active_run_conflict(
            conversation_id=conversation_id,
            requested_action="create",
            user_id=user_id,
        )

        run_id = uuid.uuid4()
        run = ChatRun(
            id=run_id,
            conversation_id=conversation_id,
            user_id=user_id,
            query=query,
            status=RunStatus.PENDING,
            shell_state_json=build_client_message_shell_state(client_message_id),
        )
        self.db_session.add(run)
        await self.db_session.flush()
        await self.db_session.refresh(run)
        logger.info(
            "created chat run",
            run_id=str(run.id),
            conversation_id=str(conversation_id),
            user_id=str(user_id),
        )
        return run

    async def ensure_conversation_access(self, conversation_id: uuid.UUID, user_id: uuid.UUID) -> None:
        conversation = await self.conversation_repo.get_by_user_and_id(
            user_id=user_id,
            conversation_id=conversation_id,
        )
        if conversation:
            return

        existing = await self.conversation_repo.get_by_id(conversation_id)
        if existing and existing.user_id != user_id:
            raise PermissionDeniedError(message="您无权访问此会话")
        raise NotFoundError(error_code="CONVERSATION_NOT_FOUND", message="会话不存在")

    async def _lock_conversation(self, conversation_id: uuid.UUID) -> None:
        await self.db_session.execute(
            select(Conversation.id).where(Conversation.id == conversation_id).with_for_update()
        )

    async def get_active_run_for_conversation(
        self,
        *,
        conversation_id: uuid.UUID,
        exclude_run_id: uuid.UUID | None = None,
    ) -> ChatRun | None:
        stmt = (
            select(ChatRun)
            .where(
                ChatRun.conversation_id == conversation_id,
                ChatRun.status.in_(tuple(item.value for item in ACTIVE_RUN_STATUSES)),
            )
            .order_by(ChatRun.created_at.desc())
        )
        if exclude_run_id is not None:
            stmt = stmt.where(ChatRun.id != exclude_run_id)
        result = await self.db_session.execute(stmt)
        return result.scalars().first()

    async def ensure_no_active_run_conflict(
        self,
        *,
        conversation_id: uuid.UUID,
        requested_action: str,
        requested_run_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        exclude_run_id: uuid.UUID | None = None,
    ) -> None:
        active_run = await self.get_active_run_for_conversation(
            conversation_id=conversation_id,
            exclude_run_id=exclude_run_id,
        )
        if active_run is None:
            return
        if user_id is not None and active_run.user_id != user_id:
            return
        raise ConflictError(
            error_code="CONVERSATION_RUN_CONFLICT",
            message="another run already owns this conversation thread",
            details={
                "conversation_id": str(conversation_id),
                "active_run_id": str(active_run.id),
                "requested_run_id": str(requested_run_id) if requested_run_id else None,
                "requested_action": requested_action,
            },
        )

    async def ensure_run_is_active_owner(
        self,
        *,
        run: ChatRun,
        requested_action: str,
    ) -> None:
        await self.ensure_no_active_run_conflict(
            conversation_id=run.conversation_id,
            requested_action=requested_action,
            requested_run_id=run.id,
            user_id=run.user_id,
            exclude_run_id=run.id,
        )

    async def get_run(self, run_id: uuid.UUID, user_id: uuid.UUID) -> ChatRun:
        stmt = select(ChatRun).where(
            ChatRun.id == run_id,
            ChatRun.user_id == user_id,
        ).execution_options(populate_existing=True)
        result = await self.db_session.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"Chat run {run_id} not found or access denied")
        return run

    async def get_run_for_conversation(
        self,
        run_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> ChatRun:
        run = await self.get_run(run_id=run_id, user_id=user_id)
        if run.conversation_id != conversation_id:
            raise ValueError(f"Chat run {run_id} not found in conversation {conversation_id}")
        return run

    async def update_run_status(
        self,
        run_id: uuid.UUID,
        status: RunStatus | str,
        error_message: str | None = None,
    ) -> None:
        stmt = select(ChatRun).where(ChatRun.id == run_id)
        result = await self.db_session.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"Chat run {run_id} not found")

        status_enum = status if isinstance(status, RunStatus) else RunStatus(str(status))
        run.status = status_enum
        run.error_message = error_message
        await self.db_session.flush()

    async def update_run_shell_state(
        self,
        run_id: uuid.UUID,
        *,
        pending_resume_value: dict[str, Any] | None = None,
        clear_pending_resume: bool = False,
    ) -> None:
        stmt = select(ChatRun).where(ChatRun.id == run_id)
        result = await self.db_session.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"Chat run {run_id} not found")

        state_json = dict(run.shell_state_json or {})
        if clear_pending_resume:
            state_json.pop("pending_resume_value", None)
        elif pending_resume_value is not None:
            state_json["pending_resume_value"] = pending_resume_value
        run.shell_state_json = state_json
        await self.db_session.flush()

    async def queue_resume_input(self, run_id: uuid.UUID, *, response: dict[str, Any]) -> None:
        await self.update_run_shell_state(run_id, pending_resume_value=response)

    @staticmethod
    def consume_pending_resume_value(run: ChatRun) -> dict[str, Any] | None:
        state_json = run.shell_state_json if isinstance(run.shell_state_json, dict) else {}
        raw_value = state_json.get("pending_resume_value")
        return dict(raw_value) if isinstance(raw_value, dict) else None

    async def interrupt_run(self, run_id: uuid.UUID, user_id: uuid.UUID) -> None:
        run = await self.get_run(run_id, user_id)
        if run.status not in (RunStatus.PENDING, RunStatus.RUNNING):
            raise ValueError(f"Cannot interrupt run with status: {run.status}")
        run.status = RunStatus.INTERRUPTED
        await self.db_session.flush()

    async def retry_run(
        self,
        run_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        client_message_id: str | None = None,
    ) -> ChatRun:
        run = await self.get_run(run_id, user_id)
        if run.status not in (RunStatus.FAILED, RunStatus.INTERRUPTED):
            raise ValueError(f"Cannot retry run with status: {run.status}")
        await self._lock_conversation(run.conversation_id)
        await self.ensure_no_active_run_conflict(
            conversation_id=run.conversation_id,
            requested_action="retry",
            requested_run_id=run.id,
            user_id=run.user_id,
        )

        new_run_id = uuid.uuid4()
        retry_run = ChatRun(
            id=new_run_id,
            conversation_id=run.conversation_id,
            user_id=run.user_id,
            query=run.query,
            status=RunStatus.PENDING,
            parent_run_id=run.id,
            retry_of_run_id=run.id,
            shell_state_json=build_client_message_shell_state(client_message_id),
        )
        self.db_session.add(retry_run)
        await self.db_session.flush()
        await self.db_session.refresh(retry_run)
        return retry_run

    async def regenerate_run(
        self,
        run_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        client_message_id: str | None = None,
    ) -> ChatRun:
        run = await self.get_run(run_id, user_id)
        if run.status != RunStatus.SUCCESS:
            raise ValueError(f"Cannot regenerate run with status: {run.status}")
        await self._lock_conversation(run.conversation_id)
        await self.ensure_no_active_run_conflict(
            conversation_id=run.conversation_id,
            requested_action="regenerate",
            requested_run_id=run.id,
            user_id=run.user_id,
        )

        new_run_id = uuid.uuid4()
        regenerate_run = ChatRun(
            id=new_run_id,
            conversation_id=run.conversation_id,
            user_id=run.user_id,
            query=run.query,
            status=RunStatus.PENDING,
            parent_run_id=run.id,
            retry_of_run_id=None,
            shell_state_json=build_client_message_shell_state(client_message_id),
        )
        self.db_session.add(regenerate_run)
        await self.db_session.flush()
        await self.db_session.refresh(regenerate_run)
        return regenerate_run
