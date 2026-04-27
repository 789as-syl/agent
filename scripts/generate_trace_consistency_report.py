"""Generate trace consistency gate report JSON."""

from __future__ import annotations

import argparse
import ast
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPORT_VERSION = "1.0"
DEFAULT_TARGET = Path("app/agents/native_agent_runner.py")
CHECKED_FIELDS = [
    "kind",
    "title",
    "status",
    "detail",
    "decision_code",
    "tool_name",
    "tool_input",
    "result_count",
    "retrieval_failed",
    "evidence",
    "reasoning_anchor",
]
_RUNTIME_IMPORT_ERROR: str | None = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _collect_sse_fields(function_node: ast.FunctionDef) -> set[str]:
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Return):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        return {keyword.arg for keyword in node.value.keywords if keyword.arg}
    return set()


def _collect_entry_fields(function_node: ast.FunctionDef) -> tuple[set[str], set[str]]:
    payload_fields: set[str] = set()
    metadata_fields: set[str] = set()

    for node in ast.walk(function_node):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "payload"
            and isinstance(node.value, ast.Dict)
        ):
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    payload_fields.add(key.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "payload"
            and isinstance(node.value, ast.Dict)
        ):
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    payload_fields.add(key.value)

        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Subscript)
            and isinstance(node.targets[0].value, ast.Name)
            and isinstance(node.targets[0].slice, ast.Constant)
            and isinstance(node.targets[0].slice.value, str)
        ):
            container = node.targets[0].value.id
            field_name = node.targets[0].slice.value
            if container == "payload":
                payload_fields.add(field_name)
            if container == "merged_metadata":
                metadata_fields.add(field_name)

    return payload_fields, metadata_fields


def _build_report_from_source(target: Path) -> dict[str, Any]:
    source = target.read_text(encoding="utf-8")
    tree = ast.parse(source)

    sse_fn = None
    entry_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_canonical_trace_to_sse_data":
            sse_fn = node
        if isinstance(node, ast.FunctionDef) and node.name == "_canonical_trace_to_entry":
            entry_fn = node

    if sse_fn is None or entry_fn is None:
        return {
            "report_version": REPORT_VERSION,
            "generated_at": _now_iso(),
            "gate_name": "trace_consistency_gate",
            "gate_status": "FAIL",
            "checked_fields": CHECKED_FIELDS,
            "mismatches": [{"field": "function_lookup", "reason": "TRACE_FUNCTION_NOT_FOUND"}],
            "source_mode": "ast",
            "target": str(target),
        }

    sse_fields = _collect_sse_fields(sse_fn)
    entry_fields, entry_metadata_fields = _collect_entry_fields(entry_fn)
    mapping = {
        "kind": ("kind", "kind"),
        "title": ("title", "title"),
        "status": ("status", "status"),
        "detail": ("detail", "detail"),
        "decision_code": ("decision_code", "decision_code"),
        "tool_name": ("tool_name", "metadata.tool_name"),
        "tool_input": ("tool_input", "metadata.tool_input"),
        "result_count": ("result_count", "metadata.result_count"),
        "retrieval_failed": ("retrieval_failed", "metadata.retrieval_failed"),
        "evidence": ("evidence", "evidence"),
        "reasoning_anchor": ("reasoning_anchor", "reasoning_anchor"),
    }

    mismatches: list[dict[str, Any]] = []
    for field, (sse_field, entry_field) in mapping.items():
        sse_present = sse_field in sse_fields
        if entry_field.startswith("metadata."):
            entry_present = entry_field.split(".", 1)[1] in entry_metadata_fields
        else:
            entry_present = entry_field in entry_fields
        if not (sse_present and entry_present):
            mismatches.append(
                {
                    "field": field,
                    "sse_present": sse_present,
                    "entry_present": entry_present,
                }
            )

    gate_status = "PASS" if not mismatches else "FAIL"
    report: dict[str, Any] = {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "trace_consistency_gate",
        "gate_status": gate_status,
        "checked_fields": CHECKED_FIELDS,
        "mismatches": mismatches,
        "source_mode": "ast",
        "target": str(target),
    }
    if _RUNTIME_IMPORT_ERROR:
        report["runtime_import_error"] = _RUNTIME_IMPORT_ERROR
    return report


def _try_runtime_report() -> dict[str, Any] | None:
    global _RUNTIME_IMPORT_ERROR
    try:
        from app.agents.native_agent_runner import (
            CanonicalTrace,
            TraceAnchor,
            TraceEvidenceItem,
            _canonical_trace_to_entry,
            _canonical_trace_to_sse_data,
        )
    except Exception as exc:
        _RUNTIME_IMPORT_ERROR = str(exc)
        return None

    trace = CanonicalTrace(
        kind="tool_result",
        title="知识库命中 2 条证据",
        status="completed",
        detail="命中证据: 商业模式画布; MVP",
        decision_code="retrieval_hit",
        tool_name="knowledge_retrieval",
        tool_input={"query": "商业模式画布"},
        result_count=2,
        retrieval_failed=False,
        evidence=[
            TraceEvidenceItem(source="classifier", label="命中问题信号", detail="商业模式"),
        ],
        reasoning_anchor=TraceAnchor(start=5, end=11),
        metadata={"payload": {"tool": "knowledge_retrieval"}},
    )
    streamed = _canonical_trace_to_sse_data(trace)
    persisted = _canonical_trace_to_entry(trace, step=3)
    streamed_evidence = [item.model_dump(exclude_none=True) for item in streamed.evidence or []]
    persisted_evidence = persisted.get("evidence", [])
    streamed_anchor = streamed.reasoning_anchor.model_dump() if streamed.reasoning_anchor else None
    persisted_anchor = persisted.get("reasoning_anchor")

    comparisons = {
        "kind": (streamed.kind, persisted.get("kind")),
        "title": (streamed.title, persisted.get("title")),
        "status": (streamed.status, persisted.get("status")),
        "detail": (streamed.detail, persisted.get("detail")),
        "decision_code": (streamed.decision_code, persisted.get("decision_code")),
        "tool_name": (streamed.tool_name, (persisted.get("metadata") or {}).get("tool_name")),
        "tool_input": (streamed.tool_input, (persisted.get("metadata") or {}).get("tool_input")),
        "result_count": (streamed.result_count, (persisted.get("metadata") or {}).get("result_count")),
        "retrieval_failed": (streamed.retrieval_failed, (persisted.get("metadata") or {}).get("retrieval_failed")),
        "evidence": (streamed_evidence, persisted_evidence),
        "reasoning_anchor": (streamed_anchor, persisted_anchor),
    }
    mismatches = [
        {"field": key, "streamed": streamed_value, "persisted": persisted_value}
        for key, (streamed_value, persisted_value) in comparisons.items()
        if streamed_value != persisted_value
    ]

    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "trace_consistency_gate",
        "gate_status": "PASS" if not mismatches else "FAIL",
        "checked_fields": CHECKED_FIELDS,
        "mismatches": mismatches,
        "source_mode": "runtime",
    }


def _build_report(target: Path) -> dict[str, Any]:
    runtime_report = _try_runtime_report()
    if runtime_report is not None:
        return runtime_report
    return _build_report_from_source(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = _build_report(args.target)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[trace_consistency_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
