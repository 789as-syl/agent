"""Tests for question admin APIs."""

from __future__ import annotations

import importlib
import io
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from xml.sax.saxutils import escape

import pytest
from httpx import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_point import KnowledgePoint
from app.models.question_bank import Question, QuestionBank, QuestionType


def build_choice_options(*texts: str) -> list[dict[str, str]]:
    labels = ("A", "B", "C", "D")
    return [{"label": labels[index], "text": text} for index, text in enumerate(texts)]


def _excel_column_name(index: int) -> str:
    column = ""
    current = index + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        column = chr(ord("A") + remainder) + column
    return column


def _xlsx_inline_cell_xml(value: str) -> str:
    escaped = escape(value)
    if value != value.strip() or "\n" in value:
        return f'<is><t xml:space="preserve">{escaped}</t></is>'
    return f"<is><t>{escaped}</t></is>"


def build_excel_import_file(rows: list[dict[str, str | None]]) -> bytes:
    header: list[str | None] = [
        "external_id",
        "question_text",
        "question_type",
        "option_a",
        "option_b",
        "option_c",
        "option_d",
        "answer",
        "explanation",
        "knowledge_point_titles",
    ]
    sheet_rows: list[list[str | None]] = [
        header,
        *[
            [
                row.get("external_id"),
                row.get("question_text"),
                row.get("question_type"),
                row.get("option_a"),
                row.get("option_b"),
                row.get("option_c"),
                row.get("option_d"),
                row.get("answer"),
                row.get("explanation"),
                row.get("knowledge_point_titles"),
            ]
            for row in rows
        ],
    ]

    sheet_xml_rows: list[str] = []
    for row_index, sheet_row in enumerate(sheet_rows, start=1):
        cell_xml: list[str] = []
        for col_index, value in enumerate(sheet_row):
            if value is None:
                continue
            cell_ref = f"{_excel_column_name(col_index)}{row_index}"
            cell_xml.append(f'<c r="{cell_ref}" t="inlineStr">{_xlsx_inline_cell_xml(str(value))}</c>')
        sheet_xml_rows.append(f'<row r="{row_index}">{"".join(cell_xml)}</row>')

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    package_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_xml_rows)}</sheetData>"
        "</worksheet>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", package_rels_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
    return buffer.getvalue()


@pytest.fixture
def patch_vectorize_dependencies(monkeypatch: MonkeyPatch) -> tuple[SimpleNamespace, SimpleNamespace]:
    redis_mock = SimpleNamespace(set=AsyncMock(return_value=True), delete=AsyncMock(return_value=1))
    monkeypatch.setattr("app.services.question_service.redis_client", redis_mock)

    task_stub = SimpleNamespace(apply_async=MagicMock(return_value=SimpleNamespace(id="vector-task-id")))
    monkeypatch.setattr("app.services.question_service.batch_vectorize", task_stub)
    return redis_mock, task_stub


class TestQuestionBanks:
    @pytest.mark.asyncio
    async def test_create_and_list_question_banks(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            "/api/v1/admin/question-banks",
            headers=admin_auth_headers,
            json={"name": "Bank A", "description": "Desc"},
        )
        assert create_resp.status_code == 200
        created = create_resp.json()
        assert created["name"] == "Bank A"

        list_resp = await client.get("/api/v1/admin/question-banks", headers=admin_auth_headers)
        assert list_resp.status_code == 200
        payload = list_resp.json()
        assert payload["total"] >= 1
        assert any(item["id"] == created["id"] for item in payload["items"])

    @pytest.mark.asyncio
    async def test_update_and_delete_question_bank(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            "/api/v1/admin/question-banks",
            headers=admin_auth_headers,
            json={"name": "Bank For Update", "description": "Desc"},
        )
        assert create_resp.status_code == 200
        bank_id = create_resp.json()["id"]

        update_resp = await client.patch(
            f"/api/v1/admin/question-banks/{bank_id}",
            headers=admin_auth_headers,
            json={"name": "Bank Updated"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Bank Updated"

        delete_resp = await client.delete(
            f"/api/v1/admin/question-banks/{bank_id}",
            headers=admin_auth_headers,
        )
        assert delete_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_question_bank_blocked_when_not_empty(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_question_bank: QuestionBank,
    ) -> None:
        question = Question(
            id=uuid4(),
            question_text="Bank keep question",
            question_type=QuestionType.SINGLE,
            answer="A",
            bank_id=test_question_bank.id,
            content_hash="hash_bank_keep",
            is_dirty=True,
        )
        db_session.add(question)
        await db_session.flush()

        resp = await client.delete(
            f"/api/v1/admin/question-banks/{test_question_bank.id}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "QUESTION_BANK_NOT_EMPTY"


class TestQuestionCrud:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("payload", "expected_answer", "expected_options"),
        [
            (
                {
                    "question_text": "2 + 2 = ?",
                    "question_type": "single",
                    "options": build_choice_options("1", "4", "6"),
                    "answer": "B",
                    "explanation": "4 是正确答案",
                },
                "B",
                build_choice_options("1", "4", "6"),
            ),
            (
                {
                    "question_text": "哪些是质数?",
                    "question_type": "multiple",
                    "options": build_choice_options("2", "4", "5", "8"),
                    "answer": "C,A",
                    "explanation": "2 和 5 是质数",
                },
                "A,C",
                build_choice_options("2", "4", "5", "8"),
            ),
            (
                {
                    "question_text": "太阳从东方升起。",
                    "question_type": "true_false",
                    "options": None,
                    "answer": "true",
                    "explanation": "常识判断",
                },
                "true",
                None,
            ),
            (
                {
                    "question_text": "请简述 HTTP 的作用。",
                    "question_type": "short_answer",
                    "options": None,
                    "answer": "用于客户端与服务端传输超文本数据的应用层协议。",
                    "explanation": "开放题",
                },
                "用于客户端与服务端传输超文本数据的应用层协议。",
                None,
            ),
        ],
    )
    async def test_create_question_uses_canonical_typed_payload(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_question_bank: QuestionBank,
        payload: dict,
        expected_answer: str,
        expected_options: list[dict[str, str]] | None,
    ) -> None:
        response = await client.post(
            "/api/v1/admin/questions",
            headers=admin_auth_headers,
            json={
                **payload,
                "bank_id": str(test_question_bank.id),
                "knowledge_point_ids": [],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["question_type"] == payload["question_type"]
        assert body["answer"] == expected_answer
        assert body["options"] == expected_options
        assert body["is_dirty"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("question_type", "answer"),
        [
            ("true_false", "true"),
            ("short_answer", "参考答案"),
        ],
    )
    async def test_non_choice_questions_reject_options_on_create(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_question_bank: QuestionBank,
        question_type: str,
        answer: str,
    ) -> None:
        response = await client.post(
            "/api/v1/admin/questions",
            headers=admin_auth_headers,
            json={
                "bank_id": str(test_question_bank.id),
                "question_text": "无效题目",
                "question_type": question_type,
                "options": build_choice_options("选项1", "选项2"),
                "answer": answer,
                "knowledge_point_ids": [],
            },
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "QUESTION_OPTIONS_NOT_ALLOWED"

    @pytest.mark.asyncio
    async def test_update_question_type_switch_requires_explicitly_clearing_options(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_question_bank: QuestionBank,
    ) -> None:
        create_resp = await client.post(
            "/api/v1/admin/questions",
            headers=admin_auth_headers,
            json={
                "bank_id": str(test_question_bank.id),
                "question_text": "原始单选题",
                "question_type": "single",
                "options": build_choice_options("A 选项", "B 选项"),
                "answer": "A",
                "knowledge_point_ids": [],
            },
        )
        assert create_resp.status_code == 200
        question_id = create_resp.json()["id"]

        update_resp = await client.patch(
            f"/api/v1/admin/questions/{question_id}",
            headers=admin_auth_headers,
            json={
                "question_type": "true_false",
                "answer": "true",
            },
        )

        assert update_resp.status_code == 422
        assert update_resp.json()["error_code"] == "QUESTION_OPTIONS_NOT_ALLOWED"

    @pytest.mark.asyncio
    async def test_update_question_type_switch_succeeds_when_options_are_cleared(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_question_bank: QuestionBank,
    ) -> None:
        create_resp = await client.post(
            "/api/v1/admin/questions",
            headers=admin_auth_headers,
            json={
                "bank_id": str(test_question_bank.id),
                "question_text": "原始单选题",
                "question_type": "single",
                "options": build_choice_options("A 选项", "B 选项"),
                "answer": "A",
                "knowledge_point_ids": [],
            },
        )
        assert create_resp.status_code == 200
        question_id = create_resp.json()["id"]

        update_resp = await client.patch(
            f"/api/v1/admin/questions/{question_id}",
            headers=admin_auth_headers,
            json={
                "question_type": "true_false",
                "options": None,
                "answer": "false",
                "explanation": "改为判断题",
            },
        )

        assert update_resp.status_code == 200
        payload = update_resp.json()
        assert payload["question_type"] == "true_false"
        assert payload["options"] is None
        assert payload["answer"] == "false"


class TestQuestionImportCompatibility:
    @pytest.mark.asyncio
    async def test_import_questions_json_partial_success(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_question_bank: QuestionBank,
    ) -> None:
        response = await client.post(
            "/api/v1/admin/questions/import",
            headers=admin_auth_headers,
            json={
                "bank_id": str(test_question_bank.id),
                "questions": [
                    {
                        "external_id": "json-1",
                        "question_text": "What is 2 + 2?",
                        "question_type": "single",
                        "options": build_choice_options("1", "2", "3", "4"),
                        "answer": "D",
                        "knowledge_point_titles": [],
                    },
                    {
                        "external_id": "json-2",
                        "question_text": "Legacy row should fail",
                        "question_type": "single_choice",
                        "options": ["1", "2", "3", "4"],
                        "answer": "4",
                        "knowledge_point_titles": [],
                    },
                ],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 2
        assert payload["created"] == 1
        assert payload["failed"] == 1
        assert payload["skipped"] == 0
        assert any("single_choice" in error for error in payload["errors"])

        list_resp = await client.get(
            f"/api/v1/admin/questions?bank_id={test_question_bank.id}",
            headers=admin_auth_headers,
        )
        assert list_resp.status_code == 200
        list_payload = list_resp.json()
        assert list_payload["total"] == 1
        assert list_payload["items"][0]["question_type"] == "single"

    @pytest.mark.asyncio
    async def test_import_questions_form_json_channel_requires_canonical_payload(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_question_bank: QuestionBank,
    ) -> None:
        payload = {
            "bank_id": str(test_question_bank.id),
            "questions": [
                {
                    "external_id": "form-1",
                    "question_text": "Canonical multiple",
                    "question_type": "multiple",
                    "options": build_choice_options("A", "B", "C"),
                    "answer": "C,A",
                    "knowledge_point_titles": [],
                }
            ],
        }

        response = await client.post(
            "/api/v1/admin/questions/import",
            headers=admin_auth_headers,
            data={
                "bank_id": str(test_question_bank.id),
                "json_data": json.dumps(payload),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["created"] == 1
        assert body["failed"] == 0

    @pytest.mark.asyncio
    async def test_import_questions_xlsx_partial_success(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_question_bank: QuestionBank,
        monkeypatch: MonkeyPatch,
    ) -> None:
        original_import_module = importlib.import_module

        def fake_import_module(name: str, package: str | None = None) -> object:
            if name == "openpyxl":
                raise ImportError("simulated missing openpyxl")
            return original_import_module(name, package)

        monkeypatch.setattr("app.services.question_service.importlib.import_module", fake_import_module)

        excel_payload = build_excel_import_file(
            [
                {
                    "external_id": "xlsx-1",
                    "question_text": "Excel 单选题",
                    "question_type": "single",
                    "option_a": "3",
                    "option_b": "4",
                    "answer": "B",
                    "explanation": "4 正确",
                },
                {
                    "external_id": "xlsx-2",
                    "question_text": "Excel 判断题非法选项",
                    "question_type": "true_false",
                    "option_a": "对",
                    "option_b": "错",
                    "answer": "true",
                    "explanation": "应当失败",
                },
            ]
        )

        response = await client.post(
            "/api/v1/admin/questions/import",
            headers=admin_auth_headers,
            data={"bank_id": str(test_question_bank.id)},
            files={
                "file": (
                    "questions.xlsx",
                    excel_payload,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 2
        assert payload["created"] == 1
        assert payload["failed"] == 1
        assert any("Options are not allowed for question type true_false" in error for error in payload["errors"])

        list_resp = await client.get(
            f"/api/v1/admin/questions?bank_id={test_question_bank.id}",
            headers=admin_auth_headers,
        )
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == 1


class TestQuestionListAndVectorize:
    @pytest.mark.asyncio
    async def test_list_questions_supports_filters(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_question_bank: QuestionBank,
    ) -> None:
        q1 = Question(
            id=uuid4(),
            question_text="Python list question",
            question_type=QuestionType.SINGLE,
            options=build_choice_options("list", "tuple"),
            answer="A",
            bank_id=test_question_bank.id,
            content_hash="hash_1",
            is_dirty=True,
        )
        q2 = Question(
            id=uuid4(),
            question_text="Math clean question",
            question_type=QuestionType.MULTIPLE,
            options=build_choice_options("2", "4", "5"),
            answer="A,C",
            bank_id=test_question_bank.id,
            content_hash="hash_2",
            is_dirty=False,
        )
        db_session.add_all([q1, q2])
        await db_session.flush()

        resp = await client.get(
            f"/api/v1/admin/questions?bank_id={test_question_bank.id}&q=Python&question_type=single&is_dirty=true",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total"] == 1
        assert payload["items"][0]["question_text"] == "Python list question"
        assert payload["items"][0]["question_type"] == "single"
        assert payload["items"][0]["is_dirty"] is True
        assert "knowledge_point_ids" in payload["items"][0]

    @pytest.mark.asyncio
    async def test_question_list_returns_knowledge_point_ids(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_question_bank: QuestionBank,
    ) -> None:
        kp = KnowledgePoint(
            id=uuid4(),
            title="KP Link",
            file_type="md",
            object_path="documents/kp-link.md",
            is_active=True,
        )
        db_session.add(kp)
        await db_session.flush()

        create_resp = await client.post(
            "/api/v1/admin/questions",
            headers=admin_auth_headers,
            json={
                "bank_id": str(test_question_bank.id),
                "question_text": "Question with link",
                "question_type": "single",
                "options": build_choice_options("答案 A", "答案 B"),
                "answer": "A",
                "knowledge_point_ids": [str(kp.id)],
            },
        )
        assert create_resp.status_code == 200
        question_id = create_resp.json()["id"]

        list_resp = await client.get(
            f"/api/v1/admin/questions?bank_id={test_question_bank.id}",
            headers=admin_auth_headers,
        )
        assert list_resp.status_code == 200
        matched = next(item for item in list_resp.json()["items"] if item["id"] == question_id)
        assert str(kp.id) in matched["knowledge_point_ids"]

    @pytest.mark.asyncio
    async def test_link_knowledge_points_rejects_invalid_ids(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_question_bank: QuestionBank,
    ) -> None:
        create_resp = await client.post(
            "/api/v1/admin/questions",
            headers=admin_auth_headers,
            json={
                "bank_id": str(test_question_bank.id),
                "question_text": "Question invalid mapping",
                "question_type": "single",
                "options": build_choice_options("答案 A", "答案 B"),
                "answer": "A",
                "knowledge_point_ids": [],
            },
        )
        assert create_resp.status_code == 200
        question_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/admin/questions/{question_id}/knowledge-points",
            headers=admin_auth_headers,
            json={"knowledge_point_ids": [str(uuid4())]},
        )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "KNOWLEDGE_POINT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_vectorize_accepts_empty_body(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_question_bank: QuestionBank,
        patch_vectorize_dependencies: tuple[SimpleNamespace, SimpleNamespace],
    ) -> None:
        question = Question(
            id=uuid4(),
            question_text="Need vectorization",
            question_type=QuestionType.SINGLE,
            options=build_choice_options("选项 A", "选项 B"),
            answer="A",
            bank_id=test_question_bank.id,
            content_hash="hash_dirty",
            is_dirty=True,
        )
        db_session.add(question)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/admin/questions/vectorize",
            headers=admin_auth_headers,
        )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["status"] == "pending"
        assert payload["celery_task_id"] == "vector-task-id"

        redis_mock, task_stub = patch_vectorize_dependencies
        task_kwargs = task_stub.apply_async.call_args.kwargs
        assert task_kwargs["args"][2] == 10
        redis_mock.delete.assert_not_called()
