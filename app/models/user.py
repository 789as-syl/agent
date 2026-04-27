"""Data model module: user."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserRole(StrEnum):
    """Supported user roles."""

    USER = "user"
    ADMIN = "admin"


class UserStatus(StrEnum):
    """Supported user account states."""

    ACTIVE = "active"
    DISABLED = "disabled"


class User(Base, TimestampMixin):
    """Application user used for authentication and admin management."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="User unique identifier",
    )
    phone: Mapped[str] = mapped_column(
        String(11),
        unique=True,
        nullable=False,
        index=True,
        comment="User phone number",
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Password hash",
    )
    role: Mapped[UserRole] = mapped_column(
        String(20),
        nullable=False,
        default=UserRole.USER,
        comment="User role",
    )
    status: Mapped[UserStatus] = mapped_column(
        String(20),
        nullable=False,
        default=UserStatus.ACTIVE,
        comment="Account status",
    )
    status_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the latest status change",
    )
    status_changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Admin user id who last changed status",
    )
    ban_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for the current disabled status",
    )

    def __repr__(self) -> str:
        role_value = self.role.value if isinstance(self.role, UserRole) else str(self.role)
        status_value = self.status.value if isinstance(self.status, UserStatus) else str(self.status)
        return (
            f"<User(id={self.id}, phone={self.phone}, role={role_value}, "
            f"status={status_value})>"
        )
