"""Persistence repository for DiagnosisReport entities."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from faultline.core.errors import EntityNotFoundError
from faultline.domain.models import DiagnosisReport
from faultline.schemas.diagnosis import (
    HumanConfirmedCause,
    ModelHypothesis,
    ObservedFact,
    RuleClassification,
)


class DiagnosisRepository:
    """Data access operations for durable DiagnosisReport records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_run_id(
        self,
        project_id: UUID,
        run_id: UUID,
    ) -> DiagnosisReport:
        """Fetch a DiagnosisReport for a run or raise EntityNotFoundError."""
        result = await self._session.execute(
            select(DiagnosisReport).where(
                DiagnosisReport.project_id == project_id,
                DiagnosisReport.run_id == run_id,
            )
        )
        report = result.scalar_one_or_none()
        if report is None:
            raise EntityNotFoundError("DiagnosisReport for run", str(run_id))
        return report

    async def get_optional_by_run_id(
        self,
        project_id: UUID,
        run_id: UUID,
    ) -> DiagnosisReport | None:
        """Return a DiagnosisReport for a run if it exists, otherwise None."""
        result = await self._session.execute(
            select(DiagnosisReport).where(
                DiagnosisReport.project_id == project_id,
                DiagnosisReport.run_id == run_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_report(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        scenario_id: UUID,
        observed_facts: list[ObservedFact],
        rule_classifications: list[RuleClassification],
        model_hypotheses: list[ModelHypothesis],
        summary: str,
    ) -> DiagnosisReport:
        """Create or update an evidence-based DiagnosisReport for an ExecutionRun."""
        existing = await self.get_optional_by_run_id(
            project_id=project_id,
            run_id=run_id,
        )
        serialized_facts = [f.model_dump(mode="json") for f in observed_facts]
        serialized_rules = [r.model_dump(mode="json")
                            for r in rule_classifications]
        serialized_hypotheses = [h.model_dump(
            mode="json") for h in model_hypotheses]

        if existing is not None:
            existing.observed_facts = serialized_facts
            existing.rule_classifications = serialized_rules
            existing.model_hypotheses = serialized_hypotheses
            existing.summary = summary
            await self._session.commit()
            await self._session.refresh(existing)
            return existing

        report = DiagnosisReport(
            project_id=project_id,
            run_id=run_id,
            scenario_id=scenario_id,
            confirmation_status="pending_human_review",
            observed_facts=serialized_facts,
            rule_classifications=serialized_rules,
            model_hypotheses=serialized_hypotheses,
            human_confirmed_cause=None,
            summary=summary,
        )
        self._session.add(report)
        await self._session.commit()
        await self._session.refresh(report)
        return report

    async def save_human_confirmation(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        confirmed_cause: HumanConfirmedCause,
    ) -> DiagnosisReport:
        """Record human root-cause confirmation on an existing DiagnosisReport."""
        report = await self.get_by_run_id(project_id=project_id, run_id=run_id)
        report.confirmation_status = "confirmed"
        report.human_confirmed_cause = confirmed_cause.model_dump(mode="json")
        await self._session.commit()
        await self._session.refresh(report)
        return report
