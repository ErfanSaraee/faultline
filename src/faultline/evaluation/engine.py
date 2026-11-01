"""Deterministic evaluation engine for scoring ExecutionRuns and comparing experiments."""

from collections import Counter
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from faultline.domain.models import EvaluationReport, ExecutionRun
from faultline.observability.telemetry import get_telemetry_manager
from faultline.repositories.evaluation import EvaluationRepository
from faultline.repositories.execution import ExecutionRunRepository
from faultline.repositories.scenario import ScenarioRepository
from faultline.repositories.workspace import AgentConfigRepository, ProjectRepository
from faultline.schemas.evaluation import (
    AssertionResult,
    EvaluationMetrics,
    RunComparisonResponse,
)
from faultline.schemas.scenario import EvaluationCriteriaSpec, ScenarioSpec

DEFAULT_COST_PER_1K_TOKENS_USD = 0.002


class EvaluationEngine:
    """Evaluates ExecutionRun records against explicit ScenarioSpec criteria."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._project_repo = ProjectRepository(session)
        self._agent_repo = AgentConfigRepository(session)
        self._scenario_repo = ScenarioRepository(session)
        self._run_repo = ExecutionRunRepository(session)
        self._eval_repo = EvaluationRepository(session)
        self._telemetry = get_telemetry_manager()

    async def evaluate_run(
        self,
        project_id: UUID,
        run_id: UUID,
    ) -> EvaluationReport:
        """Evaluate an ExecutionRun against its ScenarioDefinition and persist the report."""
        await self._project_repo.get_by_id(project_id)
        run = await self._run_repo.get_by_id(project_id=project_id, run_id=run_id)
        scenario = await self._scenario_repo.get_by_id(
            project_id=project_id,
            scenario_id=run.scenario_id,
        )
        agent_config = await self._agent_repo.get_by_id(
            project_id=project_id,
            agent_id=run.agent_config_id,
        )

        scenario_spec = ScenarioSpec.model_validate(scenario.spec)
        criteria = scenario_spec.evaluation_criteria

        cost_per_1k = float(
            agent_config.config_payload.get(
                "cost_per_1k_tokens_usd",
                DEFAULT_COST_PER_1K_TOKENS_USD,
            )
        )

        assertions = self._run_assertions(run=run, criteria=criteria)
        metrics = self._compute_metrics(
            run=run,
            criteria=criteria,
            cost_per_1k_tokens_usd=cost_per_1k,
        )

        passed_count = sum(1 for a in assertions if a.passed)
        total_count = len(assertions)
        reliability_score = (
            round(passed_count / total_count, 4) if total_count else 1.0
        )
        task_succeeded = all(a.passed for a in assertions)

        self._telemetry.metrics.record_evaluation(
            task_succeeded=task_succeeded)

        summary = (
            f"Evaluation {'PASSED' if task_succeeded else 'FAILED'}: "
            f"{passed_count}/{total_count} assertions satisfied "
            f"(score={reliability_score:.2f}, latency={metrics.total_latency_ms}ms, "
            f"tokens={metrics.total_tokens}, retries={metrics.tool_retry_count})."
        )

        return await self._eval_repo.upsert_report(
            project_id=project_id,
            run_id=run.id,
            scenario_id=scenario.id,
            task_succeeded=task_succeeded,
            reliability_score=reliability_score,
            metrics=metrics,
            assertion_results=assertions,
            summary=summary,
        )

    async def compare_runs(
        self,
        *,
        project_id: UUID,
        baseline_run_id: UUID,
        candidate_run_id: UUID,
    ) -> RunComparisonResponse:
        """Compare a baseline run and a candidate run (evaluating them if needed)."""
        await self._project_repo.get_by_id(project_id)
        baseline_run = await self._run_repo.get_by_id(
            project_id=project_id,
            run_id=baseline_run_id,
        )
        candidate_run = await self._run_repo.get_by_id(
            project_id=project_id,
            run_id=candidate_run_id,
        )

        baseline_report = await self.evaluate_run(
            project_id=project_id,
            run_id=baseline_run.id,
        )
        candidate_report = await self.evaluate_run(
            project_id=project_id,
            run_id=candidate_run.id,
        )

        base_metrics = EvaluationMetrics.model_validate(
            baseline_report.metrics)
        cand_metrics = EvaluationMetrics.model_validate(
            candidate_report.metrics)

        if baseline_report.task_succeeded and candidate_report.task_succeeded:
            classification = "resilient"
        elif baseline_report.task_succeeded and not candidate_report.task_succeeded:
            classification = "degraded"
        elif not baseline_report.task_succeeded and candidate_report.task_succeeded:
            classification = "recovered_or_improved"
        else:
            classification = "both_failed"

        failed_targets = [
            str(item["target"])
            for item in candidate_report.assertion_results
            if not item.get("passed", False)
        ]

        return RunComparisonResponse(
            project_id=project_id,
            scenario_id=candidate_run.scenario_id,
            baseline_run_id=baseline_run.id,
            candidate_run_id=candidate_run.id,
            baseline_mode=baseline_run.run_mode,
            candidate_mode=candidate_run.run_mode,
            baseline_succeeded=baseline_report.task_succeeded,
            candidate_succeeded=candidate_report.task_succeeded,
            outcome_classification=classification,
            reliability_score_delta=round(
                candidate_report.reliability_score - baseline_report.reliability_score,
                4,
            ),
            latency_delta_ms=round(
                cand_metrics.total_latency_ms - base_metrics.total_latency_ms,
                4,
            ),
            token_delta=cand_metrics.total_tokens - base_metrics.total_tokens,
            cost_delta_usd=round(
                cand_metrics.estimated_cost_usd - base_metrics.estimated_cost_usd,
                8,
            ),
            retry_delta=cand_metrics.tool_retry_count - base_metrics.tool_retry_count,
            failed_assertion_targets=failed_targets,
        )

    def _run_assertions(
        self,
        *,
        run: ExecutionRun,
        criteria: EvaluationCriteriaSpec,
    ) -> list[AssertionResult]:
        results: list[AssertionResult] = []
        final_answer = run.final_answer or ""
        invoked_tools = [
            event.name
            for event in run.trace_events
            if event.step_type == "tool_call"
        ]
        invoked_tool_set = set(invoked_tools)

        # 1. Terminal status assertion
        if criteria.require_completed_status:
            passed = run.status == "completed"
            results.append(
                AssertionResult(
                    assertion_type="status_completed",
                    target="run.status",
                    passed=passed,
                    expected="completed",
                    actual=run.status,
                    message=(
                        "Run finished with status 'completed'."
                        if passed
                        else f"Expected status 'completed' but got '{run.status}'."
                    ),
                )
            )

        # 2. Required substrings in final_answer
        for required_sub in criteria.required_substrings:
            passed = required_sub in final_answer
            results.append(
                AssertionResult(
                    assertion_type="required_substring",
                    target=required_sub,
                    passed=passed,
                    expected=f"contains '{required_sub}'",
                    actual=final_answer,
                    message=(
                        f"Final answer contains required substring '{required_sub}'."
                        if passed
                        else f"Final answer is missing required substring '{required_sub}'."
                    ),
                )
            )

        # 3. Forbidden substrings in final_answer
        for forbidden_sub in criteria.forbidden_substrings:
            passed = forbidden_sub not in final_answer
            results.append(
                AssertionResult(
                    assertion_type="forbidden_substring",
                    target=forbidden_sub,
                    passed=passed,
                    expected=f"excludes '{forbidden_sub}'",
                    actual=final_answer,
                    message=(
                        f"Final answer excludes forbidden substring '{forbidden_sub}'."
                        if passed
                        else f"Final answer contains forbidden substring '{forbidden_sub}'."
                    ),
                )
            )

        # 4. Expected tool invocations
        for expected_tool in criteria.expected_tools:
            passed = expected_tool in invoked_tool_set
            results.append(
                AssertionResult(
                    assertion_type="expected_tool",
                    target=expected_tool,
                    passed=passed,
                    expected=f"tool '{expected_tool}' invoked",
                    actual=sorted(invoked_tool_set),
                    message=(
                        f"Expected tool '{expected_tool}' was invoked."
                        if passed
                        else f"Expected tool '{expected_tool}' was never invoked."
                    ),
                )
            )

        # 5. Forbidden tool invocations
        for forbidden_tool in criteria.forbidden_tools:
            passed = forbidden_tool not in invoked_tool_set
            results.append(
                AssertionResult(
                    assertion_type="forbidden_tool",
                    target=forbidden_tool,
                    passed=passed,
                    expected=f"tool '{forbidden_tool}' not invoked",
                    actual=sorted(invoked_tool_set),
                    message=(
                        f"Forbidden tool '{forbidden_tool}' was not invoked."
                        if passed
                        else f"Forbidden tool '{forbidden_tool}' was invoked."
                    ),
                )
            )

        # 6. Latency budget assertion
        if criteria.max_total_latency_ms is not None:
            passed = run.total_latency_ms <= criteria.max_total_latency_ms
            results.append(
                AssertionResult(
                    assertion_type="latency_budget",
                    target="total_latency_ms",
                    passed=passed,
                    expected=criteria.max_total_latency_ms,
                    actual=run.total_latency_ms,
                    message=(
                        f"Latency {run.total_latency_ms}ms within budget "
                        f"({criteria.max_total_latency_ms}ms)."
                        if passed
                        else f"Latency {run.total_latency_ms}ms exceeded budget "
                        f"({criteria.max_total_latency_ms}ms)."
                    ),
                )
            )

        # 7. Token budget assertion
        if criteria.max_total_tokens is not None:
            passed = run.total_tokens <= criteria.max_total_tokens
            results.append(
                AssertionResult(
                    assertion_type="token_budget",
                    target="total_tokens",
                    passed=passed,
                    expected=criteria.max_total_tokens,
                    actual=run.total_tokens,
                    message=(
                        f"Tokens {run.total_tokens} within budget "
                        f"({criteria.max_total_tokens})."
                        if passed
                        else f"Tokens {run.total_tokens} exceeded budget "
                        f"({criteria.max_total_tokens})."
                    ),
                )
            )

        return results

    def _compute_metrics(
        self,
        *,
        run: ExecutionRun,
        criteria: EvaluationCriteriaSpec,
        cost_per_1k_tokens_usd: float,
    ) -> EvaluationMetrics:
        tool_events = [
            event for event in run.trace_events if event.step_type == "tool_call"
        ]
        tool_call_count = len(tool_events)
        failed_tool_call_count = sum(
            1 for event in tool_events if event.status == "error"
        )

        counts_by_tool = Counter(event.name for event in tool_events)
        tool_retry_count = sum(
            count - 1 for count in counts_by_tool.values() if count >= 2
        )

        invoked_tool_set = set(counts_by_tool.keys())
        tool_checks: list[bool] = []
        for expected_tool in criteria.expected_tools:
            tool_checks.append(expected_tool in invoked_tool_set)
        for forbidden_tool in criteria.forbidden_tools:
            tool_checks.append(forbidden_tool not in invoked_tool_set)

        tool_correctness_rate = (
            round(sum(1 for ok in tool_checks if ok) / len(tool_checks), 4)
            if tool_checks
            else 1.0
        )

        injected_fault_count = int(
            run.run_metadata.get("injected_fault_count", 0))
        estimated_cost_usd = round(
            (run.total_tokens / 1000.0) * cost_per_1k_tokens_usd,
            8,
        )

        return EvaluationMetrics(
            status_completed=(run.status == "completed"),
            tool_call_count=tool_call_count,
            failed_tool_call_count=failed_tool_call_count,
            tool_retry_count=tool_retry_count,
            tool_correctness_rate=tool_correctness_rate,
            injected_fault_count=injected_fault_count,
            total_latency_ms=run.total_latency_ms,
            total_tokens=run.total_tokens,
            estimated_cost_usd=estimated_cost_usd,
        )
