"""Real-server fixtures for browser integration tests."""

from __future__ import annotations

import socket
import time
from collections.abc import Iterator
from threading import Thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, sync_playwright


class StructuredResponseDispatcher:
    """Return queued typed LLM responses without allowing network access."""

    def __init__(self) -> None:
        self.pending: list[object] = []

    def queue(self, *responses: object) -> None:
        self.pending.extend(responses)

    def __call__(self, _messages: object, text_format: type[object]) -> object:
        for index, response in enumerate(self.pending):
            if isinstance(response, text_format):
                return self.pending.pop(index)
        remaining = [type(response).__name__ for response in self.pending]
        raise AssertionError(
            f"No fake {text_format.__name__} response left; remaining={remaining}"
        )

    def assert_drained(self) -> None:
        assert self.pending == []


@pytest.fixture
def llm_dispatcher(monkeypatch: pytest.MonkeyPatch) -> StructuredResponseDispatcher:
    """Patch only the external structured-response boundary."""
    from context_doctor.flows import (
        question_analysis as question_analysis_flow,
        rule_analysis as rule_analysis_flow,
        rule_generation as rule_generation_flow,
    )

    dispatcher = StructuredResponseDispatcher()
    monkeypatch.setattr(rule_analysis_flow, "parse_response", dispatcher)
    monkeypatch.setattr(question_analysis_flow, "parse_response", dispatcher)
    monkeypatch.setattr(rule_generation_flow, "parse_response", dispatcher)
    return dispatcher


@pytest.fixture
def app_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Serve the real app with in-memory context/history seams for one test."""
    from context_doctor import fastapi_app
    from context_doctor import task_manager as task_manager_module
    from context_doctor.services import context_service
    from context_doctor.services.history_service import HistoryService
    from context_doctor.task_manager import TaskManager

    contexts: dict[str, object] = {}

    def save(context, replace_context_id=None):
        context_id = replace_context_id or f"ui-context-{len(contexts) + 1}"
        persisted = context.model_copy(update={"context_id": context_id}, deep=True)
        contexts[context_id] = persisted
        return persisted

    def get(context_id):
        return contexts.get(context_id)

    monkeypatch.setattr(context_service.ContextService, "save", staticmethod(save))
    monkeypatch.setattr(context_service.ContextService, "get", staticmethod(get))
    monkeypatch.setattr(
        context_service.ContextService, "delete_expired", staticmethod(lambda _age: 0)
    )
    monkeypatch.setattr(fastapi_app, "init_db", lambda: None)
    monkeypatch.setattr(fastapi_app, "task_manager", TaskManager())
    monkeypatch.setattr(
        "context_doctor.settings.MAX_CONCURRENT_RULE_ANALYSES", 1
    )

    history_methods = {
        name: Mock(return_value=1)
        for name in (
            "start_sync_execution",
            "complete_sync_execution",
            "fail_execution",
            "start_async_execution",
            "update_async_progress",
            "complete_async_execution",
            "cancel_async_execution",
            "fail_async_execution",
        )
    }
    for name, method in history_methods.items():
        monkeypatch.setattr(HistoryService, name, method)
    monkeypatch.setattr(task_manager_module, "HistoryService", HistoryService)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(fastapi_app.app, log_level="warning", access_log=False)
    )
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "Uvicorn did not start"

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive(), "Uvicorn did not stop"


@pytest.fixture
def ui_page(app_url: str) -> Iterator[Page]:
    """A Chromium page pointed at the isolated live FastAPI application."""
    with sync_playwright() as playwright:
        browser: Browser = playwright.chromium.launch()
        page = browser.new_page(base_url=app_url)
        try:
            yield page
        finally:
            browser.close()


@pytest.fixture
def context_files(tmp_path):
    schema = tmp_path / "schema.json"
    schema.write_text(
        """{
  "description": "Revenue analytics application.",
  "tables": [
    {
      "originalName": "orders",
      "description": "Order facts.",
      "columns": [
        {"originalName": "revenue", "description": "Revenue in USD.", "type": "numeric"}
      ],
      "relations": {}
    }
  ]
}"""
    )
    rules = tmp_path / "rules.md"
    rules.write_text(
        "Rule #1: Use orders for revenue.\n\n"
        "Rule #2: Use SUM(orders.revenue) for revenue totals."
    )
    return SimpleNamespace(schema=schema, rules=rules)
