import { useState } from "react";
import { faultlineApi } from "./api/client";
import type {
    AgentConfig,
    DiagnosisReport,
    EvaluationReport,
    ExecutionRun,
    Project,
    ReleaseGateEvaluation,
    ScenarioDefinition,
} from "./types/api";

export function App() {
    const [project, setProject] = useState<Project | null>(null);
    const [agent, setAgent] = useState<AgentConfig | null>(null);
    const [scenario, setScenario] = useState<ScenarioDefinition | null>(null);
    const [runs, setRuns] = useState<ExecutionRun[]>([]);
    const [selectedRun, setSelectedRun] = useState<ExecutionRun | null>(null);
    const [evaluation, setEvaluation] = useState<EvaluationReport | null>(null);
    const [diagnosis, setDiagnosis] = useState<DiagnosisReport | null>(null);
    const [gateResult, setGateResult] = useState<ReleaseGateEvaluation | null>(null);
    const [error, setError] = useState<string | null>(null);

    async function handleBootstrapLab() {
        try {
            setError(null);
            const suffix = Math.floor(Math.random() * 9000 + 1000);
            const proj = await faultlineApi.createProject(
                `faultline-lab-${suffix}`,
                `Chaos Lab #${suffix}`
            );
            const ag = await faultlineApi.createLangGraphAgent(
                proj.id,
                "langgraph-research-agent"
            );
            const sc = await faultlineApi.createChaosScenario(
                proj.id,
                "q3-outage-http-429-scenario"
            );
            setProject(proj);
            setAgent(ag);
            setScenario(sc);
            setRuns([]);
            setSelectedRun(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to initialize lab");
        }
    }

    async function handleTriggerRun(
        mode: "baseline" | "fault_injected" | "recovery"
    ) {
        if (!project || !agent || !scenario) return;
        try {
            setError(null);
            const run = await faultlineApi.executeRun(
                project.id,
                agent.id,
                scenario.id,
                mode
            );
            setRuns((prev) => [run, ...prev]);
            setSelectedRun(run);
            const evalRep = await faultlineApi.evaluateRun(project.id, run.id);
            setEvaluation(evalRep);
            const diagRep = await faultlineApi.diagnoseRun(project.id, run.id);
            setDiagnosis(diagRep);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Run execution failed");
        }
    }

    async function handleConfirmAndLockRegression() {
        if (!project || !selectedRun) return;
        try {
            setError(null);
            const confirmed = await faultlineApi.confirmDiagnosis(
                project.id,
                selectedRun.id,
                "erfan.saraee"
            );
            setDiagnosis(confirmed);
            await faultlineApi.createAndApproveRegression(
                project.id,
                selectedRun.id,
                `reg-${selectedRun.id.slice(0, 6)}`
            );
        } catch (err) {
            setError(err instanceof Error ? err.message : "Confirmation failed");
        }
    }

    async function handleRunReleaseGate(withRecovery: boolean) {
        if (!project || !agent) return;
        try {
            setError(null);
            const res = await faultlineApi.evaluateReleaseGate(
                project.id,
                agent.id,
                withRecovery
            );
            setGateResult(res);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Release gate failed");
        }
    }

    return (
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: 24 }}>
            <header style={{ borderBottom: "1px solid #1e293b", paddingBottom: 16, marginBottom: 24 }}>
                <h1 style={{ margin: 0, color: "#38bdf8" }}>FAULTLINE Workbench</h1>
                <p style={{ margin: "6px 0 0", color: "#94a3b8" }}>
                    Agent Reliability Engineering, Chaos Testing, Replay, Evaluation & Release Gate Platform
                </p>
            </header>

            {error && (
                <div style={{ background: "#7f1d1d", padding: 12, borderRadius: 6, marginBottom: 16 }}>
                    Error: {error}
                </div>
            )}

            <section style={{ background: "#111827", padding: 16, borderRadius: 8, marginBottom: 20 }}>
                <h2 style={{ marginTop: 0, fontSize: 18 }}>1. Workspace & LangGraph Scenario Setup</h2>
                <button
                    onClick={handleBootstrapLab}
                    style={{ background: "#0284c7", color: "#fff", border: "none", padding: "10px 16px", borderRadius: 6, cursor: "pointer" }}
                >
                    Initialize Project + LangGraph Agent + HTTP 429 Scenario
                </button>
                {project && agent && scenario && (
                    <div style={{ marginTop: 12, fontSize: 14, color: "#cbd5e1" }}>
                        <div><strong>Project:</strong> {project.name} ({project.slug})</div>
                        <div><strong>Agent:</strong> {agent.name} (adapter={agent.adapter_type}, model={agent.model_name})</div>
                        <div><strong>Scenario:</strong> {scenario.name} (v{scenario.version})</div>
                    </div>
                )}
            </section>

            {project && agent && scenario && (
                <section style={{ background: "#111827", padding: 16, borderRadius: 8, marginBottom: 20 }}>
                    <h2 style={{ marginTop: 0, fontSize: 18 }}>2. Execute Controlled Experiments</h2>
                    <div style={{ display: "flex", gap: 12 }}>
                        <button onClick={() => handleTriggerRun("baseline")} style={{ background: "#059669", color: "#fff", border: "none", padding: "8px 14px", borderRadius: 6, cursor: "pointer" }}>
                            Run Baseline (No Faults)
                        </button>
                        <button onClick={() => handleTriggerRun("fault_injected")} style={{ background: "#dc2626", color: "#fff", border: "none", padding: "8px 14px", borderRadius: 6, cursor: "pointer" }}>
                            Run Fault-Injected (HTTP 429)
                        </button>
                        <button onClick={() => handleTriggerRun("recovery")} style={{ background: "#7c3aed", color: "#fff", border: "none", padding: "8px 14px", borderRadius: 6, cursor: "pointer" }}>
                            Run with Bounded Retry Recovery
                        </button>
                    </div>
                </section>
            )}

            {selectedRun && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
                    <section style={{ background: "#111827", padding: 16, borderRadius: 8 }}>
                        <h3 style={{ marginTop: 0 }}>
                            3. Observable Trace Timeline ({selectedRun.run_mode} — {runs.length} runs)
                        </h3>
                        <div style={{ fontSize: 13, marginBottom: 12 }}>
                            Status: <strong>{selectedRun.status}</strong> | Tokens: {selectedRun.total_tokens} | Latency: {selectedRun.total_latency_ms}ms
                        </div>
                        {selectedRun.trace_events.map((step) => (
                            <div
                                key={step.id}
                                style={{
                                    borderLeft: step.status === "error" ? "4px solid #ef4444" : "4px solid #10b981",
                                    background: "#1e293b",
                                    padding: 10,
                                    marginBottom: 8,
                                    borderRadius: 4,
                                    fontSize: 13,
                                }}
                            >
                                <div>
                                    <strong>Step #{step.step_index}</strong> [{step.step_type}] — {step.name} ({step.status})
                                </div>
                                <div style={{ color: "#94a3b8" }}>
                                    Latency: {step.latency_ms}ms | Tokens: {step.tokens_used}
                                </div>
                            </div>
                        ))}
                    </section>

                    <section style={{ background: "#111827", padding: 16, borderRadius: 8 }}>
                        <h3 style={{ marginTop: 0 }}>4. Evaluation, 4-Tier Diagnosis & Release Gate</h3>
                        {evaluation && (
                            <div style={{ marginBottom: 14, fontSize: 13 }}>
                                <div><strong>Evaluation:</strong> {evaluation.summary}</div>
                                <div><strong>Reliability Score:</strong> {evaluation.reliability_score}</div>
                            </div>
                        )}
                        {diagnosis && (
                            <div style={{ marginBottom: 14, fontSize: 13 }}>
                                <div><strong>Diagnosis Status:</strong> {diagnosis.confirmation_status}</div>
                                <div><strong>Observed Facts:</strong> {diagnosis.observed_facts.length}</div>
                                <div>
                                    <strong>Rule Classifications:</strong>{" "}
                                    {diagnosis.rule_classifications.map((r) => r.classification_code).join(", ")}
                                </div>
                                <button
                                    onClick={handleConfirmAndLockRegression}
                                    style={{ marginTop: 10, background: "#d97706", color: "#fff", border: "none", padding: "7px 12px", borderRadius: 6, cursor: "pointer" }}
                                >
                                    Confirm Root Cause & Approve Regression Test
                                </button>
                            </div>
                        )}
                        {diagnosis?.confirmation_status === "confirmed" && (
                            <div style={{ borderTop: "1px solid #334155", paddingTop: 12 }}>
                                <div style={{ display: "flex", gap: 10 }}>
                                    <button onClick={() => handleRunReleaseGate(false)} style={{ background: "#b91c1c", color: "#fff", border: "none", padding: "7px 12px", borderRadius: 6, cursor: "pointer" }}>
                                        Test Release Gate (Unrecovered)
                                    </button>
                                    <button onClick={() => handleRunReleaseGate(true)} style={{ background: "#15803d", color: "#fff", border: "none", padding: "7px 12px", borderRadius: 6, cursor: "pointer" }}>
                                        Test Release Gate (With Recovery)
                                    </button>
                                </div>
                                {gateResult && (
                                    <div style={{ marginTop: 10, fontSize: 13 }}>
                                        <strong>Release Verdict:</strong> {gateResult.release_decision.toUpperCase()} (Pass rate: {gateResult.pass_rate * 100}%)
                                    </div>
                                )}
                            </div>
                        )}
                    </section>
                </div>
            )}
        </div>
    );
}