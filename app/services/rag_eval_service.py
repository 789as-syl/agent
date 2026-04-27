"""RAG Eval Lab service."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.rag_eval import RagEvalRun, RagGoldenQuery
from app.repositories.rag_eval_repo import RagEvalRunRepository, RagGoldenQueryRepository
from app.schemas.admin_operations import RagEvalRunCreate
from app.services.retrieval.retrieval_service import RetrievalService


class RagEvalService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.golden_repo = RagGoldenQueryRepository(session)
        self.run_repo = RagEvalRunRepository(session)

    async def create_golden_query(
        self,
        *,
        actor_user_id: UUID,
        name: str,
        query: str,
        expected_answer: str | None,
        expected_source_ids: list[str],
        tags: list[str],
    ) -> RagGoldenQuery:
        return await self.golden_repo.create(
            created_by_user_id=actor_user_id,
            name=name,
            query=query,
            expected_answer=expected_answer,
            expected_source_ids=expected_source_ids,
            tags=tags,
            is_active=True,
        )

    async def list_golden_queries(self, *, page: int, page_size: int) -> tuple[list[RagGoldenQuery], int]:
        return await self.golden_repo.list_items(page=page, page_size=page_size, active_only=True)

    async def delete_golden_query(self, item_id: UUID) -> RagGoldenQuery:
        item = await self.golden_repo.get_by_id(item_id)
        if not item or not item.is_active:
            raise NotFoundError(error_code="RAG_GOLDEN_QUERY_NOT_FOUND", message="Golden query not found")
        return await self.golden_repo.soft_delete(item)

    async def run_eval(self, *, actor_user_id: UUID, request: RagEvalRunCreate) -> RagEvalRun:
        golden = None
        query = request.query
        expected_source_ids: list[str] = []
        if request.golden_query_id:
            golden = await self.golden_repo.get_by_id(request.golden_query_id)
            if not golden or not golden.is_active:
                raise NotFoundError(error_code="RAG_GOLDEN_QUERY_NOT_FOUND", message="Golden query not found")
            query = golden.query
            expected_source_ids = [str(item) for item in (golden.expected_source_ids or [])]
        if not query or not query.strip():
            raise ValidationError(error_code="RAG_EVAL_QUERY_REQUIRED", message="query or golden_query_id is required")

        run = await self.run_repo.create(
            golden_query_id=golden.id if golden else None,
            query=query,
            status="running",
            score=0.0,
            evidence_count=0,
            missing_expected_count=0,
            result_json={},
            created_by_user_id=actor_user_id,
        )
        try:
            response = await RetrievalService(self.session).retrieve(
                query=query,
                user_id=actor_user_id,
                conversation_id=None,
                record_observability=False,
                update_retrieval_counters=False,
            )
            evidence_ids = [block.evidence_block_id for block in response.evidence_blocks]
            kp_ids = [block.knowledge_point_id for block in response.evidence_blocks]
            matched = sum(1 for expected in expected_source_ids if expected in evidence_ids or expected in kp_ids)
            missing = max(0, len(expected_source_ids) - matched)
            evidence_count = len(response.evidence_blocks)
            score = 1.0 if not expected_source_ids and evidence_count else (matched / len(expected_source_ids) if expected_source_ids else 0.0)
            run.status = "success"
            run.score = float(score)
            run.evidence_count = evidence_count
            run.missing_expected_count = missing
            run.result_json = {
                "evidence_ids": evidence_ids,
                "knowledge_point_ids": kp_ids,
                "explanation": response.explanation.model_dump(),
                "no_evidence": evidence_count == 0,
            }
            run.error_message = None
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            run.result_json = {"error_code": "RAG_EVAL_FAILED"}
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def list_runs(self, *, page: int, page_size: int) -> tuple[list[RagEvalRun], int]:
        return await self.run_repo.list_items(page=page, page_size=page_size)
