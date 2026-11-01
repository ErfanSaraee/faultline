"""Deterministic mock agent adapter for repeatable testing without live LLM dependencies."""

from typing import Any, Literal

from faultline.adapters.base import AgentAdapter, ToolHandler, default_mock_tool_handler
from faultline.schemas.adapter import (
    AgentExecutionOutput,
    AgentStep,
    AgentTaskInput,
    ExecutionStatus,
)


class DeterministicMockAgent(AgentAdapter):
    """Predictable, zero-cost agent implementation for testing FAULTLINE engines."""

    adapter_type = "mock"

    async def execute(
        self,
        *,
        model_name: str,
        config_payload: dict[str, Any],
        task_input: AgentTaskInput,
        tool_handler: ToolHandler | None = None,
    ) -> AgentExecutionOutput:
        """Run a deterministic sequence of model and tool steps based on task_input."""
        active_handler = tool_handler or default_mock_tool_handler
        steps: list[AgentStep] = []
        collected_outputs: list[str] = []
        allow_fallback = bool(config_payload.get(
            "fallback_on_tool_error", False))
        tokens_per_step = int(config_payload.get("tokens_per_step", 25))
        model_latency_ms = float(config_payload.get("model_latency_ms", 10.0))

        for tool_request in task_input.planned_tool_calls:
            # 1. Model invocation step (planning the tool call)
            if len(steps) >= task_input.max_steps:
                return self._build_output(
                    model_name=model_name,
                    status="max_steps_exceeded",
                    steps=steps,
                    final_answer=None,
                    error_message=(
                        f"Execution exceeded max_steps limit ({task_input.max_steps})."
                    ),
                )

            steps.append(
                AgentStep(
                    step_index=len(steps),
                    step_type="model_invocation",
                    name=model_name,
                    status="ok",
                    input_payload={
                        "prompt_summary": task_input.task_prompt[:120],
                        "planned_tool": tool_request.tool_name,
                    },
                    output_payload={
                        "decision": "invoke_tool",
                        "call_id": tool_request.call_id,
                        "tool_name": tool_request.tool_name,
                    },
                    latency_ms=model_latency_ms,
                    tokens_used=tokens_per_step,
                )
            )

            # 2. Tool call execution step
            if len(steps) >= task_input.max_steps:
                return self._build_output(
                    model_name=model_name,
                    status="max_steps_exceeded",
                    steps=steps,
                    final_answer=None,
                    error_message=(
                        f"Execution exceeded max_steps limit ({task_input.max_steps})."
                    ),
                )

            tool_result = await active_handler(tool_request)
            effective_tool = tool_result.tool_name or tool_request.tool_name
            step_status: Literal["ok", "error"] = (
                "ok" if tool_result.status == "success" else "error"
            )

            steps.append(
                AgentStep(
                    step_index=len(steps),
                    step_type="tool_call",
                    name=effective_tool,
                    status=step_status,
                    input_payload={
                        "call_id": tool_request.call_id,
                        "arguments": tool_request.arguments,
                    },
                    output_payload=tool_result.model_dump(mode="json"),
                    latency_ms=tool_result.latency_ms,
                    tokens_used=0,
                )
            )

            if tool_result.status == "error":
                if not allow_fallback:
                    return self._build_output(
                        model_name=model_name,
                        status="failed",
                        steps=steps,
                        final_answer=None,
                        error_message=(
                            f"Tool '{effective_tool}' failed with "
                            f"{tool_result.error_type or 'ToolError'}: "
                            f"{tool_result.error_message or 'Unknown error'}"
                        ),
                    )
                collected_outputs.append(
                    f"[fallback:{effective_tool}={tool_result.error_type}]"
                )
            else:
                collected_outputs.append(f"[ok:{effective_tool}]")

        # 3. Final synthesis step
        if len(steps) >= task_input.max_steps:
            return self._build_output(
                model_name=model_name,
                status="max_steps_exceeded",
                steps=steps,
                final_answer=None,
                error_message=f"Execution exceeded max_steps limit ({task_input.max_steps}).",
            )

        summary_suffix = " ".join(
            collected_outputs) if collected_outputs else "[no-tools]"
        final_answer = f"Resolved task '{task_input.task_prompt}' via {summary_suffix}"

        steps.append(
            AgentStep(
                step_index=len(steps),
                step_type="final_response",
                name=model_name,
                status="ok",
                input_payload={"synthesized_items": len(collected_outputs)},
                output_payload={"final_answer": final_answer},
                latency_ms=model_latency_ms,
                tokens_used=tokens_per_step,
            )
        )

        return self._build_output(
            model_name=model_name,
            status="completed",
            steps=steps,
            final_answer=final_answer,
            error_message=None,
        )

    def _build_output(
        self,
        *,
        model_name: str,
        status: ExecutionStatus,
        steps: list[AgentStep],
        final_answer: str | None,
        error_message: str | None,
    ) -> AgentExecutionOutput:
        total_tokens = sum(step.tokens_used for step in steps)
        total_latency_ms = sum(step.latency_ms for step in steps)
        return AgentExecutionOutput(
            adapter_type=self.adapter_type,
            model_name=model_name,
            status=status,
            final_answer=final_answer,
            steps=steps,
            total_tokens=total_tokens,
            total_latency_ms=total_latency_ms,
            error_message=error_message,
        )
