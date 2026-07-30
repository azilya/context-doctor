from unittest.mock import Mock

from context_doctor import fastapi_app
from tests.conftest import assert_response_contains, fake_history_entry


def test_history_page_uses_repository_boundary(
    monkeypatch, api_client, history_session
):
    list_entries = Mock(return_value=([], 0))
    get_statistics = Mock(
        return_value={
            "total_queries": 4,
            "average_duration_seconds": 1.25,
            "by_status": {"completed": 3, "failed": 1},
        }
    )
    monkeypatch.setattr(fastapi_app.HistoryRepository, "list_entries", list_entries)
    monkeypatch.setattr(fastapi_app.HistoryRepository, "get_statistics", get_statistics)

    response = api_client.get(
        "/history?flow=rule_analysis&status=completed&search=revenue&page=2&limit=5"
    )

    assert_response_contains(
        response, "Query History", "No History Found", "Total Queries"
    )
    list_entries.assert_called_once_with(
        session=history_session,
        flow_type="rule_analysis",
        status="completed",
        search_query="revenue",
        limit=5,
        offset=5,
    )
    get_statistics.assert_called_once_with(history_session, days=7)


def test_history_page_renders_error_fallback_when_repository_raises(
    monkeypatch,
    api_client,
    history_session,
):
    monkeypatch.setattr(
        fastapi_app.HistoryRepository,
        "list_entries",
        Mock(side_effect=RuntimeError("history unavailable")),
    )

    response = api_client.get("/history")

    assert_response_contains(response, "history unavailable", "No History Found")


def test_history_detail_uses_repository_boundary(
    monkeypatch, api_client, history_session
):
    entry = fake_history_entry()
    get_by_id = Mock(return_value=entry)
    monkeypatch.setattr(fastapi_app.HistoryRepository, "get_by_id", get_by_id)

    response = api_client.get("/history/42")

    assert_response_contains(
        response,
        "Query History Entry #42",
        "Rule #9: Use SUM(revenue).",
        "analysis result",
        "Guideline text",
    )
    get_by_id.assert_called_once_with(history_session, 42)


def test_history_detail_unknown_entry_returns_404(
    monkeypatch, api_client, history_session
):
    monkeypatch.setattr(
        fastapi_app.HistoryRepository, "get_by_id", Mock(return_value=None)
    )

    response = api_client.get("/history/404")

    assert response.status_code == 404
    assert response.json() == {"detail": "History entry not found"}


def test_history_stats_uses_repository_boundary(
    monkeypatch, api_client, history_session
):
    get_statistics = Mock(return_value={"total_queries": 3, "period_days": 14})
    monkeypatch.setattr(fastapi_app.HistoryRepository, "get_statistics", get_statistics)

    response = api_client.get("/api/history/stats?days=14")

    assert response.status_code == 200
    assert response.json() == {"total_queries": 3, "period_days": 14}
    get_statistics.assert_called_once_with(history_session, days=14)


def test_delete_history_entry_uses_repository_boundary(
    monkeypatch,
    api_client,
    history_session,
):
    delete_entry = Mock(return_value=True)
    monkeypatch.setattr(fastapi_app.HistoryRepository, "delete_entry", delete_entry)

    response = api_client.delete("/api/history/42")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "id": 42}
    delete_entry.assert_called_once_with(history_session, 42)


def test_delete_history_entry_unknown_entry_returns_404(
    monkeypatch,
    api_client,
    history_session,
):
    monkeypatch.setattr(
        fastapi_app.HistoryRepository,
        "delete_entry",
        Mock(return_value=False),
    )

    response = api_client.delete("/api/history/404")

    assert response.status_code == 404
    assert response.json() == {"detail": "History entry not found"}
