"""add run projection repair jobs

Revision ID: run_projection_jobs0417
Revises: add_chat_run_projection0417
Create Date: 2026-04-17 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "run_projection_jobs0417"
down_revision: str | None = "add_chat_run_projection0417"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    job_status_enum = postgresql.ENUM(
        "pending",
        "running",
        "success",
        "failed",
        name="job_status",
        create_type=False,
    )
    op.create_table(
        "run_projection_repair_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("requested_run_id", sa.UUID(), nullable=True),
        sa.Column("status", job_status_enum, nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inconsistent_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("scan_limit", sa.Integer(), nullable=True),
        sa.Column("scanned_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repaired_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_projection_repair_jobs_status", "run_projection_repair_jobs", ["status"], unique=False)
    op.create_index(
        "ix_run_projection_repair_jobs_requested_run_id",
        "run_projection_repair_jobs",
        ["requested_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_run_projection_repair_jobs_created_at",
        "run_projection_repair_jobs",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_run_projection_repair_jobs_created_at", table_name="run_projection_repair_jobs")
    op.drop_index("ix_run_projection_repair_jobs_requested_run_id", table_name="run_projection_repair_jobs")
    op.drop_index("ix_run_projection_repair_jobs_status", table_name="run_projection_repair_jobs")
    op.drop_table("run_projection_repair_jobs")
