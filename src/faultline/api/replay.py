"""HTTP API endpoints for replaying ExecutionRuns and computing step-level trace diffs."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from faultline.db.session import get_db_session
from faultline.replay.engine import ReplayEngine
from faultline.schemas.replay import (
    ExecutionDiffResponse,
    ReplayRequest,
    ReplayRunResponse,
)


def create_replay_router() -> APIRouter:
    """Create the router handling Replay and Execution Diff endpoints."""
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["replay"],
    )

    @router.post(
        "/runs/{run_id}/replay",
        response_model=ReplayRunResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Replay an execution run (recorded_replay or live_replay) and diff traces",
    )
    async def replay_run(
        project_id: UUID,
        run_id: UUID,
        payload: ReplayRequest,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> ReplayRunResponse:
        engine = ReplayEngine(session=session)
        return await engine.replay_run(
            project_id=project_id,
            source_run_id=run_id,
            request=payload,
        )

    @router.get(
        "/runs/{run_id}/diff/{target_run_id}",
        response_model=ExecutionDiffResponse,
        summary="Compute step-by-step execution trace diff between two runs",
    )
    async def diff_runs(
        project_id: UUID,
        run_id: UUID,
        target_run_id: UUID,
        session: AsyncSession = Depends(get_db_session),  # noqa: B008
    ) -> ExecutionDiffResponse:
        engine = ReplayEngine(session=session)
        return await engine.diff_runs(
            project_id=project_id,
            source_run_id=run_id,
            target_run_id=target_run_id,
        )

    return router
