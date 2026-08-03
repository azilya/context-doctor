"""Unit coverage for persistence semantics and immutable context snapshots."""

from types import SimpleNamespace

import pytest

from context_doctor.services.context_service import ContextService


def test_analysis_context_snapshot_deep_copies_nested_schema(analysis_context):
    """A task snapshot remains independent from nested caller mutations."""
    snapshot = analysis_context.snapshot()

    analysis_context.raw_schema["description"] = "changed"

    assert snapshot.raw_schema["description"] == "Revenue analytics application."


def test_save_creates_new_identity(monkeypatch, analysis_context):
    """Create semantics assign an identifier and send normalized data to storage."""
    calls = []
    monkeypatch.setattr(
        "context_doctor.services.context_service.get_db_session",
        __import__("tests.conftest", fromlist=["session_context"]).session_context(
            object()
        ),
    )
    monkeypatch.setattr(
        "context_doctor.services.context_service.ContextRepository.upsert",
        lambda session, context_id, context, now: calls.append((context_id, context)),
    )

    saved = ContextService.save(analysis_context)

    assert saved.context_id
    assert calls == [(saved.context_id, analysis_context)]


def test_replace_rejects_unknown_identity(monkeypatch, analysis_context):
    """Explicit replacement never silently creates a misspelled identifier."""
    monkeypatch.setattr(
        "context_doctor.services.context_service.get_db_session",
        __import__("tests.conftest", fromlist=["session_context"]).session_context(
            object()
        ),
    )
    monkeypatch.setattr(
        "context_doctor.services.context_service.ContextRepository.get",
        lambda session, context_id: None,
    )

    with pytest.raises(KeyError, match="Context not found"):
        ContextService.save(analysis_context, "missing")


def test_get_revalidates_stored_raw_context(monkeypatch, valid_schema):
    """Loading reconstructs a trusted snapshot and touches retention metadata."""
    import json

    record = SimpleNamespace(
        context_id="cached",
        raw_schema_json=json.dumps(valid_schema),
        rules_text="Rule #1: Use orders.",
        sql_dialect="PostgreSQL",
        schema_filename="schema.json",
        rules_filename="rules.md",
    )
    monkeypatch.setattr(
        "context_doctor.services.context_service.get_db_session",
        __import__("tests.conftest", fromlist=["session_context"]).session_context(
            object()
        ),
    )
    monkeypatch.setattr(
        "context_doctor.services.context_service.ContextRepository.get",
        lambda session, context_id: record,
    )
    touched = []
    monkeypatch.setattr(
        "context_doctor.services.context_service.ContextRepository.touch",
        lambda session, stored, now: touched.append(stored.context_id),
    )

    context = ContextService.get("cached")

    assert context.context_id == "cached"
    assert context.schema_description["tables"]["orders"]
    assert touched == ["cached"]
