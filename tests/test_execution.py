"""Automated tests for Phase 6 BaselineExecutionEngine, fixture handlers, and run APIs."""

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


async def test_baseline_execution_run_captures_fixture_outputs_and_traces(
    api_client: AsyncClient,
) -> None:
    """Verify end-to-end baseline run execution, fixture usage, and trace persistence."""
    # گام اول: ساخت پروژه
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "baseline-exec-lab", "name": "Baseline Execution Lab"},
    )
    project_id = proj_resp.json()["id"]

    # گام دوم: ثبت کانفیگ ایجنت
    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "incident-triage-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-deterministic-v1",
            "config_payload": {"tokens_per_step": 20, "model_latency_ms": 10.0},
        },
    )
    agent_id = agent_resp.json()["id"]

    # گام سوم: ثبت سناریو با فیکسچر ابزار
    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "database-latency-triage",
            "version": 1,
            "spec": {
                "task_prompt": "Diagnose primary database latency spike.",
                "preconditions": {"cluster": "pg-prod-01"},
                "planned_tool_calls": [
                    {
                        "call_id": "call-metrics-1",
                        "tool_name": "query_prometheus",
                        "arguments": {"metric": "pg_locks_count"},
                    }
                ],
                "tool_fixtures": [
                    {
                        "tool_name": "query_prometheus",
                        "default_output": {"active_locks": 42, "status": "critical"},
                        "latency_ms": 18.5,
                    }
                ],
                "safety_constraints": {
                    "max_steps": 6,
                    "timeout_seconds": 15.0,
                    "allow_live_external_actions": False,
                },
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    # گام چهارم: اجرای سناریو روی ایجنت
    run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "baseline",
        },
    )
    assert run_resp.status_code == 201
    run_data = run_resp.json()
    run_id = run_data["id"]

    assert run_data["status"] == "completed"
    assert run_data["run_mode"] == "baseline"
    assert run_data["adapter_type"] == "mock"
    assert run_data["total_tokens"] == 40
    assert run_data["total_latency_ms"] == 38.5
    assert run_data["run_metadata"]["agent_version"] == 1
    assert run_data["run_metadata"]["scenario_version"] == 1

    # بررسی گام‌های تریس ثبت‌شده
    traces = run_data["trace_events"]
    assert len(traces) == 3
    assert [t["step_type"] for t in traces] == [
        "model_invocation",
        "tool_call",
        "final_response",
    ]
    assert traces[1]["name"] == "query_prometheus"
    assert traces[1]["output_payload"]["output"] == {
        "active_locks": 42,
        "status": "critical",
    }
    assert traces[1]["latency_ms"] == 18.5

    # گام پنجم: بررسی اندپوینت‌های دریافت لیست اجراها و تریس‌ها
    list_runs_resp = await api_client.get(f"/api/v1/projects/{project_id}/runs")
    assert list_runs_resp.status_code == 200
    assert len(list_runs_resp.json()) == 1

    get_run_resp = await api_client.get(f"/api/v1/projects/{project_id}/runs/{run_id}")
    assert get_run_resp.status_code == 200
    assert get_run_resp.json()["id"] == run_id

    traces_resp = await api_client.get(
        f"/api/v1/projects/{project_id}/runs/{run_id}/traces"
    )
    assert traces_resp.status_code == 200
    assert len(traces_resp.json()) == 3


async def test_baseline_run_persists_max_steps_exceeded_status(
    api_client: AsyncClient,
) -> None:
    """Verify scenario safety_constraints.max_steps is enforced and persisted on the run."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "step-budget-lab", "name": "Step Budget Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "looping-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-v1",
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "tight-step-budget",
            "version": 1,
            "spec": {
                "task_prompt": "Run two tools under a 2-step limit.",
                "planned_tool_calls": [
                    {"call_id": "c1", "tool_name": "tool_one", "arguments": {}},
                    {"call_id": "c2", "tool_name": "tool_two", "arguments": {}},
                ],
                "safety_constraints": {
                    "max_steps": 2,
                    "timeout_seconds": 10.0,
                    "allow_live_external_actions": False,
                },
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"agent_config_id": agent_id, "scenario_id": scenario_id},
    )
    assert run_resp.status_code == 201
    run_data = run_resp.json()
    assert run_data["status"] == "max_steps_exceeded"
    assert len(run_data["trace_events"]) == 2


async def test_run_with_unregistered_adapter_returns_422(
    api_client: AsyncClient,
) -> None:
    """Verify triggering a run with an unimplemented adapter type returns 422."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "unregistered-adapter-lab",
              "name": "Unregistered Adapter Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "proxy-agent",
            "version": 1,
            "adapter_type": "http_proxy",
            "model_name": "remote-v1",
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "basic-check",
            "version": 1,
            "spec": {"task_prompt": "Ping remote service."},
        },
    )
    scenario_id = scenario_resp.json()["id"]

    run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"agent_config_id": agent_id, "scenario_id": scenario_id},
    )
    assert run_resp.status_code == 422
    assert "http_proxy" in run_resp.json()["detail"]


async def test_get_nonexistent_run_returns_404(api_client: AsyncClient) -> None:
    """Verify requesting an unknown ExecutionRun UUID returns 404 Not Found."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "missing-run-lab", "name": "Missing Run Lab"},
    )
    project_id = proj_resp.json()["id"]

    missing_run_id = uuid4()
    resp = await api_client.get(f"/api/v1/projects/{project_id}/runs/{missing_run_id}")
    assert resp.status_code == 404
