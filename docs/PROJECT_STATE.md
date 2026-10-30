# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 5 Complete / Entering Phase 6
* **Completed Phases:**
  * Phase 1 (Bootstrap, Typed Configuration, Health Check API, and Test Harness)
  * Phase 2 (PostgreSQL Infrastructure, Async SQLAlchemy 2.x Engine, Alembic Setup, and Readiness Probe)
  * Phase 3 (Core Workspace Domain: `Project` and `AgentConfig`, Repositories, and CRUD APIs)
  * Phase 4 (Framework-Agnostic `AgentAdapter` Contract, `ToolHandler`, `DeterministicMockAgent`, and `AdapterRegistry`)
  * Phase 5 (Versioned `ScenarioDefinition` Schema, Safety/Criteria Guardrails, Repository, and CRUD APIs)
* **Next Immediate Step:** Phase 6 (Baseline Execution Engine, Fixture-Backed Tool Handler, and Structured `ExecutionRun` / `TraceEvent` Persistence).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 through ADR-008:** (Modular monolith, async SQLAlchemy, repository pattern, zero raw secrets guardrail, and decoupled `AgentAdapter` / `ToolHandler`).
* **ADR-009 (Versioned Scenario Specification & Safe-by-Default Validation):** Modeled `ScenarioDefinition` with a strongly validated `ScenarioSpec` payload (fixtures, fault rules, evaluation criteria, safety constraints). Enforced `allow_live_external_actions=False` and disjoint expected/forbidden tool sets at the Pydantic boundary.

## 3. Verified Test Coverage
* `tests/test_health.py` (2 passed)
* `tests/test_db.py` (3 passed)
* `tests/test_workspace.py` (4 passed)
* `tests/test_adapters.py` (5 passed)
* `tests/test_scenarios.py` (4 passed: versioned scenario lifecycle, unsafe external action rejection, contradictory tool criteria rejection, 404 lookup)
* Static analysis: Ruff (clean), Mypy strict (clean, 29 files).

## 4. Known Limitations
* Scenarios and agent configurations are persisted in PostgreSQL, but executing a scenario against an agent and storing trace events requires Phase 6 (`BaselineExecutionEngine`).