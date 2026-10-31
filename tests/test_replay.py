"""Automated tests for Phase 10 ReplayEngine (recorded vs live replay) and trace diffing."""

from collections.abc import AsyncIterator

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


async def test_recorded_replay_reproduces_exact_trace_path_with_zero_deviations(
    api_client: AsyncClient,
) -> None:
    """Verify recorded_replay reproduces a captured run deterministically with no deviations."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "replay-deterministic-lab",
              "name": "Replay Deterministic Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "strict-incident-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-deterministic-v1",
            "config_payload": {"fallback_on_tool_error": False, "tokens_per_step": 25},
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "recorded-fault-scenario",
            "version": 1,
            "spec": {
                "task_prompt": "Check payment gateway status.",
                "planned_tool_calls": [
                    {
                        "call_id": "call-gw-1",
                        "tool_name": "payment_gateway_status",
                        "arguments": {"region": "eu-central-1"},
                    }
                ],
                "fault_rules": [
                    {
                        "target_tool": "payment_gateway_status",
                        "fault_type": "HTTP_429_RATE_LIMIT",
                        "trigger_on_call": 1,
                        "error_message": "429 Rate limit from gateway",
                        "injected_latency_ms": 65.0,
                    }
                ],
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    # اجرای اولیه خطادار که قرار است بازپخش شود
    source_run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "fault_injected",
        },
    )
    source_run = source_run_resp.json()
    source_run_id = source_run["id"]
    assert source_run["status"] == "failed"

    # بازپخش قطعی از روی تریس‌های ضبط‌شده
    replay_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{source_run_id}/replay",
        json={"replay_mode": "recorded_replay"},
    )
    assert replay_resp.status_code == 201
    replay_payload = replay_resp.json()

    assert replay_payload["source_run_id"] == source_run_id
    assert replay_payload["replay_mode"] == "recorded_replay"
    assert (
        replay_payload["reproducibility_guarantee"] == "deterministic_recorded_trace"
    )

    replay_run = replay_payload["replay_run"]
    assert replay_run["run_mode"] == "recorded_replay"
    assert replay_run["status"] == "failed"
    assert replay_run["run_metadata"]["source_run_id"] == source_run_id

    diff = replay_payload["diff"]
    assert diff["trace_path_identical"] is True
    assert diff["status_match"] is True
    assert diff["step_count_match"] is True
    assert diff["token_delta"] == 0
    assert diff["latency_delta_ms"] == 0.0
    assert diff["deviations"] == []


async def test_recorded_replay_with_agent_override_reuses_recorded_tool_results_and_diffs(
    api_client: AsyncClient,
) -> None:
    """Verify recorded_replay with override_agent_config_id feeds recorded tools and diffs."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "replay-override-lab", "name": "Replay Override Lab"},
    )
    project_id = proj_resp.json()["id"]

    # نسخه ۱ ایجنت: در صورت خطای ابزار متوقف می‌شود
    v1_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "order-lookup-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-v1",
            "config_payload": {"fallback_on_tool_error": False, "tokens_per_step": 20},
        },
    )
    agent_v1_id = v1_resp.json()["id"]

    # نسخه ۲ ایجنت: در صورت خطای ابزار پاسخ جایگزین تولید می‌کند
    v2_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "order-lookup-agent",
            "version": 2,
            "adapter_type": "mock",
            "model_name": "mock-v2-fallback",
            "config_payload": {"fallback_on_tool_error": True, "tokens_per_step": 20},
        },
    )
    agent_v2_id = v2_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "order-db-timeout",
            "version": 1,
            "spec": {
                "task_prompt": "Check order ORD-404.",
                "planned_tool_calls": [
                    {"call_id": "c1", "tool_name": "orders_db",
                        "arguments": {"id": 404}}
                ],
                "fault_rules": [
                    {
                        "target_tool": "orders_db",
                        "fault_type": "TIMEOUT",
                        "trigger_on_call": 1,
                        "error_message": "Database read timed out",
                        "injected_latency_ms": 90.0,
                    }
                ],
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    source_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_v1_id,
            "scenario_id": scenario_id,
            "run_mode": "fault_injected",
        },
    )
    source_run_id = source_resp.json()["id"]

    # بازپخش نتایج ضبط‌شده ابزار روی نسخه ۲ ایجنت
    replay_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{source_run_id}/replay",
        json={
            "replay_mode": "recorded_replay",
            "override_agent_config_id": agent_v2_id,
        },
    )
    assert replay_resp.status_code == 201
    data = replay_resp.json()

    assert data["reproducibility_guarantee"] == "deterministic_recorded_tools"
    assert data["replay_run"]["status"] == "completed"
    assert data["replay_run"]["run_metadata"]["agent_version"] == 2

    diff = data["diff"]
    assert diff["trace_path_identical"] is False
    assert diff["status_match"] is False
    assert diff["step_count_match"] is False
    assert any(d["deviation_type"] == "step_added" for d in diff["deviations"])


async def test_live_replay_with_recovery_policy_and_standalone_diff_endpoint(
    api_client: AsyncClient,
) -> None:
    """Verify live_replay reinvokes dependencies and GET /diff compares any two runs."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "live-replay-lab", "name": "Live Replay Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "live-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-v1",
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "transient-search-glitch",
            "version": 1,
            "spec": {
                "task_prompt": "Search knowledge base.",
                "planned_tool_calls": [
                    {"call_id": "c1", "tool_name": "kb_search", "arguments": {}}
                ],
                "tool_fixtures": [
                    {
                        "tool_name": "kb_search",
                        "default_output": {"doc": "Found answer"},
                        "latency_ms": 10.0,
                    }
                ],
                "fault_rules": [
                    {
                        "target_tool": "kb_search",
                        "fault_type": "HTTP_429_RATE_LIMIT",
                        "trigger_on_call": 1,
                        "error_message": "Transient 429",
                        "injected_latency_ms": 40.0,
                    }
                ],
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    # اجرای اولیه بدون ریکاوری که شکست می‌خورد
    source_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "fault_injected",
        },
    )
    source_run_id = source_resp.json()["id"]

    # اجرای مجدد زنده به همراه سیاست بازیابی Retry
    live_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{source_run_id}/replay",
        json={
            "replay_mode": "live_replay",
            "override_recovery_policy": {
                "strategy": "retry",
                "max_retries": 1,
                "backoff_ms": 20.0,
            },
        },
    )
    assert live_resp.status_code == 201
    live_data = live_resp.json()
    assert (
        live_data["reproducibility_guarantee"] == "non_deterministic_live_execution"
    )
    target_run_id = live_data["replay_run"]["id"]
    assert live_data["replay_run"]["status"] == "completed"

    # فراخوانی مستقیم اندپوینت مقایسه گام‌به‌گام دو اجرا
    diff_resp = await api_client.get(
        f"/api/v1/projects/{project_id}/runs/{source_run_id}/diff/{target_run_id}"
    )
    assert diff_resp.status_code == 200
    diff_data = diff_resp.json()
    assert diff_data["source_run_id"] == source_run_id
    assert diff_data["target_run_id"] == target_run_id
    assert diff_data["status_match"] is False
    assert len(diff_data["deviations"]) >= 2
