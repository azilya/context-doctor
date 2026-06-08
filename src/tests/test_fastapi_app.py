import json
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from context_doctor import fastapi_app


@pytest.fixture
def api_client():
    return TestClient(fastapi_app.app)


def upload_files(valid_schema_bytes, valid_rules_bytes):
    return {
        "schema_file": ("schema.json", valid_schema_bytes, "application/json"),
        "rules_file": ("rules.md", valid_rules_bytes, "text/markdown"),
    }


def fake_history_entry(**overrides):
    values = {
        "id": 42,
        "flow_type": "rule_analysis",
        "execution_mode": "sync",
        "input_params": json.dumps({"new_rule": "Rule #9: Use SUM(revenue)."}),
        "created_at": datetime(2026, 6, 8, 12, 30, 0),
        "duration_seconds": 1.25,
        "status": "completed",
        "result_html": "<table><tr><td>analysis result</td></tr></table>",
        "error_message": None,
        "rules_text": "Rule #1: Existing rule.",
        "schema_json": '{"tables": {"orders": {}}}',
        "guidelines_text": "Guideline text",
        "task_id": None,
        "total_rules": None,
        "completed_rules": None,
        "client_backend_url": "",
        "user_agent": "test-agent",
        "ip_address": "127.0.0.1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def session_context(session):
    @contextmanager
    def fake_db_session():
        yield session

    return fake_db_session


def test_index_renders_application_shell(api_client):
    response = api_client.get("/")

    assert response.status_code == 200
    assert "Context Doctor" in response.text
    assert 'form action="/run"' in response.text
    assert 'name="schema_file"' in response.text


def test_history_page_uses_repository_boundary(monkeypatch, api_client):
    session = object()
    list_entries = Mock(return_value=([], 0))
    get_statistics = Mock(
        return_value={
            "total_queries": 4,
            "average_duration_seconds": 1.25,
            "by_status": {"completed": 3, "failed": 1},
        }
    )
    monkeypatch.setattr(fastapi_app, "get_db_session", session_context(session))
    monkeypatch.setattr(fastapi_app.HistoryRepository, "list_entries", list_entries)
    monkeypatch.setattr(fastapi_app.HistoryRepository, "get_statistics", get_statistics)

    response = api_client.get(
        "/history?flow=rule_analysis&status=completed&search=revenue&page=2&limit=5"
    )

    assert response.status_code == 200
    assert "Query History" in response.text
    assert "No History Found" in response.text
    assert "Total Queries" in response.text
    list_entries.assert_called_once_with(
        session=session,
        flow_type="rule_analysis",
        status="completed",
        search_query="revenue",
        limit=5,
        offset=5,
    )
    get_statistics.assert_called_once_with(session, days=7)


def test_history_page_renders_error_fallback_when_repository_raises(
    monkeypatch,
    api_client,
):
    monkeypatch.setattr(fastapi_app, "get_db_session", session_context(object()))
    monkeypatch.setattr(
        fastapi_app.HistoryRepository,
        "list_entries",
        Mock(side_effect=RuntimeError("history unavailable")),
    )

    response = api_client.get("/history")

    assert response.status_code == 200
    assert "history unavailable" in response.text
    assert "No History Found" in response.text


def test_history_detail_uses_repository_boundary(monkeypatch, api_client):
    session = object()
    entry = fake_history_entry()
    get_by_id = Mock(return_value=entry)
    monkeypatch.setattr(fastapi_app, "get_db_session", session_context(session))
    monkeypatch.setattr(fastapi_app.HistoryRepository, "get_by_id", get_by_id)

    response = api_client.get("/history/42")

    assert response.status_code == 200
    assert "Query History Entry #42" in response.text
    assert "Rule #9: Use SUM(revenue)." in response.text
    assert "analysis result" in response.text
    assert "Guideline text" in response.text
    get_by_id.assert_called_once_with(session, 42)


def test_history_detail_unknown_entry_returns_404(monkeypatch, api_client):
    monkeypatch.setattr(fastapi_app, "get_db_session", session_context(object()))
    monkeypatch.setattr(fastapi_app.HistoryRepository, "get_by_id", Mock(return_value=None))

    response = api_client.get("/history/404")

    assert response.status_code == 404
    assert response.json() == {"detail": "History entry not found"}


def test_history_stats_uses_repository_boundary(monkeypatch, api_client):
    session = object()
    get_statistics = Mock(return_value={"total_queries": 3, "period_days": 14})
    monkeypatch.setattr(fastapi_app, "get_db_session", session_context(session))
    monkeypatch.setattr(fastapi_app.HistoryRepository, "get_statistics", get_statistics)

    response = api_client.get("/api/history/stats?days=14")

    assert response.status_code == 200
    assert response.json() == {"total_queries": 3, "period_days": 14}
    get_statistics.assert_called_once_with(session, days=14)


def test_delete_history_entry_uses_repository_boundary(monkeypatch, api_client):
    session = object()
    delete_entry = Mock(return_value=True)
    monkeypatch.setattr(fastapi_app, "get_db_session", session_context(session))
    monkeypatch.setattr(fastapi_app.HistoryRepository, "delete_entry", delete_entry)

    response = api_client.delete("/api/history/42")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "id": 42}
    delete_entry.assert_called_once_with(session, 42)


def test_delete_history_entry_unknown_entry_returns_404(monkeypatch, api_client):
    monkeypatch.setattr(fastapi_app, "get_db_session", session_context(object()))
    monkeypatch.setattr(
        fastapi_app.HistoryRepository,
        "delete_entry",
        Mock(return_value=False),
    )

    response = api_client.delete("/api/history/404")
    assert response.status_code == 404
    assert response.json() == {"detail": "History entry not found"}


@pytest.mark.parametrize(
    ("flow", "form_overrides", "expected_fields"),
    [
        (
            "rule_analysis",
            {"new_rule": " Rule #9: Use SUM(orders.revenue). "},
            {"new_rule": "Rule #9: Use SUM(orders.revenue)."},
        ),
        (
            "question_analysis",
            {"question": " Which region has the most revenue? "},
            {"question": "Which region has the most revenue?"},
        ),
        (
            "rule_generation",
            {
                "question": " Which region has the most revenue? ",
                "problem": " Revenue answers use row counts. ",
            },
            {
                "question": "Which region has the most revenue?",
                "problem": "Revenue answers use row counts.",
            },
        ),
    ],
)
def test_run_sync_flows_render_result_without_external_services(
    monkeypatch,
    api_client,
    no_history_logging,
    valid_schema_bytes,
    valid_rules_bytes,
    flow,
    form_overrides,
    expected_fields,
):
    captured_params = []

    def fake_run_analysis(params):
        captured_params.append(params)
        return (
            f"{params.flow} rendered result",
            params.context.rules_text,
            params.context.schema_description,
            f"{params.flow} guidelines",
        )

    monkeypatch.setattr(fastapi_app, "run_analysis", fake_run_analysis)

    form_data = {"flow": flow, "sql_dialect": " PostgreSQL ", **form_overrides}
    response = api_client.post(
        "/run",
        data=form_data,
        files=upload_files(valid_schema_bytes, valid_rules_bytes),
    )

    assert response.status_code == 200
    assert f"{flow} rendered result" in response.text
    assert "Rule #1: ALWAYS join orders" in response.text
    assert "orders" in response.text
    assert len(captured_params) == 1
    params = captured_params[0]
    assert params.flow == flow
    assert params.context.sql_dialect == "PostgreSQL"
    for field_name, expected_value in expected_fields.items():
        assert getattr(params, field_name) == expected_value
    no_history_logging["start_sync_execution"].assert_called_once()
    no_history_logging["complete_sync_execution"].assert_called_once()
    no_history_logging["fail_execution"].assert_not_called()


def test_run_all_rules_starts_task_and_renders_polling_state(
    monkeypatch,
    api_client,
    no_history_logging,
    valid_schema_bytes,
    valid_rules_bytes,
):
    start_all_rules_analysis = Mock(return_value="task-123")
    fake_task_manager = Mock(start_all_rules_analysis=start_all_rules_analysis)
    monkeypatch.setattr(fastapi_app, "task_manager", fake_task_manager)
    monkeypatch.setattr(
        fastapi_app,
        "run_analysis",
        Mock(side_effect=AssertionError("all_rules_analysis must start async task")),
    )

    response = api_client.post(
        "/run",
        data={"flow": "all_rules_analysis", "sql_dialect": "PostgreSQL"},
        files=upload_files(valid_schema_bytes, valid_rules_bytes),
    )

    assert response.status_code == 200
    assert "Waiting for results" in response.text
    assert 'var taskId = "task-123";' in response.text
    assert "pollTask()" in response.text
    assert "stopTask()" in response.text
    start_all_rules_analysis.assert_called_once()
    (started_context,), _ = start_all_rules_analysis.call_args
    assert started_context.sql_dialect == "PostgreSQL"
    assert started_context.rules_text.startswith("Rule #1: ALWAYS join orders")
    assert started_context.raw_schema["description"] == "Revenue analytics application."
    assert "orders" in started_context.schema_description["tables"]
    assert started_context.schema_filename == "schema.json"
    assert started_context.rules_filename == "rules.md"
    no_history_logging["start_async_execution"].assert_called_once_with(
        task_id="task-123",
        flow_type="all_rules_analysis",
        input_params={
            "new_rule": None,
            "question": None,
            "problem": None,
            "schema_filename": "schema.json",
            "rules_filename": "rules.md",
            "sql_dialect": "PostgreSQL",
        },
        client_backend_url="",
        user_agent="testclient",
        ip_address="testclient",
    )
    no_history_logging["start_sync_execution"].assert_not_called()


@pytest.mark.parametrize(
    ("data", "files", "expected_error"),
    [
        (
            {"flow": "rule_analysis", "sql_dialect": "PostgreSQL"},
            lambda schema, rules: {
                "schema_file": ("schema.json", b"{not-json", "application/json"),
                "rules_file": ("rules.md", rules, "text/markdown"),
            },
            "Schema file is not valid JSON",
        ),
        (
            {"flow": "rule_analysis", "sql_dialect": "PostgreSQL"},
            lambda schema, rules: {
                "rules_file": ("rules.md", rules, "text/markdown"),
            },
            "Schema JSON file is required",
        ),
        (
            {"flow": "rule_analysis", "sql_dialect": "PostgreSQL"},
            lambda schema, rules: {
                "schema_file": ("schema.json", schema, "application/json"),
            },
            "Rules text file is required",
        ),
        (
            {"flow": "rule_analysis", "sql_dialect": "PostgreSQL"},
            lambda schema, rules: {
                "schema_file": ("schema.json", schema, "application/json"),
                "rules_file": ("rules.md", b" \n\t", "text/markdown"),
            },
            "Rules text must not be empty",
        ),
        (
            {"flow": "rule_analysis", "sql_dialect": "   "},
            lambda schema, rules: {
                "schema_file": ("schema.json", schema, "application/json"),
                "rules_file": ("rules.md", rules, "text/markdown"),
            },
            "SQL dialect is required",
        ),
    ],
)
def test_run_context_boundary_errors_do_not_call_analysis_or_history(
    monkeypatch,
    api_client,
    no_history_logging,
    valid_schema_bytes,
    valid_rules_bytes,
    data,
    files,
    expected_error,
):
    run_analysis = Mock(side_effect=AssertionError("analysis must not run"))
    start_all_rules_analysis = Mock(side_effect=AssertionError("task must not start"))
    monkeypatch.setattr(fastapi_app, "run_analysis", run_analysis)
    monkeypatch.setattr(
        fastapi_app,
        "task_manager",
        Mock(start_all_rules_analysis=start_all_rules_analysis),
    )

    response = api_client.post(
        "/run",
        data=data,
        files=files(valid_schema_bytes, valid_rules_bytes),
    )

    assert response.status_code == 200
    assert expected_error in response.text
    assert "PostgreSQL" in response.text or data["sql_dialect"].strip() == ""
    run_analysis.assert_not_called()
    start_all_rules_analysis.assert_not_called()
    no_history_logging["start_sync_execution"].assert_not_called()
    no_history_logging["start_async_execution"].assert_not_called()


@pytest.mark.parametrize(
    ("data", "expected_error"),
    [
        ({"flow": "rule_analysis", "sql_dialect": "PostgreSQL"}, "New rule is required"),
        (
            {"flow": "question_analysis", "sql_dialect": "PostgreSQL"},
            "Question is required",
        ),
        (
            {"flow": "rule_generation", "sql_dialect": "PostgreSQL"},
            "Problem description is required",
        ),
        (
            {"flow": "unknown_flow", "sql_dialect": "PostgreSQL"},
            "Unknown flow: unknown_flow",
        ),
    ],
)
def test_run_flow_input_errors_fail_before_llm_boundaries(
    monkeypatch,
    api_client,
    no_history_logging,
    valid_schema_bytes,
    valid_rules_bytes,
    data,
    expected_error,
):
    from context_doctor import logic

    llm_backed_functions = [
        Mock(side_effect=AssertionError("rule analysis LLM must not run")),
        Mock(side_effect=AssertionError("question analysis LLM must not run")),
        Mock(side_effect=AssertionError("rule generation LLM must not run")),
        Mock(side_effect=AssertionError("all-rules LLM must not run")),
    ]
    monkeypatch.setattr(logic, "analyze_rule_pipeline", llm_backed_functions[0])
    monkeypatch.setattr(logic, "filter_and_compare_question", llm_backed_functions[1])
    monkeypatch.setattr(logic, "generate_rule_pipeline", llm_backed_functions[2])
    monkeypatch.setattr(logic, "all_rules_pipeline", llm_backed_functions[3])

    response = api_client.post(
        "/run",
        data=data,
        files=upload_files(valid_schema_bytes, valid_rules_bytes),
    )

    assert response.status_code == 200
    assert expected_error in response.text
    assert "schema.json" in response.text
    assert "rules.md" in response.text
    for llm_backed_function in llm_backed_functions:
        llm_backed_function.assert_not_called()
    no_history_logging["start_sync_execution"].assert_called_once()
    no_history_logging["complete_sync_execution"].assert_not_called()
    no_history_logging["fail_execution"].assert_called_once()


def test_run_workflow_error_preserves_form_values_and_logs_noncritical_failure(
    monkeypatch,
    api_client,
    no_history_logging,
    valid_schema_bytes,
    valid_rules_bytes,
):
    monkeypatch.setattr(
        fastapi_app,
        "run_analysis",
        Mock(side_effect=RuntimeError("LLM parse failed: invalid structured output")),
    )

    response = api_client.post(
        "/run",
        data={
            "flow": "rule_analysis",
            "sql_dialect": " PostgreSQL ",
            "new_rule": " Rule #9: Use SUM(orders.revenue). ",
        },
        files=upload_files(valid_schema_bytes, valid_rules_bytes),
    )

    assert response.status_code == 200
    assert "LLM parse failed: invalid structured output" in response.text
    assert "Rule #9: Use SUM(orders.revenue)." in response.text
    assert "PostgreSQL" in response.text
    assert "schema.json" in response.text
    assert "rules.md" in response.text
    no_history_logging["start_sync_execution"].assert_called_once()
    no_history_logging["complete_sync_execution"].assert_not_called()
    no_history_logging["fail_execution"].assert_called_once()


def test_run_history_failure_logging_remains_noncritical_for_workflow_errors(
    monkeypatch,
    api_client,
    valid_schema_bytes,
    valid_rules_bytes,
):
    monkeypatch.setattr(
        fastapi_app.HistoryService,
        "start_sync_execution",
        Mock(return_value=101),
    )
    monkeypatch.setattr(
        fastapi_app.HistoryService,
        "fail_execution",
        Mock(side_effect=RuntimeError("history unavailable")),
    )
    monkeypatch.setattr(
        fastapi_app,
        "run_analysis",
        Mock(side_effect=RuntimeError("workflow failed")),
    )

    response = api_client.post(
        "/run",
        data={
            "flow": "rule_analysis",
            "sql_dialect": "PostgreSQL",
            "new_rule": "Rule #9: Use SUM(orders.revenue).",
        },
        files=upload_files(valid_schema_bytes, valid_rules_bytes),
    )

    assert response.status_code == 200
    assert "workflow failed" in response.text
    assert "history unavailable" not in response.text


def test_task_status_returns_incremental_payload(monkeypatch, api_client):
    get_status = Mock(
        return_value={
            "task_id": "task-123",
            "status": "running",
            "total_rules": 2,
            "completed_rules": 1,
            "pages": ["<p>Rule #1</p>"],
            "next_index": 1,
            "error": None,
            "rules_text": "Rule #1",
            "schema_json": "{}",
            "guidelines_text": "GUIDELINES",
        }
    )
    monkeypatch.setattr(fastapi_app, "task_manager", Mock(get_status=get_status))

    response = api_client.get("/tasks/task-123?from_index=1")

    assert response.status_code == 200
    assert response.json()["pages"] == ["<p>Rule #1</p>"]
    assert response.json()["next_index"] == 1
    get_status.assert_called_once_with("task-123", from_index=1)


def test_task_status_unknown_task_returns_404(monkeypatch, api_client):
    monkeypatch.setattr(
        fastapi_app,
        "task_manager",
        Mock(get_status=Mock(return_value=None)),
    )

    response = api_client.get("/tasks/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_task_cancel_returns_cancelled_payload(monkeypatch, api_client):
    cancel_task = Mock(return_value=True)
    monkeypatch.setattr(fastapi_app, "task_manager", Mock(cancel_task=cancel_task))

    response = api_client.post("/tasks/task-123/cancel")

    assert response.status_code == 200
    assert response.json() == {"task_id": "task-123", "status": "cancelled"}
    cancel_task.assert_called_once_with("task-123")


def test_task_cancel_unknown_task_returns_404(monkeypatch, api_client):
    monkeypatch.setattr(
        fastapi_app,
        "task_manager",
        Mock(cancel_task=Mock(return_value=False)),
    )

    response = api_client.post("/tasks/missing/cancel")
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}
