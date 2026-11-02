"""FastAPI application factory and core system routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal, cast

from fastapi import APIRouter, Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncEngine

from faultline import __version__
from faultline.api.diagnosis import create_diagnosis_router
from faultline.api.evaluations import create_evaluation_router
from faultline.api.observability import create_observability_router
from faultline.api.regression import create_regression_router
from faultline.api.replay import create_replay_router
from faultline.api.runs import create_run_router
from faultline.api.scenarios import create_scenario_router
from faultline.api.workspace import create_workspace_router
from faultline.core.config import Settings, get_settings
from faultline.core.errors import (
    EntityConflictError,
    EntityNotFoundError,
    PreconditionFailedError,
    UnsupportedAdapterError,
)
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


def register_exception_handlers(app: FastAPI) -> None:
    """Register domain-to-HTTP exception handlers on the FastAPI instance."""

    @app.exception_handler(EntityNotFoundError)
    async def handle_not_found(
        _request: Request,
        exc: EntityNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message},
        )

    @app.exception_handler(EntityConflictError)
    async def handle_conflict(
        _request: Request,
        exc: EntityConflictError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message},
        )

    @app.exception_handler(UnsupportedAdapterError)
    async def handle_unsupported_adapter(
        _request: Request,
        exc: UnsupportedAdapterError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exc.message},
        )

    @app.exception_handler(PreconditionFailedError)
    async def handle_precondition_failed(
        _request: Request,
        exc: PreconditionFailedError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exc.message},
        )


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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.db_engine = db_engine
    app.state.session_factory = session_factory

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: active_settings

    register_exception_handlers(app)
    app.include_router(create_health_router(),
                       prefix=active_settings.api_v1_prefix)
    app.include_router(create_workspace_router(),
                       prefix=active_settings.api_v1_prefix)
    app.include_router(create_scenario_router(),
                       prefix=active_settings.api_v1_prefix)
    app.include_router(create_run_router(),
                       prefix=active_settings.api_v1_prefix)
    app.include_router(create_evaluation_router(),
                       prefix=active_settings.api_v1_prefix)
    app.include_router(create_replay_router(),
                       prefix=active_settings.api_v1_prefix)
    app.include_router(create_diagnosis_router(),
                       prefix=active_settings.api_v1_prefix)
    app.include_router(create_regression_router(),
                       prefix=active_settings.api_v1_prefix)
    app.include_router(
        create_observability_router(), prefix=active_settings.api_v1_prefix
    )
    return app


app = create_app()
