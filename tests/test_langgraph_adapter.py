"""Automated tests for Phase 13 LangGraphResearchAdapter integration and chaos workflows."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from faultline.adapters import AdapterRegistry, LangGraphResearchAdapter
from faultline.api.app import create_app
from faultline.core.config import Settings
from faultline.db.base import Base
from faultline.schemas.adapter import AgentTaskInput


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


async def test_langgraph_research_agent_end_to_end_fault_and_recovery_workflow(
    api_client: AsyncClient,
) -> None:
    """Verify LangGraph research agent across baseline, fault_injected, and recovery runs."""
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={"slug": "langgraph-research-lab",
              "name": "LangGraph Research Lab"},
    )
    project_id = proj_resp.json()["id"]

    # ثبت ایجنت با adapter_type='langgraph'
    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "langgraph-research-assistant",
            "version": 1,
            "adapter_type": "langgraph",
            "model_name": "gpt-4o-mini-graph",
            "config_payload": {
                "tokens_per_step": 30,
                "model_latency_ms": 12.0,
                "fallback_on_tool_error": False,
            },
        },
    )
    assert agent_resp.status_code == 201
    agent_id = agent_resp.json()["id"]

    # ثبت سناریوی پژوهشی دو مرحله‌ای (جستجوی وب + بازیابی سند)
    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "multi-step-research-chaos",
            "version": 1,
            "spec": {
                "task_prompt": "Investigate distributed consensus raft leader election.",
                "planned_tool_calls": [
                    {
                        "call_id": "call-search-1",
                        "tool_name": "search_web",
                        "arguments": {"query": "raft leader election split vote"},
                    },
                    {
                        "call_id": "call-doc-1",
                        "tool_name": "retrieve_docs",
                        "arguments": {"doc_id": "paper-raft-2014"},
                    },
                ],
                "tool_fixtures": [
                    {
                        "tool_name": "search_web",
                        "default_output": {"top_hit": "paper-raft-2014"},
                        "latency_ms": 20.0,
                    },
                    {
                        "tool_name": "retrieve_docs",
                        "default_output": {"content": "Randomized election timeouts"},
                        "latency_ms": 25.0,
                    },
                    {
                        "tool_name": "retrieve_docs_cache",
                        "default_output": {"content": "Cached raft election summary"},
                        "latency_ms": 8.0,
                    },
                ],
                "fault_rules": [
                    {
                        "target_tool": "search_web",
                        "fault_type": "HTTP_429_RATE_LIMIT",
                        "trigger_on_call": 1,
                        "error_message": "Search API rate limited (429)",
                        "injected_latency_ms": 40.0,
                    },
                    {
                        "target_tool": "retrieve_docs",
                        "fault_type": "TIMEOUT",
                        "trigger_on_call": 1,
                        "error_message": "Document store timed out (attempt 1)",
                        "injected_latency_ms": 80.0,
                    },
                    {
                        "target_tool": "retrieve_docs",
                        "fault_type": "TIMEOUT",
                        "trigger_on_call": 2,
                        "error_message": "Document store timed out (attempt 2)",
                        "injected_latency_ms": 80.0,
                    },
                ],
                "evaluation_criteria": {
                    "require_completed_status": True,
                    "required_substrings": ["[ok:search_web]"],
                    "expected_tools": ["search_web"],
                    "max_total_latency_ms": 500.0,
                },
            },
        },
    )
    scenario_id = scenario_resp.json()["id"]

    # ۱. اجرای پایه (Baseline) روی گراف واقعی LangGraph
    base_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "baseline",
        },
    )
    assert base_resp.status_code == 201
    base_run = base_resp.json()
    assert base_run["status"] == "completed"
    assert base_run["adapter_type"] == "langgraph"
    assert len(base_run["trace_events"]) == 5
    assert base_run["trace_events"][0]["input_payload"]["graph_node"] == "planner"
    assert base_run["trace_events"][1]["input_payload"]["graph_node"] == "tool_executor"
    assert base_run["trace_events"][4]["input_payload"]["graph_node"] == "synthesizer"

    # ۲. اجرای خطادار (Fault Injected) بدون ریکاوری
    fault_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "fault_injected",
        },
    )
    assert fault_resp.status_code == 201
    fault_run = fault_resp.json()
    assert fault_run["status"] == "failed"
    assert "HTTP_429_RATE_LIMIT" in fault_run["error_message"]

    # ۳. اجرای بازیابی (Recovery) با Retry روی ابزار جستجو و Fallback روی ابزار اسناد
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
                "retryable_fault_types": ["HTTP_429_RATE_LIMIT", "TIMEOUT"],
                "fallback_tool_map": {"retrieve_docs": "retrieve_docs_cache"},
            },
        },
    )
    assert rec_resp.status_code == 201
    rec_run = rec_resp.json()
    assert rec_run["status"] == "completed"
    assert "[ok:search_web] [ok:retrieve_docs_cache]" in rec_run["final_answer"]

    eval_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{rec_run['id']}/evaluate"
    )
    assert eval_resp.status_code == 200
    assert eval_resp.json()["task_succeeded"] is True
    assert eval_resp.json()["reliability_score"] == 1.0


async def test_langgraph_adapter_auto_plans_research_tools_and_enforces_max_steps() -> None:
    """Verify auto_plan_research_tools and max_steps guardrail inside StateGraph."""
    registry = AdapterRegistry()
    assert "langgraph" in registry.list_supported_types()

    adapter = registry.get("langgraph")
    assert isinstance(adapter, LangGraphResearchAdapter)

    # تست برنامه‌ریزی خودکار ابزارهای پژوهش زمانی که لیست ابزار خالی است
    auto_output = await adapter.execute(
        model_name="langgraph-v1",
        config_payload={"auto_plan_research_tools": True},
        task_input=AgentTaskInput(
            task_prompt="Analyze PostgreSQL connection pooling bottlenecks.",
            max_steps=10,
        ),
    )
    assert auto_output.status == "completed"
    assert len(auto_output.steps) == 5
    assert auto_output.final_answer is not None
    assert "[ok:search_web] [ok:retrieve_docs]" in auto_output.final_answer

    # تست توقف گراف در صورت عبور از سقف گام‌های مجاز (max_steps)
    limited_output = await adapter.execute(
        model_name="langgraph-v1",
        config_payload={"auto_plan_research_tools": True},
        task_input=AgentTaskInput(
            task_prompt="Analyze PostgreSQL connection pooling bottlenecks.",
            max_steps=3,
        ),
    )
    assert limited_output.status == "max_steps_exceeded"
    assert len(limited_output.steps) == 3
