# AGENTS.md

## Repo Shape

- Python package, `pyproject.toml`, `uv.lock`, `README.md`, templates, prompts, and examples live under `src/`; run uv/Uvicorn commands from `src/` unless noted.
- FastAPI entrypoint is `context_doctor.fastapi_app:app`.
- Templates, prompts, guidelines, and examples are loaded package-relatively with `importlib.resources`.
- `src/.venv/` may exist in the repo checkout; do not inspect or edit it as project source.

## Commands

- Install dependencies: from `src/`, run `uv sync`.
- Dev server: from `src/`, run `../start.sh`; it starts Uvicorn on `localhost:8008` with reload for Python, prompt YAML, and templates. Override with `HOST` or `PORT` if needed.
- Direct local server: from `src/`, run `uv run python -m uvicorn context_doctor.fastapi_app:app --host localhost --port 8008`.
- Production-style local server: from `src/`, run `uv run python -m uvicorn context_doctor.fastapi_app:app --host 0.0.0.0 --port 8000`.
- Docker build from repo root: `docker build -t context-doctor .`; the Dockerfile copies `src/pyproject.toml`, `src/README.md`, and `src/context_doctor`, then runs `pip install .`.
- Lint from `src/`: `uv run ruff check .`. Format with `uv run ruff format .`.
- No automated test suite is configured. Use `TEST_PLAN.md` plus manual checks for `/`, `/history`, all four flows, async polling, cancellation, and partial results.

## Runtime Requirements

- Required env vars for LLM-backed flows: `BASE_URL`, `OPENAI_TOKEN`, `OPENAI_MODEL`.
- Optional env vars: `MAX_CONCURRENT_RULE_ANALYSES` defaults to `1`; `DATABASE_URL` overrides SQLite; `CONTEXT_DOCTOR_DB_PATH` overrides the default SQLite path before `DATABASE_URL` is built.
- Request context is supplied by uploading schema JSON, rules text, and SQL dialect on every `/run` request.

## Execution Flow

- Browser submits uploaded context and flow inputs to `POST /run` in `fastapi_app.py`; synchronous flows route through `logic.run_analysis()`.
- `rule_analysis` calls `rule_analysis_flow.analyze_rule_pipeline()` for comparison plus guideline validation.
- `question_analysis` calls `question_analysis_flow.filter_and_compare_question()` and does not return guideline text.
- `rule_generation` calls `rule_generation_flow.generate_rule_pipeline()` with optional question text.
- `all_rules_analysis` is special: `fastapi_app.py` starts `TaskManager.start_all_rules_analysis()`, the frontend polls `GET /tasks/{task_id}`, and cancellation uses `POST /tasks/{task_id}/cancel`.

## Gotchas

- LLM prompt/guideline loading happens at module import using package-relative resources.
- OpenAI-compatible LLM calls use structured Pydantic parsing and `temperature=0`; update the relevant Pydantic response model when changing prompt output shape.
- All-rules analysis splits rules with regex `(^|\n)Rule #`; malformed rule headings can collapse or skip rules.
- `MAX_CONCURRENT_RULE_ANALYSES` controls LLM fan-out for all-rules analysis; high values multiply external API/LLM load.
- History is non-critical. Preserve the pattern that history init/writes are wrapped in `try`/`except` and never break analysis results.
- SQLite defaults to `context_doctor_history.db` in the current working directory and enables WAL; writes are still serialized.
- When editing `TaskManager`, keep lock scope small, avoid I/O while holding `_lock`, and check cancellation in long-running loops.
- When adding a new analysis flow, update the pipeline module, prompt YAML if needed, `logic.run_analysis()`, `AnalysisParams`, and `templates/index.html` together.
