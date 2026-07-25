"""call_export_jobs table for async call exports

Revision ID: 006
Revises: 005
Create Date: 2026-07-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "call_export_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("filters_json", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), server_default="0"),
        sa.Column("storage_path", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_call_export_jobs_user_id", "call_export_jobs", ["user_id"])
    op.create_index("ix_call_export_jobs_status", "call_export_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_call_export_jobs_status", table_name="call_export_jobs")
    op.drop_index("ix_call_export_jobs_user_id", table_name="call_export_jobs")
    op.drop_table("call_export_jobs")
