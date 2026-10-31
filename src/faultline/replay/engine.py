"""Replay engine supporting deterministic recorded replay, live replay, and trace diffing."""

from collections import defaultdict, deque
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from faultline.adapters.base import ToolHandler
from faultline.adapters.registry import AdapterRegistry
from faultline.domain.models import ExecutionRun, TraceEvent
from faultline.execution.engine import (
    BaselineExecutionEngine,
    build_fixture_tool_handler,
)
from faultline.execution.recovery import RecoveryToolInterceptor
from faultline.faults.injector import FaultInjector
from faultline.repositories.execution import ExecutionRunRepository
from faultline.repositories.scenario import ScenarioRepository
from faultline.repositories.workspace import AgentConfigRepository, ProjectRepository
from faultline.schemas.adapter import (
    AgentExecutionOutput,
    AgentStep,
    AgentStepType,
    AgentTaskInput,
    ExecutionStatus,
    ToolCallRequest,
    ToolCallResult,
)
from faultline.schemas.execution import ExecutionRunResponse, RecoveryPolicySpec
from faultline.schemas.replay import (
    ExecutionDiffResponse,
    ReplayRequest,
    ReplayRunResponse,
    StepDeviation,
)
from faultline.schemas.scenario import ScenarioSpec


class RecordedToolHandler:
    """Serves recorded ToolCallResult payloads captured during a prior ExecutionRun."""

    def __init__(self, source_trace_events: list[TraceEvent]) -> None:
        self._queues_by_tool: dict[str,
                                   deque[ToolCallResult]] = defaultdict(deque)
        for event in source_trace_events:
            if event.step_type == "tool_call":
                payload = event.output_payload
                recorded_status: Literal["success", "error"] = (
                    "success" if payload.get(
                        "status") == "success" else "error"
                )
                result = ToolCallResult(
                    call_id=str(payload.get(
                        "call_id", f"recorded-{event.step_index}")),
                    tool_name=event.name,
                    status=recorded_status,
                    output=payload.get("output"),
                    error_type=payload.get("error_type"),
                    error_message=payload.get("error_message"),
                    latency_ms=event.latency_ms,
                )
                self._queues_by_tool[event.name].append(result)

    def as_tool_handler(self) -> ToolHandler:
        """Return an async ToolHandler callable backed by recorded tool queues."""

        async def handler(request: ToolCallRequest) -> ToolCallResult:
            queue = self._queues_by_tool.get(request.tool_name)
            if queue:
                recorded = queue.popleft()
                return recorded.model_copy(update={"call_id": request.call_id})

            return ToolCallResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                status="error",
                error_type="UNRECORDED_TOOL_CALL",
                error_message=(
                    f"Tool '{request.tool_name}' had no remaining recorded results "
                    "in source run trace."
                ),
                latency_ms=0.0,
            )

        return handler


class ReplayEngine:
    """Orchestrates recorded replay, live re-execution, and step-level run diffing."""

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
        self._baseline_engine = BaselineExecutionEngine(
            session=session,
            adapter_registry=self._registry,
        )

    async def replay_run(
        self,
        *,
        project_id: UUID,
        source_run_id: UUID,
        request: ReplayRequest,
    ) -> ReplayRunResponse:
        """Execute a recorded or live replay of a source run and compute its diff."""
        await self._project_repo.get_by_id(project_id)
        source_run = await self._run_repo.get_by_id(
            project_id=project_id,
            run_id=source_run_id,
        )

        target_agent_id = request.override_agent_config_id or source_run.agent_config_id
        agent_config = await self._agent_repo.get_by_id(
            project_id=project_id,
            agent_id=target_agent_id,
        )
        scenario = await self._scenario_repo.get_by_id(
            project_id=project_id,
            scenario_id=source_run.scenario_id,
        )
        scenario_spec = ScenarioSpec.model_validate(scenario.spec)

        guarantee: Literal[
            "deterministic_recorded_trace",
            "deterministic_recorded_tools",
            "non_deterministic_live_execution",
        ]

        if request.replay_mode == "recorded_replay":
            if request.override_agent_config_id is None:
                guarantee = "deterministic_recorded_trace"
                execution_output = self._reconstruct_output_from_trace(
                    source_run)
            else:
                guarantee = "deterministic_recorded_tools"
                adapter = self._registry.get(agent_config.adapter_type)
                recorded_handler = RecordedToolHandler(source_run.trace_events)
                task_input = AgentTaskInput(
                    task_prompt=scenario_spec.task_prompt,
                    planned_tool_calls=scenario_spec.planned_tool_calls,
                    context_data=scenario_spec.preconditions,
                    max_steps=scenario_spec.safety_constraints.max_steps,
                )
                execution_output = await adapter.execute(
                    model_name=agent_config.model_name,
                    config_payload=agent_config.config_payload,
                    task_input=task_input,
                    tool_handler=recorded_handler.as_tool_handler(),
                )
            replay_metadata: dict[str, Any] = {
                **source_run.run_metadata,
                "source_run_id": str(source_run.id),
                "source_run_mode": source_run.run_mode,
                "source_model_name": source_run.model_name,
                "agent_name": agent_config.name,
                "agent_version": agent_config.version,
                "replay_mode": "recorded_replay",
                "reproducibility_guarantee": guarantee,
            }
            replay_run = await self._run_repo.create_from_output(
                project_id=project_id,
                agent_config_id=agent_config.id,
                scenario_id=scenario.id,
                run_mode="recorded_replay",
                execution_output=execution_output,
                run_metadata=replay_metadata,
            )
        else:
            guarantee = "non_deterministic_live_execution"
            replay_run = await self._execute_live_replay(
                project_id=project_id,
                source_run=source_run,
                agent_id=agent_config.id,
                scenario_spec=scenario_spec,
                override_recovery_policy=request.override_recovery_policy,
            )

        diff = await self.diff_runs(
            project_id=project_id,
            source_run_id=source_run.id,
            target_run_id=replay_run.id,
        )

        return ReplayRunResponse(
            source_run_id=source_run.id,
            replay_mode=request.replay_mode,
            reproducibility_guarantee=guarantee,
            replay_run=ExecutionRunResponse.model_validate(replay_run),
            diff=diff,
        )

    async def diff_runs(
        self,
        *,
        project_id: UUID,
        source_run_id: UUID,
        target_run_id: UUID,
    ) -> ExecutionDiffResponse:
        """Compute a step-by-step trace diff between source_run and target_run."""
        await self._project_repo.get_by_id(project_id)
        source_run = await self._run_repo.get_by_id(
            project_id=project_id,
            run_id=source_run_id,
        )
        target_run = await self._run_repo.get_by_id(
            project_id=project_id,
            run_id=target_run_id,
        )

        deviations = self._compute_step_deviations(
            source_events=source_run.trace_events,
            target_events=target_run.trace_events,
        )
        status_match = source_run.status == target_run.status
        final_answer_match = source_run.final_answer == target_run.final_answer
        step_count_match = len(source_run.trace_events) == len(
            target_run.trace_events)
        trace_path_identical = (
            status_match
            and final_answer_match
            and step_count_match
            and len(deviations) == 0
        )

        return ExecutionDiffResponse(
            project_id=project_id,
            source_run_id=source_run.id,
            target_run_id=target_run.id,
            source_run_mode=source_run.run_mode,
            target_run_mode=target_run.run_mode,
            source_model_name=source_run.model_name,
            target_model_name=target_run.model_name,
            status_match=status_match,
            final_answer_match=final_answer_match,
            step_count_match=step_count_match,
            trace_path_identical=trace_path_identical,
            token_delta=target_run.total_tokens - source_run.total_tokens,
            latency_delta_ms=round(
                target_run.total_latency_ms - source_run.total_latency_ms,
                4,
            ),
            deviations=deviations,
        )

    def _reconstruct_output_from_trace(
        self,
        source_run: ExecutionRun,
    ) -> AgentExecutionOutput:
        steps: list[AgentStep] = []
        for event in source_run.trace_events:
            step_status: Literal["ok", "error"] = (
                "ok" if event.status == "ok" else "error"
            )
            steps.append(
                AgentStep(
                    step_index=event.step_index,
                    step_type=cast(AgentStepType, event.step_type),
                    name=event.name,
                    status=step_status,
                    input_payload=event.input_payload,
                    output_payload=event.output_payload,
                    latency_ms=event.latency_ms,
                    tokens_used=event.tokens_used,
                )
            )

        return AgentExecutionOutput(
            adapter_type=source_run.adapter_type,
            model_name=source_run.model_name,
            status=cast(ExecutionStatus, source_run.status),
            final_answer=source_run.final_answer,
            steps=steps,
            total_tokens=source_run.total_tokens,
            total_latency_ms=source_run.total_latency_ms,
            error_message=source_run.error_message,
        )

    async def _execute_live_replay(
        self,
        *,
        project_id: UUID,
        source_run: ExecutionRun,
        agent_id: UUID,
        scenario_spec: ScenarioSpec,
        override_recovery_policy: RecoveryPolicySpec | None,
    ) -> ExecutionRun:
        agent_config = await self._agent_repo.get_by_id(
            project_id=project_id,
            agent_id=agent_id,
        )
        scenario = await self._scenario_repo.get_by_id(
            project_id=project_id,
            scenario_id=source_run.scenario_id,
        )
        adapter = self._registry.get(agent_config.adapter_type)

        task_input = AgentTaskInput(
            task_prompt=scenario_spec.task_prompt,
            planned_tool_calls=scenario_spec.planned_tool_calls,
            context_data=scenario_spec.preconditions,
            max_steps=scenario_spec.safety_constraints.max_steps,
        )

        base_tool_handler = build_fixture_tool_handler(
            scenario_spec.tool_fixtures)
        fault_injector: FaultInjector | None = None
        recovery_interceptor: RecoveryToolInterceptor | None = None
        active_handler: ToolHandler = base_tool_handler

        should_inject_faults = (
            source_run.run_mode in ("fault_injected", "recovery")
            or override_recovery_policy is not None
        )
        if should_inject_faults:
            fault_injector = FaultInjector(scenario_spec.fault_rules)
            active_handler = fault_injector.wrap(base_tool_handler)

        active_policy = override_recovery_policy
        if active_policy is None and "recovery_policy" in source_run.run_metadata:
            active_policy = RecoveryPolicySpec.model_validate(
                source_run.run_metadata["recovery_policy"]
            )

        if active_policy is not None:
            recovery_interceptor = RecoveryToolInterceptor(active_policy)
            active_handler = recovery_interceptor.wrap(active_handler)

        execution_output = await adapter.execute(
            model_name=agent_config.model_name,
            config_payload=agent_config.config_payload,
            task_input=task_input,
            tool_handler=active_handler,
        )

        if recovery_interceptor is not None:
            execution_output = recovery_interceptor.expand_execution_output(
                execution_output
            )

        triggered_faults = (
            [e.model_dump(mode="json")
             for e in fault_injector.triggered_events]
            if fault_injector is not None
            else []
        )

        live_metadata: dict[str, Any] = {
            "source_run_id": str(source_run.id),
            "source_run_mode": source_run.run_mode,
            "source_model_name": source_run.model_name,
            "agent_name": agent_config.name,
            "agent_version": agent_config.version,
            "scenario_name": scenario.name,
            "scenario_version": scenario.version,
            "max_steps": scenario_spec.safety_constraints.max_steps,
            "configured_fault_rules": len(scenario_spec.fault_rules),
            "injected_fault_count": len(triggered_faults),
            "injected_faults": triggered_faults,
            "replay_mode": "live_replay",
            "reproducibility_guarantee": "non_deterministic_live_execution",
        }
        if recovery_interceptor is not None and active_policy is not None:
            live_metadata["recovery_policy"] = active_policy.model_dump(
                mode="json")
            live_metadata["recovery_summary"] = recovery_interceptor.summary.model_dump(
                mode="json"
            )

        return await self._run_repo.create_from_output(
            project_id=project_id,
            agent_config_id=agent_config.id,
            scenario_id=scenario.id,
            run_mode="live_replay",
            execution_output=execution_output,
            run_metadata=live_metadata,
        )

    def _compute_step_deviations(
        self,
        *,
        source_events: list[TraceEvent],
        target_events: list[TraceEvent],
    ) -> list[StepDeviation]:
        deviations: list[StepDeviation] = []
        max_len = max(len(source_events), len(target_events))

        for idx in range(max_len):
            src = source_events[idx] if idx < len(source_events) else None
            tgt = target_events[idx] if idx < len(target_events) else None

            if src is None and tgt is not None:
                deviations.append(
                    StepDeviation(
                        step_index=idx,
                        deviation_type="step_added",
                        source_summary=None,
                        target_summary=self._summarize_event(tgt),
                        description=(
                            f"Step {idx} ('{tgt.step_type}:{tgt.name}') was added "
                            "in target run."
                        ),
                    )
                )
                continue

            if src is not None and tgt is None:
                deviations.append(
                    StepDeviation(
                        step_index=idx,
                        deviation_type="step_removed",
                        source_summary=self._summarize_event(src),
                        target_summary=None,
                        description=(
                            f"Step {idx} ('{src.step_type}:{src.name}') from source "
                            "run is missing in target run."
                        ),
                    )
                )
                continue

            assert src is not None and tgt is not None

            if src.step_type != tgt.step_type:
                deviations.append(
                    StepDeviation(
                        step_index=idx,
                        deviation_type="step_type_changed",
                        source_summary=self._summarize_event(src),
                        target_summary=self._summarize_event(tgt),
                        description=(
                            f"Step {idx} type changed from '{src.step_type}' "
                            f"to '{tgt.step_type}'."
                        ),
                    )
                )
            elif src.name != tgt.name:
                deviations.append(
                    StepDeviation(
                        step_index=idx,
                        deviation_type="tool_or_model_changed",
                        source_summary=self._summarize_event(src),
                        target_summary=self._summarize_event(tgt),
                        description=(
                            f"Step {idx} component changed from '{src.name}' "
                            f"to '{tgt.name}'."
                        ),
                    )
                )
            elif src.status != tgt.status:
                deviations.append(
                    StepDeviation(
                        step_index=idx,
                        deviation_type="status_changed",
                        source_summary=self._summarize_event(src),
                        target_summary=self._summarize_event(tgt),
                        description=(
                            f"Step {idx} ('{src.name}') status changed from "
                            f"'{src.status}' to '{tgt.status}'."
                        ),
                    )
                )
            elif src.output_payload != tgt.output_payload:
                deviations.append(
                    StepDeviation(
                        step_index=idx,
                        deviation_type="output_changed",
                        source_summary=self._summarize_event(src),
                        target_summary=self._summarize_event(tgt),
                        description=(
                            f"Step {idx} ('{src.name}') output payload diverged."
                        ),
                    )
                )

        return deviations

    def _summarize_event(self, event: TraceEvent) -> dict[str, Any]:
        return {
            "step_index": event.step_index,
            "step_type": event.step_type,
            "name": event.name,
            "status": event.status,
            "output_payload": event.output_payload,
        }
