"""Baseline execution engine orchestrating agent adapters, scenario fixtures, and tracing."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from faultline.adapters.base import ToolHandler, default_mock_tool_handler
from faultline.adapters.registry import AdapterRegistry
from faultline.domain.models import ExecutionRun
from faultline.repositories.execution import ExecutionRunRepository
from faultline.repositories.scenario import ScenarioRepository
from faultline.repositories.workspace import AgentConfigRepository, ProjectRepository
from faultline.schemas.adapter import (
    AgentTaskInput,
    ToolCallRequest,
    ToolCallResult,
)
from faultline.schemas.execution import RunCreateRequest
from faultline.schemas.scenario import ScenarioSpec, ToolFixture


def build_fixture_tool_handler(fixtures: list[ToolFixture]) -> ToolHandler:
    """Create a deterministic ToolHandler backed by scenario ToolFixture definitions."""
    fixture_map: dict[str, ToolFixture] = {f.tool_name: f for f in fixtures}

    async def fixture_tool_handler(request: ToolCallRequest) -> ToolCallResult:
        matched_fixture = fixture_map.get(request.tool_name)
        if matched_fixture is not None:
            return ToolCallResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                status="success",
                output=matched_fixture.default_output,
                latency_ms=matched_fixture.latency_ms,
            )
        return await default_mock_tool_handler(request)

    return fixture_tool_handler


class BaselineExecutionEngine:
    """Orchestrates baseline scenario runs and persists structured execution traces."""

    def __init__(
        self,
        session: AsyncSession,
        adapter_registry: AdapterRegistry | None = None,
    ) -> None:
        self._session = session
        self._registry = adapter_registry or AdapterRegistry()
        self._project_repo = ProjectRepository(session)
        self._agent_repo = AgentConfigRepository(session)
        self._scenario_repo = ScenarioRepository(session)
        self._run_repo = ExecutionRunRepository(session)

    async def execute_run(
        self,
        project_id: UUID,
        request: RunCreateRequest,
    ) -> ExecutionRun:
        """Execute a scenario against an agent configuration and store its trace."""
        await self._project_repo.get_by_id(project_id)

        agent_config = await self._agent_repo.get_by_id(
            project_id=project_id,
            agent_id=request.agent_config_id,
        )
        scenario = await self._scenario_repo.get_by_id(
            project_id=project_id,
            scenario_id=request.scenario_id,
        )

        scenario_spec = ScenarioSpec.model_validate(scenario.spec)
        adapter = self._registry.get(agent_config.adapter_type)

        task_input = AgentTaskInput(
            task_prompt=scenario_spec.task_prompt,
            planned_tool_calls=scenario_spec.planned_tool_calls,
            context_data=scenario_spec.preconditions,
            max_steps=scenario_spec.safety_constraints.max_steps,
        )
        tool_handler = build_fixture_tool_handler(scenario_spec.tool_fixtures)

        execution_output = await adapter.execute(
            model_name=agent_config.model_name,
            config_payload=agent_config.config_payload,
            task_input=task_input,
            tool_handler=tool_handler,
        )

        run_metadata = {
            "agent_name": agent_config.name,
            "agent_version": agent_config.version,
            "scenario_name": scenario.name,
            "scenario_version": scenario.version,
            "max_steps": scenario_spec.safety_constraints.max_steps,
        }

        return await self._run_repo.create_from_output(
            project_id=project_id,
            agent_config_id=agent_config.id,
            scenario_id=scenario.id,
            run_mode=request.run_mode,
            execution_output=execution_output,
            run_metadata=run_metadata,
        )
