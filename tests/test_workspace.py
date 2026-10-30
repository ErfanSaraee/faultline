"""Automated tests for Phase 3 Project and AgentConfig domain, repositories, and APIs."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from faultline.api.app import create_app
from faultline.core.config import Settings
from faultline.db.base import Base


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    """Provide an isolated HTTPX AsyncClient backed by an in-memory SQLite database."""
    settings = Settings(
        env="testing", database_url="sqlite+aiosqlite:///:memory:")
    app = create_app(settings=settings)

    async with app.state.db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    await app.state.db_engine.dispose()


async def test_create_get_and_list_projects(api_client: AsyncClient) -> None:
    """Verify creating, fetching, and listing project workspaces."""
    create_resp = await api_client.post(
        "/api/v1/projects",
        json={
            "slug": "research-agent-lab",
            "name": "Research Agent Lab",
            "description": "Reliability evaluation suite for tool-using RAG agents.",
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    project_id = created["id"]
    assert created["slug"] == "research-agent-lab"
    assert created["name"] == "Research Agent Lab"

    # Duplicate slug must return 409 Conflict
    conflict_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "research-agent-lab", "name": "Duplicate Project"},
    )
    assert conflict_resp.status_code == 409

    # Fetch by ID
    get_resp = await api_client.get(f"/api/v1/projects/{project_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == project_id

    # List projects
    list_resp = await api_client.get("/api/v1/projects")
    assert list_resp.status_code == 200
    projects = list_resp.json()
    assert len(projects) == 1
    assert projects[0]["slug"] == "research-agent-lab"


async def test_get_nonexistent_project_returns_404(api_client: AsyncClient) -> None:
    """Verify requesting an unknown project UUID returns 404 Not Found."""
    missing_id = uuid4()
    response = await api_client.get(f"/api/v1/projects/{missing_id}")
    assert response.status_code == 404
    assert str(missing_id) in response.json()["detail"]


async def test_versioned_agent_config_lifecycle(api_client: AsyncClient) -> None:
    """Verify registering multiple versions of an agent config and preventing duplicates."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "finops-assistant", "name": "FinOps Assistant"},
    )
    project_id = proj_resp.json()["id"]

    # Create version 1
    v1_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "finops-router",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-deterministic-v1",
            "config_payload": {"max_steps": 5, "timeout_seconds": 10},
            "secret_refs": {"llm_api_key": "OPENAI_API_KEY"},
        },
    )
    assert v1_resp.status_code == 201
    v1_data = v1_resp.json()
    assert v1_data["version"] == 1
    assert v1_data["secret_refs"] == {"llm_api_key": "OPENAI_API_KEY"}

    # Duplicate version 1 must return 409 Conflict
    dup_v1_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "finops-router",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-deterministic-v1",
        },
    )
    assert dup_v1_resp.status_code == 409

    # Create version 2 under the same logical name
    v2_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "finops-router",
            "version": 2,
            "adapter_type": "langgraph",
            "model_name": "gpt-4o-mini",
            "config_payload": {"max_steps": 8, "timeout_seconds": 15},
            "secret_refs": {"llm_api_key": "OPENAI_API_KEY"},
        },
    )
    assert v2_resp.status_code == 201
    assert v2_resp.json()["version"] == 2

    # List all versions
    list_resp = await api_client.get(f"/api/v1/projects/{project_id}/agents")
    assert list_resp.status_code == 200
    configs = list_resp.json()
    assert len(configs) == 2
    assert [c["version"] for c in configs] == [2, 1]


async def test_agent_config_rejects_raw_secret_values(api_client: AsyncClient) -> None:
    """Verify security guardrail rejects raw credentials in secret_refs."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "security-test", "name": "Security Test"},
    )
    project_id = proj_resp.json()["id"]

    # Attempting to pass a raw API key instead of an uppercase env var reference
    bad_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "insecure-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-v1",
            "secret_refs": {"api_key": "sk-proj-raw-secret-token-12345"},
        },
    )
    assert bad_resp.status_code == 422
