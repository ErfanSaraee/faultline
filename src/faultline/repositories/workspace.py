"""Persistence repositories for Project and AgentConfig entities."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from faultline.core.errors import EntityConflictError, EntityNotFoundError
from faultline.domain.models import AgentConfig, Project
from faultline.schemas.workspace import AgentConfigCreate, ProjectCreate


class ProjectRepository:
    """Data access operations for Project workspaces."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, project_id: UUID) -> Project:
        """Fetch a Project by UUID or raise EntityNotFoundError."""
        result = await self._session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise EntityNotFoundError("Project", str(project_id))
        return project

    async def get_by_slug(self, slug: str) -> Project | None:
        """Fetch a Project by its unique slug if it exists."""
        result = await self._session.execute(
            select(Project).where(Project.slug == slug)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Project]:
        """Return all projects ordered by creation timestamp descending."""
        result = await self._session.execute(
            select(Project).order_by(Project.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, payload: ProjectCreate) -> Project:
        """Create and persist a new Project workspace."""
        existing = await self.get_by_slug(payload.slug)
        if existing is not None:
            raise EntityConflictError(
                f"Project with slug '{payload.slug}' already exists."
            )

        project = Project(
            slug=payload.slug,
            name=payload.name,
            description=payload.description,
        )
        self._session.add(project)
        await self._session.commit()
        await self._session.refresh(project)
        return project


class AgentConfigRepository:
    """Data access operations for versioned AgentConfig entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, project_id: UUID, agent_id: UUID) -> AgentConfig:
        """Fetch an AgentConfig scoped to a Project or raise EntityNotFoundError."""
        result = await self._session.execute(
            select(AgentConfig).where(
                AgentConfig.id == agent_id,
                AgentConfig.project_id == project_id,
            )
        )
        agent_config = result.scalar_one_or_none()
        if agent_config is None:
            raise EntityNotFoundError("AgentConfig", str(agent_id))
        return agent_config

    async def get_by_name_and_version(
        self,
        project_id: UUID,
        name: str,
        version: int,
    ) -> AgentConfig | None:
        """Check if a specific (project_id, name, version) combination exists."""
        result = await self._session.execute(
            select(AgentConfig).where(
                AgentConfig.project_id == project_id,
                AgentConfig.name == name,
                AgentConfig.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: UUID) -> list[AgentConfig]:
        """Return all AgentConfigs for a project ordered by name and version."""
        result = await self._session.execute(
            select(AgentConfig)
            .where(AgentConfig.project_id == project_id)
            .order_by(AgentConfig.name.asc(), AgentConfig.version.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        project_id: UUID,
        payload: AgentConfigCreate,
    ) -> AgentConfig:
        """Create and persist a versioned AgentConfig within a Project."""
        existing = await self.get_by_name_and_version(
            project_id=project_id,
            name=payload.name,
            version=payload.version,
        )
        if existing is not None:
            raise EntityConflictError(
                f"AgentConfig '{payload.name}' version {payload.version} "
                f"already exists in project '{project_id}'."
            )

        agent_config = AgentConfig(
            project_id=project_id,
            name=payload.name,
            version=payload.version,
            adapter_type=payload.adapter_type,
            model_name=payload.model_name,
            system_prompt=payload.system_prompt,
            config_payload=payload.config_payload,
            secret_refs=payload.secret_refs,
        )
        self._session.add(agent_config)
        await self._session.commit()
        await self._session.refresh(agent_config)
        return agent_config
