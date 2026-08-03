# TEST_PLAN.md

## Automated Test Status

- Unit suite - completed: needed low-level coverage for context parsing, prompt construction, result formatting, dispatch, async task state, and non-critical history behavior; implemented under `tests/unit`.
- Functional suite - completed: needed app-boundary coverage for existing workflows and HTTP route contracts; implemented under `tests/functional` with FastAPI `TestClient` and deterministic LLM/task/history fakes.
- Verification - completed: `uv run pytest` and `uv run ruff check .` are the handoff gates.
- Live dependencies - completed: tests do not require `BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, a live LLM endpoint, or a live web server.

## Completed Test Suites

### `tests/unit` - completed

- Context ingestion - needed schema/rules/dialect validation; implemented `ContextStore.from_uploads` tests for valid JSON, invalid JSON, non-object JSON, missing schema shape, non-UTF-8 bytes, empty rules, blank dialect, filenames, raw schema, and normalized descriptions.
- Rule splitting - needed deterministic all-rules boundaries; implemented `TaskManager._split_rules` tests for valid headings, malformed headings, leading text, single-rule text, empty input, and whitespace input.
- Prompt contracts - needed stable prompt inputs for LLM-backed flows; implemented mocked `parse_response` tests for rule analysis, question analysis, and rule generation prompts.
- Result contracts - needed stable UI/history row data; implemented formatting tests for category order, joined lists, nested comparison fields, generated-rule summary placement, HTML escaping, and newline handling.
- Flow dispatch - needed stable `logic.run_analysis()` behavior; implemented dispatch tests for all four flows plus required-input, unknown-flow, and empty-response errors.
- Async task manager - needed stable all-rules lifecycle behavior; implemented pending/running/completed/failed/cancelled, cancellation, partial-result, `next_index`, empty-result, and non-critical history failure tests.

### `tests/functional` - completed

- Main app routes - needed browser-facing route contracts; implemented `GET /`, `/history`, `/history/{entry_id}`, `/api/history/stats`, and `DELETE /api/history/{entry_id}` tests.
- Run endpoint - needed form submission coverage; implemented `POST /run` tests for synchronous workflows, all-rules task startup, validation errors, workflow and empty-response errors, and non-critical history logging failures.
- API aliases - needed migration-safe endpoint coverage; implemented `/api/run`, `/api/tasks/{task_id}`, and `/api/tasks/{task_id}/cancel` success and 404 checks while legacy paths remain active.
- Workflow smoke tests - needed functional coverage for existing Context Doctor workflows; implemented real FastAPI form submissions with deterministic structured LLM fakes for `rule_analysis`, `question_analysis`, `rule_generation`, and `all_rules_analysis`.
- Task polling/cancellation - needed async client contract coverage; implemented incremental payload, `next_index`, context field, cancellation, and unknown-task checks.

## Deferred Checks

- Browser integration - completed: Playwright drives the real FastAPI form through all four flow selections, multipart schema/rules upload, conditional rule/question/problem fields, and all-rules task polling to completed DOM state. It also verifies that the cached context returned after upload can run a new rule, a new question, a new generation problem, or a complete all-rules rerun without reselecting either file.
- Live LLM smoke tests - deferred: run only deliberately with real credentials.
- Production-style runtime checks - deferred: direct Uvicorn, `./start.sh`, Docker build/run, and environment-specific SQLite path behavior remain manual.

## Local Commands

- Install dependencies: `uv sync`.
- Install the local browser runtime once: `uv run playwright install chromium`.
- Run tests: `uv run pytest`.
- Run lint: `uv run ruff check .`.
- Format when needed: `uv run ruff format .`.

## Phase 5-7 Coverage

- Context lifecycle: immutable snapshots, create/replace identity rules, reconstruction,
  last-used touches, and API reuse metadata are covered without live services.
- Frontend extraction: Python route tests assert packaged asset wiring; run
  `node --test tests/js/*.test.cjs` for pure paging helper behavior.
- Dialect documentation: supported and unsupported outcomes use a mocked HTTP boundary;
  automated tests never access official documentation sites.
