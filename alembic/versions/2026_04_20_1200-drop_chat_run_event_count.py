"""drop unused chat_runs.run_event_count

Revision ID: drop_run_event_count0420
Revises: native_convergence0420
Create Date: 2026-04-20 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "drop_run_event_count0420"
down_revision: str | None = "native_convergence0420"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("chat_runs", "run_event_count")


def downgrade() -> None:
    op.add_column(
        "chat_runs",
        sa.Column(
            "run_event_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.alter_column("chat_runs", "run_event_count", server_default=None)
