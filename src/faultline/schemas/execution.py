"""Pydantic v2 schemas for ExecutionRun and TraceEvent contracts."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from faultline.schemas.adapter import AgentStepType, ExecutionStatus

RunMode = Literal[
    "baseline",
    "fault_injected",
    "recovery",
    "recorded_replay",
    "live_replay",
]


class RunCreateRequest(BaseModel):
    """Payload required to trigger a scenario execution run."""

    agent_config_id: UUID = Field(
        description="UUID of the versioned AgentConfig to execute"
    )
    scenario_id: UUID = Field(
        description="UUID of the versioned ScenarioDefinition to run"
    )
    run_mode: Literal["baseline"] = Field(
        default="baseline",
        description="Execution mode (Phase 6 supports baseline execution)",
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
