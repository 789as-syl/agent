"""rename chat_runs.agent_state_json and drop stale shell columns

Revision ID: chat_run_shell_cleanup0420
Revises: drop_run_event_count0420
Create Date: 2026-04-20 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "chat_run_shell_cleanup0420"
down_revision: str | None = "drop_run_event_count0420"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("chat_runs", "agent_state_json", new_column_name="shell_state_json")
    op.drop_index("ix_chat_runs_branch_key", table_name="chat_runs")
    op.drop_column("chat_runs", "branch_key")
    op.drop_column("chat_runs", "last_event_id")
    op.drop_column("chat_runs", "total_steps")
    op.drop_column("chat_runs", "duration_ms")


def downgrade() -> None:
    op.add_column(
        "chat_runs",
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "chat_runs",
        sa.Column("total_steps", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("chat_runs", "total_steps", server_default=None)
    op.add_column(
        "chat_runs",
        sa.Column("last_event_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "chat_runs",
        sa.Column("branch_key", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_chat_runs_branch_key", "chat_runs", ["branch_key"], unique=False)
    op.alter_column("chat_runs", "shell_state_json", new_column_name="agent_state_json")
