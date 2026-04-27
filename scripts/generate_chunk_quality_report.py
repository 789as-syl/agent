"""Generate chunk quality gate report JSON."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_ingestion_supported_file_types
from app.services.document_processing import build_chunk_bundle, parse_document_artifact

REPORT_VERSION = "1.0"
REQUIRED_FIELDS = [
    "parser_name",
    "ocr_used",
    "extracted_char_count",
    "avg_chunk_chars",
    "short_chunk_ratio",
    "duplicate_chunk_ratio",
    "table_block_count",
    "image_block_count",
    "heading_path",
    "block_type",
    "chunker_type",
    "token_count",
    "provenance",
    "quality_status",
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _build_report(input_dir: Path, max_short_ratio: float, max_duplicate_ratio: float) -> dict[str, Any]:
    files = [path for path in input_dir.rglob("*") if path.is_file()] if input_dir.exists() else []
    supported_types = set(get_ingestion_supported_file_types())
    parser_names: list[str] = []
    heading_paths: set[str] = set()
    block_types: set[str] = set()
    chunker_types: set[str] = set()
    provenance_entries: list[dict[str, Any]] = []
    token_total = 0
    processed_samples = 0
    extracted_char_count = 0
    avg_chunk_chars_values: list[int] = []
    short_chunks = 0
    duplicate_chunks = 0
    total_chunks = 0
    table_block_count = 0
    image_block_count = 0
    table_chunks_with_structure = 0
    table_chunks_total = 0
    contextualized_chunks = 0
    missing_fields: set[str] = set()
    violations: list[dict[str, Any]] = []

    for path in files:
        file_type = path.suffix.lower().lstrip(".")
        if file_type not in supported_types:
            continue
        try:
            document = parse_document_artifact(str(path), file_type)
            bundle = build_chunk_bundle(file_type=file_type, document=document)
        except Exception as exc:
            violations.append(
                {
                    "reason": "PARSER_MISSING",
                    "sample": str(path),
                    "error": str(exc),
                    "file_type": file_type,
                }
            )
            continue

        processed_samples += 1
        parser_names.append(document.parser_name)
        extracted_char_count += int(bundle.document_metadata.get("extracted_char_count") or 0)
        table_block_count += int(bundle.document_metadata.get("table_block_count") or 0)
        image_block_count += int(bundle.document_metadata.get("image_block_count") or 0)
        avg_chunk_chars_values.append(int(bundle.document_metadata.get("avg_chunk_chars") or 0))

        for chunk in bundle.chunks:
            metadata = dict(chunk.get("metadata_json") or {})
            total_chunks += 1
            block_types.add(str(metadata.get("block_type") or "unknown"))
            chunker_types.add(str(metadata.get("chunker_type") or "unknown"))
            token_total += int(metadata.get("token_count") or 0)
            heading_path = metadata.get("heading_path") or []
            if isinstance(heading_path, list):
                heading_paths.update(str(item) for item in heading_path if item)
            provenance = metadata.get("provenance") or []
            if isinstance(provenance, list):
                provenance_entries.extend(item for item in provenance if isinstance(item, dict))
            if metadata.get("quality_status") == "short":
                short_chunks += 1
            if metadata.get("quality_status") == "duplicate" or metadata.get("is_duplicate"):
                duplicate_chunks += 1
            if str(metadata.get("contextualized_text") or "").strip():
                contextualized_chunks += 1
            if metadata.get("block_type") == "table":
                table_chunks_total += 1
                if metadata.get("caption") is not None and metadata.get("table_header") and int(metadata.get("table_row_count") or 0) >= 1:
                    table_chunks_with_structure += 1
            for field in ("heading_path", "block_type", "chunker_type", "token_count", "provenance", "quality_status"):
                if field not in metadata:
                    missing_fields.add(field)

        for field in (
            "parser_name",
            "ocr_used",
            "extracted_char_count",
            "avg_chunk_chars",
            "short_chunk_ratio",
            "duplicate_chunk_ratio",
            "table_block_count",
            "image_block_count",
            "quality_status",
        ):
            if field not in bundle.document_metadata:
                missing_fields.add(field)

    short_chunk_ratio = round(short_chunks / max(1, total_chunks), 4) if total_chunks else 0.0
    duplicate_chunk_ratio = round(duplicate_chunks / max(1, total_chunks), 4) if total_chunks else 0.0

    if processed_samples == 0:
        violations.append({"reason": "NO_PARSABLE_SAMPLES"})
    if missing_fields:
        violations.append(
            {"reason": "MISSING_REQUIRED_FIELDS", "missing_fields": sorted(missing_fields)}
        )
    if short_chunk_ratio > max_short_ratio:
        violations.append(
            {
                "reason": "SHORT_CHUNK_RATIO_EXCEEDED",
                "observed": short_chunk_ratio,
                "limit": max_short_ratio,
            }
        )
    if duplicate_chunk_ratio > max_duplicate_ratio:
        violations.append(
            {
                "reason": "DUPLICATE_CHUNK_RATIO_EXCEEDED",
                "observed": duplicate_chunk_ratio,
                "limit": max_duplicate_ratio,
            }
        )
    if table_chunks_total and table_chunks_with_structure != table_chunks_total:
        violations.append(
            {
                "reason": "TABLE_STRUCTURE_DEGRADED",
                "structured_chunks": table_chunks_with_structure,
                "table_chunks_total": table_chunks_total,
            }
        )

    quality_status = "passed" if not violations else "failed"
    gate_status = "PASS" if quality_status == "passed" else "FAIL"
    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "chunk_quality_gate",
        "gate_status": gate_status,
        "required_fields": REQUIRED_FIELDS,
        "parser_name": sorted(set(parser_names)) or ["unknown"],
        "ocr_used": False,
        "extracted_char_count": extracted_char_count,
        "avg_chunk_chars": (
            round(sum(avg_chunk_chars_values) / max(1, len(avg_chunk_chars_values)), 2)
            if avg_chunk_chars_values
            else 0.0
        ),
        "short_chunk_ratio": short_chunk_ratio,
        "duplicate_chunk_ratio": duplicate_chunk_ratio,
        "table_block_count": table_block_count,
        "image_block_count": image_block_count,
        "heading_path": sorted(heading_paths) or ["root"],
        "block_type": sorted(block_types) or ["unknown"],
        "chunker_type": sorted(chunker_types) or ["unknown"],
        "token_count": token_total,
        "provenance": {"input_dir": str(input_dir), "sample_count": len(files), "processed_samples": processed_samples},
        "table_structure_preserved": table_chunks_with_structure == table_chunks_total,
        "contextualized_text_present_ratio": round(contextualized_chunks / max(1, total_chunks), 4),
        "chunk_count": total_chunks,
        "quality_status": quality_status,
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data_example"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-short-ratio", type=float, default=0.40)
    parser.add_argument("--max-duplicate-ratio", type=float, default=0.20)
    args = parser.parse_args()

    report = _build_report(args.input_dir, args.max_short_ratio, args.max_duplicate_ratio)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[chunk_quality_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
