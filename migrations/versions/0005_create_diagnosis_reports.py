"""create diagnosis_reports table

Revision ID: 0005_diagnosis_reports
Revises: 0004_evaluation_reports
Create Date: 2026-10-31 22:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_diagnosis_reports"
down_revision: str | None = "0004_evaluation_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnosis_reports",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("confirmation_status", sa.String(length=32), nullable=False),
        sa.Column("observed_facts", sa.JSON(), nullable=False),
        sa.Column("rule_classifications", sa.JSON(), nullable=False),
        sa.Column("model_hypotheses", sa.JSON(), nullable=False),
        sa.Column("human_confirmed_cause", sa.JSON(), nullable=True),
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
            name=op.f("fk_diagnosis_reports_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["execution_runs.id"],
            name=op.f("fk_diagnosis_reports_run_id_execution_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenario_definitions.id"],
            name=op.f("fk_diagnosis_reports_scenario_id_scenario_definitions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagnosis_reports")),
        sa.UniqueConstraint("run_id", name=op.f(
            "uq_diagnosis_reports_run_id")),
    )
    op.create_index(
        op.f("ix_diagnosis_reports_project_id"),
        "diagnosis_reports",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_diagnosis_reports_run_id"),
        "diagnosis_reports",
        ["run_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_diagnosis_reports_scenario_id"),
        "diagnosis_reports",
        ["scenario_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_diagnosis_reports_scenario_id"),
        table_name="diagnosis_reports",
    )
    op.drop_index(
        op.f("ix_diagnosis_reports_run_id"),
        table_name="diagnosis_reports",
    )
    op.drop_index(
        op.f("ix_diagnosis_reports_project_id"),
        table_name="diagnosis_reports",
    )
    op.drop_table("diagnosis_reports")
