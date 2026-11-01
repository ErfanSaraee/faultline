"""Pydantic v2 schemas for RegressionCase management, suite execution, and release gates."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from faultline.schemas.execution import RecoveryPolicySpec

RegressionApprovalStatus = Literal["candidate", "approved", "rejected"]
ReleaseDecision = Literal["approved", "rejected"]


class RegressionCandidateCreate(BaseModel):
    """Payload to generate a candidate regression test from a human-confirmed diagnosis."""

    source_run_id: UUID = Field(
        description="UUID of the diagnosed ExecutionRun with a human-confirmed cause"
    )
    name: str = Field(
        min_length=3,
        max_length=128,
        description="Unique name for the regression test case within the project",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional context explaining what regression this test prevents",
    )


class RegressionReviewRequest(BaseModel):
    """Payload submitted by a human engineer to approve or reject a regression candidate."""

    decision: Literal["approved", "rejected"] = Field(
        description="Review decision ('approved' activates the test in the regression suite)"
    )
    reviewed_by: str = Field(
        min_length=1,
        max_length=128,
        description="Engineer handle approving or rejecting the candidate",
    )
    review_notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional review commentary",
    )


class RegressionCaseResponse(BaseModel):
    """Serialized RegressionCase returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    source_run_id: UUID
    scenario_id: UUID
    name: str
    description: str | None
    approval_status: RegressionApprovalStatus
    confirmed_root_cause: str
    classification_code: str | None
    review_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ReleaseGateCriteria(BaseModel):
    """Explicit reliability thresholds required for a release gate to pass."""

    min_pass_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Minimum fraction of approved regression cases that must succeed",
    )
    min_average_reliability_score: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Minimum average reliability_score across all regression runs",
    )
    max_suite_latency_ms: float | None = Field(
        default=None,
        gt=0.0,
        description="Optional upper bound on cumulative latency across the regression suite",
    )


class ReleaseGateRunRequest(BaseModel):
    """Payload to execute the approved regression suite and evaluate release readiness."""

    agent_config_id: UUID = Field(
        description="UUID of the candidate AgentConfig version being evaluated for release"
    )
    recovery_policy: RecoveryPolicySpec | None = Field(
        default=None,
        description="Optional recovery policy to apply during regression suite execution",
    )
    gate_criteria: ReleaseGateCriteria = Field(
        default_factory=ReleaseGateCriteria,
        description="Explicit reliability thresholds for approving or rejecting the release",
    )


class RegressionCaseRunResult(BaseModel):
    """Outcome of executing a single approved RegressionCase during a suite run."""

    regression_case_id: UUID
    case_name: str
    scenario_id: UUID
    execution_run_id: UUID
    task_succeeded: bool
    reliability_score: float
    total_latency_ms: float
    total_tokens: int


class ReleaseGateEvaluationResponse(BaseModel):
    """Release gate verdict and per-case results after running the regression suite."""

    project_id: UUID
    agent_config_id: UUID
    release_decision: ReleaseDecision
    total_cases_executed: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    average_reliability_score: float
    total_suite_latency_ms: float
    rejection_reasons: list[str] = Field(default_factory=list)
    case_results: list[RegressionCaseRunResult] = Field(default_factory=list)
