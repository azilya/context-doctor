import json
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient


class ParseResponseRecorder:
    """Records structured LLM parse calls while returning typed fake responses."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, messages, text_format):
        if not self.responses:
            raise AssertionError("parse_response was called more times than expected")

        response = self.responses.pop(0)
        if not isinstance(response, text_format):
            raise AssertionError(
                f"Expected {text_format.__name__}, got {type(response).__name__}"
            )

        self.calls.append({"messages": messages, "text_format": text_format})
        return response

    def only_call(self):
        if len(self.calls) != 1:
            raise AssertionError(f"Expected 1 parse_response call, got {len(self.calls)}")
        return self.calls[0]


@pytest.fixture(autouse=True)
def block_real_openai_client(monkeypatch):
    # Tests must mock LLM boundaries explicitly; accidental credentials should never
    # turn unit coverage into live OpenAI-compatible API traffic.
    import context_doctor.llm_client as llm_client

    def fail_if_unmocked():
        raise AssertionError("Tests must not create a real OpenAI client")

    monkeypatch.setattr(llm_client, "get_openai_client", fail_if_unmocked)


@pytest.fixture
def parse_response_recorder():
    return ParseResponseRecorder


def assert_response_contains(response, *fragments):
    assert response.status_code == 200
    for fragment in fragments:
        assert fragment in response.text


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


@pytest.fixture
def api_client():
    from context_doctor import fastapi_app

    with TestClient(fastapi_app.app) as client:
        yield client


def make_upload_files(schema_content, rules_content):
    return {
        "schema_file": ("schema.json", schema_content, "application/json"),
        "rules_file": ("rules.md", rules_content, "text/markdown"),
    }


@pytest.fixture
def upload_files(valid_schema_bytes, valid_rules_bytes):
    return make_upload_files(valid_schema_bytes, valid_rules_bytes)


@pytest.fixture
def post_run(api_client, upload_files):
    def _post_run(data, files=None):
        return api_client.post("/run", data=data, files=files or upload_files)

    return _post_run


def session_context(session):
    @contextmanager
    def fake_db_session():
        yield session

    return fake_db_session


@pytest.fixture
def history_session(monkeypatch):
    from context_doctor import fastapi_app

    session = object()
    monkeypatch.setattr(fastapi_app, "get_db_session", session_context(session))
    return session


@pytest.fixture
def valid_schema():
    return {
        "description": "Revenue analytics application.",
        "tables": [
            {
                "originalName": "customers",
                "description": "Customer dimension table.",
                "columns": [
                    {
                        "originalName": "customer_id",
                        "description": "Unique customer identifier.",
                        "type": "integer",
                    },
                    {
                        "originalName": "region",
                        "description": "Customer sales region.",
                        "type": "text",
                    },
                ],
                "relations": {},
            },
            {
                "originalName": "orders",
                "description": "Order fact table.",
                "columns": [
                    {
                        "originalName": "order_id",
                        "description": "Unique order identifier.",
                        "type": "integer",
                    },
                    {
                        "originalName": "customer_id",
                        "description": "Customer identifier on each order.",
                        "type": "integer",
                    },
                    {
                        "originalName": "revenue",
                        "description": "Order revenue in USD.",
                        "type": "numeric",
                    },
                ],
                "relations": {
                    "customer_id": ["orders.customer_id -> customers.customer_id"]
                },
            },
        ],
    }


@pytest.fixture
def valid_schema_bytes(valid_schema):
    return json.dumps(valid_schema).encode("utf-8")


@pytest.fixture
def valid_rules_text():
    return (
        "Rule #1: ALWAYS join orders to customers on customer_id.\n\n"
        "Rule #2: WHEN users ask for revenue, use SUM(orders.revenue)."
    )


@pytest.fixture
def valid_rules_bytes(valid_rules_text):
    return valid_rules_text.encode("utf-8")


@pytest.fixture
def sql_dialect():
    return "PostgreSQL"


@pytest.fixture
def analysis_context(valid_schema_bytes, valid_rules_bytes, sql_dialect):
    from context_doctor.context_store import ContextStore

    return ContextStore.from_uploads(
        schema_content=valid_schema_bytes,
        rules_content=valid_rules_bytes,
        sql_dialect=sql_dialect,
        schema_filename="schema.json",
        rules_filename="rules.md",
    )


@pytest.fixture
def category_result():
    from context_doctor.rule_analysis_flow import CategoryResult

    return CategoryResult(
        explanation="Conflicts with an existing revenue rule.",
        matched_rules=[2, 4],
        matched_from_schema=["orders.revenue", "customers.region"],
    )


@pytest.fixture
def accept_new_rule_response(category_result):
    from context_doctor.rule_analysis_flow import AcceptNewRule

    return AcceptNewRule(
        analysis_summary="The new rule overlaps with revenue guidance.",
        typos=["revnue should be revenue"],
        dialect_inconsistencies=["Use DATE_TRUNC for PostgreSQL."],
        contradictions=category_result,
        duplications=category_result,
    )


@pytest.fixture
def question_analysis_response():
    from context_doctor.question_analysis_flow import QuestionAnalysis

    return QuestionAnalysis(
        analysis_summary="The filtered rules answer the question.",
        typos=["#1: custmer should be customer"],
        dialect_inconsistencies=["Use ILIKE in PostgreSQL."],
        contradictions=["Rule #1 conflicts with the schema."],
        duplications=["Rule #2 repeats the revenue column description."],
    )


@pytest.fixture
def relevant_description():
    from context_doctor.question_analysis_flow import RelevantDescription

    return RelevantDescription(
        type="column",
        name="orders.revenue",
        description="Order revenue\nin USD.",
    )


@pytest.fixture
def relevant_context_response(relevant_description):
    from context_doctor.question_analysis_flow import RelevantContext

    return RelevantContext(
        analysis_summary="Revenue rules and columns are relevant.",
        relevant_rules=["Rule #2: Use SUM(orders.revenue)."],
        relevant_descriptions=[relevant_description],
    )


@pytest.fixture
def rule_suggestion_response():
    from context_doctor.rule_generation_flow import RuleSuggestion

    return RuleSuggestion(
        analysis_summary="A revenue aggregation rule solves the problem.",
        suggested_rule="Rule #3: WHEN users ask for revenue, use SUM(orders.revenue).",
    )


@pytest.fixture
def no_history_writes(monkeypatch):
    from context_doctor.services.history_service import HistoryService

    methods = {
        name: Mock()
        for name in [
            "update_async_progress",
            "complete_async_execution",
            "cancel_async_execution",
            "fail_async_execution",
        ]
    }
    for name, method in methods.items():
        monkeypatch.setattr(HistoryService, name, method)
    return methods


@pytest.fixture
def no_history_logging(monkeypatch):
    from context_doctor.services.history_service import HistoryService

    methods = {
        "start_sync_execution": Mock(return_value=101),
        "complete_sync_execution": Mock(),
        "fail_execution": Mock(),
        "start_async_execution": Mock(return_value=202),
    }
    for name, method in methods.items():
        monkeypatch.setattr(HistoryService, name, method)
    return methods
