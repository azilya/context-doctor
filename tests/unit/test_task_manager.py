from unittest.mock import Mock

import pytest

from context_doctor import task_manager
from context_doctor.task_manager import TaskManager, TaskState


@pytest.mark.parametrize(
    ("rules_text", "expected_rules"),
    [
        (
            "Rule #1: Join customers.\nRule #2: Sum revenue.",
            ["Rule #1: Join customers.", "Rule #2: Sum revenue."],
        ),
        ("", []),
    ],
)
def test_split_rules_documents_current_regex_behavior(rules_text, expected_rules):
    # These expectations pin today's regex splitter, including imperfect handling of
    # malformed headings. They document compatibility, not the ideal parser shape.
    assert TaskManager._split_rules(rules_text) == expected_rules


def manager_with_task(status="pending"):
    manager = TaskManager()
    manager._tasks["task-id"] = TaskState(task_id="task-id", status=status)
    return manager


def test_new_task_state_is_pending():
    manager = manager_with_task()

    assert manager.get_status("task-id")["status"] == "pending"


def test_cancel_task_marks_running_task_cancelled():
    manager = manager_with_task(status="running")

    assert manager.cancel_task("task-id") is True
    assert manager.get_status("task-id")["status"] == "cancelled"
    assert manager._is_cancelled("task-id") is True
    assert manager.cancel_task("missing") is False
    assert manager.get_status("missing") is None


def test_get_status_returns_incremental_pages_for_polling():
    manager = manager_with_task(status="running")
    manager._tasks["task-id"].results = {
        2: "<p>Rule #3</p>",
        0: "<p>Rule #1</p>",
        1: None,
    }

    status = manager.get_status("task-id", from_index=1)

    assert status["pages"] == ["<p>Rule #3</p>"]
    assert status["next_index"] == 3

    status_after_known_results = manager.get_status("task-id", from_index=3)

    assert status_after_known_results["pages"] == []
    assert status_after_known_results["next_index"] == 3


def test_joined_results_returns_ordered_non_empty_html():
    manager = manager_with_task()
    manager._tasks["task-id"].results = {
        2: "<p>third</p>",
        0: "<p>first</p>",
        1: None,
    }

    assert manager._joined_results("task-id") == "<p>first</p><p>third</p>"


def test_analyze_one_skips_empty_results(monkeypatch: pytest.MonkeyPatch):
    manager = TaskManager()
    empty_result = [
        {"Category": "typos", "Details": ""},
        {"Category": "dialect_inconsistencies", "Details": ""},
        {"Category": "contradictions_explained", "Details": ""},
        {"Category": "contradictions_with_rules", "Details": ""},
        {"Category": "contradictions_with_schema", "Details": ""},
        {"Category": "duplications_explained", "Details": ""},
        {"Category": "duplications_with_rules", "Details": ""},
        {"Category": "duplications_with_schema", "Details": ""},
        {"Category": "guideline_violations", "Details": ""},
    ]
    analyze_single_rule_pipeline = Mock(return_value=empty_result)
    prettify_html = Mock(
        side_effect=AssertionError("empty results should not render HTML")
    )
    monkeypatch.setattr(
        task_manager, "analyze_single_rule_pipeline", analyze_single_rule_pipeline
    )
    monkeypatch.setattr(task_manager, "prettify_html", prettify_html)

    result = manager._analyze_one("Rule #1", ["Rule #1"], "PostgreSQL", {})

    assert result is None
    analyze_single_rule_pipeline.assert_called_once_with(
        "Rule #1", ["Rule #1"], "PostgreSQL", {}
    )
    prettify_html.assert_not_called()


def test_run_all_rules_analysis_completes_with_mocked_rule_analysis(
    monkeypatch: pytest.MonkeyPatch,
    analysis_context: task_manager.AnalysisContext,
    no_history_writes: dict[str, Mock],
):
    manager = manager_with_task()
    monkeypatch.setattr(task_manager.settings, "MAX_CONCURRENT_RULE_ANALYSES", 1)
    analyze_one = Mock(side_effect=lambda rule, *_: f"<p>{rule}</p>")
    monkeypatch.setattr(manager, "_analyze_one", analyze_one)

    manager._run_all_rules_analysis("task-id", analysis_context)

    status = manager.get_status("task-id")
    assert status["status"] == "completed"
    assert status["total_rules"] == 2
    assert status["completed_rules"] == 2
    assert status["pages"] == [
        "<p>Rule #1: ALWAYS join orders to customers on customer_id.\n</p>",
        "<p>Rule #2: WHEN users ask for revenue, use SUM(orders.revenue).</p>",
    ]
    assert status["next_index"] == 2
    assert status["rules_text"] == analysis_context.rules_text
    assert "orders" in status["schema_json"]
    assert status["guidelines_text"]
    assert analyze_one.call_count == 2
    no_history_writes["complete_async_execution"].assert_called_once()


def test_run_all_rules_analysis_respects_preexisting_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    analysis_context: task_manager.AnalysisContext,
    no_history_writes: dict[str, Mock],
):
    manager = manager_with_task()
    manager._tasks["task-id"].cancelled = True
    monkeypatch.setattr(task_manager.settings, "MAX_CONCURRENT_RULE_ANALYSES", 1)
    analyze_one = Mock()
    monkeypatch.setattr(manager, "_analyze_one", analyze_one)

    manager._run_all_rules_analysis("task-id", analysis_context)

    status = manager.get_status("task-id")
    assert status["status"] == "cancelled"
    assert status["total_rules"] == 2
    assert status["completed_rules"] == 0
    assert status["pages"] == []
    assert status["rules_text"] == analysis_context.rules_text
    assert "orders" in status["schema_json"]
    assert status["guidelines_text"]
    analyze_one.assert_not_called()
    no_history_writes["cancel_async_execution"].assert_called_once()


def test_run_all_rules_analysis_records_failure_without_real_llm(
    monkeypatch: pytest.MonkeyPatch,
    analysis_context: task_manager.AnalysisContext,
    no_history_writes: dict[str, Mock],
):
    manager = manager_with_task()
    monkeypatch.setattr(task_manager.settings, "MAX_CONCURRENT_RULE_ANALYSES", 1)
    monkeypatch.setattr(manager, "_analyze_one", Mock(side_effect=RuntimeError("boom")))

    manager._run_all_rules_analysis("task-id", analysis_context)

    status = manager.get_status("task-id")
    assert status["status"] == "failed"
    assert status["error"] == "boom"
    no_history_writes["fail_async_execution"].assert_called_once()


def test_run_all_rules_analysis_failure_retains_partial_results(
    monkeypatch: pytest.MonkeyPatch,
    analysis_context: task_manager.AnalysisContext,
    no_history_writes: dict[str, Mock],
):
    manager = manager_with_task()
    monkeypatch.setattr(task_manager.settings, "MAX_CONCURRENT_RULE_ANALYSES", 1)
    analyze_one = Mock(side_effect=["<p>first result</p>", RuntimeError("boom")])
    monkeypatch.setattr(manager, "_analyze_one", analyze_one)

    manager._run_all_rules_analysis("task-id", analysis_context)

    status = manager.get_status("task-id")
    assert status["status"] == "failed"
    assert status["completed_rules"] == 1
    assert status["pages"] == ["<p>first result</p>"]
    assert status["next_index"] == 1
    assert status["error"] == "boom"
    no_history_writes["fail_async_execution"].assert_called_once()
    _, fail_kwargs = no_history_writes["fail_async_execution"].call_args
    assert fail_kwargs["partial_result_html"] == "<p>first result</p>"


def test_history_write_failures_do_not_break_task_completion(
    monkeypatch: pytest.MonkeyPatch,
    analysis_context: task_manager.AnalysisContext,
):
    manager = manager_with_task()
    monkeypatch.setattr(task_manager.settings, "MAX_CONCURRENT_RULE_ANALYSES", 1)
    monkeypatch.setattr(manager, "_analyze_one", Mock(return_value="<p>ok</p>"))
    monkeypatch.setattr(
        task_manager.HistoryService,
        "update_async_progress",
        Mock(side_effect=RuntimeError("history unavailable")),
    )
    monkeypatch.setattr(
        task_manager.HistoryService,
        "complete_async_execution",
        Mock(side_effect=RuntimeError("history unavailable")),
    )

    manager._run_all_rules_analysis("task-id", analysis_context)

    status = manager.get_status("task-id")
    assert status["status"] == "completed"
    assert status["completed_rules"] == 2
