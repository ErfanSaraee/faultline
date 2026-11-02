export interface Project {
    id: string;
    slug: string;
    name: string;
    description: string | null;
    created_at: string;
}

export interface AgentConfig {
    id: string;
    project_id: string;
    name: string;
    version: number;
    adapter_type: "mock" | "langgraph" | "http_proxy";
    model_name: string;
    config_payload: Record<string, unknown>;
}

export interface ScenarioDefinition {
    id: string;
    project_id: string;
    name: string;
    version: number;
    description: string | null;
    spec: {
        task_prompt: string;
        planned_tool_calls: Array<{
            call_id: string;
            tool_name: string;
            arguments: Record<string, unknown>;
        }>;
        fault_rules: Array<{
            target_tool: string;
            fault_type: string;
            trigger_on_call: number;
            error_message: string;
            injected_latency_ms: number;
        }>;
    };
}

export interface TraceEvent {
    id: string;
    step_index: number;
    step_type: "model_invocation" | "tool_call" | "final_response" | "error";
    name: string;
    status: "ok" | "error";
    input_payload: Record<string, unknown>;
    output_payload: Record<string, unknown>;
    latency_ms: number;
    tokens_used: number;
}

export interface ExecutionRun {
    id: string;
    project_id: string;
    agent_config_id: string;
    scenario_id: string;
    run_mode: string;
    status: "completed" | "failed" | "max_steps_exceeded";
    adapter_type: string;
    model_name: string;
    final_answer: string | null;
    error_message: string | null;
    total_tokens: number;
    total_latency_ms: number;
    run_metadata: Record<string, unknown>;
    trace_events: TraceEvent[];
}

export interface EvaluationReport {
    id: string;
    run_id: string;
    task_succeeded: boolean;
    reliability_score: number;
    summary: string;
    metrics: {
        tool_call_count: number;
        failed_tool_call_count: number;
        tool_retry_count: number;
        tool_correctness_rate: number;
        injected_fault_count: number;
        total_latency_ms: number;
        total_tokens: number;
        estimated_cost_usd: number;
    };
}

export interface DiagnosisReport {
    id: string;
    run_id: string;
    confirmation_status: "pending_human_review" | "confirmed";
    observed_facts: Array<{
        fact_id: string;
        source_type: string;
        component_name: string;
        statement: string;
    }>;
    rule_classifications: Array<{
        rule_id: string;
        classification_code: string;
        severity: string;
        title: string;
    }>;
    model_hypotheses: Array<{
        hypothesis_id: string;
        verification_status: string;
        confidence: number;
        hypothesis_statement: string;
        suggested_remediation: string;
    }>;
    human_confirmed_cause: {
        confirmed_by: string;
        confirmed_root_cause: string;
    } | null;
    summary: string;
}

export interface ReleaseGateEvaluation {
    release_decision: "approved" | "rejected";
    total_cases_executed: number;
    passed_cases: number;
    failed_cases: number;
    pass_rate: number;
    average_reliability_score: number;
    rejection_reasons: string[];
}