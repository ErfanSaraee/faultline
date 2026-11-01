# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 13 Complete / Entering Phase 14
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
* **Next Immediate Step:** Phase 14 (Security Hardening, Automated Secret/PII/CoT Redaction in Traces, OpenTelemetry Span Instrumentation, and Bounded-Cardinality Platform Metrics).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 through ADR-016:** (Modular monolith, async SQLAlchemy, repository pattern, zero raw secrets, decoupled `AgentAdapter` / `ToolHandler`, validated `ScenarioSpec`, eager-loaded trace persistence, `FaultInjector`, `EvaluationEngine`, `RecoveryToolInterceptor`, `ReplayEngine`, 4-tier `DiagnosisEngine`, and human-gated `RegressionSuiteEngine`).
* **ADR-017 (LangGraph StateGraph Integration via ToolHandler Boundary):** Implemented `LangGraphResearchAdapter` (`adapter_type='langgraph'`) using a compiled `StateGraph` (`planner` -> `tool_executor` -> `synthesizer`). By routing the graph's `tool_executor` node through FAULTLINE's `ToolHandler` contract, all fault injection, recovery policies, replay, and evaluation engines work seamlessly on LangGraph workflows without requiring external LLM API keys during automated testing.

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
* `tests/test_langgraph_adapter.py` (2 passed: end-to-end LangGraph baseline/fault/recovery workflow, auto-planning & max_steps guardrail)
* Static analysis: Ruff (clean), Mypy strict (clean, 65 files).

## 4. Known Limitations
* Trace payloads and final answers are persisted as-is without automated PII/secret/Chain-of-Thought scrubbing, and OpenTelemetry spans/metrics are not yet emitted; both are addressed in Phase 14.