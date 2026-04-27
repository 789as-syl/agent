"""Tests for health endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


class TestHealthCheck:
    """Tests for GET /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, client: AsyncClient) -> None:
        """Test liveness probe returns ok status."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "knowledge-base-agent"

    @pytest.mark.asyncio
    async def test_health_check_no_auth_required(self, client: AsyncClient) -> None:
        """Test that health check doesn't require authentication."""
        response = await client.get("/health")

        assert response.status_code == 200


class TestReadinessCheck:
    """Tests for GET /ready endpoint."""

    @pytest.mark.asyncio
    async def test_readiness_all_services_healthy(
        self,
        client: AsyncClient,
        mock_redis: MagicMock,
        mock_minio: MagicMock,
    ) -> None:
        """Test readiness when all services are healthy."""
        with (
            patch("app.api.health.get_async_engine") as mock_engine,
            patch("app.api.health.check_celery_broker") as mock_celery_check,
            patch(
                "app.api.health.get_document_runtime_readiness",
                return_value={"missing_types": [], "docling_runtime_ready": True, "docling_pdf_runtime_ready": True},
            ),
            patch("app.api.health.is_docling_runtime_available", return_value=True),
            patch("app.api.health.is_docling_pdf_runtime_available", return_value=True),
            patch("app.api.health.get_current_database_revision", AsyncMock(return_value="head-1")),
            patch("app.api.health.get_alembic_head_revisions", return_value=("head-1",)),
            patch("app.api.health.ensure_database_schema_current", AsyncMock()),
        ):
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock()

            mock_engine.return_value.connect.return_value = mock_conn
            mock_celery_check.return_value = True

            with (
                patch("app.api.health.redis_client", mock_redis),
                patch("app.api.health.check_minio", AsyncMock(return_value=True)),
            ):
                response = await client.get("/ready")

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "ready"
                assert len(data["checks"]) == 6

                for check in data["checks"]:
                    assert check["status"] == "ok"

    @pytest.mark.asyncio
    async def test_readiness_database_unhealthy(self, client: AsyncClient) -> None:
        """Test readiness when database is unhealthy."""
        with (
            patch("app.api.health.get_async_engine") as mock_engine,
            patch(
                "app.api.health.get_document_runtime_readiness",
                return_value={"missing_types": [], "docling_runtime_ready": True, "docling_pdf_runtime_ready": True},
            ),
            patch("app.api.health.is_docling_runtime_available", return_value=True),
            patch("app.api.health.is_docling_pdf_runtime_available", return_value=True),
            patch("app.api.health.get_current_database_revision", AsyncMock(return_value="head-1")),
            patch("app.api.health.get_alembic_head_revisions", return_value=("head-1",)),
            patch("app.api.health.ensure_database_schema_current", AsyncMock()),
        ):
            mock_engine.return_value.connect.side_effect = Exception("DB connection failed")

            response = await client.get("/ready")

            assert response.status_code == 503
            data = response.json()
            assert "detail" in data
            assert data["detail"]["status"] == "not_ready"

            db_check = next((c for c in data["detail"]["checks"] if c["service"] == "postgresql"), None)
            assert db_check is not None
            assert db_check["status"] == "failed"

    @pytest.mark.asyncio
    async def test_readiness_redis_unhealthy(self, client: AsyncClient) -> None:
        """Test readiness when Redis is unhealthy."""
        with (
            patch("app.api.health.get_async_engine") as mock_engine,
            patch("app.api.health.redis_client") as mock_redis,
            patch(
                "app.api.health.get_document_runtime_readiness",
                return_value={"missing_types": [], "docling_runtime_ready": True, "docling_pdf_runtime_ready": True},
            ),
            patch("app.api.health.is_docling_runtime_available", return_value=True),
            patch("app.api.health.is_docling_pdf_runtime_available", return_value=True),
            patch("app.api.health.get_current_database_revision", AsyncMock(return_value="head-1")),
            patch("app.api.health.get_alembic_head_revisions", return_value=("head-1",)),
            patch("app.api.health.ensure_database_schema_current", AsyncMock()),
        ):
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock()
            mock_engine.return_value.connect.return_value = mock_conn

            mock_redis.ping.side_effect = Exception("Redis connection failed")

            response = await client.get("/ready")

            assert response.status_code == 503
            data = response.json()

            redis_check = next((c for c in data["detail"]["checks"] if c["service"] == "redis"), None)
            assert redis_check is not None
            assert redis_check["status"] == "failed"

    @pytest.mark.asyncio
    async def test_readiness_minio_unhealthy(
        self,
        client: AsyncClient,
        mock_redis: MagicMock,
    ) -> None:
        """Test readiness when MinIO is unhealthy."""
        with (
            patch("app.api.health.get_async_engine") as mock_engine,
            patch("app.api.health.redis_client", mock_redis),
            patch("app.api.health.check_minio") as mock_check_minio,
            patch(
                "app.api.health.get_document_runtime_readiness",
                return_value={"missing_types": [], "docling_runtime_ready": True, "docling_pdf_runtime_ready": True},
            ),
            patch("app.api.health.is_docling_runtime_available", return_value=True),
            patch("app.api.health.is_docling_pdf_runtime_available", return_value=True),
            patch("app.api.health.get_current_database_revision", AsyncMock(return_value="head-1")),
            patch("app.api.health.get_alembic_head_revisions", return_value=("head-1",)),
            patch("app.api.health.ensure_database_schema_current", AsyncMock()),
        ):
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock()
            mock_engine.return_value.connect.return_value = mock_conn

            mock_check_minio.return_value = False

            response = await client.get("/ready")

            assert response.status_code == 503
            data = response.json()

            minio_check = next((c for c in data["detail"]["checks"] if c["service"] == "minio"), None)
            assert minio_check is not None
            assert minio_check["status"] == "failed"

    @pytest.mark.asyncio
    async def test_readiness_celery_unhealthy(
        self,
        client: AsyncClient,
        mock_redis: MagicMock,
    ) -> None:
        """Test readiness when Celery broker is unhealthy."""
        with (
            patch("app.api.health.get_async_engine") as mock_engine,
            patch("app.api.health.redis_client", mock_redis),
            patch("app.api.health.check_celery_broker") as mock_celery,
            patch(
                "app.api.health.get_document_runtime_readiness",
                return_value={"missing_types": [], "docling_runtime_ready": True, "docling_pdf_runtime_ready": True},
            ),
            patch("app.api.health.is_docling_runtime_available", return_value=True),
            patch("app.api.health.is_docling_pdf_runtime_available", return_value=True),
            patch("app.api.health.get_current_database_revision", AsyncMock(return_value="head-1")),
            patch("app.api.health.get_alembic_head_revisions", return_value=("head-1",)),
            patch("app.api.health.ensure_database_schema_current", AsyncMock()),
        ):
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock()
            mock_engine.return_value.connect.return_value = mock_conn

            mock_celery.return_value = False

            with patch("app.api.health.check_minio", AsyncMock(return_value=True)):
                response = await client.get("/ready")

            assert response.status_code == 503
            data = response.json()

            celery_check = next((c for c in data["detail"]["checks"] if c["service"] == "celery"), None)
            assert celery_check is not None
            assert celery_check["status"] == "failed"

    @pytest.mark.asyncio
    async def test_readiness_document_parsers_unhealthy(
        self,
        client: AsyncClient,
        mock_redis: MagicMock,
    ) -> None:
        """Test readiness when configured document parsers are missing."""
        with (
            patch("app.api.health.get_async_engine") as mock_engine,
            patch("app.api.health.redis_client", mock_redis),
            patch("app.api.health.check_celery_broker", return_value=True),
            patch("app.api.health.check_minio", AsyncMock(return_value=True)),
            patch(
                "app.api.health.get_document_runtime_readiness",
                return_value={"missing_types": ["pdf"], "docling_runtime_ready": True, "docling_pdf_runtime_ready": False},
            ),
            patch("app.api.health.is_docling_runtime_available", return_value=True),
            patch("app.api.health.is_docling_pdf_runtime_available", return_value=False),
            patch("app.api.health.get_current_database_revision", AsyncMock(return_value="head-1")),
            patch("app.api.health.get_alembic_head_revisions", return_value=("head-1",)),
            patch("app.api.health.ensure_database_schema_current", AsyncMock()),
        ):
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock()
            mock_engine.return_value.connect.return_value = mock_conn

            response = await client.get("/ready")

            assert response.status_code == 503
            data = response.json()
            parser_check = next(
                (c for c in data["detail"]["checks"] if c["service"] == "document_parsers"),
                None,
            )
            assert parser_check is not None
            assert parser_check["status"] == "failed"
            assert "pdf" in parser_check["message"]

    @pytest.mark.asyncio
    async def test_readiness_schema_drift_unhealthy(
        self,
        client: AsyncClient,
        mock_redis: MagicMock,
    ) -> None:
        with (
            patch("app.api.health.get_async_engine") as mock_engine,
            patch("app.api.health.redis_client", mock_redis),
            patch("app.api.health.check_celery_broker", return_value=True),
            patch("app.api.health.check_minio", AsyncMock(return_value=True)),
            patch(
                "app.api.health.get_document_runtime_readiness",
                return_value={"missing_types": [], "docling_runtime_ready": True, "docling_pdf_runtime_ready": True},
            ),
            patch("app.api.health.is_docling_runtime_available", return_value=True),
            patch("app.api.health.is_docling_pdf_runtime_available", return_value=True),
            patch("app.api.health.get_current_database_revision", AsyncMock(return_value="old-head")),
            patch("app.api.health.get_alembic_head_revisions", return_value=("new-head",)),
            patch(
                "app.api.health.ensure_database_schema_current",
                AsyncMock(side_effect=RuntimeError("Database schema is out of date")),
            ),
        ):
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock()
            mock_engine.return_value.connect.return_value = mock_conn

            response = await client.get("/ready")

            assert response.status_code == 503
            data = response.json()
            schema_check = next(
                (c for c in data["detail"]["checks"] if c["service"] == "database_schema"),
                None,
            )
            assert schema_check is not None
            assert schema_check["status"] == "failed"
            assert "old-head" in schema_check["message"]
            assert "new-head" in schema_check["message"]

    @pytest.mark.asyncio
    async def test_readiness_no_auth_required(self, client: AsyncClient) -> None:
        """Test that readiness check doesn't require authentication."""
        response = await client.get("/ready")

        assert response.status_code in [200, 503]
