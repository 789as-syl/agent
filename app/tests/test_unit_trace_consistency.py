"""Unit tests for stream/persisted trace consistency invariants."""

from __future__ import annotations

from app.agents.native_agent_runner import (
    CanonicalTrace,
    TraceAnchor,
    TraceEvidenceItem,
    _canonical_trace_to_entry,
    _canonical_trace_to_sse_data,
)


def test_trace_consistency_core_fields_keep_stream_persisted_parity() -> None:
    trace = CanonicalTrace(
        kind="tool_result",
        title="知识库命中 1 条",
        status="completed",
        detail="命中商业模式画布",
        decision_code="retrieval_hit",
        tool_name="knowledge_retrieval",
        tool_input={"query": "商业模式画布"},
        result_count=1,
        retrieval_failed=False,
        evidence=[
            TraceEvidenceItem(
                source="classifier",
                label="命中信号",
                detail="创新创业语义",
                reasoning_range=TraceAnchor(start=2, end=5),
            )
        ],
        reasoning_anchor=TraceAnchor(start=2, end=5),
        metadata={"provenance_summary": "kb"},
    )

    streamed = _canonical_trace_to_sse_data(trace)
    persisted = _canonical_trace_to_entry(trace, step=4)
    persisted_metadata = persisted["metadata"]

    assert streamed.kind == persisted["kind"]
    assert streamed.title == persisted["title"]
    assert streamed.status == persisted["status"]
    assert streamed.detail == persisted["detail"]
    assert streamed.decision_code == persisted["decision_code"]
    assert streamed.tool_name == persisted_metadata["tool_name"]
    assert streamed.tool_input == persisted_metadata["tool_input"]
    assert streamed.result_count == persisted_metadata["result_count"]
    assert streamed.retrieval_failed is None
    assert "retrieval_failed" not in persisted_metadata
    assert streamed.semantic_key == persisted["semantic_key"]
    assert streamed.reasoning_anchor is not None
    assert streamed.reasoning_anchor.model_dump() == persisted["reasoning_anchor"]
    assert streamed.evidence is not None
    assert [item.model_dump(exclude_none=True) for item in streamed.evidence] == persisted["evidence"]
    assert persisted_metadata["provenance_summary"] == "kb"


def test_trace_consistency_preserves_answer_basis_and_structured_evidence_fields() -> None:
    trace = CanonicalTrace(
        kind="tool_result",
        title="知识库命中 1 个证据块",
        status="completed",
        detail="命中证据：商业模式画布",
        decision_code="retrieval_hit",
        answer_basis="knowledge_backed",
        tool_name="knowledge_retrieval",
        result_count=1,
        evidence=[
            TraceEvidenceItem(
                source="knowledge_retrieval",
                label="商业模式画布",
                detail="page=12",
                title="商业模式画布",
                snippet="用于描述价值主张、客户细分和收入来源的结构化工具。",
                source_type="courseware",
                locator="page 12",
                evidence_type="retrieved_chunk",
            )
        ],
    )

    streamed = _canonical_trace_to_sse_data(trace)
    persisted = _canonical_trace_to_entry(trace, step=7)

    assert streamed.answer_basis == "knowledge_backed"
    assert persisted["answer_basis"] == "knowledge_backed"
    assert streamed.evidence is not None
    streamed_evidence = streamed.evidence[0].model_dump(exclude_none=True)
    assert streamed_evidence["title"] == "商业模式画布"
    assert streamed_evidence["snippet"] == "用于描述价值主张、客户细分和收入来源的结构化工具。"
    assert streamed_evidence["source_type"] == "courseware"
    assert streamed_evidence["locator"] == "page 12"
    assert streamed_evidence["evidence_type"] == "retrieved_chunk"
    assert persisted["evidence"][0] == streamed_evidence


def test_retrieval_failure_trace_uses_user_visible_answer_basis_not_raw_internal_label() -> None:
    trace = CanonicalTrace(
        kind="tool_result",
        title="知识库检索失败",
        status="completed",
        detail="知识库检索暂不可用，已切换为直接回答",
        decision_code="retrieval_failed",
        answer_basis="retrieval_unavailable",
        tool_name="knowledge_retrieval",
        result_count=0,
        retrieval_failed=True,
    )

    streamed = _canonical_trace_to_sse_data(trace)
    persisted = _canonical_trace_to_entry(trace, step=8)

    assert streamed.answer_basis == "retrieval_unavailable"
    assert persisted["answer_basis"] == "retrieval_unavailable"
    assert streamed.retrieval_failed is None
    assert "retrieval_failed" not in persisted.get("metadata", {})
    assert str(streamed.model_dump()).find("retrieval_failed': True") == -1
    assert persisted["decision_code"] == "retrieval_unavailable"
    assert persisted["answer_basis"] == "retrieval_unavailable"
