"""HTTP API endpoints for triggering ExecutionRuns and inspecting TraceEvents."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from faultline.db.session import get_db_session
from faultline.execution.engine import BaselineExecutionEngine
from faultline.repositories.execution import ExecutionRunRepository
from faultline.repositories.workspace import ProjectRepository
from faultline.schemas.execution import (
    ExecutionRunResponse,
    RunCreateRequest,
    TraceEventResponse,
)


def create_run_router() -> APIRouter:
    """Create the router handling ExecutionRun and TraceEvent endpoints."""
    router = APIRouter(
        prefix="/projects/{project_id}/runs",
        tags=["runs"],
    )

    @router.post(
        "",
        response_model=ExecutionRunResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Execute a scenario run and capture structured trace events",
    )
    async def create_run(
        project_id: UUID,
        payload: RunCreateRequest,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> ExecutionRunResponse:
        engine = BaselineExecutionEngine(session=session)
        run = await engine.execute_run(project_id=project_id, request=payload)
        return ExecutionRunResponse.model_validate(run)

    @router.get(
        "",
        response_model=list[ExecutionRunResponse],
        summary="List execution runs for a project",
    )
    async def list_runs(
        project_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> list[ExecutionRunResponse]:
        project_repo = ProjectRepository(session)
        await project_repo.get_by_id(project_id)

        run_repo = ExecutionRunRepository(session)
        runs = await run_repo.list_by_project(project_id)
        return [ExecutionRunResponse.model_validate(r) for r in runs]

    @router.get(
        "/{run_id}",
        response_model=ExecutionRunResponse,
        summary="Get a specific execution run with its captured trace events",
    )
    async def get_run(
        project_id: UUID,
        run_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> ExecutionRunResponse:
        project_repo = ProjectRepository(session)
        await project_repo.get_by_id(project_id)

        run_repo = ExecutionRunRepository(session)
        run = await run_repo.get_by_id(project_id=project_id, run_id=run_id)
        return ExecutionRunResponse.model_validate(run)

    @router.get(
        "/{run_id}/traces",
        response_model=list[TraceEventResponse],
        summary="Get ordered observable trace events for an execution run",
    )
    async def list_run_traces(
        project_id: UUID,
        run_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> list[TraceEventResponse]:
        project_repo = ProjectRepository(session)
        await project_repo.get_by_id(project_id)

        run_repo = ExecutionRunRepository(session)
        traces = await run_repo.list_trace_events(
            project_id=project_id,
            run_id=run_id,
        )
        return [TraceEventResponse.model_validate(t) for t in traces]

    return router
