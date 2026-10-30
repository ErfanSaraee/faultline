"""HTTP API endpoints for managing versioned ScenarioDefinitions."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from faultline.db.session import get_db_session
from faultline.repositories.scenario import ScenarioRepository
from faultline.repositories.workspace import ProjectRepository
from faultline.schemas.scenario import ScenarioCreate, ScenarioResponse


def create_scenario_router() -> APIRouter:
    """Create the router handling ScenarioDefinition endpoints under a Project."""
    router = APIRouter(
        prefix="/projects/{project_id}/scenarios",
        tags=["scenarios"],
    )

    @router.post(
        "",
        response_model=ScenarioResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Create a versioned test scenario in a project",
    )
    async def create_scenario(
        project_id: UUID,
        payload: ScenarioCreate,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> ScenarioResponse:
        project_repo = ProjectRepository(session)
        await project_repo.get_by_id(project_id)

        scenario_repo = ScenarioRepository(session)
        scenario = await scenario_repo.create(project_id=project_id, payload=payload)
        return ScenarioResponse.model_validate(scenario)

    @router.get(
        "",
        response_model=list[ScenarioResponse],
        summary="List versioned test scenarios for a project",
    )
    async def list_scenarios(
        project_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> list[ScenarioResponse]:
        project_repo = ProjectRepository(session)
        await project_repo.get_by_id(project_id)

        scenario_repo = ScenarioRepository(session)
        scenarios = await scenario_repo.list_by_project(project_id)
        return [ScenarioResponse.model_validate(s) for s in scenarios]

    @router.get(
        "/{scenario_id}",
        response_model=ScenarioResponse,
        summary="Get a specific test scenario by ID",
    )
    async def get_scenario(
        project_id: UUID,
        scenario_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> ScenarioResponse:
        project_repo = ProjectRepository(session)
        await project_repo.get_by_id(project_id)

        scenario_repo = ScenarioRepository(session)
        scenario = await scenario_repo.get_by_id(
            project_id=project_id,
            scenario_id=scenario_id,
        )
        return ScenarioResponse.model_validate(scenario)

    return router
