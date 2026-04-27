"""Schema模块：admin_analytics。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AdminRange = Literal["1d", "7d", "30d"]


class DashboardMetrics(BaseModel):
    request_count: int = 0
    hit_rate: float = 0
    avg_latency_ms: float = 0
    document_count: int = 0


class DashboardTrendPoint(BaseModel):
    bucket: str
    request_count: int = 0
    hit_count: int = 0
    avg_latency_ms: float = 0


class DashboardBreakdownItem(BaseModel):
    key: str
    label: str
    value: int = 0


class KnowledgeHeatItem(BaseModel):
    knowledge_point_id: str
    title: str
    count: int = 0


class AdminDashboardResponse(BaseModel):
    range: AdminRange
    metrics: DashboardMetrics
    trends: list[DashboardTrendPoint] = Field(default_factory=list)
    result_breakdown: list[DashboardBreakdownItem] = Field(default_factory=list)
    knowledge_heat: list[KnowledgeHeatItem] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    label: str
    node_type: Literal["knowledge_point", "question"]
    weight: float = 1.0
    is_orphan: bool = False
    link_count: int = 0


class GraphLink(BaseModel):
    source: str
    target: str
    weight: float = 1.0


class KnowledgeGraphSummary(BaseModel):
    node_count: int = 0
    edge_count: int = 0
    knowledge_point_count: int = 0
    question_count: int = 0


class KnowledgeGraphResponse(BaseModel):
    range: AdminRange
    nodes: list[GraphNode] = Field(default_factory=list)
    links: list[GraphLink] = Field(default_factory=list)
    summary: KnowledgeGraphSummary
