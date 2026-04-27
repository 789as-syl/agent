"""Reindex active knowledge points through the current Docling ingestion pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core.config import get_ingestion_supported_file_types
from app.models.engine import get_celery_session, init_db_engine
from app.models.enums import JobStatus
from app.repositories.ingestion_job_repo import IngestionJobRepository
from app.repositories.knowledge_point_repo import KnowledgePointRepository
from app.tasks.async_runner import run_coroutine_sync
from app.tasks.ingestion_tasks import process_document


async def _list_targets() -> list[dict[str, Any]]:
    async with get_celery_session() as session:
        kp_repo = KnowledgePointRepository(session)
        items, _total = await kp_repo.list_knowledge_points(page=1, page_size=500, include_chunks=False)
        supported = set(get_ingestion_supported_file_types())
        return [
            {
                "id": item.id,
                "title": item.title,
                "file_type": item.file_type,
                "object_path": item.object_path,
            }
            for item in items
            if str(item.file_type).lower() in supported
        ]


async def _create_job(target: dict[str, Any]) -> str:
    async with get_celery_session() as session:
        repo = IngestionJobRepository(session)
        job = await repo.create(
            knowledge_point_id=UUID(str(target["id"])),
            object_path=str(target["object_path"]),
            file_type=str(target["file_type"]),
            status=JobStatus.PENDING,
            progress=0,
        )
        await session.commit()
        return str(job.id)


async def _mark_stale(target: dict[str, Any], error_message: str) -> None:
    async with get_celery_session() as session:
        kp_repo = KnowledgePointRepository(session)
        kp = await kp_repo.get_by_id(UUID(str(target["id"])), include_chunks=False)
        if kp is None:
            return
        metadata = dict(getattr(kp, "document_metadata_json", {}) or {})
        metadata["docling_backfill_status"] = "stale_blocked"
        metadata["docling_backfill_error"] = error_message
        await kp_repo.update(kp.id, is_active=False, document_metadata_json=metadata)
        await session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    init_db_engine()
    targets = run_coroutine_sync(_list_targets())
    results: list[dict[str, Any]] = []
    for target in targets:
        job_id = run_coroutine_sync(_create_job(target))
        try:
            result = process_document.run(job_id)
        except Exception as exc:
            result = {"status": "failed", "error": str(exc)}
            run_coroutine_sync(_mark_stale(target, str(exc)))
        results.append({"job_id": job_id, "knowledge_point_id": str(target["id"]), "title": target["title"], **result})
        print(f"[docling-reindex] {target['title']} -> {result['status']}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[docling-reindex] wrote -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
