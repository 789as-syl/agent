"""数据模型模块：retrieval_log。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RetrievalLog(Base):
    """
    检索日志模型，用于审计和分析检索操作。

    设计目的：
        - 记录每次 RAG 检索的完整上下文，包括查询语句、配置快照、返回结果和性能指标。
        - 支持按用户、时间、缓存命中等多维度查询，便于生成统计报表。
        - 为检索质量调优和 A/B 测试提供数据基础。

    注意：该模型记录的是**单次检索操作**，而非整个对话。一个对话可能包含多次检索。
    """

    __tablename__ = "retrieval_logs"

    # ----- 主键：日志唯一标识 -----
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="日志唯一标识 UUID"
    )

    # ----- 用户标识（谁发起的检索）-----
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="发起检索的用户 ID"
    )

    # ----- 所属会话（可选，用于关联对话上下文）-----
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="所属会话 ID，若检索发生在对话中则记录，独立检索可为空"
    )

    # ----- 查询信息 -----
    original_query: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="用户输入的原始查询语句"
    )

    # ----- 配置快照：记录本次检索使用的参数 -----
    config_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="检索配置快照，如 top_k、相似度阈值、使用的模型、混合检索权重等"
    )

    # ----- 检索结果：分阶段记录命中的知识点 ID -----
    direct_hit_kp_ids: Mapped[list] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
        comment="直接命中（如关键词精确匹配）的知识点 ID 列表"
    )
    mapped_kp_ids: Mapped[list] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
        comment="经过映射（如实体链接、同义词扩展）后命中的知识点 ID 列表"
    )
    final_kp_ids: Mapped[list] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
        comment="最终返回给用户的知识点 ID 列表（去重排序后）"
    )
    # ----- evidence 时代兼容字段（sidecar）-----
    anchor_kp_ids: Mapped[list | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        comment="evidence 口径：锚点知识点 ID 列表（可回退映射到 direct_hit_kp_ids）"
    )
    expanded_kp_ids_non_anchor: Mapped[list | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        comment="evidence 口径：扩展命中但非锚点的知识点 ID 列表（可回退映射到 mapped_kp_ids）"
    )
    final_evidence_kp_ids: Mapped[list | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        comment="evidence 口径：最终证据聚合后的知识点 ID 列表（可回退映射到 final_kp_ids）"
    )

    # ----- 详细评分数据（用于调试和排序分析）-----
    scores_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="每个最终知识点的详细评分，如 BM25 分数、向量相似度、融合分数等"
    )

    # ----- 缓存与性能指标 -----
    cache_hit: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否命中缓存（完全相同的查询直接返回缓存结果）"
    )
    duration_ms: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="检索耗时（毫秒），包括向量搜索、重排序、融合等全流程时间"
    )

    # ----- 创建时间 -----
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="日志记录创建时间（UTC）"
    )

    # ----- 表级配置（索引等）-----
    __table_args__ = (
        Index("ix_retrieval_logs_user_id", "user_id"),
        Index("ix_retrieval_logs_created_at", "created_at"),
        Index("ix_retrieval_logs_cache_hit", "cache_hit"),
    )
