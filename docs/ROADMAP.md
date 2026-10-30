# FAULTLINE — Engineering Roadmap

This document tracks the incremental implementation phases for FAULTLINE. No phase is marked complete until its automated tests and verification checks pass.

## Phase Overview

- [x] **Phase 1:** Repository Bootstrap, Typed Configuration, Health API, and Test Harness *(Completed)*
- [x] **Phase 2:** PostgreSQL Infrastructure, Async SQLAlchemy 2.x Engine, and Alembic Migrations *(Completed)*
- [x] **Phase 3:** Core Workspace Domain (`Project`, `AgentConfig`), Repositories, and CRUD APIs *(Completed)*
- [x] **Phase 4:** Framework-Agnostic `AgentAdapter` Contract and `DeterministicMockAgent` *(Completed)*
- [x] **Phase 5:** Versioned `ScenarioDefinition` Schema, Validation, and Persistence *(Completed)*
- [x] **Phase 6:** Baseline Execution Engine and Structured Observable Trace/Event Capture *(Completed)*
- [ ] **Phase 7:** Controlled Fault Injection Engine (HTTP 429, Timeouts, Malformed Payloads, Contradictions) *(In Progress)*
- [ ] **Phase 8:** Evaluation Engine (Task Assertions, Tool Correctness, Latency, Cost, Reliability Scoring)
- [ ] **Phase 9:** Recovery Policy Engine (Bounded Retries, Fallbacks) and Baseline-vs-Recovery Comparison
- [ ] **Phase 10:** Replay Engine (Recorded Replay vs. Live Re-execution) and Execution Diffing
- [ ] **Phase 11:** Evidence-Based Failure Diagnosis (Facts, Rule Classifications, Grounded Hypotheses)
- [ ] **Phase 12:** Regression Test Generation, Human Approval Workflow, and Release Gates
- [ ] **Phase 13:** Real Framework Integration — LangGraph Research Agent Adapter
- [ ] **Phase 14:** Security Hardening, Secret/PII Redaction, and OpenTelemetry Integration
- [ ] **Phase 15:** Developer Workbench UI (React + TypeScript) & End-to-End MVP Verification