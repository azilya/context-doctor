"""Unit tests for the concrete dialect-documentation tool."""

from context_doctor.services import dialect_docs


def test_unknown_dialect_is_structured_failure():
    """Unregistered dialects fail without accidental web traffic."""
    result = dialect_docs.check_dialect_documentation("unknown")

    assert result.valid is False
    assert result.current is False
    assert result.url is None


def test_official_current_documentation_is_checked(monkeypatch):
    """Registered docs are probed at their official current-version URL."""

    class Response:
        status_code = 200

    calls = []
    monkeypatch.setattr(
        dialect_docs,
        "requests",
        type(
            "Requests",
            (),
            {
                "head": staticmethod(
                    lambda url, **kwargs: (calls.append((url, kwargs)) or Response())
                ),
                "RequestException": Exception,
            },
        ),
    )

    result = dialect_docs.check_dialect_documentation("PostgreSQL", timeout=1)

    assert result.valid is True
    assert result.current is True
    assert calls == [
        (
            "https://www.postgresql.org/docs/current/sql.html",
            {
                "headers": {"User-Agent": "context-doctor/0.1"},
                "timeout": 1,
                "allow_redirects": True,
            },
        )
    ]
