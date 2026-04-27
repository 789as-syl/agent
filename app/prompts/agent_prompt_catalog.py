"""Minimal prompt helpers still needed after the native-only cutover."""

from __future__ import annotations


def build_memory_summary_prompt(*, old_summary: str, formatted_new_messages: str) -> str:
    return (
        "你是对话记忆压缩助手。\n"
        "请基于历史摘要与新增消息，生成更新后的精炼摘要。\n\n"
        "【保留内容】事实信息、用户偏好、关键约束、未完成任务。\n"
        "【删除内容】寒暄、重复表达、无关细节。\n\n"
        f"历史摘要:\n{old_summary or '(无)'}\n\n"
        f"新增消息:\n{formatted_new_messages}\n\n"
        "仅输出纯文本摘要，不要输出 JSON 或额外说明。"
    )


__all__ = ["build_memory_summary_prompt"]
