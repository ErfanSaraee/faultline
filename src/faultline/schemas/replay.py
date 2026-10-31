"""Pydantic v2 schemas for deterministic recorded replay, live replay, and run diffing."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from faultline.schemas.execution import ExecutionRunResponse, RecoveryPolicySpec

ReplayMode = Literal["recorded_replay", "live_replay"]

DeviationType = Literal[
    "step_added",
    "step_removed",
    "step_type_changed",
    "tool_or_model_changed",
    "status_changed",
    "output_changed",
]


class ReplayRequest(BaseModel):
    """Payload required to replay an existing ExecutionRun."""

    replay_mode: ReplayMode = Field(
        default="recorded_replay",
        description=(
            "Explicit replay mode: 'recorded_replay' reuses captured trace/tool outputs; "
            "'live_replay' reinvokes the agent and dependencies live."
        ),
    )
    override_agent_config_id: UUID | None = Field(
        default=None,
        description="Optional new AgentConfig UUID to test against the source run",
    )
    override_recovery_policy: RecoveryPolicySpec | None = Field(
        default=None,
        description="Optional recovery policy override (applicable to live_replay)",
    )


class StepDeviation(BaseModel):
    """Single observable step difference between a source run and a target/replay run."""

    step_index: int = Field(
        ge=0, description="Zero-based step index where deviation occurred")
    deviation_type: DeviationType = Field(
        description="Classification of step divergence")
    source_summary: dict[str, Any] | None = Field(
        default=None,
        description="Snapshot of the step in the original source run, if present",
    )
    target_summary: dict[str, Any] | None = Field(
        default=None,
        description="Snapshot of the step in the target/replay run, if present",
    )
    description: str = Field(
        description="Human-readable explanation of the deviation")


class ExecutionDiffResponse(BaseModel):
    """Structured step-by-step comparison and deviation report between two runs."""

    project_id: UUID
    source_run_id: UUID
    target_run_id: UUID
    source_run_mode: str
    target_run_mode: str
    source_model_name: str
    target_model_name: str
    status_match: bool = Field(
        description="Whether both runs ended with the exact same terminal status"
    )
    final_answer_match: bool = Field(
        description="Whether both runs produced the exact same final_answer string"
    )
    step_count_match: bool = Field(
        description="Whether both runs recorded the same number of trace events"
    )
    trace_path_identical: bool = Field(
        description=(
            "True only if status, final_answer, and all trace steps match "
            "without deviations"
        )
    )
    token_delta: int = Field(
        description="Target total_tokens minus source total_tokens"
    )
    latency_delta_ms: float = Field(
        description="Target total_latency_ms minus source total_latency_ms"
    )
    deviations: list[StepDeviation] = Field(
        default_factory=list,
        description="Ordered list of step-level deviations detected between the runs",
    )


class ReplayRunResponse(BaseModel):
    """Combined response returning the newly created replay run and its diff against source."""

    source_run_id: UUID
    replay_mode: ReplayMode
    reproducibility_guarantee: Literal[
        "deterministic_recorded_trace",
        "deterministic_recorded_tools",
        "non_deterministic_live_execution",
    ] = Field(
        description="Explicit statement of determinism guarantees for this replay run"
    )
    replay_run: ExecutionRunResponse
    diff: ExecutionDiffResponse
