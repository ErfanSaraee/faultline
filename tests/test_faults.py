"""Automated tests for Phase 7 FaultInjector and fault-injected execution runs."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from faultline.adapters.base import default_mock_tool_handler
from faultline.api.app import create_app
from faultline.core.config import Settings
from faultline.db.base import Base
from faultline.faults import FaultInjector
from faultline.schemas.adapter import ToolCallRequest
from faultline.schemas.scenario import FaultRuleSpec


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


async def test_baseline_vs_fault_injected_run_on_same_scenario(
    api_client: AsyncClient,
) -> None:
    """Verify baseline mode ignores fault rules while fault_injected mode triggers them."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "chaos-comparison-lab", "name": "Chaos Comparison Lab"},
    )
    project_id = proj_resp.json()["id"]

    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "strict-research-agent",
            "version": 1,
            "adapter_type": "mock",
            "model_name": "mock-deterministic-v1",
            "config_payload": {"fallback_on_tool_error": False, "model_latency_ms": 10.0},
        },
    )
    agent_id = agent_resp.json()["id"]

    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "search-rate-limit-experiment",
            "version": 1,
            "spec": {
                "task_prompt": "Find root cause for incident INC-77.",
                "planned_tool_calls": [
                    {
                        "call_id": "call-search-1",
                        "tool_name": "search_incidents",
                        "arguments": {"incident_id": "INC-77"},
                    }
                ],
                "tool_fixtures": [
                    {
                        "tool_name": "search_incidents",
                        "default_output": {"incident_id": "INC-77", "cause": "DNS outage"},
                        "latency_ms": 12.0,
                    }
                ],
                "fault_rules": [
                    {
                        "target_tool": "search_incidents",
                        "fault_type": "HTTP_429_RATE_LIMIT",
                        "trigger_on_call": 1,
                        "error_message": "429 Too Many Requests from search_incidents",
                        "injected_latency_ms": 75.0,
                    }
                ],
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    # اجرای اول در حالت پایه (بدون تزریق خطا)
    baseline_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "baseline",
        },
    )
    assert baseline_resp.status_code == 201
    baseline_data = baseline_resp.json()
    assert baseline_data["status"] == "completed"
    assert baseline_data["run_metadata"]["injected_fault_count"] == 0
    assert len(baseline_data["trace_events"]) == 3

    # اجرای دوم در حالت تزریق خطا روی همان سناریو
    fault_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "fault_injected",
        },
    )
    assert fault_resp.status_code == 201
    fault_data = fault_resp.json()
    assert fault_data["status"] == "failed"
    assert fault_data["run_mode"] == "fault_injected"
    assert "HTTP_429_RATE_LIMIT" in fault_data["error_message"]
    assert fault_data["run_metadata"]["injected_fault_count"] == 1

    injected_event = fault_data["run_metadata"]["injected_faults"][0]
    assert injected_event["tool_name"] == "search_incidents"
    assert injected_event["fault_type"] == "HTTP_429_RATE_LIMIT"
    assert injected_event["invocation_number"] == 1

    # بررسی گام ابزار در تریس‌ها
    tool_trace = fault_data["trace_events"][1]
    assert tool_trace["step_type"] == "tool_call"
    assert tool_trace["status"] == "error"
    assert tool_trace["latency_ms"] == 75.0
    assert tool_trace["output_payload"]["error_type"] == "HTTP_429_RATE_LIMIT"


async def test_transient_fault_triggers_only_on_configured_invocation(
    api_client: AsyncClient,
) -> None:
    """Verify a fault rule with trigger_on_call=1 fails call #1 but allows call #2 to succeed."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "transient-fault-lab", "name": "Transient Fault Lab"},
    )
    project_id = proj_resp.json()["id"]

    # ایجنت دارای قابلیت ادامه در صورت خطا تا فراخوانی دوم ابزار هم انجام شود
    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "resilient-doc-agent",
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
            "name": "transient-timeout-scenario",
            "version": 1,
            "spec": {
                "task_prompt": "Fetch document twice to test transient timeout.",
                "planned_tool_calls": [
                    {"call_id": "call-doc-1", "tool_name": "fetch_doc",
                        "arguments": {"id": 1}},
                    {"call_id": "call-doc-2", "tool_name": "fetch_doc",
                        "arguments": {"id": 1}},
                ],
                "tool_fixtures": [
                    {
                        "tool_name": "fetch_doc",
                        "default_output": {"content": "Verified runbook instructions"},
                        "latency_ms": 10.0,
                    }
                ],
                "fault_rules": [
                    {
                        "target_tool": "fetch_doc",
                        "fault_type": "TIMEOUT",
                        "trigger_on_call": 1,
                        "error_message": "Read timed out on first attempt",
                        "injected_latency_ms": 500.0,
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
    assert run_data["status"] == "completed"
    assert run_data["run_metadata"]["injected_fault_count"] == 1
    assert "[fallback:fetch_doc=TIMEOUT] [ok:fetch_doc]" in run_data["final_answer"]

    traces = run_data["trace_events"]
    # گام ۱: فراخوانی اول ابزار (خطای TIMEOUT)
    assert traces[1]["status"] == "error"
    assert traces[1]["output_payload"]["error_type"] == "TIMEOUT"
    # گام ۳: فراخوانی دوم همان ابزار (موفق و سالم)
    assert traces[3]["status"] == "ok"
    assert traces[3]["output_payload"]["output"] == {
        "content": "Verified runbook instructions"
    }


async def test_fault_injector_payload_corruption_variants() -> None:
    """Verify MALFORMED_JSON, EMPTY_RESPONSE, and CONTRADICTORY_DATA fault outputs."""
    rules = [
        FaultRuleSpec(
            target_tool="json_api",
            fault_type="MALFORMED_JSON",
            trigger_on_call=1,
            error_message="Corrupted JSON stream",
        ),
        FaultRuleSpec(
            target_tool="empty_api",
            fault_type="EMPTY_RESPONSE",
            trigger_on_call=1,
            error_message="Empty payload returned",
        ),
        FaultRuleSpec(
            target_tool="rag_retriever",
            fault_type="CONTRADICTORY_DATA",
            trigger_on_call=1,
            error_message="Service region is simultaneously eu-west-1 and us-east-1",
        ),
    ]
    injector = FaultInjector(rules)
    wrapped = injector.wrap(default_mock_tool_handler)

    res_malformed = await wrapped(
        ToolCallRequest(call_id="c1", tool_name="json_api", arguments={})
    )
    assert res_malformed.status == "error"
    assert res_malformed.error_type == "MALFORMED_JSON"
    assert res_malformed.output is not None
    assert "raw_corrupted_payload" in res_malformed.output

    res_empty = await wrapped(
        ToolCallRequest(call_id="c2", tool_name="empty_api", arguments={})
    )
    assert res_empty.status == "error"
    assert res_empty.error_type == "EMPTY_RESPONSE"
    assert res_empty.output == {}

    res_contra = await wrapped(
        ToolCallRequest(call_id="c3", tool_name="rag_retriever", arguments={})
    )
    assert res_contra.status == "error"
    assert res_contra.error_type == "CONTRADICTORY_DATA"
    assert res_contra.output is not None
    assert res_contra.output["contradiction_injected"] is True

    assert len(injector.triggered_events) == 3
