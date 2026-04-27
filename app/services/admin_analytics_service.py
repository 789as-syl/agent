"""Admin analytics service helpers."""

from __future__ import annotations

import json

from app.core.config import settings
from app.core.redis import redis_client
from app.repositories.admin_analytics_repo import AdminAnalyticsRepository, range_to_since
from app.schemas.admin_analytics import (
    AdminDashboardResponse,
    AdminRange,
    DashboardBreakdownItem,
    DashboardMetrics,
    DashboardTrendPoint,
    GraphLink,
    GraphNode,
    KnowledgeGraphResponse,
    KnowledgeGraphSummary,
    KnowledgeHeatItem,
)


class AdminAnalyticsService:
    def __init__(self, repo: AdminAnalyticsRepository):
        self.repo = repo

    async def get_dashboard(self, range_value: AdminRange) -> AdminDashboardResponse:
        cache_key = f"admin:dashboard:{range_value}"
        cached = await self._get_cache(cache_key)
        if cached:
            return AdminDashboardResponse.model_validate(cached)

        since = range_to_since(range_value)

        metrics_raw = await self.repo.get_dashboard_metrics(since)
        trends_raw = await self.repo.get_dashboard_trends(since, range_value)
        breakdown_raw = await self.repo.get_dashboard_breakdown(since)
        heat_raw = await self.repo.get_knowledge_heat(since, limit=10)

        payload = AdminDashboardResponse(
            range=range_value,
            metrics=DashboardMetrics(**metrics_raw),
            trends=[DashboardTrendPoint(**item) for item in trends_raw],
            result_breakdown=[DashboardBreakdownItem(**item) for item in breakdown_raw],
            knowledge_heat=[KnowledgeHeatItem(**item) for item in heat_raw],
        )

        await self._set_cache(cache_key, payload.model_dump())
        return payload

    async def get_knowledge_graph(
        self,
        range_value: AdminRange,
        node_limit: int,
        include_orphan_questions: bool = True,
        force_refresh: bool = False,
    ) -> KnowledgeGraphResponse:
        cache_key = f"admin:knowledge-graph:{range_value}:{node_limit}:{int(include_orphan_questions)}"
        if not force_refresh:
            cached = await self._get_cache(cache_key)
            if cached:
                return KnowledgeGraphResponse.model_validate(cached)

        since = range_to_since(range_value)
        graph_raw = await self.repo.get_graph_data(
            since,
            node_limit,
            include_orphan_questions=include_orphan_questions,
        )

        kp_nodes = [
            GraphNode(
                id=item["id"],
                label=item["label"],
                node_type="knowledge_point",
                weight=item["weight"],
                is_orphan=bool(item.get("is_orphan", False)),
                link_count=int(item.get("link_count", 0)),
            )
            for item in graph_raw["knowledge_points"]
        ]
        question_nodes = [
            GraphNode(
                id=item["id"],
                label=item["label"],
                node_type="question",
                weight=item["weight"],
                is_orphan=bool(item.get("is_orphan", False)),
                link_count=int(item.get("link_count", 0)),
            )
            for item in graph_raw["questions"]
        ]
        links = [GraphLink(**item) for item in graph_raw["links"]]

        response = KnowledgeGraphResponse(
            range=range_value,
            nodes=[*kp_nodes, *question_nodes],
            links=links,
            summary=KnowledgeGraphSummary(
                node_count=len(kp_nodes) + len(question_nodes),
                edge_count=len(links),
                knowledge_point_count=len(kp_nodes),
                question_count=len(question_nodes),
            ),
        )

        await self._set_cache(cache_key, response.model_dump())
        return response

    async def _get_cache(self, key: str) -> dict[str, object] | None:
        try:
            raw = await redis_client.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    async def _set_cache(self, key: str, payload: dict[str, object]) -> None:
        try:
            await redis_client.setex(key, settings.admin_analytics_cache_ttl, json.dumps(payload, ensure_ascii=False))
        except Exception:
            return None


async def invalidate_admin_analytics_cache() -> None:
    """Invalidate cached admin dashboard/graph payloads after source data changes."""
    try:
        keys: list[str] = []
        async for key in redis_client.scan_iter(match="admin:dashboard:*"):
            keys.append(key)
        async for key in redis_client.scan_iter(match="admin:knowledge-graph:*"):
            keys.append(key)
        if keys:
            await redis_client.delete(*keys)
    except Exception:
        # Non-blocking cache invalidation
        return None

