"""Deterministic tool for validating official SQL-dialect documentation links."""

from dataclasses import asdict, dataclass

import requests

OFFICIAL_DIALECT_DOCS = {
    "postgresql": "https://www.postgresql.org/docs/current/sql.html",
    "snowflake": "https://docs.snowflake.com/en/sql-reference",
    "trino": "https://trino.io/docs/current/sql.html",
}


@dataclass(frozen=True)
class DialectDocumentationResult:
    """Structured output from the documentation validation tool."""

    dialect: str
    url: str | None
    valid: bool
    current: bool
    detail: str

    def to_dict(self) -> dict:
        """Serialize the tool result for JSON APIs.

        Returns:
            Dictionary containing all validation fields.
        """
        return asdict(self)


def check_dialect_documentation(
    dialect: str, timeout: float = 5.0
) -> DialectDocumentationResult:
    """Check availability of a dialect's version-current official docs.

    Args:
        dialect: Supported SQL dialect name.
        timeout: Maximum HTTP wait in seconds.

    Returns:
        Structured availability and currency result. Network failures are data,
        not exceptions, so an agent can decide how to proceed.
    """
    normalized = dialect.strip().casefold()
    url = OFFICIAL_DIALECT_DOCS.get(normalized)
    if url is None:
        return DialectDocumentationResult(
            dialect=dialect.strip(),
            url=None,
            valid=False,
            current=False,
            detail="No official documentation source is registered for this dialect.",
        )

    # A real HTTP boundary makes this an actionable tool rather than another LLM
    # prompt. Automated tests replace requests.head and never make live requests.
    try:
        response = requests.head(
            url,
            headers={"User-Agent": "context-doctor/0.1"},
            timeout=timeout,
            allow_redirects=True,
        )
        valid = 200 <= response.status_code < 400
    except requests.RequestException as exc:
        return DialectDocumentationResult(
            dialect=dialect.strip(),
            url=url,
            valid=False,
            current="current" in url,
            detail=f"Official documentation could not be reached: {exc}",
        )
    return DialectDocumentationResult(
        dialect=dialect.strip(),
        url=url,
        valid=valid,
        current="current" in url or "sql-reference" in url,
        detail="Official documentation is reachable."
        if valid
        else "Unexpected HTTP status.",
    )
