"""Automated tests for Phase 4 AgentAdapter contract, registry, and DeterministicMockAgent."""

import pytest

from faultline.adapters import AdapterRegistry, DeterministicMockAgent
from faultline.core.errors import UnsupportedAdapterError
from faultline.schemas.adapter import (
    AgentTaskInput,
    ToolCallRequest,
    ToolCallResult,
)


async def test_mock_agent_executes_multi_tool_workflow_deterministically() -> None:
    """Verify DeterministicMockAgent produces exact step sequences, tokens, and latencies."""
    agent = DeterministicMockAgent()
    task_input = AgentTaskInput(
        task_prompt="Summarize Q3 cloud infrastructure incidents.",
        planned_tool_calls=[
            ToolCallRequest(
                call_id="call-1",
                tool_name="search_incidents",
                arguments={"quarter": "Q3"},
            ),
            ToolCallRequest(
                call_id="call-2",
                tool_name="fetch_postmortem",
                arguments={"incident_id": "INC-402"},
            ),
        ],
        max_steps=10,
    )

    result = await agent.execute(
        model_name="mock-deterministic-v1",
        config_payload={"tokens_per_step": 30, "model_latency_ms": 12.0},
        task_input=task_input,
    )

    assert result.status == "completed"
    assert result.adapter_type == "mock"
    assert result.model_name == "mock-deterministic-v1"
    assert result.error_message is None
    assert result.final_answer is not None
    assert "[ok:search_incidents] [ok:fetch_postmortem]" in result.final_answer

    # 2 tools * (1 model step + 1 tool step) + 1 final response step = 5 steps
    assert len(result.steps) == 5
    assert [s.step_type for s in result.steps] == [
        "model_invocation",
        "tool_call",
        "model_invocation",
        "tool_call",
        "final_response",
    ]
    # 3 model/final steps * 30 tokens = 90 tokens
    assert result.total_tokens == 90
    # 3 model steps * 12ms + 2 tool steps * 5ms = 46.0ms
    assert result.total_latency_ms == 46.0


async def test_mock_agent_halts_on_tool_failure_by_default() -> None:
    """Verify agent transitions to 'failed' status when a tool returns an error."""
    agent = DeterministicMockAgent()
    task_input = AgentTaskInput(
        task_prompt="Retrieve customer billing record.",
        planned_tool_calls=[
            ToolCallRequest(
                call_id="call-err-1",
                tool_name="billing_service",
                arguments={"customer_id": "CUST-99"},
            ),
        ],
    )

    async def failing_tool_handler(request: ToolCallRequest) -> ToolCallResult:
        return ToolCallResult(
            call_id=request.call_id,
            tool_name=request.tool_name,
            status="error",
            error_type="HTTP_429_RATE_LIMIT",
            error_message="Rate limit exceeded on billing_service",
            latency_ms=45.0,
        )

    result = await agent.execute(
        model_name="mock-v1",
        config_payload={},
        task_input=task_input,
        tool_handler=failing_tool_handler,
    )

    assert result.status == "failed"
    assert result.final_answer is None
    assert result.error_message is not None
    assert "HTTP_429_RATE_LIMIT" in result.error_message
    assert len(result.steps) == 2
    assert result.steps[1].step_type == "tool_call"
    assert result.steps[1].status == "error"


async def test_mock_agent_completes_with_fallback_when_configured() -> None:
    """Verify agent continues with fallback marker when fallback_on_tool_error is enabled."""
    agent = DeterministicMockAgent()
    task_input = AgentTaskInput(
        task_prompt="Check optional cache service.",
        planned_tool_calls=[
            ToolCallRequest(
                call_id="call-cache-1",
                tool_name="redis_cache_lookup",
                arguments={"key": "user_profile"},
            ),
        ],
    )

    async def timeout_tool_handler(request: ToolCallRequest) -> ToolCallResult:
        return ToolCallResult(
            call_id=request.call_id,
            tool_name=request.tool_name,
            status="error",
            error_type="TIMEOUT",
            error_message="Cache read timed out after 2000ms",
            latency_ms=2000.0,
        )

    result = await agent.execute(
        model_name="mock-v1",
        config_payload={"fallback_on_tool_error": True},
        task_input=task_input,
        tool_handler=timeout_tool_handler,
    )

    assert result.status == "completed"
    assert result.final_answer is not None
    assert "[fallback:redis_cache_lookup=TIMEOUT]" in result.final_answer
    assert len(result.steps) == 3


async def test_mock_agent_enforces_max_steps_guardrail() -> None:
    """Verify agent aborts with 'max_steps_exceeded' when step budget is exhausted."""
    agent = DeterministicMockAgent()
    task_input = AgentTaskInput(
        task_prompt="Run multi-step research.",
        planned_tool_calls=[
            ToolCallRequest(call_id="c1", tool_name="tool_a", arguments={}),
            ToolCallRequest(call_id="c2", tool_name="tool_b", arguments={}),
        ],
        max_steps=2,
    )

    result = await agent.execute(
        model_name="mock-v1",
        config_payload={},
        task_input=task_input,
    )

    assert result.status == "max_steps_exceeded"
    assert result.final_answer is None
    assert len(result.steps) == 2
    assert result.error_message is not None
    assert "max_steps" in result.error_message


def test_adapter_registry_lookup_and_unsupported_error() -> None:
    """Verify AdapterRegistry resolves registered adapters and rejects unknown types."""
    registry = AdapterRegistry()
    assert "mock" in registry.list_supported_types()

    adapter = registry.get("mock")
    assert isinstance(adapter, DeterministicMockAgent)

    with pytest.raises(UnsupportedAdapterError) as exc_info:
        registry.get("nonexistent_framework")

    assert exc_info.value.adapter_type == "nonexistent_framework"
