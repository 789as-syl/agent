"""Check runtime retrieval path does not call question-lane APIs."""

from __future__ import annotations

import argparse
import ast
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPORT_VERSION = "1.0"
FORBIDDEN_RUNTIME_METHODS = {"vector_search", "get_knowledge_point_mapping"}
DEFAULT_ADMIN_GRAPH_PATHS = [
    Path("app/services/admin_analytics_service.py"),
    Path("app/repositories/admin_analytics_repo.py"),
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _find_forbidden_runtime_calls(target: Path) -> list[dict[str, Any]]:
    source = target.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in FORBIDDEN_RUNTIME_METHODS:
            continue

        receiver = ast.unparse(func.value)
        if "question_repo" not in receiver:
            continue

        calls.append(
            {
                "line": getattr(node, "lineno", None),
                "method": func.attr,
                "expression": f"{receiver}.{func.attr}",
            }
        )
    return calls


def _build_report(target: Path, admin_paths: list[Path]) -> dict[str, Any]:
    forbidden_calls_found = _find_forbidden_runtime_calls(target)
    admin_graph_paths_checked = [str(path) for path in admin_paths if path.exists()]

    violations: list[dict[str, Any]] = []
    for missing_path in [path for path in admin_paths if not path.exists()]:
        violations.append(
            {
                "reason": "ADMIN_GRAPH_PATH_MISSING",
                "path": str(missing_path),
            }
        )
    for call in forbidden_calls_found:
        violations.append(
            {
                "reason": "RUNTIME_QUESTION_CALL_FORBIDDEN",
                **call,
            }
        )

    gate_status = "PASS" if not violations else "FAIL"
    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "question_decoupling_gate",
        "gate_status": gate_status,
        "forbidden_calls_found": forbidden_calls_found,
        "admin_graph_paths_checked": admin_graph_paths_checked,
        "violations": violations,
        "target": str(target),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--admin-path", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    admin_paths = args.admin_path if args.admin_path else DEFAULT_ADMIN_GRAPH_PATHS
    report = _build_report(args.target, admin_paths)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[question_decoupling_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
