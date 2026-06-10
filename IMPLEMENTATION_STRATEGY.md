# Implementation Strategy

## Executive summary

The repository is in a good place for a disciplined follow-up pass: the current code paths are understandable, the major product workflows are already present, and the highest-value work now is to harden behavior before reshaping architecture. The best order is: build the test foundation first, then stabilize the async all-rules path, then tighten validation and response contracts, and only after that start larger refactors such as API routing, context persistence, and frontend JS extraction.

This document is meant to be durable: use it as the standing reference for what to do next, what to avoid starting too early, and how to verify progress without guessing.

## Source of truth

Use these files as the canonical inputs for future implementation work:

- `TODO` — roadmap source referenced in prior analysis.
- `TEST_PLAN.md` — current testing strategy and manual verification checklist.
- `AGENTS.md` — repository constraints, command locations, runtime notes, and workflow boundaries.
- `src/context_doctor/fastapi_app.py` — HTTP entrypoints and current request/response wiring.
- `src/context_doctor/logic.py` — flow dispatch and required input validation.
- `src/context_doctor/context_store.py` — context ingestion and normalization.
- `src/context_doctor/task_manager.py` — async all-rules orchestration, cancellation, and partial-result handling.
- `src/context_doctor/rule_analysis_flow.py`, `src/context_doctor/question_analysis_flow.py`, `src/context_doctor/rule_generation_flow.py` — prompt construction and result shaping.
- `src/context_doctor/services/history_service.py` and `src/context_doctor/database/*` — history persistence and failure isolation.
- `src/context_doctor/templates/index.html`, `src/context_doctor/templates/history.html`, `src/context_doctor/templates/history_detail.html` — current UI surfaces and data contracts.

## Working constraints

Follow the repo-specific guidance from `AGENTS.md`:

- Run `uv` commands from the repository root.
- Use `uv run ruff check .` for linting.
- Use `uv run ruff format .` for formatting.
- Automated tests are configured under `tests`; run `uv run pytest` and `uv run ruff check .` from the repository root before handoff.
- Keep LLM-backed calls mocked in tests; the suite must not require real API credentials or OpenAI-compatible traffic.
- The dev server is started from the repository root with `./start.sh`.
- Avoid editing `src/.venv/`.

## Priority order

### Phase 1: Build the test foundation

**Status:** complete for the current stabilization pass. The project now has API, workflow-boundary, prompt-construction, formatting, context-ingestion, logic-dispatch, and async task-manager coverage in `tests`. The first test pass also included small production-file adjustments in `src/context_doctor/database/models.py`, `src/context_doctor/logic.py`, and `pyproject.toml`; keep those in mind when reviewing history because they support the testable contracts now in place.

**Why this comes first:** the codebase already has multiple flows, async task behavior, and non-critical failure handling. A broad test scaffold will make every later refactor safer and will expose current contracts before they drift.

**Completed tasks**

1. Added reusable fixtures for uploaded context, SQL dialects, generated rules, and parsed LLM responses, with parameterized invalid schema and rules cases.
2. Added unit coverage for schema normalization, rule splitting, prompt construction, result formatting, task-state transitions, cancellation checks, and history failures remaining non-critical.
3. Added API-level checks for `/`, `/history`, history detail/delete/stat endpoints, `POST /run`, `GET /tasks/{task_id}`, and `POST /tasks/{task_id}/cancel`.
4. Added workflow-boundary tests for `rule_analysis`, `question_analysis`, `rule_generation`, and `all_rules_analysis` without live LLM calls.

**Acceptance criteria**

- Tests run without requiring real `BASE_URL`, `OPENAI_API_KEY`, or `OPENAI_MODEL`.
- The test suite documents local setup and manual verification in `TEST_PLAN.md`.
- Failures in history persistence do not break successful analysis outcomes.
- The async task lifecycle can be exercised deterministically.

**Verification**

- From the repository root: `uv run ruff check .`
- From the repository root: `uv run pytest`
- Manual checks from `TEST_PLAN.md`: `/`, `/history`, all four flows, async polling, cancellation, partial results.

### Phase 2: Harden async all-rules analysis and validation

**Status:** automated coverage is in place for the current task lifecycle, cancellation, partial results, request validation, and non-critical history boundaries. Remaining work is production hardening and manual browser verification.

**Why now:** `all_rules_analysis` is the most stateful path. It combines thread execution, cancellation, partial-page delivery, and history side effects, so it should be stabilized before broader refactors.

**Concrete first tasks**

1. Verify task-state transitions in `TaskManager` for pending, running, completed, failed, and cancelled.
2. Lock in cancellation checks, partial-result collection, and `next_index` behavior.
3. Tighten user-facing validation for missing uploads, empty rules, missing dialects, malformed schemas, and unknown flows.
4. Confirm history writes stay non-critical in both success and failure paths.

**Acceptance criteria**

- Async progress updates remain stable under cancellation and failure.
- Partial results are preserved and reported predictably.
- Validation errors are clear and do not leak internal exceptions.

**Verification**

- `uv run ruff check .`
- Manual async checks from `TEST_PLAN.md`, especially polling and cancellation.

### Phase 3: Lock down prompt/result contracts

**Status:** complete for the current automated test pass. Prompt construction, result formatting, flow dispatch, required inputs, and optional rule-generation question behavior are covered.

**Why now:** prompt inputs and output formatting are core compatibility boundaries. Once they are tested, later changes can be made without breaking the UI or history renderers.

**Concrete first tasks**

1. Cover prompt construction in all three analysis flows with mocked parsed responses.
2. Cover result formatting helpers and generated-rule ordering.
3. Confirm `logic.run_analysis()` dispatch and required-input behavior.

**Acceptance criteria**

- Prompt variables map consistently to the expected flow inputs.
- Result tables, summaries, and empty-list cases render predictably.
- `rule_generation` preserves the optional-question behavior.

**Verification**

- API tests for `/run`.
- Manual smoke tests for all synchronous flows.

### Phase 4: Refactor API routing and flow layout

**Why after tests:** splitting routers and moving flow modules is a structural change with broad import impact. It is much safer once the current contracts are covered.

**Concrete first tasks**

1. Move API routes into routers and plan the `/api` split.
2. Move analysis flows into a dedicated flows folder.
3. Update imports and keep existing behavior unchanged during the transition.

**Acceptance criteria**

- Existing endpoints and workflow behavior remain intact.
- Imports are clearer and responsibilities are easier to navigate.

**Verification**

- Run the API tests and manual UI checks.
- Confirm `/`, `/history`, `/run`, and task polling still work.

### Phase 5: Rework context caching and persistence

**Why this is high risk:** this touches ingestion, validation, persistence, and async task behavior all at once. It should not start until tests and flow contracts are stable.

**Concrete first tasks**

1. Replace `ContextStore` with a `ContextService` in `src/context_doctor/services/context_service.py`.
2. Keep `AnalysisContext` colocated with the service layer until the final shape is clear.
3. Introduce repository/storage abstractions only when persistence is actually being added.
4. Preserve immutable `AnalysisContext` snapshots for async tasks.

**Acceptance criteria**

- Upload ingestion, validation, normalization, and persistence orchestration are clearly separated.
- A `context_id` is returned after upload when persistence is enabled.
- Raw schema JSON, normalized schema description, rules, dialect, filenames, and timestamps are persisted.
- History entries can store `context_id`.
- Create-vs-replace semantics, deletion/expiry, and UI reuse/new-context controls are defined before implementation.

**Do not start with**

- Database schema changes without a confirmed persistence contract.
- UI controls for reuse/new context before the backend data model is fixed.
- Async task wiring changes before context snapshots are immutable.

**Verification**

- Add tests first for the current store behavior, then migrate to service/repository tests.
- Validate that existing analysis flows still receive complete context objects.

### Phase 6: Extract frontend JavaScript

**Why later:** this is mostly a maintainability upgrade. It should follow backend stabilization so the DOM/state contracts are known and stable.

**Concrete first tasks**

1. Create `src/context_doctor/static/index.js`.
2. Move inline JS into modules/functions and keep templates focused on markup and data attributes.
3. Preserve `/run`, `/tasks/{task_id}`, cancellation, polling, and partial-result rendering.
4. Add lightweight JS unit-test scaffolding for testable DOM/state helpers.

**Acceptance criteria**

- No visual redesign is introduced.
- The current frontend behavior remains intact.
- DOM helpers are testable in isolation.

**Verification**

- Manual UI checks for the main page, async polling, cancellation, and history pages.

### Phase 7: Explore agentic tooling and SQL-dialect documentation checks

**Why last:** these are exploratory capabilities, not stabilization work. They should be deferred until the core product is dependable.

**Concrete first tasks**

1. Define the actual agentic behavior the product should support.
2. Add a tool or validation path that can check SQL dialect documentation validity/currentness.
3. Decide what belongs in-product versus in supporting ops tooling.

**Acceptance criteria**

- The exploration is scoped to a concrete user problem.
- The capability has clear input/output boundaries and a test plan.

**Do not start with**

- Prompt rewrites without a product decision.
- New orchestration layers without a target workflow.

## Risk and dependency matrix

| Area | Dependency | Main risk | Mitigation |
| --- | --- | --- | --- |
| Testing foundation | None, but depends on understanding current flows | Tests may encode unstable behavior if written too late | Write tests before large refactors and use current code paths as the reference |
| Async all-rules hardening | Test fixtures and task-manager coverage | Cancellation and partial-result regressions | Add deterministic mocks and verify `next_index`, status transitions, and partial pages |
| Prompt/result contracts | LLM mocks and format helpers | UI/history output drift | Snapshot the contract with unit and API tests |
| API/flow refactor | Stable tests and prompt contracts | Import churn across app entrypoints | Keep behavior unchanged while moving structure |
| Context persistence refactor | Stable tests, immutable context snapshots, clarified history model | High coupling across upload, async tasks, and history | Defer until contracts are fixed; introduce repository abstractions deliberately |
| Frontend JS extraction | Stable endpoint contracts | Breaking form submission/polling/cancellation behavior | Keep markup/data attributes stable and move logic incrementally |
| Agentic tooling exploration | Product decision and architectural clarity | Premature complexity | Treat as exploratory and last in sequence |

## Recommended next move

The test foundation and prompt/result contract coverage are now in place. The next recommended move is to finish Phase 2 production hardening and the remaining manual async checks in `TEST_PLAN.md`, then proceed to the Phase 4 API/flow layout work. Avoid beginning high-risk persistence, frontend JavaScript extraction, or exploratory tooling until those async checks are complete.
