"""Application settings loaded from environment variables."""

import os
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


BASE_URL = os.getenv("BASE_URL", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")

MAX_CONCURRENT_RULE_ANALYSES = _int_env("MAX_CONCURRENT_RULE_ANALYSES", 1)
# Cached contexts expire after 30 days by default to prevent unbounded growth.
CONTEXT_CACHE_TTL_SECONDS = _int_env("CONTEXT_CACHE_TTL_SECONDS", 30 * 24 * 60 * 60)

CONTEXT_DOCTOR_DB_PATH = os.getenv(
    "CONTEXT_DOCTOR_DB_PATH",
    str(Path.cwd() / "context_doctor_history.db"),
)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{CONTEXT_DOCTOR_DB_PATH}")
