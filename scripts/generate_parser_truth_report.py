"""Generate parser truth-source audit report."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

REPORT_VERSION = "1.0"
TOKENS = (
    "pypdf_text",
    "docx_xml_structured",
    "pptx_xml_structured",
    "_build_group_chunks",
    "_build_table_chunks",
    "_merge_short_chunks",
    "_build_llama_documents",
    "_split_documents",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _scan(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return [{"reason": "TARGET_MISSING", "target": str(path)}]
    text = path.read_text(encoding="utf-8")
    violations: list[dict[str, object]] = []
    for token in TOKENS:
        for line_no, line in enumerate(text.splitlines(), start=1):
            if token in line:
                violations.append({"target": str(path), "token": token, "line": line_no})
                break
    return violations


def _build_report(targets: list[Path]) -> dict[str, object]:
    violations: list[dict[str, object]] = []
    for target in targets:
        violations.extend(_scan(target))
    gate_status = "PASS" if not violations else "FAIL"
    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "parser_truth_gate",
        "gate_status": gate_status,
        "targets": [str(path) for path in targets],
        "legacy_parser_names_found": [v["token"] for v in violations if isinstance(v, dict)],
        "legacy_routes_found": [v for v in violations if isinstance(v, dict)],
        "compat_paths_found": [],
        "llama_chunk_helpers_found": [
            v for v in violations if isinstance(v, dict) and str(v.get("token")).startswith("_build_")
        ],
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    targets = args.target or [Path("app/services/document_processing.py"), Path("app/tasks/ingestion_tasks.py")]
    report = _build_report(targets)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[parser_truth_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
