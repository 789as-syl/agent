"""Retrieval schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievalWeights(BaseModel):
    """Score-fusion weights for evidence retrieval."""

    dense_hit: float = Field(default=1.0, ge=0, description="Weight for dense/vector anchor hits.")
    lexical_hit: float = Field(default=0.35, ge=0, description="Weight for lexical/BM25 anchor hits.")


class RetrievalConfig(BaseModel):
    """Runtime retrieval configuration snapshot."""

    similarity_threshold: float = Field(default=0.7, ge=0, le=1)
    top_k_before_rerank: int = Field(default=20, ge=1)
    top_k_after_rerank: int = Field(default=8, ge=1)
    cache_ttl: int = Field(default=3600, ge=0)
    enable_rerank: bool = Field(default=True)
    enable_cache: bool = Field(default=True)
    enable_lexical_search: bool = Field(default=True)
    lexical_top_k: int = Field(default=10, ge=1)
    table_neighbor_rows: int = Field(default=1, ge=0, le=5)
    weights: RetrievalWeights = Field(default_factory=RetrievalWeights)


class EvidenceBlockHit(BaseModel):
    """Expanded evidence block returned by retrieval."""

    evidence_block_id: str = Field(..., description="Stable evidence block identifier.")
    knowledge_point_id: str = Field(..., description="Knowledge point UUID (string form).")
    title: str = Field(..., description="Human-readable evidence title.")
    content: str = Field(..., description="Expanded evidence block text sent to the model.")
    score: float = Field(..., ge=0, description="Final fused/re-ranked score.")
    group_type: str = Field(..., description="Anchor group type such as section/table/list/slide.")
    anchor_chunk_indices: list[int] = Field(default_factory=list, description="Anchor chunk indices contributing to the block.")
    provenance: list[dict[str, object]] = Field(default_factory=list, description="Structured provenance entries.")
    similarity: float | None = Field(None, ge=0, le=1)
    rerank_score: float | None = Field(None, ge=0)


class KnowledgePointHit(EvidenceBlockHit):
    """Backward-compatible alias for historical imports."""


class RetrievalExplanation(BaseModel):
    """Retrieval pipeline summary for observability and debugging."""

    cache_hit: bool = Field(..., description="Whether the retrieval result came from cache.")
    anchor_hit_count: int = Field(..., description="Unique anchor groups returned by dense retrieval.")
    lexical_hit_count: int = Field(..., description="Unique anchor groups returned by lexical retrieval.")
    evidence_block_count: int = Field(..., description="Expanded evidence block count before final truncation.")
    rerank_applied: bool = Field(..., description="Whether rerank was applied to expanded evidence blocks.")
    scores: dict[str, float] = Field(default_factory=dict, description="Top fused scores by evidence block ID.")

    @property
    def direct_hit_count(self) -> int:
        return self.anchor_hit_count

    @property
    def mapped_hit_count(self) -> int:
        return self.lexical_hit_count


class RetrievalResponse(BaseModel):
    """Full retrieval response payload."""

    evidence_blocks: list[EvidenceBlockHit] = Field(..., description="Ranked evidence blocks.")
    explanation: RetrievalExplanation = Field(..., description="Retrieval explanation metadata.")
    query: str = Field(..., description="Original query used for retrieval.")
    config_used: RetrievalConfig = Field(..., description="Effective retrieval config snapshot.")

    @property
    def knowledge_points(self) -> list[EvidenceBlockHit]:
        return self.evidence_blocks
