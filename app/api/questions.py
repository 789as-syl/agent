# ruff: noqa: B008
"""Question admin routes."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.api.dependencies import get_async_session, get_current_admin_user
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.enums import JobStatus
from app.models.question_bank import Question, QuestionType
from app.models.user import User
from app.repositories.knowledge_point_repo import KnowledgePointRepository
from app.repositories.question_repo import QuestionBankRepository, QuestionRepository, VectorizationJobRepository
from app.schemas.question import (
    QuestionBankCreate,
    QuestionBankListResponse,
    QuestionBankResponse,
    QuestionBankUpdate,
    QuestionCreate,
    QuestionImportResponse,
    QuestionKnowledgePointLink,
    QuestionListResponse,
    QuestionResponse,
    QuestionUpdate,
    QuestionVectorizeRequest,
    VectorizationJobListResponse,
    VectorizationJobResponse,
    VectorizationJobRetryResponse,
)
from app.services.admin_audit_service import AdminAuditService
from app.services.question_service import QuestionService, parse_json_import_payload

admin_question_router = APIRouter(prefix="/api/v1/admin", tags=["admin-questions"])


def _build_question_service(session: AsyncSession) -> QuestionService:
    return QuestionService(
        question_repo=QuestionRepository(session),
        job_repo=VectorizationJobRepository(session),
        kp_repo=KnowledgePointRepository(session),
    )


def _build_question_response(question: Question, knowledge_point_ids: list[UUID] | None = None) -> QuestionResponse:
    return QuestionResponse(
        id=question.id,
        bank_id=question.bank_id,
        external_id=question.external_id,
        content_hash=question.content_hash,
        question_text=question.question_text,
        question_type=question.question_type,
        options=question.options,
        answer=question.answer,
        explanation=question.explanation,
        knowledge_point_ids=knowledge_point_ids or [],
        is_dirty=question.is_dirty,
        created_at=question.created_at,
        updated_at=question.updated_at,
    )


@admin_question_router.get("/question-banks", response_model=QuestionBankListResponse)
async def list_question_banks(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> QuestionBankListResponse:
    _ = current_user
    banks_with_count = await QuestionBankRepository(session).list_banks()
    items = [
        QuestionBankResponse(
            id=bank.id,
            name=bank.name,
            description=bank.description,
            total_questions=total,
            created_at=bank.created_at,
            updated_at=bank.updated_at,
        )
        for bank, total in banks_with_count
    ]
    return QuestionBankListResponse(items=items, total=len(items))


@admin_question_router.post("/question-banks", response_model=QuestionBankResponse)
async def create_question_bank(
    request: QuestionBankCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> QuestionBankResponse:
    _ = current_user
    bank = await QuestionBankRepository(session).create(name=request.name, description=request.description)
    return QuestionBankResponse(
        id=bank.id,
        name=bank.name,
        description=bank.description,
        total_questions=0,
        created_at=bank.created_at,
        updated_at=bank.updated_at,
    )


@admin_question_router.patch("/question-banks/{bank_id}", response_model=QuestionBankResponse)
async def update_question_bank(
    bank_id: UUID,
    request: QuestionBankUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> QuestionBankResponse:
    _ = current_user
    update_data = request.model_dump(exclude_unset=True)
    if not update_data:
        raise ValidationError(error_code="EMPTY_UPDATE", message="No fields to update")

    bank_repo = QuestionBankRepository(session)
    bank = await bank_repo.update(
        bank_id,
        name=update_data.get("name"),
        description=update_data.get("description"),
    )
    if not bank:
        raise NotFoundError(error_code="QUESTION_BANK_NOT_FOUND", message="Question bank not found")

    total_questions = await bank_repo.count_questions(bank_id)
    return QuestionBankResponse(
        id=bank.id,
        name=bank.name,
        description=bank.description,
        total_questions=total_questions,
        created_at=bank.created_at,
        updated_at=bank.updated_at,
    )


@admin_question_router.delete("/question-banks/{bank_id}")
async def delete_question_bank(
    bank_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> dict[str, str]:
    _ = current_user
    bank_repo = QuestionBankRepository(session)
    bank = await bank_repo.get_by_id(bank_id)
    if not bank:
        raise NotFoundError(error_code="QUESTION_BANK_NOT_FOUND", message="Question bank not found")

    total_questions = await bank_repo.count_questions(bank_id)
    if total_questions > 0:
        raise ConflictError(
            error_code="QUESTION_BANK_NOT_EMPTY",
            message="Question bank contains questions and cannot be deleted",
            details={"total_questions": total_questions},
        )

    await bank_repo.delete(bank_id)
    await AdminAuditService(session).record(
        actor_user_id=current_user.id,
        action="question_bank.delete",
        resource_type="question_bank",
        resource_id=bank_id,
        summary="Deleted empty question bank",
    )
    return {"message": "Question bank deleted successfully"}


@admin_question_router.post("/questions", response_model=QuestionResponse)
async def create_question(
    request: QuestionCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> QuestionResponse:
    _ = current_user
    bank_repo = QuestionBankRepository(session)
    if not await bank_repo.get_by_id(request.bank_id):
        raise NotFoundError(error_code="QUESTION_BANK_NOT_FOUND", message="Question bank not found")

    service = _build_question_service(session)
    data = request.model_dump(exclude={"knowledge_point_ids"})
    question = await service.create_question(**data, knowledge_point_ids=request.knowledge_point_ids)
    return _build_question_response(question, request.knowledge_point_ids)


@admin_question_router.get("/questions", response_model=QuestionListResponse)
async def list_questions(
    page: int = 1,
    page_size: int = 20,
    bank_id: UUID | None = None,
    q: str | None = None,
    question_type: QuestionType | None = None,
    is_dirty: bool | None = None,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> QuestionListResponse:
    _ = current_user
    service = _build_question_service(session)
    items, total = await service.list_questions(
        bank_id=bank_id,
        page=page,
        page_size=page_size,
        q=q,
        question_type=question_type,
        is_dirty=is_dirty,
    )
    question_ids = [item.id for item in items]
    mapping = await QuestionRepository(session).get_knowledge_point_mapping(question_ids)

    return QuestionListResponse(
        items=[
            _build_question_response(
                item,
                [entry["knowledge_point_id"] for entry in mapping.get(item.id, [])],
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@admin_question_router.get("/questions/{question_id}", response_model=QuestionResponse)
async def get_question(
    question_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> QuestionResponse:
    _ = current_user
    question = await QuestionRepository(session).get_by_id(question_id)
    if not question:
        raise NotFoundError(error_code="QUESTION_NOT_FOUND", message="Question not found")
    mapping = await QuestionRepository(session).get_knowledge_point_mapping([question_id])
    return _build_question_response(
        question,
        [entry["knowledge_point_id"] for entry in mapping.get(question_id, [])],
    )


@admin_question_router.patch("/questions/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: UUID,
    request: QuestionUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> QuestionResponse:
    _ = current_user
    service = _build_question_service(session)
    question = await service.update_question(question_id, **request.model_dump(exclude_unset=True))
    mapping = await QuestionRepository(session).get_knowledge_point_mapping([question_id])
    return _build_question_response(
        question,
        [entry["knowledge_point_id"] for entry in mapping.get(question_id, [])],
    )


@admin_question_router.delete("/questions/{question_id}")
async def delete_question(
    question_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> dict[str, str]:
    _ = current_user
    service = _build_question_service(session)
    await service.delete_question(question_id)
    await AdminAuditService(session).record(
        actor_user_id=current_user.id,
        action="question.delete",
        resource_type="question",
        resource_id=question_id,
        summary="Deleted question",
    )
    return {"message": "Question deleted successfully"}


@admin_question_router.post("/questions/import", response_model=QuestionImportResponse)
async def import_questions(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> QuestionImportResponse:
    _ = current_user
    service = _build_question_service(session)
    bank_repo = QuestionBankRepository(session)

    content_type = request.headers.get("content-type", "")

    if content_type.startswith("application/json"):
        payload: Any = await request.json()
        if not isinstance(payload, dict):
            raise ValidationError(error_code="INVALID_JSON", message="JSON import payload must be an object")

        raw_bank_id = payload.get("bank_id")
        raw_questions = payload.get("questions")
        if raw_bank_id is None:
            raise ValidationError(error_code="BANK_ID_REQUIRED", message="bank_id is required")
        if not isinstance(raw_questions, list):
            raise ValidationError(error_code="QUESTIONS_REQUIRED", message="questions must be a list")

        try:
            bank_id = UUID(str(raw_bank_id))
        except ValueError as exc:
            raise ValidationError(error_code="INVALID_BANK_ID", message="Invalid bank_id") from exc

        if not await bank_repo.get_by_id(bank_id):
            raise NotFoundError(error_code="QUESTION_BANK_NOT_FOUND", message="Question bank not found")
        return await service.import_questions_json(bank_id, raw_questions)

    form = await request.form()
    raw_bank_id = form.get("bank_id")
    if not raw_bank_id:
        raise ValidationError(error_code="BANK_ID_REQUIRED", message="bank_id is required for form import")

    try:
        bank_id = UUID(str(raw_bank_id))
    except ValueError as exc:
        raise ValidationError(error_code="INVALID_BANK_ID", message="Invalid bank_id") from exc

    if not await bank_repo.get_by_id(bank_id):
        raise NotFoundError(error_code="QUESTION_BANK_NOT_FOUND", message="Question bank not found")

    file = form.get("file")
    json_data = form.get("json_data")

    if isinstance(file, UploadFile):
        file_name = file.filename or ""
        content = await file.read()
        if not content:
            raise ValidationError(error_code="EMPTY_FILE", message="File is empty")

        if file_name.lower().endswith(".xlsx"):
            return await service.import_questions_excel(bank_id, content)

        if file_name.lower().endswith(".json"):
            text_payload = content.decode("utf-8")
            parsed = json.loads(text_payload)

            if isinstance(parsed, dict) and "questions" in parsed:
                json_bank_id, raw_questions = await parse_json_import_payload(text_payload)
                if json_bank_id != bank_id:
                    raise ValidationError(error_code="BANK_ID_MISMATCH", message="Bank ID mismatch")
                return await service.import_questions_json(bank_id, raw_questions)

            if isinstance(parsed, list):
                return await service.import_questions_json(bank_id, parsed)

            raise ValidationError(error_code="INVALID_JSON", message="Unsupported JSON payload")

        raise ValidationError(error_code="INVALID_FILE_TYPE", message="Only .json and .xlsx files are supported")

    if json_data:
        json_bank_id, questions = await parse_json_import_payload(str(json_data))
        if json_bank_id != bank_id:
            raise ValidationError(error_code="BANK_ID_MISMATCH", message="Bank ID mismatch")
        return await service.import_questions_json(bank_id, questions)

    raise ValidationError(error_code="MISSING_INPUT", message="Either multipart file or json_data is required")


@admin_question_router.post("/questions/vectorize", response_model=VectorizationJobResponse)
async def trigger_vectorization(
    request: QuestionVectorizeRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> VectorizationJobResponse:
    _ = current_user
    service = _build_question_service(session)
    payload = request or QuestionVectorizeRequest()
    return await service.trigger_vectorization(payload)


@admin_question_router.get("/questions/vectorize-jobs", response_model=VectorizationJobListResponse)
async def list_vectorization_jobs(
    page: int = 1,
    page_size: int = 20,
    status: JobStatus | None = None,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> VectorizationJobListResponse:
    _ = current_user
    items, total = await VectorizationJobRepository(session).list_jobs(
        page=page,
        page_size=page_size,
        status=status,
    )
    return VectorizationJobListResponse(
        items=[VectorizationJobResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@admin_question_router.get("/questions/vectorize-jobs/{job_id}", response_model=VectorizationJobResponse)
async def get_vectorization_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> VectorizationJobResponse:
    _ = current_user
    return await _build_question_service(session).get_vectorization_job(job_id)


@admin_question_router.post("/questions/vectorize-jobs/{job_id}/retry", response_model=VectorizationJobRetryResponse)
async def retry_vectorization_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> VectorizationJobRetryResponse:
    job_repo = VectorizationJobRepository(session)
    original = await job_repo.get_by_id(job_id)
    if not original:
        raise NotFoundError(error_code="VECTORIZATION_JOB_NOT_FOUND", message="Vectorization job not found")
    if original.status != JobStatus.FAILED:
        raise ValidationError(error_code="VECTORIZATION_JOB_NOT_FAILED", message="Only failed vectorization jobs can be retried")
    new_job = await job_repo.create(
        status=JobStatus.PENDING,
        progress=0,
        total_questions=original.total_questions,
        processed_questions=0,
        metadata_json={"retry_of_job_id": str(original.id)},
    )
    await AdminAuditService(session).record(
        actor_user_id=current_user.id,
        action="vectorization_job.retry",
        resource_type="vectorization_job",
        resource_id=job_id,
        summary="Retried failed vectorization job",
        metadata_json={"new_job_id": str(new_job.id)},
    )
    return VectorizationJobRetryResponse(
        job_id=original.id,
        new_job_id=new_job.id,
        status=new_job.status,
        message="Retry vectorization job created successfully",
    )


@admin_question_router.post("/questions/{question_id}/knowledge-points")
async def link_knowledge_points(
    question_id: UUID,
    request: QuestionKnowledgePointLink,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> dict[str, str]:
    _ = current_user
    await _build_question_service(session).link_knowledge_points(question_id, request.knowledge_point_ids)
    return {"message": "Knowledge points linked successfully"}


@admin_question_router.delete("/questions/{question_id}/knowledge-points/{knowledge_point_id}")
async def unlink_knowledge_point(
    question_id: UUID,
    knowledge_point_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> dict[str, str]:
    _ = current_user
    await _build_question_service(session).unlink_knowledge_point(question_id, knowledge_point_id)
    return {"message": "Knowledge point unlinked successfully"}
