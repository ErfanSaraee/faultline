"""SQLAlchemy ORM domain models for Projects, AgentConfigs, and ScenarioDefinitions."""

from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
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
