"""Functional contracts for cached-context and task-managed rule APIs."""

from unittest.mock import Mock

from context_doctor import fastapi_app


def test_context_create_returns_persisted_identity(
    monkeypatch, api_client, upload_files, analysis_context
):
    """Context uploads return the identity produced by the service boundary."""
    persisted = analysis_context.model_copy(update={"context_id": "context-123"})
    from_uploads = Mock(return_value=analysis_context)
    save = Mock(return_value=persisted)
    monkeypatch.setattr(fastapi_app.ContextService, "from_uploads", from_uploads)
    monkeypatch.setattr(fastapi_app.ContextService, "save", save)

    response = api_client.post(
        "/api/contexts",
        data={"sql_dialect": "PostgreSQL"},
        files=upload_files,
    )

    assert response.status_code == 200
    assert response.json() == {
        "context_id": "context-123",
        "schema_filename": "schema.json",
        "rules_filename": "rules.md",
        "sql_dialect": "PostgreSQL",
    }
    from_uploads.assert_called_once()
    save.assert_called_once_with(analysis_context, None)


def test_context_metadata_and_delete_contracts(
    monkeypatch, api_client, analysis_context
):
    """Cached contexts can be inspected safely and deleted explicitly."""
    persisted = analysis_context.model_copy(update={"context_id": "context-123"})
    monkeypatch.setattr(fastapi_app.ContextService, "get", Mock(return_value=persisted))
    delete = Mock(return_value=True)
    monkeypatch.setattr(fastapi_app.ContextService, "delete", delete)

    metadata = api_client.get("/api/contexts/context-123")
    deleted = api_client.delete("/api/contexts/context-123")

    assert metadata.status_code == 200
    assert "raw_schema" not in metadata.json()
    assert metadata.json()["context_id"] == "context-123"
    assert deleted.json() == {"status": "deleted", "context_id": "context-123"}
    delete.assert_called_once_with("context-123")


def test_context_routes_return_not_found(monkeypatch, api_client):
    """Unknown context identities return stable HTTP 404 responses."""
    monkeypatch.setattr(fastapi_app.ContextService, "get", Mock(return_value=None))
    monkeypatch.setattr(fastapi_app.ContextService, "delete", Mock(return_value=False))

    assert api_client.get("/api/contexts/missing").status_code == 404
    assert api_client.delete("/api/contexts/missing").status_code == 404


def test_rule_analysis_task_uses_cached_context(
    monkeypatch, no_history_logging, api_client, analysis_context
):
    """Single-rule task startup delegates to the manager and records identity."""
    persisted = analysis_context.model_copy(update={"context_id": "context-123"})
    monkeypatch.setattr(fastapi_app.ContextService, "get", Mock(return_value=persisted))
    start_rule_analysis = Mock(return_value="task-123")
    monkeypatch.setattr(
        fastapi_app,
        "task_manager",
        Mock(start_rule_analysis=start_rule_analysis),
    )

    response = api_client.post(
        "/api/tasks/rule-analysis",
        data={"context_id": "context-123", "new_rule": " Rule #9: Use SUM. "},
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "task-123", "status": "pending"}
    start_rule_analysis.assert_called_once_with(persisted, " Rule #9: Use SUM. ")
    no_history_logging["start_async_execution"].assert_called_once_with(
        task_id="task-123",
        flow_type="rule_analysis",
        input_params={"context_id": "context-123", "new_rule": "Rule #9: Use SUM."},
    )
