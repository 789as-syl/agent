"""add full platform v1 remediation models

Revision ID: full_platform_v1_0426
Revises: add_kp_document_metadata0423
Create Date: 2026-04-26 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "full_platform_v1_0426"
down_revision: str | None = "add_kp_document_metadata0423"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def upgrade() -> None:
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_audit_logs_actor_user_id", "admin_audit_logs", ["actor_user_id"])
    op.create_index("ix_admin_audit_logs_action", "admin_audit_logs", ["action"])
    op.create_index("ix_admin_audit_logs_resource", "admin_audit_logs", ["resource_type", "resource_id"])
    op.create_index("ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"])

    op.create_table(
        "rag_golden_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=True),
        sa.Column("expected_source_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rag_golden_queries_created_by_user_id", "rag_golden_queries", ["created_by_user_id"])
    op.create_index("ix_rag_golden_queries_is_active", "rag_golden_queries", ["is_active"])
    op.create_index("ix_rag_golden_queries_created_at", "rag_golden_queries", ["created_at"])

    op.create_table(
        "rag_eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("golden_query_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_expected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["golden_query_id"], ["rag_golden_queries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rag_eval_runs_golden_query_id", "rag_eval_runs", ["golden_query_id"])
    op.create_index("ix_rag_eval_runs_status", "rag_eval_runs", ["status"])
    op.create_index("ix_rag_eval_runs_created_by_user_id", "rag_eval_runs", ["created_by_user_id"])
    op.create_index("ix_rag_eval_runs_created_at", "rag_eval_runs", ["created_at"])

    op.create_table(
        "practice_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("question_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("current_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_questions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_practice_sessions_user_id", "practice_sessions", ["user_id"])
    op.create_index("ix_practice_sessions_status", "practice_sessions", ["status"])
    op.create_index("ix_practice_sessions_created_at", "practice_sessions", ["created_at"])

    op.create_table(
        "practice_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_answer", sa.Text(), nullable=False),
        sa.Column("correct_answer", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_practice_attempts_session_id", "practice_attempts", ["session_id"])
    op.create_index("ix_practice_attempts_user_id", "practice_attempts", ["user_id"])
    op.create_index("ix_practice_attempts_question_id", "practice_attempts", ["question_id"])

    op.create_table(
        "wrong_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wrong_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_answer", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "question_id", name="uq_wrong_questions_user_question"),
    )
    op.create_index("ix_wrong_questions_user_id", "wrong_questions", ["user_id"])
    op.create_index("ix_wrong_questions_question_id", "wrong_questions", ["question_id"])

    op.create_table(
        "mastery_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("knowledge_point_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mastery_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("attempts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mastery_records_user_id", "mastery_records", ["user_id"])
    op.create_index("ix_mastery_records_question_id", "mastery_records", ["question_id"])
    op.create_index("ix_mastery_records_knowledge_point_id", "mastery_records", ["knowledge_point_id"])

    op.create_table(
        "review_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="due"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ease_factor", sa.Float(), nullable=False, server_default="2.5"),
        sa.Column("last_result", sa.String(length=32), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "question_id", name="uq_review_cards_user_question"),
    )
    op.create_index("ix_review_cards_user_id", "review_cards", ["user_id"])
    op.create_index("ix_review_cards_due_at", "review_cards", ["due_at"])
    op.create_index("ix_review_cards_status", "review_cards", ["status"])

    op.create_table(
        "learning_path_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_point_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_path_items_user_id", "learning_path_items", ["user_id"])
    op.create_index("ix_learning_path_items_status", "learning_path_items", ["status"])
    op.create_index("ix_learning_path_items_priority", "learning_path_items", ["priority"])


def downgrade() -> None:
    for table, indexes in (
        ("learning_path_items", ["ix_learning_path_items_priority", "ix_learning_path_items_status", "ix_learning_path_items_user_id"]),
        ("review_cards", ["ix_review_cards_status", "ix_review_cards_due_at", "ix_review_cards_user_id"]),
        ("mastery_records", ["ix_mastery_records_knowledge_point_id", "ix_mastery_records_question_id", "ix_mastery_records_user_id"]),
        ("wrong_questions", ["ix_wrong_questions_question_id", "ix_wrong_questions_user_id"]),
        ("practice_attempts", ["ix_practice_attempts_question_id", "ix_practice_attempts_user_id", "ix_practice_attempts_session_id"]),
        ("practice_sessions", ["ix_practice_sessions_created_at", "ix_practice_sessions_status", "ix_practice_sessions_user_id"]),
        ("rag_eval_runs", ["ix_rag_eval_runs_created_at", "ix_rag_eval_runs_created_by_user_id", "ix_rag_eval_runs_status", "ix_rag_eval_runs_golden_query_id"]),
        ("rag_golden_queries", ["ix_rag_golden_queries_created_at", "ix_rag_golden_queries_is_active", "ix_rag_golden_queries_created_by_user_id"]),
        ("admin_audit_logs", ["ix_admin_audit_logs_created_at", "ix_admin_audit_logs_resource", "ix_admin_audit_logs_action", "ix_admin_audit_logs_actor_user_id"]),
    ):
        for index_name in indexes:
            op.drop_index(index_name, table_name=table)
        op.drop_table(table)
