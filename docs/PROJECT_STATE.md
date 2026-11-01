# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 14 Complete / Entering Phase 15 (Final MVP Phase)
* **Completed Phases:**
  * Phase 1 (Bootstrap, Typed Configuration, Health Check API, and Test Harness)
  * Phase 2 (PostgreSQL Infrastructure, Async SQLAlchemy 2.x Engine, Alembic Setup, and Readiness Probe)
  * Phase 3 (Core Workspace Domain: `Project` and `AgentConfig`, Repositories, and CRUD APIs)
  * Phase 4 (Framework-Agnostic `AgentAdapter` Contract, `ToolHandler`, `DeterministicMockAgent`, and `AdapterRegistry`)
  * Phase 5 (Versioned `ScenarioDefinition` Schema, Safety/Criteria Guardrails, Repository, and CRUD APIs)
  * Phase 6 (Baseline Execution Engine, Fixture-Backed `ToolHandler`, `ExecutionRun` and `TraceEvent` Persistence & APIs)
  * Phase 7 (Controlled Fault Injection Engine: `FaultInjector`, per-tool call counters, payload corruption variants, and `"fault_injected"` execution mode)
  * Phase 8 (Evaluation Engine: explicit assertion checks, superficial-vs-true completion detection, retry/cost/latency metrics, and run comparison APIs)
  * Phase 9 (Recovery Policy Engine: `RecoveryPolicySpec`, `RecoveryToolInterceptor`, bounded retries, fallback tool routing, and per-attempt trace expansion)
  * Phase 10 (Replay Engine: explicit separation of `recorded_replay` vs. `live_replay`, `RecordedToolHandler`, and step-by-step execution diffing)
  * Phase 11 (Evidence-Based Failure Diagnosis: 4-tier separation of Observed Facts, Rule Classifications, Unconfirmed Model Hypotheses, and Human-Confirmed Causes)
  * Phase 12 (Regression Suite Engine: candidate generation from confirmed diagnoses, human approval workflow, and automated Release Gate enforcement)
  * Phase 13 (Real Framework Integration: `LangGraphResearchAdapter` using `langgraph.graph.StateGraph`)
  * Phase 14 (Security Hardening, Automated Secret/PII/CoT Redaction in `ExecutionRunRepository`, OpenTelemetry Span Emission, and Bounded-Cardinality Metrics)
* **Next Immediate Step:** Phase 15 (Developer Workbench UI in React + TypeScript, CORS support, 15-step End-to-End MVP Verification Test, Docker Compose, and Portfolio Documentation).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 through ADR-017:** (Modular monolith, async SQLAlchemy, repository pattern, zero raw secrets, decoupled `AgentAdapter` / `ToolHandler`, validated `ScenarioSpec`, eager-loaded trace persistence, `FaultInjector`, `EvaluationEngine`, `RecoveryToolInterceptor`, `ReplayEngine`, 4-tier `DiagnosisEngine`, human-gated `RegressionSuiteEngine`, and `LangGraphResearchAdapter`).
* **ADR-018 (Storage-Boundary Redaction & Complementary OpenTelemetry Instrumentation):** Enforced recursive secret, PII, and hidden Chain-of-Thought (`[REDACTED_COT]`) scrubbing inside `ExecutionRunRepository` before any run or trace event is written to PostgreSQL. Integrated `opentelemetry-sdk` span emission and bounded-cardinality platform counters alongside internal experiment tables, correlating each `ExecutionRun` via `run_metadata["otel_trace_id"]`.

## 3. Verified Test Coverage
* `tests/test_health.py` (2 passed)
* `tests/test_db.py` (3 passed)
* `tests/test_workspace.py` (4 passed)
* `tests/test_adapters.py` (5 passed)
* `tests/test_scenarios.py` (4 passed)
* `tests/test_execution.py` (4 passed)
* `tests/test_faults.py` (3 passed)
* `tests/test_evaluation.py` (3 passed)
* `tests/test_recovery.py` (4 passed)
* `tests/test_replay.py` (3 passed)
* `tests/test_diagnosis.py` (3 passed)
* `tests/test_regression.py` (3 passed)
* `tests/test_langgraph_adapter.py` (2 passed)
* `tests/test_security_and_observability.py` (2 passed: secret/PII/CoT redaction and OpenTelemetry spans/metrics)
* Static analysis: Ruff (clean), Mypy strict (clean, 71 files).

## 4. Known Limitations
* The React + TypeScript Developer Workbench UI and end-to-end 15-step workflow verification test are scheduled for Phase 15.