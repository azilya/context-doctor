"""Business logic for query history tracking.

This service provides high-level methods for tracking query execution,
ensuring that history logging never breaks the main application functionality.
All methods are designed to be non-blocking and fail gracefully.
"""

import logging
from datetime import datetime
from typing import Optional

from ..database.repository import HistoryRepository
from ..database.session import get_db_session

logger = logging.getLogger(__name__)


class HistoryService:
    """Service for managing query history with non-blocking operations."""

    @staticmethod
    def start_sync_execution(
        flow_type: str,
        input_params: dict,
        client_backend_url: str = "",
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[int]:
        """Start tracking a synchronous execution.

        Args:
            flow_type: Type of analysis flow (rule_analysis, question_analysis, rule_generation)
            input_params: Dictionary of input parameters
            client_backend_url: URL of the backend API being queried
            user_agent: User agent from HTTP request
            ip_address: Client IP address

        Returns:
            History entry ID if successful, None if logging failed
            (Failures are logged but don't raise exceptions)
        """
        logger.info(
            f"[HISTORY] Starting sync execution: flow={flow_type}, params={list(input_params.keys())}"
        )

        try:
            with get_db_session() as session:
                logger.debug("[HISTORY] Database session created")
                entry = HistoryRepository.create_entry(
                    session=session,
                    flow_type=flow_type,
                    execution_mode="sync",
                    input_params=input_params,
                    status="running",
                    started_at=datetime.utcnow(),
                    client_backend_url=client_backend_url,
                    user_agent=user_agent,
                    ip_address=ip_address,
                )
                logger.info(
                    f"[HISTORY] ✓ Sync entry created: ID={entry.id}, flow={flow_type}"
                )
                return entry.id
        except Exception as e:
            logger.exception(f"[HISTORY] ✗ Failed to start sync execution: {e}")
            return None

    @staticmethod
    def complete_sync_execution(
        entry_id: Optional[int],
        result_html: str,
        rules_text: str = "",
        schema_json: str = "",
        guidelines_text: str = "",
        duration_seconds: Optional[float] = None,
    ):
        """Mark a synchronous execution as completed.

        Args:
            entry_id: History entry ID (can be None if initial logging failed)
            result_html: Rendered HTML output
            rules_text: Rules used in analysis
            schema_json: Schema description JSON
            guidelines_text: Guidelines used
            duration_seconds: Execution duration in seconds
        """
        if not entry_id:
            logger.warning("[HISTORY] Skipping complete: entry_id is None")
            return

        logger.info(
            f"[HISTORY] Completing sync entry: ID={entry_id}, duration={duration_seconds}s"
        )

        try:
            with get_db_session() as session:
                HistoryRepository.update_entry(
                    session=session,
                    entry_id=entry_id,
                    status="completed",
                    completed_at=datetime.utcnow(),
                    duration_seconds=duration_seconds,
                    result_html=result_html,
                    rules_text=rules_text,
                    schema_json=schema_json,
                    guidelines_text=guidelines_text,
                )
                logger.info(f"[HISTORY] ✓ Sync entry completed: ID={entry_id}")
        except Exception as e:
            logger.exception(
                f"[HISTORY] ✗ Failed to complete: ID={entry_id}, error={e}"
            )

    @staticmethod
    def fail_execution(
        entry_id: Optional[int],
        error_message: str,
        duration_seconds: Optional[float] = None,
    ):
        """Mark an execution as failed.

        Args:
            entry_id: History entry ID (can be None if initial logging failed)
            error_message: Error message describing the failure
            duration_seconds: Execution duration in seconds
        """
        if not entry_id:
            return

        try:
            with get_db_session() as session:
                HistoryRepository.update_entry(
                    session=session,
                    entry_id=entry_id,
                    status="failed",
                    completed_at=datetime.utcnow(),
                    error_message=error_message,
                    duration_seconds=duration_seconds,
                )
        except Exception as e:
            logger.exception(f"Failed to update failed execution: {e}")

    @staticmethod
    def start_async_execution(
        task_id: str,
        flow_type: str,
        input_params: dict,
        client_backend_url: str = "",
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[int]:
        """Start tracking an asynchronous execution.

        Args:
            task_id: Unique task identifier for the async flow
            flow_type: Type of analysis flow (typically 'all_rules_analysis')
            input_params: Dictionary of input parameters
            client_backend_url: URL of the backend API being queried
            user_agent: User agent from HTTP request
            ip_address: Client IP address

        Returns:
            History entry ID if successful, None if logging failed
        """
        logger.info(
            f"[HISTORY] Starting async execution: task_id={task_id}, flow={flow_type}"
        )

        try:
            with get_db_session() as session:
                entry = HistoryRepository.create_entry(
                    session=session,
                    flow_type=flow_type,
                    execution_mode="async",
                    input_params=input_params,
                    status="running",
                    started_at=datetime.utcnow(),
                    task_id=task_id,
                    client_backend_url=client_backend_url,
                    user_agent=user_agent,
                    ip_address=ip_address,
                )
                logger.info(
                    f"[HISTORY] ✓ Async entry created: ID={entry.id}, task_id={task_id}"
                )
                return entry.id
        except Exception as e:
            logger.exception(
                f"[HISTORY] ✗ Failed to start async: task_id={task_id}, error={e}"
            )
            return None

    @staticmethod
    def update_async_progress(
        task_id: str,
        total_rules: Optional[int] = None,
        completed_rules: Optional[int] = None,
        rules_text: Optional[str] = None,
        schema_json: Optional[str] = None,
        guidelines_text: Optional[str] = None,
        client_backend_url: Optional[str] = None,
    ):
        """Update progress for an asynchronous execution.

        Args:
            task_id: Task identifier
            total_rules: Total number of rules to analyze
            completed_rules: Number of rules completed so far
            rules_text: Rules used in analysis
            schema_json: Schema description JSON
            guidelines_text: Guidelines used
            client_backend_url: Backend URL (if not set initially)
        """
        try:
            with get_db_session() as session:
                entry = HistoryRepository.get_by_task_id(session, task_id)
                if entry:
                    updates = {}
                    if total_rules is not None:
                        updates["total_rules"] = total_rules
                    if completed_rules is not None:
                        updates["completed_rules"] = completed_rules
                    if rules_text:
                        updates["rules_text"] = rules_text
                    if schema_json:
                        updates["schema_json"] = schema_json
                    if guidelines_text:
                        updates["guidelines_text"] = guidelines_text
                    if client_backend_url:
                        updates["client_backend_url"] = client_backend_url

                    if updates:
                        HistoryRepository.update_entry(session, entry.id, **updates)
                        logger.debug(
                            f"[HISTORY] Updated async progress: task_id={task_id}, updates={list(updates.keys())}"
                        )
                else:
                    logger.warning(f"[HISTORY] Entry not found for task_id={task_id}")
        except Exception as e:
            logger.exception(
                f"[HISTORY] ✗ Failed to update async progress: task_id={task_id}, error={e}"
            )

    @staticmethod
    def complete_async_execution(
        task_id: str, result_html: str, duration_seconds: float
    ):
        """Mark an asynchronous execution as completed.

        Args:
            task_id: Task identifier
            result_html: Rendered HTML output (all pages concatenated)
            duration_seconds: Total execution duration in seconds
        """
        logger.info(
            f"[HISTORY] Completing async: task_id={task_id}, duration={duration_seconds}s, html_size={len(result_html)} chars"
        )

        try:
            with get_db_session() as session:
                entry = HistoryRepository.get_by_task_id(session, task_id)
                if entry:
                    HistoryRepository.update_entry(
                        session=session,
                        entry_id=entry.id,
                        status="completed",
                        completed_at=datetime.utcnow(),
                        duration_seconds=duration_seconds,
                        result_html=result_html,
                    )
                    logger.info(f"[HISTORY] ✓ Async completed: task_id={task_id}")
                else:
                    logger.warning(f"[HISTORY] Entry not found for task_id={task_id}")
        except Exception as e:
            logger.exception(
                f"[HISTORY] ✗ Failed to complete async: task_id={task_id}, error={e}"
            )

    @staticmethod
    def cancel_async_execution(
        task_id: str,
        duration_seconds: Optional[float] = None,
        partial_result_html: Optional[str] = None,
    ):
        """Mark an asynchronous execution as cancelled.

        Args:
            task_id: Task identifier
            duration_seconds: Execution duration in seconds
            partial_result_html: Partial HTML results before cancellation
        """
        logger.info(
            f"[HISTORY] Cancelling async: task_id={task_id}, has_partial={bool(partial_result_html)}"
        )

        try:
            with get_db_session() as session:
                entry = HistoryRepository.get_by_task_id(session, task_id)
                if entry:
                    updates = {
                        "status": "cancelled",
                        "completed_at": datetime.utcnow(),
                        "duration_seconds": duration_seconds,
                    }
                    # Store partial results if available
                    if partial_result_html:
                        updates["result_html"] = partial_result_html

                    HistoryRepository.update_entry(session, entry.id, **updates)
                    logger.info(f"[HISTORY] ✓ Async cancelled: task_id={task_id}")
                else:
                    logger.warning(f"[HISTORY] Entry not found for task_id={task_id}")
        except Exception as e:
            logger.exception(
                f"[HISTORY] ✗ Failed to cancel async: task_id={task_id}, error={e}"
            )

    @staticmethod
    def fail_async_execution(
        task_id: str,
        error_message: str,
        duration_seconds: Optional[float] = None,
        partial_result_html: Optional[str] = None,
    ):
        """Mark an asynchronous execution as failed.

        Args:
            task_id: Task identifier
            error_message: Error message describing the failure
            duration_seconds: Execution duration in seconds
            partial_result_html: Partial HTML results before failure
        """
        logger.info(
            f"[HISTORY] Failing async: task_id={task_id}, has_partial={bool(partial_result_html)}"
        )

        try:
            with get_db_session() as session:
                entry = HistoryRepository.get_by_task_id(session, task_id)
                if entry:
                    updates = {
                        "status": "failed",
                        "completed_at": datetime.utcnow(),
                        "error_message": error_message,
                        "duration_seconds": duration_seconds,
                    }
                    # Store partial results if available
                    if partial_result_html:
                        updates["result_html"] = partial_result_html

                    HistoryRepository.update_entry(session, entry.id, **updates)
                    logger.info(f"[HISTORY] ✓ Async failed: task_id={task_id}")
                else:
                    logger.warning(f"[HISTORY] Entry not found for task_id={task_id}")
        except Exception as e:
            logger.exception(
                f"[HISTORY] ✗ Failed to update failed async: task_id={task_id}, error={e}"
            )
