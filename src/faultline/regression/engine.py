"""Regression suite engine managing candidate generation, review, and release gates."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from faultline.adapters.registry import AdapterRegistry
from faultline.core.errors import PreconditionFailedError
from faultline.domain.models import RegressionCase
from faultline.evaluation.engine import EvaluationEngine
from faultline.execution.engine import BaselineExecutionEngine
from faultline.repositories.diagnosis import DiagnosisRepository
from faultline.repositories.execution import ExecutionRunRepository
from faultline.repositories.regression import RegressionRepository
from faultline.repositories.workspace import AgentConfigRepository, ProjectRepository
from faultline.schemas.execution import RunCreateRequest
from faultline.schemas.regression import (
    RegressionCandidateCreate,
    RegressionCaseRunResult,
    RegressionReviewRequest,
    ReleaseDecision,
    ReleaseGateEvaluationResponse,
    ReleaseGateRunRequest,
)


class RegressionSuiteEngine:
    """Orchestrates regression test creation, human approval, and release gate checks."""

    def __init__(
        self,
        session: AsyncSession,
        adapter_registry: AdapterRegistry | None = None,
    ) -> None:
        self._session = session
        self._registry = adapter_registry or AdapterRegistry()
        self._project_repo = ProjectRepository(session)
        self._agent_repo = AgentConfigRepository(session)
        self._run_repo = ExecutionRunRepository(session)
        self._diag_repo = DiagnosisRepository(session)
        self._reg_repo = RegressionRepository(session)
        self._exec_engine = BaselineExecutionEngine(
            session=session,
            adapter_registry=self._registry,
        )
        self._eval_engine = EvaluationEngine(session=session)

    async def create_candidate_from_run(
        self,
        *,
        project_id: UUID,
        request: RegressionCandidateCreate,
    ) -> RegressionCase:
        """Generate a candidate regression test from a human-confirmed diagnosed run."""
        await self._project_repo.get_by_id(project_id)
        source_run = await self._run_repo.get_by_id(
            project_id=project_id,
            run_id=request.source_run_id,
        )

        diag_report = await self._diag_repo.get_optional_by_run_id(
            project_id=project_id,
            run_id=source_run.id,
        )
        if (
            diag_report is None
            or diag_report.confirmation_status != "confirmed"
            or diag_report.human_confirmed_cause is None
        ):
            raise PreconditionFailedError(
                f"Run '{source_run.id}' must have a human-confirmed diagnosis report "
                "before generating a regression test candidate."
            )

        human_cause = diag_report.human_confirmed_cause
        confirmed_root_cause = str(human_cause.get("confirmed_root_cause", ""))
        classification_code = human_cause.get("selected_classification_code")

        metadata = {
            "source_run_mode": source_run.run_mode,
            "source_status": source_run.status,
            "confirmed_by": human_cause.get("confirmed_by"),
            "confirmed_at": human_cause.get("confirmed_at"),
        }

        return await self._reg_repo.create_candidate(
            project_id=project_id,
            source_run_id=source_run.id,
            scenario_id=source_run.scenario_id,
            name=request.name,
            description=request.description,
            confirmed_root_cause=confirmed_root_cause,
            classification_code=(
                str(classification_code) if classification_code is not None else None
            ),
            review_metadata=metadata,
        )

    async def review_candidate(
        self,
        *,
        project_id: UUID,
        case_id: UUID,
        request: RegressionReviewRequest,
    ) -> RegressionCase:
        """Approve or reject a candidate RegressionCase after human engineering review."""
        await self._project_repo.get_by_id(project_id)
        existing = await self._reg_repo.get_by_id(
            project_id=project_id,
            case_id=case_id,
        )

        updated_metadata = {
            **existing.review_metadata,
            "reviewed_by": request.reviewed_by,
            "review_notes": request.review_notes,
            "reviewed_at": datetime.now(UTC).isoformat(),
            "decision": request.decision,
        }

        return await self._reg_repo.update_review_status(
            project_id=project_id,
            case_id=case_id,
            approval_status=request.decision,
            review_metadata=updated_metadata,
        )

    async def evaluate_release_gate(
        self,
        *,
        project_id: UUID,
        request: ReleaseGateRunRequest,
    ) -> ReleaseGateEvaluationResponse:
        """Run all approved regression cases against an agent version and enforce gate."""
        await self._project_repo.get_by_id(project_id)
        await self._agent_repo.get_by_id(
            project_id=project_id,
            agent_id=request.agent_config_id,
        )

        approved_cases = await self._reg_repo.list_approved_by_project(project_id)
        if not approved_cases:
            raise PreconditionFailedError(
                f"Project '{project_id}' has no approved regression test cases "
                "to execute for release gate evaluation."
            )

        case_results: list[RegressionCaseRunResult] = []
        run_mode: Literal["fault_injected", "recovery"] = (
            "recovery" if request.recovery_policy is not None else "fault_injected"
        )

        for reg_case in approved_cases:
            run_req = RunCreateRequest(
                agent_config_id=request.agent_config_id,
                scenario_id=reg_case.scenario_id,
                run_mode=run_mode,
                recovery_policy=request.recovery_policy,
            )
            exec_run = await self._exec_engine.execute_run(
                project_id=project_id,
                request=run_req,
            )
            eval_report = await self._eval_engine.evaluate_run(
                project_id=project_id,
                run_id=exec_run.id,
            )

            case_results.append(
                RegressionCaseRunResult(
                    regression_case_id=reg_case.id,
                    case_name=reg_case.name,
                    scenario_id=reg_case.scenario_id,
                    execution_run_id=exec_run.id,
                    task_succeeded=eval_report.task_succeeded,
                    reliability_score=eval_report.reliability_score,
                    total_latency_ms=exec_run.total_latency_ms,
                    total_tokens=exec_run.total_tokens,
                )
            )

        total_executed = len(case_results)
        passed_cases = sum(1 for r in case_results if r.task_succeeded)
        failed_cases = total_executed - passed_cases
        pass_rate = round(passed_cases / total_executed, 4)
        avg_score = round(
            sum(r.reliability_score for r in case_results) / total_executed,
            4,
        )
        total_latency = round(
            sum(r.total_latency_ms for r in case_results),
            4,
        )

        rejection_reasons: list[str] = []
        criteria = request.gate_criteria

        if pass_rate < criteria.min_pass_rate:
            rejection_reasons.append(
                f"Suite pass_rate ({pass_rate:.2f}) is below required "
                f"min_pass_rate ({criteria.min_pass_rate:.2f})."
            )

        if avg_score < criteria.min_average_reliability_score:
            rejection_reasons.append(
                f"Average reliability_score ({avg_score:.2f}) is below required "
                f"min_average_reliability_score ({criteria.min_average_reliability_score:.2f})."
            )

        if (
            criteria.max_suite_latency_ms is not None
            and total_latency > criteria.max_suite_latency_ms
        ):
            rejection_reasons.append(
                f"Total suite latency ({total_latency}ms) exceeded "
                f"max_suite_latency_ms ({criteria.max_suite_latency_ms}ms)."
            )

        decision: ReleaseDecision = (
            "approved" if len(rejection_reasons) == 0 else "rejected"
        )

        return ReleaseGateEvaluationResponse(
            project_id=project_id,
            agent_config_id=request.agent_config_id,
            release_decision=decision,
            total_cases_executed=total_executed,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            pass_rate=pass_rate,
            average_reliability_score=avg_score,
            total_suite_latency_ms=total_latency,
            rejection_reasons=rejection_reasons,
            case_results=case_results,
        )
