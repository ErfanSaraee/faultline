"""Pydantic v2 schemas for ExecutionRun, TraceEvent, and InjectedFaultEvent contracts."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from faultline.schemas.adapter import AgentStepType, ExecutionStatus
from faultline.schemas.scenario import FaultType

RunMode = Literal[
    "baseline",
    "fault_injected",
    "recovery",
    "recorded_replay",
    "live_replay",
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
        description="Diagnostic error message returned to the agent")
    injected_latency_ms: float = Field(
        ge=0.0,
        description="Simulated latency in milliseconds injected by the fault rule",
    )


class RunCreateRequest(BaseModel):
    """Payload required to trigger a scenario execution run."""

    agent_config_id: UUID = Field(
        description="UUID of the versioned AgentConfig to execute"
    )
    scenario_id: UUID = Field(
        description="UUID of the versioned ScenarioDefinition to run"
    )
    run_mode: Literal["baseline", "fault_injected"] = Field(
        default="baseline",
        description=(
            "Execution mode ('baseline' ignores fault rules; "
            "'fault_injected' activates them)"
        ),
    )


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
