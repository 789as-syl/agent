# ruff: noqa: B008
"""Admin analytics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_session, get_current_admin_user
from app.models.user import User
from app.repositories.admin_analytics_repo import AdminAnalyticsRepository
from app.schemas.admin_analytics import AdminDashboardResponse, AdminRange, KnowledgeGraphResponse
from app.services.admin_analytics_service import AdminAnalyticsService

admin_analytics_router = APIRouter(prefix="/api/v1/admin", tags=["admin-analytics"])


@admin_analytics_router.get("/dashboard", response_model=AdminDashboardResponse)
async def get_dashboard(
    range: AdminRange = Query(default="7d"),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> AdminDashboardResponse:
    _ = current_user
    service = AdminAnalyticsService(AdminAnalyticsRepository(session))
    return await service.get_dashboard(range)


@admin_analytics_router.get("/knowledge-graph", response_model=KnowledgeGraphResponse)
async def get_knowledge_graph(
    range: AdminRange = Query(default="7d"),
    node_limit: int = Query(default=200, ge=1, le=1000),
    include_orphan_questions: bool = Query(default=True),
    force_refresh: bool = Query(default=False),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> KnowledgeGraphResponse:
    _ = current_user
    service = AdminAnalyticsService(AdminAnalyticsRepository(session))
    return await service.get_knowledge_graph(
        range,
        node_limit,
        include_orphan_questions=include_orphan_questions,
        force_refresh=force_refresh,
    )
