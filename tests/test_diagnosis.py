"""Automated tests for Phase 11 Evidence-Based Failure Diagnosis and human confirmation."""

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


async def test_diagnosis_separates_facts_rules_unconfirmed_hypotheses_and_human_cause(
    api_client: AsyncClient,
) -> None:
    """Verify 4-tier evidence separation and human confirmation transition."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "diagnosis-evidence-lab",
              "name": "Diagnosis Evidence Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "strict-Order-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-deterministic-v1",
            "config_payload": {"fallback_on_tool_error": False},
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "inventory-rate-limit-failure",
            "version": 1,
            "spec": {
                "task_prompt": "Check warehouse stock for SKU-88.",
                "planned_tool_calls": [
                    {
                        "call_id": "call-stock-1",
                        "tool_name": "inventory_service",
                        "arguments": {"sku": "SKU-88"},
                    }
                ],
                "fault_rules": [
                    {
                        "target_tool": "inventory_service",
                        "fault_type": "HTTP_429_RATE_LIMIT",
                        "trigger_on_call": 1,
                        "error_message": "429 Too Many Requests on inventory_service",
                        "injected_latency_ms": 60.0,
                    }
                ],
                "evaluation_criteria": {
                    "require_completed_status": True,
                    "expected_tools": ["inventory_service"],
                },
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "fault_injected",
        },
    )
    run_id = run_resp.json()["id"]

    # گام اول: تولید گزارش تشخیص مبتنی بر شواهد
    diag_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{run_id}/diagnose"
    )
    assert diag_resp.status_code == 200
    diag = diag_resp.json()

    # بررسی اینکه تا قبل از تایید انسان، وضعیت در انتظار بازبینی است
    assert diag["confirmation_status"] == "pending_human_review"
    assert diag["human_confirmed_cause"] is None

    # بررسی لایه اول: فکت‌های مشاهده‌شده
    facts = diag["observed_facts"]
    assert len(facts) >= 3
    trace_facts = [f for f in facts if f["source_type"] == "trace_event"]
    assert len(trace_facts) == 1
    assert trace_facts[0]["step_index"] == 1
    assert trace_facts[0]["component_name"] == "inventory_service"

    # بررسی لایه دوم: دسته‌بندی مبتنی بر قانون
    rules = diag["rule_classifications"]
    codes = [r["classification_code"] for r in rules]
    assert "DEPENDENCY_RATE_LIMITED" in codes
    rate_rule = next(
        r for r in rules if r["classification_code"] == "DEPENDENCY_RATE_LIMITED"
    )
    assert len(rate_rule["supporting_fact_ids"]) >= 1

    # بررسی لایه سوم: فرضیه‌های مدل (حتماً غیرقطعی و تاییدنشده)
    hypotheses = diag["model_hypotheses"]
    assert len(hypotheses) >= 1
    assert all(
        h["verification_status"] == "unconfirmed_hypothesis" for h in hypotheses
    )

    # گام دوم: ثبت تاییدیه نهایی توسط مهندس انسان
    confirm_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{run_id}/diagnosis/confirm",
        json={
            "confirmed_by": "erfan.saraee",
            "confirmed_root_cause": (
                "Inventory service returned HTTP 429 and agent had no retry policy."
            ),
            "selected_classification_code": "DEPENDENCY_RATE_LIMITED",
            "endorsed_hypothesis_id": hypotheses[0]["hypothesis_id"],
            "resolution_notes": "Add bounded retry policy and lock as regression test.",
        },
    )
    assert confirm_resp.status_code == 200
    confirmed_diag = confirm_resp.json()
    assert confirmed_diag["confirmation_status"] == "confirmed"
    assert confirmed_diag["human_confirmed_cause"] is not None
    assert (
        confirmed_diag["human_confirmed_cause"]["confirmed_by"] == "erfan.saraee"
    )
    assert (
        confirmed_diag["human_confirmed_cause"]["selected_classification_code"]
        == "DEPENDENCY_RATE_LIMITED"
    )


async def test_diagnosis_detects_superficial_completion_failure(
    api_client: AsyncClient,
) -> None:
    """Verify DiagnosisEngine flags SUPERFICIAL_COMPLETION_FAILURE when fallback masks error."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "superficial-diag-lab", "name": "Superficial Diag Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "masking-fallback-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-v1",
            "config_payload": {"fallback_on_tool_error": True},
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "masked-timeout-scenario",
            "version": 1,
            "spec": {
                "task_prompt": "Fetch customer contract terms.",
                "planned_tool_calls": [
                    {"call_id": "c1", "tool_name": "contracts_db", "arguments": {}}
                ],
                "fault_rules": [
                    {
                        "target_tool": "contracts_db",
                        "fault_type": "TIMEOUT",
                        "trigger_on_call": 1,
                        "error_message": "Read timed out",
                        "injected_latency_ms": 100.0,
                    }
                ],
                "evaluation_criteria": {
                    "require_completed_status": True,
                    "required_substrings": ["[ok:contracts_db]"],
                    "forbidden_substrings": ["[fallback:"],
                },
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "fault_injected",
        },
    )
    run_id = run_resp.json()["id"]

    diag_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{run_id}/diagnose"
    )
    assert diag_resp.status_code == 200
    diag = diag_resp.json()

    codes = [r["classification_code"] for r in diag["rule_classifications"]]
    assert "DEPENDENCY_TIMEOUT" in codes
    assert "SUPERFICIAL_COMPLETION_FAILURE" in codes


async def test_get_diagnosis_before_diagnosing_returns_404(
    api_client: AsyncClient,
) -> None:
    """Verify GET /runs/{run_id}/diagnosis returns 404 when no report exists yet."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "undiagnosed-run-lab", "name": "Undiagnosed Run Lab"},
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
            "spec": {"task_prompt": "Simple task."},
        },
    )
    scenario_id = scenario_resp.json()["id"]

    run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"agent_config_id": agent_id, "scenario_id": scenario_id},
    )
    run_id = run_resp.json()["id"]

    get_resp = await api_client.get(
        f"/api/v1/projects/{project_id}/runs/{run_id}/diagnosis"
    )
    assert get_resp.status_code == 404
