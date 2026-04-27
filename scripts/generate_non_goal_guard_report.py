"""Generate non-goal guard gate report JSON."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from app.repositories.question_repo import compute_embedding_text_hash
from app.tasks import vectorization_tasks

REPORT_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _build_report() -> dict[str, Any]:
    violations: list[dict[str, Any]] = []

    clean_text = "语义未变化的题目"
    clean_case = SimpleNamespace(
        id=uuid4(),
        question_text=clean_text,
        question_embedding=[0.1, 0.2],
        embedding_text_hash=compute_embedding_text_hash(clean_text),
        is_dirty=False,
    )
    if vectorization_tasks._question_needs_vectorization(clean_case):
        violations.append(
            {
                "reason": "CLEAN_QUESTION_SHOULD_NOT_REVECTORIZE",
                "case": "clean_case",
            }
        )

    dirty_case = SimpleNamespace(
        id=uuid4(),
        question_text="脏数据题目",
        question_embedding=[0.3, 0.4],
        embedding_text_hash=compute_embedding_text_hash("脏数据题目"),
        is_dirty=True,
    )
    if not vectorization_tasks._question_needs_vectorization(dirty_case):
        violations.append(
            {
                "reason": "DIRTY_QUESTION_MUST_VECTORIZE",
                "case": "dirty_case",
            }
        )

    stale_hash_case = SimpleNamespace(
        id=uuid4(),
        question_text="hash 不匹配",
        question_embedding=[0.5, 0.6],
        embedding_text_hash="stale-hash",
        is_dirty=False,
    )
    if not vectorization_tasks._question_needs_vectorization(stale_hash_case):
        violations.append(
            {
                "reason": "STALE_HASH_MUST_VECTORIZE",
                "case": "stale_hash_case",
            }
        )

    semantics_changed = bool(violations)
    gate_status = "FAIL" if semantics_changed else "PASS"
    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "non_goal_guard_gate",
        "gate_status": gate_status,
        "question_vectorization_semantics_changed": semantics_changed,
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = _build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[non_goal_guard_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
