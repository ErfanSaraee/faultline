"""OpenTelemetry tracing and bounded-cardinality platform metrics for FAULTLINE."""

from collections import Counter
from collections.abc import Sequence
from typing import Any

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

from faultline.schemas.adapter import AgentExecutionOutput


class PlatformMetricsCollector:
    """In-memory bounded-cardinality metrics collector for platform observability."""

    def __init__(self) -> None:
        self._runs_by_label: Counter[tuple[str, str, str]] = Counter()
        self._faults_by_type: Counter[str] = Counter()
        self._evaluations_by_outcome: Counter[str] = Counter()
        self._total_tokens_consumed: int = 0

    def record_run(
        self,
        *,
        adapter_type: str,
        run_mode: str,
        status: str,
        tokens_used: int,
    ) -> None:
        """Increment run counters using strictly bounded-cardinality labels."""
        self._runs_by_label[(adapter_type, run_mode, status)] += 1
        self._total_tokens_consumed += max(0, tokens_used)

    def record_injected_fault(self, fault_type: str) -> None:
        """Increment injected fault counter by fault_type taxonomy."""
        self._faults_by_type[fault_type] += 1

    def record_evaluation(self, *, task_succeeded: bool) -> None:
        """Increment evaluation counter by boolean pass/fail outcome."""
        outcome = "passed" if task_succeeded else "failed"
        self._evaluations_by_outcome[outcome] += 1

    def snapshot(self) -> dict[str, Any]:
        """Return a structured snapshot of all bounded-cardinality platform metrics."""
        runs_breakdown = [
            {
                "adapter_type": adapter,
                "run_mode": mode,
                "status": status,
                "count": count,
            }
            for (adapter, mode, status), count in sorted(self._runs_by_label.items())
        ]
        faults_breakdown = {
            fault_type: count
            for fault_type, count in sorted(self._faults_by_type.items())
        }
        evaluations_breakdown = {
            outcome: count
            for outcome, count in sorted(self._evaluations_by_outcome.items())
        }
        return {
            "runs_total": sum(self._runs_by_label.values()),
            "runs_by_bounded_labels": runs_breakdown,
            "injected_faults_total": sum(self._faults_by_type.values()),
            "injected_faults_by_type": faults_breakdown,
            "evaluations_total": sum(self._evaluations_by_outcome.values()),
            "evaluations_by_outcome": evaluations_breakdown,
            "tokens_consumed_total": self._total_tokens_consumed,
        }


class TelemetryManager:
    """Manages OpenTelemetry TracerProvider, span emission, and bounded metrics."""

    def __init__(self) -> None:
        resource = Resource.create(
            {
                "service.name": "faultline",
                "service.component": "reliability-engine",
            }
        )
        self._exporter = InMemorySpanExporter()
        self._provider = TracerProvider(resource=resource)
        self._provider.add_span_processor(SimpleSpanProcessor(self._exporter))
        self._tracer = self._provider.get_tracer("faultline.execution")
        self.metrics = PlatformMetricsCollector()

    def record_execution_trace(
        self,
        *,
        run_mode: str,
        scenario_name: str,
        execution_output: AgentExecutionOutput,
        injected_fault_types: Sequence[str],
    ) -> str:
        """Emit OpenTelemetry parent and step spans and return the hex OTel trace_id."""
        with self._tracer.start_as_current_span("faultline.execution.run") as root_span:
            root_span.set_attribute(
                "gen_ai.system", execution_output.adapter_type)
            root_span.set_attribute(
                "gen_ai.request.model", execution_output.model_name)
            root_span.set_attribute("faultline.run.mode", run_mode)
            root_span.set_attribute(
                "faultline.run.status", execution_output.status)
            root_span.set_attribute("faultline.scenario.name", scenario_name)
            root_span.set_attribute(
                "faultline.run.total_tokens", execution_output.total_tokens
            )
            root_span.set_attribute(
                "faultline.run.total_latency_ms", execution_output.total_latency_ms
            )

            if execution_output.status != "completed":
                root_span.set_status(
                    Status(
                        StatusCode.ERROR,
                        description=execution_output.error_message or "Run failed",
                    )
                )
            else:
                root_span.set_status(Status(StatusCode.OK))

            for step in execution_output.steps:
                span_name = f"faultline.step.{step.step_type}"
                with self._tracer.start_as_current_span(span_name) as step_span:
                    step_span.set_attribute(
                        "faultline.step.index", step.step_index)
                    step_span.set_attribute(
                        "faultline.step.type", step.step_type)
                    step_span.set_attribute("faultline.step.name", step.name)
                    step_span.set_attribute(
                        "faultline.step.status", step.status)
                    step_span.set_attribute(
                        "faultline.step.latency_ms", step.latency_ms
                    )
                    step_span.set_attribute(
                        "faultline.step.tokens_used", step.tokens_used
                    )
                    if step.status == "error":
                        step_span.set_status(Status(StatusCode.ERROR))
                    else:
                        step_span.set_status(Status(StatusCode.OK))

            trace_id_int = root_span.get_span_context().trace_id
            otel_trace_id = f"{trace_id_int:032x}"

        self.metrics.record_run(
            adapter_type=execution_output.adapter_type,
            run_mode=run_mode,
            status=execution_output.status,
            tokens_used=execution_output.total_tokens,
        )
        for fault_type in injected_fault_types:
            self.metrics.record_injected_fault(fault_type)

        return otel_trace_id

    def get_recent_spans(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return serialized recent OpenTelemetry spans for inspection and verification."""
        finished: tuple[ReadableSpan, ...] = self._exporter.get_finished_spans()
        recent = finished[-limit:] if limit > 0 else finished
        serialized: list[dict[str, Any]] = []
        for span in recent:
            ctx = span.get_span_context()
            serialized.append(
                {
                    "name": span.name,
                    "trace_id": f"{ctx.trace_id:032x}" if ctx is not None else "",
                    "span_id": f"{ctx.span_id:016x}" if ctx is not None else "",
                    "status_code": span.status.status_code.name,
                    "attributes": dict(span.attributes or {}),
                }
            )
        return serialized


_GLOBAL_TELEMETRY = TelemetryManager()


def get_telemetry_manager() -> TelemetryManager:
    """Return the singleton TelemetryManager instance."""
    return _GLOBAL_TELEMETRY
