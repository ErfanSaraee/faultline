"""Automated tests for Phase 2 database infrastructure, sessions, and readiness probes."""

from httpx import ASGITransport, AsyncClient
from sqlalchemy import String, select
from sqlalchemy.orm import Mapped, mapped_column

from faultline.api.app import create_app
from faultline.core.config import Settings
from faultline.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from faultline.db.session import (
    create_db_engine,
    create_session_factory,
    verify_database_connection,
)


class _SampleProbeModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Transient ORM model used strictly to test Base metadata and mixins."""

    __tablename__ = "sample_probe_records"

    name: Mapped[str] = mapped_column(String(64), nullable=False)


async def test_async_engine_and_mixins_roundtrip() -> None:
    """Verify AsyncEngine, session factory, UUID primary key, and UTC timestamps."""
    settings = Settings(
        env="testing", database_url="sqlite+aiosqlite:///:memory:")
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        record = _SampleProbeModel(name="baseline-probe")
        session.add(record)
        await session.commit()
        await session.refresh(record)

        assert record.id is not None
        assert record.created_at is not None
        assert record.updated_at is not None

    async with session_factory() as session:
        result = await session.execute(
            select(_SampleProbeModel).where(
                _SampleProbeModel.name == "baseline-probe")
        )
        fetched = result.scalar_one()
        assert fetched.id == record.id

    assert await verify_database_connection(engine) is True
    await engine.dispose()


async def test_readiness_endpoint_returns_200_when_db_is_connected() -> None:
    """Verify /api/v1/health/ready returns 200 Ready when database responds."""
    settings = Settings(
        env="testing", database_url="sqlite+aiosqlite:///:memory:")
    app = create_app(settings=settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["database"] == "connected"
    assert "timestamp" in payload

    await app.state.db_engine.dispose()


async def test_readiness_endpoint_returns_503_when_db_is_unreachable() -> None:
    """Verify /api/v1/health/ready returns 503 Degraded when database connection fails."""
    # Port 54329 is intentionally unbound to simulate a down PostgreSQL instance
    settings = Settings(
        env="testing",
        database_url="postgresql+asyncpg://invalid:invalid@127.0.0.1:54329/unreachable",
    )
    app = create_app(settings=settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["database"] == "unreachable"

    await app.state.db_engine.dispose()
