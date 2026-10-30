"""Persistence repository for ExecutionRun and TraceEvent entities."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from faultline.core.errors import EntityNotFoundError
from faultline.domain.models import ExecutionRun, TraceEvent
from faultline.schemas.adapter import AgentExecutionOutput


class ExecutionRunRepository:
    """Data access operations for durable ExecutionRun and TraceEvent records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_from_output(
        self,
        *,
        project_id: UUID,
        agent_config_id: UUID,
        scenario_id: UUID,
        run_mode: str,
        execution_output: AgentExecutionOutput,
        run_metadata: dict[str, Any],
    ) -> ExecutionRun:
        """Persist an ExecutionRun and all of its ordered TraceEvent records."""
        trace_events = [
            TraceEvent(
                step_index=step.step_index,
                step_type=step.step_type,
                name=step.name,
                status=step.status,
                input_payload=step.input_payload,
                output_payload=step.output_payload,
                latency_ms=step.latency_ms,
                tokens_used=step.tokens_used,
            )
            for step in execution_output.steps
        ]

        run = ExecutionRun(
            project_id=project_id,
            agent_config_id=agent_config_id,
            scenario_id=scenario_id,
            run_mode=run_mode,
            status=execution_output.status,
            adapter_type=execution_output.adapter_type,
            model_name=execution_output.model_name,
            final_answer=execution_output.final_answer,
            error_message=execution_output.error_message,
            total_tokens=execution_output.total_tokens,
            total_latency_ms=execution_output.total_latency_ms,
            run_metadata=run_metadata,
            trace_events=trace_events,
        )
        self._session.add(run)
        await self._session.commit()
        return await self.get_by_id(project_id=project_id, run_id=run.id)

    async def get_by_id(self, project_id: UUID, run_id: UUID) -> ExecutionRun:
        """Fetch an ExecutionRun with eager-loaded trace_events or raise EntityNotFoundError."""
        result = await self._session.execute(
            select(ExecutionRun)
            .options(selectinload(ExecutionRun.trace_events))
            .where(
                ExecutionRun.id == run_id,
                ExecutionRun.project_id == project_id,
            )
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise EntityNotFoundError("ExecutionRun", str(run_id))
        return run

    async def list_by_project(self, project_id: UUID) -> list[ExecutionRun]:
        """Return all ExecutionRuns for a project ordered by newest first."""
        result = await self._session.execute(
            select(ExecutionRun)
            .options(selectinload(ExecutionRun.trace_events))
            .where(ExecutionRun.project_id == project_id)
            .order_by(ExecutionRun.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_trace_events(
        self,
        project_id: UUID,
        run_id: UUID,
    ) -> list[TraceEvent]:
        """Return ordered TraceEvent rows for a specific ExecutionRun."""
        run = await self.get_by_id(project_id=project_id, run_id=run_id)
        return list(run.trace_events)
