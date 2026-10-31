# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 7 Complete / Entering Phase 8
* **Completed Phases:**
  * Phase 1 (Bootstrap, Typed Configuration, Health Check API, and Test Harness)
  * Phase 2 (PostgreSQL Infrastructure, Async SQLAlchemy 2.x Engine, Alembic Setup, and Readiness Probe)
  * Phase 3 (Core Workspace Domain: `Project` and `AgentConfig`, Repositories, and CRUD APIs)
  * Phase 4 (Framework-Agnostic `AgentAdapter` Contract, `ToolHandler`, `DeterministicMockAgent`, and `AdapterRegistry`)
  * Phase 5 (Versioned `ScenarioDefinition` Schema, Safety/Criteria Guardrails, Repository, and CRUD APIs)
  * Phase 6 (Baseline Execution Engine, Fixture-Backed `ToolHandler`, `ExecutionRun` and `TraceEvent` Persistence & APIs)
  * Phase 7 (Controlled Fault Injection Engine: `FaultInjector`, per-tool invocation tracking, payload corruption variants, and `"fault_injected"` execution mode)
* **Next Immediate Step:** Phase 8 (Evaluation Engine: explicit assertions, reliability scoring, failure classification, and baseline-vs-candidate run comparison).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 through ADR-010:** (Modular monolith, async SQLAlchemy, repository pattern, zero raw secrets, decoupled `AgentAdapter` / `ToolHandler`, validated `ScenarioSpec`, and eager-loaded `TraceEvent` persistence).
* **ADR-011 (Deterministic Tool-Boundary Fault Interception):** Implemented `FaultInjector.wrap()` around `ToolHandler` with per-tool invocation counters (`trigger_on_call`) so transient and persistent faults (`HTTP_429_RATE_LIMIT`, `TIMEOUT`, `MALFORMED_JSON`, `EMPTY_RESPONSE`, `CONTRADICTORY_DATA`, `TOOL_UNAVAILABLE`) are injected deterministically and recorded in `run_metadata["injected_faults"]`.

## 3. Verified Test Coverage
* `tests/test_health.py` (2 passed)
* `tests/test_db.py` (3 passed)
* `tests/test_workspace.py` (4 passed)
* `tests/test_adapters.py` (5 passed)
* `tests/test_scenarios.py` (4 passed)
* `tests/test_execution.py` (4 passed)
* `tests/test_faults.py` (3 passed: baseline vs fault_injected comparison, transient call #1 fault vs call #2 recovery, payload corruption variants)
* Static analysis: Ruff (clean), Mypy strict (clean, 38 files).

## 4. Known Limitations
* Execution runs and fault events are recorded, but automated assertion checking, reliability scoring, and baseline-vs-fault run comparison require Phase 8 (`EvaluationEngine`).