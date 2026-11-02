"""End-to-end verification of the complete 15-step FAULTLINE product workflow."""

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


async def test_complete_15_step_reliability_engineering_mvp_workflow(
    api_client: AsyncClient,
) -> None:
    """Verify all 15 steps of the main FAULTLINE workflow from project to release gate."""
    # گام ۱: ایجاد پروژه کاری
    proj_resp = await api_client.post(
        "/api/v1/projects",
        json={
            "slug": "e2e-reliability-workbench",
            "name": "E2E Reliability Workbench",
            "description": "Full 15-step workflow verification.",
        },
    )
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # گام ۲: ثبت ایجنت پژوهشی LangGraph
    agent_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/agents",
        json={
            "name": "research-rag-agent",
            "version": 1,
            "adapter_type": "langgraph",
            "model_name": "gpt-4o-mini-graph",
            "config_payload": {
                "tokens_per_step": 25,
                "model_latency_ms": 10.0,
                "fallback_on_tool_error": False,
            },
            "secret_refs": {"openai": "OPENAI_API_KEY"},
        },
    )
    assert agent_resp.status_code == 201
    agent_id = agent_resp.json()["id"]

    # گام ۳ و ۴: تعریف تسک، رفتار مورد انتظار و ساخت سناریوی نسخه‌بندی‌شده
    scenario_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={
            "name": "rag-retrieval-rate-limit-chaos",
            "version": 1,
            "description": "Tests transient HTTP 429 on search_tool during research.",
            "spec": {
                "task_prompt": "Summarize postmortem findings for outage INC-2026.",
                "planned_tool_calls": [
                    {
                        "call_id": "call-1",
                        "tool_name": "search_tool",
                        "arguments": {"query": "INC-2026 postmortem"},
                    },
                    {
                        "call_id": "call-2",
                        "tool_name": "retrieve_docs",
                        "arguments": {"doc_id": "PM-2026"},
                    },
                ],
                "tool_fixtures": [
                    {
                        "tool_name": "search_tool",
                        "default_output": {"doc_id": "PM-2026"},
                        "latency_ms": 12.0,
                    },
                    {
                        "tool_name": "retrieve_docs",
                        "default_output": {"summary": "BGP route leak in us-east"},
                        "latency_ms": 18.0,
                    },
                ],
                "fault_rules": [
                    {
                        "target_tool": "search_tool",
                        "fault_type": "HTTP_429_RATE_LIMIT",
                        "trigger_on_call": 1,
                        "error_message": "Search API returned 429 Too Many Requests",
                        "injected_latency_ms": 45.0,
                    }
                ],
                "evaluation_criteria": {
                    "require_completed_status": True,
                    "required_substrings": ["[ok:search_tool]", "[ok:retrieve_docs]"],
                    "expected_tools": ["search_tool", "retrieve_docs"],
                    "max_total_latency_ms": 300.0,
                    "max_total_tokens": 250,
                },
                "safety_constraints": {
                    "max_steps": 10,
                    "timeout_seconds": 30.0,
                    "allow_live_external_actions": False,
                },
            },
        },
    )
    assert scenario_resp.status_code == 201
    scenario_id = scenario_resp.json()["id"]

    # گام ۵: اجرای پایه بدون تزریق خطا (Baseline Run)
    base_run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "baseline",
        },
    )
    assert base_run_resp.status_code == 201
    base_run_id = base_run_resp.json()["id"]
    assert base_run_resp.json()["status"] == "completed"

    # گام ۶: اجرای آزمایش تزریق خطای کنترل‌شده (Fault-Injected Run)
    fault_run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "fault_injected",
        },
    )
    assert fault_run_resp.status_code == 201
    fault_run_id = fault_run_resp.json()["id"]
    assert fault_run_resp.json()["status"] == "failed"

    # گام ۷: دریافت و بازرسی مسیر کامل تریس‌های قابل‌مشاهده
    traces_resp = await api_client.get(
        f"/api/v1/projects/{project_id}/runs/{fault_run_id}/traces"
    )
    assert traces_resp.status_code == 200
    assert len(traces_resp.json()) == 2
    assert traces_resp.json()[1]["status"] == "error"

    # گام ۸: ارزیابی نتایج در برابر معیارهای صریح سناریو
    base_eval_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{base_run_id}/evaluate"
    )
    assert base_eval_resp.json()["task_succeeded"] is True

    fault_eval_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{fault_run_id}/evaluate"
    )
    assert fault_eval_resp.json()["task_succeeded"] is False

    # گام ۹: مقایسه علمی اجرای پایه و اجرای خطادار
    cmp_resp = await api_client.get(
        f"/api/v1/projects/{project_id}/evaluations/compare",
        params={"baseline_run_id": base_run_id,
                "candidate_run_id": fault_run_id},
    )
    assert cmp_resp.status_code == 200
    assert cmp_resp.json()["outcome_classification"] == "degraded"

    # گام ۱۰: تست سیاست بازیابی (Recovery Policy) روی همان سناریو
    rec_run_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "agent_config_id": agent_id,
            "scenario_id": scenario_id,
            "run_mode": "recovery",
            "recovery_policy": {
                "strategy": "retry",
                "max_retries": 1,
                "backoff_ms": 20.0,
                "retryable_fault_types": ["HTTP_429_RATE_LIMIT"],
            },
        },
    )
    assert rec_run_resp.status_code == 201
    rec_run_id = rec_run_resp.json()["id"]
    assert rec_run_resp.json()["status"] == "completed"

    # بررسی بازپخش قطعی و محاسبه تفاوت گام‌ها
    replay_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{fault_run_id}/replay",
        json={"replay_mode": "recorded_replay"},
    )
    assert replay_resp.status_code == 201
    assert replay_resp.json()["diff"]["trace_path_identical"] is True

    diff_rec_resp = await api_client.get(
        f"/api/v1/projects/{project_id}/runs/{fault_run_id}/diff/{rec_run_id}"
    )
    assert diff_rec_resp.status_code == 200
    assert diff_rec_resp.json()["trace_path_identical"] is False

    # گام ۱۱: ریشه‌یابی خطا با استفاده از شواهد و ثبت تاییدیه مهندس انسان
    diag_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{fault_run_id}/diagnose"
    )
    assert diag_resp.status_code == 200
    assert diag_resp.json()["confirmation_status"] == "pending_human_review"

    confirm_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/runs/{fault_run_id}/diagnosis/confirm",
        json={
            "confirmed_by": "erfan.saraee",
            "confirmed_root_cause": "Unrecovered HTTP 429 on search_tool invocation #1.",
            "selected_classification_code": "DEPENDENCY_RATE_LIMITED",
        },
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["confirmation_status"] == "confirmed"

    # گام ۱۲: تولید کاندیدای تست رگرسیون از روی اجرای تاییدشده
    reg_cand_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/regression-cases",
        json={
            "source_run_id": fault_run_id,
            "name": "reg-search-tool-429",
            "description": "Prevent regression on search_tool transient HTTP 429.",
        },
    )
    assert reg_cand_resp.status_code == 201
    case_id = reg_cand_resp.json()["id"]

    # گام ۱۳: بازبینی و تایید تست رگرسیون توسط انسان
    review_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/regression-cases/{case_id}/review",
        json={"decision": "approved", "reviewed_by": "erfan.saraee"},
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["approval_status"] == "approved"

    # گام ۱۴ و ۱۵ (الف): رد انتشار زمانی که معیارهای پایداری برآورده نمی‌شوند
    reject_gate_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/regression-suite/evaluate-release",
        json={
            "agent_config_id": agent_id,
            "gate_criteria": {
                "min_pass_rate": 1.0,
                "min_average_reliability_score": 0.95,
            },
        },
    )
    assert reject_gate_resp.status_code == 200
    assert reject_gate_resp.json()["release_decision"] == "rejected"

    # گام ۱۴ و ۱۵ (ب): تایید انتشار زمانی که سیاست بازیابی معیارها را برآورده می‌کند
    approve_gate_resp = await api_client.post(
        f"/api/v1/projects/{project_id}/regression-suite/evaluate-release",
        json={
            "agent_config_id": agent_id,
            "recovery_policy": {
                "strategy": "retry",
                "max_retries": 1,
                "backoff_ms": 15.0,
                "retryable_fault_types": ["HTTP_429_RATE_LIMIT"],
            },
            "gate_criteria": {
                "min_pass_rate": 1.0,
                "min_average_reliability_score": 0.95,
            },
        },
    )
    assert approve_gate_resp.status_code == 200
    assert approve_gate_resp.json()["release_decision"] == "approved"
