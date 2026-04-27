"""数据模型模块：question_knowledge_point。"""

import uuid as uuid_module

from sqlalchemy import Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class QuestionKnowledgePoint(Base):
    """
    题目与知识点的多对多关联表（带关联权重）。

    设计目的：
        - 一道题目可以关联多个知识点（例如：一道 Python 题目既涉及"列表"又涉及"循环"）。
        - 一个知识点可以被多道题目关联。
        - 通过 `relevance_weight` 字段表示该知识点与题目的相关程度，用于检索排序或推荐算法。

    字段说明：
        - question_id：题目 ID（外键，级联删除）
        - knowledge_point_id：知识点 ID（外键，级联删除）
        - relevance_weight：关联权重（0.0 ~ 1.0 或更大），默认 1.0
        - created_at：关联创建时间
    """

    __tablename__ = "question_knowledge_points"

    # ----- 复合主键：题目 ID + 知识点 ID -----
    question_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
        comment="题目 ID（外键，删除题目时自动删除关联）"
    )
    knowledge_point_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        primary_key=True,
        comment="知识点 ID（外键，删除知识点时自动删除关联）"
    )

    # ----- 关联权重：表示该知识点对此题目的重要程度 -----
    relevance_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        comment="关联权重，值越大表示该知识点与题目越相关，可用于排序和加权检索"
    )

    # ----- 关联关系：便于通过中间表直接访问两端的对象 -----
    question = relationship(
        "Question",
        back_populates="knowledge_points"
    )
    knowledge_point = relationship(
        "KnowledgePoint",
        lazy="selectin"   # 加载时自动用 IN 查询一次性获取知识点详情，避免 N+1
    )
