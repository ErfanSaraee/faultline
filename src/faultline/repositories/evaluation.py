"""Persistence repository for EvaluationReport entities."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from faultline.core.errors import EntityNotFoundError
from faultline.domain.models import EvaluationReport
from faultline.schemas.evaluation import AssertionResult, EvaluationMetrics


class EvaluationRepository:
    """Data access operations for durable EvaluationReport records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_run_id(
        self,
        project_id: UUID,
        run_id: UUID,
    ) -> EvaluationReport:
        """Fetch an EvaluationReport for a specific run or raise EntityNotFoundError."""
        result = await self._session.execute(
            select(EvaluationReport).where(
                EvaluationReport.project_id == project_id,
                EvaluationReport.run_id == run_id,
            )
        )
        report = result.scalar_one_or_none()
        if report is None:
            raise EntityNotFoundError("EvaluationReport for run", str(run_id))
        return report

    async def get_optional_by_run_id(
        self,
        project_id: UUID,
        run_id: UUID,
    ) -> EvaluationReport | None:
        """Return an EvaluationReport for a run if it exists, otherwise None."""
        result = await self._session.execute(
            select(EvaluationReport).where(
                EvaluationReport.project_id == project_id,
                EvaluationReport.run_id == run_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_report(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        scenario_id: UUID,
        task_succeeded: bool,
        reliability_score: float,
        metrics: EvaluationMetrics,
        assertion_results: list[AssertionResult],
        summary: str,
    ) -> EvaluationReport:
        """Create or update the EvaluationReport for a specific ExecutionRun."""
        existing = await self.get_optional_by_run_id(
            project_id=project_id,
            run_id=run_id,
        )
        serialized_metrics = metrics.model_dump(mode="json")
        serialized_assertions = [a.model_dump(
            mode="json") for a in assertion_results]

        if existing is not None:
            existing.task_succeeded = task_succeeded
            existing.reliability_score = reliability_score
            existing.metrics = serialized_metrics
            existing.assertion_results = serialized_assertions
            existing.summary = summary
            await self._session.commit()
            await self._session.refresh(existing)
            return existing

        report = EvaluationReport(
            project_id=project_id,
            run_id=run_id,
            scenario_id=scenario_id,
            task_succeeded=task_succeeded,
            reliability_score=reliability_score,
            metrics=serialized_metrics,
            assertion_results=serialized_assertions,
            summary=summary,
        )
        self._session.add(report)
        await self._session.commit()
        await self._session.refresh(report)
        return report
