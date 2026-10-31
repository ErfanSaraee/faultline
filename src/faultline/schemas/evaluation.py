"""Pydantic v2 schemas for deterministic evaluation reports and run comparisons."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssertionResult(BaseModel):
    """Outcome of a single explicit evaluation assertion check."""

    assertion_type: str = Field(description="Category of assertion evaluated")
    target: str = Field(
        description="Specific field, substring, or tool evaluated")
    passed: bool = Field(description="Whether the assertion succeeded")
    expected: Any = Field(
        description="Expected value or condition from ScenarioSpec")
    actual: Any = Field(
        description="Observed value from ExecutionRun or TraceEvents")
    message: str = Field(
        description="Human-readable explanation of assertion outcome")


class EvaluationMetrics(BaseModel):
    """Quantitative reliability and efficiency metrics extracted from a run."""

    status_completed: bool = Field(
        description="Whether the run finished with status == 'completed'"
    )
    tool_call_count: int = Field(
        ge=0, description="Total tool invocations in the run")
    failed_tool_call_count: int = Field(
        ge=0,
        description="Number of tool invocations that ended in error",
    )
    tool_retry_count: int = Field(
        ge=0,
        description="Repeated calls to the same tool beyond the initial invocation",
    )
    tool_correctness_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of tool expectations satisfied (0.0 to 1.0)",
    )
    injected_fault_count: int = Field(
        ge=0,
        description="Number of controlled faults triggered during the run",
    )
    total_latency_ms: float = Field(
        ge=0.0,
        description="Cumulative latency in milliseconds",
    )
    total_tokens: int = Field(
        ge=0, description="Cumulative LLM tokens consumed")
    estimated_cost_usd: float = Field(
        ge=0.0,
        description="Estimated execution cost in USD based on token consumption",
    )


class EvaluationReportResponse(BaseModel):
    """Serialized EvaluationReport returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    run_id: UUID
    scenario_id: UUID
    task_succeeded: bool
    reliability_score: float
    metrics: EvaluationMetrics
    assertion_results: list[AssertionResult]
    summary: str
    created_at: datetime
    updated_at: datetime


class RunComparisonResponse(BaseModel):
    """Structured comparison between a baseline run and a candidate/fault-injected run."""

    project_id: UUID
    scenario_id: UUID
    baseline_run_id: UUID
    candidate_run_id: UUID
    baseline_mode: str
    candidate_mode: str
    baseline_succeeded: bool
    candidate_succeeded: bool
    outcome_classification: str = Field(
        description=(
            "Classification of comparison: 'resilient' (both succeeded), "
            "'degraded' (baseline succeeded, candidate failed), "
            "'recovered_or_improved' (baseline failed, candidate succeeded), "
            "or 'both_failed'"
        )
    )
    reliability_score_delta: float = Field(
        description="Candidate reliability_score minus baseline reliability_score"
    )
    latency_delta_ms: float = Field(
        description="Candidate total_latency_ms minus baseline total_latency_ms"
    )
    token_delta: int = Field(
        description="Candidate total_tokens minus baseline total_tokens"
    )
    cost_delta_usd: float = Field(
        description="Candidate estimated_cost_usd minus baseline estimated_cost_usd"
    )
    retry_delta: int = Field(
        description="Candidate tool_retry_count minus baseline tool_retry_count"
    )
    failed_assertion_targets: list[str] = Field(
        default_factory=list,
        description="Targets of assertions that failed in the candidate run",
    )
