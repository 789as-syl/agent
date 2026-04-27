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
