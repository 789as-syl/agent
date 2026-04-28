"""add message feedback

Revision ID: add_message_feedback_0427
Revises: full_platform_v1_0426
Create Date: 2026-04-27 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "add_message_feedback_0427"
down_revision: str | None = "full_platform_v1_0426"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rating", sa.String(length=32), nullable=False),
        sa.Column("evidence_quality", sa.String(length=32), nullable=True),
        sa.Column("hallucination_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["chat_runs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "message_id", name="uq_message_feedback_user_message"),
    )
    op.create_index("ix_message_feedback_user_id", "message_feedback", ["user_id"])
    op.create_index("ix_message_feedback_message_id", "message_feedback", ["message_id"])
    op.create_index("ix_message_feedback_conversation_id", "message_feedback", ["conversation_id"])
    op.create_index("ix_message_feedback_run_id", "message_feedback", ["run_id"])
    op.create_index("ix_message_feedback_rating", "message_feedback", ["rating"])
    op.create_index("ix_message_feedback_hallucination", "message_feedback", ["hallucination_flag"])
    op.create_index("ix_message_feedback_created_at", "message_feedback", ["created_at"])


def downgrade() -> None:
    for index_name in (
        "ix_message_feedback_created_at",
        "ix_message_feedback_hallucination",
        "ix_message_feedback_rating",
        "ix_message_feedback_run_id",
        "ix_message_feedback_conversation_id",
        "ix_message_feedback_message_id",
        "ix_message_feedback_user_id",
    ):
        op.drop_index(index_name, table_name="message_feedback")
    op.drop_table("message_feedback")
