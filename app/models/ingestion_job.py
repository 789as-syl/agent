"""数据模型模块：ingestion_job。"""

import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import JobStatus


class IngestionJob(Base, TimestampMixin):
    """
    文档入库任务追踪模型。

    用途：
        - 追踪文档上传后，从 MinIO 拉取、解析文本、切分、向量化、存入知识库的完整流程。
        - 支持异步任务（Celery）状态管理，前端可通过轮询该表获取实时进度。

    状态机流转：
        pending  →  running  →  success
                         ↘  failed

    字段说明：
        - id：任务唯一标识 UUID
        - knowledge_point_id：入库成功后关联的知识点 ID（失败时为 NULL）
        - object_path：MinIO 中的文件路径（用于定位原始文件）
        - file_type：文件类型（pdf、md、docx 等）
        - status：当前状态（pending / running / success / failed）
        - progress：进度百分比（0-100）
        - error_message：失败时的错误详情
        - celery_task_id：关联的 Celery 任务 ID，便于查询或撤销
        - created_at / updated_at：记录创建和更新时间
    """

    __tablename__ = "ingestion_jobs"

    # ----- 主键：UUID 唯一标识 -----
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="任务唯一标识 UUID"
    )

    # ----- 关联的知识点 ID（任务成功后才会有值）-----
    knowledge_point_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_points.id"),
        nullable=True,
        comment="入库成功后创建的知识点 ID，失败时为 NULL"
    )

    # ----- MinIO 对象存储路径 -----
    object_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="文件在 MinIO 中的完整路径（如 documents/uuid_filename.pdf）"
    )

    # ----- 文件类型 -----
    file_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="文件类型：pdf、md、docx、txt 等"
    )

    # ----- 任务状态 -----
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status", create_constraint=True, native_enum=True),
        nullable=False,
        default=JobStatus.PENDING,
        comment="任务状态：pending（等待） / running（执行中） / success（成功） / failed（失败）"
    )

    # ----- 进度百分比（0-100）-----
    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="任务进度百分比，取值范围 0-100"
    )

    # ----- 错误信息（仅失败时填充）-----
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="任务失败时的详细错误信息"
    )

    # ----- Celery 任务 ID -----
    celery_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="关联的 Celery 任务 ID，用于异步任务追踪与管理"
    )

    # ----- 表级索引（加速常见查询）-----
    __table_args__ = (
        Index("ix_ingestion_jobs_status", "status"),           # 按状态筛选任务（如查询所有 pending 任务）
        Index("ix_ingestion_jobs_kp_id", "knowledge_point_id"),# 按知识点反查入库任务
        Index("ix_ingestion_jobs_created_at", "created_at"),   # 按时间排序或清理历史记录
    )
