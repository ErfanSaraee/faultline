# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 1 Complete
* **Completed Phases:**
  * Phase 1 (Bootstrap, Typed Configuration, Health Check API, and Test Harness)
* **Next Immediate Step:** Phase 2 (PostgreSQL Infrastructure, Async SQLAlchemy 2.x, and Alembic Migrations).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 (Modular Monolith Layout):** Adopted a `src/faultline` package layout to enforce strict import hygiene and clear module boundaries (`core`, `api`, and subsequent domain modules) within a single deployable backend unit.
* **ADR-002 (Application Factory Pattern):** Used FastAPI's `create_app()` factory pattern in `faultline.api.app` instead of a reliance on module-level global state. This enables isolated app instances with custom settings per test case.
* **ADR-003 (Validated Configuration):** Centralized environment configuration in `faultline.core.config.Settings` using `pydantic-settings` with the `FAULTLINE_` prefix and strict environment validation.

## 3. Verified Test Coverage
* `tests/test_health.py`:
  * `test_health_endpoint_returns_expected_contract` (PASSED)
  * `test_default_settings_validation` (PASSED)
* Static analysis: Ruff (clean), Mypy strict (clean, 6 files).

## 4. Known Limitations
* No database persistence is connected in Phase 1; `/api/v1/health` reports service liveness and configuration metadata only. Database readiness will be added in Phase 2.