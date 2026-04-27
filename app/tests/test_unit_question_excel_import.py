"""Unit tests for Excel question import fallback parsing."""

from __future__ import annotations

import importlib
import io
import zipfile
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from xml.sax.saxutils import escape

import pytest

from app.schemas.question import QuestionImportResponse
from app.services.question_service import QuestionService, _iter_excel_rows
from app.tests.test_api_questions import _excel_column_name, build_excel_import_file


def _force_missing_openpyxl(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None) -> object:
        if name == "openpyxl":
            raise ImportError("simulated missing openpyxl")
        return original_import_module(name, package)

    monkeypatch.setattr("app.services.question_service.importlib.import_module", fake_import_module)


def _build_shared_strings_excel_file(rows: list[list[str | None]]) -> bytes:
    string_index: dict[str, int] = {}
    shared_strings: list[str] = []
    total_strings = 0
    worksheet_rows: list[str] = []

    for row_index, row in enumerate(rows, start=1):
        cell_xml: list[str] = []
        for col_index, value in enumerate(row):
            if value is None:
                continue

            total_strings += 1
            if value not in string_index:
                string_index[value] = len(shared_strings)
                shared_strings.append(value)

            cell_ref = f"{_excel_column_name(col_index)}{row_index}"
            cell_xml.append(
                f'<c r="{cell_ref}" t="s"><v>{string_index[value]}</v></c>'
            )
        worksheet_rows.append(f'<row r="{row_index}">{"".join(cell_xml)}</row>')

    shared_strings_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{total_strings}" uniqueCount="{len(shared_strings)}">'
        + "".join(f"<si><t>{escape(value)}</t></si>" for value in shared_strings)
        + "</sst>"
    )
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
        '<Override PartName="/xl/sharedStrings.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>"
    )
    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(worksheet_rows)}</sheetData>"
        "</worksheet>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", package_rels_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
        archive.writestr("xl/sharedStrings.xml", shared_strings_xml)
    return buffer.getvalue()


def test_iter_excel_rows_falls_back_to_stdlib_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_missing_openpyxl(monkeypatch)

    payload = build_excel_import_file(
        [
            {
                "external_id": "xlsx-1",
                "question_text": "Fallback parser question",
                "question_type": "single",
                "option_a": "A",
                "option_b": "B",
                "answer": "A",
                "knowledge_point_titles": "KP1, KP2",
            }
        ]
    )

    rows = list(_iter_excel_rows(payload))

    assert rows[0][:4] == ("external_id", "question_text", "question_type", "option_a")
    assert rows[1][0] == "xlsx-1"
    assert rows[1][1] == "Fallback parser question"
    assert rows[1][2] == "single"
    assert rows[1][3] == "A"
    assert rows[1][4] == "B"
    assert rows[1][7] == "A"
    assert rows[1][9] == "KP1, KP2"


def test_iter_excel_rows_reads_shared_strings_workbooks(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_missing_openpyxl(monkeypatch)

    payload = _build_shared_strings_excel_file(
        [
            [
                "external_id",
                "question_text",
                "question_type",
                "option_a",
                "option_b",
                "answer",
            ],
            [
                "shared-1",
                "Shared strings question",
                "single",
                "A",
                "B",
                "B",
            ],
        ]
    )

    rows = list(_iter_excel_rows(payload))

    assert rows[0] == (
        "external_id",
        "question_text",
        "question_type",
        "option_a",
        "option_b",
        "answer",
    )
    assert rows[1] == ("shared-1", "Shared strings question", "single", "A", "B", "B")


@pytest.mark.asyncio
async def test_import_questions_excel_continues_without_openpyxl(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_missing_openpyxl(monkeypatch)

    service = QuestionService(question_repo=MagicMock(), job_repo=MagicMock(), kp_repo=None)
    expected = QuestionImportResponse(total=1, created=1, updated=0, skipped=0, failed=0, errors=[])
    service.import_questions_json = AsyncMock(return_value=expected)  # type: ignore[method-assign]

    payload = build_excel_import_file(
        [
            {
                "external_id": "xlsx-2",
                "question_text": "Excel import fallback",
                "question_type": "single",
                "option_a": "3",
                "option_b": "4",
                "answer": "B",
                "explanation": "4 正确",
                "knowledge_point_titles": "集合, 基础",
            }
        ]
    )

    result = await service.import_questions_excel(uuid4(), payload)

    assert result == expected
    service.import_questions_json.assert_awaited_once()

    await_args = service.import_questions_json.await_args
    assert await_args is not None

    _, items = await_args.args
    assert len(items) == 1
    item = items[0]
    assert item.external_id == "xlsx-2"
    assert item.question_text == "Excel import fallback"
    assert item.question_type.value == "single"
    assert [option.model_dump() for option in item.options or []] == [
        {"label": "A", "text": "3"},
        {"label": "B", "text": "4"},
    ]
    assert item.answer == "B"
    assert item.explanation == "4 正确"
    assert item.knowledge_point_titles == ["集合", "基础"]
