"""Repository helpers for admin dashboard analytics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

from sqlalchemy import and_, case, func, select, text
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_point import KnowledgePoint
from app.models.question_bank import Question
from app.models.question_knowledge_point import QuestionKnowledgePoint
from app.models.retrieval_log import RetrievalLog

RANGE_TO_DAYS: dict[str, int] = {"1d": 1, "7d": 7, "30d": 30}
QuestionRow = Row[tuple[uuid.UUID, str]]
DASHBOARD_BREAKDOWN_LABELS: dict[str, str] = {
    "direct_only": "直接命中",
    "mapped_only": "映射命中",
    "hybrid": "混合命中",
    "empty": "未命中",
}


class KnowledgePointGraphItem(TypedDict):
    knowledge_point_id: str
    title: str
    hit_count: int


def resolve_dashboard_breakdown_label(key: str, label: str | None = None) -> str:
    fallback = DASHBOARD_BREAKDOWN_LABELS.get(key, key)
    normalized = (label or "").strip()
    if not normalized or set(normalized) == {"?"}:
        return fallback
    return normalized


def normalize_dashboard_breakdown_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **item,
            "label": resolve_dashboard_breakdown_label(
                str(item.get("key") or ""),
                item.get("label") if isinstance(item.get("label"), str) else None,
            ),
        }
        for item in items
    ]


def range_to_since(value: str) -> datetime:
    """Convert a dashboard range selector into a UTC lower-bound timestamp."""
    days = RANGE_TO_DAYS.get(value, 7)
    return datetime.now(UTC) - timedelta(days=days)


class AdminAnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._has_evidence_sidecar_columns: bool | None = None

    @staticmethod
    def _anchor_kp_ids_expr(*, use_evidence_sidecar: bool) -> Any:
        if not use_evidence_sidecar:
            return RetrievalLog.direct_hit_kp_ids
        return func.coalesce(RetrievalLog.anchor_kp_ids, RetrievalLog.direct_hit_kp_ids)

    @staticmethod
    def _expanded_kp_ids_expr(*, use_evidence_sidecar: bool) -> Any:
        if not use_evidence_sidecar:
            return RetrievalLog.mapped_kp_ids
        return func.coalesce(RetrievalLog.expanded_kp_ids_non_anchor, RetrievalLog.mapped_kp_ids)

    @staticmethod
    def _final_kp_ids_expr(*, use_evidence_sidecar: bool) -> Any:
        if not use_evidence_sidecar:
            return RetrievalLog.final_kp_ids
        return func.coalesce(RetrievalLog.final_evidence_kp_ids, RetrievalLog.final_kp_ids)

    @staticmethod
    def _final_kp_ids_sql(*, use_evidence_sidecar: bool, table_alias: str | None = None) -> str:
        prefix = f"{table_alias}." if table_alias else ""
        if use_evidence_sidecar:
            return f"coalesce({prefix}final_evidence_kp_ids, {prefix}final_kp_ids)"
        return f"{prefix}final_kp_ids"

    async def _supports_evidence_sidecar(self) -> bool:
        if self._has_evidence_sidecar_columns is not None:
            return self._has_evidence_sidecar_columns

        stmt = text(
            """
            SELECT count(*)::int AS count
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'retrieval_logs'
              AND column_name IN (
                'anchor_kp_ids',
                'expanded_kp_ids_non_anchor',
                'final_evidence_kp_ids'
              )
            """
        )
        count = int((await self.session.execute(stmt)).scalar() or 0)
        self._has_evidence_sidecar_columns = count == 3
        return self._has_evidence_sidecar_columns

    async def get_dashboard_metrics(self, since: datetime) -> dict[str, Any]:
        use_evidence_sidecar = await self._supports_evidence_sidecar()
        final_count = func.coalesce(
            func.cardinality(self._final_kp_ids_expr(use_evidence_sidecar=use_evidence_sidecar)),
            0,
        )
        hit_expr = case((final_count > 0, 1), else_=0)

        stmt = select(
            func.count(RetrievalLog.id).label("request_count"),
            func.coalesce(func.avg(RetrievalLog.duration_ms), 0).label("avg_latency_ms"),
            func.coalesce(func.sum(hit_expr), 0).label("hit_count"),
        ).where(RetrievalLog.created_at >= since)
        row = (await self.session.execute(stmt)).one()

        document_count = int(
            (
                await self.session.execute(
                    select(func.count(KnowledgePoint.id)).where(KnowledgePoint.is_active.is_(True))
                )
            ).scalar()
            or 0
        )

        request_count = int(row.request_count or 0)
        hit_count = int(row.hit_count or 0)
        hit_rate = (hit_count / request_count * 100) if request_count else 0

        return {
            "request_count": request_count,
            "hit_rate": round(hit_rate, 2),
            "avg_latency_ms": round(float(row.avg_latency_ms or 0), 2),
            "document_count": document_count,
        }

    async def get_dashboard_trends(self, since: datetime, range_value: str) -> list[dict[str, Any]]:
        use_evidence_sidecar = await self._supports_evidence_sidecar()
        bucket_unit = "hour" if range_value == "1d" else "day"
        bucket_format = "MM-DD HH24:00" if range_value == "1d" else "MM-DD"
        final_ids_sql = self._final_kp_ids_sql(use_evidence_sidecar=use_evidence_sidecar)
        sql = text(
            f"""
            SELECT
                to_char(date_trunc('{bucket_unit}', created_at), '{bucket_format}') AS bucket,
                count(*)::int AS request_count,
                sum(
                    CASE
                        WHEN coalesce(cardinality({final_ids_sql}), 0) > 0
                        THEN 1
                        ELSE 0
                    END
                )::int AS hit_count,
                coalesce(avg(duration_ms), 0)::float AS avg_latency_ms
            FROM retrieval_logs
            WHERE created_at >= :since
            GROUP BY date_trunc('{bucket_unit}', created_at)
            ORDER BY date_trunc('{bucket_unit}', created_at) ASC
            """
        )
        rows = (await self.session.execute(sql, {"since": since})).mappings().all()
        return [
            {
                "bucket": str(row["bucket"]),
                "request_count": int(row["request_count"] or 0),
                "hit_count": int(row["hit_count"] or 0),
                "avg_latency_ms": round(float(row["avg_latency_ms"] or 0), 2),
            }
            for row in rows
        ]

    async def get_dashboard_breakdown(self, since: datetime) -> list[dict[str, Any]]:
        use_evidence_sidecar = await self._supports_evidence_sidecar()
        direct_count = func.coalesce(
            func.cardinality(self._anchor_kp_ids_expr(use_evidence_sidecar=use_evidence_sidecar)),
            0,
        )
        mapped_count = func.coalesce(
            func.cardinality(self._expanded_kp_ids_expr(use_evidence_sidecar=use_evidence_sidecar)),
            0,
        )

        stmt = select(
            func.coalesce(func.sum(case((and_(direct_count > 0, mapped_count == 0), 1), else_=0)), 0).label(
                "direct_only"
            ),
            func.coalesce(func.sum(case((and_(direct_count == 0, mapped_count > 0), 1), else_=0)), 0).label(
                "mapped_only"
            ),
            func.coalesce(func.sum(case((and_(direct_count > 0, mapped_count > 0), 1), else_=0)), 0).label(
                "hybrid"
            ),
            func.coalesce(func.sum(case((and_(direct_count == 0, mapped_count == 0), 1), else_=0)), 0).label(
                "empty"
            ),
        ).where(RetrievalLog.created_at >= since)

        row = (await self.session.execute(stmt)).one()
        return normalize_dashboard_breakdown_items(
            [
                {"key": "direct_only", "label": None, "value": int(row.direct_only or 0)},
                {"key": "mapped_only", "label": None, "value": int(row.mapped_only or 0)},
                {"key": "hybrid", "label": None, "value": int(row.hybrid or 0)},
                {"key": "empty", "label": None, "value": int(row.empty or 0)},
            ]
        )

    async def get_knowledge_heat(self, since: datetime, limit: int = 10) -> list[dict[str, Any]]:
        use_evidence_sidecar = await self._supports_evidence_sidecar()
        final_ids_sql = self._final_kp_ids_sql(use_evidence_sidecar=use_evidence_sidecar, table_alias="rl")
        sql = text(
            f"""
            SELECT
                kp.id::text AS knowledge_point_id,
                kp.title,
                count(*)::int AS count
            FROM retrieval_logs rl
            JOIN LATERAL unnest({final_ids_sql}) AS kp_id ON TRUE
            JOIN knowledge_points kp ON kp.id = kp_id
            WHERE rl.created_at >= :since
            GROUP BY kp.id, kp.title
            ORDER BY count DESC
            LIMIT :limit
            """
        )
        rows = (await self.session.execute(sql, {"since": since, "limit": limit})).mappings().all()
        return [
            {
                "knowledge_point_id": str(row["knowledge_point_id"]),
                "title": str(row["title"]),
                "count": int(row["count"] or 0),
            }
            for row in rows
        ]

    async def get_graph_data(
        self,
        since: datetime,
        node_limit: int,
        include_orphan_questions: bool = True,
    ) -> dict[str, Any]:
        use_evidence_sidecar = await self._supports_evidence_sidecar()
        final_ids_sql = self._final_kp_ids_sql(use_evidence_sidecar=use_evidence_sidecar, table_alias="rl")
        top_kp_sql = text(
            f"""
            SELECT
                kp.id::text AS knowledge_point_id,
                kp.title,
                count(*)::int AS hit_count
            FROM retrieval_logs rl
            JOIN LATERAL unnest({final_ids_sql}) AS kp_id ON TRUE
            JOIN knowledge_points kp ON kp.id = kp_id
            WHERE rl.created_at >= :since
            GROUP BY kp.id, kp.title
            ORDER BY hit_count DESC
            LIMIT :limit
            """
        )
        top_kp_rows = (await self.session.execute(top_kp_sql, {"since": since, "limit": node_limit})).mappings().all()
        knowledge_points: list[KnowledgePointGraphItem] = [
            {
                "knowledge_point_id": str(row["knowledge_point_id"]),
                "title": str(row["title"]),
                "hit_count": int(row["hit_count"] or 0),
            }
            for row in top_kp_rows
        ]

        if not knowledge_points:
            fallback_stmt = (
                select(KnowledgePoint.id, KnowledgePoint.title, KnowledgePoint.retrieval_count)
                .where(KnowledgePoint.is_active.is_(True))
                .order_by(KnowledgePoint.retrieval_count.desc(), KnowledgePoint.created_at.desc())
                .limit(node_limit)
            )
            fallback_rows = (await self.session.execute(fallback_stmt)).all()
            knowledge_points = [
                {
                    "knowledge_point_id": str(row.id),
                    "title": row.title,
                    "hit_count": int(row.retrieval_count or 0),
                }
                for row in fallback_rows
            ]

        kp_ids = [item["knowledge_point_id"] for item in knowledge_points]
        if not kp_ids:
            orphan_question_nodes: list[dict[str, Any]] = []
            if include_orphan_questions:
                orphan_rows = await self._get_orphan_questions(limit=node_limit)
                orphan_question_nodes = [
                    self._build_orphan_question_payload(question_id, question_text)
                    for question_id, question_text in orphan_rows
                ]
            return {"knowledge_points": [], "questions": orphan_question_nodes, "links": []}

        link_sql = text(
            """
            SELECT
                qkp.question_id::text AS question_id,
                qkp.knowledge_point_id::text AS knowledge_point_id,
                qkp.relevance_weight
            FROM question_knowledge_points qkp
            WHERE qkp.knowledge_point_id = ANY(CAST(:kp_ids AS uuid[]))
            ORDER BY qkp.relevance_weight DESC
            LIMIT :limit
            """
        )
        link_rows = (
            await self.session.execute(link_sql, {"kp_ids": kp_ids, "limit": max(node_limit * 6, 200)})
        ).mappings().all()

        question_degree: dict[str, int] = {}
        kp_link_count: dict[str, int] = {}
        for row in link_rows:
            question_id = str(row["question_id"])
            knowledge_point_id = str(row["knowledge_point_id"])
            question_degree[question_id] = question_degree.get(question_id, 0) + 1
            kp_link_count[knowledge_point_id] = kp_link_count.get(knowledge_point_id, 0) + 1

        linked_question_ids = sorted(
            question_degree.keys(),
            key=lambda question_id: (-question_degree[question_id], question_id),
        )
        linked_question_ids = linked_question_ids[:node_limit]
        linked_question_set = set(linked_question_ids)
        filtered_link_rows = [row for row in link_rows if str(row["question_id"]) in linked_question_set]

        question_map: dict[str, str] = {}
        if linked_question_ids:
            typed_question_ids = [uuid.UUID(item) for item in linked_question_ids]
            question_stmt = select(Question.id, Question.question_text).where(Question.id.in_(typed_question_ids))
            question_rows: list[QuestionRow] = list((await self.session.execute(question_stmt)).all())
            for question_id, question_text in question_rows:
                question_map[str(question_id)] = question_text

        orphan_questions: list[dict[str, Any]] = []
        if include_orphan_questions and len(linked_question_ids) < node_limit:
            orphan_limit = node_limit - len(linked_question_ids)
            orphan_rows = await self._get_orphan_questions(
                limit=orphan_limit,
                exclude_question_ids=linked_question_ids,
            )
            orphan_questions = [
                self._build_orphan_question_payload(question_id, question_text)
                for question_id, question_text in orphan_rows
            ]

        return {
            "knowledge_points": [
                {
                    "id": item["knowledge_point_id"],
                    "label": item["title"],
                    "weight": float(item["hit_count"]),
                    "is_orphan": False,
                    "link_count": int(kp_link_count.get(item["knowledge_point_id"], 0)),
                }
                for item in knowledge_points
            ],
            "questions": [
                {
                    "id": question_id,
                    "label": question_map.get(question_id, f"?? {question_id[:8]}"),
                    "weight": float(question_degree.get(question_id, 1)),
                    "is_orphan": False,
                    "link_count": int(question_degree.get(question_id, 0)),
                }
                for question_id in linked_question_ids
            ]
            + orphan_questions,
            "links": [
                {
                    "source": str(row["question_id"]),
                    "target": str(row["knowledge_point_id"]),
                    "weight": float(row["relevance_weight"] or 1.0),
                }
                for row in filtered_link_rows
            ],
        }

    @staticmethod
    def _build_orphan_question_payload(question_id: uuid.UUID, question_text: str) -> dict[str, Any]:
        return {
            "id": str(question_id),
            "label": question_text,
            "weight": 1.0,
            "is_orphan": True,
            "link_count": 0,
        }

    async def _get_orphan_questions(
        self,
        limit: int,
        exclude_question_ids: list[str] | None = None,
    ) -> list[QuestionRow]:
        stmt = (
            select(Question.id, Question.question_text)
            .outerjoin(QuestionKnowledgePoint, QuestionKnowledgePoint.question_id == Question.id)
            .where(QuestionKnowledgePoint.question_id.is_(None))
            .order_by(Question.updated_at.desc(), Question.created_at.desc())
            .limit(limit)
        )
        if exclude_question_ids:
            typed_ids = [uuid.UUID(item) for item in exclude_question_ids]
            stmt = stmt.where(~Question.id.in_(typed_ids))
        return list((await self.session.execute(stmt)).all())
