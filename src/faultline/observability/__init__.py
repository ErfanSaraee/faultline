"""Observability package providing OpenTelemetry tracing and bounded metrics."""

from faultline.observability.telemetry import (
    PlatformMetricsCollector,
    TelemetryManager,
    get_telemetry_manager,
)

__all__ = [
    "PlatformMetricsCollector",
    "TelemetryManager",
    "get_telemetry_manager",
]
