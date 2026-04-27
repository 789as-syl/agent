"""数据模型模块：question_bank。"""

import enum
import uuid as uuid_module
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class QuestionType(str, enum.Enum):
    """题型枚举"""
    SINGLE = "single"           # 单选题
    MULTIPLE = "multiple"       # 多选题
    TRUE_FALSE = "true_false"   # 判断题
    SHORT_ANSWER = "short_answer"  # 简答题


class QuestionBank(Base, TimestampMixin):
    """
    题库模型。
    """

    __tablename__ = "question_banks"

    # ----- 主键 -----
    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
        comment="题库唯一标识 UUID"
    )

    # ----- 题库名称 -----
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="题库名称"
    )

    # ----- 题库描述（可选）-----
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="题库描述"
    )

    # ----- 关联关系：一个题库包含多道题目 -----
    questions = relationship(
        "Question",
        back_populates="bank",
        lazy="select"   # 按需加载，避免列表查询时自动加载所有题目
    )


class Question(Base, TimestampMixin):
    """
    问题模型，支持脏数据追踪（dirty tracking）以实现增量向量化。

    设计要点：
        - 通过 external_id + content_hash 实现幂等导入，避免重复创建相同题目。
        - is_dirty 字段标记题目内容是否变更，用于触发异步向量重新生成。
        - 支持多种题型（单选、多选、判断、简答），选项以 JSONB 存储。
    """

    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_is_dirty", "is_dirty"),
    )

    # ----- 主键 -----
    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
        comment="题目唯一标识 UUID"
    )

    # ----- 所属题库 ID（外键）-----
    bank_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("question_banks.id"),
        nullable=False,
        comment="所属题库 ID"
    )

    # ----- 外部标识（可选，用于幂等导入）-----
    external_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="外部标识，用于幂等导入"
    )

    # ----- 题目内容哈希（SHA256），用于判断题目是否变更 -----
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="题目关键字段（题干+选项+答案）的 SHA256 哈希值"
    )

    # ----- 题干文本 -----
    question_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="题干文本"
    )

    # ----- 题型 -----
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType),
        nullable=False,
        comment="题型"
    )

    # ----- 选项（JSONB 格式）-----
    # 示例：[{"label": "A", "text": "选项内容"}, ...]
    options: Mapped[list[dict] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="选项列表，每个选项包含 label 和 text"
    )

    # ----- 标准答案（单选/多选存选项字母，判断存 true/false，简答存文本）-----
    answer: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="标准答案"
    )

    # ----- 答案解析(可选)-----
    explanation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="答案解析"
    )

    # ----- 脏标记:内容变更后置为 True,触发向量重新生成 -----
    is_dirty: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="脏标记,为 True 时表示需要重新生成向量"
    )

    # ----- 向量嵌入字段 -----
    question_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1024),
        nullable=True,
        comment="题干文本的向量嵌入(1024维)"
    )
    embedding_text_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="当前题干向量对应的题干哈希，用于判定向量是否过期"
    )
    vectorized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最近一次成功生成题干向量的时间"
    )

    # ----- 关联关系 -----
    # 所属题库
    bank = relationship("QuestionBank", back_populates="questions")

    # 关联的知识点（多对多中间表）
    knowledge_points = relationship(
        "QuestionKnowledgePoint",
        back_populates="question",
        lazy="selectin",
        cascade="all, delete-orphan"   # 删除题目时自动删除关联记录
    )
