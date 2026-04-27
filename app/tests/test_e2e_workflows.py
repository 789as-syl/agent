"""Tests for end-to-end workflows."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question_bank import QuestionBank


class TestUserJourney:
    """End-to-end tests for user journey."""

    @pytest.mark.asyncio
    async def test_complete_user_registration_to_chat_flow(
        self,
        client: AsyncClient,
        mock_redis,
        mock_celery,
    ):
        """Test complete flow from registration to creating a chat."""
        import time
        phone = f"139{str(int(time.time() * 1000))[-8:]}"

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "phone": phone,
                "password": "TestPass123",
            },
        )
        assert response.status_code == 201
        tokens = response.json()
        auth_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        response = await client.get(
            "/api/v1/auth/me",
            headers=auth_headers,
        )
        assert response.status_code == 200
        user_data = response.json()
        assert user_data["phone"] == phone

        response = await client.post(
            "/api/v1/conversations",
            headers=auth_headers,
            json={"title": "My First Chat"},
        )
        assert response.status_code == 201
        conv_data = response.json()
        conv_id = conv_data["id"]

        response = await client.get(
            "/api/v1/conversations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        conv_list = response.json()
        assert conv_list["total"] >= 1

        response = await client.post(
            f"/api/v1/conversations/{conv_id}/runs",
            headers=auth_headers,
            json={"query": "What is machine learning?"},
        )
        assert response.status_code == 201
        run_data = response.json()
        assert run_data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_user_login_and_token_refresh_flow(
        self,
        client: AsyncClient,
        test_user,
        mock_redis,
    ):
        """Test login and token refresh flow."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "phone": test_user.phone,
                "password": "TestPass123",
            },
        )
        assert response.status_code == 200
        login_data = response.json()
        assert "access_token" in login_data

        from app.services.token_service import TokenService
        tokens = TokenService.generate_tokens(
            user_id=str(test_user.id),
            phone=test_user.phone,
        )

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 200
        refresh_data = response.json()
        assert "access_token" in refresh_data


class TestAdminWorkflow:
    """End-to-end tests for admin workflows."""

    @pytest.mark.asyncio
    async def test_complete_question_management_workflow(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
    ):
        """Test complete question management workflow."""
        bank = QuestionBank(
            id=uuid4(),
            name="Test Bank",
            description="Test bank for e2e",
        )
        db_session.add(bank)
        await db_session.flush()

        response = await client.post(
            "/api/v1/admin/questions",
            headers=admin_auth_headers,
            json={
                "question_text": "What is Python?",
                "question_type": "single",
                "options": [
                    {"label": "A", "text": "A snake"},
                    {"label": "B", "text": "A programming language"},
                    {"label": "C", "text": "A fruit"},
                    {"label": "D", "text": "A car"},
                ],
                "answer": "B",
                "explanation": "Python is a high-level programming language.",
                "bank_id": str(bank.id),
                "knowledge_point_ids": [],
            },
        )
        assert response.status_code == 200
        question_data = response.json()
        question_id = question_data["id"]

        response = await client.get(
            "/api/v1/admin/questions",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        list_data = response.json()
        assert list_data["total"] >= 1

        response = await client.patch(
            f"/api/v1/admin/questions/{question_id}",
            headers=admin_auth_headers,
            json={"question_text": "What is Python programming language?"},
        )
        assert response.status_code == 200
        updated_data = response.json()
        assert updated_data["question_text"] == "What is Python programming language?"

        response = await client.delete(
            f"/api/v1/admin/questions/{question_id}",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_complete_document_ingestion_workflow(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        mock_minio,
        mock_celery,
        db_session: AsyncSession,
    ):
        """Test complete document ingestion workflow."""
        response = await client.post(
            "/api/v1/admin/uploads/presign",
            headers=admin_auth_headers,
            json={
                "file_name": "test.txt",
                "file_type": "txt",
            },
        )
        assert response.status_code == 200
        presign_data = response.json()
        assert "upload_url" in presign_data
        assert "object_path" in presign_data

        response = await client.post(
            "/api/v1/admin/uploads/callback",
            headers=admin_auth_headers,
            json={
                "object_path": presign_data["object_path"],
                "file_name": "test.txt",
                "file_type": "txt",
                "file_size": 1024,
            },
        )
        assert response.status_code == 200
        callback_data = response.json()
        assert "job_id" in callback_data
        assert callback_data["status"] == "pending"

        response = await client.get(
            "/api/v1/admin/knowledge-points",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        kp_list = response.json()
        assert kp_list["total"] >= 1


class TestConversationWorkflow:
    """End-to-end tests for conversation workflows."""

    @pytest.mark.asyncio
    async def test_complete_conversation_lifecycle(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user,
    ):
        """Test complete conversation lifecycle."""
        response = await client.post(
            "/api/v1/conversations",
            headers=auth_headers,
            json={"title": "Lifecycle Test"},
        )
        assert response.status_code == 201
        conv_data = response.json()
        conv_id = conv_data["id"]

        response = await client.patch(
            f"/api/v1/conversations/{conv_id}",
            headers=auth_headers,
            json={"title": "Updated Title"},
        )
        assert response.status_code == 200
        updated_data = response.json()
        assert updated_data["title"] == "Updated Title"

        response = await client.get(
            f"/api/v1/conversations/{conv_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        get_data = response.json()
        assert get_data["title"] == "Updated Title"

        response = await client.delete(
            f"/api/v1/conversations/{conv_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        response = await client.get(
            f"/api/v1/conversations/{conv_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestPermissionEnforcement:
    """Tests for permission enforcement across workflows."""

    @pytest.mark.asyncio
    async def test_regular_user_cannot_access_admin_endpoints(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Test that regular users cannot access admin endpoints."""
        response = await client.get(
            "/api/v1/admin/questions",
            headers=auth_headers,
        )
        assert response.status_code == 403

        response = await client.get(
            "/api/v1/admin/knowledge-points",
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_user_cannot_access_other_users_conversations(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
        other_user,
    ):
        """Test that users cannot access other users' conversations."""
        from app.models.conversation import Conversation
        from app.services.token_service import TokenService

        conv = Conversation(
            id=uuid4(),
            user_id=other_user.id,
            title="Other User Conv",
            is_deleted=False,
        )
        db_session.add(conv)
        await db_session.flush()

        tokens = TokenService.generate_tokens(
            user_id=str(test_user.id),
            phone=test_user.phone,
        )
        auth_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        response = await client.get(
            f"/api/v1/conversations/{conv.id}",
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_user_cannot_access_protected_endpoints(
        self,
        client: AsyncClient,
    ):
        """Test that unauthenticated users cannot access protected endpoints."""
        response = await client.get("/api/v1/conversations")
        assert response.status_code == 403

        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 403

        response = await client.post(
            "/api/v1/conversations",
            json={"title": "Test"},
        )
        assert response.status_code == 403
