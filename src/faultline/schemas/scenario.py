"""Pydantic v2 schemas for versioned ScenarioDefinition contracts."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from faultline.schemas.adapter import ToolCallRequest

FaultType = Literal[
    "HTTP_429_RATE_LIMIT",
    "TIMEOUT",
    "MALFORMED_JSON",
    "EMPTY_RESPONSE",
    "CONTRADICTORY_DATA",
    "TOOL_UNAVAILABLE",
]


class ToolFixture(BaseModel):
    """Deterministic mock response fixture for a specific tool dependency."""

    tool_name: str = Field(min_length=1, max_length=128,
                           description="Target tool identifier")
    default_output: dict[str, Any] = Field(
        default_factory=dict,
        description="Deterministic payload returned when the tool succeeds",
    )
    latency_ms: float = Field(
        default=5.0,
        ge=0.0,
        le=60000.0,
        description="Simulated baseline latency in milliseconds",
    )


class FaultRuleSpec(BaseModel):
    """Controlled fault injection rule targeting a specific tool invocation."""

    target_tool: str = Field(
        min_length=1,
        max_length=128,
        description="Tool name where the fault should be injected",
    )
    fault_type: FaultType = Field(
        description="Category of controlled failure to inject")
    trigger_on_call: int = Field(
        default=1,
        ge=1,
        le=100,
        description="1-based invocation count on which this fault triggers for target_tool",
    )
    error_message: str = Field(
        default="Injected fault triggered by FAULTLINE scenario.",
        min_length=1,
        max_length=500,
        description="Diagnostic error message returned when the fault triggers",
    )
    injected_latency_ms: float = Field(
        default=50.0,
        ge=0.0,
        le=120000.0,
        description="Latency in milliseconds applied when the fault triggers",
    )


class EvaluationCriteriaSpec(BaseModel):
    """Explicit evaluation assertions used to judge an execution run."""

    require_completed_status: bool = Field(
        default=True,
        description="Whether the agent run must finish with status == 'completed'",
    )
    required_substrings: list[str] = Field(
        default_factory=list,
        description="Substrings that must appear in the final answer",
    )
    forbidden_substrings: list[str] = Field(
        default_factory=list,
        description="Substrings that must not appear in the final answer",
    )
    expected_tools: list[str] = Field(
        default_factory=list,
        description="Tool names that must be invoked at least once during the run",
    )
    forbidden_tools: list[str] = Field(
        default_factory=list,
        description="Tool names that must never be invoked during the run",
    )
    max_total_latency_ms: float | None = Field(
        default=None,
        gt=0.0,
        description="Optional upper bound on cumulative run latency in milliseconds",
    )
    max_total_tokens: int | None = Field(
        default=None,
        gt=0,
        description="Optional upper bound on cumulative LLM tokens consumed",
    )

    @model_validator(mode="after")
    def validate_disjoint_tool_sets(self) -> "EvaluationCriteriaSpec":
        overlap = set(self.expected_tools).intersection(
            set(self.forbidden_tools))
        if overlap:
            sorted_overlap = ", ".join(sorted(overlap))
            raise ValueError(
                f"Tools cannot be both expected and forbidden: {sorted_overlap}"
            )
        return self


class SafetyConstraintsSpec(BaseModel):
    """Execution limits and safe-by-default guardrails for a scenario."""

    max_steps: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum observable execution steps permitted",
    )
    timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        le=300.0,
        description="Maximum wall-clock execution time in seconds",
    )
    allow_live_external_actions: bool = Field(
        default=False,
        description="Must remain False to prevent irreversible external side effects",
    )

    @field_validator("allow_live_external_actions")
    @classmethod
    def enforce_safe_execution_mode(cls, value: bool) -> bool:
        if value is True:
            raise ValueError(
                "Safe-by-default violation: allow_live_external_actions cannot be True."
            )
        return value


class ScenarioSpec(BaseModel):
    """Complete structured specification of a repeatable test scenario."""

    task_prompt: str = Field(
        min_length=1,
        max_length=20000,
        description="Task instruction given to the agent under test",
    )
    preconditions: dict[str, Any] = Field(
        default_factory=dict,
        description="Initial context or environment state assumptions",
    )
    planned_tool_calls: list[ToolCallRequest] = Field(
        default_factory=list,
        description="Planned sequence of tool invocations for deterministic/mock runs",
    )
    tool_fixtures: list[ToolFixture] = Field(
        default_factory=list,
        description="Deterministic tool response fixtures",
    )
    fault_rules: list[FaultRuleSpec] = Field(
        default_factory=list,
        description="Controlled fault injection rules active in this scenario",
    )
    evaluation_criteria: EvaluationCriteriaSpec = Field(
        default_factory=EvaluationCriteriaSpec,
        description="Explicit evaluation assertions for scoring the run",
    )
    safety_constraints: SafetyConstraintsSpec = Field(
        default_factory=SafetyConstraintsSpec,
        description="Safety and step budget constraints",
    )


class ScenarioCreate(BaseModel):
    """Payload required to register a versioned ScenarioDefinition."""

    name: str = Field(
        min_length=1,
        max_length=128,
        description="Logical scenario name (e.g. 'billing-lookup-rate-limit')",
    )
    version: int = Field(
        default=1,
        ge=1,
        le=10000,
        description="Explicit positive integer scenario version",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional human-readable summary of the experiment scenario",
    )
    spec: ScenarioSpec = Field(description="Structured scenario specification")


class ScenarioResponse(BaseModel):
    """Serialized ScenarioDefinition returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    version: int
    description: str | None
    spec: ScenarioSpec
    created_at: datetime
    updated_at: datetime
