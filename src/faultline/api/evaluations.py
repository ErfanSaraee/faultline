"""HTTP API endpoints for evaluating ExecutionRuns and comparing experiment outcomes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from faultline.db.session import get_db_session
from faultline.evaluation.engine import EvaluationEngine
from faultline.repositories.evaluation import EvaluationRepository
from faultline.repositories.workspace import ProjectRepository
from faultline.schemas.evaluation import (
    EvaluationReportResponse,
    RunComparisonResponse,
)


def create_evaluation_router() -> APIRouter:
    """Create the router handling run evaluation and comparison endpoints."""
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["evaluations"],
    )

    @router.post(
        "/runs/{run_id}/evaluate",
        response_model=EvaluationReportResponse,
        summary="Evaluate an execution run against its scenario criteria",
    )
    async def evaluate_run(
        project_id: UUID,
        run_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> EvaluationReportResponse:
        engine = EvaluationEngine(session=session)
        report = await engine.evaluate_run(project_id=project_id, run_id=run_id)
        return EvaluationReportResponse.model_validate(report)

    @router.get(
        "/runs/{run_id}/evaluation",
        response_model=EvaluationReportResponse,
        summary="Get the persisted evaluation report for an execution run",
    )
    async def get_run_evaluation(
        project_id: UUID,
        run_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> EvaluationReportResponse:
        project_repo = ProjectRepository(session)
        await project_repo.get_by_id(project_id)

        eval_repo = EvaluationRepository(session)
        report = await eval_repo.get_by_run_id(project_id=project_id, run_id=run_id)
        return EvaluationReportResponse.model_validate(report)

    @router.get(
        "/evaluations/compare",
        response_model=RunComparisonResponse,
        summary="Compare a baseline run against a fault-injected or candidate run",
    )
    async def compare_runs(
        project_id: UUID,
        baseline_run_id: UUID = Query(  # noqa: B008
            description="UUID of the baseline ExecutionRun"
        ),
        candidate_run_id: UUID = Query(  # noqa: B008
            description="UUID of the candidate or fault-injected ExecutionRun"
        ),
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> RunComparisonResponse:
        engine = EvaluationEngine(session=session)
        return await engine.compare_runs(
            project_id=project_id,
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
        )

    return router
