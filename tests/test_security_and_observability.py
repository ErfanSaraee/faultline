"""Automated tests for Phase 14 Secret/PII/CoT redaction and OpenTelemetry observability."""

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


async def test_persisted_traces_redact_secrets_pii_and_hidden_chain_of_thought(
    api_client: AsyncClient,
) -> None:
    """Verify secrets, emails, SSNs, and chain_of_thought are scrubbed before DB storage."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "redaction-privacy-lab",
              "name": "Redaction Privacy Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "privacy-test-agent",
            "version": 1,
            "adapter_type": "langgraph",
            "model_name": "gpt-4o-mini-graph",
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "sensitive-payload-scenario",
            "version": 1,
            "spec": {
                "task_prompt": (
                    "Check account for user ali.rezaei@example.com "
                    "with token Bearer eyJSuperSecret999."
                ),
                "planned_tool_calls": [
                    {
                        "call_id": "call-auth-1",
                        "tool_name": "crm_lookup",
                        "arguments": {
                            "email": "ali.rezaei@example.com",
                            "api_key": "sk-proj-1234567890abcdef1234",
                            "chain_of_thought": "Hidden reasoning step that must never be stored",
                        },
                    }
                ],
                "tool_fixtures": [
                    {
                        "tool_name": "crm_lookup",
                        "default_output": {
                            "customer_email": "ali.rezaei@example.com",
                            "ssn": "123-45-6789",
                            "auth_token": "secret-session-token-xyz",
                            "raw_reasoning": "Internal model monologue",
                            "status_note": (
                                "Contacted ali.rezaei@example.com using "
                                "sk-proj-9999888877776666"
                            ),
                        },
                        "latency_ms": 12.0,
                    }
                ],
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

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

    # بررسی سانسور ایمیل و توکن در پاسخ نهایی اجرای ذخیره‌شده
    final_answer = run_data["final_answer"]
    assert "ali.rezaei@example.com" not in final_answer
    assert "eyJSuperSecret999" not in final_answer
    assert "[REDACTED_EMAIL]" in final_answer
    assert "[REDACTED_SECRET]" in final_answer

    # بررسی سانسور کلیدهای حساس و افکار پنهان در گام ابزار در دیتابیس
    tool_trace = run_data["trace_events"][1]
    input_args = tool_trace["input_payload"]["arguments"]
    assert input_args["email"] == "[REDACTED_EMAIL]"
    assert input_args["api_key"] == "[REDACTED_SECRET]"
    assert input_args["chain_of_thought"] == "[REDACTED_COT]"

    tool_out = tool_trace["output_payload"]["output"]
    assert tool_out["customer_email"] == "[REDACTED_EMAIL]"
    assert tool_out["ssn"] == "[REDACTED_SECRET]"
    assert tool_out["auth_token"] == "[REDACTED_SECRET]"
    assert tool_out["raw_reasoning"] == "[REDACTED_COT]"
    assert "sk-proj-9999888877776666" not in tool_out["status_note"]
    assert "[REDACTED_SECRET]" in tool_out["status_note"]


async def test_opentelemetry_spans_and_bounded_cardinality_metrics_endpoints(
    api_client: AsyncClient,
) -> None:
    """Verify OTel trace correlation IDs, emitted spans, and bounded metrics snapshot."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "otel-telemetry-lab", "name": "OTel Telemetry Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "otel-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-otel-v1",
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "otel-fault-scenario",
            "version": 1,
            "spec": {
                "task_prompt": "Test OTel span emission.",
                "planned_tool_calls": [
                    {"call_id": "c1", "tool_name": "metrics_service", "arguments": {}}
                ],
                "fault_rules": [
                    {
                        "target_tool": "metrics_service",
                        "fault_type": "HTTP_429_RATE_LIMIT",
                        "trigger_on_call": 1,
                        "error_message": "Rate limit 429",
                    }
                ],
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
    assert run_resp.status_code == 201
    run_data = run_resp.json()
    run_id = run_data["id"]

    otel_trace_id = run_data["run_metadata"].get("otel_trace_id")
    assert isinstance(otel_trace_id, str)
    assert len(otel_trace_id) == 32

    await api_client.post(f"/api/v1/projects/{project_id}/runs/{run_id}/evaluate")

    # بررسی اندپوینت Spanهای OpenTelemetry
    spans_resp = await api_client.get("/api/v1/observability/spans")
    assert spans_resp.status_code == 200
    spans = spans_resp.json()
    matching_spans = [s for s in spans if s["trace_id"] == otel_trace_id]
    assert len(matching_spans) >= 2
    assert any(s["name"] == "faultline.execution.run" for s in matching_spans)

    # بررسی اندپوینت متریک‌های پلتفرم با برچسب‌های محدود
    metrics_resp = await api_client.get("/api/v1/observability/metrics")
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert metrics["runs_total"] >= 1
    assert metrics["injected_faults_total"] >= 1
    assert metrics["injected_faults_by_type"].get(
        "HTTP_429_RATE_LIMIT", 0) >= 1
    assert metrics["evaluations_total"] >= 1
