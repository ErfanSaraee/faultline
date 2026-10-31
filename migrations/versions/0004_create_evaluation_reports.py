"""create evaluation_reports table

Revision ID: 0004_evaluation_reports
Revises: 0003_execution_runs_traces
Create Date: 2026-10-31 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_evaluation_reports"
down_revision: str | None = "0003_execution_runs_traces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_reports",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("task_succeeded", sa.Boolean(), nullable=False),
        sa.Column("reliability_score", sa.Float(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("assertion_results", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
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
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_evaluation_reports_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["execution_runs.id"],
            name=op.f("fk_evaluation_reports_run_id_execution_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenario_definitions.id"],
            name=op.f("fk_evaluation_reports_scenario_id_scenario_definitions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_reports")),
        sa.UniqueConstraint("run_id", name=op.f(
            "uq_evaluation_reports_run_id")),
    )
    op.create_index(
        op.f("ix_evaluation_reports_project_id"),
        "evaluation_reports",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_reports_run_id"),
        "evaluation_reports",
        ["run_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_evaluation_reports_scenario_id"),
        "evaluation_reports",
        ["scenario_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_evaluation_reports_scenario_id"),
        table_name="evaluation_reports",
    )
    op.drop_index(
        op.f("ix_evaluation_reports_run_id"),
        table_name="evaluation_reports",
    )
    op.drop_index(
        op.f("ix_evaluation_reports_project_id"),
        table_name="evaluation_reports",
    )
    op.drop_table("evaluation_reports")
