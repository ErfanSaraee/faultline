import type {
    AgentConfig,
    DiagnosisReport,
    EvaluationReport,
    ExecutionRun,
    Project,
    ReleaseGateEvaluation,
    ScenarioDefinition,
} from "../types/api";

const API_BASE = "http://127.0.0.1:8000/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });
    if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(errBody.detail || `HTTP ${response.status}`);
    }
    return response.json() as Promise<T>;
}

export const faultlineApi = {
    listProjects: () => request<Project[]>("/projects"),
    createProject: (slug: string, name: string) =>
        request<Project>("/projects", {
            method: "POST",
            body: JSON.stringify({ slug, name }),
        }),
    createLangGraphAgent: (projectId: string, name: string) =>
        request<AgentConfig>(`/projects/${projectId}/agents`, {
            method: "POST",
            body: JSON.stringify({
                name,
                version: 1,
                adapter_type: "langgraph",
                model_name: "gpt-4o-mini-graph",
                config_payload: { tokens_per_step: 25, model_latency_ms: 12.0 },
            }),
        }),
    createChaosScenario: (projectId: string, name: string) =>
        request<ScenarioDefinition>(`/projects/${projectId}/scenarios`, {
            method: "POST",
            body: JSON.stringify({
                name,
                version: 1,
                spec: {
                    task_prompt: "Investigate Q3 cloud incident and retrieve postmortem.",
                    planned_tool_calls: [
                        {
                            call_id: "call-1",
                            tool_name: "search_web",
                            arguments: { query: "Q3 outage" },
                        },
                        {
                            call_id: "call-2",
                            tool_name: "retrieve_docs",
                            arguments: { doc_id: "INC-2026" },
                        },
                    ],
                    tool_fixtures: [
                        {
                            tool_name: "search_web",
                            default_output: { hit: "INC-2026" },
                            latency_ms: 15.0,
                        },
                        {
                            tool_name: "retrieve_docs",
                            default_output: { summary: "DNS resolver timeout" },
                            latency_ms: 20.0,
                        },
                    ],
                    fault_rules: [
                        {
                            target_tool: "search_web",
                            fault_type: "HTTP_429_RATE_LIMIT",
                            trigger_on_call: 1,
                            error_message: "429 Too Many Requests on search_web",
                            injected_latency_ms: 55.0,
                        },
                    ],
                    evaluation_criteria: {
                        require_completed_status: True_val(),
                        required_substrings: ["[ok:search_web]", "[ok:retrieve_docs]"],
                        expected_tools: ["search_web", "retrieve_docs"],
                        max_total_latency_ms: 400.0,
                    },
                },
            }),
        }),
    executeRun: (
        projectId: string,
        agentId: string,
        scenarioId: string,
        runMode: "baseline" | "fault_injected" | "recovery"
    ) =>
        request<ExecutionRun>(`/projects/${projectId}/runs`, {
            method: "POST",
            body: JSON.stringify({
                agent_config_id: agentId,
                scenario_id: scenarioId,
                run_mode: runMode,
                recovery_policy:
                    runMode === "recovery"
                        ? {
                            strategy: "retry",
                            max_retries: 1,
                            backoff_ms: 20.0,
                            retryable_fault_types: ["HTTP_429_RATE_LIMIT"],
                        }
                        : undefined,
            }),
        }),
    evaluateRun: (projectId: string, runId: string) =>
        request<EvaluationReport>(`/projects/${projectId}/runs/${runId}/evaluate`, {
            method: "POST",
        }),
    diagnoseRun: (projectId: string, runId: string) =>
        request<DiagnosisReport>(`/projects/${projectId}/runs/${runId}/diagnose`, {
            method: "POST",
        }),
    confirmDiagnosis: (projectId: string, runId: string, engineer: string) =>
        request<DiagnosisReport>(
            `/projects/${projectId}/runs/${runId}/diagnosis/confirm`,
            {
                method: "POST",
                body: JSON.stringify({
                    confirmed_by: engineer,
                    confirmed_root_cause:
                        "Transient HTTP 429 on search_web caused unrecovered abort.",
                    selected_classification_code: "DEPENDENCY_RATE_LIMITED",
                }),
            }
        ),
    createAndApproveRegression: async (
        projectId: string,
        sourceRunId: string,
        name: string
    ) => {
        const candidate = await request<{ id: string }>(
            `/projects/${projectId}/regression-cases`,
            {
                method: "POST",
                body: JSON.stringify({ source_run_id: sourceRunId, name }),
            }
        );
        return request(`/projects/${projectId}/regression-cases/${candidate.id}/review`, {
            method: "POST",
            body: JSON.stringify({
                decision: "approved",
                reviewed_by: "erfan.saraee",
            }),
        });
    },
    evaluateReleaseGate: (
        projectId: string,
        agentId: string,
        withRecovery: boolean
    ) =>
        request<ReleaseGateEvaluation>(
            `/projects/${projectId}/regression-suite/evaluate-release`,
            {
                method: "POST",
                body: JSON.stringify({
                    agent_config_id: agentId,
                    recovery_policy: withRecovery
                        ? {
                            strategy: "retry",
                            max_retries: 1,
                            backoff_ms: 20.0,
                            retryable_fault_types: ["HTTP_429_RATE_LIMIT"],
                        }
                        : undefined,
                }),
            }
        ),
};

function True_val(): boolean {
    return true;
}