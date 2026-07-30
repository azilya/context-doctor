"""Validated context ingestion and persistent context lifecycle services."""

import json
from datetime import UTC, datetime, timedelta
from importlib import resources
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from ..database.context_repository import ContextRepository
from ..database.session import get_db_session
from ..utils import simplify_description


class AnalysisContext(BaseModel):
    """Immutable snapshot of all inputs used by an analysis.

    Attributes:
        context_id: Stable identifier of the persisted source context.
        raw_schema: Original uploaded schema object.
        schema_description: Normalized schema sent to analysis flows.
        rules_text: Uploaded SQL-generation rules.
        sql_dialect: SQL dialect associated with the rules.
        schema_filename: Original schema filename, when supplied.
        rules_filename: Original rules filename, when supplied.
    """

    model_config = ConfigDict(frozen=True)

    context_id: str | None = None
    raw_schema: dict
    schema_description: dict
    rules_text: str
    sql_dialect: str
    schema_filename: str | None = None
    rules_filename: str | None = None

    def snapshot(self) -> "AnalysisContext":
        """Return a deep, immutable copy safe for a background task.

        Returns:
            Independent context whose nested schema values cannot be affected by
            later replacements of the persisted context.
        """
        # Pydantic's deep copy prevents callers mutating a nested uploaded mapping
        # from changing a task after it has started.
        return self.model_copy(deep=True)


class ContextService:
    """Ingest, normalize, persist, retrieve, and expire analysis contexts."""

    @staticmethod
    def _read_example_text(name: str) -> str:
        """Read a bundled example resource.

        Args:
            name: Package-relative example filename.

        Returns:
            UTF-8 resource contents.
        """
        return resources.files("context_doctor.examples").joinpath(name).read_text()

    @classmethod
    def _read_example_json(cls, name: str) -> dict:
        """Read a bundled JSON example.

        Args:
            name: Package-relative example filename.

        Returns:
            Decoded JSON object.
        """
        return json.loads(cls._read_example_text(name))

    @classmethod
    def from_examples(cls) -> AnalysisContext:
        """Build a validated context from bundled examples.

        Returns:
            Immutable example context.
        """
        schema = cls._read_example_json("schema.json")
        return cls._build_context(
            raw_schema=schema,
            rules_text=cls._read_example_text("rules.md").strip(),
            sql_dialect=cls._read_example_text("dialect.txt").strip(),
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
        """Validate uploaded bytes and build an immutable context.

        Args:
            schema_content: UTF-8 JSON schema bytes.
            rules_content: UTF-8 rules bytes.
            sql_dialect: Non-empty SQL dialect name.
            schema_filename: Original schema filename.
            rules_filename: Original rules filename.

        Returns:
            Validated context snapshot.

        Raises:
            TypeError: If schema JSON is not an object.
            ValueError: If an upload is absent, malformed, or incomplete.
        """
        if not schema_content:
            raise ValueError("Schema JSON file is required")
        if not rules_content:
            raise ValueError("Rules text file is required")

        # Decode each user-controlled input explicitly so validation errors remain
        # actionable at the HTTP boundary.
        try:
            schema = json.loads(schema_content.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ValueError("Schema file must be UTF-8 encoded JSON") from exc
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
        context_id: str | None = None,
    ) -> AnalysisContext:
        """Normalize validated source values into an analysis context.

        Args:
            raw_schema: Decoded schema object.
            rules_text: Rules source text.
            sql_dialect: SQL dialect name.
            schema_filename: Original schema filename.
            rules_filename: Original rules filename.
            context_id: Existing persistent identifier, when loading.

        Returns:
            Immutable normalized context.

        Raises:
            ValueError: If required content or schema fields are absent.
        """
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
            context_id=context_id,
            raw_schema=raw_schema,
            schema_description=schema_description,
            rules_text=rules_text,
            sql_dialect=sql_dialect,
            schema_filename=schema_filename,
            rules_filename=rules_filename,
        )

    @classmethod
    def save(
        cls, context: AnalysisContext, replace_context_id: str | None = None
    ) -> AnalysisContext:
        """Create a context or explicitly replace an existing identifier.

        Args:
            context: Validated source context.
            replace_context_id: Identifier to replace; omitted means create.

        Returns:
            Persisted immutable snapshot with a context identifier.

        Raises:
            KeyError: If an explicitly replaced context does not exist.
        """
        context_id = replace_context_id or uuid4().hex
        now = datetime.now(UTC).replace(tzinfo=None)
        # Repository work is kept behind the service so routes never manipulate
        # persistence records or serialized schema directly.
        with get_db_session() as session:
            if replace_context_id and not ContextRepository.get(session, context_id):
                raise KeyError(f"Context not found: {context_id}")
            ContextRepository.upsert(session, context_id, context, now)
        return context.model_copy(update={"context_id": context_id}, deep=True)

    @classmethod
    def get(cls, context_id: str) -> AnalysisContext | None:
        """Load a context and update its last-used time.

        Args:
            context_id: Persistent context identifier.

        Returns:
            Immutable snapshot, or ``None`` when unknown.
        """
        with get_db_session() as session:
            record = ContextRepository.get(session, context_id)
            if record is None:
                return None
            ContextRepository.touch(
                session, record, datetime.now(UTC).replace(tzinfo=None)
            )
            # Re-normalize stored raw data to detect incompatible/corrupt records
            # before they reach an LLM-backed flow.
            return cls._build_context(
                raw_schema=json.loads(record.raw_schema_json),
                rules_text=record.rules_text,
                sql_dialect=record.sql_dialect,
                schema_filename=record.schema_filename,
                rules_filename=record.rules_filename,
                context_id=record.context_id,
            )

    @staticmethod
    def delete(context_id: str) -> bool:
        """Delete a persisted context.

        Args:
            context_id: Persistent context identifier.

        Returns:
            Whether a record was deleted.
        """
        with get_db_session() as session:
            return ContextRepository.delete(session, context_id)

    @staticmethod
    def delete_expired(max_age_seconds: int) -> int:
        """Delete contexts not used within a bounded retention period.

        Args:
            max_age_seconds: Maximum inactivity age in seconds.

        Returns:
            Number of deleted records.

        Raises:
            ValueError: If the retention age is not positive.
        """
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
            seconds=max_age_seconds
        )
        with get_db_session() as session:
            return ContextRepository.delete_older_than(session, cutoff)
