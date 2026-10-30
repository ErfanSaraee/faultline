"""create execution_runs and trace_events tables

Revision ID: 0003_execution_runs_traces
Revises: 0002_scenario_definitions
Create Date: 2026-10-30 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_execution_runs_traces"
down_revision: str | None = "0002_scenario_definitions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_runs",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("agent_config_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("run_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("adapter_type", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("final_answer", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("total_latency_ms", sa.Float(), nullable=False),
        sa.Column("run_metadata", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_config_id"],
            ["agent_configs.id"],
            name=op.f("fk_execution_runs_agent_config_id_agent_configs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_execution_runs_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenario_definitions.id"],
            name=op.f("fk_execution_runs_scenario_id_scenario_definitions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execution_runs")),
    )
    op.create_index(
        op.f("ix_execution_runs_agent_config_id"),
        "execution_runs",
        ["agent_config_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_execution_runs_project_id"),
        "execution_runs",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_execution_runs_scenario_id"),
        "execution_runs",
        ["scenario_id"],
        unique=False,
    )

    op.create_table(
        "trace_events",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["execution_runs.id"],
            name=op.f("fk_trace_events_run_id_execution_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trace_events")),
    )
    op.create_index(
        op.f("ix_trace_events_run_id"),
        "trace_events",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_trace_events_run_id"), table_name="trace_events")
    op.drop_table("trace_events")
    op.drop_index(op.f("ix_execution_runs_scenario_id"),
                  table_name="execution_runs")
    op.drop_index(op.f("ix_execution_runs_project_id"),
                  table_name="execution_runs")
    op.drop_index(
        op.f("ix_execution_runs_agent_config_id"),
        table_name="execution_runs",
    )
    op.drop_table("execution_runs")
