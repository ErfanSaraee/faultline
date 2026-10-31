"""Pydantic v2 schemas for evidence-based failure diagnosis and human confirmation."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

FactSourceType = Literal[
    "execution_run",
    "trace_event",
    "injected_fault",
    "recovery_telemetry",
    "evaluation_assertion",
]

DiagnosisSeverity = Literal["info", "warning", "error", "critical"]

ConfirmationStatus = Literal["pending_human_review", "confirmed"]


class ObservedFact(BaseModel):
    """Verifiable fact extracted directly from recorded traces, errors, or evaluations."""

    fact_id: str = Field(
        description="Deterministic identifier within the report (e.g. 'FACT-1')")
    source_type: FactSourceType = Field(
        description="Origin of the verifiable evidence")
    step_index: int | None = Field(
        default=None,
        description="Correlated zero-based trace step index, if applicable",
    )
    component_name: str = Field(
        description="Agent, tool, or subsystem associated with the fact")
    statement: str = Field(
        description="Objective description of the observed event")
    evidence_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured snapshot of the underlying recorded evidence",
    )


class RuleClassification(BaseModel):
    """Deterministic rule-based failure classification grounded in observed facts."""

    rule_id: str = Field(
        description="Identifier of the diagnostic rule triggered")
    classification_code: str = Field(
        description="Machine-readable failure taxonomy code (e.g. 'DEPENDENCY_RATE_LIMITED')"
    )
    severity: DiagnosisSeverity = Field(
        description="Diagnostic severity level")
    title: str = Field(description="Short human-readable classification title")
    rationale: str = Field(
        description="Explanation of why the deterministic rule matched")
    supporting_fact_ids: list[str] = Field(
        default_factory=list,
        description="IDs of ObservedFact items that prove this classification",
    )


class ModelHypothesis(BaseModel):
    """Plausible root-cause hypothesis grounded in evidence, explicitly marked unconfirmed."""

    hypothesis_id: str = Field(
        description="Identifier for this candidate hypothesis")
    verification_status: Literal["unconfirmed_hypothesis"] = Field(
        default="unconfirmed_hypothesis",
        description="Guardrail marker: model hypotheses are never auto-confirmed",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Heuristic or model confidence score between 0.0 and 1.0",
    )
    hypothesis_statement: str = Field(
        description="Proposed explanation of why the agent failed or degraded"
    )
    suggested_remediation: str = Field(
        description="Actionable engineering recommendation to test or mitigate the issue"
    )
    supporting_fact_ids: list[str] = Field(
        default_factory=list,
        description="IDs of ObservedFact items cited by this hypothesis",
    )


class HumanConfirmedCause(BaseModel):
    """Human-verified root cause record established after reviewing evidence."""

    confirmed_by: str = Field(min_length=1, max_length=128)
    confirmed_root_cause: str = Field(min_length=1, max_length=2000)
    selected_classification_code: str | None = Field(
        default=None, max_length=128)
    endorsed_hypothesis_id: str | None = Field(default=None, max_length=64)
    resolution_notes: str | None = Field(default=None, max_length=2000)
    confirmed_at: datetime


class HumanConfirmationRequest(BaseModel):
    """Payload submitted by a developer to confirm the root cause of a diagnosed run."""

    confirmed_by: str = Field(
        min_length=1,
        max_length=128,
        description="Identifier or handle of the engineer confirming the diagnosis",
    )
    confirmed_root_cause: str = Field(
        min_length=5,
        max_length=2000,
        description="Verified root cause statement",
    )
    selected_classification_code: str | None = Field(
        default=None,
        max_length=128,
        description="Optional classification_code from rule_classifications",
    )
    endorsed_hypothesis_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional hypothesis_id from model_hypotheses",
    )
    resolution_notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional engineering notes for regression test creation",
    )


class DiagnosisReportResponse(BaseModel):
    """Serialized DiagnosisReport returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    run_id: UUID
    scenario_id: UUID
    confirmation_status: ConfirmationStatus
    observed_facts: list[ObservedFact]
    rule_classifications: list[RuleClassification]
    model_hypotheses: list[ModelHypothesis]
    human_confirmed_cause: HumanConfirmedCause | None
    summary: str
    created_at: datetime
    updated_at: datetime
