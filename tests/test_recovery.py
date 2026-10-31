"""Automated tests for Phase 9 RecoveryPolicyEngine, bounded retries, and fallbacks."""

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


async def test_bounded_retry_recovers_transient_fault_and_tracks_overhead(
    api_client: AsyncClient,
) -> None:
    """Verify bounded retry recovers a transient HTTP 429 fault and records retry traces."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "recovery-retry-lab", "name": "Recovery Retry Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "strict-billing-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-deterministic-v1",
            "config_payload": {"tokens_per_step": 20, "model_latency_ms": 10.0},
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "transient-429-billing-lookup",
            "version": 1,
            "spec": {
                "task_prompt": "Fetch invoice status for INV-100.",
                "planned_tool_calls": [
                    {
                        "call_id": "call-inv-1",
                        "tool_name": "query_invoices",
                        "arguments": {"invoice_id": "INV-100"},
                    }
                ],
                "tool_fixtures": [
                    {
                        "tool_name": "query_invoices",
                        "default_output": {"invoice_id": "INV-100", "status": "paid"},
                        "latency_ms": 15.0,
                    }
                ],
                "fault_rules": [
                    {
                        "target_tool": "query_invoices",
                        "fault_type": "HTTP_429_RATE_LIMIT",
                        "trigger_on_call": 1,
                        "error_message": "Rate limit exceeded on first attempt",
                        "injected_latency_ms": 50.0,
                    }
                ],
                "evaluation_criteria": {
                    "require_completed_status": True,
                    "required_substrings": ["[ok:query_invoices]"],
                    "expected_tools": ["query_invoices"],
                    "max_total_latency_ms": 200.0,
                },
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    # گام اول: اجرای حالت تزریق خطا بدون سیاست بازیابی (منجر به شکست می‌شود)
    fault_run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "fault_injected",
        },
    )
    fault_run = fault_run_resp.json()
    fault_run_id = fault_run["id"]
    assert fault_run["status"] == "failed"

    # گام دوم: اجرای همان سناریو با سیاست بازیابی Retry
    rec_run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "recovery",
            "recovery_policy": {
                "strategy": "retry",
                "max_retries": 1,
                "backoff_ms": 30.0,
                "retry_token_overhead": 15,
                "retryable_fault_types": ["HTTP_429_RATE_LIMIT"],
            },
        },
    )
    assert rec_run_resp.status_code == 201
    rec_run = rec_run_resp.json()
    rec_run_id = rec_run["id"]

    assert rec_run["status"] == "completed"
    assert rec_run["run_mode"] == "recovery"
    summary = rec_run["run_metadata"]["recovery_summary"]
    assert summary["retries_performed"] == 1
    assert summary["recoveries_succeeded"] == 1
    assert summary["recoveries_exhausted"] == 0

    # بررسی ثبت هر دو تلاش (اولیه ناموفق + تلاش مجدد موفق) در تریس‌ها
    traces = rec_run["trace_events"]
    assert len(traces) == 4
    assert traces[1]["step_type"] == "tool_call"
    assert traces[1]["status"] == "error"
    assert traces[1]["input_payload"]["attempt_kind"] == "initial"
    assert traces[2]["step_type"] == "tool_call"
    assert traces[2]["status"] == "ok"
    assert traces[2]["input_payload"]["attempt_kind"] == "retry"
    assert traces[2]["latency_ms"] == 45.0

    # گام سوم: مقایسه علمی اجرای شکست‌خورده با اجرای بازیابی‌شده
    cmp_resp = await api_client.get(
        f"/api/v1/projects/{project_id}/evaluations/compare",
        params={
            "baseline_run_id": fault_run_id,
            "candidate_run_id": rec_run_id,
        },
    )
    assert cmp_resp.status_code == 200
    cmp_data = cmp_resp.json()
    assert cmp_data["outcome_classification"] == "recovered_or_improved"
    assert cmp_data["baseline_succeeded"] is False
    assert cmp_data["candidate_succeeded"] is True
    assert cmp_data["retry_delta"] == 1
    assert cmp_data["token_delta"] == 35


async def test_retry_exhaustion_and_latency_budget_violation_prove_retries_can_fail(
    api_client: AsyncClient,
) -> None:
    """Verify retries fail when retry budget is exhausted or backoff breaches latency SLA."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "retry-exhaustion-lab", "name": "Retry Exhaustion Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "timeout-prone-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-v1",
        },
    )
    agent_id = agent_resp.json()["id"]

    # سناریویی که هم در فراخوانی اول و هم در فراخوانی دوم خطای TIMEOUT می‌دهد
    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "persistent-timeout-outage",
            "version": 1,
            "spec": {
                "task_prompt": "Query overloaded analytics cluster.",
                "planned_tool_calls": [
                    {"call_id": "c1", "tool_name": "analytics_db", "arguments": {}}
                ],
                "fault_rules": [
                    {
                        "target_tool": "analytics_db",
                        "fault_type": "TIMEOUT",
                        "trigger_on_call": 1,
                        "error_message": "Timeout on attempt 1",
                        "injected_latency_ms": 100.0,
                    },
                    {
                        "target_tool": "analytics_db",
                        "fault_type": "TIMEOUT",
                        "trigger_on_call": 2,
                        "error_message": "Timeout on attempt 2",
                        "injected_latency_ms": 100.0,
                    },
                ],
                "evaluation_criteria": {
                    "require_completed_status": True,
                    "expected_tools": ["analytics_db"],
                },
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    rec_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "recovery",
            "recovery_policy": {
                "strategy": "retry",
                "max_retries": 1,
                "backoff_ms": 50.0,
                "retry_token_overhead": 20,
            },
        },
    )
    assert rec_resp.status_code == 201
    rec_data = rec_resp.json()
    assert rec_data["status"] == "failed"

    summary = rec_data["run_metadata"]["recovery_summary"]
    assert summary["retries_performed"] == 1
    assert summary["recoveries_succeeded"] == 0
    assert summary["recoveries_exhausted"] == 1

    eval_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{rec_data['id']}/evaluate"
    )
    eval_data = eval_resp.json()
    assert eval_data["task_succeeded"] is False
    assert eval_data["metrics"]["failed_tool_call_count"] == 2
    assert eval_data["metrics"]["tool_retry_count"] == 1


async def test_retry_then_fallback_tool_routing_recovers_persistent_primary_outage(
    api_client: AsyncClient,
) -> None:
    """Verify retry_then_fallback switches to backup tool after primary retries fail."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "fallback-routing-lab", "name": "Fallback Routing Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "search-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-v1",
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "primary-search-down-with-archive-backup",
            "version": 1,
            "spec": {
                "task_prompt": "Find runbook for service outage.",
                "planned_tool_calls": [
                    {"call_id": "c1", "tool_name": "primary_search", "arguments": {}}
                ],
                "tool_fixtures": [
                    {
                        "tool_name": "archive_search",
                        "default_output": {"runbook": "Restart replica pool"},
                        "latency_ms": 20.0,
                    }
                ],
                "fault_rules": [
                    {
                        "target_tool": "primary_search",
                        "fault_type": "TOOL_UNAVAILABLE",
                        "trigger_on_call": 1,
                        "error_message": "Primary search cluster down (call 1)",
                        "injected_latency_ms": 30.0,
                    },
                    {
                        "target_tool": "primary_search",
                        "fault_type": "TOOL_UNAVAILABLE",
                        "trigger_on_call": 2,
                        "error_message": "Primary search cluster down (call 2)",
                        "injected_latency_ms": 30.0,
                    },
                ],
                "evaluation_criteria": {
                    "require_completed_status": True,
                    "expected_tools": ["primary_search", "archive_search"],
                },
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    rec_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "recovery",
            "recovery_policy": {
                "strategy": "retry_then_fallback",
                "max_retries": 1,
                "backoff_ms": 15.0,
                "fallback_tool_map": {"primary_search": "archive_search"},
            },
        },
    )
    assert rec_resp.status_code == 201
    rec_data = rec_resp.json()
    assert rec_data["status"] == "completed"

    summary = rec_data["run_metadata"]["recovery_summary"]
    assert summary["retries_performed"] == 1
    assert summary["fallbacks_performed"] == 1
    assert summary["recoveries_succeeded"] == 1

    eval_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{rec_data['id']}/evaluate"
    )
    assert eval_resp.json()["task_succeeded"] is True


async def test_recovery_run_mode_requires_recovery_policy_payload(
    api_client: AsyncClient,
) -> None:
    """Verify RunCreateRequest rejects run_mode='recovery' when recovery_policy is omitted."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "validation-lab", "name": "Validation Lab"},
    )
    project_id = proj_resp.json()["id"]

    bad_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": "00000000-0000-0000-0000-000000000001",
            "scenario_id": "00000000-0000-0000-0000-000000000002",
            "run_mode": "recovery",
        },
    )
    assert bad_resp.status_code == 422
