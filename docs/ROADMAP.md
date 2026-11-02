# FAULTLINE — Engineering Roadmap

This document tracks the incremental implementation phases for FAULTLINE. All 15 MVP phases have been implemented and verified via automated tests, Ruff linting, and strict Mypy type checking.

## Phase Overview

- [x] **Phase 1:** Repository Bootstrap, Typed Configuration, Health API, and Test Harness *(Completed)*
- [x] **Phase 2:** PostgreSQL Infrastructure, Async SQLAlchemy 2.x Engine, and Alembic Migrations *(Completed)*
- [x] **Phase 3:** Core Workspace Domain (`Project`, `AgentConfig`), Repositories, and CRUD APIs *(Completed)*
- [x] **Phase 4:** Framework-Agnostic `AgentAdapter` Contract and `DeterministicMockAgent` *(Completed)*
- [x] **Phase 5:** Versioned `ScenarioDefinition` Schema, Validation, and Persistence *(Completed)*
- [x] **Phase 6:** Baseline Execution Engine and Structured Observable Trace/Event Capture *(Completed)*
- [x] **Phase 7:** Controlled Fault Injection Engine (HTTP 429, Timeouts, Malformed Payloads, Contradictions) *(Completed)*
- [x] **Phase 8:** Evaluation Engine (Task Assertions, Tool Correctness, Latency, Cost, Reliability Scoring) *(Completed)*
- [x] **Phase 9:** Recovery Policy Engine (Bounded Retries, Fallbacks) and Baseline-vs-Recovery Comparison *(Completed)*
- [x] **Phase 10:** Replay Engine (Recorded Replay vs. Live Re-execution) and Execution Diffing *(Completed)*
- [x] **Phase 11:** Evidence-Based Failure Diagnosis (Facts, Rule Classifications, Grounded Hypotheses) *(Completed)*
- [x] **Phase 12:** Regression Test Generation, Human Approval Workflow, and Release Gates *(Completed)*
- [x] **Phase 13:** Real Framework Integration — LangGraph Research Agent Adapter *(Completed)*
- [x] **Phase 14:** Security Hardening, Secret/PII Redaction, and OpenTelemetry Integration *(Completed)*
- [x] **Phase 15:** Developer Workbench UI (React + TypeScript) & End-to-End MVP Verification *(Completed)*