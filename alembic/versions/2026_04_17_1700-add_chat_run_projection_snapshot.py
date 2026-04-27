"""add chat run projection snapshot

Revision ID: add_chat_run_projection0417
Revises: add_run_event_sequence0417
Create Date: 2026-04-17 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_chat_run_projection0417"
down_revision: str | None = "add_run_event_sequence0417"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_runs",
        sa.Column(
            "trace_projection_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Persisted trace projection snapshot",
        ),
    )
    op.add_column(
        "chat_runs",
        sa.Column(
            "run_event_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Persisted run event count",
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE chat_runs
            SET run_event_count = counts.event_count
            FROM (
                SELECT run_id, COUNT(*)::INTEGER AS event_count
                FROM run_events
                GROUP BY run_id
            ) AS counts
            WHERE chat_runs.id = counts.run_id
            """
        )
    )
    op.alter_column("chat_runs", "run_event_count", server_default=None)


def downgrade() -> None:
    op.drop_column("chat_runs", "run_event_count")
    op.drop_column("chat_runs", "trace_projection_json")
