# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 9 Complete / Entering Phase 10
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
* **Next Immediate Step:** Phase 10 (Replay Engine: explicit separation of `recorded_replay` vs. `live_replay`, provenance preservation, and step-by-step execution diffing).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 through ADR-012:** (Modular monolith, async SQLAlchemy, repository pattern, zero raw secrets, decoupled `AgentAdapter` / `ToolHandler`, validated `ScenarioSpec`, eager-loaded trace persistence, tool-boundary `FaultInjector`, and deterministic `EvaluationEngine`).
* **ADR-013 (Tool-Boundary Recovery Interceptor & Trace Expansion):** Implemented `RecoveryToolInterceptor` around `FaultInjector` to execute bounded retries (with configurable `backoff_ms` and `retry_token_overhead`) and fallback tool routing (`fallback_tool_map`). Expanded intermediate retry/fallback attempts into explicit `TraceEvent` rows so `EvaluationEngine` accurately measures retry overhead and SLA violations.

## 3. Verified Test Coverage
* `tests/test_health.py` (2 passed)
* `tests/test_db.py` (3 passed)
* `tests/test_workspace.py` (4 passed)
* `tests/test_adapters.py` (5 passed)
* `tests/test_scenarios.py` (4 passed)
* `tests/test_execution.py` (4 passed)
* `tests/test_faults.py` (3 passed)
* `tests/test_evaluation.py` (3 passed)
* `tests/test_recovery.py` (4 passed: bounded retry recovery, retry exhaustion, fallback tool routing, recovery policy validation)
* Static analysis: Ruff (clean), Mypy strict (clean, 46 files).

## 4. Known Limitations
* Runs cannot yet be replayed from recorded traces or diffed step-by-step for execution path deviations; this is addressed in Phase 10 (`ReplayEngine`).