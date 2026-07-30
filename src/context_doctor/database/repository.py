"""Data access layer for query history.

This module provides CRUD operations for the QueryHistory model,
abstracting database operations from business logic.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session

from .models import QueryHistory

logger = logging.getLogger(__name__)


class HistoryRepository:
    """Repository for query history database operations."""

    @staticmethod
    def create_entry(
        session: Session,
        flow_type: str,
        execution_mode: str,
        input_params: dict,
        **kwargs,
    ) -> QueryHistory:
        """Create a new history entry.

        Args:
            session: Database session
            flow_type: Type of analysis flow
            execution_mode: 'sync' or 'async'
            input_params: Dictionary of input parameters
            **kwargs: Additional fields (status, started_at, client_backend_url, etc.)

        Returns:
            Created QueryHistory instance with ID assigned
        """
        # Provide defaults only if not specified by caller
        kwargs.setdefault("status", "pending")
        kwargs.setdefault("created_at", datetime.utcnow())

        entry = QueryHistory(
            flow_type=flow_type,
            execution_mode=execution_mode,
            input_params=json.dumps(input_params),
            **kwargs,
        )
        session.add(entry)
        session.flush()  # Get the ID without committing the transaction
        return entry

    @staticmethod
    def update_entry(
        session: Session, entry_id: int, **updates
    ) -> Optional[QueryHistory]:
        """Update an existing history entry.

        Args:
            session: Database session
            entry_id: ID of the entry to update
            **updates: Fields to update

        Returns:
            Updated QueryHistory instance, or None if not found
        """
        entry = session.query(QueryHistory).filter(QueryHistory.id == entry_id).first()
        if entry:
            for key, value in updates.items():
                setattr(entry, key, value)
            session.flush()
        return entry

    @staticmethod
    def get_by_id(session: Session, entry_id: int) -> Optional[QueryHistory]:
        """Get a history entry by ID.

        Args:
            session: Database session
            entry_id: ID of the entry to retrieve

        Returns:
            QueryHistory instance, or None if not found
        """
        return session.query(QueryHistory).filter(QueryHistory.id == entry_id).first()

    @staticmethod
    def get_by_task_id(session: Session, task_id: str) -> Optional[QueryHistory]:
        """Get a history entry by task_id (for async flows).

        Args:
            session: Database session
            task_id: Task ID to search for

        Returns:
            QueryHistory instance, or None if not found
        """
        return (
            session.query(QueryHistory).filter(QueryHistory.task_id == task_id).first()
        )

    @staticmethod
    def list_entries(
        session: Session,
        flow_type: Optional[str] = None,
        status: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[QueryHistory], int]:
        """List history entries with filtering and pagination.

        Args:
            session: Database session
            flow_type: Filter by flow type (optional)
            status: Filter by status (optional)
            search_query: Search in input_params and error_message (optional)
            limit: Maximum number of entries to return
            offset: Number of entries to skip (for pagination)

        Returns:
            Tuple of (list of QueryHistory entries, total count)
        """
        query = session.query(QueryHistory)

        # Apply filters
        if flow_type:
            query = query.filter(QueryHistory.flow_type == flow_type)
        if status:
            query = query.filter(QueryHistory.status == status)
        if search_query:
            # Search in input_params and error_message
            search_pattern = f"%{search_query}%"
            query = query.filter(
                or_(
                    QueryHistory.input_params.like(search_pattern),
                    QueryHistory.error_message.like(search_pattern),
                )
            )

        # Get total count before pagination
        total = query.count()

        # Apply ordering and pagination
        entries = (
            query.order_by(desc(QueryHistory.created_at))
            .limit(limit)
            .offset(offset)
            .all()
        )

        return entries, total

    @staticmethod
    def get_statistics(session: Session, days: int = 7) -> dict:
        """Get aggregate statistics for query history.

        Args:
            session: Database session
            days: Number of days to include in statistics

        Returns:
            Dictionary with statistics:
                - total_queries: Total number of queries
                - by_flow: Count per flow type
                - by_status: Count per status
                - average_duration_seconds: Average execution duration
                - period_days: Number of days included
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Total queries in period
        total = (
            session.query(QueryHistory)
            .filter(QueryHistory.created_at >= cutoff_date)
            .count()
        )

        # Count by flow type
        by_flow = {}
        flow_types = [
            "rule_analysis",
            "all_rules_analysis",
            "question_analysis",
            "rule_generation",
        ]
        for flow_type in flow_types:
            count = (
                session.query(QueryHistory)
                .filter(
                    and_(
                        QueryHistory.flow_type == flow_type,
                        QueryHistory.created_at >= cutoff_date,
                    )
                )
                .count()
            )
            by_flow[flow_type] = count

        # Count by status
        by_status = {}
        statuses = ["completed", "failed", "cancelled", "running"]
        for status in statuses:
            count = (
                session.query(QueryHistory)
                .filter(
                    and_(
                        QueryHistory.status == status,
                        QueryHistory.created_at >= cutoff_date,
                    )
                )
                .count()
            )
            by_status[status] = count

        # Average duration for completed queries
        avg_duration = (
            session.query(func.avg(QueryHistory.duration_seconds))
            .filter(
                and_(
                    QueryHistory.status == "completed",
                    QueryHistory.duration_seconds.isnot(None),
                    QueryHistory.created_at >= cutoff_date,
                )
            )
            .scalar()
            or 0
        )

        return {
            "total_queries": total,
            "by_flow": by_flow,
            "by_status": by_status,
            "average_duration_seconds": round(avg_duration, 2),
            "period_days": days,
        }

    @staticmethod
    def delete_entry(session: Session, entry_id: int) -> bool:
        """Delete a history entry.

        Args:
            session: Database session
            entry_id: ID of the entry to delete

        Returns:
            True if entry was deleted, False if not found
        """
        entry = session.query(QueryHistory).filter(QueryHistory.id == entry_id).first()
        if entry:
            session.delete(entry)
            session.flush()
            return True
        return False
