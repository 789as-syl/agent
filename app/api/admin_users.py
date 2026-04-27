# ruff: noqa: B008
"""Admin user management and conversation audit routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_session, get_current_admin_user
from app.models.user import User, UserStatus
from app.schemas.admin_users import (
    AdminConversationListResponse,
    AdminConversationMessageListResponse,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserStatusUpdateRequest,
)
from app.services.admin_user_service import (
    AdminUserService,
    serialize_admin_conversation,
    serialize_admin_message,
    serialize_admin_user,
)

admin_user_router = APIRouter(prefix="/api/v1/admin", tags=["admin-users"])


@admin_user_router.get("/users", response_model=AdminUserListResponse)
async def list_admin_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    status: UserStatus | None = Query(default=None),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> AdminUserListResponse:
    _ = current_user
    service = AdminUserService(session)
    items, total = await service.list_users(page=page, page_size=page_size, q=q, status=status)
    return AdminUserListResponse(
        items=[serialize_admin_user(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@admin_user_router.get("/users/{user_id}", response_model=AdminUserResponse)
async def get_admin_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> AdminUserResponse:
    _ = current_user
    service = AdminUserService(session)
    return serialize_admin_user(await service.get_user(user_id))


@admin_user_router.patch("/users/{user_id}/status", response_model=AdminUserResponse)
async def update_admin_user_status(
    user_id: UUID,
    request: AdminUserStatusUpdateRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> AdminUserResponse:
    service = AdminUserService(session)
    user = await service.update_user_status(
        target_user_id=user_id,
        actor_user=current_user,
        target_status=request.status,
        ban_reason=request.ban_reason,
    )
    return serialize_admin_user(user)


@admin_user_router.get("/users/{user_id}/conversations", response_model=AdminConversationListResponse)
async def list_admin_user_conversations(
    user_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> AdminConversationListResponse:
    _ = current_user
    service = AdminUserService(session)
    items, total = await service.list_user_conversations(user_id=user_id, page=page, page_size=page_size)
    return AdminConversationListResponse(
        items=[serialize_admin_conversation(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@admin_user_router.get(
    "/users/{user_id}/conversations/{conversation_id}/messages",
    response_model=AdminConversationMessageListResponse,
)
async def list_admin_conversation_messages(
    user_id: UUID,
    conversation_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> AdminConversationMessageListResponse:
    _ = current_user
    service = AdminUserService(session)
    items, total = await service.list_conversation_messages(
        user_id=user_id,
        conversation_id=conversation_id,
        page=page,
        page_size=page_size,
    )
    return AdminConversationMessageListResponse(
        items=[serialize_admin_message(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
