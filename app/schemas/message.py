"""Message schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Public message payload for conversation APIs."""

    id: UUID
    conversation_id: UUID
    run_id: UUID | None = None
    client_message_id: str | None = None
    role: str
    content: str
    content_blocks: list[dict[str, Any]] | None = None
    execution_trace: list[dict[str, Any]] | None = None
    created_at: datetime
    reply_to_message_id: UUID | None = None

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    """Paginated message response."""

    items: list[MessageResponse]
    total: int
    skip: int
    limit: int
