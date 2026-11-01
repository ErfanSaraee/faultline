"""HTTP API endpoints for RegressionCase management and Release Gate evaluation."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from faultline.db.session import get_db_session
from faultline.regression.engine import RegressionSuiteEngine
from faultline.repositories.regression import RegressionRepository
from faultline.repositories.workspace import ProjectRepository
from faultline.schemas.regression import (
    RegressionCandidateCreate,
    RegressionCaseResponse,
    RegressionReviewRequest,
    ReleaseGateEvaluationResponse,
    ReleaseGateRunRequest,
)


def create_regression_router() -> APIRouter:
    """Create the router handling regression test lifecycle and release gates."""
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["regression"],
    )

    @router.post(
        "/regression-cases",
        response_model=RegressionCaseResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Generate a candidate regression test from a confirmed diagnosis",
    )
    async def create_regression_candidate(
        project_id: UUID,
        payload: RegressionCandidateCreate,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> RegressionCaseResponse:
        engine = RegressionSuiteEngine(session=session)
        case = await engine.create_candidate_from_run(
            project_id=project_id,
            request=payload,
        )
        return RegressionCaseResponse.model_validate(case)

    @router.get(
        "/regression-cases",
        response_model=list[RegressionCaseResponse],
        summary="List regression test cases for a project",
    )
    async def list_regression_cases(
        project_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> list[RegressionCaseResponse]:
        project_repo = ProjectRepository(session)
        await project_repo.get_by_id(project_id)

        reg_repo = RegressionRepository(session)
        cases = await reg_repo.list_by_project(project_id)
        return [RegressionCaseResponse.model_validate(c) for c in cases]

    @router.post(
        "/regression-cases/{case_id}/review",
        response_model=RegressionCaseResponse,
        summary="Approve or reject a candidate regression test case",
    )
    async def review_regression_case(
        project_id: UUID,
        case_id: UUID,
        payload: RegressionReviewRequest,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> RegressionCaseResponse:
        engine = RegressionSuiteEngine(session=session)
        case = await engine.review_candidate(
            project_id=project_id,
            case_id=case_id,
            request=payload,
        )
        return RegressionCaseResponse.model_validate(case)

    @router.post(
        "/regression-suite/evaluate-release",
        response_model=ReleaseGateEvaluationResponse,
        summary="Execute the approved regression suite and evaluate release gate criteria",
    )
    async def evaluate_release_gate(
        project_id: UUID,
        payload: ReleaseGateRunRequest,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> ReleaseGateEvaluationResponse:
        engine = RegressionSuiteEngine(session=session)
        return await engine.evaluate_release_gate(
            project_id=project_id,
            request=payload,
        )

    return router
