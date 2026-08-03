import json

import pytest

from context_doctor.context_store import ContextStore


def test_from_uploads_builds_normalized_context(
    valid_schema,
    valid_schema_bytes,
    valid_rules_bytes,
):
    context = ContextStore.from_uploads(
        schema_content=valid_schema_bytes,
        rules_content=valid_rules_bytes,
        sql_dialect=" PostgreSQL ",
        schema_filename="uploaded-schema.json",
        rules_filename="uploaded-rules.md",
    )

    assert context.raw_schema == valid_schema
    assert context.schema_filename == "uploaded-schema.json"
    assert context.rules_filename == "uploaded-rules.md"
    assert context.sql_dialect == "PostgreSQL"
    assert context.rules_text.startswith("Rule #1")
    assert context.schema_description == {
        "application_description": "Revenue analytics application.",
        "tables": {
            "customers": {
                "description": "Customer dimension table.",
                "columns": {
                    "customer_id": {
                        "description": "Unique customer identifier.",
                        "type": "integer",
                    },
                    "region": {
                        "description": "Customer sales region.",
                        "type": "text",
                    },
                },
                "foreign_keys": [],
            },
            "orders": {
                "description": "Order fact table.",
                "columns": {
                    "order_id": {
                        "description": "Unique order identifier.",
                        "type": "integer",
                    },
                    "customer_id": {
                        "description": "Customer identifier on each order.",
                        "type": "integer",
                    },
                    "revenue": {
                        "description": "Order revenue in USD.",
                        "type": "numeric",
                    },
                },
                "foreign_keys": ["orders.customer_id -> customers.customer_id"],
            },
        },
    }


@pytest.mark.parametrize(
    ("schema_content", "expected_error", "expected_message"),
    [
        (b"", ValueError, "Schema JSON file is required"),
        (b"{not-json", ValueError, "Schema file is not valid JSON"),
        (b"[]", TypeError, "Schema JSON must be an object"),
        (b"\xff", ValueError, "Schema file must be UTF-8 encoded JSON"),
    ],
)
def test_from_uploads_rejects_invalid_schema_boundary_inputs(
    schema_content,
    expected_error,
    expected_message,
    valid_rules_bytes,
):
    with pytest.raises(expected_error, match=expected_message):
        ContextStore.from_uploads(schema_content, valid_rules_bytes, "PostgreSQL")


def test_from_uploads_requires_schema_shape(valid_rules_bytes):
    incomplete_schema = json.dumps({"description": "missing tables"}).encode("utf-8")

    with pytest.raises(ValueError) as error:
        ContextStore.from_uploads(incomplete_schema, valid_rules_bytes, "PostgreSQL")

    assert "application description, tables, columns, and relations" in str(error.value)


@pytest.mark.parametrize(
    ("rules_content", "sql_dialect", "expected_message"),
    [
        (b"", "PostgreSQL", "Rules text file is required"),
        (b" \n\t", "PostgreSQL", "Rules text must not be empty"),
        (b"Rule #1: Use revenue.", "  ", "SQL dialect is required"),
        (b"\xff", "PostgreSQL", "Rules file must be UTF-8 encoded text"),
    ],
)
def test_from_uploads_rejects_invalid_rules_and_dialect(
    rules_content,
    sql_dialect,
    expected_message,
    valid_schema_bytes,
):
    with pytest.raises(ValueError, match=expected_message):
        ContextStore.from_uploads(valid_schema_bytes, rules_content, sql_dialect)
