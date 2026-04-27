"""add run event sequence

Revision ID: add_run_event_sequence0417
Revises: add_run_events0417
Create Date: 2026-04-17 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_run_event_sequence0417"
down_revision: str | None = "add_run_events0417"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEQUENCE_NAME = "run_events_sequence_no_seq"


def upgrade() -> None:
    op.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE_NAME} AS BIGINT"))
    op.add_column(
        "run_events",
        sa.Column(
            "sequence_no",
            sa.BigInteger(),
            nullable=True,
            server_default=sa.text(f"nextval('{SEQUENCE_NAME}')"),
            comment="Run event sequence order key",
        ),
    )
    op.execute(sa.text(f"UPDATE run_events SET sequence_no = nextval('{SEQUENCE_NAME}') WHERE sequence_no IS NULL"))
    op.alter_column("run_events", "sequence_no", nullable=False)
    op.create_index("ix_run_events_sequence_no", "run_events", ["sequence_no"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_run_events_sequence_no", table_name="run_events")
    op.drop_column("run_events", "sequence_no")
    op.execute(sa.text(f"DROP SEQUENCE IF EXISTS {SEQUENCE_NAME}"))
