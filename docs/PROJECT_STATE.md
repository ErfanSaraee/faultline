# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 2 Complete / Entering Phase 3
* **Completed Phases:**
  * Phase 1 (Bootstrap, Typed Configuration, Health Check API, and Test Harness)
  * Phase 2 (PostgreSQL Infrastructure, Async SQLAlchemy 2.x Engine, Alembic Setup, and Readiness Probe)
* **Next Immediate Step:** Phase 3 (Core Workspace Domain: `Project` and `AgentConfig`, Repositories, Alembic Migration, and CRUD APIs).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 (Modular Monolith Layout):** Adopted a `src/faultline` package layout to enforce strict import hygiene and clear module boundaries.
* **ADR-002 (Application Factory Pattern):** Used FastAPI's `create_app()` factory pattern in `faultline.api.app` with lifespan resource cleanup.
* **ADR-003 (Validated Configuration):** Centralized environment configuration in `faultline.core.config.Settings` using `pydantic-settings`.
* **ADR-004 (Async SQLAlchemy 2.x & Naming Conventions):** Standardized on `AsyncEngine` and `async_sessionmaker` with `expire_on_commit=False` and deterministic constraint naming conventions (`POSTGRES_NAMING_CONVENTION`) to ensure reliable Alembic migrations.
* **ADR-005 (Liveness vs. Readiness Separation):** Kept `/api/v1/health` as a lightweight process liveness check while adding `/api/v1/health/ready` to execute a database connectivity probe (`SELECT 1`), returning HTTP 503 when degraded.

## 3. Verified Test Coverage
* `tests/test_health.py` (2 passed)
* `tests/test_db.py` (3 passed: ORM roundtrip, readiness 200 OK, readiness 503 degraded)

## 4. Known Limitations
* No domain tables are migrated yet; `Project` and `AgentConfig` tables and migrations are introduced in Phase 3.