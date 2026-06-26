"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("login", sa.String(100), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), server_default="supervisor"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "operators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("webitel_id", sa.String(50), unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("team_name", sa.String(100)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
    )
    op.create_table(
        "scenarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("system_prompt", sa.Text(), server_default=""),
        sa.Column("llm_model", sa.String(100), server_default="gpt-4o-mini"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "criteria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("scenarios.id", ondelete="CASCADE")),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("weight_percent", sa.Integer(), server_default="10"),
        sa.Column("max_score", sa.Integer(), server_default="10"),
        sa.Column("prompt", sa.Text(), server_default=""),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
    )
    op.create_table(
        "calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_uuid", postgresql.UUID(as_uuid=True), unique=True, nullable=False),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("operators.id")),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("scenarios.id")),
        sa.Column("direction", sa.String(20)),
        sa.Column("duration", sa.Integer()),
        sa.Column("client_number", sa.String(50)),
        sa.Column("audio_path", sa.Text()),
        sa.Column("call_timestamp", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("error_message", sa.Text()),
        sa.Column("source", sa.String(50), server_default="webitel"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "transcriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id", sa.Integer(), sa.ForeignKey("calls.id", ondelete="CASCADE")),
        sa.Column("full_text", sa.Text()),
        sa.Column("utterances", postgresql.JSONB()),
        sa.Column("model_name", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "analysis_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id", sa.Integer(), sa.ForeignKey("calls.id", ondelete="CASCADE")),
        sa.Column("llm_model", sa.String(50)),
        sa.Column("total_score", sa.Integer()),
        sa.Column("is_violation", sa.Boolean(), server_default="false"),
        sa.Column("summary", sa.Text()),
        sa.Column("client_pains", sa.Text()),
        sa.Column("call_outcome", sa.String(100)),
        sa.Column("criteria_results", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "call_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id", sa.Integer(), sa.ForeignKey("calls.id", ondelete="CASCADE")),
        sa.Column("tag", sa.String(100), nullable=False),
        sa.UniqueConstraint("call_id", "tag", name="uq_call_tag"),
    )
    op.create_table(
        "supervisor_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id", sa.Integer(), sa.ForeignKey("calls.id", ondelete="CASCADE")),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "playground_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("scenarios.id")),
        sa.Column("use_scenario_prompt", sa.Boolean(), server_default="true"),
        sa.Column("custom_prompt", sa.Text()),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "playground_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("playground_jobs.id", ondelete="CASCADE")),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "playground_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("playground_files.id", ondelete="CASCADE"), unique=True),
        sa.Column("transcription", postgresql.JSONB()),
        sa.Column("analysis", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(100), unique=True, nullable=False),
        sa.Column("value_encrypted", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("stats_json", postgresql.JSONB()),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("error_message", sa.Text()),
    )
    op.create_table(
        "automation_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("is_enabled", sa.Boolean(), server_default="true"),
        sa.Column("schedule_cron", sa.String(100), server_default="*/30 * * * *"),
        sa.Column("batch_size", sa.Integer(), server_default="10"),
        sa.Column("active_days", postgresql.JSONB(), server_default="[]"),
        sa.Column("time_from", sa.String(10)),
        sa.Column("time_to", sa.String(10)),
        sa.Column("default_scenario_id", sa.Integer(), sa.ForeignKey("scenarios.id")),
    )


def downgrade() -> None:
    for t in [
        "automation_rules",
        "sync_runs",
        "app_settings",
        "playground_results",
        "playground_files",
        "playground_jobs",
        "supervisor_notes",
        "call_tags",
        "analysis_results",
        "transcriptions",
        "calls",
        "criteria",
        "scenarios",
        "operators",
        "users",
    ]:
        op.drop_table(t)
