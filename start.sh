#!/usr/bin/env sh

export UV_PROJECT_ENVIRONMENT=${UV_PROJECT_ENVIRONMENT:-.venv}
export BASE_URL=${BASE_URL:-}
export OPENAI_API_KEY=${OPENAI_API_KEY:-}
export OPENAI_MODEL=${OPENAI_MODEL:-}
export MAX_CONCURRENT_RULE_ANALYSES=${MAX_CONCURRENT_RULE_ANALYSES:-1}
export HOST=${HOST:-localhost}
export PORT=${PORT:-8008}

exec uv run python -m uvicorn context_doctor.fastapi_app:app --host "$HOST" --port "$PORT" --reload --reload-include "context_doctor/prompts/*.yaml" --reload-include "context_doctor/templates/*.html"
