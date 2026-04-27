from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_rag_eval_lab_crud_and_run_without_external_credentials(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    auth_headers: dict[str, str],
) -> None:
    denied = await client.get("/api/v1/admin/rag-eval/golden-queries", headers=auth_headers)
    assert denied.status_code == 403

    create_response = await client.post(
        "/api/v1/admin/rag-eval/golden-queries",
        headers=admin_auth_headers,
        json={"name": "No evidence case", "query": "unlikely local evidence query", "expected_source_ids": []},
    )
    assert create_response.status_code == 200
    query_id = create_response.json()["id"]

    list_response = await client.get("/api/v1/admin/rag-eval/golden-queries", headers=admin_auth_headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 1

    run_response = await client.post(
        "/api/v1/admin/rag-eval/runs",
        headers=admin_auth_headers,
        json={"golden_query_id": query_id},
    )
    assert run_response.status_code == 200
    assert run_response.json()["status"] in {"success", "failed"}
    assert "provider_payload" not in str(run_response.json())

    delete_response = await client.delete(f"/api/v1/admin/rag-eval/golden-queries/{query_id}", headers=admin_auth_headers)
    assert delete_response.status_code == 200
