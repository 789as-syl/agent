"""Score fusion helpers for evidence retrieval."""

from __future__ import annotations

from app.core.log_config import get_logger
from app.schemas.retrieval import RetrievalWeights

logger = get_logger(__name__)


class ScoreFusionService:
    """Fuse dense and lexical anchor scores."""

    def fuse_scores(
        self,
        dense_hits: dict[str, float],
        lexical_hits: dict[str, float],
        weights: RetrievalWeights,
    ) -> dict[str, float]:
        fused_scores: dict[str, float] = {}
        for evidence_id, score in dense_hits.items():
            fused_scores[evidence_id] = fused_scores.get(evidence_id, 0.0) + (score * weights.dense_hit)
        for evidence_id, score in lexical_hits.items():
            fused_scores[evidence_id] = fused_scores.get(evidence_id, 0.0) + (score * weights.lexical_hit)
        logger.info(
            "score fusion complete",
            dense_hit_count=len(dense_hits),
            lexical_hit_count=len(lexical_hits),
            unique_anchor_count=len(fused_scores),
        )
        return fused_scores

    def aggregate_anchor_hits(self, results: list[dict]) -> dict[str, float]:
        hits: dict[str, float] = {}
        for result in results:
            evidence_id = str(result["evidence_block_id"])
            score = float(result.get("similarity") or result.get("score") or 0.0)
            hits[evidence_id] = max(hits.get(evidence_id, 0.0), score)
        return hits
