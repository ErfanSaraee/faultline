"""create regression_cases table

Revision ID: 0006_regression_cases
Revises: 0005_diagnosis_reports
Create Date: 2026-10-31 23:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_regression_cases"
down_revision: str | None = "0005_diagnosis_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "regression_cases",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("approval_status", sa.String(length=32), nullable=False),
        sa.Column("confirmed_root_cause", sa.Text(), nullable=False),
        sa.Column("classification_code", sa.String(length=128), nullable=True),
        sa.Column("review_metadata", sa.JSON(), nullable=False),
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
            name=op.f("fk_regression_cases_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenario_definitions.id"],
            name=op.f("fk_regression_cases_scenario_id_scenario_definitions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["execution_runs.id"],
            name=op.f("fk_regression_cases_source_run_id_execution_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_regression_cases")),
        sa.UniqueConstraint(
            "project_id",
            "name",
            name="uq_regression_cases_project_name",
        ),
    )
    op.create_index(
        op.f("ix_regression_cases_project_id"),
        "regression_cases",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_regression_cases_scenario_id"),
        "regression_cases",
        ["scenario_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_regression_cases_source_run_id"),
        "regression_cases",
        ["source_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_regression_cases_source_run_id"),
        table_name="regression_cases",
    )
    op.drop_index(
        op.f("ix_regression_cases_scenario_id"),
        table_name="regression_cases",
    )
    op.drop_index(
        op.f("ix_regression_cases_project_id"),
        table_name="regression_cases",
    )
    op.drop_table("regression_cases")
