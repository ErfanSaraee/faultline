"""FastAPI application factory and core system routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal, cast

from fastapi import APIRouter, Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncEngine

from faultline import __version__
from faultline.core.config import Settings, get_settings
from faultline.db.session import (
    create_db_engine,
    create_session_factory,
    verify_database_connection,
)


class HealthResponse(BaseModel):
    """Schema for the service liveness response."""

    status: Literal["ok"] = Field(
        default="ok", description="Service liveness indicator")
    service: str = Field(description="Application name")
    version: str = Field(description="Semantic version of the running service")
    environment: str = Field(description="Current runtime environment")
    timestamp: datetime = Field(
        description="UTC timestamp of health check generation")


class ReadinessResponse(BaseModel):
    """Schema for the service readiness response including database status."""

    status: Literal["ready", "degraded"] = Field(
        description="Overall readiness state")
    database: Literal["connected", "unreachable"] = Field(
        description="Database connectivity status"
    )
    timestamp: datetime = Field(description="UTC timestamp of readiness check")


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

    @router.get(
        "/health/ready",
        response_model=ReadinessResponse,
        summary="Service and database readiness check",
    )
    async def readiness_check(request: Request) -> JSONResponse:
        engine = cast(AsyncEngine, request.app.state.db_engine)
        is_connected = await verify_database_connection(engine)

        if is_connected:
            payload = ReadinessResponse(
                status="ready",
                database="connected",
                timestamp=datetime.now(UTC),
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=payload.model_dump(mode="json"),
            )

        payload = ReadinessResponse(
            status="degraded",
            database="unreachable",
            timestamp=datetime.now(UTC),
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(mode="json"),
        )

    return router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Instantiate and configure the FastAPI application.

    Args:
        settings: Optional custom settings override (primarily used for isolated testing).
    """
    active_settings = settings or get_settings()
    db_engine = create_db_engine(active_settings)
    session_factory = create_session_factory(db_engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await db_engine.dispose()

    app = FastAPI(
        title="FAULTLINE API",
        description=(
            "Agent Reliability Engineering, Chaos Testing, Replay, "
            "Evaluation & Recovery Platform"
        ),
        version=__version__,
        debug=active_settings.debug,
        lifespan=lifespan,
    )

    app.state.db_engine = db_engine
    app.state.session_factory = session_factory

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: active_settings

    app.include_router(create_health_router(),
                       prefix=active_settings.api_v1_prefix)
    return app


app = create_app()
