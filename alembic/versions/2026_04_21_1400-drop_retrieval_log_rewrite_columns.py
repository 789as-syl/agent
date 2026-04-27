"""drop retrieval log rewrite columns

Revision ID: drop_retrieval_rewrite_cols0421
Revises: chat_run_shell_cleanup0420
Create Date: 2026-04-21 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "drop_retrieval_rewrite_cols0421"
down_revision: str | None = "chat_run_shell_cleanup0420"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("retrieval_logs", "rewritten_statement")
    op.drop_column("retrieval_logs", "rewritten_question")


def downgrade() -> None:
    op.add_column(
        "retrieval_logs",
        sa.Column(
            "rewritten_question",
            sa.Text(),
            nullable=True,
            comment="rewrite question form for retrieval, nullable",
        ),
    )
    op.add_column(
        "retrieval_logs",
        sa.Column(
            "rewritten_statement",
            sa.Text(),
            nullable=True,
            comment="rewrite statement form for retrieval, nullable",
        ),
    )
