"""Evidence-based failure diagnosis engine separating facts, rules, hypotheses, and human review."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from faultline.domain.models import DiagnosisReport, EvaluationReport, ExecutionRun
from faultline.evaluation.engine import EvaluationEngine
from faultline.repositories.diagnosis import DiagnosisRepository
from faultline.repositories.evaluation import EvaluationRepository
from faultline.repositories.execution import ExecutionRunRepository
from faultline.repositories.workspace import ProjectRepository
from faultline.schemas.diagnosis import (
    HumanConfirmationRequest,
    HumanConfirmedCause,
    ModelHypothesis,
    ObservedFact,
    RuleClassification,
)


class DiagnosisEngine:
    """Produces verifiable failure diagnostics grounded in traces and evaluation outputs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._project_repo = ProjectRepository(session)
        self._run_repo = ExecutionRunRepository(session)
        self._eval_repo = EvaluationRepository(session)
        self._diag_repo = DiagnosisRepository(session)
        self._eval_engine = EvaluationEngine(session)

    async def diagnose_run(
        self,
        project_id: UUID,
        run_id: UUID,
    ) -> DiagnosisReport:
        """Analyze an ExecutionRun, extract facts, classify failures, and propose hypotheses."""
        await self._project_repo.get_by_id(project_id)
        run = await self._run_repo.get_by_id(project_id=project_id, run_id=run_id)

        eval_report = await self._eval_repo.get_optional_by_run_id(
            project_id=project_id,
            run_id=run.id,
        )
        if eval_report is None:
            eval_report = await self._eval_engine.evaluate_run(
                project_id=project_id,
                run_id=run.id,
            )

        facts = self._extract_observed_facts(run=run, eval_report=eval_report)
        classifications = self._apply_diagnostic_rules(
            run=run,
            eval_report=eval_report,
            facts=facts,
        )
        hypotheses = self._generate_grounded_hypotheses(
            classifications=classifications,
        )

        primary_codes = ", ".join(
            c.classification_code for c in classifications)
        summary = (
            f"Diagnosed run {run.id}: {len(facts)} observed facts, "
            f"{len(classifications)} rule classifications [{primary_codes}], "
            f"{len(hypotheses)} unconfirmed hypotheses (awaiting human review)."
        )

        return await self._diag_repo.upsert_report(
            project_id=project_id,
            run_id=run.id,
            scenario_id=run.scenario_id,
            observed_facts=facts,
            rule_classifications=classifications,
            model_hypotheses=hypotheses,
            summary=summary,
        )

    async def confirm_diagnosis(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        request: HumanConfirmationRequest,
    ) -> DiagnosisReport:
        """Record human confirmation of root cause on an existing DiagnosisReport."""
        await self._project_repo.get_by_id(project_id)
        confirmed = HumanConfirmedCause(
            confirmed_by=request.confirmed_by,
            confirmed_root_cause=request.confirmed_root_cause,
            selected_classification_code=request.selected_classification_code,
            endorsed_hypothesis_id=request.endorsed_hypothesis_id,
            resolution_notes=request.resolution_notes,
            confirmed_at=datetime.now(UTC),
        )
        return await self._diag_repo.save_human_confirmation(
            project_id=project_id,
            run_id=run_id,
            confirmed_cause=confirmed,
        )

    def _extract_observed_facts(
        self,
        *,
        run: ExecutionRun,
        eval_report: EvaluationReport,
    ) -> list[ObservedFact]:
        facts: list[ObservedFact] = []

        def next_fact_id() -> str:
            return f"FACT-{len(facts) + 1}"

        # 1. Terminal execution status fact
        facts.append(
            ObservedFact(
                fact_id=next_fact_id(),
                source_type="execution_run",
                step_index=None,
                component_name=run.adapter_type,
                statement=(
                    f"Run finished with terminal status '{run.status}' "
                    f"in mode '{run.run_mode}'."
                ),
                evidence_payload={
                    "status": run.status,
                    "run_mode": run.run_mode,
                    "error_message": run.error_message,
                    "total_latency_ms": run.total_latency_ms,
                    "total_tokens": run.total_tokens,
                },
            )
        )

        # 2. Injected fault telemetry facts
        injected_faults = run.run_metadata.get("injected_faults", [])
        for fault in injected_faults:
            facts.append(
                ObservedFact(
                    fact_id=next_fact_id(),
                    source_type="injected_fault",
                    step_index=None,
                    component_name=str(fault.get("tool_name", "unknown_tool")),
                    statement=(
                        f"Controlled fault '{fault.get('fault_type')}' was injected on "
                        f"tool '{fault.get('tool_name')}' (invocation "
                        f"#{fault.get('invocation_number')})."
                    ),
                    evidence_payload=dict(fault),
                )
            )

        # 3. Trace error step facts
        for event in run.trace_events:
            if event.status == "error":
                error_type = event.output_payload.get(
                    "error_type", "ToolError")
                error_msg = event.output_payload.get("error_message", "")
                facts.append(
                    ObservedFact(
                        fact_id=next_fact_id(),
                        source_type="trace_event",
                        step_index=event.step_index,
                        component_name=event.name,
                        statement=(
                            f"Trace step {event.step_index} ('{event.step_type}:{event.name}') "
                            f"recorded status 'error' ({error_type}: {error_msg})."
                        ),
                        evidence_payload={
                            "step_index": event.step_index,
                            "step_type": event.step_type,
                            "error_type": error_type,
                            "error_message": error_msg,
                            "latency_ms": event.latency_ms,
                        },
                    )
                )

        # 4. Recovery exhaustion telemetry facts
        recovery_summary = run.run_metadata.get("recovery_summary")
        if isinstance(recovery_summary, dict):
            exhausted = int(recovery_summary.get("recoveries_exhausted", 0))
            if exhausted > 0:
                facts.append(
                    ObservedFact(
                        fact_id=next_fact_id(),
                        source_type="recovery_telemetry",
                        step_index=None,
                        component_name="recovery_interceptor",
                        statement=(
                            f"Recovery policy '{recovery_summary.get('strategy')}' "
                            f"exhausted its retry/fallback budget ({exhausted} exhausted)."
                        ),
                        evidence_payload=dict(recovery_summary),
                    )
                )

        # 5. Failed evaluation assertion facts
        for assertion in eval_report.assertion_results:
            if not assertion.get("passed", True):
                facts.append(
                    ObservedFact(
                        fact_id=next_fact_id(),
                        source_type="evaluation_assertion",
                        step_index=None,
                        component_name=str(
                            assertion.get("target", "criteria")),
                        statement=str(
                            assertion.get(
                                "message", "Evaluation assertion failed.")
                        ),
                        evidence_payload=dict(assertion),
                    )
                )

        return facts

    def _apply_diagnostic_rules(
        self,
        *,
        run: ExecutionRun,
        eval_report: EvaluationReport,
        facts: list[ObservedFact],
    ) -> list[RuleClassification]:
        classifications: list[RuleClassification] = []

        # Map error types to fact IDs
        rate_limit_facts = [
            f.fact_id
            for f in facts
            if f.evidence_payload.get("error_type") == "HTTP_429_RATE_LIMIT"
            or f.evidence_payload.get("fault_type") == "HTTP_429_RATE_LIMIT"
        ]
        if rate_limit_facts:
            classifications.append(
                RuleClassification(
                    rule_id="RULE-DEP-429",
                    classification_code="DEPENDENCY_RATE_LIMITED",
                    severity="error",
                    title="Tool Dependency Rate Limited (HTTP 429)",
                    rationale=(
                        "One or more tool invocations failed with HTTP_429_RATE_LIMIT."
                    ),
                    supporting_fact_ids=rate_limit_facts,
                )
            )

        timeout_facts = [
            f.fact_id
            for f in facts
            if f.evidence_payload.get("error_type") == "TIMEOUT"
            or f.evidence_payload.get("fault_type") == "TIMEOUT"
        ]
        if timeout_facts:
            classifications.append(
                RuleClassification(
                    rule_id="RULE-DEP-TIMEOUT",
                    classification_code="DEPENDENCY_TIMEOUT",
                    severity="error",
                    title="Tool Dependency Timed Out",
                    rationale="A tool dependency failed to respond within its timeout window.",
                    supporting_fact_ids=timeout_facts,
                )
            )

        corruption_types = {"MALFORMED_JSON",
                            "EMPTY_RESPONSE", "CONTRADICTORY_DATA"}
        corruption_facts = [
            f.fact_id
            for f in facts
            if f.evidence_payload.get("error_type") in corruption_types
            or f.evidence_payload.get("fault_type") in corruption_types
        ]
        if corruption_facts:
            classifications.append(
                RuleClassification(
                    rule_id="RULE-DEP-PAYLOAD",
                    classification_code="TOOL_PAYLOAD_CORRUPTION_OR_CONTRADICTION",
                    severity="error",
                    title="Malformed, Empty, or Contradictory Tool Payload",
                    rationale=(
                        "A tool returned corrupted JSON, empty content, or contradictory data."
                    ),
                    supporting_fact_ids=corruption_facts,
                )
            )

        if run.status == "max_steps_exceeded":
            classifications.append(
                RuleClassification(
                    rule_id="RULE-EXEC-MAXSTEPS",
                    classification_code="STEP_BUDGET_EXHAUSTED",
                    severity="critical",
                    title="Execution Step Budget Exhausted",
                    rationale=(
                        "The agent reached the scenario max_steps guardrail before completing."
                    ),
                    supporting_fact_ids=["FACT-1"],
                )
            )

        exhausted_facts = [
            f.fact_id for f in facts if f.source_type == "recovery_telemetry"
        ]
        if exhausted_facts:
            classifications.append(
                RuleClassification(
                    rule_id="RULE-REC-EXHAUSTED",
                    classification_code="RECOVERY_BUDGET_EXHAUSTED",
                    severity="critical",
                    title="Recovery Policy Exhausted Without Resolution",
                    rationale=(
                        "Configured retries/fallbacks were executed but the fault persisted."
                    ),
                    supporting_fact_ids=exhausted_facts,
                )
            )

        # Superficial completion detection: run finished 'completed' but failed assertions
        if run.status == "completed" and not eval_report.task_succeeded:
            failed_assertion_facts = [
                f.fact_id for f in facts if f.source_type == "evaluation_assertion"
            ]
            classifications.append(
                RuleClassification(
                    rule_id="RULE-EVAL-SUPERFICIAL",
                    classification_code="SUPERFICIAL_COMPLETION_FAILURE",
                    severity="warning",
                    title="Superficial Completion Masked Scenario Failure",
                    rationale=(
                        "The agent returned a 'completed' status, but explicit scenario "
                        "evaluation assertions failed."
                    ),
                    supporting_fact_ids=["FACT-1", *failed_assertion_facts],
                )
            )

        if not classifications:
            if eval_report.task_succeeded:
                classifications.append(
                    RuleClassification(
                        rule_id="RULE-HEALTHY",
                        classification_code="HEALTHY_EXECUTION",
                        severity="info",
                        title="Execution Satisfied All Scenario Criteria",
                        rationale="No trace errors or assertion failures were observed.",
                        supporting_fact_ids=["FACT-1"],
                    )
                )
            else:
                all_fact_ids = [f.fact_id for f in facts]
                classifications.append(
                    RuleClassification(
                        rule_id="RULE-GENERIC-FAILURE",
                        classification_code="UNCLASSIFIED_EXECUTION_FAILURE",
                        severity="error",
                        title="Execution Failed Scenario Criteria",
                        rationale="The run failed one or more criteria.",
                        supporting_fact_ids=all_fact_ids,
                    )
                )

        return classifications

    def _generate_grounded_hypotheses(
        self,
        *,
        classifications: list[RuleClassification],
    ) -> list[ModelHypothesis]:
        hypotheses: list[ModelHypothesis] = []

        for idx, item in enumerate(classifications, start=1):
            code = item.classification_code
            if code == "HEALTHY_EXECUTION":
                continue

            if code == "DEPENDENCY_RATE_LIMITED":
                statement = (
                    "The agent lacked a bounded backoff retry or fallback policy when "
                    "the tool dependency throttled requests with HTTP 429."
                )
                remediation = (
                    "Run a recovery experiment with strategy='retry' (max_retries=1..2) "
                    "or route to a secondary read replica tool."
                )
                confidence = 0.9
            elif code == "DEPENDENCY_TIMEOUT":
                statement = (
                    "Downstream service latency exceeded the tool call timeout threshold, "
                    "aborting the agent workflow."
                )
                remediation = (
                    "Test a 'retry_then_fallback' policy with a cached/archive fallback "
                    "tool while ensuring total latency remains within scenario SLA."
                )
                confidence = 0.88
            elif code == "SUPERFICIAL_COMPLETION_FAILURE":
                statement = (
                    "The agent swallowed a tool error or emitted a degraded fallback "
                    "response that failed required scenario content or budget criteria."
                )
                remediation = (
                    "Replace generic error-swallowing fallback strings with verified "
                    "backup tool routing or bounded retries."
                )
                confidence = 0.85
            elif code == "RECOVERY_BUDGET_EXHAUSTED":
                statement = (
                    "Retrying the same failing primary tool was ineffective because the "
                    "dependency outage persisted across consecutive calls."
                )
                remediation = (
                    "Switch from pure 'retry' to 'retry_then_fallback' with an "
                    "independent backup tool in fallback_tool_map."
                )
                confidence = 0.92
            elif code == "STEP_BUDGET_EXHAUSTED":
                statement = (
                    "The agent planned more model/tool steps than permitted by the "
                    "scenario safety_constraints.max_steps limit."
                )
                remediation = (
                    "Reduce redundant tool invocations in the agent prompt/graph or "
                    "verify whether max_steps is overly restrictive for the task."
                )
                confidence = 0.9
            else:
                statement = (
                    f"Execution failed under classification '{code}' based on "
                    "captured trace and evaluation evidence."
                )
                remediation = (
                    "Inspect the cited trace events and convert this run into a "
                    "regression test case after human verification."
                )
                confidence = 0.75

            hypotheses.append(
                ModelHypothesis(
                    hypothesis_id=f"HYP-{idx}",
                    verification_status="unconfirmed_hypothesis",
                    confidence=confidence,
                    hypothesis_statement=statement,
                    suggested_remediation=remediation,
                    supporting_fact_ids=item.supporting_fact_ids,
                )
            )

        return hypotheses
