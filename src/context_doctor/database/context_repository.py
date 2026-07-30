"""Database operations for persisted analysis contexts."""

import json
from datetime import datetime

from sqlalchemy.orm import Session

from .models import StoredContext


class ContextRepository:
    """Small repository isolating context persistence from validation logic."""

    @staticmethod
    def get(session: Session, context_id: str) -> StoredContext | None:
        """Return one stored context by identifier.

        Args:
            session: Active database session.
            context_id: Stable context identifier.

        Returns:
            Stored context record, or ``None`` when it does not exist.
        """
        # Primary-key lookup is sufficient because context identifiers are opaque
        # and globally unique within this application database.
        return session.get(StoredContext, context_id)

    @classmethod
    def upsert(
        cls, session: Session, context_id: str, context, now: datetime
    ) -> StoredContext:
        """Create or replace a context while preserving its creation time.

        Args:
            session: Active database session.
            context_id: Identifier to create or replace.
            context: Validated analysis context to serialize.
            now: Timestamp used for creation and last-use tracking.

        Returns:
            Newly created or updated persistence record.
        """
        record = cls.get(session, context_id)
        if record is None:
            record = StoredContext(context_id=context_id, created_at=now)
            session.add(record)
        # Store both raw and normalized forms for traceability and fast inspection;
        # loading still revalidates raw data at the service boundary.
        record.raw_schema_json = json.dumps(context.raw_schema, ensure_ascii=False)
        record.schema_description_json = json.dumps(
            context.schema_description, ensure_ascii=False
        )
        record.rules_text = context.rules_text
        record.sql_dialect = context.sql_dialect
        record.schema_filename = context.schema_filename
        record.rules_filename = context.rules_filename
        record.last_used_at = now
        session.flush()
        return record

    @staticmethod
    def touch(session: Session, record: StoredContext, now: datetime) -> None:
        """Update last-used time for retention accounting.

        Args:
            session: Active database session.
            record: Context record being reused.
            now: New last-used timestamp.
        """
        # Touching on every successful load makes expiry reflect actual reuse rather
        # than only the original upload date.
        record.last_used_at = now
        session.flush()

    @classmethod
    def delete(cls, session: Session, context_id: str) -> bool:
        """Delete a context when it exists.

        Args:
            session: Active database session.
            context_id: Identifier to delete.

        Returns:
            Whether a stored record was found and deleted.
        """
        record = cls.get(session, context_id)
        if record is None:
            return False
        session.delete(record)
        session.flush()
        return True

    @staticmethod
    def delete_older_than(session: Session, cutoff: datetime) -> int:
        """Bulk-delete contexts last used before the cutoff.

        Args:
            session: Active database session.
            cutoff: Exclusive upper bound for the last-used timestamp.

        Returns:
            Number of deleted records.
        """
        # A single database-side delete bounds startup cleanup cost and avoids
        # loading expired uploaded schemas into application memory.
        return (
            session.query(StoredContext)
            .filter(StoredContext.last_used_at < cutoff)
            .delete(synchronize_session=False)
        )
