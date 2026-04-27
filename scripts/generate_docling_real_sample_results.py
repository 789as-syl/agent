"""Generate per-sample real regression results for the Docling hard-cutover sample lock."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from sample_gate_utils import load_structured_file, now_iso, write_json

from app.services.document_processing import build_chunk_bundle, parse_document_artifact


def _run_sample(sample: dict[str, Any]) -> dict[str, Any]:
    sample_id = str(sample.get("sample_id") or "").strip()
    sample_path = Path(str(sample.get("path") or ""))
    category = str(sample.get("category") or "")
    file_type = sample_path.suffix.lower().lstrip(".")

    if category == "blocked_format":
        try:
            parse_document_artifact(str(sample_path), file_type)
        except Exception as exc:
            return {
                "sample_id": sample_id,
                "status": "PASS",
                "passed": True,
                "mode": "blocked_format",
                "detail": str(exc),
            }
        return {
            "sample_id": sample_id,
            "status": "FAIL",
            "passed": False,
            "mode": "blocked_format",
            "detail": "blocked format unexpectedly parsed",
        }

    try:
        document = parse_document_artifact(str(sample_path), file_type)
        bundle = build_chunk_bundle(file_type=file_type, document=document)
    except Exception as exc:
        return {
            "sample_id": sample_id,
            "status": "FAIL",
            "passed": False,
            "mode": "supported_format",
            "detail": str(exc),
        }

    return {
        "sample_id": sample_id,
        "status": "PASS",
        "passed": bool(bundle.chunks),
        "mode": "supported_format",
        "parser_name": document.parser_name,
        "chunk_count": len(bundle.chunks),
        "quality_status": bundle.document_metadata.get("quality_status"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-manifest", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = load_structured_file(args.sample_manifest)
    samples = list(manifest.get("samples") or [])
    args.results_dir.mkdir(parents=True, exist_ok=True)

    for sample in samples:
        result = _run_sample(sample)
        output_path = args.results_dir / f"{result['sample_id']}.json"
        write_json(output_path, {"generated_at": now_iso(), **result})
        print(f"[docling-ws4] {result['status']} -> {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
