"""Persistence repository for RegressionCase entities."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from faultline.core.errors import EntityConflictError, EntityNotFoundError
from faultline.domain.models import RegressionCase


class RegressionRepository:
    """Data access operations for candidate and approved RegressionCase records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self,
        project_id: UUID,
        case_id: UUID,
    ) -> RegressionCase:
        """Fetch a RegressionCase scoped to a Project or raise EntityNotFoundError."""
        result = await self._session.execute(
            select(RegressionCase).where(
                RegressionCase.id == case_id,
                RegressionCase.project_id == project_id,
            )
        )
        case = result.scalar_one_or_none()
        if case is None:
            raise EntityNotFoundError("RegressionCase", str(case_id))
        return case

    async def get_by_name(
        self,
        project_id: UUID,
        name: str,
    ) -> RegressionCase | None:
        """Return a RegressionCase by name within a project if it exists."""
        result = await self._session.execute(
            select(RegressionCase).where(
                RegressionCase.project_id == project_id,
                RegressionCase.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: UUID) -> list[RegressionCase]:
        """Return all RegressionCase records for a project ordered by newest first."""
        result = await self._session.execute(
            select(RegressionCase)
            .where(RegressionCase.project_id == project_id)
            .order_by(RegressionCase.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_approved_by_project(self, project_id: UUID) -> list[RegressionCase]:
        """Return only human-approved RegressionCase records for suite execution."""
        result = await self._session.execute(
            select(RegressionCase)
            .where(
                RegressionCase.project_id == project_id,
                RegressionCase.approval_status == "approved",
            )
            .order_by(RegressionCase.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_candidate(
        self,
        *,
        project_id: UUID,
        source_run_id: UUID,
        scenario_id: UUID,
        name: str,
        description: str | None,
        confirmed_root_cause: str,
        classification_code: str | None,
        review_metadata: dict[str, Any],
    ) -> RegressionCase:
        """Create and persist a candidate RegressionCase."""
        existing = await self.get_by_name(project_id=project_id, name=name)
        if existing is not None:
            raise EntityConflictError(
                f"RegressionCase with name '{name}' already exists in project '{project_id}'."
            )

        case = RegressionCase(
            project_id=project_id,
            source_run_id=source_run_id,
            scenario_id=scenario_id,
            name=name,
            description=description,
            approval_status="candidate",
            confirmed_root_cause=confirmed_root_cause,
            classification_code=classification_code,
            review_metadata=review_metadata,
        )
        self._session.add(case)
        await self._session.commit()
        await self._session.refresh(case)
        return case

    async def update_review_status(
        self,
        *,
        project_id: UUID,
        case_id: UUID,
        approval_status: str,
        review_metadata: dict[str, Any],
    ) -> RegressionCase:
        """Update approval_status and review_metadata on a RegressionCase."""
        case = await self.get_by_id(project_id=project_id, case_id=case_id)
        case.approval_status = approval_status
        case.review_metadata = review_metadata
        await self._session.commit()
        await self._session.refresh(case)
        return case
