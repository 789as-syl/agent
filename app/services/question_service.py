"""Question service layer."""

from __future__ import annotations

import importlib
import io
import json
import posixpath
import zipfile
from collections.abc import Iterator, Sequence
from typing import Any
from uuid import UUID
from xml.etree import ElementTree as ET

from celery.exceptions import CeleryError
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.log_config import get_logger
from app.core.redis import redis_client
from app.models.enums import JobStatus
from app.models.question_bank import Question, QuestionType
from app.repositories.knowledge_point_repo import KnowledgePointRepository
from app.repositories.question_repo import QuestionRepository, VectorizationJobRepository, compute_content_hash
from app.schemas.question import (
    QuestionImportItem,
    QuestionImportResponse,
    QuestionVectorizeRequest,
    VectorizationJobResponse,
)
from app.services.admin_analytics_service import invalidate_admin_analytics_cache
from app.services.question_rules import normalize_question_payload
from app.tasks.vectorization_tasks import batch_vectorize

logger = get_logger(__name__)

VECTORIZATION_LOCK_KEY = "vectorization:lock"
VECTORIZATION_LOCK_TIMEOUT = 3600

EXCEL_HEADER_MAPPING: dict[str, list[str]] = {
    "external_id": ["external_id", "id", "编号", "外部编号"],
    "question_text": ["question_text", "question", "题干", "题目"],
    "question_type": ["question_type", "type", "题型"],
    "option_a": ["option_a", "选项a", "a"],
    "option_b": ["option_b", "选项b", "b"],
    "option_c": ["option_c", "选项c", "c"],
    "option_d": ["option_d", "选项d", "d"],
    "answer": ["answer", "答案"],
    "explanation": ["explanation", "解析", "答案解析"],
    "knowledge_point_titles": ["knowledge_point_titles", "knowledge_points", "知识点", "知识点标题"],
}

_XLSX_NAMESPACES = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "office_rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "package_rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_XLSX_REL_ID_ATTR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _iter_excel_rows(file_content: bytes) -> Iterator[tuple[Any, ...]]:
    try:
        openpyxl = importlib.import_module("openpyxl")
    except ImportError:
        logger.info("openpyxl unavailable, falling back to stdlib xlsx parser")
        return _iter_excel_rows_with_stdlib(file_content)

    return _iter_excel_rows_with_openpyxl(file_content, openpyxl)


def _iter_excel_rows_with_openpyxl(file_content: bytes, openpyxl: Any) -> Iterator[tuple[Any, ...]]:
    workbook = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)

    try:
        worksheet = workbook.active
        if worksheet is None:
            raise ValueError("Invalid Excel file")

        for row in worksheet.iter_rows(values_only=True):
            yield tuple(row)
    finally:
        workbook.close()


def _iter_excel_rows_with_stdlib(file_content: bytes) -> Iterator[tuple[Any, ...]]:
    try:
        with zipfile.ZipFile(io.BytesIO(file_content)) as archive:
            sheet_path = _get_first_sheet_path(archive)
            shared_strings = _load_shared_strings(archive)
            sheet_xml = archive.read(sheet_path)
    except KeyError as exc:
        raise ValueError(f"Invalid Excel file: missing workbook part {exc}") from exc
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid Excel file: unreadable zip container") from exc
    except ET.ParseError as exc:
        raise ValueError("Invalid Excel file: malformed XML") from exc

    try:
        root = ET.fromstring(sheet_xml)
    except ET.ParseError as exc:
        raise ValueError("Invalid Excel file: malformed worksheet XML") from exc
    for row in root.findall(".//main:sheetData/main:row", _XLSX_NAMESPACES):
        values: list[Any | None] = []
        next_col = 0

        for cell in row.findall("main:c", _XLSX_NAMESPACES):
            ref = cell.attrib.get("r")
            col_index = _column_index_from_ref(ref) if ref else next_col
            if col_index > len(values):
                values.extend([None] * (col_index - len(values)))

            cell_value = _parse_xlsx_cell_value(cell, shared_strings)
            if col_index == len(values):
                values.append(cell_value)
            else:
                values[col_index] = cell_value

            next_col = col_index + 1

        yield tuple(values)


def _get_first_sheet_path(archive: zipfile.ZipFile) -> str:
    workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
    rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))

    relationship_targets = {
        relation.attrib["Id"]: relation.attrib["Target"]
        for relation in rels_root.findall("package_rel:Relationship", _XLSX_NAMESPACES)
        if relation.attrib.get("Id") and relation.attrib.get("Target")
    }

    for sheet in workbook_root.findall(".//main:sheets/main:sheet", _XLSX_NAMESPACES):
        relationship_id = sheet.attrib.get(_XLSX_REL_ID_ATTR)
        if not relationship_id:
            continue

        target = relationship_targets.get(relationship_id)
        if not target:
            continue

        normalized_target = target.lstrip("/")
        if not normalized_target.startswith("xl/"):
            normalized_target = posixpath.normpath(posixpath.join("xl", normalized_target))
        return normalized_target

    raise ValueError("Invalid Excel file: workbook has no worksheets")


def _load_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        xml_bytes = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []

    root = ET.fromstring(xml_bytes)
    shared_strings: list[str] = []
    for item in root.findall("main:si", _XLSX_NAMESPACES):
        texts = [node.text or "" for node in item.findall(".//main:t", _XLSX_NAMESPACES)]
        shared_strings.append("".join(texts))
    return shared_strings


def _parse_xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> Any | None:
    cell_type = cell.attrib.get("t")

    if cell_type == "inlineStr":
        return _extract_inline_string(cell)

    value_node = cell.find("main:v", _XLSX_NAMESPACES)
    raw_value = value_node.text if value_node is not None else None
    if raw_value is None:
        return _extract_inline_string(cell)

    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)]
        except (ValueError, IndexError):
            return raw_value
    if cell_type == "b":
        return raw_value == "1"
    if cell_type in {"str", "d", "e"}:
        return raw_value
    return _coerce_excel_number(raw_value)


def _extract_inline_string(cell: ET.Element) -> str | None:
    texts = [node.text or "" for node in cell.findall(".//main:t", _XLSX_NAMESPACES)]
    merged = "".join(texts)
    return merged or None


def _coerce_excel_number(raw_value: str) -> int | float | str | None:
    normalized = raw_value.strip()
    if not normalized:
        return None

    try:
        numeric = float(normalized)
    except ValueError:
        return normalized

    if any(marker in normalized.lower() for marker in (".", "e")):
        return numeric
    return int(numeric)


def _column_index_from_ref(cell_ref: str) -> int:
    column = "".join(char for char in cell_ref if char.isalpha()).upper()
    if not column:
        raise ValueError(f"Invalid Excel cell reference: {cell_ref}")

    index = 0
    for char in column:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


class QuestionService:
    def __init__(
        self,
        question_repo: QuestionRepository,
        job_repo: VectorizationJobRepository,
        kp_repo: KnowledgePointRepository | None = None,
    ) -> None:
        self.question_repo = question_repo
        self.job_repo = job_repo
        self.kp_repo = kp_repo

    async def create_question(self, **kwargs: Any) -> Question:
        normalized = normalize_question_payload(
            question_text=kwargs["question_text"],
            question_type=kwargs["question_type"],
            options=kwargs.get("options"),
            answer=kwargs.get("answer"),
            explanation=kwargs.get("explanation"),
        )
        normalized["content_hash"] = compute_content_hash(
            normalized["question_text"],
            normalized.get("options"),
            normalized.get("answer"),
        )

        knowledge_point_ids = kwargs.pop("knowledge_point_ids", [])
        question = await self.question_repo.create(
            bank_id=kwargs["bank_id"],
            external_id=kwargs.get("external_id"),
            content_hash=normalized["content_hash"],
            question_text=normalized["question_text"],
            question_type=normalized["question_type"],
            options=normalized["options"],
            answer=normalized["answer"],
            explanation=normalized["explanation"],
            is_dirty=True,
        )

        if knowledge_point_ids:
            if self.kp_repo:
                existing_points = await self.kp_repo.get_by_ids(knowledge_point_ids)
                existing_ids = {kp.id for kp in existing_points}
                invalid_ids = [str(kp_id) for kp_id in knowledge_point_ids if kp_id not in existing_ids]
                if invalid_ids:
                    raise ValidationError(
                        error_code="KNOWLEDGE_POINT_NOT_FOUND",
                        message="Some knowledge points do not exist",
                        details={"knowledge_point_ids": invalid_ids},
                    )
            await self.question_repo.link_knowledge_points(question.id, knowledge_point_ids)
            refreshed_question = await self.question_repo.get_by_id(question.id)
            if not refreshed_question:
                raise NotFoundError(error_code="QUESTION_NOT_FOUND", message=f"Question {question.id} not found")
            question = refreshed_question

        await invalidate_admin_analytics_cache()
        return question

    async def update_question(self, question_id: UUID, **kwargs: Any) -> Question:
        question = await self.question_repo.get_by_id(question_id)
        if not question:
            raise NotFoundError(error_code="QUESTION_NOT_FOUND", message=f"Question {question_id} not found")

        merged = {
            "question_text": kwargs.get("question_text", question.question_text),
            "question_type": kwargs.get("question_type", question.question_type),
            "options": kwargs.get("options", question.options),
            "answer": kwargs.get("answer", question.answer),
            "explanation": kwargs.get("explanation", question.explanation),
        }
        normalized = normalize_question_payload(**merged)

        updated = await self.question_repo.update(
            question_id,
            question_text=normalized["question_text"],
            question_type=normalized["question_type"],
            options=normalized["options"],
            answer=normalized["answer"],
            explanation=normalized["explanation"],
        )
        if not updated:
            raise NotFoundError(error_code="QUESTION_NOT_FOUND", message=f"Question {question_id} not found")
        await invalidate_admin_analytics_cache()
        return updated

    async def delete_question(self, question_id: UUID) -> bool:
        deleted = await self.question_repo.delete(question_id)
        if not deleted:
            raise NotFoundError(error_code="QUESTION_NOT_FOUND", message=f"Question {question_id} not found")
        await invalidate_admin_analytics_cache()
        return True

    async def list_questions(
        self,
        bank_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
        q: str | None = None,
        question_type: QuestionType | None = None,
        is_dirty: bool | None = None,
    ) -> tuple[list[Question], int]:
        return await self.question_repo.list_questions(
            bank_id=bank_id,
            page=page,
            page_size=page_size,
            q=q,
            question_type=question_type,
            is_dirty=is_dirty,
        )

    async def import_questions_json(
        self,
        bank_id: UUID,
        questions: Sequence[QuestionImportItem | dict[str, Any]],
    ) -> QuestionImportResponse:
        total = len(questions)
        created = 0
        updated = 0
        skipped = 0
        failed = 0
        errors: list[str] = []

        has_data_change = False

        for idx, raw_item in enumerate(questions):
            try:
                item = (
                    raw_item
                    if isinstance(raw_item, QuestionImportItem)
                    else QuestionImportItem.model_validate(raw_item)
                )
                normalized = normalize_question_payload(
                    question_text=item.question_text,
                    question_type=item.question_type,
                    options=[opt.model_dump() for opt in item.options] if item.options else None,
                    answer=item.answer,
                    explanation=item.explanation,
                )
                content_hash = compute_content_hash(
                    normalized["question_text"],
                    normalized.get("options"),
                    normalized.get("answer"),
                )

                question_data = {
                    "question_text": normalized["question_text"],
                    "question_type": normalized["question_type"],
                    "options": normalized["options"],
                    "answer": normalized["answer"],
                    "explanation": normalized["explanation"],
                }

                question, is_created, is_updated = await self.question_repo.upsert_by_external_id_or_hash(
                    bank_id=bank_id,
                    external_id=item.external_id,
                    content_hash=content_hash,
                    **question_data,
                )

                if is_created:
                    created += 1
                    has_data_change = True
                elif is_updated:
                    updated += 1
                    has_data_change = True
                else:
                    skipped += 1

                if item.knowledge_point_titles and self.kp_repo:
                    kp_ids = await self._resolve_knowledge_point_ids(item.knowledge_point_titles)
                    if kp_ids:
                        await self.question_repo.link_knowledge_points(question.id, kp_ids)
                        has_data_change = True
            except (ValidationError, PydanticValidationError) as exc:
                failed += 1
                message = f"Item {idx + 1}: {exc}"
                errors.append(message)
                logger.warning("Question import validation failed", item_index=idx, error=str(exc))
            except Exception as exc:
                failed += 1
                message = f"Item {idx + 1}: {exc}"
                errors.append(message)
                logger.exception("Question import failed", item_index=idx, error=str(exc))

        if has_data_change:
            await invalidate_admin_analytics_cache()

        return QuestionImportResponse(
            total=total,
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=errors,
        )

    async def import_questions_excel(self, bank_id: UUID, file_content: bytes) -> QuestionImportResponse:
        try:
            rows = _iter_excel_rows(file_content)
            header_row = next(rows, None)
            if not header_row:
                raise ValidationError(error_code="EXCEL_NO_HEADER", message="Excel file has no header row")

            mapping = self._parse_excel_header(header_row)
            for required in ("question_text", "question_type", "answer"):
                if required not in mapping:
                    raise ValidationError(
                        error_code="EXCEL_MISSING_REQUIRED_COLUMN",
                        message=f"Excel missing required column: {required}",
                    )

            items: list[QuestionImportItem] = []
            row_errors: list[str] = []
            for row_index, row in enumerate(rows, start=2):
                if not any(cell is not None and str(cell).strip() for cell in row):
                    continue
                try:
                    item = self._parse_excel_row_with_header(row, mapping)
                    items.append(item)
                except Exception as exc:
                    message = f"Row {row_index}: {exc}"
                    row_errors.append(message)
                    logger.warning("Skipping invalid excel row", row=row_index, error=str(exc))

            if not items:
                raise ValidationError(error_code="EXCEL_EMPTY", message="Excel file has no valid rows")

            result = await self.import_questions_json(bank_id, items)
            if row_errors:
                return QuestionImportResponse(
                    total=result.total + len(row_errors),
                    created=result.created,
                    updated=result.updated,
                    skipped=result.skipped,
                    failed=result.failed + len(row_errors),
                    errors=[*row_errors, *result.errors],
                )
            return result

        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(error_code="EXCEL_PARSE_ERROR", message=f"Failed to parse Excel file: {exc}") from exc

    def _parse_excel_header(self, header_row: tuple[Any, ...]) -> dict[str, int]:
        mapping: dict[str, int] = {}

        for idx, cell in enumerate(header_row):
            if cell is None:
                continue
            value = str(cell).strip().lower()
            for standard, aliases in EXCEL_HEADER_MAPPING.items():
                if value in {alias.lower() for alias in aliases}:
                    mapping[standard] = idx
                    break

        return mapping

    def _parse_excel_row_with_header(self, row: tuple[Any, ...], mapping: dict[str, int]) -> QuestionImportItem:
        def get_value(key: str) -> Any | None:
            if key not in mapping:
                return None
            col = mapping[key]
            return row[col] if col < len(row) else None

        question_text = get_value("question_text")
        question_type = get_value("question_type")
        answer = get_value("answer")

        if not question_text or not question_type or not answer:
            raise ValueError("Missing required fields")

        options: list[dict[str, str]] = []
        for label in ["A", "B", "C", "D"]:
            option_value = get_value(f"option_{label.lower()}")
            if option_value is not None and str(option_value).strip():
                options.append({"label": label, "text": str(option_value).strip()})

        kp_titles_raw = get_value("knowledge_point_titles")
        kp_titles = [item.strip() for item in str(kp_titles_raw or "").split(",") if item and item.strip()]

        payload = {
            "external_id": str(get_value("external_id")).strip() if get_value("external_id") is not None else None,
            "question_text": str(question_text).strip(),
            "question_type": str(question_type).strip(),
            "options": options or None,
            "answer": str(answer).strip(),
            "explanation": str(get_value("explanation")).strip() if get_value("explanation") is not None else None,
            "knowledge_point_titles": kp_titles,
        }
        return QuestionImportItem.model_validate(payload)

    async def trigger_vectorization(self, request: QuestionVectorizeRequest) -> VectorizationJobResponse:
        lock_acquired = await redis_client.set(
            VECTORIZATION_LOCK_KEY,
            "1",
            nx=True,
            ex=VECTORIZATION_LOCK_TIMEOUT,
        )
        if not lock_acquired:
            raise ConflictError(
                error_code="VECTORIZATION_IN_PROGRESS",
                message="A vectorization task is already running. Please wait for completion.",
            )

        try:
            total = await self.question_repo.count_vectorization_candidates(only_dirty=request.only_dirty)
            if request.only_dirty and total == 0:
                raise ValidationError(error_code="NO_DIRTY_QUESTIONS", message="No dirty questions to vectorize")

            job = await self.job_repo.create(
                status=JobStatus.PENDING,
                total_questions=total,
                processed_questions=0,
                progress=0,
            )
            await self.job_repo.session.commit()

            try:
                task = batch_vectorize.apply_async(
                    args=[str(job.id), request.only_dirty, request.batch_size],
                    task_id=f"vectorize_{job.id}",
                )
            except CeleryError as exc:
                await self.job_repo.update_status(
                    job.id,
                    status=JobStatus.FAILED,
                    error_message=f"Failed to dispatch vectorization task: {exc}",
                )
                await self.job_repo.session.commit()
                raise ValidationError(
                    error_code="VECTORIZATION_TASK_DISPATCH_FAILED",
                    message=f"Failed to dispatch vectorization task: {exc}",
                ) from exc

            await self.job_repo.update_status(job.id, celery_task_id=task.id)
            await self.job_repo.session.commit()
            logger.info("Vectorization task dispatched", job_id=str(job.id), task_id=task.id)
            return VectorizationJobResponse.model_validate(job)

        except Exception:
            await redis_client.delete(VECTORIZATION_LOCK_KEY)
            raise

    async def get_vectorization_job(self, job_id: UUID) -> VectorizationJobResponse:
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            raise NotFoundError(
                error_code="VECTORIZATION_JOB_NOT_FOUND",
                message=f"Vectorization job {job_id} not found",
            )
        return VectorizationJobResponse.model_validate(job)

    async def link_knowledge_points(self, question_id: UUID, knowledge_point_ids: list[UUID]) -> bool:
        question = await self.question_repo.get_by_id(question_id)
        if not question:
            raise NotFoundError(error_code="QUESTION_NOT_FOUND", message=f"Question {question_id} not found")

        if knowledge_point_ids and self.kp_repo:
            existing_points = await self.kp_repo.get_by_ids(knowledge_point_ids)
            existing_ids = {kp.id for kp in existing_points}
            invalid_ids = [str(kp_id) for kp_id in knowledge_point_ids if kp_id not in existing_ids]
            if invalid_ids:
                raise ValidationError(
                    error_code="KNOWLEDGE_POINT_NOT_FOUND",
                    message="Some knowledge points do not exist",
                    details={"knowledge_point_ids": invalid_ids},
                )

        await self.question_repo.link_knowledge_points(question_id, knowledge_point_ids)
        await invalidate_admin_analytics_cache()
        return True

    async def unlink_knowledge_point(self, question_id: UUID, knowledge_point_id: UUID) -> bool:
        deleted = await self.question_repo.delete_knowledge_point_link(question_id, knowledge_point_id)
        if not deleted:
            raise NotFoundError(error_code="LINK_NOT_FOUND", message="Knowledge point link not found")
        await invalidate_admin_analytics_cache()
        return True

    async def _resolve_knowledge_point_ids(self, titles: list[str]) -> list[UUID]:
        if not self.kp_repo or not titles:
            return []
        points = await self.kp_repo.get_by_titles(titles)
        return [kp.id for kp in points]


async def parse_json_import_payload(raw_json: str) -> tuple[UUID, list[dict[str, Any]]]:
    """Parse form json_data payload into bank id and raw question rows."""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValidationError(error_code="INVALID_JSON", message=f"Invalid JSON data: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValidationError(error_code="INVALID_JSON", message="JSON import payload must be an object")

    raw_bank_id = payload.get("bank_id")
    raw_questions = payload.get("questions")
    if raw_bank_id is None:
        raise ValidationError(error_code="BANK_ID_REQUIRED", message="bank_id is required")
    if not isinstance(raw_questions, list):
        raise ValidationError(error_code="QUESTIONS_REQUIRED", message="questions must be a list")

    try:
        bank_id = UUID(str(raw_bank_id))
    except ValueError as exc:
        raise ValidationError(error_code="INVALID_BANK_ID", message="Invalid bank_id") from exc

    return bank_id, raw_questions
