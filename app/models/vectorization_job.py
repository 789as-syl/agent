"""数据模型模块：vectorization_job。"""

import uuid as uuid_module
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import JobStatus


class VectorizationJob(Base, TimestampMixin):
    """
    向量化任务追踪模型。

    用于记录批量向量生成任务（如题目向量化）的执行状态、进度和结果。
    通常配合 Celery 等异步任务队列使用，提供任务的可观测性和管理能力。

    字段说明：
        - id：任务唯一标识 UUID
        - status：任务状态（pending / running / success / failed）
        - progress：进度百分比（0-100）
        - total_questions：本次任务需处理的题目总数
        - processed_questions：已成功处理的题目数量
        - celery_task_id：关联的 Celery 任务 ID（用于查询或撤销任务）
        - error_message：失败时的错误详情
        - started_at：任务开始执行的时间
        - finished_at：任务完成（成功或失败）的时间
        - metadata_json：额外元数据
    """

    __tablename__ = "vectorization_jobs"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
        comment="任务唯一标识 UUID"
    )

    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status", create_constraint=True, native_enum=True),
        nullable=False,
        default=JobStatus.PENDING,
        comment="任务状态：pending（等待中）、running（执行中）、success（成功）、failed（失败）"
    )

    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="任务进度百分比，取值范围 0-100"
    )

    total_questions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="本次任务需要处理的题目总数"
    )

    processed_questions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="已成功处理的题目数量"
    )

    celery_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="关联的 Celery 任务 ID，用于异步任务追踪与管理"
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="任务失败时的错误详细信息"
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="任务实际开始执行的时间（UTC）"
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="任务完成（成功或失败）的时间（UTC）"
    )

    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="额外元数据，如触发参数、重试信息等"
    )
