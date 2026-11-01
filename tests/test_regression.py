"""Automated tests for Phase 12 RegressionSuiteEngine and Release Gate workflow."""

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


async def test_full_regression_lifecycle_and_release_gate_enforcement(
    api_client: AsyncClient,
) -> None:
    """Verify candidate creation, human approval, release rejection, and release approval."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "release-gate-lab", "name": "Release Gate Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "payment-verification-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-deterministic-v1",
            "config_payload": {"fallback_on_tool_error": False, "tokens_per_step": 20},
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "bank-api-transient-429",
            "version": 1,
            "spec": {
                "task_prompt": "Verify transaction TX-100 with bank API.",
                "planned_tool_calls": [
                    {
                        "call_id": "call-tx-1",
                        "tool_name": "bank_status_api",
                        "arguments": {"tx_id": "TX-100"},
                    }
                ],
                "tool_fixtures": [
                    {
                        "tool_name": "bank_status_api",
                        "default_output": {"tx_id": "TX-100", "settled": True},
                        "latency_ms": 15.0,
                    }
                ],
                "fault_rules": [
                    {
                        "target_tool": "bank_status_api",
                        "fault_type": "HTTP_429_RATE_LIMIT",
                        "trigger_on_call": 1,
                        "error_message": "429 Too Many Requests from bank_status_api",
                        "injected_latency_ms": 50.0,
                    }
                ],
                "evaluation_criteria": {
                    "require_completed_status": True,
                    "required_substrings": ["[ok:bank_status_api]"],
                    "expected_tools": ["bank_status_api"],
                    "max_total_latency_ms": 200.0,
                },
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    # گام اول: اجرای خطادار که شکست می‌خورد
    run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "fault_injected",
        },
    )
    run_id = run_resp.json()["id"]

    # گام دوم: تشخیص و تایید انسانی علت ریشه‌ای
    await api_client.post(f"/api/v1/projects/{project_id}/runs/{run_id}/diagnose")
    await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{run_id}/diagnosis/confirm",
        json={
            "confirmed_by": "erfan.saraee",
            "confirmed_root_cause": "Bank API transient 429 caused unrecovered abort.",
            "selected_classification_code": "DEPENDENCY_RATE_LIMITED",
        },
    )

    # گام سوم: ساخت کاندیدای تست رگرسیون از روی اجرای تاییدشده
    cand_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/regression-cases",
        json={
            "source_run_id": run_id,
            "name": "reg-bank-api-429-resilience",
            "description": "Ensure agent survives transient HTTP 429 on bank_status_api.",
        },
    )
    assert cand_resp.status_code == 201
    cand_data = cand_resp.json()
    case_id = cand_data["id"]
    assert cand_data["approval_status"] == "candidate"
    assert cand_data["classification_code"] == "DEPENDENCY_RATE_LIMITED"

    # گام چهارم: تایید تست رگرسیون توسط مهندس انسان
    review_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/regression-cases/{case_id}/review",
        json={
            "decision": "approved",
            "reviewed_by": "erfan.saraee",
            "review_notes": "Approved for mandatory release gate suite.",
        },
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["approval_status"] == "approved"

    # گام پنجم: اجرای گیت انتشار بدون سیاست بازیابی (باید انتشار را مسدود کند!)
    reject_gate_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/regression-suite/evaluate-release",
        json={
            "agent_config_id": agent_id,
            "gate_criteria": {
                "min_pass_rate": 1.0,
                "min_average_reliability_score": 0.9,
            },
        },
    )
    assert reject_gate_resp.status_code == 200
    reject_gate = reject_gate_resp.json()
    assert reject_gate["release_decision"] == "rejected"
    assert reject_gate["passed_cases"] == 0
    assert reject_gate["failed_cases"] == 1
    assert len(reject_gate["rejection_reasons"]) >= 1

    # گام ششم: اجرای گیت انتشار به همراه سیاست بازیابی Retry (باید انتشار را تایید کند!)
    approve_gate_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/regression-suite/evaluate-release",
        json={
            "agent_config_id": agent_id,
            "recovery_policy": {
                "strategy": "retry",
                "max_retries": 1,
                "backoff_ms": 20.0,
                "retryable_fault_types": ["HTTP_429_RATE_LIMIT"],
            },
            "gate_criteria": {
                "min_pass_rate": 1.0,
                "min_average_reliability_score": 0.9,
                "max_suite_latency_ms": 200.0,
            },
        },
    )
    assert approve_gate_resp.status_code == 200
    approve_gate = approve_gate_resp.json()
    assert approve_gate["release_decision"] == "approved"
    assert approve_gate["passed_cases"] == 1
    assert approve_gate["failed_cases"] == 0
    assert approve_gate["pass_rate"] == 1.0
    assert approve_gate["average_reliability_score"] == 1.0
    assert approve_gate["rejection_reasons"] == []


async def test_creating_regression_candidate_without_confirmed_diagnosis_returns_422(
    api_client: AsyncClient,
) -> None:
    """Verify regression candidate generation is rejected if diagnosis is unconfirmed."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "unconfirmed-reg-lab", "name": "Unconfirmed Reg Lab"},
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
            "spec": {"task_prompt": "Test task."},
        },
    )
    scenario_id = scenario_resp.json()["id"]

    run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"agent_config_id": agent_id, "scenario_id": scenario_id},
    )
    run_id = run_resp.json()["id"]

    # تشخیص انجام می‌شود اما توسط انسان تایید نمی‌شود
    await api_client.post(f"/api/v1/projects/{project_id}/runs/{run_id}/diagnose")

    bad_cand_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/regression-cases",
        json={
            "source_run_id": run_id,
            "name": "premature-regression-case",
        },
    )
    assert bad_cand_resp.status_code == 422


async def test_release_gate_without_approved_cases_returns_422(
    api_client: AsyncClient,
) -> None:
    """Verify release gate evaluation fails with 422 when no approved cases exist."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "empty-suite-lab", "name": "Empty Suite Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "candidate-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-v1",
        },
    )
    agent_id = agent_resp.json()["id"]

    gate_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/regression-suite/evaluate-release",
        json={"agent_config_id": agent_id},
    )
    assert gate_resp.status_code == 422
