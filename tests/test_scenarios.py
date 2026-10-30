"""Automated tests for Phase 5 ScenarioDefinition schemas, repository, and APIs."""

from collections.abc import AsyncIterator
from typing import Any
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


async def test_versioned_scenario_lifecycle(api_client: AsyncClient) -> None:
    """Verify creating baseline and fault-injected scenario versions, listing, and conflict."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "incident-response-lab",
              "name": "Incident Response Lab"},
    )
    project_id = proj_resp.json()["id"]

    # ساختار مشخصات سناریوی نسخه ۱ (حالت عادی بدون تزریق خطا)
    v1_spec: dict[str, Any] = {
        "task_prompt": "Investigate Q3 outage root cause.",
        "preconditions": {"region": "us-east-1"},
        "planned_tool_calls": [
            {
                "call_id": "call-1",
                "tool_name": "search_incidents",
                "arguments": {"quarter": "Q3"},
            }
        ],
        "tool_fixtures": [
            {
                "tool_name": "search_incidents",
                "default_output": {"incident_id": "INC-900", "severity": "SEV-1"},
                "latency_ms": 15.0,
            }
        ],
        "fault_rules": [],
        "evaluation_criteria": {
            "require_completed_status": True,
            "required_substrings": ["search_incidents"],
            "expected_tools": ["search_incidents"],
            "max_total_latency_ms": 500.0,
            "max_total_tokens": 200,
        },
        "safety_constraints": {
            "max_steps": 6,
            "timeout_seconds": 15.0,
            "allow_live_external_actions": False,
        },
    }

    v1_payload: dict[str, Any] = {
        "name": "q3-outage-investigation",
        "version": 1,
        "description": "Baseline scenario without injected faults.",
        "spec": v1_spec,
    }

    v1_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json=v1_payload,
    )
    assert v1_resp.status_code == 201
    v1_data = v1_resp.json()
    scenario_v1_id = v1_data["id"]
    assert v1_data["version"] == 1
    assert v1_data["spec"]["task_prompt"] == "Investigate Q3 outage root cause."
    assert len(v1_data["spec"]["tool_fixtures"]) == 1

    # ارسال مجدد نسخه ۱ باید خطای ۴۰۹ تعارض داده بدهد
    dup_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json=v1_payload,
    )
    assert dup_resp.status_code == 409

    # ساختار سناریوی نسخه ۲ (افزودن قانون خطای HTTP 429 به ابزار)
    v2_spec: dict[str, Any] = {
        **v1_spec,
        "fault_rules": [
            {
                "target_tool": "search_incidents",
                "fault_type": "HTTP_429_RATE_LIMIT",
                "trigger_on_call": 1,
                "error_message": "Too Many Requests from search service",
                "injected_latency_ms": 80.0,
            }
        ],
    }

    v2_payload: dict[str, Any] = {
        "name": "q3-outage-investigation",
        "version": 2,
        "description": "Injects HTTP 429 rate limit on first search_incidents call.",
        "spec": v2_spec,
    }

    v2_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json=v2_payload,
    )
    assert v2_resp.status_code == 201
    assert v2_resp.json()["version"] == 2
    assert v2_resp.json()[
        "spec"]["fault_rules"][0]["fault_type"] == "HTTP_429_RATE_LIMIT"

    # دریافت نسخه ۱ با شناسه
    get_resp = await api_client.get(
        f"/api/v1/projects/{project_id}/scenarios/{scenario_v1_id}"
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == scenario_v1_id

    # دریافت لیست سناریوها به ترتیب نزولی نسخه
    list_resp = await api_client.get(f"/api/v1/projects/{project_id}/scenarios")
    assert list_resp.status_code == 200
    scenarios = list_resp.json()
    assert len(scenarios) == 2
    assert [s["version"] for s in scenarios] == [2, 1]


async def test_scenario_rejects_unsafe_live_external_actions(
    api_client: AsyncClient,
) -> None:
    """Verify safety constraint validator rejects allow_live_external_actions=True."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "safety-check-lab", "name": "Safety Check Lab"},
    )
    project_id = proj_resp.json()["id"]

    unsafe_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "unsafe-scenario",
            "version": 1,
            "spec": {
                "task_prompt": "Execute production payment transfer.",
                "safety_constraints": {
                    "max_steps": 5,
                    "timeout_seconds": 10.0,
                    "allow_live_external_actions": True,
                },
            },
        },
    )
    assert unsafe_resp.status_code == 422


async def test_scenario_rejects_overlapping_expected_and_forbidden_tools(
    api_client: AsyncClient,
) -> None:
    """Verify evaluation criteria validator rejects contradictory tool assertions."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "criteria-check-lab", "name": "Criteria Check Lab"},
    )
    project_id = proj_resp.json()["id"]

    contradictory_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "contradictory-criteria",
            "version": 1,
            "spec": {
                "task_prompt": "Query knowledge base.",
                "evaluation_criteria": {
                    "expected_tools": ["search_kb"],
                    "forbidden_tools": ["search_kb", "delete_record"],
                },
            },
        },
    )
    assert contradictory_resp.status_code == 422


async def test_get_nonexistent_scenario_returns_404(api_client: AsyncClient) -> None:
    """Verify requesting an unknown scenario UUID returns 404 Not Found."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "missing-scenario-lab", "name": "Missing Scenario Lab"},
    )
    project_id = proj_resp.json()["id"]

    missing_id = uuid4()
    resp = await api_client.get(f"/api/v1/projects/{project_id}/scenarios/{missing_id}")
    assert resp.status_code == 404
