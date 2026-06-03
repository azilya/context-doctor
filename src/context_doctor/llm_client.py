"""OpenAI-compatible LLM client helpers."""

from functools import lru_cache

from openai import OpenAI

from . import settings


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    if not settings.OPENAI_TOKEN:
        raise ValueError("OPENAI_TOKEN is required for LLM analysis")
    if not settings.OPENAI_MODEL:
        raise ValueError("OPENAI_MODEL is required for LLM analysis")

    kwargs = {"api_key": settings.OPENAI_TOKEN}
    if settings.BASE_URL:
        kwargs["base_url"] = settings.BASE_URL
    return OpenAI(**kwargs)


def parse_response(messages: list[dict], text_format):
    return (
        get_openai_client()
        .responses.parse(
            model=settings.OPENAI_MODEL,
            input=messages,
            temperature=0,
            text_format=text_format,
        )
        .output_parsed
    )
