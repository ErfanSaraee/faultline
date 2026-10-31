"""Pydantic v2 schemas for ExecutionRun, TraceEvent, Fault, and Recovery contracts."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from faultline.schemas.adapter import AgentStepType, ExecutionStatus
from faultline.schemas.scenario import FaultType

RunMode = Literal[
    "baseline",
    "fault_injected",
    "recovery",
    "recorded_replay",
    "live_replay",
]

RecoveryStrategy = Literal["retry", "fallback_tool", "retry_then_fallback"]

DEFAULT_RETRYABLE_FAULTS: list[FaultType] = [
    "HTTP_429_RATE_LIMIT",
    "TIMEOUT",
    "TOOL_UNAVAILABLE",
]


class InjectedFaultEvent(BaseModel):
    """Record of a controlled fault that was actively triggered during a run."""

    call_id: str = Field(description="Correlated tool call identifier")
    tool_name: str = Field(
        description="Target tool name where the fault occurred")
    invocation_number: int = Field(
        ge=1,
        description="1-based invocation count for this tool when the fault triggered",
    )
    fault_type: FaultType = Field(description="Category of injected fault")
    error_message: str = Field(
        description="Diagnostic error message returned to the agent"
    )
    injected_latency_ms: float = Field(
        ge=0.0,
        description="Simulated latency in milliseconds injected by the fault rule",
    )


class RecoveryPolicySpec(BaseModel):
    """Configuration for controlled recovery-policy experiments at the tool boundary."""

    strategy: RecoveryStrategy = Field(
        default="retry",
        description="Recovery mechanism ('retry', 'fallback_tool', 'retry_then_fallback')",
    )
    max_retries: int = Field(
        default=1,
        ge=0,
        le=5,
        description="Maximum bounded retry attempts per failed tool call",
    )
    backoff_ms: float = Field(
        default=25.0,
        ge=0.0,
        le=10000.0,
        description="Additional backoff latency in milliseconds per retry attempt",
    )
    retry_token_overhead: int = Field(
        default=15,
        ge=0,
        le=5000,
        description="Additional LLM token overhead incurred per retry or fallback step",
    )
    retryable_fault_types: list[FaultType] = Field(
        default_factory=lambda: list(DEFAULT_RETRYABLE_FAULTS),
        description="Fault categories eligible for automatic retry",
    )
    fallback_tool_map: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from primary tool name to backup tool name",
    )


class RecoverySummary(BaseModel):
    """Telemetry summary of recovery actions executed during a recovery run."""

    strategy: RecoveryStrategy
    retries_performed: int = Field(ge=0, default=0)
    fallbacks_performed: int = Field(ge=0, default=0)
    recoveries_succeeded: int = Field(ge=0, default=0)
    recoveries_exhausted: int = Field(ge=0, default=0)


class RunCreateRequest(BaseModel):
    """Payload required to trigger a scenario execution run."""

    agent_config_id: UUID = Field(
        description="UUID of the versioned AgentConfig to execute"
    )
    scenario_id: UUID = Field(
        description="UUID of the versioned ScenarioDefinition to run"
    )
    run_mode: Literal["baseline", "fault_injected", "recovery"] = Field(
        default="baseline",
        description=(
            "Execution mode ('baseline', 'fault_injected', or 'recovery' with policy)"
        ),
    )
    recovery_policy: RecoveryPolicySpec | None = Field(
        default=None,
        description="Required recovery policy configuration when run_mode is 'recovery'",
    )

    @model_validator(mode="after")
    def validate_recovery_policy_mode(self) -> "RunCreateRequest":
        if self.run_mode == "recovery" and self.recovery_policy is None:
            raise ValueError(
                "recovery_policy must be provided when run_mode is 'recovery'."
            )
        if self.run_mode != "recovery" and self.recovery_policy is not None:
            raise ValueError(
                "recovery_policy is only permitted when run_mode is 'recovery'."
            )
        return self


class TraceEventResponse(BaseModel):
    """Serialized observable TraceEvent step returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    step_index: int
    step_type: AgentStepType
    name: str
    status: Literal["ok", "error"]
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    latency_ms: float
    tokens_used: int
    created_at: datetime


class ExecutionRunResponse(BaseModel):
    """Serialized ExecutionRun record including captured trace events."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    agent_config_id: UUID
    scenario_id: UUID
    run_mode: RunMode
    status: ExecutionStatus
    adapter_type: str
    model_name: str
    final_answer: str | None
    error_message: str | None
    total_tokens: int
    total_latency_ms: float
    run_metadata: dict[str, Any]
    trace_events: list[TraceEventResponse]
    created_at: datetime
    updated_at: datetime
