"""Generate blocked-format contract audit report."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_ingestion_supported_file_types
from app.core.file_types import normalize_file_type
from app.tasks.ingestion_tasks import SAFE_FILE_EXTENSIONS

REPORT_VERSION = "1.0"
BLOCKED_FORMATS = ("doc", "ppt")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _layer_checks() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rejected_layers: list[dict[str, object]] = []
    unexpected_acceptance: list[dict[str, object]] = []
    supported = set(get_ingestion_supported_file_types())

    for file_type in BLOCKED_FORMATS:
        try:
            normalize_file_type(file_type)
            unexpected_acceptance.append({"layer": "normalize_file_type", "file_type": file_type})
        except ValueError:
            rejected_layers.append({"layer": "normalize_file_type", "file_type": file_type})

        if file_type in supported:
            unexpected_acceptance.append({"layer": "settings.allowed_file_types", "file_type": file_type})
        else:
            rejected_layers.append({"layer": "settings.allowed_file_types", "file_type": file_type})

        if file_type in SAFE_FILE_EXTENSIONS:
            unexpected_acceptance.append({"layer": "ingestion_task_safe_extensions", "file_type": file_type})
        else:
            rejected_layers.append({"layer": "ingestion_task_safe_extensions", "file_type": file_type})

    return rejected_layers, unexpected_acceptance


def _build_report() -> dict[str, object]:
    rejected_layers, unexpected_acceptance = _layer_checks()
    gate_status = "PASS" if not unexpected_acceptance else "FAIL"
    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "blocked_format_contract_gate",
        "gate_status": gate_status,
        "blocked_formats": list(BLOCKED_FORMATS),
        "rejected_layers": rejected_layers,
        "unexpected_acceptance": unexpected_acceptance,
        "error_codes": {
            "invalid_type": "INGESTION_INVALID_FILE_TYPE",
            "parser_unavailable": "INGESTION_PARSER_UNAVAILABLE",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = _build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[blocked_format_contract_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
