# FAULTLINE — Project State & Architecture Log

## 1. Current Implementation Status
* **Current Phase:** Phase 15 Complete (MVP v0.1.0 Release Ready)
* **Completed Phases:** Phases 1 through 15 (All core reliability engineering engines, LangGraph integration, security/redaction, OpenTelemetry observability, React + TypeScript Workbench UI, and 15-step E2E workflow verification complete).

## 2. Architectural Decisions Record (ADR Summary)
* **ADR-001 (Modular Monolith Layout):** Adopted a `src/faultline` package layout with strict module boundaries (`core`, `db`, `domain`, `schemas`, `repositories`, `adapters`, `execution`, `faults`, `evaluation`, `replay`, `diagnosis`, `regression`, `security`, `observability`, `api`).
* **ADR-002 through ADR-009:** Application factory pattern, validated settings, async SQLAlchemy 2.x with deterministic naming conventions, liveness/readiness separation, repository pattern, zero raw secrets guardrail (`UPPER_SNAKE_CASE` env references only), framework-agnostic `AgentAdapter` / `ToolHandler`, and safe-by-default `ScenarioSpec`.
* **ADR-010 through ADR-016:** Eager-loaded `ExecutionRun` / `TraceEvent` persistence, tool-boundary `FaultInjector`, deterministic `EvaluationEngine` catching superficial completions, `RecoveryToolInterceptor` with trace expansion, `ReplayEngine` separating `recorded_replay` from `live_replay` with step diffing, 4-tier `DiagnosisEngine` (`ObservedFact`, `RuleClassification`, `ModelHypothesis`, `HumanConfirmedCause`), and human-gated `RegressionSuiteEngine` with Release Gates.
* **ADR-017 & ADR-018:** Real `LangGraphResearchAdapter` (`StateGraph`) routed through `ToolHandler`, recursive secret/PII/CoT redaction before database persistence, and OpenTelemetry span/metric emission.
* **ADR-019 (Typed React Workbench & 15-Step End-to-End Verification):** Built a React + TypeScript Developer Workbench consuming live backend APIs without fabricated statistics, verified by `tests/test_e2e_mvp_workflow.py`.

## 3. Verified Test Coverage (46 Passed across 14 Test Suites)
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
* `tests/test_diagnosis.py` (3 passed)
* `tests/test_regression.py` (3 passed)
* `tests/test_langgraph_adapter.py` (2 passed)
* `tests/test_security_and_observability.py` (2 passed)
* `tests/test_e2e_mvp_workflow.py` (1 comprehensive 15-step E2E workflow test passed)
* Static analysis: Ruff (clean), Mypy strict (clean, 72 source files), Frontend TypeScript + Vite build (clean).