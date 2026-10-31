"""Automated tests for Phase 8 EvaluationEngine, assertions, metrics, and comparisons."""

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


async def test_evaluator_distinguishes_superficial_completion_from_true_satisfaction(
    api_client: AsyncClient,
) -> None:
    """Verify evaluator catches a 'completed' fallback run that failed scenario criteria."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "eval-precision-lab",
              "name": "Evaluation Precision Lab"},
    )
    project_id = proj_resp.json()["id"]

    # ایجنت در صورت خطای ابزار متوقف نمی‌شود و پاسخ جایگزین تولید می‌کند
    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "fallback-enabled-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-deterministic-v1",
            "config_payload": {
                "fallback_on_tool_error": True,
                "tokens_per_step": 25,
                "model_latency_ms": 10.0,
            },
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "verified-incident-lookup",
            "version": 1,
            "spec": {
                "task_prompt": "Retrieve verified incident details.",
                "planned_tool_calls": [
                    {
                        "call_id": "call-1",
                        "tool_name": "search_incidents",
                        "arguments": {"incident_id": "INC-500"},
                    }
                ],
                "tool_fixtures": [
                    {
                        "tool_name": "search_incidents",
                        "default_output": {"incident_id": "INC-500", "verified": True},
                        "latency_ms": 15.0,
                    }
                ],
                "fault_rules": [
                    {
                        "target_tool": "search_incidents",
                        "fault_type": "HTTP_429_RATE_LIMIT",
                        "trigger_on_call": 1,
                        "error_message": "Rate limit exceeded",
                        "injected_latency_ms": 120.0,
                    }
                ],
                "evaluation_criteria": {
                    "require_completed_status": True,
                    "required_substrings": ["[ok:search_incidents]"],
                    "forbidden_substrings": ["[fallback:"],
                    "expected_tools": ["search_incidents"],
                    "max_total_latency_ms": 100.0,
                },
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    # گام اول: اجرای حالت پایه (بدون تزریق خطا)
    base_run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "baseline",
        },
    )
    base_run_id = base_run_resp.json()["id"]

    base_eval_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{base_run_id}/evaluate"
    )
    assert base_eval_resp.status_code == 200
    base_eval = base_eval_resp.json()
    assert base_eval["task_succeeded"] is True
    assert base_eval["reliability_score"] == 1.0
    assert base_eval["metrics"]["failed_tool_call_count"] == 0

    # گام دوم: اجرای حالت تزریق خطا (ایجنت وضعیت completed می‌گیرد اما معیارها نقض می‌شوند)
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
    assert fault_run["status"] == "completed"

    fault_eval_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{fault_run_id}/evaluate"
    )
    assert fault_eval_resp.status_code == 200
    fault_eval = fault_eval_resp.json()
    assert fault_eval["task_succeeded"] is False
    assert fault_eval["reliability_score"] == 0.4
    assert fault_eval["metrics"]["failed_tool_call_count"] == 1
    assert fault_eval["metrics"]["injected_fault_count"] == 1

    # بررسی دریافت کارنامه ذخیره‌شده با متد GET
    get_eval_resp = await api_client.get(
        f"/api/v1/projects/{project_id}/runs/{fault_run_id}/evaluation"
    )
    assert get_eval_resp.status_code == 200
    assert get_eval_resp.json()["id"] == fault_eval["id"]

    # گام سوم: مقایسه علمی اجرای پایه و اجرای خطادار
    cmp_resp = await api_client.get(
        f"/api/v1/projects/{project_id}/evaluations/compare",
        params={
            "baseline_run_id": base_run_id,
            "candidate_run_id": fault_run_id,
        },
    )
    assert cmp_resp.status_code == 200
    cmp_data = cmp_resp.json()
    assert cmp_data["outcome_classification"] == "degraded"
    assert cmp_data["baseline_succeeded"] is True
    assert cmp_data["candidate_succeeded"] is False
    assert cmp_data["reliability_score_delta"] == -0.6
    assert cmp_data["latency_delta_ms"] == 105.0
    assert "[ok:search_incidents]" in cmp_data["failed_assertion_targets"]
    assert "[fallback:" in cmp_data["failed_assertion_targets"]
    assert "total_latency_ms" in cmp_data["failed_assertion_targets"]


async def test_evaluation_metrics_track_retries_forbidden_tools_and_token_budgets(
    api_client: AsyncClient,
) -> None:
    """Verify retry counting, forbidden tool failure, and token budget enforcement."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "retry-metrics-lab", "name": "Retry Metrics Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "heavy-retry-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-v1",
            "config_payload": {"tokens_per_step": 50, "cost_per_1k_tokens_usd": 0.01},
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "retry-and-forbidden-tool-check",
            "version": 1,
            "spec": {
                "task_prompt": "Query API and avoid destructive tools.",
                "planned_tool_calls": [
                    {"call_id": "c1", "tool_name": "fetch_data", "arguments": {}},
                    {"call_id": "c2", "tool_name": "fetch_data", "arguments": {}},
                    {"call_id": "c3", "tool_name": "drop_partition", "arguments": {}},
                ],
                "evaluation_criteria": {
                    "require_completed_status": True,
                    "expected_tools": ["fetch_data"],
                    "forbidden_tools": ["drop_partition"],
                    "max_total_tokens": 100,
                },
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"agent_config_id": agent_id, "scenario_id": scenario_id},
    )
    run_id = run_resp.json()["id"]

    eval_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{run_id}/evaluate"
    )
    assert eval_resp.status_code == 200
    report = eval_resp.json()

    assert report["task_succeeded"] is False
    metrics = report["metrics"]
    assert metrics["tool_call_count"] == 3
    assert metrics["tool_retry_count"] == 1
    assert metrics["tool_correctness_rate"] == 0.5
    assert metrics["total_tokens"] == 200
    assert metrics["estimated_cost_usd"] == 0.002


async def test_get_evaluation_before_evaluating_returns_404(
    api_client: AsyncClient,
) -> None:
    """Verify GET /runs/{run_id}/evaluation returns 404 when no report exists yet."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "unscored-run-lab", "name": "Unscored Run Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "basic-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-v1",
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "basic-scenario",
            "version": 1,
            "spec": {"task_prompt": "Simple check."},
        },
    )
    scenario_id = scenario_resp.json()["id"]

    run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"agent_config_id": agent_id, "scenario_id": scenario_id},
    )
    run_id = run_resp.json()["id"]

    get_resp = await api_client.get(
        f"/api/v1/projects/{project_id}/runs/{run_id}/evaluation"
    )
    assert get_resp.status_code == 404
