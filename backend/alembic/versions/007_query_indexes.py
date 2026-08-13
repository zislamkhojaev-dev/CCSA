"""Indexes for call list, dashboard, and latest transcription/analysis lookups.

Revision ID: 007
Revises: 006
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_calls_status", "calls", ["status"])
    op.create_index("ix_calls_operator_id", "calls", ["operator_id"])
    op.create_index("ix_calls_scenario_id", "calls", ["scenario_id"])
    op.create_index("ix_calls_call_timestamp", "calls", ["call_timestamp"])
    op.create_index("ix_calls_created_at", "calls", ["created_at"])
    op.execute(
        "CREATE INDEX ix_calls_effective_ts ON calls (COALESCE(call_timestamp, created_at))"
    )
    op.create_index(
        "ix_transcriptions_call_id_created_at",
        "transcriptions",
        ["call_id", "created_at"],
    )
    op.create_index(
        "ix_analysis_results_call_id_created_at",
        "analysis_results",
        ["call_id", "created_at"],
    )
    op.create_index("ix_analysis_results_total_score", "analysis_results", ["total_score"])
    op.create_index("ix_call_tags_call_id", "call_tags", ["call_id"])
    op.create_index("ix_call_tags_tag_id", "call_tags", ["tag_id"])
    op.create_index("ix_operators_team_name", "operators", ["team_name"])


def downgrade() -> None:
    op.drop_index("ix_operators_team_name", table_name="operators")
    op.drop_index("ix_call_tags_tag_id", table_name="call_tags")
    op.drop_index("ix_call_tags_call_id", table_name="call_tags")
    op.drop_index("ix_analysis_results_total_score", table_name="analysis_results")
    op.drop_index("ix_analysis_results_call_id_created_at", table_name="analysis_results")
    op.drop_index("ix_transcriptions_call_id_created_at", table_name="transcriptions")
    op.execute("DROP INDEX IF EXISTS ix_calls_effective_ts")
    op.drop_index("ix_calls_created_at", table_name="calls")
    op.drop_index("ix_calls_call_timestamp", table_name="calls")
    op.drop_index("ix_calls_scenario_id", table_name="calls")
    op.drop_index("ix_calls_operator_id", table_name="calls")
    op.drop_index("ix_calls_status", table_name="calls")
