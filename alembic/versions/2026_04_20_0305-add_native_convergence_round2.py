"""add active conversation run uniqueness and content blocks

Revision ID: native_convergence0420
Revises: run_projection_jobs0417
Create Date: 2026-04-20 03:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "native_convergence0420"
down_revision: str | None = "run_projection_jobs0417"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "content_blocks_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_index(
        "uq_chat_runs_active_conversation",
        "chat_runs",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index("uq_chat_runs_active_conversation", table_name="chat_runs")
    op.drop_column("messages", "content_blocks_json")
