"""数据模型模块：chat_run。"""

import uuid
from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import RunStatus


class ChatRun(Base, TimestampMixin):
    """
    Agent 执行运行记录模型。

    设计目的：
        - 跟踪每次 Agent 执行的生命周期状态（pending、running、success、failed、interrupted）。
        - 存储最小业务壳元数据（shell_state_json），例如待消费的 resume 输入。
        - 记录错误信息，用于监控和调试。

    继承：
        - Base：SQLAlchemy 声明式基类。
        - TimestampMixin：自动添加 created_at 和 updated_at 字段。
    """

    __tablename__ = "chat_runs"

    # ----- 主键：运行记录唯一标识 -----
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="本次运行的唯一标识 UUID"
    )

    # ----- 所属会话（一个会话可以包含多次运行）-----
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id"),
        nullable=False,
        comment="所属会话 ID"
    )

    # ----- 发起用户（便于按用户查询历史运行记录）-----
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        comment="发起本次运行的用户 ID"
    )

    # ----- 原始用户查询 -----
    query: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="用户输入的原始查询文本"
    )

    # ----- 运行状态 -----
    status: Mapped[RunStatus] = mapped_column(
        SAEnum(RunStatus, name="run_status", create_constraint=True, native_enum=True),
        nullable=False,
        default=RunStatus.PENDING,
        comment="运行状态：pending（等待）、running（执行中）、success（成功）、failed（失败）、interrupted（中断）"
    )

    # ----- 最小业务壳元数据（不是运行时事实源）-----
    shell_state_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="仅保留业务壳需要的轻量 JSON 元数据，例如 pending_resume_value"
    )

    # ----- 错误信息（仅在失败时填充）-----
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="运行失败时的详细错误信息"
    )

    # ----- 运行血缘（retry / regenerate 语义）-----
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_runs.id"),
        nullable=True,
        comment="父运行 ID；子运行由哪个 run 派生而来"
    )
    retry_of_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_runs.id"),
        nullable=True,
        comment="若本次运行是 retry 产生，则记录被重试的 run ID"
    )

    # ----- 表级索引（加速常用查询）-----
    __table_args__ = (
        Index("ix_chat_runs_conversation_id", "conversation_id"),  # 按会话查询运行记录
        Index("ix_chat_runs_user_id", "user_id"),                  # 按用户查询
        Index("ix_chat_runs_status", "status"),                    # 按状态筛选（如查找所有中断的任务）
        Index("ix_chat_runs_parent_run_id", "parent_run_id"),      # 按父运行查询血缘
        Index("ix_chat_runs_retry_of_run_id", "retry_of_run_id"),  # 按被重试运行查询血缘
        Index(
            "uq_chat_runs_active_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'RUNNING')"),
        ),
    )

    def __repr__(self) -> str:
        """对象的字符串表示，便于调试。"""
        return f"<ChatRun(id={self.id}, conversation_id={self.conversation_id}, status={self.status})>"
