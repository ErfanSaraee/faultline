"""Automated tests for Phase 1 configuration and system health endpoint."""

from httpx import ASGITransport, AsyncClient

from faultline import __version__
from faultline.api.app import create_app
from faultline.core.config import Settings


async def test_health_endpoint_returns_expected_contract() -> None:
    """Verify /api/v1/health returns 200 OK with accurate service metadata."""
    test_settings = Settings(env="testing", app_name="faultline-test")
    app = create_app(settings=test_settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "faultline-test"
    assert payload["version"] == __version__
    assert payload["environment"] == "testing"
    assert "timestamp" in payload


def test_default_settings_validation() -> None:
    """Verify default configuration values are safe and deterministic."""
    settings = Settings()
    assert settings.app_name == "faultline"
    assert settings.debug is False
    assert settings.api_v1_prefix == "/api/v1"
