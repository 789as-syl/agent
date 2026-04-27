"""Runtime-state assembly from native LangGraph checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.runtime.constants import REQUEST_HUMAN_INPUT_TOOL_NAME
from app.agents.runtime.native_checkpoint import (
    extract_pending_interrupt,
    get_checkpoint_tuple,
    get_legacy_run_checkpoint,
)
from app.models.chat_run import ChatRun
from app.models.enums import RunStatus


@dataclass(slots=True)
class RunResumeSnapshot:
    hitl_pending: bool
    hitl_kind: str | None
    hitl_prompt: str | None
    allowed_actions: list[str]
    resume_supported: bool
    legacy_checkpoint_detected: bool
    reason: str | None
    interrupt_payload: dict[str, Any] | None
    action_name: str | None
    action_args: dict[str, Any]


class RunResumeService:
    """Read minimal runtime status from native checkpoints."""

    async def build_resume_snapshot(self, run: ChatRun) -> RunResumeSnapshot:
        checkpoint_tuple = await get_checkpoint_tuple(thread_id=str(run.conversation_id))
        interrupt_payload = extract_pending_interrupt(checkpoint_tuple)

        hitl_pending = False
        hitl_kind: str | None = None
        hitl_prompt: str | None = None
        allowed_actions: list[str] = []
        action_name: str | None = None
        action_args: dict[str, Any] = {}

        if isinstance(interrupt_payload, dict):
            action_requests = interrupt_payload.get("action_requests")
            review_configs = interrupt_payload.get("review_configs")
            if isinstance(action_requests, list) and action_requests:
                first_action = action_requests[0] or {}
                if isinstance(first_action, dict):
                    action_name = str(first_action.get("name") or "") or None
                    action_args = dict(first_action.get("args") or {})
                    hitl_prompt = (
                        str(first_action.get("description") or action_args.get("prompt") or "").strip() or None
                    )
                    hitl_kind = str(action_args.get("kind") or "input").strip() or "input"
                    hitl_pending = True
            if isinstance(review_configs, list) and review_configs:
                first_review = review_configs[0] or {}
                if isinstance(first_review, dict):
                    raw_actions = [str(item) for item in (first_review.get("allowed_decisions") or [])]
                    allowed_actions = [self._semantic_action(action_name, item) for item in raw_actions]

        resume_supported = True
        legacy_checkpoint_detected = False
        reason: str | None = None
        if checkpoint_tuple is None and run.status in {RunStatus.RUNNING, RunStatus.INTERRUPTED}:
            legacy_checkpoint = await get_legacy_run_checkpoint(run_id=str(run.id))
            if legacy_checkpoint is not None:
                resume_supported = False
                legacy_checkpoint_detected = True
                reason = "thread_key_migrated"
            else:
                resume_supported = False
                legacy_checkpoint_detected = False
                reason = "checkpoint_missing_after_migration"

        return RunResumeSnapshot(
            hitl_pending=hitl_pending,
            hitl_kind=hitl_kind,
            hitl_prompt=hitl_prompt,
            allowed_actions=allowed_actions,
            resume_supported=resume_supported,
            legacy_checkpoint_detected=legacy_checkpoint_detected,
            reason=reason,
            interrupt_payload=interrupt_payload if isinstance(interrupt_payload, dict) else None,
            action_name=action_name,
            action_args=action_args,
        )

    async def build_runtime_state_payload(self, run: ChatRun) -> dict[str, Any]:
        snapshot = await self.build_resume_snapshot(run)
        return {
            "hitl": {
                "pending": snapshot.hitl_pending,
                "kind": snapshot.hitl_kind,
                "prompt": snapshot.hitl_prompt,
                "allowed_actions": snapshot.allowed_actions,
            }
            if snapshot.hitl_pending
            else None,
        }

    @staticmethod
    def _semantic_action(action_name: str | None, action: str) -> str:
        if action_name == REQUEST_HUMAN_INPUT_TOOL_NAME and action == "edit":
            return "respond"
        return action
