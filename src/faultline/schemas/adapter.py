"""Pydantic v2 data contracts for framework-agnostic agent execution and tracing."""

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentStepType = Literal["model_invocation",
                        "tool_call", "final_response", "error"]
ExecutionStatus = Literal["completed", "failed", "max_steps_exceeded"]


class ToolCallRequest(BaseModel):
    """Structured request emitted by an agent when invoking an external tool."""

    call_id: str = Field(
        min_length=1, description="Unique identifier for this tool invocation")
    tool_name: str = Field(
        min_length=1, description="Logical name of the invoked tool")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured arguments passed to the tool",
    )


class ToolCallResult(BaseModel):
    """Structured result returned to the agent from a tool invocation."""

    call_id: str = Field(
        min_length=1, description="Correlated tool call identifier")
    tool_name: str = Field(
        min_length=1, description="Logical name of the invoked tool")
    status: Literal["success", "error"] = Field(
        description="Outcome of the tool execution")
    output: dict[str, Any] | None = Field(
        default=None,
        description="Sanitized structured output when status is 'success'",
    )
    error_type: str | None = Field(
        default=None,
        description="Machine-readable error classification when status is 'error'",
    )
    error_message: str | None = Field(
        default=None,
        description="Diagnostic error message when status is 'error'",
    )
    latency_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Execution latency of the tool call in milliseconds",
    )


class AgentStep(BaseModel):
    """Single observable execution step captured during an agent run."""

    step_index: int = Field(
        ge=0, description="Zero-based sequential step number")
    step_type: AgentStepType = Field(
        description="Category of observable execution step")
    name: str = Field(
        min_length=1, description="Component or tool name executed in this step")
    status: Literal["ok", "error"] = Field(
        description="Step completion status")
    input_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitized observable input metadata",
    )
    output_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitized observable output or error metadata",
    )
    latency_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Duration of this step in milliseconds",
    )
    tokens_used: int = Field(
        default=0,
        ge=0,
        description="Total LLM tokens consumed during this step, if applicable",
    )


class AgentTaskInput(BaseModel):
    """Standardized input contract passed to any AgentAdapter.execute() call."""

    task_prompt: str = Field(
        min_length=1,
        max_length=20000,
        description="Primary task instruction for the agent to resolve",
    )
    planned_tool_calls: list[ToolCallRequest] = Field(
        default_factory=list,
        description="Optional deterministic sequence of tool calls for mock/scripted runs",
    )
    context_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Supplementary scenario fixtures or execution context",
    )
    max_steps: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Hard upper bound on observable execution steps to prevent infinite loops",
    )


class AgentExecutionOutput(BaseModel):
    """Standardized execution result returned by any AgentAdapter implementation."""

    adapter_type: str = Field(
        description="Identifier of the adapter that executed the run")
    model_name: str = Field(
        description="Model identifier used during execution")
    status: ExecutionStatus = Field(
        description="Terminal outcome of the agent execution")
    final_answer: str | None = Field(
        default=None,
        description="Final user-facing output produced by the agent, if completed",
    )
    steps: list[AgentStep] = Field(
        default_factory=list,
        description="Ordered sequence of observable steps captured during execution",
    )
    total_tokens: int = Field(
        default=0,
        ge=0,
        description="Cumulative tokens consumed across all steps",
    )
    total_latency_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Cumulative execution time in milliseconds",
    )
    error_message: str | None = Field(
        default=None,
        description="Terminal failure explanation if status is not 'completed'",
    )
