"""HTTP API endpoints for platform metrics and OpenTelemetry span inspection."""

from typing import Any

from fastapi import APIRouter, Query

from faultline.observability.telemetry import get_telemetry_manager


def create_observability_router() -> APIRouter:
    """Create the router exposing bounded platform metrics and OTel spans."""
    router = APIRouter(
        prefix="/observability",
        tags=["observability"],
    )

    @router.get(
        "/metrics",
        summary="Get bounded-cardinality platform telemetry metrics",
    )
    async def get_platform_metrics() -> dict[str, Any]:
        telemetry = get_telemetry_manager()
        return telemetry.metrics.snapshot()

    @router.get(
        "/spans",
        summary="Inspect recent OpenTelemetry spans emitted by the platform",
    )
    async def get_recent_otel_spans(
        limit: int = Query(default=50, ge=1, le=500),  # noqa: B008
    ) -> list[dict[str, Any]]:
        telemetry = get_telemetry_manager()
        return telemetry.get_recent_spans(limit=limit)

    return router
