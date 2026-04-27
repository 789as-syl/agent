"""数据模型模块：run_event。"""

import uuid
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RunEvent(Base, TimestampMixin):
    """
    Agent 运行事件存储模型。

    设计目的：
        - 以 append-only 方式持久化一次 run 的关键过程事件。
        - 区分 checkpoint state 与 event transcript playback，便于审计与调试。
        - 作为业务 playback / audit 的事件事实源，而不是运行时真相。
    """

    __tablename__ = "run_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="事件记录主键 UUID",
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_runs.id"),
        nullable=False,
        comment="所属 chat run ID",
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id"),
        nullable=False,
        comment="所属会话 ID",
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        comment="所属用户 ID",
    )

    event_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        comment="SSE 事件唯一 ID",
    )

    event_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="事件类型，如 execution_trace / hitl_requested / final_answer",
    )

    step: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="事件对应的运行步数",
    )

    sequence_no: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        server_default=text("nextval('run_events_sequence_no_seq')"),
        comment="事件存储顺序号，作为 playback/delta 的主排序键",
    )

    is_final: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否为 run 的终态事件",
    )

    event_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="完整 SSEEvent JSON，作为 event transcript playback 的事实源",
    )

    __table_args__ = (
        Index("ix_run_events_run_id", "run_id"),
        Index("ix_run_events_conversation_id", "conversation_id"),
        Index("ix_run_events_user_id", "user_id"),
        Index("ix_run_events_event_id", "event_id", unique=True),
        Index("ix_run_events_sequence_no", "sequence_no", unique=True),
    )

    def __repr__(self) -> str:
        return f"<RunEvent(id={self.id}, run_id={self.run_id}, event_type={self.event_type})>"
