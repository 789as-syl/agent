"""Evidence-centric retrieval orchestration service."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.log_config import get_logger
from app.core.redis import redis_client
from app.core.trace_context import build_trace_log_context, merge_trace_log_context
from app.models.retrieval_log import RetrievalLog
from app.repositories.knowledge_point_repo import KnowledgePointRepository
from app.repositories.question_repo import QuestionRepository
from app.schemas.retrieval import EvidenceBlockHit, RetrievalConfig, RetrievalExplanation, RetrievalResponse
from app.services.retrieval.embedding_service import EmbeddingService
from app.services.retrieval.rerank_service import RerankService
from app.services.retrieval.score_fusion_service import ScoreFusionService
from app.services.retrieval.vector_search_service import VectorSearchService

logger = get_logger(__name__)


class RetrievalService:
    """Coordinate anchor search, evidence expansion, rerank, and observability logging."""

    def __init__(self, db_session: AsyncSession, config: RetrievalConfig | None = None) -> None:
        self.config = config or RetrievalConfig()
        self.db_session = db_session
        self.kp_repo = KnowledgePointRepository(db_session)
        self.question_repo = QuestionRepository(db_session)
        self.embedding_service = EmbeddingService(cache_ttl=self.config.cache_ttl)
        self.vector_search_service = VectorSearchService(self.kp_repo, self.question_repo)
        self.score_fusion_service = ScoreFusionService()
        self.rerank_service = RerankService()

    def _trace_context(
        self,
        *,
        user_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        stage: str | None = None,
        event_type: str | None = None,
    ) -> dict[str, str]:
        return build_trace_log_context(
            user_id=str(user_id) if user_id else None,
            conversation_id=str(conversation_id) if conversation_id else None,
            stage=stage,
            event_type=event_type,
        )

    def _get_cache_key(self, query: str, config: RetrievalConfig, context: str = "") -> str:
        config_hash = hashlib.sha256(config.model_dump_json().encode()).hexdigest()
        payload = {"query": query, "context": context}
        query_hash = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return f"retrieval-evidence:{query_hash}:{config_hash}"

    async def _get_from_cache(
        self,
        query: str,
        config: RetrievalConfig,
        context: str = "",
        *,
        user_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
    ) -> RetrievalResponse | None:
        if not config.enable_cache:
            return None
        cache_key = self._get_cache_key(query, config, context)
        cached = await redis_client.get(cache_key)
        if not cached:
            return None
        logger.info(
            "retrieval cache hit",
            **merge_trace_log_context(
                self._trace_context(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    stage="retrieval",
                    event_type="cache_hit",
                ),
                query_preview=query[:50],
            ),
        )
        return RetrievalResponse(**json.loads(cached))

    async def _save_to_cache(
        self,
        query: str,
        config: RetrievalConfig,
        result: RetrievalResponse,
        context: str = "",
    ) -> None:
        if not config.enable_cache:
            return
        cache_key = self._get_cache_key(query, config, context)
        payload = json.dumps(result.model_dump(), ensure_ascii=False, default=str)
        await redis_client.setex(cache_key, config.cache_ttl, payload)

    async def _has_vector_data(self) -> bool:
        kp_count = await self.kp_repo.count_vectorized_chunks()
        question_repo = getattr(self, "question_repo", None)
        if question_repo is None:
            return kp_count > 0
        question_count = await question_repo.count_vectorized_questions()
        return kp_count > 0 or question_count > 0

    @staticmethod
    def _build_empty_response(query: str, config: RetrievalConfig) -> RetrievalResponse:
        return RetrievalResponse(
            evidence_blocks=[],
            explanation=RetrievalExplanation(
                cache_hit=False,
                anchor_hit_count=0,
                lexical_hit_count=0,
                evidence_block_count=0,
                rerank_applied=False,
                scores={},
            ),
            query=query,
            config_used=config,
        )

    async def retrieve(
        self,
        query: str,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None = None,
        context: str = "",
        config: RetrievalConfig | None = None,
        *,
        record_observability: bool = True,
        update_retrieval_counters: bool = True,
    ) -> RetrievalResponse:
        start_time = time.time()
        config = config or self.config
        cached = await self._get_from_cache(query, config, context, user_id=user_id, conversation_id=conversation_id)
        if cached:
            cached.explanation.cache_hit = True
            return cached

        if not await self._has_vector_data():
            return self._build_empty_response(query, config)

        query_embedding = await self.embedding_service.generate(query)
        dense_results = await self.vector_search_service.search_knowledge_points(
            query_embedding,
            top_k=config.top_k_before_rerank,
            similarity_threshold=config.similarity_threshold,
            update_retrieval_count=update_retrieval_counters,
        )
        lexical_results = (
            await self.vector_search_service.search_keyword(query, top_k=config.lexical_top_k)
            if config.enable_lexical_search
            else []
        )
        question_results = await self.vector_search_service.search_questions(
            query_embedding,
            top_k=max(1, min(config.top_k_after_rerank, config.top_k_before_rerank)),
            similarity_threshold=max(0.0, config.similarity_threshold - 0.1),
        )

        anchor_candidates = self._merge_anchor_candidates(dense_results, lexical_results)
        dense_hits = {
            str(candidate["evidence_block_id"]): float(candidate.get("dense_score") or 0.0)
            for candidate in anchor_candidates
            if candidate.get("dense_score") is not None
        }
        lexical_hits = {
            str(candidate["evidence_block_id"]): float(candidate.get("lexical_score") or 0.0)
            for candidate in anchor_candidates
            if candidate.get("lexical_score") is not None
        }
        fused_scores = self.score_fusion_service.fuse_scores(dense_hits, lexical_hits, config.weights)
        top_anchor_ids = sorted(fused_scores, key=lambda evidence_id: fused_scores[evidence_id], reverse=True)[
            : config.top_k_before_rerank
        ]
        anchor_map = {candidate["evidence_block_id"]: candidate for candidate in anchor_candidates}
        selected_anchors = [anchor_map[evidence_id] for evidence_id in top_anchor_ids if evidence_id in anchor_map]

        evidence_candidates = await self._expand_anchor_candidates(selected_anchors, config)
        evidence_candidates.extend(self._question_results_to_evidence(question_results))

        rerank_applied = False
        if config.enable_rerank and evidence_candidates:
            reranked = await self.rerank_service.rerank(
                query=query,
                documents=evidence_candidates,
                top_n=config.top_k_after_rerank,
            )
            rerank_applied = True
        else:
            reranked = evidence_candidates[: config.top_k_after_rerank]

        final_blocks: list[EvidenceBlockHit] = []
        for candidate in reranked:
            evidence_id = str(candidate["evidence_block_id"])
            final_blocks.append(
                EvidenceBlockHit(
                    evidence_block_id=evidence_id,
                    knowledge_point_id=str(candidate["knowledge_point_id"]),
                    title=str(candidate["title"]),
                    content=str(candidate["content"]),
                    score=float(
                        fused_scores.get(
                            evidence_id,
                            candidate.get("rerank_score") or candidate.get("similarity") or 0.0,
                        )
                    ),
                    group_type=str(candidate.get("group_type") or "section"),
                    anchor_chunk_indices=list(candidate.get("anchor_chunk_indices") or []),
                    provenance=list(candidate.get("provenance") or []),
                    similarity=(
                        float(candidate["similarity"]) if candidate.get("similarity") is not None else None
                    ),
                    rerank_score=(
                        float(candidate["rerank_score"]) if candidate.get("rerank_score") is not None else None
                    ),
                )
            )

        response = RetrievalResponse(
            evidence_blocks=final_blocks,
            explanation=RetrievalExplanation(
                cache_hit=False,
                anchor_hit_count=len(dense_hits),
                lexical_hit_count=len(lexical_hits) + len(question_results),
                evidence_block_count=len(evidence_candidates),
                rerank_applied=rerank_applied,
                scores={evidence_id: fused_scores[evidence_id] for evidence_id in top_anchor_ids},
            ),
            query=query,
            config_used=config,
        )

        duration_ms = int((time.time() - start_time) * 1000)
        if record_observability:
            await self._log_retrieval(
                query=query,
                config=config,
                direct_hit_kp_ids=self._unique_kp_ids(selected_anchors),
                mapped_kp_ids=self._expanded_non_anchor_kp_ids(evidence_candidates, selected_anchors),
                final_kp_ids=self._unique_kp_ids([block.model_dump() for block in final_blocks]),
                scores_json=fused_scores,
                cache_hit=False,
                duration_ms=duration_ms,
                user_id=user_id,
                conversation_id=conversation_id,
            )
        if not self.db_session.is_active:
            await self.db_session.rollback()
        await self._save_to_cache(query, config, response, context)
        return response

    def _merge_anchor_candidates(self, dense_results: list[dict], lexical_results: list[dict]) -> list[dict[str, Any]]:
        candidates: dict[str, dict[str, Any]] = {}
        for source, results in (("dense", dense_results), ("lexical", lexical_results)):
            for result in results:
                metadata = dict(result.get("metadata_json") or {})
                group_type = str(
                    metadata.get("docling_group_type")
                    or metadata.get("block_type")
                    or "section"
                )
                group_id = str(
                    metadata.get("docling_group_id")
                    or metadata.get("table_id")
                    or result.get("chunk_id")
                )
                evidence_id = f"{result['knowledge_point_id']}::{group_type}::{group_id}"
                current = candidates.get(evidence_id)
                score_value = float(result.get("similarity") or result.get("score") or 0.0)
                if current is None:
                    candidates[evidence_id] = {
                        **result,
                        "evidence_block_id": evidence_id,
                        "group_type": group_type,
                        "group_id": group_id,
                        "dense_score": None,
                        "lexical_score": None,
                    }
                    current = candidates[evidence_id]
                if source == "dense":
                    current["dense_score"] = max(float(current.get("dense_score") or 0.0), score_value)
                    current["similarity"] = max(float(current.get("similarity") or 0.0), score_value)
                else:
                    current["lexical_score"] = max(float(current.get("lexical_score") or 0.0), score_value)
                    current["score"] = max(float(current.get("score") or 0.0), score_value)
        return list(candidates.values())

    async def _expand_anchor_candidates(
        self,
        anchors: list[dict[str, Any]],
        config: RetrievalConfig,
    ) -> list[dict[str, Any]]:
        kp_ids = list({uuid.UUID(str(anchor["knowledge_point_id"])) for anchor in anchors})
        chunks_by_kp = await self.kp_repo.get_chunks_by_knowledge_point_ids(kp_ids)
        evidence_candidates: list[dict[str, Any]] = []
        for anchor in anchors:
            kp_id = uuid.UUID(str(anchor["knowledge_point_id"]))
            kp_chunks = chunks_by_kp.get(kp_id, [])
            if not kp_chunks:
                continue
            metadata = dict(anchor.get("metadata_json") or {})
            group_type = str(anchor.get("group_type") or "section")
            group_id = str(
                anchor.get("group_id")
                or metadata.get("docling_group_id")
                or metadata.get("table_id")
                or anchor.get("chunk_id")
            )
            related_chunks = []
            for chunk in kp_chunks:
                chunk_metadata = dict(chunk.metadata_json or {})
                chunk_group_id = str(
                    chunk_metadata.get("docling_group_id")
                    or chunk_metadata.get("table_id")
                    or chunk.id
                )
                chunk_group_type = str(chunk_metadata.get("docling_group_type") or "")
                if chunk_group_id == group_id and (not chunk_group_type or chunk_group_type == group_type):
                    related_chunks.append(chunk)
            if not related_chunks:
                related_chunks = [chunk for chunk in kp_chunks if chunk.chunk_index == anchor.get("chunk_index")]
            content, provenance = self._build_evidence_content(related_chunks, metadata, config.table_neighbor_rows)
            evidence_candidates.append(
                {
                    "evidence_block_id": anchor["evidence_block_id"],
                    "knowledge_point_id": str(anchor["knowledge_point_id"]),
                    "title": _evidence_title(anchor.get("knowledge_point_title"), metadata),
                    "content": content,
                    "group_type": group_type,
                    "anchor_chunk_indices": [chunk.chunk_index for chunk in related_chunks],
                    "provenance": provenance,
                    "similarity": anchor.get("similarity"),
                }
            )
        return evidence_candidates

    @staticmethod
    def _question_results_to_evidence(question_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        evidence_candidates: list[dict[str, Any]] = []
        for result in question_results:
            question_id = str(result.get("question_id") or "")
            if not question_id:
                continue
            content_parts = [f"题目：{result.get('question_text') or ''}"]
            options = result.get("options")
            if isinstance(options, list) and options:
                content_parts.append(
                    "选项：" + "；".join(
                        f"{item.get('label')}. {item.get('text')}" for item in options if isinstance(item, dict)
                    )
                )
            if result.get("answer"):
                content_parts.append(f"答案：{result['answer']}")
            if result.get("explanation"):
                content_parts.append(f"解析：{result['explanation']}")
            evidence_candidates.append(
                {
                    "evidence_block_id": f"question::{question_id}",
                    "knowledge_point_id": f"question::{question_id}",
                    "title": "题库证据",
                    "content": "\n".join(content_parts).strip(),
                    "group_type": "question",
                    "anchor_chunk_indices": [],
                    "provenance": [{"source_type": "question_bank", "question_id": question_id}],
                    "similarity": result.get("similarity") or result.get("score") or 0.0,
                }
            )
        return evidence_candidates

    def _build_evidence_content(
        self,
        chunks: list[Any],
        anchor_metadata: dict[str, Any],
        table_neighbor_rows: int,
    ) -> tuple[str, list[dict[str, Any]]]:
        ordered_chunks = sorted(chunks, key=lambda chunk: chunk.chunk_index)
        group_type = str(anchor_metadata.get("docling_group_type") or anchor_metadata.get("block_type") or "section")
        provenance: list[dict[str, Any]] = []
        for chunk in ordered_chunks:
            if not chunk.metadata_json:
                continue
            raw_provenance = chunk.metadata_json.get("provenance")
            if isinstance(raw_provenance, dict):
                provenance.append(dict(raw_provenance))
            elif isinstance(raw_provenance, list):
                provenance.extend(dict(item) for item in raw_provenance if isinstance(item, dict))
        if group_type == "table":
            limited = ordered_chunks[: max(1, table_neighbor_rows * 2 + 1)]
            content = "\n".join(chunk.content for chunk in limited)
            limited_chunk_ids = {chunk.chunk_index for chunk in limited}
            limited_provenance = [
                item
                for item in provenance
                if _chunk_index_matches(item.get("chunk_index"), limited_chunk_ids)
            ]
            return content.strip(), limited_provenance
        content = "\n".join(chunk.content for chunk in ordered_chunks)
        return content.strip(), provenance

    async def _log_retrieval(
        self,
        query: str,
        config: RetrievalConfig,
        direct_hit_kp_ids: list[str],
        mapped_kp_ids: list[str],
        final_kp_ids: list[str],
        scores_json: dict[str, Any],
        cache_hit: bool,
        duration_ms: int,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
    ) -> None:
        try:
            payload = RetrievalLog(
                user_id=user_id,
                conversation_id=conversation_id,
                original_query=query,
                config_json=config.model_dump(),
                direct_hit_kp_ids=[uuid.UUID(value) for value in direct_hit_kp_ids],
                mapped_kp_ids=[uuid.UUID(value) for value in mapped_kp_ids],
                final_kp_ids=[uuid.UUID(value) for value in final_kp_ids],
                anchor_kp_ids=[uuid.UUID(value) for value in direct_hit_kp_ids],
                expanded_kp_ids_non_anchor=[uuid.UUID(value) for value in mapped_kp_ids],
                final_evidence_kp_ids=[uuid.UUID(value) for value in final_kp_ids],
                scores_json={key: float(value) for key, value in scores_json.items()},
                cache_hit=cache_hit,
                duration_ms=duration_ms,
            )
            self.db_session.add(payload)
            await self.db_session.flush()
        except Exception as exc:  # pragma: no cover
            logger.warning("retrieval log persistence failed", error=str(exc))

    async def _update_retrieval_counts(self, *kp_result_groups: list[dict[str, Any]]) -> None:
        for group in kp_result_groups:
            chunk_ids: list[uuid.UUID] = []
            for result in group:
                chunk_id = result.get("chunk_id")
                if chunk_id is None:
                    continue
                chunk_ids.append(chunk_id if isinstance(chunk_id, uuid.UUID) else uuid.UUID(str(chunk_id)))
            if chunk_ids:
                await self.kp_repo.increment_retrieval_counts(chunk_ids)

    @staticmethod
    def _select_best_candidates(all_kp_results: list[dict[str, Any]], top_kp_ids: list[str]) -> list[dict[str, Any]]:
        best_by_kp: dict[str, dict[str, Any]] = {}
        best_similarity: dict[str, float] = {}
        for result in all_kp_results:
            kp_id = str(result["knowledge_point_id"])
            similarity = float(result.get("similarity") or 0.0)
            if kp_id not in best_similarity or similarity > best_similarity[kp_id]:
                best_similarity[kp_id] = similarity
                best_by_kp[kp_id] = result
        return [best_by_kp[kp_id] for kp_id in top_kp_ids if kp_id in best_by_kp]

    @staticmethod
    def _unique_kp_ids(items: list[dict[str, Any]]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            kp_id = str(item.get("knowledge_point_id") or "")
            if kp_id.startswith("question::") or item.get("group_type") == "question":
                continue
            try:
                uuid.UUID(kp_id)
            except ValueError:
                continue
            if kp_id and kp_id not in seen:
                seen.add(kp_id)
                ordered.append(kp_id)
        return ordered

    @staticmethod
    def _expanded_non_anchor_kp_ids(
        evidence_candidates: list[dict[str, Any]],
        anchors: list[dict[str, Any]],
    ) -> list[str]:
        anchor_set = set(RetrievalService._unique_kp_ids(anchors))
        ordered: list[str] = []
        for candidate in evidence_candidates:
            kp_id = str(candidate.get("knowledge_point_id") or "")
            if kp_id and kp_id not in anchor_set and kp_id not in ordered:
                ordered.append(kp_id)
        return ordered


def _evidence_title(default_title: Any, metadata: dict[str, Any]) -> str:
    heading_path = list(metadata.get("heading_path") or [])
    if heading_path:
        return " / ".join(str(item) for item in heading_path if item)
    caption = str(metadata.get("caption") or "").strip()
    if caption:
        return caption
    return str(default_title or "结构化证据")


def _chunk_index_matches(value: Any, allowed: set[int]) -> bool:
    if value in (None, ""):
        return True
    try:
        return int(value) in allowed
    except (TypeError, ValueError):
        return False
