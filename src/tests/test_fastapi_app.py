from contextlib import contextmanager
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


def test_index_renders_application_shell(api_client):
    response = api_client.get("/")

    assert response.status_code == 200
    assert "Context Doctor" in response.text
    assert 'form action="/run"' in response.text
    assert 'name="schema_file"' in response.text


def test_history_page_uses_repository_boundary(monkeypatch, api_client):
    session = object()

    @contextmanager
    def fake_db_session():
        yield session

    list_entries = Mock(return_value=([], 0))
    get_statistics = Mock(
        return_value={
            "total_queries": 4,
            "average_duration_seconds": 1.25,
            "by_status": {"completed": 3, "failed": 1},
        }
    )
    monkeypatch.setattr(fastapi_app, "get_db_session", fake_db_session)
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
    no_history_logging["start_async_execution"].assert_called_once()
    no_history_logging["start_sync_execution"].assert_not_called()


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
