"""FastAPI application factory and core system routes."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel, Field

from faultline import __version__
from faultline.core.config import Settings, get_settings


class HealthResponse(BaseModel):
    """Schema for the service health and readiness response."""

    status: Literal["ok"] = Field(
        default="ok", description="Service health indicator")
    service: str = Field(description="Application name")
    version: str = Field(description="Semantic version of the running service")
    environment: str = Field(description="Current runtime environment")
    timestamp: datetime = Field(
        description="UTC timestamp of health check generation")


def create_health_router() -> APIRouter:
    """Create the router handling liveness and readiness probes."""
    router = APIRouter(tags=["system"])

    @router.get(
        "/health",
        response_model=HealthResponse,
        summary="Service liveness check",
    )
    async def health_check(
        settings: Settings = Depends(get_settings),  # noqa: B008
    ) -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            version=__version__,
            environment=settings.env,
            timestamp=datetime.now(UTC),
        )

    return router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Instantiate and configure the FastAPI application.

    Args:
        settings: Optional custom settings override (primarily used for isolated testing).
    """
    active_settings = settings or get_settings()

    app = FastAPI(
        title="FAULTLINE API",
        description=(
            "Agent Reliability Engineering, Chaos Testing, Replay, "
            "Evaluation & Recovery Platform"
        ),
        version=__version__,
        debug=active_settings.debug,
    )

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: active_settings

    app.include_router(create_health_router(),
                       prefix=active_settings.api_v1_prefix)
    return app


app = create_app()
