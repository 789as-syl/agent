"""????: knowledge_point_repo?"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.knowledge_point import KnowledgePoint, KnowledgePointChunk


class KnowledgePointRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs: Any) -> KnowledgePoint:
        kp = KnowledgePoint(**kwargs)
        self.session.add(kp)
        await self.session.flush()
        await self.session.refresh(kp)
        return kp

    async def get_active_by_object_path(self, object_path: str) -> KnowledgePoint | None:
        result = await self.session.execute(
            select(KnowledgePoint).where(
                KnowledgePoint.object_path == object_path,
                KnowledgePoint.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, kp_id: uuid.UUID, include_chunks: bool = True) -> KnowledgePoint | None:
        stmt = select(KnowledgePoint).where(KnowledgePoint.id == kp_id)
        if include_chunks:
            stmt = stmt.options(selectinload(KnowledgePoint.chunks)).execution_options(populate_existing=True)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_knowledge_points(
        self,
        page: int = 1,
        page_size: int = 20,
        q: str | None = None,
        include_chunks: bool = False,
    ) -> tuple[list[KnowledgePoint], int]:
        stmt = select(KnowledgePoint).where(KnowledgePoint.is_active.is_(True))
        count_stmt = select(func.count()).select_from(KnowledgePoint).where(KnowledgePoint.is_active.is_(True))

        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(KnowledgePoint.title.ilike(pattern))
            count_stmt = count_stmt.where(KnowledgePoint.title.ilike(pattern))

        if include_chunks:
            stmt = stmt.options(selectinload(KnowledgePoint.chunks)).execution_options(populate_existing=True)

        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        stmt = stmt.order_by(KnowledgePoint.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

        items = list((await self.session.execute(stmt)).scalars().all())
        return items, total

    async def get_by_titles(self, titles: list[str]) -> list[KnowledgePoint]:
        if not titles:
            return []
        result = await self.session.execute(select(KnowledgePoint).where(KnowledgePoint.title.in_(titles)))
        return list(result.scalars().all())

    async def count_vectorized_chunks(self) -> int:
        stmt = (
            select(func.count())
            .select_from(KnowledgePointChunk)
            .join(KnowledgePoint, KnowledgePoint.id == KnowledgePointChunk.knowledge_point_id)
            .where(
                KnowledgePoint.is_active.is_(True),
                KnowledgePointChunk.embedding.is_not(None),
            )
        )
        return int((await self.session.execute(stmt)).scalar() or 0)

    async def count_chunks_by_kp_id(self, kp_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(KnowledgePointChunk)
            .where(KnowledgePointChunk.knowledge_point_id == kp_id)
        )
        return int(result.scalar() or 0)

    async def get_by_ids(self, kp_ids: list[uuid.UUID]) -> list[KnowledgePoint]:
        if not kp_ids:
            return []
        result = await self.session.execute(select(KnowledgePoint).where(KnowledgePoint.id.in_(kp_ids)))
        return list(result.scalars().all())

    async def get_chunks_by_knowledge_point_ids(
        self,
        kp_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[KnowledgePointChunk]]:
        if not kp_ids:
            return {}
        stmt = (
            select(KnowledgePointChunk)
            .where(KnowledgePointChunk.knowledge_point_id.in_(kp_ids))
            .order_by(KnowledgePointChunk.knowledge_point_id, KnowledgePointChunk.chunk_index)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        mapping: dict[uuid.UUID, list[KnowledgePointChunk]] = {kp_id: [] for kp_id in kp_ids}
        for row in rows:
            mapping.setdefault(row.knowledge_point_id, []).append(row)
        return mapping

    async def update(self, kp_id: uuid.UUID, **kwargs: Any) -> KnowledgePoint | None:
        kp = await self.get_by_id(kp_id)
        if not kp:
            return None

        for key, value in kwargs.items():
            if hasattr(kp, key):
                setattr(kp, key, value)

        self.session.add(kp)
        await self.session.flush()
        await self.session.refresh(kp)
        return kp

    async def delete(self, kp_id: uuid.UUID) -> bool:
        result = await self.session.execute(delete(KnowledgePoint).where(KnowledgePoint.id == kp_id))
        await self.session.flush()
        return bool(getattr(result, "rowcount", 0))

    async def create_chunks(self, kp_id: uuid.UUID, chunks_data: list[dict[str, Any]]) -> list[KnowledgePointChunk]:
        chunks = [KnowledgePointChunk(knowledge_point_id=kp_id, **data) for data in chunks_data]
        self.session.add_all(chunks)
        await self.session.flush()
        return chunks

    async def delete_chunks_by_kp_id(self, kp_id: uuid.UUID) -> int:
        result = await self.session.execute(
            delete(KnowledgePointChunk).where(KnowledgePointChunk.knowledge_point_id == kp_id)
        )
        await self.session.flush()
        return int(getattr(result, "rowcount", 0) or 0)

    async def vector_search(
        self,
        embedding: list[float],
        top_k: int = 10,
        similarity_threshold: float = 0.7,
        update_retrieval_count: bool = True,
    ) -> list[dict[str, Any]]:
        if not embedding:
            return []
        embedding_str = f"[{','.join(map(str, embedding))}]"
        max_distance = max(0.0, 1 - float(similarity_threshold))

        stmt = text(
            """
            WITH matched AS (
                SELECT
                    kc.id AS chunk_id,
                    kc.knowledge_point_id,
                    kc.chunk_index,
                    kc.content AS chunk_content,
                    kc.metadata_json,
                    kp.id AS kp_id,
                    kp.title AS kp_title,
                    kc.embedding <=> CAST(:embedding AS vector) AS distance,
                    1 - (kc.embedding <=> CAST(:embedding AS vector)) AS similarity
                FROM knowledge_point_chunks kc
                JOIN knowledge_points kp ON kc.knowledge_point_id = kp.id
                WHERE kp.is_active = TRUE
                  AND kc.embedding IS NOT NULL
                  AND kc.embedding <=> CAST(:embedding AS vector) <= :max_distance
                ORDER BY kc.embedding <=> CAST(:embedding AS vector)
                LIMIT :top_k
            )
            SELECT * FROM matched
            """
        )

        rows = (
            await self.session.execute(
                stmt,
                {
                    "embedding": embedding_str,
                    "top_k": top_k,
                    "max_distance": max_distance,
                },
            )
        ).fetchall()

        results: list[dict[str, Any]] = []
        chunk_ids: list[uuid.UUID] = []
        for row in rows:
            results.append(
                {
                    "chunk_id": row.chunk_id,
                    "knowledge_point_id": row.kp_id,
                    "chunk_index": row.chunk_index,
                    "chunk_content": row.chunk_content,
                    "metadata_json": row.metadata_json,
                    "knowledge_point_title": row.kp_title,
                    "similarity": float(row.similarity),
                }
            )
            if update_retrieval_count:
                chunk_ids.append(row.chunk_id)

        if update_retrieval_count and chunk_ids:
            await self._increment_retrieval_counts(chunk_ids)

        return results

    async def keyword_search(
        self,
        query: str,
        top_k: int = 10,
        update_retrieval_count: bool = True,
    ) -> list[dict[str, Any]]:
        stmt = text(
            """
            SELECT
                kc.id AS chunk_id,
                kc.knowledge_point_id,
                kc.chunk_index,
                kc.content AS chunk_content,
                kc.metadata_json,
                kp.id AS kp_id,
                kp.title AS kp_title,
                paradedb.score(kc.id) AS score
            FROM knowledge_point_chunks kc
            JOIN knowledge_points kp ON kc.knowledge_point_id = kp.id
            WHERE kc.id @@@ :query
              AND kp.is_active = TRUE
            ORDER BY score DESC
            LIMIT :top_k
            """
        )

        rows = (await self.session.execute(stmt, {"query": query, "top_k": top_k})).fetchall()

        results: list[dict[str, Any]] = []
        chunk_ids: list[uuid.UUID] = []
        for row in rows:
            results.append(
                {
                    "chunk_id": row.chunk_id,
                    "knowledge_point_id": row.knowledge_point_id,
                    "chunk_index": row.chunk_index,
                    "chunk_content": row.chunk_content,
                    "metadata_json": row.metadata_json,
                    "knowledge_point_title": row.kp_title,
                    "score": float(row.score),
                    "similarity": None,
                }
            )
            if update_retrieval_count:
                chunk_ids.append(row.chunk_id)

        if update_retrieval_count and chunk_ids:
            await self._increment_retrieval_counts(chunk_ids)

        return results

    async def _increment_retrieval_counts(self, chunk_ids: list[uuid.UUID]) -> None:
        if not chunk_ids:
            return

        await self.session.execute(
            update(KnowledgePointChunk)
            .where(KnowledgePointChunk.id.in_(chunk_ids))
            .values(retrieval_count=KnowledgePointChunk.retrieval_count + 1)
        )

        kp_ids = [
            row[0]
            for row in (
                await self.session.execute(
                    select(KnowledgePointChunk.knowledge_point_id)
                    .where(KnowledgePointChunk.id.in_(chunk_ids))
                    .distinct()
                )
            ).fetchall()
        ]

        if kp_ids:
            await self.session.execute(
                update(KnowledgePoint)
                .where(KnowledgePoint.id.in_(kp_ids))
                .values(retrieval_count=KnowledgePoint.retrieval_count + 1)
            )

        await self.session.flush()

    async def increment_retrieval_counts(self, chunk_ids: list[uuid.UUID]) -> None:
        """Public wrapper for retrieval_count accumulation."""
        await self._increment_retrieval_counts(chunk_ids)
