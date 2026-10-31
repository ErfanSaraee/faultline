"""Deterministic fault injection interceptor for agent tool invocations."""

from collections import defaultdict
from typing import Any

from faultline.adapters.base import ToolHandler
from faultline.schemas.adapter import ToolCallRequest, ToolCallResult
from faultline.schemas.execution import InjectedFaultEvent
from faultline.schemas.scenario import FaultRuleSpec


class FaultInjector:
    """Intercepts ToolCallRequests and deterministically injects configured faults."""

    def __init__(self, fault_rules: list[FaultRuleSpec]) -> None:
        self._rules = fault_rules
        self._call_counts: dict[str, int] = defaultdict(int)
        self._triggered_events: list[InjectedFaultEvent] = []

    @property
    def triggered_events(self) -> list[InjectedFaultEvent]:
        """Return an ordered copy of all fault events triggered during execution."""
        return list(self._triggered_events)

    def wrap(self, base_handler: ToolHandler) -> ToolHandler:
        """Wrap a healthy ToolHandler with deterministic fault interception logic."""

        async def intercepting_tool_handler(request: ToolCallRequest) -> ToolCallResult:
            self._call_counts[request.tool_name] += 1
            current_invocation = self._call_counts[request.tool_name]

            matching_rule = self._find_matching_rule(
                tool_name=request.tool_name,
                invocation_number=current_invocation,
            )
            if matching_rule is None:
                return await base_handler(request)

            self._triggered_events.append(
                InjectedFaultEvent(
                    call_id=request.call_id,
                    tool_name=request.tool_name,
                    invocation_number=current_invocation,
                    fault_type=matching_rule.fault_type,
                    error_message=matching_rule.error_message,
                    injected_latency_ms=matching_rule.injected_latency_ms,
                )
            )
            return self._build_fault_result(request=request, rule=matching_rule)

        return intercepting_tool_handler

    def _find_matching_rule(
        self,
        *,
        tool_name: str,
        invocation_number: int,
    ) -> FaultRuleSpec | None:
        for rule in self._rules:
            if (
                rule.target_tool == tool_name
                and rule.trigger_on_call == invocation_number
            ):
                return rule
        return None

    def _build_fault_result(
        self,
        *,
        request: ToolCallRequest,
        rule: FaultRuleSpec,
    ) -> ToolCallResult:
        fault_output: dict[str, Any] | None = None

        if rule.fault_type == "MALFORMED_JSON":
            fault_output = {
                "raw_corrupted_payload": '{"corrupted": true, "unterminated_value',
            }
        elif rule.fault_type == "EMPTY_RESPONSE":
            fault_output = {}
        elif rule.fault_type == "CONTRADICTORY_DATA":
            fault_output = {
                "contradiction_injected": True,
                "conflicting_statement": rule.error_message,
            }

        return ToolCallResult(
            call_id=request.call_id,
            tool_name=request.tool_name,
            status="error",
            output=fault_output,
            error_type=rule.fault_type,
            error_message=rule.error_message,
            latency_ms=rule.injected_latency_ms,
        )
