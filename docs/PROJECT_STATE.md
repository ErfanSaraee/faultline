# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 10 Complete / Entering Phase 11
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
* **Next Immediate Step:** Phase 11 (Evidence-Based Failure Diagnosis: explicit separation of Observed Facts, Rule-Based Classifications, Model Hypotheses, and Human-Confirmed Causes).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 through ADR-013:** (Modular monolith, async SQLAlchemy, repository pattern, zero raw secrets, decoupled `AgentAdapter` / `ToolHandler`, validated `ScenarioSpec`, eager-loaded trace persistence, `FaultInjector`, `EvaluationEngine`, and `RecoveryToolInterceptor`).
* **ADR-014 (Explicit Determinism Boundaries in Replay & Step Diffing):** Distinguished `recorded_replay` (reconstructing recorded trace steps or feeding recorded `ToolCallResult` queues via `RecordedToolHandler`) from `live_replay` (reinvoking the adapter and dependencies live). Recorded explicit `reproducibility_guarantee` metadata and implemented step-level `StepDeviation` diffing.

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
* `tests/test_replay.py` (3 passed: deterministic recorded trace replay, recorded tool replay with agent override, live replay with recovery & standalone diff)
* Static analysis: Ruff (clean), Mypy strict (clean, 51 files).

## 4. Known Limitations
* Failed or degraded runs can be evaluated, replayed, and diffed, but automated root-cause diagnosis grounded in verifiable evidence requires Phase 11 (`DiagnosisEngine`).