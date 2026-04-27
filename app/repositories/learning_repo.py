"""Repositories for user-owned learning loop."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import (
    LearningPathItem,
    MasteryRecord,
    PracticeAttempt,
    PracticeSession,
    ReviewCard,
    WrongQuestion,
)
from app.models.question_bank import Question
from app.models.question_knowledge_point import QuestionKnowledgePoint


class LearningRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_questions_for_practice(
        self,
        *,
        question_ids: list[UUID] | None = None,
        knowledge_point_id: UUID | None = None,
        limit: int = 10,
    ) -> list[Question]:
        stmt = select(Question).where(Question.is_dirty.is_(False))
        if question_ids:
            stmt = stmt.where(Question.id.in_(question_ids))
        if knowledge_point_id:
            stmt = stmt.join(QuestionKnowledgePoint, QuestionKnowledgePoint.question_id == Question.id).where(
                QuestionKnowledgePoint.knowledge_point_id == knowledge_point_id
            )
        stmt = stmt.order_by(Question.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_questions_by_ids(self, question_ids: list[UUID]) -> list[Question]:
        if not question_ids:
            return []
        rows = list((await self.session.execute(select(Question).where(Question.id.in_(question_ids)))).scalars().all())
        by_id = {row.id: row for row in rows}
        return [by_id[item] for item in question_ids if item in by_id]

    async def create_session(self, **kwargs: Any) -> PracticeSession:
        item = PracticeSession(**kwargs)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def get_session_for_user(self, session_id: UUID, user_id: UUID) -> PracticeSession | None:
        return cast(
            PracticeSession | None,
            await self.session.scalar(
                select(PracticeSession).where(PracticeSession.id == session_id, PracticeSession.user_id == user_id)
            ),
        )

    async def list_sessions_for_user(self, *, user_id: UUID, page: int, page_size: int) -> tuple[list[PracticeSession], int]:
        count_stmt = select(func.count()).select_from(PracticeSession).where(PracticeSession.user_id == user_id)
        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        stmt = (
            select(PracticeSession)
            .where(PracticeSession.user_id == user_id)
            .order_by(PracticeSession.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.execute(stmt)).scalars().all()), total

    async def create_attempt(self, **kwargs: Any) -> PracticeAttempt:
        item = PracticeAttempt(created_at=datetime.now(UTC), **kwargs)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def upsert_wrong_question(self, *, user_id: UUID, question_id: UUID, last_answer: str) -> WrongQuestion:
        stmt = (
            pg_insert(WrongQuestion)
            .values(
                user_id=user_id,
                question_id=question_id,
                wrong_count=1,
                last_answer=last_answer,
                metadata_json={},
            )
            .on_conflict_do_update(
                constraint="uq_wrong_questions_user_question",
                set_={
                    "wrong_count": WrongQuestion.wrong_count + 1,
                    "last_answer": last_answer,
                    "resolved_at": None,
                    "updated_at": func.now(),
                },
            )
            .returning(WrongQuestion)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def upsert_review_card(self, *, user_id: UUID, question_id: UUID, is_correct: bool) -> ReviewCard:
        now = datetime.now(UTC)
        status = "scheduled" if is_correct else "due"
        stmt = (
            pg_insert(ReviewCard)
            .values(
                user_id=user_id,
                question_id=question_id,
                status=status,
                due_at=now,
                interval_days=2 if is_correct else 1,
                ease_factor=2.5,
                last_result="correct" if is_correct else "wrong",
            )
            .on_conflict_do_update(
                constraint="uq_review_cards_user_question",
                set_={
                    "status": status,
                    "due_at": now,
                    "interval_days": 2 if is_correct else 1,
                    "last_result": "correct" if is_correct else "wrong",
                    "updated_at": func.now(),
                },
            )
            .returning(ReviewCard)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def upsert_mastery(self, *, user_id: UUID, question_id: UUID, is_correct: bool) -> MasteryRecord:
        existing = await self.session.scalar(
            select(MasteryRecord).where(MasteryRecord.user_id == user_id, MasteryRecord.question_id == question_id)
        )
        if existing is None:
            existing = MasteryRecord(
                user_id=user_id,
                question_id=question_id,
                knowledge_point_id=None,
                mastery_score=1.0 if is_correct else 0.0,
                attempts_count=1,
                correct_count=1 if is_correct else 0,
                last_practiced_at=datetime.now(UTC),
            )
        else:
            existing.attempts_count += 1
            existing.correct_count += 1 if is_correct else 0
            existing.mastery_score = existing.correct_count / max(1, existing.attempts_count)
            existing.last_practiced_at = datetime.now(UTC)
        self.session.add(existing)
        await self.session.flush()
        await self.session.refresh(existing)
        return existing

    async def list_wrong_questions(self, *, user_id: UUID, page: int, page_size: int) -> tuple[list[tuple[WrongQuestion, Question]], int]:
        count_stmt = select(func.count()).select_from(WrongQuestion).where(WrongQuestion.user_id == user_id)
        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        stmt = (
            select(WrongQuestion, Question)
            .join(Question, Question.id == WrongQuestion.question_id)
            .where(WrongQuestion.user_id == user_id)
            .order_by(WrongQuestion.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows], total

    async def list_mastery(self, *, user_id: UUID) -> list[MasteryRecord]:
        return list((await self.session.execute(select(MasteryRecord).where(MasteryRecord.user_id == user_id))).scalars().all())

    async def list_review_cards(self, *, user_id: UUID, page: int, page_size: int) -> tuple[list[tuple[ReviewCard, Question]], int]:
        count_stmt = select(func.count()).select_from(ReviewCard).where(ReviewCard.user_id == user_id)
        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        stmt = (
            select(ReviewCard, Question)
            .join(Question, Question.id == ReviewCard.question_id)
            .where(ReviewCard.user_id == user_id)
            .order_by(ReviewCard.due_at.asc(), ReviewCard.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows], total

    async def list_path_items(self, *, user_id: UUID) -> list[LearningPathItem]:
        return list(
            (await self.session.execute(
                select(LearningPathItem)
                .where(LearningPathItem.user_id == user_id)
                .order_by(LearningPathItem.priority.asc(), LearningPathItem.created_at.desc())
            )).scalars().all()
        )

    async def ensure_path_item_for_question(self, *, user_id: UUID, question_id: UUID, title: str, reason: str) -> None:
        existing = await self.session.scalar(
            select(LearningPathItem).where(
                LearningPathItem.user_id == user_id,
                LearningPathItem.question_id == question_id,
                LearningPathItem.status != "done",
            )
        )
        if existing:
            return
        self.session.add(
            LearningPathItem(
                user_id=user_id,
                question_id=question_id,
                knowledge_point_id=None,
                title=title,
                status="pending",
                priority=50,
                reason=reason,
            )
        )
        await self.session.flush()
