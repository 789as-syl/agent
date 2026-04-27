"""Schemas for admin user management and conversation audit."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.user import UserStatus


class AdminUserResponse(BaseModel):
    id: UUID
    phone: str
    status: UserStatus
    created_at: datetime
    status_changed_at: datetime | None = None
    status_changed_by_user_id: UUID | None = None
    ban_reason: str | None = None

    model_config = {"from_attributes": True, "use_enum_values": True}


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    total: int
    page: int
    page_size: int


class AdminUserStatusUpdateRequest(BaseModel):
    status: UserStatus
    ban_reason: str | None = Field(default=None, max_length=1000)

    model_config = {"use_enum_values": True}

    @field_validator("ban_reason")
    @classmethod
    def normalize_ban_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class AdminConversationSummaryResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminConversationListResponse(BaseModel):
    items: list[AdminConversationSummaryResponse]
    total: int
    page: int
    page_size: int


class AdminAuditMessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    content_blocks: list[dict] | None = None
    created_at: datetime
    audit_playback: list[dict] | None = None
    reply_to_message_id: UUID | None = None


class AdminConversationMessageListResponse(BaseModel):
    items: list[AdminAuditMessageResponse]
    total: int
    page: int
    page_size: int
