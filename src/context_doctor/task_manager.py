import json
import logging
import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from threading import Lock, Thread
from uuid import uuid4

from . import settings
from .context_store import AnalysisContext
from .rule_analysis_flow import analyze_single_rule_pipeline, guidelines
from .services.history_service import HistoryService
from .utils import prettify_html


@dataclass
class TaskState:
    task_id: str
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    total_rules: int = 0
    completed_rules: int = 0
    results: dict[int, str | None] = field(default_factory=dict)
    error: str | None = None
    rules_text: str = ""
    schema_json: str = ""
    guidelines_text: str = ""
    cancelled: bool = False


class TaskManager:
    def __init__(self):
        self._lock = Lock()
        self._tasks: dict[str, TaskState] = {}

    def start_all_rules_analysis(self, context: AnalysisContext) -> str:
        task_id = uuid4().hex
        state = TaskState(task_id=task_id)
        with self._lock:
            self._tasks[task_id] = state
        thread = Thread(
            target=self._run_all_rules_analysis, args=(task_id, context), daemon=True
        )
        thread.start()
        return task_id

    def get_status(self, task_id: str, from_index: int = 0) -> dict | None:
        with self._lock:
            state = self._tasks.get(task_id)
            if not state:
                return None
            ordered_pages = sorted(state.results.items(), key=lambda item: item[0])
            pages = [
                html
                for i, html in ordered_pages
                if i >= from_index and html is not None
            ]
            next_index = ordered_pages[-1][0] + 1 if ordered_pages else 0
            return {
                "task_id": task_id,
                "status": state.status,
                "total_rules": state.total_rules,
                "completed_rules": state.completed_rules,
                "pages": pages,
                "next_index": next_index,
                "error": state.error,
                "rules_text": state.rules_text,
                "schema_json": state.schema_json,
                "guidelines_text": state.guidelines_text,
            }

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            state = self._tasks.get(task_id)
            if not state:
                return False
            state.cancelled = True
            if state.status not in {"completed", "failed"}:
                state.status = "cancelled"
            logging.info(f"Task {task_id} cancelled successfully")
            return True

    def _run_all_rules_analysis(self, task_id: str, context: AnalysisContext) -> None:
        start_time = time.time()
        try:
            self._set_status(task_id, status="running")
            logging.info(f"Task created with ID: {task_id}")
            schema_description = context.schema_description
            sql_dialect = context.sql_dialect
            rules = context.rules_text
            logging.info(f"Uploaded context prepared, dialect: {sql_dialect}")

            rules_lst = self._split_rules(rules)
            total_rules = len(rules_lst)
            schema_json = json.dumps(schema_description, indent=2, ensure_ascii=False)

            self._set_status(
                task_id,
                rules_text=rules,
                schema_json=schema_json,
                guidelines_text=guidelines,
                total_rules=total_rules,
            )

            # Update history with context data (non-blocking)
            try:
                HistoryService.update_async_progress(
                    task_id=task_id,
                    total_rules=total_rules,
                    rules_text=rules,
                    schema_json=schema_json,
                    guidelines_text=guidelines,
                )
            except Exception:
                logging.exception("History context update failed (non-critical)")

            max_workers = settings.MAX_CONCURRENT_RULE_ANALYSES

            rules_iter = iter(enumerate(rules_lst))
            futures = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for _ in range(min(max_workers, total_rules)):
                    if self._is_cancelled(task_id):
                        break
                    item = next(rules_iter, None)
                    if item is None:
                        break
                    index, rule = item
                    fut = executor.submit(
                        self._analyze_one,
                        rule,
                        rules_lst,
                        sql_dialect,
                        schema_description,
                    )
                    futures[fut] = index

                while futures:
                    if self._is_cancelled(task_id):
                        for fut in futures:
                            fut.cancel()
                        break
                    done, _ = wait(futures, return_when=FIRST_COMPLETED)
                    for fut in done:
                        index = futures.pop(fut, None)
                        if self._is_cancelled(task_id):
                            continue
                        html = fut.result()
                        self._append_results(task_id, index, html)
                        item = next(rules_iter, None)
                        if item is not None:
                            next_index, rule = item
                            next_fut = executor.submit(
                                self._analyze_one,
                                rule,
                                rules_lst,
                                sql_dialect,
                                schema_description,
                            )
                            futures[next_fut] = next_index

            if self._is_cancelled(task_id):
                self._set_status(task_id, status="cancelled")

                partial_html = self._joined_results(task_id)

                # Log cancellation to history with partial results (non-blocking)
                try:
                    duration = time.time() - start_time
                    HistoryService.cancel_async_execution(
                        task_id=task_id,
                        duration_seconds=duration,
                        partial_result_html=partial_html if partial_html else None,
                    )
                except Exception:
                    logging.exception(
                        "History cancellation logging failed (non-critical)"
                    )
            else:
                self._set_status(task_id, status="completed")
                # Log completion to history (non-blocking)
                try:
                    duration = time.time() - start_time
                    HistoryService.complete_async_execution(
                        task_id=task_id,
                        result_html=self._joined_results(task_id),
                        duration_seconds=duration,
                    )
                except Exception:
                    logging.exception(
                        "History completion logging failed (non-critical)"
                    )
        except Exception as exc:
            logging.exception("Background all_rules_analysis failed")
            self._set_status(task_id, status="failed", error=str(exc))

            # Collect partial results before logging failure
            partial_html = self._joined_results(task_id)

            # Log failure to history with partial results (non-blocking)
            try:
                duration = time.time() - start_time
                HistoryService.fail_async_execution(
                    task_id=task_id,
                    error_message=str(exc),
                    duration_seconds=duration,
                    partial_result_html=partial_html if partial_html else None,
                )
            except Exception:
                logging.exception("History failure logging failed (non-critical)")

    def _analyze_one(
        self,
        rule: str,
        all_rules: list[str],
        dialect: str,
        descriptions: dict,
    ) -> str | None:
        response = analyze_single_rule_pipeline(rule, all_rules, dialect, descriptions)
        if self._is_empty_result(response):
            logging.debug("Empty result for rule analysis, skipping HTML generation")
            return None
        response.loc[0, "Category"] = "analyzed_rule"
        return prettify_html(response)

    def _append_results(self, task_id: str, rule_index: int, html: str | None) -> None:
        with self._lock:
            state = self._tasks.get(task_id)
            if not state:
                return
            state.results[rule_index] = html
            state.completed_rules += 1
            completed_count = state.completed_rules

        # Update history progress (non-blocking, outside lock)
        try:
            HistoryService.update_async_progress(
                task_id=task_id, completed_rules=completed_count
            )
        except Exception:
            # Don't log every progress update failure to avoid spam
            pass

    def _set_status(self, task_id: str, **updates) -> None:
        with self._lock:
            state = self._tasks.get(task_id)
            if not state:
                return
            for key, value in updates.items():
                setattr(state, key, value)

    def _is_cancelled(self, task_id: str) -> bool:
        with self._lock:
            state = self._tasks.get(task_id)
            return bool(state and state.cancelled)

    def _joined_results(self, task_id: str) -> str:
        with self._lock:
            state = self._tasks.get(task_id)
            if not state:
                return ""
            return "".join(html for _, html in sorted(state.results.items()) if html)

    @staticmethod
    def _split_rules(rules: str) -> list[str]:
        rules_lst = re.split("(^|\n)Rule #", rules)
        return ["Rule #" + r for r in rules_lst if len(r) > 1]

    @staticmethod
    def _is_empty_result(df) -> bool:
        return all(
            not df.set_index("Category").loc[c, "Details"]
            for c in [
                "typos",
                "dialect_inconsistencies",
                "contradictions_explained",
                "contradictions_with_rules",
                "contradictions_with_schema",
                "duplications_explained",
                "duplications_with_rules",
                "duplications_with_schema",
                "guideline_violations",
            ]
        )
