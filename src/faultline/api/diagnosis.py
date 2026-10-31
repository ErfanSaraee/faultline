"""HTTP API endpoints for evidence-based failure diagnosis and human confirmation."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from faultline.db.session import get_db_session
from faultline.diagnosis.engine import DiagnosisEngine
from faultline.repositories.diagnosis import DiagnosisRepository
from faultline.repositories.workspace import ProjectRepository
from faultline.schemas.diagnosis import (
    DiagnosisReportResponse,
    HumanConfirmationRequest,
)


def create_diagnosis_router() -> APIRouter:
    """Create the router handling failure diagnosis and human confirmation endpoints."""
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["diagnosis"],
    )

    @router.post(
        "/runs/{run_id}/diagnose",
        response_model=DiagnosisReportResponse,
        summary="Generate an evidence-based diagnosis report for an execution run",
    )
    async def diagnose_run(
        project_id: UUID,
        run_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> DiagnosisReportResponse:
        engine = DiagnosisEngine(session=session)
        report = await engine.diagnose_run(project_id=project_id, run_id=run_id)
        return DiagnosisReportResponse.model_validate(report)

    @router.get(
        "/runs/{run_id}/diagnosis",
        response_model=DiagnosisReportResponse,
        summary="Get the persisted diagnosis report for an execution run",
    )
    async def get_run_diagnosis(
        project_id: UUID,
        run_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> DiagnosisReportResponse:
        project_repo = ProjectRepository(session)
        await project_repo.get_by_id(project_id)

        diag_repo = DiagnosisRepository(session)
        report = await diag_repo.get_by_run_id(project_id=project_id, run_id=run_id)
        return DiagnosisReportResponse.model_validate(report)

    @router.post(
        "/runs/{run_id}/diagnosis/confirm",
        response_model=DiagnosisReportResponse,
        summary="Record human confirmation of the root cause on a diagnosis report",
    )
    async def confirm_run_diagnosis(
        project_id: UUID,
        run_id: UUID,
        payload: HumanConfirmationRequest,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> DiagnosisReportResponse:
        engine = DiagnosisEngine(session=session)
        report = await engine.confirm_diagnosis(
            project_id=project_id,
            run_id=run_id,
            request=payload,
        )
        return DiagnosisReportResponse.model_validate(report)

    return router
