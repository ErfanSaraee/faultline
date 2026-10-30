"""HTTP API endpoints for managing Projects and Agent Configurations."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from faultline.db.session import get_db_session
from faultline.repositories.workspace import AgentConfigRepository, ProjectRepository
from faultline.schemas.workspace import (
    AgentConfigCreate,
    AgentConfigResponse,
    ProjectCreate,
    ProjectResponse,
)


def create_workspace_router() -> APIRouter:
    """Create the router handling Project and AgentConfig endpoints."""
    router = APIRouter(prefix="/projects", tags=["workspace"])

    @router.post(
        "",
        response_model=ProjectResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Create a new project workspace",
    )
    async def create_project(
        payload: ProjectCreate,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> ProjectResponse:
        repo = ProjectRepository(session)
        project = await repo.create(payload)
        return ProjectResponse.model_validate(project)

    @router.get(
        "",
        response_model=list[ProjectResponse],
        summary="List all project workspaces",
    )
    async def list_projects(
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> list[ProjectResponse]:
        repo = ProjectRepository(session)
        projects = await repo.list_all()
        return [ProjectResponse.model_validate(p) for p in projects]

    @router.get(
        "/{project_id}",
        response_model=ProjectResponse,
        summary="Get a project workspace by ID",
    )
    async def get_project(
        project_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> ProjectResponse:
        repo = ProjectRepository(session)
        project = await repo.get_by_id(project_id)
        return ProjectResponse.model_validate(project)

    @router.post(
        "/{project_id}/agents",
        response_model=AgentConfigResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Register a versioned agent configuration in a project",
    )
    async def create_agent_config(
        project_id: UUID,
        payload: AgentConfigCreate,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> AgentConfigResponse:
        project_repo = ProjectRepository(session)
        await project_repo.get_by_id(project_id)

        agent_repo = AgentConfigRepository(session)
        agent_config = await agent_repo.create(project_id=project_id, payload=payload)
        return AgentConfigResponse.model_validate(agent_config)

    @router.get(
        "/{project_id}/agents",
        response_model=list[AgentConfigResponse],
        summary="List versioned agent configurations for a project",
    )
    async def list_agent_configs(
        project_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> list[AgentConfigResponse]:
        project_repo = ProjectRepository(session)
        await project_repo.get_by_id(project_id)

        agent_repo = AgentConfigRepository(session)
        configs = await agent_repo.list_by_project(project_id)
        return [AgentConfigResponse.model_validate(c) for c in configs]

    @router.get(
        "/{project_id}/agents/{agent_id}",
        response_model=AgentConfigResponse,
        summary="Get a specific agent configuration by ID",
    )
    async def get_agent_config(
        project_id: UUID,
        agent_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> AgentConfigResponse:
        project_repo = ProjectRepository(session)
        await project_repo.get_by_id(project_id)

        agent_repo = AgentConfigRepository(session)
        agent_config = await agent_repo.get_by_id(
            project_id=project_id,
            agent_id=agent_id,
        )
        return AgentConfigResponse.model_validate(agent_config)

    return router
