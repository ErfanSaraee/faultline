# FAULTLINE

**Agent Reliability Engineering, Chaos Testing, Replay, Evaluation & Recovery Platform**

FAULTLINE is an engineering workbench designed to systematically test, observe, evaluate, and improve the reliability of AI agents under controlled failure conditions.

Instead of asking whether an agent works when every dependency succeeds, FAULTLINE investigates how an agent behaves when tools fail, retrieval degrades, latencies spike, payloads become malformed, or recovery policies intervene.

## Core Engineering Pillars

1. **Controlled Fault Injection:** Deterministic failure simulation across tools, retrieval layers, and model providers.
2. **Structured Execution Tracing:** Observable step-by-step event capture without relying on hidden chain-of-thought.
3. **Repeatable Evaluation:** Explicit assertions and reliability metrics beyond superficial response checks.
4. **Replay & Comparison:** Clear separation between deterministic recorded replay and live re-execution.
5. **Evidence-Based Diagnostics & Regression Gates:** Grounded failure classification and automated regression suites.

## Current Status

* **Active Phase:** Phase 1 — Repository Bootstrap, Configuration, and Health API.
* See [`docs/ROADMAP.md`](docs/ROADMAP.md) and [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) for architectural decisions and phase tracking.

## Quickstart (Development)

### Prerequisites
* Python 3.12+
* [`uv`](https://docs.astral.sh/uv/) package manager

### Setup & Verification

```bash
# Synchronize virtual environment and dependencies
uv sync

# Run test suite
uv run pytest

# Run linter and type checker
uv run ruff check .
uv run mypy src tests

# Start local API server
uv run uvicorn faultline.api.app:create_app --factory --reload
