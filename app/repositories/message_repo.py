"""仓储模块：message_repo。"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


class MessageRepository:
    """Data access wrapper for append-only message records."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, message_id: UUID) -> Message | None:
        """Return one message by primary key, or ``None`` when missing."""
        result = await self.session.execute(
            select(Message).where(Message.id == message_id)
        )
        return result.scalar_one_or_none()

    async def list_by_conversation(
        self,
        conversation_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Message], int]:
        """Return paginated conversation messages plus the total row count."""
        stmt = (
            select(Message, func.count().over().label("total_count"))
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        if not rows:
            return [], 0

        messages = [row.Message for row in rows]
        total = rows[0].total_count

        return messages, total

    async def list_recent_by_conversation(
        self,
        conversation_id: UUID,
        limit: int,
    ) -> list[Message]:
        """Return latest messages in ascending order by created time."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        messages = list(result.scalars().all())
        messages.reverse()
        return messages

    async def list_all_by_conversation(self, conversation_id: UUID) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_after_message(
        self,
        conversation_id: UUID,
        message_id: UUID,
    ) -> list[Message]:
        """Return messages created after the given message within one conversation."""

        anchor_message = await self.get_by_id(message_id)
        if not anchor_message or anchor_message.conversation_id != conversation_id:
            return await self.list_all_by_conversation(conversation_id)

        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .where(
                or_(
                    Message.created_at > anchor_message.created_at,
                    and_(
                        Message.created_at == anchor_message.created_at,
                        Message.id > anchor_message.id,
                    ),
                )
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_metadata_field(
        self,
        key: str,
        value: str,
        conversation_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Message]:
        """Return messages filtered by one JSONB metadata field."""
        condition = Message.metadata_json[key].astext == value

        stmt = select(Message).where(condition)

        if conversation_id is not None:
            stmt = stmt.where(Message.conversation_id == conversation_id)

        stmt = stmt.order_by(Message.created_at.asc()).offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        metadata: dict | None = None,
        content_blocks: list[dict] | None = None,
    ) -> Message:
        """Create and flush one append-only message row."""
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata_json=metadata or {},
            content_blocks_json=content_blocks,
            created_at=datetime.now(UTC),
        )

        self.session.add(message)
        await self.session.flush()
        await self.session.refresh(message)
        return message
