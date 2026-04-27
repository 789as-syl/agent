# ruff: noqa: I001
"""后端包初始化模块：app.models。"""

from app.models.base import Base, TimestampMixin
from app.models.admin_audit_log import AdminAuditLog
from app.models.chat_run import ChatRun
from app.models.conversation_memory import ConversationMemory
from app.models.conversation import Conversation
from app.models.engine import (
    async_engine,
    async_session_factory,
    close_db,
    get_async_engine,
    get_async_session,
    get_celery_session,
    init_db_engine,
)
from app.models.enums import JobStatus, RunStatus
from app.models.ingestion_job import IngestionJob
from app.models.knowledge_point import KnowledgePoint, KnowledgePointChunk
from app.models.learning import (
    LearningPathItem,
    MasteryRecord,
    PracticeAttempt,
    PracticeSession,
    ReviewCard,
    WrongQuestion,
)
from app.models.message import Message
from app.models.question_bank import Question, QuestionBank
from app.models.question_knowledge_point import QuestionKnowledgePoint
from app.models.rag_eval import RagEvalRun, RagGoldenQuery
from app.models.retrieval_log import RetrievalLog
from app.models.run_event import RunEvent
from app.models.user import User
from app.models.vectorization_job import VectorizationJob

__all__ = [
    "AdminAuditLog",
    "Base",
    "ChatRun",
    "Conversation",
    "ConversationMemory",
    "IngestionJob",
    "JobStatus",
    "KnowledgePoint",
    "KnowledgePointChunk",
    "LearningPathItem",
    "MasteryRecord",
    "Message",
    "PracticeAttempt",
    "PracticeSession",
    "Question",
    "QuestionBank",
    "QuestionKnowledgePoint",
    "RagEvalRun",
    "RagGoldenQuery",
    "RetrievalLog",
    "ReviewCard",
    "RunEvent",
    "RunStatus",
    "TimestampMixin",
    "User",
    "VectorizationJob",
    "WrongQuestion",
    "async_engine",
    "async_session_factory",
    "close_db",
    "get_async_session",
    "get_celery_session",
    "init_db_engine",
]


async def init_db() -> None:
    """验证数据库连接可用性。

    注意：不再调用 init_db_engine()，由应用启动时显式调用。
    此方法仅做连通性检查，确保引擎已初始化且数据库可达。
    """
    engine = get_async_engine()
    if engine is None:
        raise RuntimeError("Database engine not initialized. Call init_db_engine() first.")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: None)
