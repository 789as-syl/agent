# ruff: noqa: B008
"""Admin RAG Eval Lab routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_session, get_current_admin_user
from app.models.user import User
from app.schemas.admin_operations import (
    RagEvalRunCreate,
    RagEvalRunListResponse,
    RagEvalRunResponse,
    RagGoldenQueryCreate,
    RagGoldenQueryListResponse,
    RagGoldenQueryResponse,
)
from app.services.admin_audit_service import AdminAuditService
from app.services.rag_eval_service import RagEvalService

rag_eval_lab_router = APIRouter(prefix="/api/v1/admin", tags=["rag-eval-lab"])


@rag_eval_lab_router.get("/rag-eval/golden-queries", response_model=RagGoldenQueryListResponse)
async def list_golden_queries(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> RagGoldenQueryListResponse:
    _ = current_user
    items, total = await RagEvalService(session).list_golden_queries(page=page, page_size=page_size)
    return RagGoldenQueryListResponse(
        items=[RagGoldenQueryResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@rag_eval_lab_router.post("/rag-eval/golden-queries", response_model=RagGoldenQueryResponse)
async def create_golden_query(
    request: RagGoldenQueryCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> RagGoldenQueryResponse:
    item = await RagEvalService(session).create_golden_query(
        actor_user_id=current_user.id,
        name=request.name,
        query=request.query,
        expected_answer=request.expected_answer,
        expected_source_ids=request.expected_source_ids,
        tags=request.tags,
    )
    await AdminAuditService(session).record(
        actor_user_id=current_user.id,
        action="rag_golden_query.create",
        resource_type="rag_golden_query",
        resource_id=item.id,
        summary=f"Created golden query {item.name}",
        metadata_json={"tags": item.tags},
    )
    return RagGoldenQueryResponse.model_validate(item)


@rag_eval_lab_router.delete("/rag-eval/golden-queries/{query_id}")
async def delete_golden_query(
    query_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> dict[str, str]:
    await RagEvalService(session).delete_golden_query(query_id)
    await AdminAuditService(session).record(
        actor_user_id=current_user.id,
        action="rag_golden_query.delete",
        resource_type="rag_golden_query",
        resource_id=query_id,
        summary="Deleted golden query",
    )
    return {"message": "Golden query deleted successfully"}


@rag_eval_lab_router.get("/rag-eval/runs", response_model=RagEvalRunListResponse)
async def list_eval_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> RagEvalRunListResponse:
    _ = current_user
    items, total = await RagEvalService(session).list_runs(page=page, page_size=page_size)
    return RagEvalRunListResponse(
        items=[RagEvalRunResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@rag_eval_lab_router.post("/rag-eval/runs", response_model=RagEvalRunResponse)
async def create_eval_run(
    request: RagEvalRunCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> RagEvalRunResponse:
    run = await RagEvalService(session).run_eval(actor_user_id=current_user.id, request=request)
    await AdminAuditService(session).record(
        actor_user_id=current_user.id,
        action="rag_eval.run",
        resource_type="rag_eval_run",
        resource_id=run.id,
        summary="Ran RAG evaluation",
        metadata_json={"status": run.status, "score": run.score},
    )
    return RagEvalRunResponse.model_validate(run)
