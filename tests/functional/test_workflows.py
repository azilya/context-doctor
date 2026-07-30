import re
import time

from context_doctor import fastapi_app
from context_doctor.flows import (
    question_analysis as question_analysis_flow,
    rule_analysis as rule_analysis_flow,
    rule_generation as rule_generation_flow,
)
from context_doctor.task_manager import TaskManager
from tests.conftest import assert_response_contains


def parse_response_dispatcher(*responses):
    pending = list(responses)

    def fake_parse_response(messages, text_format):
        for index, response in enumerate(pending):
            if isinstance(response, text_format):
                return pending.pop(index)
        expected = text_format.__name__
        remaining = [type(response).__name__ for response in pending]
        raise AssertionError(f"No fake {expected} response left; remaining={remaining}")

    fake_parse_response.pending = pending
    return fake_parse_response


def category_result(
    explanation="Functional workflow found an overlap.",
    matched_rules=None,
    matched_from_schema=None,
):
    return rule_analysis_flow.CategoryResult(
        explanation=explanation,
        matched_rules=matched_rules or [2],
        matched_from_schema=matched_from_schema or ["orders.revenue"],
    )


def accept_new_rule_response(summary="Functional rule comparison summary."):
    return rule_analysis_flow.AcceptNewRule(
        analysis_summary=summary,
        typos=[],
        dialect_inconsistencies=["Use PostgreSQL aggregate syntax."],
        contradictions=category_result(),
        duplications=category_result(
            explanation="Functional workflow found duplicate revenue guidance."
        ),
    )


def rule_validation_response(summary="Functional guideline validation summary."):
    return rule_analysis_flow.RuleValidationResult(
        analysis_summary=summary,
        violations=["Functional guideline violation."],
    )


def relevant_context_response():
    return question_analysis_flow.RelevantContext(
        analysis_summary="Functional context filtering summary.",
        relevant_rules=[
            "Rule #2: WHEN users ask for revenue, use SUM(orders.revenue)."
        ],
        relevant_descriptions=[
            question_analysis_flow.RelevantDescription(
                type="column",
                name="orders.revenue",
                description="Order revenue in USD.",
            )
        ],
    )


def question_comparison_response():
    return question_analysis_flow.QuestionAnalysis(
        analysis_summary="Functional question comparison summary.",
        typos=[],
        dialect_inconsistencies=["Use DATE_TRUNC in PostgreSQL."],
        contradictions=["Functional question contradiction."],
        duplications=["Functional question duplication."],
    )


def rule_suggestion_response():
    return rule_generation_flow.RuleSuggestion(
        analysis_summary="Functional generation summary.",
        suggested_rule=(
            "Rule #3: WHEN users ask for revenue by region, "
            "join customers and aggregate SUM(orders.revenue)."
        ),
    )


def assert_no_pending_responses(dispatcher):
    assert dispatcher.pending == []


def task_id_from_response(response):
    match = re.search(r'"taskId": "([^"]+)"', response.text)
    assert match, response.text
    return match.group(1)


def wait_for_task(api_client, task_id):
    last_payload = None
    for _ in range(50):
        response = api_client.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["status"] in {"completed", "failed", "cancelled"}:
            return last_payload
        time.sleep(0.02)
    raise AssertionError(f"Task did not finish: {last_payload}")


def test_rule_analysis_workflow_runs_through_fastapi_form(
    monkeypatch,
    no_history_logging,
    post_run,
):
    dispatcher = parse_response_dispatcher(
        accept_new_rule_response(),
        rule_validation_response(),
    )
    monkeypatch.setattr(rule_analysis_flow, "parse_response", dispatcher)

    response = post_run(
        {
            "flow": "rule_analysis",
            "sql_dialect": "PostgreSQL",
            "new_rule": "Rule #9: Use SUM(orders.revenue).",
        }
    )

    assert_response_contains(
        response,
        "Rule #9: Use SUM(orders.revenue).",
        "Functional rule comparison summary.",
        "Functional guideline validation summary.",
        "Functional guideline violation.",
        "Use PostgreSQL aggregate syntax.",
    )
    no_history_logging["complete_sync_execution"].assert_called_once()
    assert_no_pending_responses(dispatcher)


def test_question_analysis_workflow_runs_through_fastapi_form(
    monkeypatch,
    no_history_logging,
    post_run,
):
    dispatcher = parse_response_dispatcher(
        relevant_context_response(),
        question_comparison_response(),
    )
    monkeypatch.setattr(question_analysis_flow, "parse_response", dispatcher)

    response = post_run(
        {
            "flow": "question_analysis",
            "sql_dialect": "PostgreSQL",
            "question": "Which region has the most revenue?",
        }
    )

    assert_response_contains(
        response,
        "Which region has the most revenue?",
        "Functional context filtering summary.",
        "Functional question comparison summary.",
        "Rule #2: WHEN users ask for revenue",
        "orders.revenue",
    )
    no_history_logging["complete_sync_execution"].assert_called_once()
    assert_no_pending_responses(dispatcher)


def test_rule_generation_workflow_runs_through_fastapi_form(
    monkeypatch,
    no_history_logging,
    post_run,
):
    dispatcher = parse_response_dispatcher(
        relevant_context_response(),
        rule_suggestion_response(),
        accept_new_rule_response("Functional generated rule comparison summary."),
        rule_validation_response("Functional generated rule validation summary."),
    )
    monkeypatch.setattr(question_analysis_flow, "parse_response", dispatcher)
    monkeypatch.setattr(rule_generation_flow, "parse_response", dispatcher)
    monkeypatch.setattr(rule_analysis_flow, "parse_response", dispatcher)

    response = post_run(
        {
            "flow": "rule_generation",
            "sql_dialect": "PostgreSQL",
            "question": "Which region has the most revenue?",
            "problem": "Revenue answers use row counts instead of sums.",
        }
    )

    assert_response_contains(
        response,
        "Rule #3: WHEN users ask for revenue by region",
        "Functional generation summary.",
        "Functional generated rule comparison summary.",
        "Functional generated rule validation summary.",
        "Revenue answers use row counts instead of sums.",
    )
    no_history_logging["complete_sync_execution"].assert_called_once()
    assert_no_pending_responses(dispatcher)


def test_all_rules_analysis_workflow_starts_task_and_returns_polled_results(
    monkeypatch,
    no_history_logging,
    no_history_writes,
    api_client,
    upload_files,
):
    dispatcher = parse_response_dispatcher(
        accept_new_rule_response("Functional first rule comparison summary."),
        rule_validation_response("Functional first rule validation summary."),
        accept_new_rule_response("Functional second rule comparison summary."),
        rule_validation_response("Functional second rule validation summary."),
    )
    monkeypatch.setattr(rule_analysis_flow, "parse_response", dispatcher)
    monkeypatch.setattr(fastapi_app, "task_manager", TaskManager())
    monkeypatch.setattr(
        "context_doctor.settings.MAX_CONCURRENT_RULE_ANALYSES",
        1,
    )

    response = api_client.post(
        "/run",
        data={"flow": "all_rules_analysis", "sql_dialect": "PostgreSQL"},
        files=upload_files,
    )

    assert_response_contains(response, "Waiting for results", 'src="/static/index.js"')
    task_id = task_id_from_response(response)
    payload = wait_for_task(api_client, task_id)

    assert payload["status"] == "completed"
    assert payload["total_rules"] == 2
    assert payload["completed_rules"] == 2
    assert payload["next_index"] == 2
    assert len(payload["pages"]) == 2
    assert "Functional first rule comparison summary." in payload["pages"][0]
    assert "Functional second rule validation summary." in payload["pages"][1]
    no_history_logging["start_async_execution"].assert_called_once()
    no_history_writes["complete_async_execution"].assert_called_once()
    assert_no_pending_responses(dispatcher)
