"""Persistence repository for versioned ScenarioDefinition entities."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from faultline.core.errors import EntityConflictError, EntityNotFoundError
from faultline.domain.models import ScenarioDefinition
from faultline.schemas.scenario import ScenarioCreate


class ScenarioRepository:
    """Data access operations for versioned ScenarioDefinition entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self,
        project_id: UUID,
        scenario_id: UUID,
    ) -> ScenarioDefinition:
        """Fetch a ScenarioDefinition scoped to a Project or raise EntityNotFoundError."""
        result = await self._session.execute(
            select(ScenarioDefinition).where(
                ScenarioDefinition.id == scenario_id,
                ScenarioDefinition.project_id == project_id,
            )
        )
        scenario = result.scalar_one_or_none()
        if scenario is None:
            raise EntityNotFoundError("ScenarioDefinition", str(scenario_id))
        return scenario

    async def get_by_name_and_version(
        self,
        project_id: UUID,
        name: str,
        version: int,
    ) -> ScenarioDefinition | None:
        """Check if a specific (project_id, name, version) scenario exists."""
        result = await self._session.execute(
            select(ScenarioDefinition).where(
                ScenarioDefinition.project_id == project_id,
                ScenarioDefinition.name == name,
                ScenarioDefinition.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: UUID) -> list[ScenarioDefinition]:
        """Return all scenarios for a project ordered by name and descending version."""
        result = await self._session.execute(
            select(ScenarioDefinition)
            .where(ScenarioDefinition.project_id == project_id)
            .order_by(ScenarioDefinition.name.asc(), ScenarioDefinition.version.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        project_id: UUID,
        payload: ScenarioCreate,
    ) -> ScenarioDefinition:
        """Create and persist a versioned ScenarioDefinition within a Project."""
        existing = await self.get_by_name_and_version(
            project_id=project_id,
            name=payload.name,
            version=payload.version,
        )
        if existing is not None:
            raise EntityConflictError(
                f"ScenarioDefinition '{payload.name}' version {payload.version} "
                f"already exists in project '{project_id}'."
            )

        scenario = ScenarioDefinition(
            project_id=project_id,
            name=payload.name,
            version=payload.version,
            description=payload.description,
            spec=payload.spec.model_dump(mode="json"),
        )
        self._session.add(scenario)
        await self._session.commit()
        await self._session.refresh(scenario)
        return scenario
