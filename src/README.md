# Context Doctor

Context Doctor is a FastAPI demo for inspecting text-to-SQL rule context. It supports one-rule analysis, all-rules analysis, question analysis, and rule generation.

For full setup instructions, see the repository-level `README.md`.

## Local Run

```sh
uv sync
uv run python -m uvicorn context_doctor.fastapi_app:app --host localhost --port 8008
```

Set `BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` before running LLM-backed workflows. Upload schema JSON, rules text, and SQL dialect in the UI for each request.
