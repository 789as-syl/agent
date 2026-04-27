"""User-owned learning loop service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.learning import PracticeSession
from app.models.question_bank import Question
from app.repositories.learning_repo import LearningRepository
from app.schemas.learning import (
    LearningPathItemResponse,
    LearningPathResponse,
    MasteryRecordListResponse,
    MasteryRecordResponse,
    PracticeAttemptResponse,
    PracticeQuestionView,
    PracticeSessionCreate,
    PracticeSessionListResponse,
    PracticeSessionResponse,
    PracticeSubmitResponse,
    ReviewCardListResponse,
    ReviewCardResponse,
    WrongQuestionListResponse,
    WrongQuestionResponse,
)


class LearningService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = LearningRepository(session)

    async def create_practice_session(self, *, user_id: UUID, request: PracticeSessionCreate) -> PracticeSessionResponse:
        questions = await self.repo.list_questions_for_practice(
            question_ids=request.question_ids,
            knowledge_point_id=request.knowledge_point_id,
            limit=request.limit,
        )
        if not questions:
            raise ValidationError(error_code="NO_PRACTICE_QUESTIONS", message="No available questions for practice")
        question_ids = [question.id for question in questions]
        title = request.title or ("知识点练习" if request.knowledge_point_id else "自主练习")
        session = await self.repo.create_session(
            user_id=user_id,
            title=title,
            status="active",
            source_type="knowledge_point" if request.knowledge_point_id else ("manual" if request.question_ids else "question_bank"),
            source_id=str(request.knowledge_point_id) if request.knowledge_point_id else None,
            question_ids=[str(item) for item in question_ids],
            current_index=0,
            total_questions=len(question_ids),
            correct_count=0,
            score=0.0,
        )
        return await self._serialize_session(session, questions=questions)

    async def list_practice_sessions(self, *, user_id: UUID, page: int, page_size: int) -> PracticeSessionListResponse:
        items, total = await self.repo.list_sessions_for_user(user_id=user_id, page=page, page_size=page_size)
        return PracticeSessionListResponse(
            items=[await self._serialize_session(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_practice_session(self, *, user_id: UUID, session_id: UUID) -> PracticeSessionResponse:
        session = await self.repo.get_session_for_user(session_id, user_id)
        if not session:
            raise NotFoundError(error_code="PRACTICE_SESSION_NOT_FOUND", message="Practice session not found")
        return await self._serialize_session(session)

    async def submit_practice_answer(self, *, user_id: UUID, session_id: UUID, question_id: UUID, answer: str) -> PracticeSubmitResponse:
        session = await self.repo.get_session_for_user(session_id, user_id)
        if not session:
            raise NotFoundError(error_code="PRACTICE_SESSION_NOT_FOUND", message="Practice session not found")
        question_ids = [UUID(str(item)) for item in (session.question_ids or [])]
        if question_id not in question_ids:
            raise ValidationError(error_code="QUESTION_NOT_IN_SESSION", message="Question does not belong to this session")
        question = (await self.repo.get_questions_by_ids([question_id]))[0]
        normalized_answer = answer.strip()
        correct_answer = (question.answer or "").strip()
        is_correct = normalized_answer.casefold() == correct_answer.casefold() if correct_answer else False
        attempt = await self.repo.create_attempt(
            session_id=session.id,
            user_id=user_id,
            question_id=question_id,
            submitted_answer=normalized_answer,
            correct_answer=question.answer,
            is_correct=is_correct,
            explanation=question.explanation,
            metadata_json={"question_type": question.question_type.value if hasattr(question.question_type, "value") else str(question.question_type)},
        )
        wrong_updated = False
        if is_correct:
            session.correct_count += 1
        else:
            await self.repo.upsert_wrong_question(user_id=user_id, question_id=question_id, last_answer=normalized_answer)
            await self.repo.ensure_path_item_for_question(
                user_id=user_id,
                question_id=question_id,
                title=question.question_text[:120],
                reason="来自错题本的薄弱项",
            )
            wrong_updated = True
        review_card = await self.repo.upsert_review_card(user_id=user_id, question_id=question_id, is_correct=is_correct)
        await self.repo.upsert_mastery(user_id=user_id, question_id=question_id, is_correct=is_correct)

        attempted_count = min(session.total_questions, session.current_index + 1)
        session.current_index = attempted_count
        session.score = session.correct_count / max(1, attempted_count)
        if attempted_count >= session.total_questions:
            session.status = "completed"
            session.completed_at = datetime.now(UTC)
        self.session.add(session)
        await self.session.flush()
        await self.session.refresh(session)
        return PracticeSubmitResponse(
            attempt=PracticeAttemptResponse.model_validate(attempt),
            session=await self._serialize_session(session),
            wrong_question_updated=wrong_updated,
            review_card_due_at=review_card.due_at,
        )

    async def list_wrong_questions(self, *, user_id: UUID, page: int, page_size: int) -> WrongQuestionListResponse:
        rows, total = await self.repo.list_wrong_questions(user_id=user_id, page=page, page_size=page_size)
        return WrongQuestionListResponse(
            items=[
                WrongQuestionResponse(
                    id=wrong.id,
                    question_id=wrong.question_id,
                    question_text=question.question_text,
                    wrong_count=wrong.wrong_count,
                    last_answer=wrong.last_answer,
                    resolved_at=wrong.resolved_at,
                    created_at=wrong.created_at,
                    updated_at=wrong.updated_at,
                )
                for wrong, question in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def list_mastery(self, *, user_id: UUID) -> MasteryRecordListResponse:
        items = await self.repo.list_mastery(user_id=user_id)
        return MasteryRecordListResponse(
            items=[MasteryRecordResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def list_review_cards(self, *, user_id: UUID, page: int, page_size: int) -> ReviewCardListResponse:
        rows, total = await self.repo.list_review_cards(user_id=user_id, page=page, page_size=page_size)
        return ReviewCardListResponse(
            items=[
                ReviewCardResponse(
                    id=card.id,
                    question_id=card.question_id,
                    question_text=question.question_text,
                    status=card.status,
                    due_at=card.due_at,
                    interval_days=card.interval_days,
                    ease_factor=card.ease_factor,
                    last_result=card.last_result,
                )
                for card, question in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def learning_path(self, *, user_id: UUID) -> LearningPathResponse:
        items = await self.repo.list_path_items(user_id=user_id)
        return LearningPathResponse(
            items=[LearningPathItemResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def _serialize_session(
        self,
        session: PracticeSession,
        *,
        questions: list[Question] | None = None,
    ) -> PracticeSessionResponse:
        question_ids = [UUID(str(item)) for item in (session.question_ids or [])]
        resolved_questions = questions if questions is not None else await self.repo.get_questions_by_ids(question_ids)
        views = [
            PracticeQuestionView(
                id=question.id,
                question_text=question.question_text,
                question_type=question.question_type.value if hasattr(question.question_type, "value") else str(question.question_type),
                options=question.options,
                knowledge_point_ids=[link.knowledge_point_id for link in (question.knowledge_points or [])],
            )
            for question in resolved_questions
        ]
        return PracticeSessionResponse(
            id=session.id,
            title=session.title,
            status=session.status,
            source_type=session.source_type,
            source_id=session.source_id,
            question_ids=question_ids,
            current_index=session.current_index,
            total_questions=session.total_questions,
            correct_count=session.correct_count,
            score=session.score,
            completed_at=session.completed_at,
            created_at=session.created_at,
            updated_at=session.updated_at,
            questions=views,
        )
