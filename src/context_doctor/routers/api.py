"""Form and JSON routes for the Context Doctor FastAPI app."""

import json
import time

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

router = APIRouter()


def _strip_or_none(value: str | None) -> str | None:
    """Trim submitted form values without inventing missing values.

    Args:
        value: Optional form value from FastAPI.

    Returns:
        Trimmed string when a value is present, otherwise ``None``.
    """
    # Keep the boundary parse tiny; internal route logic only sees stripped text.
    return value.strip() if isinstance(value, str) else value


@router.post("/api/run", response_class=HTMLResponse)
@router.post("/run", response_class=HTMLResponse)
async def run_analysis_view(
    request: Request,
    flow: str = Form(""),
    new_rule: str | None = Form(None),
    question: str | None = Form(None),
    problem: str | None = Form(None),
    sql_dialect: str = Form("PostgreSQL"),
    schema_file: UploadFile | None = File(None),
    rules_file: UploadFile | None = File(None),
    context_id: str | None = Form(None),
    replace_context: bool = Form(False),
):
    """Run the selected analysis flow and render the result page.

    Args:
        request: Incoming browser request used by Jinja templates.
        flow: Analysis flow selected in the form.
        new_rule: Optional rule text for rule-specific flows.
        question: Optional natural-language question.
        problem: Optional generation problem statement.
        sql_dialect: SQL dialect label to attach to uploaded context.
        schema_file: Optional uploaded schema file.
        rules_file: Optional uploaded rules file.
        context_id: Existing cached context to reuse or explicitly replace.
        replace_context: Whether uploads replace the supplied cached context.

    Returns:
        Rendered main page containing either sync results or an async task id.
    """
    # Import lazily so tests can keep monkeypatching fastapi_app symbols.
    from context_doctor import fastapi_app

    cleaned_flow = _strip_or_none(flow) or ""
    cleaned_new_rule = _strip_or_none(new_rule)
    cleaned_question = _strip_or_none(question)
    cleaned_problem = _strip_or_none(problem)
    cleaned_sql_dialect = _strip_or_none(sql_dialect) or ""
    cleaned_context_id = _strip_or_none(context_id)

    # Capture request metadata once for history records.
    user_agent = request.headers.get("user-agent")
    client_ip = request.client.host if request.client else None

    # Keep history input payload identical to the previous route.
    input_params = {
        "new_rule": cleaned_new_rule,
        "question": cleaned_question,
        "problem": cleaned_problem,
        "schema_filename": schema_file.filename if schema_file else None,
        "rules_filename": rules_file.filename if rules_file else None,
        "sql_dialect": cleaned_sql_dialect,
    }

    try:
        # Reuse requires no file reads; an upload always creates a new identity
        # unless the caller opts into explicit replacement semantics.
        if cleaned_context_id and not schema_file and not rules_file:
            analysis_context = fastapi_app.ContextService.get(cleaned_context_id)
            if analysis_context is None:
                raise ValueError(f"Context not found: {cleaned_context_id}")
        else:
            analysis_context = fastapi_app.ContextService.from_uploads(
                schema_content=await schema_file.read() if schema_file else b"",
                rules_content=await rules_file.read() if rules_file else b"",
                sql_dialect=cleaned_sql_dialect,
                schema_filename=schema_file.filename if schema_file else None,
                rules_filename=rules_file.filename if rules_file else None,
            )
            analysis_context = fastapi_app.ContextService.save(
                analysis_context,
                replace_context_id=cleaned_context_id if replace_context else None,
            )
        # History input JSON carries the stable identifier for run-to-context
        # traceability without making history availability critical to analysis.
        input_params["context_id"] = analysis_context.context_id
        cleaned = fastapi_app.AnalysisParams(
            flow=cleaned_flow,
            context=analysis_context,
            new_rule=cleaned_new_rule,
            question=cleaned_question,
            problem=cleaned_problem,
        )

        if cleaned.flow == "all_rules_analysis":
            # Async flow returns immediately with a task id for browser polling.
            task_id = fastapi_app.task_manager.start_all_rules_analysis(
                analysis_context
            )

            try:
                # History is best-effort and must not block the user flow.
                fastapi_app.HistoryService.start_async_execution(
                    task_id=task_id,
                    flow_type=cleaned.flow,
                    input_params=input_params,
                    client_backend_url="",
                    user_agent=user_agent,
                    ip_address=client_ip,
                )
            except Exception:
                fastapi_app.logger.exception("History logging failed (non-critical)")

            template_context = {
                "request": request,
                "result": "",
                "rules_text": "",
                "schema_json": "",
                "guidelines_text": "",
                "selected_flow": cleaned.flow,
                "form_values": {
                    "new_rule": cleaned.new_rule or "",
                    "question": cleaned.question or "",
                    "problem": cleaned.problem or "",
                    "sql_dialect": cleaned_sql_dialect,
                    "schema_filename": analysis_context.schema_filename or "",
                    "rules_filename": analysis_context.rules_filename or "",
                    "context_id": analysis_context.context_id or "",
                },
                "task_id": task_id,
            }
            return fastapi_app.templates.TemplateResponse(
                "index.html", template_context
            )

        # Sync flows track duration and render the completed result directly.
        start_time = time.time()
        history_entry_id = None

        try:
            # History start is best-effort to avoid losing the main analysis.
            history_entry_id = fastapi_app.HistoryService.start_sync_execution(
                flow_type=cleaned.flow,
                input_params=input_params,
                client_backend_url="",
                user_agent=user_agent,
                ip_address=client_ip,
            )
        except Exception:
            fastapi_app.logger.exception("History start logging failed (non-critical)")

        # Delegate real analysis to existing business logic unchanged.
        result, rules_text, schema_description, guidelines_text = (
            fastapi_app.run_analysis(cleaned)
        )
        duration = time.time() - start_time

        # Preserve the previous HTML/list rendering contract for templates.
        result_html = (
            fastapi_app.prettify_html(result)
            if isinstance(result, list)
            else f"<pre>{result}</pre>"
        )
        schema_json = json.dumps(schema_description, indent=2, ensure_ascii=False)

        try:
            # Completion history is non-critical; rendering succeeds if it fails.
            fastapi_app.HistoryService.complete_sync_execution(
                entry_id=history_entry_id,
                result_html=result_html,
                rules_text=rules_text,
                schema_json=schema_json,
                guidelines_text=guidelines_text,
                duration_seconds=duration,
            )
        except Exception:
            fastapi_app.logger.exception(
                "History completion logging failed (non-critical)"
            )

        form_values = {
            "new_rule": cleaned.new_rule or "",
            "question": cleaned.question or "",
            "problem": cleaned.problem or "",
            "sql_dialect": cleaned_sql_dialect,
            "schema_filename": analysis_context.schema_filename or "",
            "rules_filename": analysis_context.rules_filename or "",
            "context_id": analysis_context.context_id or "",
        }

        template_context = {
            "request": request,
            "result": result_html,
            "rules_text": rules_text,
            "schema_json": schema_json,
            "guidelines_text": guidelines_text,
            "selected_flow": cleaned.flow,
            "form_values": form_values,
        }
        return fastapi_app.templates.TemplateResponse("index.html", template_context)
    except Exception as e:
        # Failed sync executions get best-effort history failure metadata.
        if cleaned_flow != "all_rules_analysis" and "history_entry_id" in locals():
            try:
                duration = time.time() - start_time if "start_time" in locals() else 0
                fastapi_app.HistoryService.fail_execution(
                    entry_id=history_entry_id,
                    error_message=str(e),
                    duration_seconds=duration,
                )
            except Exception:
                fastapi_app.logger.exception(
                    "History error logging failed (non-critical)"
                )

        form_values = {
            "new_rule": cleaned_new_rule or "",
            "question": cleaned_question or "",
            "problem": cleaned_problem or "",
            "sql_dialect": cleaned_sql_dialect,
            "schema_filename": schema_file.filename if schema_file else "",
            "rules_filename": rules_file.filename if rules_file else "",
            "context_id": cleaned_context_id or "",
        }
        return fastapi_app.templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": str(e),
                "rules_text": "",
                "schema_json": "",
                "guidelines_text": "",
                "selected_flow": cleaned_flow,
                "form_values": form_values,
            },
        )


@router.get("/api/tasks/{task_id}")
@router.get("/tasks/{task_id}")
async def task_status(task_id: str, from_index: int = 0):
    """Return the current status for an async all-rules task.

    Args:
        task_id: Identifier returned when the async task started.
        from_index: First result index the browser has not received yet.

    Returns:
        Task status payload including any new partial results.

    Raises:
        HTTPException: If the task id is unknown.
    """
    # Read from the shared task manager so polling sees the same tasks.
    from context_doctor import fastapi_app

    status = fastapi_app.task_manager.get_status(task_id, from_index=from_index)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return status


@router.post("/api/tasks/rule-analysis")
async def start_rule_analysis_task(
    context_id: str = Form(...), new_rule: str = Form(...)
):
    """Start one proposed-rule analysis through the task manager.

    Args:
        context_id: Previously created immutable context identifier.
        new_rule: Proposed SQL-generation rule.

    Returns:
        Pending task identity for the standard polling endpoint.

    Raises:
        HTTPException: If the cached context does not exist.
    """
    from context_doctor import fastapi_app

    context = fastapi_app.ContextService.get(context_id.strip())
    if context is None:
        raise HTTPException(status_code=404, detail="Context not found")
    # This opt-in API completes the task-manager migration while the legacy
    # browser POST remains synchronous for compatibility.
    task_id = fastapi_app.task_manager.start_rule_analysis(context, new_rule)
    try:
        fastapi_app.HistoryService.start_async_execution(
            task_id=task_id,
            flow_type="rule_analysis",
            input_params={
                "context_id": context.context_id,
                "new_rule": new_rule.strip(),
            },
        )
    except Exception:
        fastapi_app.logger.exception("History logging failed (non-critical)")
    return {"task_id": task_id, "status": "pending"}


@router.post("/api/tasks/{task_id}/cancel")
@router.post("/tasks/{task_id}/cancel")
async def task_cancel(task_id: str):
    """Cancel an async all-rules task.

    Args:
        task_id: Identifier returned when the async task started.

    Returns:
        Cancellation confirmation payload.

    Raises:
        HTTPException: If the task id is unknown.
    """
    # Fail loud on unknown tasks; callers should not treat that as success.
    from context_doctor import fastapi_app

    if not fastapi_app.task_manager.cancel_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, "status": "cancelled"}


@router.get("/api/history/stats")
async def history_stats(days: int = 7):
    """Get usage statistics as JSON.

    Args:
        days: Number of trailing days to include.

    Returns:
        History statistics payload.

    Raises:
        HTTPException: If statistics cannot be loaded.
    """
    # Use the app-level session factory to preserve test monkeypatches.
    from context_doctor import fastapi_app

    try:
        with fastapi_app.get_db_session() as session:
            return fastapi_app.HistoryRepository.get_statistics(session, days=days)
    except Exception as e:
        fastapi_app.logger.exception("Failed to get history statistics")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/contexts")
async def create_context(
    schema_file: UploadFile = File(...),
    rules_file: UploadFile = File(...),
    sql_dialect: str = Form(...),
    replace_context_id: str | None = Form(None),
):
    """Create or explicitly replace a reusable analysis context.

    Args:
        schema_file: Uploaded schema JSON.
        rules_file: Uploaded rules text.
        sql_dialect: SQL dialect for the context.
        replace_context_id: Existing identifier to replace, when desired.

    Returns:
        Context identity and normalized metadata.
    """
    from context_doctor import fastapi_app

    # The API shares exactly the same validation/persistence boundary as the
    # browser form, preventing divergent cache formats.
    context = fastapi_app.ContextService.from_uploads(
        await schema_file.read(),
        await rules_file.read(),
        sql_dialect,
        schema_file.filename,
        rules_file.filename,
    )
    try:
        context = fastapi_app.ContextService.save(context, replace_context_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "context_id": context.context_id,
        "schema_filename": context.schema_filename,
        "rules_filename": context.rules_filename,
        "sql_dialect": context.sql_dialect,
    }


@router.get("/api/contexts/{context_id}")
async def get_context(context_id: str):
    """Return safe metadata for a reusable context.

    Args:
        context_id: Persistent context identifier.

    Returns:
        Context metadata without exposing full uploaded content.
    """
    from context_doctor import fastapi_app

    context = fastapi_app.ContextService.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Context not found")
    return {
        "context_id": context.context_id,
        "schema_filename": context.schema_filename,
        "rules_filename": context.rules_filename,
        "sql_dialect": context.sql_dialect,
    }


@router.delete("/api/contexts/{context_id}")
async def delete_context(context_id: str):
    """Delete a reusable context.

    Args:
        context_id: Persistent context identifier.

    Returns:
        Deletion confirmation.
    """
    from context_doctor import fastapi_app

    if not fastapi_app.ContextService.delete(context_id):
        raise HTTPException(status_code=404, detail="Context not found")
    return {"status": "deleted", "context_id": context_id}


@router.delete("/api/history/{entry_id}")
async def delete_history_entry(entry_id: int):
    """Delete a history entry.

    Args:
        entry_id: Database identifier for the history entry.

    Returns:
        Deletion confirmation payload.

    Raises:
        HTTPException: If the entry is missing or deletion fails.
    """
    # Keep deletion on the shared repository/session path.
    from context_doctor import fastapi_app

    try:
        with fastapi_app.get_db_session() as session:
            success = fastapi_app.HistoryRepository.delete_entry(session, entry_id)
            if not success:
                raise HTTPException(status_code=404, detail="History entry not found")
            return {"status": "deleted", "id": entry_id}
    except HTTPException:
        raise
    except Exception as e:
        fastapi_app.logger.exception("Failed to delete history entry")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/tools/sql-dialect-docs")
async def validate_sql_dialect_docs(dialect: str):
    """Run the official SQL-dialect documentation validation tool.

    Args:
        dialect: SQL dialect name to validate.

    Returns:
        Structured tool result suitable for agentic orchestration.
    """
    from context_doctor.services.dialect_docs import check_dialect_documentation

    # The endpoint exposes a concrete, independently callable tool; analysis
    # prompts are deliberately not changed or granted implicit network access.
    return check_dialect_documentation(dialect).to_dict()
