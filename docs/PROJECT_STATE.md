# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 11 Complete / Entering Phase 12
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
* **Next Immediate Step:** Phase 12 (Regression Test Generation, Human Review/Approval Workflow, Regression Suite Execution, and Release Gates).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 through ADR-014:** (Modular monolith, async SQLAlchemy, repository pattern, zero raw secrets, decoupled `AgentAdapter` / `ToolHandler`, validated `ScenarioSpec`, eager-loaded trace persistence, `FaultInjector`, `EvaluationEngine`, `RecoveryToolInterceptor`, and `ReplayEngine`).
* **ADR-015 (Four-Tier Evidence-Grounded Diagnosis):** Implemented `DiagnosisEngine` and `DiagnosisReport` with strict structural separation between `observed_facts` (extracted directly from trace/evaluation records), `rule_classifications` (deterministic failure taxonomy citing fact IDs), `model_hypotheses` (locked with `verification_status='unconfirmed_hypothesis'`), and `human_confirmed_cause` (populated only via explicit human review endpoint).

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
* `tests/test_diagnosis.py` (3 passed: 4-tier evidence separation & human confirmation, superficial completion diagnosis, 404 lookup)
* Static analysis: Ruff (clean), Mypy strict (clean, 57 files).

## 4. Known Limitations
* Diagnosed and human-confirmed failures cannot yet be locked into an automated regression suite or used as a release gate; this is implemented in Phase 12.