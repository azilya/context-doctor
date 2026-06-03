"""Context ingestion and normalization for analysis flows."""

import json
from importlib import resources

from pydantic import BaseModel

from .utils import simplify_description


class AnalysisContext(BaseModel):
    raw_schema: dict
    schema_description: dict
    rules_text: str
    sql_dialect: str
    schema_filename: str | None = None
    rules_filename: str | None = None


class ContextStore:
    @staticmethod
    def _read_example_text(name: str) -> str:
        return resources.files("context_doctor.examples").joinpath(name).read_text()

    @classmethod
    def _read_example_json(cls, name: str) -> dict:
        return json.loads(cls._read_example_text(name))

    @classmethod
    def from_examples(cls) -> AnalysisContext:
        schema = cls._read_example_json("schema.json")
        rules_text = cls._read_example_text("rules.md").strip()
        sql_dialect = cls._read_example_text("dialect.txt").strip()
        return cls._build_context(
            raw_schema=schema,
            rules_text=rules_text,
            sql_dialect=sql_dialect,
            schema_filename="schema.json",
            rules_filename="rules.md",
        )

    @classmethod
    def from_uploads(
        cls,
        schema_content: bytes,
        rules_content: bytes,
        sql_dialect: str,
        schema_filename: str | None = None,
        rules_filename: str | None = None,
    ) -> AnalysisContext:
        if not schema_content:
            raise ValueError("Schema JSON file is required")
        if not rules_content:
            raise ValueError("Rules text file is required")

        try:
            schema_text = schema_content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Schema file must be UTF-8 encoded JSON") from exc

        try:
            schema = json.loads(schema_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Schema file is not valid JSON: {exc.msg}") from exc

        if not isinstance(schema, dict):
            raise TypeError("Schema JSON must be an object")

        try:
            rules_text = rules_content.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise ValueError("Rules file must be UTF-8 encoded text") from exc

        return cls._build_context(
            raw_schema=schema,
            rules_text=rules_text,
            sql_dialect=sql_dialect,
            schema_filename=schema_filename,
            rules_filename=rules_filename,
        )

    @staticmethod
    def _build_context(
        raw_schema: dict,
        rules_text: str,
        sql_dialect: str,
        schema_filename: str | None,
        rules_filename: str | None,
    ) -> AnalysisContext:
        if not rules_text:
            raise ValueError("Rules text must not be empty")
        sql_dialect = sql_dialect.strip()
        if not sql_dialect:
            raise ValueError("SQL dialect is required")

        try:
            schema_description = simplify_description(raw_schema)
        except (KeyError, TypeError) as exc:
            raise ValueError(
                "Schema JSON must contain application description, tables, columns, and relations"
            ) from exc

        return AnalysisContext(
            raw_schema=raw_schema,
            schema_description=schema_description,
            rules_text=rules_text,
            sql_dialect=sql_dialect,
            schema_filename=schema_filename,
            rules_filename=rules_filename,
        )
