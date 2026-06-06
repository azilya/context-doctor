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
        (
            "Intro text\nRule #1: Join customers.",
            ["Rule #Intro text", "Rule #1: Join customers."],
        ),
        (
            "Rule 1: Missing hash.\nRule #2: Sum revenue.",
            ["Rule #Rule 1: Missing hash.", "Rule #2: Sum revenue."],
        ),
        ("Always join customers.", ["Rule #Always join customers."]),
        ("", []),
        (" \n ", ["Rule # \n "]),
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
