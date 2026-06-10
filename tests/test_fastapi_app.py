from unittest.mock import Mock

import pytest

from context_doctor import fastapi_app
from tests.conftest import assert_response_contains


def test_index_renders_application_shell(api_client):
    response = api_client.get("/")

    assert_response_contains(
        response,
        "Context Doctor",
        'form action="/run"',
        'name="schema_file"',
    )


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
    no_history_logging,
    post_run,
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

    response = post_run({"flow": flow, "sql_dialect": " PostgreSQL ", **form_overrides})

    assert_response_contains(
        response,
        f"{flow} rendered result",
        "Rule #1: ALWAYS join orders",
        "orders",
    )
    assert len(captured_params) == 1
    params = captured_params[0]
    assert params.flow == flow
    assert params.context.sql_dialect == "PostgreSQL"
    for field_name, expected_value in expected_fields.items():
        assert getattr(params, field_name) == expected_value
    no_history_logging["start_sync_execution"].assert_called_once()
    no_history_logging["complete_sync_execution"].assert_called_once()
    no_history_logging["fail_execution"].assert_not_called()


@pytest.fixture
def llm_boundary_mocks(monkeypatch):
    from context_doctor import logic

    mocks = {
        "analyze_rule_pipeline": Mock(
            side_effect=AssertionError("rule analysis LLM must not run")
        ),
        "filter_and_compare_question": Mock(
            side_effect=AssertionError("question analysis LLM must not run")
        ),
        "generate_rule_pipeline": Mock(
            side_effect=AssertionError("rule generation LLM must not run")
        ),
        "all_rules_pipeline": Mock(
            side_effect=AssertionError("all-rules LLM must not run")
        ),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(logic, name, mock)
    return mocks


def test_run_all_rules_starts_task_and_renders_polling_state(
    monkeypatch,
    no_history_logging,
    post_run,
):
    start_all_rules_analysis = Mock(return_value="task-123")
    monkeypatch.setattr(
        fastapi_app,
        "task_manager",
        Mock(start_all_rules_analysis=start_all_rules_analysis),
    )
    monkeypatch.setattr(
        fastapi_app,
        "run_analysis",
        Mock(side_effect=AssertionError("all_rules_analysis must start async task")),
    )

    response = post_run({"flow": "all_rules_analysis", "sql_dialect": "PostgreSQL"})

    assert_response_contains(
        response,
        "Waiting for results",
        'var taskId = "task-123";',
        "pollTask()",
        "stopTask()",
    )
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
    no_history_logging,
    post_run,
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

    response = post_run(data, files=files(valid_schema_bytes, valid_rules_bytes))

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
    no_history_logging,
    post_run,
    llm_boundary_mocks,
    data,
    expected_error,
):
    response = post_run(data)

    assert_response_contains(response, expected_error, "schema.json", "rules.md")
    for llm_backed_function in llm_boundary_mocks.values():
        llm_backed_function.assert_not_called()
    no_history_logging["start_sync_execution"].assert_called_once()
    no_history_logging["complete_sync_execution"].assert_not_called()
    no_history_logging["fail_execution"].assert_called_once()


def test_run_workflow_error_preserves_form_values_and_logs_noncritical_failure(
    monkeypatch,
    no_history_logging,
    post_run,
):
    monkeypatch.setattr(
        fastapi_app,
        "run_analysis",
        Mock(side_effect=RuntimeError("LLM parse failed: invalid structured output")),
    )

    response = post_run(
        {
            "flow": "rule_analysis",
            "sql_dialect": " PostgreSQL ",
            "new_rule": " Rule #9: Use SUM(orders.revenue). ",
        }
    )

    assert_response_contains(
        response,
        "LLM parse failed: invalid structured output",
        "Rule #9: Use SUM(orders.revenue).",
        "PostgreSQL",
        "schema.json",
        "rules.md",
    )
    no_history_logging["start_sync_execution"].assert_called_once()
    no_history_logging["complete_sync_execution"].assert_not_called()
    no_history_logging["fail_execution"].assert_called_once()


def test_run_history_failure_logging_remains_noncritical_for_workflow_errors(
    monkeypatch,
    post_run,
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

    response = post_run(
        {
            "flow": "rule_analysis",
            "sql_dialect": "PostgreSQL",
            "new_rule": "Rule #9: Use SUM(orders.revenue).",
        }
    )

    assert_response_contains(response, "workflow failed")
    assert "history unavailable" not in response.text


def test_task_status_returns_incremental_payload(monkeypatch, api_client):
    task_status = {
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
    get_status = Mock(return_value=task_status)
    monkeypatch.setattr(fastapi_app, "task_manager", Mock(get_status=get_status))

    response = api_client.get("/tasks/task-123?from_index=1")

    assert response.status_code == 200
    assert response.json() == task_status
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
