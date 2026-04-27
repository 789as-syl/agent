"""Admin audit log model."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AdminAuditLog(Base, TimestampMixin):
    """Append-only admin operation audit record.

    This is deliberately user/admin scoped only. It does not introduce tenant,
    organization, or fine-grained RBAC concepts.
    """

    __tablename__ = "admin_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_admin_audit_logs_actor_user_id", "actor_user_id"),
        Index("ix_admin_audit_logs_action", "action"),
        Index("ix_admin_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_admin_audit_logs_created_at", "created_at"),
    )
