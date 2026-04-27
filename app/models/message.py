"""数据模型模块：message。"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Message(Base):
    """
    消息模型（仅追加，不允许更新）。

    设计原则：
        - 一条消息属于一个会话（conversation）。
        - 消息一旦创建即不可修改，保证对话历史的完整性与审计可追溯性。
        - 使用 JSONB 存储扩展元数据（如引用来源、模型参数等）。
    """

    __tablename__ = "messages"

    # ----- 主键：UUID 唯一标识 -----
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="消息唯一标识 UUID"
    )

    # ----- 所属会话 ID（外键关联到 conversations 表）-----
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id"),
        nullable=False,
        comment="所属会话 ID，关联 conversations 表"
    )

    # ----- 消息角色 -----
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="消息发送者角色：user（用户）、assistant（助手）、system（系统）"
    )

    # ----- 消息内容 -----
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="消息正文内容，支持长文本"
    )

    # ----- 扩展元数据（JSONB 格式）-----
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="扩展元数据，如引用来源、模型参数、token 消耗等"
    )

    content_blocks_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="标准 content blocks 存储，用于保留结构化输出内容"
    )

    # ----- 创建时间（由数据库自动填充）-----
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="NOW()",   # 数据库函数自动生成当前时间戳
        comment="消息创建时间（UTC）"
    )

    # ----- 表级索引：加速按会话查询消息 -----
    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
    )

    def __repr__(self) -> str:
        """对象的字符串表示，便于调试。"""
        return f"<Message(id={self.id}, conversation_id={self.conversation_id}, role={self.role})>"
