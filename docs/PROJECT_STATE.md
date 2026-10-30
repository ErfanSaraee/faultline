# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 3 Complete / Entering Phase 4
* **Completed Phases:**
  * Phase 1 (Bootstrap, Typed Configuration, Health Check API, and Test Harness)
  * Phase 2 (PostgreSQL Infrastructure, Async SQLAlchemy 2.x Engine, Alembic Setup, and Readiness Probe)
  * Phase 3 (Core Workspace Domain: `Project` and `AgentConfig`, Repositories, Alembic Migration, and CRUD APIs)
* **Next Immediate Step:** Phase 4 (Framework-Agnostic `AgentAdapter` Contract, `AdapterRegistry`, and `DeterministicMockAgent`).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 (Modular Monolith Layout):** Adopted a `src/faultline` package layout to enforce strict import hygiene and clear module boundaries.
* **ADR-002 (Application Factory Pattern):** Used FastAPI's `create_app()` factory pattern in `faultline.api.app` with lifespan resource cleanup.
* **ADR-003 (Validated Configuration):** Centralized environment configuration in `faultline.core.config.Settings` using `pydantic-settings`.
* **ADR-004 (Async SQLAlchemy 2.x & Naming Conventions):** Standardized on `AsyncEngine` and `async_sessionmaker` with `expire_on_commit=False` and deterministic constraint naming conventions (`POSTGRES_NAMING_CONVENTION`).
* **ADR-005 (Liveness vs. Readiness Separation):** Kept `/api/v1/health` as a lightweight process liveness check while adding `/api/v1/health/ready` to execute a database connectivity probe (`SELECT 1`).
* **ADR-006 (Repository Pattern & Domain Error Mapping):** Isolated SQLAlchemy queries inside `faultline.repositories` and raised framework-independent domain exceptions (`EntityNotFoundError`, `EntityConflictError`) translated to HTTP 404/409 at the FastAPI boundary.
* **ADR-007 (Zero Raw Secrets Guardrail):** Enforced a strict regex validator on `AgentConfigCreate.secret_refs` so only environment variable names (`UPPER_SNAKE_CASE`) are persisted, rejecting raw API keys with HTTP 422.

## 3. Verified Test Coverage
* `tests/test_health.py` (2 passed)
* `tests/test_db.py` (3 passed)
* `tests/test_workspace.py` (4 passed: project CRUD/conflict, 404 handling, versioned agent config lifecycle, raw secret rejection)
* Static analysis: Ruff (clean), Mypy strict (clean, 19 files).

## 4. Known Limitations
* `AgentConfig` records can be stored and versioned in the database, but cannot yet be executed until the `AgentAdapter` runtime interface is introduced in Phase 4.