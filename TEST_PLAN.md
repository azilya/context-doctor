# TEST_PLAN.md

## Current automated status

- Automated tests live under `tests` and run from the repository root with `uv run pytest`.
- The suite is deterministic and does not require `BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, a live LLM endpoint, or a live web server.
- LLM-backed boundaries are mocked or blocked by the shared fixture in `tests/conftest.py`; accidental OpenAI-compatible client creation fails the test.
- Async all-rules tests set `MAX_CONCURRENT_RULE_ANALYSES` low, usually `1`, to keep ordering predictable.
- Current verification target: `uv run pytest` and `uv run ruff check .` from the repository root before handoff.

## Covered fixtures and mocks

- Valid uploaded schema JSON exercises application, table, column, relation, and normalized description handling.
- Invalid schema cases cover missing bytes, malformed JSON, non-object JSON, missing required shape, and non-UTF-8 bytes.
- Rules fixtures cover multiple well-formed `Rule #` headings, empty content, whitespace-only content, malformed headings, leading text, and single-rule input.
- SQL dialect fixtures include `PostgreSQL` plus blank/whitespace boundary checks.
- Uploaded context, SQL dialect, generated-rule, and structured Pydantic LLM responses are shared in fixtures; flow-specific question and problem values stay close to the tests that use them.
- History and task boundaries are mocked so tests assert side effects without persistent database dependence.

## Covered unit foundations

- `ContextStore.from_uploads` and context building: valid JSON, UTF-8 decoding, required schema shape, non-empty rules, required SQL dialect, filenames, raw schema, and normalized schema description.
- `TaskManager._split_rules`: multiple `Rule #` headings, leading text, malformed headings, single-rule input, empty input, and whitespace-only input. Current imperfect splitter behavior is intentionally pinned.
- Prompt construction in rule analysis, question analysis, and rule generation by mocking `parse_response` and asserting prompt variables include rules, schema descriptions, SQL dialect, questions, problems, guidelines, and generated rules.
- Result formatting in rule analysis, question analysis, and rule generation, including category order, joined list fields, nested comparison fields, summaries, and generated-rule summary placement.
- `logic.run_analysis` dispatch for all four flows plus missing required inputs, optional rule-generation question text, and unknown flows.
- `TaskManager` pending/running/completed/failed/cancelled transitions, cancellation checks, partial-result retention, `from_index`/`next_index`, skipped empty analyses, and non-critical history write failures.

## Covered API and workflow checks

- `GET /` renders the main application shell and workflow form.
- `GET /history` covers repository arguments, filters, pagination offset, empty state, statistics, and repository error fallback.
- `GET /history/{entry_id}` covers detail rendering and 404 for missing entries using repository/session mocks.
- `GET /api/history/stats` covers statistics JSON through the repository boundary.
- `DELETE /api/history/{entry_id}` covers success and 404 paths through the repository boundary.
- `POST /run` synchronous flows cover rule analysis, question analysis, and rule generation rendering with mocked workflow execution, preserved form values, uploaded context, and non-critical history completion.
- `POST /run` all-rules flow covers async task startup, polling-state rendering, a valid `AnalysisContext` passed to `TaskManager`, and expected `HistoryService.start_async_execution` payload.
- `GET /tasks/{task_id}` covers incremental payloads, context fields, `next_index`, and 404 for unknown task IDs.
- `POST /tasks/{task_id}/cancel` covers successful cancellation payloads and 404 for unknown task IDs.
- Workflow error handling covers visible errors, preserved form values, and non-critical history failure logging.

## Covered error handling

- Invalid schema JSON, missing schema upload, missing rules upload, empty rules text, and blank SQL dialect render user-visible errors and do not call analysis/task boundaries.
- Missing new rule, missing question, missing problem, and unknown flow fail fast through `logic.run_analysis`; LLM-backed flow helpers are asserted not called.
- LLM parse/workflow failures are simulated without live traffic; the error remains visible, form values are preserved, and history failure logging remains non-critical.
- Sync failure logging and async progress/completion write errors remain non-critical where explicitly exercised; cancellation and failure side effects are asserted through mocked history boundaries.

## Manual or deferred checks

- Live LLM smoke tests remain manual and should be run only deliberately with real credentials.
- Browser-only behavior remains manual: file picker UX, copy buttons, collapsible sections, async polling DOM updates, stop button behavior, pagination controls, and history-detail delete redirect.
- Production-style server and Docker checks remain manual: direct Uvicorn, `./start.sh`, Docker build/run, and environment-specific SQLite path behavior.
- Future refactors should add or adjust tests before changing API routers, context persistence, frontend JavaScript extraction, or prompt output schemas.

## Recommended local setup and commands

- From the repository root, install dependencies with `uv sync`.
- From the repository root, run tests with `uv run pytest`.
- From the repository root, run lint with `uv run ruff check .`.
- Use `uv run ruff format .` only when formatting changes are needed.
- For manual checks, start the dev server from the repository root with `./start.sh` and verify `/`, `/history`, all four workflows, async polling, cancellation, partial results, and history detail/delete behavior.
