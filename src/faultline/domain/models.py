"""SQLAlchemy ORM domain models for Projects, Agents, Scenarios, Runs, Traces, and Evaluations."""

from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from faultline.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Logical workspace grouping agent configurations, scenarios, and runs."""

    __tablename__ = "projects"

    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    agent_configs: Mapped[list["AgentConfig"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    scenarios: Mapped[list["ScenarioDefinition"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list["ExecutionRun"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class AgentConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Versioned configuration contract for connecting an agent adapter."""

    __tablename__ = "agent_configs"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "name",
            "version",
            name="uq_agent_configs_project_name_version",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    secret_refs: Mapped[dict[str, str]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    project: Mapped["Project"] = relationship(back_populates="agent_configs")


class ScenarioDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Versioned test scenario specification including fixtures, faults, and criteria."""

    __tablename__ = "scenario_definitions"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "name",
            "version",
            name="uq_scenario_definitions_project_name_version",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    spec: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    project: Mapped["Project"] = relationship(back_populates="scenarios")


class ExecutionRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Durable record of a single scenario execution against an agent configuration."""

    __tablename__ = "execution_runs"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    agent_config_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_configs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("scenario_definitions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    run_mode: Mapped[str] = mapped_column(
        String(32), default="baseline", nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_tokens: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False)
    total_latency_ms: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    project: Mapped["Project"] = relationship(back_populates="runs")
    trace_events: Mapped[list["TraceEvent"]] = relationship(
        back_populates="run",
        order_by="TraceEvent.step_index",
        cascade="all, delete-orphan",
    )
    evaluation_report: Mapped["EvaluationReport | None"] = relationship(
        back_populates="run",
        uselist=False,
        cascade="all, delete-orphan",
    )


class TraceEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structured observable step captured during an ExecutionRun."""

    __tablename__ = "trace_events"

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    output_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    latency_ms: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False)
    tokens_used: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False)

    run: Mapped["ExecutionRun"] = relationship(back_populates="trace_events")


class EvaluationReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persisted evaluation outcome and reliability metrics for an ExecutionRun."""

    __tablename__ = "evaluation_reports"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_runs.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("scenario_definitions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    task_succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reliability_score: Mapped[float] = mapped_column(Float, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    assertion_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    run: Mapped["ExecutionRun"] = relationship(
        back_populates="evaluation_report")
