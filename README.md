# Context Doctor

Context Doctor is a small FastAPI demo for inspecting text-to-SQL rule context. It can compare a proposed rule against existing rules and schema descriptions, analyze all rules, inspect context relevant to a user question, or suggest a new rule for a described SQL-generation problem.

## Workflows

- One rule analysis: checks a proposed rule for typos, dialect inconsistencies, contradictions, duplications, and guideline violations.
- All rules analysis: analyzes every existing rule asynchronously and streams partial results to the browser.
- Question analysis: finds rules and schema descriptions relevant to a user question, then checks them for conflicts.
- Rule generation: suggests a rule for a described problem and evaluates the suggestion.

## Requirements

- Python 3.12 or newer.
- uv for local development, or Docker for containerized use.
- An OpenAI-compatible endpoint that supports structured `responses.parse` calls.

## Quickstart

The app accepts schema JSON and rules text uploads for every analysis request. Sample files are included in the repository.

```sh
cd src
uv sync
BASE_URL= \
OPENAI_TOKEN= \
OPENAI_MODEL= \
uv run python -m uvicorn context_doctor.fastapi_app:app --host localhost --port 8008
```

Open <http://localhost:8008/>.

Use these sample uploads in the UI:

- `src/context_doctor/examples/schema.json`
- `src/context_doctor/examples/rules.md`

Use `PostgreSQL` as the sample SQL dialect.

LLM-backed workflows require `BASE_URL`, `OPENAI_TOKEN`, and `OPENAI_MODEL`.

For the reload-enabled development server, run this from `src/`:

```sh
../start.sh
```

## Environment

Copy `.env.example` to `.env` for local use and fill in values. Do not commit `.env`.

OpenAI-compatible settings:

- `BASE_URL`: Base URL for the OpenAI-compatible API.
- `OPENAI_TOKEN`: API token for the OpenAI-compatible API.
- `OPENAI_MODEL`: Model/deployment name used for analysis.

Runtime settings:

- `MAX_CONCURRENT_RULE_ANALYSES`: Parallel LLM calls for all-rules analysis, defaults to `1`.
- `DATABASE_URL`: Optional SQLAlchemy database URL.
- `CONTEXT_DOCTOR_DB_PATH`: SQLite path used when `DATABASE_URL` is not set.

## Uploaded Context Format

Upload schema as a JSON object with `description` and `tables`. Each table should include `originalName`, `description`, `columns`, and `relations`. Each column should include `originalName`, `description`, and `type`.

Upload rules as plain text. All-rules analysis expects rule headings in the form `Rule #`.

Enter the SQL dialect as text, for example `PostgreSQL`, `Trino`, or `Snowflake`.

## Docker

Build from the repository root:

```sh
docker build -t context-doctor .
```

Run with environment values:

```sh
docker run --rm -p 8000:8000 --env-file .env context-doctor
```

Open <http://localhost:8000/>.

## Manual Checks

- Load `/`.
- Load `/history`.
- Run one rule analysis.
- Run all rules analysis and verify polling progress.
- Cancel all rules analysis and verify partial results.
- Run question analysis.
- Run rule generation.
- Confirm history records are written without breaking analysis if history fails.

## Security

- Never commit `.env`, API tokens, private URLs, or runtime database files.
- `.env.example` contains placeholders only.
- Sample files are synthetic and safe for public demos.
