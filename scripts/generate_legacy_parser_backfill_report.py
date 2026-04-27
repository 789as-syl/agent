"""Generate legacy-parser backfill report from current database state."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

REPORT_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


async def _collect() -> dict[str, Any]:
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            legacy_chunk_rows = (
                await conn.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM knowledge_point_chunks
                        JOIN knowledge_points ON knowledge_points.id = knowledge_point_chunks.knowledge_point_id
                        WHERE knowledge_points.is_active = TRUE
                          AND (
                               COALESCE(metadata_json->>'parser_name', '') = ''
                            OR metadata_json->>'parser_name' NOT LIKE 'upstream_docling:%'
                            OR COALESCE(metadata_json->>'docling_group_id', '') = ''
                          )
                        """
                    )
                )
            ).scalar_one()
            legacy_doc_rows = (
                await conn.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM knowledge_points
                        WHERE is_active = TRUE
                          AND (
                               COALESCE(document_metadata_json->'truth_signature'->'parser'->>'name', '') = ''
                            OR document_metadata_json->'truth_signature'->'parser'->>'name' NOT LIKE 'upstream_docling:%'
                            OR document_metadata_json->'docling_artifact'->>'object_path' IS NULL
                          )
                        """
                    )
                )
            ).scalar_one()
            stale_rows_blocked = (
                await conn.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM knowledge_points
                        WHERE is_active = FALSE
                          AND document_metadata_json->>'docling_backfill_status' = 'stale_blocked'
                        """
                    )
                )
            ).scalar_one()
            recent_success = (
                await conn.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM ingestion_jobs
                        WHERE status = 'SUCCESS'
                          AND created_at >= now() - interval '1 day'
                        """
                    )
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    violations: list[dict[str, Any]] = []
    if int(legacy_chunk_rows or 0) > 0:
        violations.append({"reason": "LEGACY_CHUNK_ROWS_REMAIN", "count": int(legacy_chunk_rows)})
    if int(legacy_doc_rows or 0) > 0:
        violations.append({"reason": "LEGACY_DOCUMENT_METADATA_REMAIN", "count": int(legacy_doc_rows)})
    return {
        "legacy_rows_remaining": int(legacy_chunk_rows or 0) + int(legacy_doc_rows or 0),
        "reindexed_rows": int(recent_success or 0),
        "stale_rows_blocked": int(stale_rows_blocked or 0),
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = asyncio.run(_collect())
    report = {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "legacy_parser_backfill_gate",
        "gate_status": "PASS" if not payload["violations"] else "FAIL",
        **payload,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[legacy_parser_backfill_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
