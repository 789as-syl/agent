"""B1 Agent/Trace contract tests for replay and durable history boundaries."""

from __future__ import annotations

from app.schemas.sse_event import (
    DoneData,
    ExecutionTraceData,
    FinalAnswerData,
    HITLRequestedData,
    SSEEvent,
)
from app.services.agent_trace_contract import (
    TRUTH_SOURCE_CONTRACT,
    find_durable_history_contract_leaks,
    normalize_sse_event_for_replay,
)


def test_three_truth_source_contract_assigns_distinct_owners() -> None:
    assert "runtime continuation" in TRUTH_SOURCE_CONTRACT["checkpoint"]["owns"]
    assert "Append-only run transcript" in TRUTH_SOURCE_CONTRACT["run_events"]["owns"]
    assert "Final user-visible conversation history" in TRUTH_SOURCE_CONTRACT["messages"]["owns"]
    assert "raw chain-of-thought" in TRUTH_SOURCE_CONTRACT["messages"]["does_not_own"]


def test_normalized_replay_equivalence_ignores_volatile_ids_and_timestamps() -> None:
    left = SSEEvent(
        event_id="volatile-left",
        request_id="run-1",
        conversation_id="conversation-1",
        event_type="execution_trace",
        step=1,
        timestamp="2026-04-26T00:00:00Z",
        trace_data=ExecutionTraceData(
            kind="tool_result",
            title="知识库命中 1 条",
            status="completed",
            semantic_key="tool:knowledge_retrieval:hit",
            metadata={"step_id": "generated-left", "result_count": 1},
        ),
        is_final=False,
    )
    right = left.model_copy(
        update={
            "event_id": "volatile-right",
            "timestamp": "2026-04-26T00:00:01Z",
            "trace_data": ExecutionTraceData(
                kind="tool_result",
                title="知识库命中 1 条",
                status="completed",
                semantic_key="tool:knowledge_retrieval:hit",
                metadata={"step_id": "generated-right", "result_count": 1},
            ),
        }
    )

    assert normalize_sse_event_for_replay(left) == normalize_sse_event_for_replay(right)


def test_normalized_replay_preserves_semantic_terminal_state_and_answer() -> None:
    answer = SSEEvent.create_event(
        event_type="final_answer",
        request_id="run-1",
        conversation_id="conversation-1",
        step=3,
        trace_data=FinalAnswerData(answer="最终答案", content_blocks=None),
    )
    done = SSEEvent.create_event(
        event_type="done",
        request_id="run-1",
        conversation_id="conversation-1",
        step=4,
        trace_data=DoneData(total_steps=4, duration_ms=10, success=True),
        is_final=True,
    )

    normalized_answer = normalize_sse_event_for_replay(answer)
    normalized_done = normalize_sse_event_for_replay(done)

    assert normalized_answer["event_type"] == "final_answer"
    assert normalized_answer["trace_data"]["answer"] == "最终答案"
    assert normalized_done["event_type"] == "done"
    assert normalized_done["trace_data"]["success"] is True
    assert normalized_done["is_final"] is True


def test_normalized_replay_preserves_hitl_prompt_and_allowed_actions() -> None:
    requested = SSEEvent(
        event_id="volatile-hitl-event",
        request_id="run-1",
        conversation_id="conversation-1",
        event_type="hitl_requested",
        step=2,
        timestamp="2026-04-26T00:00:00Z",
        trace_data=HITLRequestedData(
            kind="input",
            prompt="which file?",
            allowed_actions=["respond", "reject"],
        ),
        is_final=False,
    )

    normalized = normalize_sse_event_for_replay(requested)

    assert "event_id" not in normalized
    assert "timestamp" not in normalized
    assert normalized["event_type"] == "hitl_requested"
    assert normalized["trace_data"]["kind"] == "input"
    assert normalized["trace_data"]["prompt"] == "which file?"
    assert normalized["trace_data"]["allowed_actions"] == ["respond", "reject"]


def test_durable_history_contract_flags_raw_cot_and_protocol_leaks() -> None:
    payload = {
        "role": "assistant",
        "content": "自然语言答案",
        "metadata": {
            "execution_trace": [{"title": "工具完成", "metadata": {"tool_name": "knowledge_retrieval"}}],
            "raw_reasoning": "hidden model thought",
        },
        "content_blocks": [
            {"type": "text", "text": "自然语言答案"},
            {"type": "json", "protocol_version": "native-v1", "payload": {"error_code": "X"}},
        ],
    }

    leaks = find_durable_history_contract_leaks(payload)

    assert "metadata.raw_reasoning" in leaks
    assert "content_blocks[1].protocol_version" in leaks
    assert "content_blocks[1].payload" in leaks
    assert "content_blocks[1].payload.error_code" in leaks
