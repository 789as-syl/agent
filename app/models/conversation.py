"""数据模型模块：conversation。"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Conversation(Base, TimestampMixin):
    """
    会话模型，支持软删除。

    继承关系：
        - Base：提供 SQLAlchemy 声明式映射能力。
        - TimestampMixin：自动添加 created_at 和 updated_at 审计字段。

    设计要点：
        - 每个会话属于一个用户（多租户隔离）。
        - 支持软删除（is_deleted），保留历史数据但逻辑上不可见。
    """

    __tablename__ = "conversations"

    # ----- 主键：UUID 唯一标识 -----
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="会话唯一标识 UUID"
    )

    # ----- 所属用户 ID（外键关联到 users 表）-----
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        comment="拥有该会话的用户 ID"
    )

    # ----- 会话标题（可自定义或自动生成）-----
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="New Conversation",
        comment="会话标题，默认值为 'New Conversation'"
    )

    # ----- 软删除标记 -----
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="软删除标记：True 表示已删除，查询时应过滤"
    )

    # ----- 表级索引（加速常用查询）-----
    __table_args__ = (
        Index("ix_conversations_user_id", "user_id"),          # 按用户查询会话列表
        Index("ix_conversations_is_deleted", "is_deleted"),    # 过滤已删除记录
    )

    def __repr__(self) -> str:
        """对象的字符串表示，便于调试。"""
        return f"<Conversation(id={self.id}, user_id={self.user_id}, title={self.title})>"
