"""Framework-agnostic AgentAdapter interface and tool handler contract."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from faultline.schemas.adapter import (
    AgentExecutionOutput,
    AgentTaskInput,
    ToolCallRequest,
    ToolCallResult,
)

ToolHandler = Callable[[ToolCallRequest], Awaitable[ToolCallResult]]


async def default_mock_tool_handler(request: ToolCallRequest) -> ToolCallResult:
    """Execute a deterministic in-memory tool simulation when no custom handler is supplied."""
    return ToolCallResult(
        call_id=request.call_id,
        tool_name=request.tool_name,
        status="success",
        output={
            "tool": request.tool_name,
            "echo_args": request.arguments,
            "simulated": True,
        },
        latency_ms=5.0,
    )


class AgentAdapter(ABC):
    """Abstract base contract that all agent framework integrations must implement."""

    adapter_type: str

    @abstractmethod
    async def execute(
        self,
        *,
        model_name: str,
        config_payload: dict[str, Any],
        task_input: AgentTaskInput,
        tool_handler: ToolHandler | None = None,
    ) -> AgentExecutionOutput:
        """Execute an agent task and return structured observable steps and outcome."""
