"""Agent knowledge retrieval tool."""

import uuid
from typing import Any

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.log_config import get_logger
from app.core.trace_context import build_trace_log_context, merge_trace_log_context
from app.schemas.retrieval import RetrievalConfig
from app.services.retrieval.retrieval_service import RetrievalService
from app.tools.result_protocol import build_tool_result
from app.tools.runtime_context import build_dialogue_context

logger = get_logger(__name__)


class KnowledgeRetrievalInput(BaseModel):
    query: str = Field(
        description="Required. Question to search in the knowledge base.",
        examples=["根据我上传的商业计划书，总结当前融资风险"],
    )


class RetrievalTool:
    name = "knowledge_retrieval"

    def __init__(self, db_session: AsyncSession, config: RetrievalConfig | None = None):
        self.db_session = db_session
        self.config = config or RetrievalConfig()

    def _trace_context(
        self,
        *,
        request_id: str,
        user_id: str,
        conversation_id: str,
        stage: str | None = None,
        event_type: str | None = None,
    ) -> dict[str, str]:
        return build_trace_log_context(
            request_id=request_id,
            conversation_id=conversation_id,
            user_id=user_id,
            stage=stage,
            event_type=event_type,
        )

    async def execute(
        self,
        *,
        query: str,
        runtime: ToolRuntime[Any, Any],
    ) -> dict[str, Any]:
        context = runtime.context
        request_trace_id = str(getattr(context, "request_id", "") or uuid.uuid4())
        user_id = str(getattr(context, "user_id", "") or "")
        conversation_id = str(getattr(context, "conversation_id", "") or "")
        dialogue_context = build_dialogue_context(runtime)
        logger.info(
            "retrieval tool query received",
            **merge_trace_log_context(
                self._trace_context(
                    request_id=request_trace_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    stage="tool_retrieval",
                    event_type="start",
                ),
                query_preview=query[:100],
            ),
        )
        try:
            service = RetrievalService(db_session=self.db_session, config=self.config)
            result = await service.retrieve(
                query=query,
                user_id=uuid.UUID(user_id),
                conversation_id=uuid.UUID(conversation_id),
                context=dialogue_context,
                config=self.config,
            )
            if not self.db_session.is_active:
                await self.db_session.rollback()
            evidence_blocks = [
                {
                    "evidence_block_id": item.evidence_block_id,
                    "knowledge_point_id": item.knowledge_point_id,
                    "title": item.title,
                    "content": item.content,
                    "score": item.score,
                    "group_type": item.group_type,
                    "anchor_chunk_indices": item.anchor_chunk_indices,
                    "provenance": item.provenance,
                    "similarity": item.similarity,
                    "rerank_score": item.rerank_score,
                }
                for item in result.evidence_blocks
            ]
            return build_tool_result(
                success=True,
                tool="knowledge_retrieval",
                retrieval_failed=False,
                message=f"found {len(evidence_blocks)} evidence blocks",
                evidence_blocks=evidence_blocks,
                total_count=len(evidence_blocks),
                result_count=len(evidence_blocks),
                explanation=result.explanation.model_dump() if result.explanation else None,
            )
        except Exception as exc:
            logger.error(
                "retrieval tool failed",
                exc_info=True,
                **merge_trace_log_context(
                    self._trace_context(
                        request_id=request_trace_id,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        stage="tool_retrieval",
                        event_type="failed",
                    ),
                    error=str(exc),
                ),
            )
            try:
                await self.db_session.rollback()
            except Exception as rollback_exc:  # pragma: no cover
                logger.warning(
                    "retrieval tool rollback failed",
                    **merge_trace_log_context(
                        self._trace_context(
                            request_id=request_trace_id,
                            user_id=user_id,
                            conversation_id=conversation_id,
                            stage="tool_retrieval",
                            event_type="rollback_failed",
                        ),
                        error=str(rollback_exc),
                    ),
                )
            return build_tool_result(
                success=False,
                tool="knowledge_retrieval",
                retrieval_failed=True,
                message="知识库检索暂不可用，已切换为直接回答",
                evidence_blocks=[],
                total_count=0,
                result_count=0,
                error_code="RETRIEVAL_PROVIDER_UNAVAILABLE",
            )


def create_retrieval_tool(
    db_session: AsyncSession,
    config: RetrievalConfig | None = None,
) -> Any:
    retrieval = RetrievalTool(db_session=db_session, config=config)

    @tool(
        "knowledge_retrieval",
        args_schema=KnowledgeRetrievalInput,
        description=(
            "Purpose: retrieve evidence from the private knowledge base for an innovation/entrepreneurship answer.\n"
            "Call when: the user is asking an in-scope innovation/entrepreneurship question, especially when "
            "you may need knowledge-base evidence, course materials, uploaded files, project context, question-bank "
            "evidence, or recent dialogue context. This is the default first tool for in-scope domain questions.\n"
            "Do not call when: the request is casual chat, clearly outside the innovation/entrepreneurship scope, "
            "a pure deterministic calculation, or a latest/real-time external-information query "
            "that should go to web search.\n"
            "Input: query(string, required). Runtime context is injected automatically.\n"
            "Output: JSON with evidence_blocks[], result_count, and success."
        ),
    )
    async def knowledge_retrieval(query: str, runtime: ToolRuntime[Any, Any]) -> dict[str, Any]:
        return await retrieval.execute(query=query, runtime=runtime)

    return knowledge_retrieval
