# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 8 Complete / Entering Phase 9
* **Completed Phases:**
  * Phase 1 (Bootstrap, Typed Configuration, Health Check API, and Test Harness)
  * Phase 2 (PostgreSQL Infrastructure, Async SQLAlchemy 2.x Engine, Alembic Setup, and Readiness Probe)
  * Phase 3 (Core Workspace Domain: `Project` and `AgentConfig`, Repositories, and CRUD APIs)
  * Phase 4 (Framework-Agnostic `AgentAdapter` Contract, `ToolHandler`, `DeterministicMockAgent`, and `AdapterRegistry`)
  * Phase 5 (Versioned `ScenarioDefinition` Schema, Safety/Criteria Guardrails, Repository, and CRUD APIs)
  * Phase 6 (Baseline Execution Engine, Fixture-Backed `ToolHandler`, `ExecutionRun` and `TraceEvent` Persistence & APIs)
  * Phase 7 (Controlled Fault Injection Engine: `FaultInjector`, per-tool call counters, payload corruption variants, and `"fault_injected"` execution mode)
  * Phase 8 (Evaluation Engine: explicit assertion checks, superficial-vs-true completion detection, retry/cost/latency metrics, and run comparison APIs)
* **Next Immediate Step:** Phase 9 (Recovery Policy Engine: `RecoveryPolicySpec`, `RecoveryToolInterceptor`, bounded retries, fallback tool routing, and recovery trade-off evaluation).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 through ADR-011:** (Modular monolith, async SQLAlchemy, repository pattern, zero raw secrets, decoupled `AgentAdapter` / `ToolHandler`, validated `ScenarioSpec`, eager-loaded trace persistence, and tool-boundary `FaultInjector`).
* **ADR-012 (Evidence-Grounded Deterministic Evaluation):** Implemented `EvaluationEngine` to score runs strictly against explicit `ScenarioSpec.evaluation_criteria` (terminal status, required/forbidden substrings, expected/forbidden tools, and latency/token budgets) rather than trusting `run.status == 'completed'` alone. Added `/evaluations/compare` to compute exact reliability, latency, token, cost, and retry deltas between runs.

## 3. Verified Test Coverage
* `tests/test_health.py` (2 passed)
* `tests/test_db.py` (3 passed)
* `tests/test_workspace.py` (4 passed)
* `tests/test_adapters.py` (5 passed)
* `tests/test_scenarios.py` (4 passed)
* `tests/test_execution.py` (4 passed)
* `tests/test_faults.py` (3 passed)
* `tests/test_evaluation.py` (3 passed: superficial completion detection & run comparison, retry/forbidden-tool/token-budget metrics, unscored run 404)
* Static analysis: Ruff (clean), Mypy strict (clean, 44 files).

## 4. Known Limitations
* Fault-injected runs can be executed and evaluated, but automated recovery policy experiments (`"recovery"` run mode with bounded retries and fallback tools) require Phase 9.