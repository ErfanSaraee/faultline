# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 6 Complete / Entering Phase 7
* **Completed Phases:**
  * Phase 1 (Bootstrap, Typed Configuration, Health Check API, and Test Harness)
  * Phase 2 (PostgreSQL Infrastructure, Async SQLAlchemy 2.x Engine, Alembic Setup, and Readiness Probe)
  * Phase 3 (Core Workspace Domain: `Project` and `AgentConfig`, Repositories, and CRUD APIs)
  * Phase 4 (Framework-Agnostic `AgentAdapter` Contract, `ToolHandler`, `DeterministicMockAgent`, and `AdapterRegistry`)
  * Phase 5 (Versioned `ScenarioDefinition` Schema, Safety/Criteria Guardrails, Repository, and CRUD APIs)
  * Phase 6 (Baseline Execution Engine, Fixture-Backed `ToolHandler`, `ExecutionRun` and `TraceEvent` Persistence & APIs)
* **Next Immediate Step:** Phase 7 (Controlled Fault Injection Engine: `FaultInjector`, transient/persistent tool fault interception, and `"fault_injected"` execution mode).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 through ADR-009:** (Modular monolith, async SQLAlchemy, repository pattern, zero raw secrets, decoupled `AgentAdapter` / `ToolHandler`, and validated `ScenarioSpec`).
* **ADR-010 (Durable Execution Runs & Eager-Loaded Trace Events):** Persisted each run in `execution_runs` and its step-by-step observable events in `trace_events` ordered by `step_index`. Used `selectinload(ExecutionRun.trace_events)` in `ExecutionRunRepository` to prevent async lazy-loading errors during API serialization.

## 3. Verified Test Coverage
* `tests/test_health.py` (2 passed)
* `tests/test_db.py` (3 passed)
* `tests/test_workspace.py` (4 passed)
* `tests/test_adapters.py` (5 passed)
* `tests/test_scenarios.py` (4 passed)
* `tests/test_execution.py` (4 passed: baseline run & trace capture, max_steps enforcement, unregistered adapter 422, missing run 404)
* Static analysis: Ruff (clean), Mypy strict (clean, 35 files).

## 4. Known Limitations
* Phase 6 executes runs strictly in `"baseline"` mode using healthy tool fixtures. Controlled fault injection (`fault_rules`) is activated in Phase 7.