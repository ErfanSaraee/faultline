"""Recovery policy interceptor implementing bounded retries and fallback tool routing."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

from faultline.adapters.base import ToolHandler
from faultline.schemas.adapter import (
    AgentExecutionOutput,
    AgentStep,
    ToolCallRequest,
    ToolCallResult,
)
from faultline.schemas.execution import RecoveryPolicySpec, RecoverySummary


@dataclass
class _RecordedAttempt:
    """Internal record of a single tool invocation attempt under a recovery policy."""

    request: ToolCallRequest
    result: ToolCallResult
    attempt_kind: Literal["initial", "retry", "fallback"]
    tokens_overhead: int


class RecoveryToolInterceptor:
    """Applies bounded retry and fallback-tool policies around a ToolHandler."""

    def __init__(self, policy: RecoveryPolicySpec) -> None:
        self._policy = policy
        self._attempts_by_call_id: dict[str,
                                        list[_RecordedAttempt]] = defaultdict(list)
        self._retries_performed = 0
        self._fallbacks_performed = 0
        self._recoveries_succeeded = 0
        self._recoveries_exhausted = 0

    @property
    def summary(self) -> RecoverySummary:
        """Return aggregated recovery telemetry for run_metadata."""
        return RecoverySummary(
            strategy=self._policy.strategy,
            retries_performed=self._retries_performed,
            fallbacks_performed=self._fallbacks_performed,
            recoveries_succeeded=self._recoveries_succeeded,
            recoveries_exhausted=self._recoveries_exhausted,
        )

    def wrap(self, downstream_handler: ToolHandler) -> ToolHandler:
        """Wrap a downstream (fault-injected) ToolHandler with recovery policy logic."""

        async def recovering_tool_handler(request: ToolCallRequest) -> ToolCallResult:
            initial_result = await downstream_handler(request)
            self._attempts_by_call_id[request.call_id].append(
                _RecordedAttempt(
                    request=request,
                    result=initial_result,
                    attempt_kind="initial",
                    tokens_overhead=0,
                )
            )

            if initial_result.status == "success":
                return initial_result

            current_result = initial_result

            # گام اول بازیابی: تلاش مجدد بودجه‌بندی‌شده برای خطاهای گذرا
            if self._policy.strategy in ("retry", "retry_then_fallback"):
                for retry_num in range(1, self._policy.max_retries + 1):
                    if not self._is_retryable(current_result):
                        break

                    self._retries_performed += 1
                    retry_req = ToolCallRequest(
                        call_id=f"{request.call_id}-retry-{retry_num}",
                        tool_name=request.tool_name,
                        arguments=request.arguments,
                    )
                    raw_retry_res = await downstream_handler(retry_req)
                    adjusted_res = raw_retry_res.model_copy(
                        update={
                            "latency_ms": (
                                raw_retry_res.latency_ms + self._policy.backoff_ms
                            )
                        }
                    )
                    self._attempts_by_call_id[request.call_id].append(
                        _RecordedAttempt(
                            request=retry_req,
                            result=adjusted_res,
                            attempt_kind="retry",
                            tokens_overhead=self._policy.retry_token_overhead,
                        )
                    )
                    current_result = adjusted_res
                    if current_result.status == "success":
                        self._recoveries_succeeded += 1
                        return current_result

            # گام دوم بازیابی: هدایت به ابزار پشتیبان در صورت تعریف شدن
            if (
                current_result.status == "error"
                and self._policy.strategy in ("fallback_tool", "retry_then_fallback")
            ):
                fallback_tool = self._policy.fallback_tool_map.get(
                    request.tool_name)
                if fallback_tool is not None:
                    self._fallbacks_performed += 1
                    fallback_req = ToolCallRequest(
                        call_id=f"{request.call_id}-fallback",
                        tool_name=fallback_tool,
                        arguments=request.arguments,
                    )
                    fallback_res = await downstream_handler(fallback_req)
                    self._attempts_by_call_id[request.call_id].append(
                        _RecordedAttempt(
                            request=fallback_req,
                            result=fallback_res,
                            attempt_kind="fallback",
                            tokens_overhead=self._policy.retry_token_overhead,
                        )
                    )
                    current_result = fallback_res
                    if current_result.status == "success":
                        self._recoveries_succeeded += 1
                        return current_result

            self._recoveries_exhausted += 1
            return current_result

        return recovering_tool_handler

    def expand_execution_output(
        self,
        execution_output: AgentExecutionOutput,
    ) -> AgentExecutionOutput:
        """Expand logical tool_call steps into per-attempt observable steps."""
        expanded_steps: list[AgentStep] = []

        for step in execution_output.steps:
            if step.step_type != "tool_call":
                expanded_steps.append(
                    step.model_copy(update={"step_index": len(expanded_steps)})
                )
                continue

            call_id = str(step.input_payload.get("call_id", ""))
            attempts = self._attempts_by_call_id.get(call_id)
            if not attempts:
                expanded_steps.append(
                    step.model_copy(update={"step_index": len(expanded_steps)})
                )
                continue

            for attempt in attempts:
                step_status: Literal["ok", "error"] = (
                    "ok" if attempt.result.status == "success" else "error"
                )
                output_payload: dict[str, Any] = {
                    **attempt.result.model_dump(mode="json"),
                    "recovery_attempt_kind": attempt.attempt_kind,
                }
                expanded_steps.append(
                    AgentStep(
                        step_index=len(expanded_steps),
                        step_type="tool_call",
                        name=attempt.request.tool_name,
                        status=step_status,
                        input_payload={
                            "call_id": attempt.request.call_id,
                            "arguments": attempt.request.arguments,
                            "attempt_kind": attempt.attempt_kind,
                        },
                        output_payload=output_payload,
                        latency_ms=attempt.result.latency_ms,
                        tokens_used=attempt.tokens_overhead,
                    )
                )

        total_tokens = sum(s.tokens_used for s in expanded_steps)
        total_latency_ms = sum(s.latency_ms for s in expanded_steps)

        return execution_output.model_copy(
            update={
                "steps": expanded_steps,
                "total_tokens": total_tokens,
                "total_latency_ms": total_latency_ms,
            }
        )

    def _is_retryable(self, result: ToolCallResult) -> bool:
        if result.error_type is None:
            return False
        return result.error_type in self._policy.retryable_fault_types
