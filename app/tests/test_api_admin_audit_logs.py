from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.admin_audit_service import AdminAuditService


@pytest.mark.asyncio
async def test_admin_audit_log_list_is_admin_only(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_admin_user: User,
) -> None:
    await AdminAuditService(db_session).record(
        actor_user_id=test_admin_user.id,
        action="test.delete",
        resource_type="test_resource",
        resource_id="resource-1",
        summary="deleted test resource",
    )
    await db_session.commit()

    denied = await client.get("/api/v1/admin/audit-logs", headers=auth_headers)
    assert denied.status_code == 403

    response = await client.get("/api/v1/admin/audit-logs", headers=admin_auth_headers)
    assert response.status_code == 200
    assert response.json()["items"][0]["action"] == "test.delete"
