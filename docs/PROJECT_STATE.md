# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 4 Complete / Entering Phase 5
* **Completed Phases:**
  * Phase 1 (Bootstrap, Typed Configuration, Health Check API, and Test Harness)
  * Phase 2 (PostgreSQL Infrastructure, Async SQLAlchemy 2.x Engine, Alembic Setup, and Readiness Probe)
  * Phase 3 (Core Workspace Domain: `Project` and `AgentConfig`, Repositories, and CRUD APIs)
  * Phase 4 (Framework-Agnostic `AgentAdapter` Contract, `ToolHandler`, `DeterministicMockAgent`, and `AdapterRegistry`)
* **Next Immediate Step:** Phase 5 (Versioned `ScenarioDefinition` Schema, Validation, and Persistence).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 through ADR-007:** (Maintained modular monolith, async SQLAlchemy, repository pattern, and strict validation guardrails).
* **ADR-008 (Framework-Agnostic Adapter & Decoupled ToolHandler):** Defined `AgentAdapter` abstract contract so execution engines can invoke any agent framework uniformly. Separated `ToolHandler` to allow intercepting tool requests for deterministic runs and future fault injection without modifying agent internals.

## 3. Verified Test Coverage
* `tests/test_health.py` (2 passed)
* `tests/test_db.py` (3 passed)
* `tests/test_workspace.py` (4 passed)
* `tests/test_adapters.py` (5 passed: multi-tool mock execution, default error halting, fallback handling, max_steps guardrail, registry resolution)
* Static analysis: Ruff (clean), Mypy strict (clean, 25 files).

## 4. Known Limitations
* Agent configurations and adapters are implemented independently; binding them to executable test scenarios will be addressed in upcoming phases.