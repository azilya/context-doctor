"""Deterministic tool for validating official SQL-dialect documentation links."""

from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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
    # prompt. Automated tests replace urlopen and never make live requests.
    request = Request(url, method="HEAD", headers={"User-Agent": "context-doctor/0.1"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            valid = 200 <= response.status < 400
    except (HTTPError, URLError, TimeoutError) as exc:
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
