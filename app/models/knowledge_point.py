"""数据模型模块：knowledge_point。"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

EMBEDDING_DIM = 1024

class KnowledgePoint(Base, TimestampMixin):
    __tablename__ = "knowledge_points"
    __table_args__ = (
        Index(
            "ix_knowledge_points_retrieval_count_desc",
            "retrieval_count",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="知识点唯一标识 UUID"
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="文档标题（通常取自文件名或用户输入）"
    )
    file_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="文件类型：pdf, md, docx, txt 等"
    )
    object_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="文件在 MinIO 中的存储路径（如 documents/uuid_filename.pdf）"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="标记当前知识点分块向量是否激活"
    )
    retrieval_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="知识点被检索次数（所有chunk检索次数之和）"
    )
    document_metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="文档级解析/缓存/质量元数据，如 parser_name、cache_path、quality_status 等",
    )

    # Relationships
    # lazy="selectin" 会在访问 chunks 时使用 IN 查询一次性加载所有关联分块，避免 N+1 问题
    chunks = relationship(
        "KnowledgePointChunk",
        back_populates="knowledge_point",
        lazy="noload"   # 不自动加载分块，按需通过 selectinload 显式加载
    )


class KnowledgePointChunk(Base):
    """
    知识点分块模型（每个知识点被切分为多个块，每个块拥有独立的向量嵌入）。
    """

    __tablename__ = "knowledge_point_chunks"
    __table_args__ = (
        Index("ix_knowledge_point_chunks_kp_id", "knowledge_point_id"),
        Index("ix_knowledge_point_chunks_chunk_index", "chunk_index"),
        Index("ix_knowledge_point_chunks_kp_id_order", "knowledge_point_id", "chunk_index"),
        Index("ix_knowledge_point_chunks_retrieval_count", "retrieval_count"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="分块唯一标识 UUID"
    )
    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属知识点 ID"
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="分块在文档中的序号（从 0 开始）"
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="分块包含的文本内容"
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM),
        nullable=True,
        comment=f"文本向量表示（{EMBEDDING_DIM} 维），用于相似度检索。可能为空表示等待异步生成"
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="分块元数据，如页码、标题层级、语言等"
    )
    retrieval_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="该分块被检索命中的次数"
    )

    # Relationships
    knowledge_point = relationship("KnowledgePoint", back_populates="chunks")
