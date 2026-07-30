# Implementation Strategy

## Current State

Context Doctor has deterministic unit and functional coverage for the existing workflows, route contracts, prompt/result contracts, async all-rules behavior, and history failure isolation. This is enough preparation to continue Phase 4 API and flow refactoring without adding more test infrastructure first.

## Source Of Truth

- `TODO` - active roadmap items.
- `TEST_PLAN.md` - current automated and deferred test coverage.
- `AGENTS.md` - repository commands, constraints, and runtime notes.
- `src/context_doctor/fastapi_app.py` and `src/context_doctor/routers/*` - HTTP entrypoints and route wiring.
- `src/context_doctor/logic.py` - flow dispatch and required-input validation.
- `src/context_doctor/context_store.py` - context ingestion and normalization.
- `src/context_doctor/task_manager.py` - async all-rules orchestration, cancellation, and partial results.
- `src/context_doctor/flows/` - prompt construction and result shaping for each analysis workflow.
- `src/context_doctor/services/history_service.py` and `src/context_doctor/database/*` - history persistence and failure isolation.
- `src/context_doctor/templates/*` - current browser UI contracts.

## Working Constraints

- Run commands from the repository root.
- Test with `uv run pytest`.
- Lint with `uv run ruff check .`.
- Keep LLM-backed calls mocked in automated tests.
- Avoid editing `src/.venv/`.

## Phase 1: Build The Test Foundation - completed

- Needed: reusable deterministic fixtures and mocks for uploaded context, SQL dialect, generated rules, structured LLM responses, history boundaries, and task boundaries.
- Implemented: shared fixtures in `tests/conftest.py`, plus unit tests under `tests/unit` and route/functional tests under `tests/functional`.
- Needed: baseline coverage before refactors.
- Implemented: context ingestion, prompt construction, result formatting, logic dispatch, task lifecycle, route contracts, workflow smoke tests, and history failure isolation.

## Phase 2: Harden Async All-Rules Analysis And Validation - completed

- Needed: stable async task states and polling contracts.
- Implemented: pending/running/completed/failed/cancelled state tests, cancellation checks, partial-result retention, `completed_rules`, and `next_index` coverage.
- Needed: stable validation behavior before broader route work.
- Implemented: missing upload, malformed schema, empty rules, blank dialect, missing flow inputs, unknown flow, and visible error rendering tests.
- Needed: non-critical history behavior.
- Implemented: success, failure, cancellation, progress, and history-write failure tests with deterministic mocks.

## Phase 3: Lock Down Prompt And Result Contracts - completed

- Needed: stable prompt variables for all LLM-backed flows.
- Implemented: mocked parser tests for rule analysis, question analysis, and rule generation prompt construction.
- Needed: stable result rows for UI and history rendering.
- Implemented: row ordering, summary placement, generated-rule ordering, empty-result handling, and HTML escaping tests.
- Needed: functional workflow coverage for existing flows.
- Implemented: FastAPI form-submission smoke tests for one rule analysis, all rules analysis, rule generation, and question analysis with structured LLM fakes.

## Phase 4: Refactor API Routing And Flow Layout - completed

- Needed: behavior-preserving route split.
- Implemented: routers under `src/context_doctor/routers`, with legacy browser paths and `/api` aliases covered by tests.
- Implemented: synchronous flows reject `None`, an empty string, or an empty list with a flow-specific error; the route renders that error with empty result/context fields and records a best-effort history failure.
- Implemented: analysis flows live in the dedicated `context_doctor.flows` package, and internal callers and tests use the new module paths.
- Deferred: route single-rule analysis through the task manager only after choosing the async API shape; this changes the browser/API contract rather than the completed route-layout refactor.
- Constraint: do not remove legacy `/run` or `/tasks/*` paths until replacement browser behavior is manually re-verified or covered by browser automation.

## Phase 5: Rework Context Caching And Persistence - completed

- Implemented: `ContextService`, persistent repository/storage, stable `context_id`, explicit create/replace, retrieval/touch, deletion/expiry, history traceability, UI/API reuse controls, and immutable async snapshots.

## Phase 6: Extract Frontend JavaScript - completed

- Implemented: package static assets, FastAPI mounting, behavior-free template hooks, extracted flow/polling/paging/copy behavior, and lightweight Node tests for pure helpers. The visual design and endpoint contracts are preserved.

## Phase 7: Agentic Tooling And SQL-Dialect Documentation Checks - completed

- Decision: prefer explicit, observable tools over an unconstrained autonomous prompt loop.
- Implemented: structured official SQL-dialect documentation validation exposed as an opt-in API tool, with network-mocked unit tests.

## Recommended Next Move

All roadmap phases are complete. Preserve the compatibility routes while gathering usage data; future agent orchestration can consume the structured dialect tool without changing deterministic analysis or silently introducing network access.
