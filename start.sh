export BASE_URL=${BASE_URL:-}
export OPENAI_TOKEN=${OPENAI_TOKEN:-}
export OPENAI_MODEL=${OPENAI_MODEL:-}
export MAX_CONCURRENT_RULE_ANALYSES=${MAX_CONCURRENT_RULE_ANALYSES:-1}

poetry run uvicorn context_doctor.fastapi_app:app --host localhost --port 8008 --reload --reload-include "context_doctor/prompts/*.yaml" --reload-include "context_doctor/templates/*.html"
