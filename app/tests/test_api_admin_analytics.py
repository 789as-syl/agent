"""API tests for admin analytics endpoints."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_point import KnowledgePoint
from app.models.question_bank import Question, QuestionBank, QuestionType
from app.models.question_knowledge_point import QuestionKnowledgePoint
from app.models.retrieval_log import RetrievalLog
from app.repositories.admin_analytics_repo import normalize_dashboard_breakdown_items

EXPECTED_BREAKDOWN_LABELS = {
    "direct_only": "直接命中",
    "mapped_only": "映射命中",
    "hybrid": "混合命中",
    "empty": "未命中",
}


def test_normalize_dashboard_breakdown_items_repairs_placeholder_labels() -> None:
    normalized = normalize_dashboard_breakdown_items(
        [
            {"key": "direct_only", "label": "????", "value": 1},
            {"key": "mapped_only", "label": "   ", "value": 2},
            {"key": "hybrid", "label": None, "value": 3},
            {"key": "empty", "label": "???", "value": 4},
        ]
    )

    assert {item["key"]: item["label"] for item in normalized} == EXPECTED_BREAKDOWN_LABELS


class TestAdminDashboard:
    @pytest.mark.asyncio
    async def test_dashboard_empty_returns_zero_values(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        await db_session.execute(delete(RetrievalLog))
        await db_session.flush()
        response = await client.get("/api/v1/admin/dashboard?range=7d", headers=admin_auth_headers)
        assert response.status_code == 200

        payload = response.json()
        assert payload["range"] == "7d"
        assert payload["metrics"]["request_count"] == 0
        assert payload["metrics"]["hit_rate"] == 0
        assert isinstance(payload["trends"], list)
        assert isinstance(payload["result_breakdown"], list)
        assert isinstance(payload["knowledge_heat"], list)
        assert {item["key"]: item["label"] for item in payload["result_breakdown"]} == EXPECTED_BREAKDOWN_LABELS

    @pytest.mark.asyncio
    async def test_dashboard_with_logs_returns_aggregates(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        kp = KnowledgePoint(
            id=uuid4(),
            title="Dashboard KP",
            file_type="pdf",
            object_path="documents/kp.pdf",
            is_active=True,
        )
        db_session.add(kp)
        await db_session.flush()

        log1 = RetrievalLog(
            id=uuid4(),
            user_id=uuid4(),
            conversation_id=None,
            original_query="q1",
            config_json={"top_k": 5},
            direct_hit_kp_ids=[kp.id],
            mapped_kp_ids=[],
            final_kp_ids=[kp.id],
            scores_json={str(kp.id): 0.9},
            cache_hit=False,
            duration_ms=120,
        )
        log2 = RetrievalLog(
            id=uuid4(),
            user_id=uuid4(),
            conversation_id=None,
            original_query="q2",
            config_json={"top_k": 5},
            direct_hit_kp_ids=[],
            mapped_kp_ids=[],
            final_kp_ids=[],
            scores_json={},
            cache_hit=False,
            duration_ms=180,
        )
        db_session.add_all([log1, log2])
        await db_session.flush()

        response = await client.get("/api/v1/admin/dashboard?range=7d", headers=admin_auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["metrics"]["request_count"] >= 2
        assert payload["metrics"]["hit_rate"] > 0
        assert payload["metrics"]["document_count"] >= 1
        assert {item["key"]: item["label"] for item in payload["result_breakdown"]} == EXPECTED_BREAKDOWN_LABELS

    @pytest.mark.asyncio
    async def test_dashboard_supports_evidence_sidecar_fields(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        kp = KnowledgePoint(
            id=uuid4(),
            title="Evidence Dashboard KP",
            file_type="pdf",
            object_path="documents/evidence-dashboard.pdf",
            is_active=True,
        )
        db_session.add(kp)
        await db_session.flush()

        db_session.add(
            RetrievalLog(
                id=uuid4(),
                user_id=uuid4(),
                conversation_id=None,
                original_query="evidence dashboard",
                config_json={"top_k": 8},
                direct_hit_kp_ids=[],
                mapped_kp_ids=[],
                final_kp_ids=[],
                anchor_kp_ids=[kp.id],
                expanded_kp_ids_non_anchor=[],
                final_evidence_kp_ids=[kp.id],
                scores_json={str(kp.id): 0.82},
                cache_hit=False,
                duration_ms=140,
            )
        )
        await db_session.flush()

        response = await client.get("/api/v1/admin/dashboard?range=7d", headers=admin_auth_headers)
        assert response.status_code == 200
        payload = response.json()

        assert payload["metrics"]["request_count"] >= 1
        assert payload["metrics"]["hit_rate"] > 0
        assert any(item["key"] == "direct_only" and item["value"] >= 1 for item in payload["result_breakdown"])


class TestKnowledgeGraph:
    @pytest.mark.asyncio
    async def test_knowledge_graph_empty_returns_empty_structure(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        response = await client.get(
            "/api/v1/admin/knowledge-graph?range=7d&node_limit=200",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["range"] == "7d"
        assert isinstance(payload["nodes"], list)
        assert isinstance(payload["links"], list)
        assert payload["summary"]["node_count"] >= 0

    @pytest.mark.asyncio
    async def test_knowledge_graph_with_data(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        bank = QuestionBank(id=uuid4(), name="Graph Bank", description="")
        kp = KnowledgePoint(
            id=uuid4(),
            title="Graph KP",
            file_type="pdf",
            object_path="documents/graph.pdf",
            is_active=True,
        )
        question = Question(
            id=uuid4(),
            question_text="Graph Question",
            question_type=QuestionType.SINGLE,
            answer="A",
            bank_id=bank.id,
            content_hash="graph_hash",
            is_dirty=False,
        )

        db_session.add_all([bank, kp, question])
        await db_session.flush()

        link = QuestionKnowledgePoint(
            question_id=question.id,
            knowledge_point_id=kp.id,
            relevance_weight=1.0,
        )
        db_session.add(link)

        log = RetrievalLog(
            id=uuid4(),
            user_id=uuid4(),
            conversation_id=None,
            original_query="graph",
            config_json={"top_k": 5},
            direct_hit_kp_ids=[kp.id],
            mapped_kp_ids=[kp.id],
            final_kp_ids=[kp.id],
            scores_json={str(kp.id): 0.95},
            cache_hit=False,
            duration_ms=100,
        )
        db_session.add(log)
        await db_session.flush()

        response = await client.get(
            "/api/v1/admin/knowledge-graph?range=7d&node_limit=200",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["knowledge_point_count"] >= 1
        assert payload["summary"]["question_count"] >= 1
        assert payload["summary"]["edge_count"] >= 1

    @pytest.mark.asyncio
    async def test_knowledge_graph_uses_final_evidence_kp_ids_when_final_is_empty(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        bank = QuestionBank(id=uuid4(), name="Evidence Graph Bank", description="")
        kp = KnowledgePoint(
            id=uuid4(),
            title="Evidence Graph KP",
            file_type="pdf",
            object_path="documents/evidence-graph.pdf",
            is_active=True,
        )
        question = Question(
            id=uuid4(),
            question_text="Evidence Graph Question",
            question_type=QuestionType.SINGLE,
            answer="A",
            bank_id=bank.id,
            content_hash="evidence_graph_hash",
            is_dirty=False,
        )

        db_session.add_all([bank, kp, question])
        await db_session.flush()

        db_session.add(
            QuestionKnowledgePoint(
                question_id=question.id,
                knowledge_point_id=kp.id,
                relevance_weight=1.0,
            )
        )
        db_session.add(
            RetrievalLog(
                id=uuid4(),
                user_id=uuid4(),
                conversation_id=None,
                original_query="evidence graph",
                config_json={"top_k": 5},
                direct_hit_kp_ids=[],
                mapped_kp_ids=[],
                final_kp_ids=[],
                anchor_kp_ids=[kp.id],
                expanded_kp_ids_non_anchor=[],
                final_evidence_kp_ids=[kp.id],
                scores_json={str(kp.id): 0.93},
                cache_hit=False,
                duration_ms=88,
            )
        )
        await db_session.flush()

        response = await client.get(
            "/api/v1/admin/knowledge-graph?range=7d&node_limit=200&force_refresh=true",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["knowledge_point_count"] >= 1
        assert payload["summary"]["edge_count"] >= 1

    @pytest.mark.asyncio
    async def test_dashboard_and_graph_require_admin(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        dashboard_resp = await client.get("/api/v1/admin/dashboard", headers=auth_headers)
        graph_resp = await client.get("/api/v1/admin/knowledge-graph", headers=auth_headers)
        assert dashboard_resp.status_code == 403
        assert graph_resp.status_code == 403

    @pytest.mark.asyncio
    async def test_knowledge_graph_can_include_orphan_questions(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        bank = QuestionBank(id=uuid4(), name="Orphan Bank", description="")
        kp = KnowledgePoint(
            id=uuid4(),
            title="Orphan KP",
            file_type="pdf",
            object_path="documents/orphan.pdf",
            is_active=True,
        )
        linked_question = Question(
            id=uuid4(),
            question_text="Linked Question",
            question_type=QuestionType.SINGLE,
            answer="A",
            bank_id=bank.id,
            content_hash="linked_hash",
            is_dirty=False,
        )
        orphan_question = Question(
            id=uuid4(),
            question_text="Orphan Question",
            question_type=QuestionType.SINGLE,
            answer="B",
            bank_id=bank.id,
            content_hash="orphan_hash",
            is_dirty=False,
        )
        db_session.add_all([bank, kp, linked_question, orphan_question])
        await db_session.flush()

        db_session.add(
            QuestionKnowledgePoint(
                question_id=linked_question.id,
                knowledge_point_id=kp.id,
                relevance_weight=1.0,
            )
        )
        db_session.add(
            RetrievalLog(
                id=uuid4(),
                user_id=uuid4(),
                conversation_id=None,
                original_query="orphan",
                config_json={"top_k": 5},
                direct_hit_kp_ids=[kp.id],
                mapped_kp_ids=[],
                final_kp_ids=[kp.id],
                scores_json={str(kp.id): 0.9},
                cache_hit=False,
                duration_ms=100,
            )
        )
        await db_session.flush()

        without_orphan = await client.get(
            "/api/v1/admin/knowledge-graph?range=7d&node_limit=200&include_orphan_questions=false&force_refresh=true",
            headers=admin_auth_headers,
        )
        with_orphan = await client.get(
            "/api/v1/admin/knowledge-graph?range=7d&node_limit=200&include_orphan_questions=true&force_refresh=true",
            headers=admin_auth_headers,
        )

        assert without_orphan.status_code == 200
        assert with_orphan.status_code == 200
        payload_without = without_orphan.json()
        payload_with = with_orphan.json()

        without_ids = {node["id"] for node in payload_without["nodes"]}
        with_nodes = {node["id"]: node for node in payload_with["nodes"]}

        assert str(orphan_question.id) not in without_ids
        assert str(orphan_question.id) in with_nodes
        assert with_nodes[str(orphan_question.id)]["is_orphan"] is True
