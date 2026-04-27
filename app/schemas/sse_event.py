"""Schema模块: sse_event。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "execution_trace",
    "reasoning_delta",
    "hitl_requested",
    "hitl_resolved",
    "generation_delta",
    "final_answer",
    "error",
    "done",
]


class TraceRange(BaseModel):
    start: int = Field(..., ge=0, description="起始字符偏移")
    end: int = Field(..., ge=0, description="结束字符偏移")


class TraceEvidence(BaseModel):
    source: str = Field(..., description="证据来源，例如 classifier/reasoning/tool_result")
    label: str = Field(..., description="简短证据标签")
    detail: str | None = Field(default=None, description="补充证据说明")
    event_id: str | None = Field(default=None, description="关联事件 ID")
    reasoning_range: TraceRange | None = Field(default=None, description="关联 reasoning 区间")


class ExecutionTraceData(BaseModel):
    kind: str = Field(..., description="执行轨迹节点类型")
    title: str = Field(..., description="轨迹节点标题")
    detail: str | None = Field(default=None, description="可选详细信息")
    status: str | None = Field(default=None, description="pending/running/completed/error")
    decision_code: str | None = Field(default=None, description="决策/步骤编码")
    tool_name: str | None = Field(default=None, description="工具名称")
    tool_input: dict[str, Any] | None = Field(default=None, description="工具输入摘要")
    result_summary: str | None = Field(default=None, description="兼容旧版本的结果摘要别名")
    result_count: int | None = Field(default=None, description="结果数量")
    retrieval_failed: bool | None = Field(default=None, description="检索是否失败")
    semantic_key: str | None = Field(default=None, description="稳定语义键，用于实时与历史 trace 去重")
    evidence: list[TraceEvidence] | None = Field(default=None, description="用于支撑该步骤的证据列表")
    reasoning_anchor: TraceRange | None = Field(default=None, description="关联的 reasoning 区间")
    metadata: dict[str, Any] | None = Field(default=None, description="补充元数据")


class HITLRequestedData(BaseModel):
    kind: str = Field(..., description="HITL 节点类型，如 input/confirm/edit")
    prompt: str = Field(..., description="向前端展示的人类输入/确认提示")
    allowed_actions: list[str] = Field(default_factory=list, description="允许的人类决策动作")


class HITLResolvedData(BaseModel):
    kind: str | None = Field(default=None, description="HITL 节点类型")


class GenerationDeltaData(BaseModel):
    delta: str = Field(..., description="本次推送的文本增量")
    accumulated: str | None = Field(default=None, description="截至目前的累积文本")
    content_blocks: list[dict[str, Any]] | None = Field(default=None, description="可选的当前内容块")


class ReasoningDeltaData(BaseModel):
    delta: str = Field(..., description="本次推送的 reasoning 文本增量")
    accumulated: str | None = Field(default=None, description="截至目前的累积 reasoning 文本")
    source: str | None = Field(default=None, description="reasoning 来源字段，如 reasoning_content")
    truncated: bool = Field(default=False, description="是否已因为预算限制截断")


class FinalAnswerData(BaseModel):
    answer: str = Field(..., description="最终答案文本")
    content_blocks: list[dict[str, Any]] | None = Field(default=None, description="最终答案的标准 content blocks")


class ErrorData(BaseModel):
    error_code: str = Field(..., description="错误码")
    error_message: str = Field(..., description="人类可读的错误描述")
    recoverable: bool = Field(default=False, description="是否可恢复")


class DoneData(BaseModel):
    total_steps: int = Field(..., description="总步数")
    duration_ms: int = Field(..., description="总耗时（毫秒）")
    success: bool = Field(default=True, description="是否成功完成")


TraceData = (
    ExecutionTraceData
    | ReasoningDeltaData
    | HITLRequestedData
    | HITLResolvedData
    | GenerationDeltaData
    | FinalAnswerData
    | ErrorData
    | DoneData
)


class SSEEvent(BaseModel):
    event_id: str = Field(..., description="事件唯一标识 UUID")
    request_id: str = Field(..., description="请求 ID")
    conversation_id: str = Field(..., description="所属会话 ID")
    event_type: EventType = Field(..., description="事件类型")
    step: int = Field(..., description="当前步数")
    timestamp: str = Field(..., description="ISO 8601 UTC 时间戳")
    trace_data: TraceData = Field(..., description="事件负载")
    is_final: bool = Field(default=False, description="是否为终态事件")

    @staticmethod
    def create_event(
        event_type: EventType,
        request_id: str,
        conversation_id: str,
        step: int,
        trace_data: TraceData,
        is_final: bool = False,
    ) -> SSEEvent:
        import uuid

        return SSEEvent(
            event_id=str(uuid.uuid4()),
            request_id=request_id,
            conversation_id=conversation_id,
            event_type=event_type,
            step=step,
            timestamp=datetime.now(UTC).isoformat(),
            trace_data=trace_data,
            is_final=is_final,
        )

    def to_sse_format(self, *, include_id: bool = True) -> str:
        import json

        lines = [f"event: {self.event_type}"]
        if include_id:
            lines.append(f"id: {self.event_id}")
        lines.append(f"data: {json.dumps(self.model_dump(mode='json'), ensure_ascii=False)}")
        lines.append("")
        return "\n".join(lines) + "\n"
