import json
import logging
import time
from importlib import resources

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .context_store import ContextStore
from .database.repository import HistoryRepository
from .database.session import get_db_session, init_db
from .logic import AnalysisParams, run_analysis
from .services.history_service import HistoryService
from .task_manager import TaskManager
from .utils import prettify_html

logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(
    directory=str(resources.files("context_doctor").joinpath("templates"))
)
templates.env.filters["fromjson"] = json.loads
task_manager = TaskManager()


@app.on_event("startup")
async def startup_event():
    """Initialize database on application startup."""
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.exception(f"Failed to initialize database: {e}")
        # Don't fail startup - history is non-critical


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/run", response_class=HTMLResponse)
async def run_analysis_view(
    request: Request,
    flow: str = Form(""),
    new_rule: str | None = Form(None),
    question: str | None = Form(None),
    problem: str | None = Form(None),
    sql_dialect: str = Form("PostgreSQL"),
    schema_file: UploadFile | None = File(None),
    rules_file: UploadFile | None = File(None),
):
    def _strip_or_none(val):
        return val.strip() if isinstance(val, str) else val

    cleaned_flow = _strip_or_none(flow)
    cleaned_new_rule = _strip_or_none(new_rule) if new_rule is not None else None
    cleaned_question = _strip_or_none(question) if question is not None else None
    cleaned_problem = _strip_or_none(problem) if problem is not None else None
    cleaned_sql_dialect = _strip_or_none(sql_dialect) or ""

    # Capture request metadata for history tracking
    user_agent = request.headers.get("user-agent")
    client_ip = request.client.host if request.client else None

    # Prepare input params for history
    input_params = {
        "new_rule": cleaned_new_rule,
        "question": cleaned_question,
        "problem": cleaned_problem,
        "schema_filename": schema_file.filename if schema_file else None,
        "rules_filename": rules_file.filename if rules_file else None,
        "sql_dialect": cleaned_sql_dialect,
    }

    try:
        analysis_context = ContextStore.from_uploads(
            schema_content=await schema_file.read() if schema_file else b"",
            rules_content=await rules_file.read() if rules_file else b"",
            sql_dialect=cleaned_sql_dialect,
            schema_filename=schema_file.filename if schema_file else None,
            rules_filename=rules_file.filename if rules_file else None,
        )
        cleaned = AnalysisParams(
            flow=cleaned_flow,
            context=analysis_context,
            new_rule=cleaned_new_rule,
            question=cleaned_question,
            problem=cleaned_problem,
        )

        if cleaned.flow == "all_rules_analysis":
            # ASYNC FLOW - Start task and log to history
            task_id = task_manager.start_all_rules_analysis(analysis_context)

            # Log async execution start (non-blocking)
            try:
                HistoryService.start_async_execution(
                    task_id=task_id,
                    flow_type=cleaned.flow,
                    input_params=input_params,
                    client_backend_url="",
                    user_agent=user_agent,
                    ip_address=client_ip,
                )
            except Exception:
                logger.exception("History logging failed (non-critical)")

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
                },
                "task_id": task_id,
            }
            return templates.TemplateResponse("index.html", template_context)

        else:
            # SYNC FLOW - Track execution start to completion
            start_time = time.time()
            history_entry_id = None

            # Start history tracking (non-blocking)
            try:
                history_entry_id = HistoryService.start_sync_execution(
                    flow_type=cleaned.flow,
                    input_params=input_params,
                    client_backend_url="",
                    user_agent=user_agent,
                    ip_address=client_ip,
                )
            except Exception:
                logger.exception("History start logging failed (non-critical)")

            # Execute analysis
            result, rules_text, schema_description, guidelines_text = run_analysis(
                cleaned
            )

            # Calculate duration
            duration = time.time() - start_time

            result_html = (
                prettify_html(result) if isinstance(result, list) else f"<pre>{result}</pre>"
            )

            schema_json = json.dumps(schema_description, indent=2, ensure_ascii=False)

            # Complete history tracking (non-blocking)
            try:
                HistoryService.complete_sync_execution(
                    entry_id=history_entry_id,
                    result_html=result_html,
                    rules_text=rules_text,
                    schema_json=schema_json,
                    guidelines_text=guidelines_text,
                    duration_seconds=duration,
                )
            except Exception:
                logger.exception("History completion logging failed (non-critical)")

            form_values = {
                "new_rule": cleaned.new_rule or "",
                "question": cleaned.question or "",
                "problem": cleaned.problem or "",
                "sql_dialect": cleaned_sql_dialect,
                "schema_filename": analysis_context.schema_filename or "",
                "rules_filename": analysis_context.rules_filename or "",
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
            return templates.TemplateResponse("index.html", template_context)
    except Exception as e:
        # Log failed execution (non-blocking)
        if cleaned_flow != "all_rules_analysis" and "history_entry_id" in locals():
            try:
                duration = time.time() - start_time if "start_time" in locals() else 0
                HistoryService.fail_execution(
                    entry_id=history_entry_id,
                    error_message=str(e),
                    duration_seconds=duration,
                )
            except Exception:
                logger.exception("History error logging failed (non-critical)")

        form_values = {
            "new_rule": cleaned_new_rule or "",
            "question": cleaned_question or "",
            "problem": cleaned_problem or "",
            "sql_dialect": cleaned_sql_dialect,
            "schema_filename": schema_file.filename if schema_file else "",
            "rules_filename": rules_file.filename if rules_file else "",
        }
        return templates.TemplateResponse(
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


@app.get("/tasks/{task_id}")
async def task_status(task_id: str, from_index: int = 0):
    status = task_manager.get_status(task_id, from_index=from_index)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return status


@app.post("/tasks/{task_id}/cancel")
async def task_cancel(task_id: str):
    if not task_manager.cancel_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, "status": "cancelled"}


@app.get("/history", response_class=HTMLResponse)
async def history_list(
    request: Request,
    flow: str | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 20,
):
    """Display query history with filtering and pagination."""
    offset = (page - 1) * limit

    try:
        with get_db_session() as session:
            entries, total = HistoryRepository.list_entries(
                session=session,
                flow_type=flow,
                status=status,
                search_query=search,
                limit=limit,
                offset=offset,
            )

            # Get statistics
            stats = HistoryRepository.get_statistics(session, days=7)

            total_pages = (total + limit - 1) // limit if total > 0 else 1

            return templates.TemplateResponse(
                "history.html",
                {
                    "request": request,
                    "entries": entries,
                    "total": total,
                    "page": page,
                    "total_pages": total_pages,
                    "limit": limit,
                    "stats": stats,
                    "filters": {"flow": flow, "status": status, "search": search},
                },
            )
    except Exception as e:
        logger.exception("Failed to load history")
        return templates.TemplateResponse(
            "history.html",
            {
                "request": request,
                "error": str(e),
                "entries": [],
                "total": 0,
                "page": 1,
                "total_pages": 1,
                "limit": limit,
                "stats": {},
                "filters": {"flow": flow, "status": status, "search": search},
            },
        )


@app.get("/history/{entry_id}", response_class=HTMLResponse)
async def history_detail(request: Request, entry_id: int):
    """Display detailed view of a single history entry."""
    try:
        with get_db_session() as session:
            entry = HistoryRepository.get_by_id(session, entry_id)
            if not entry:
                raise HTTPException(status_code=404, detail="History entry not found")

            # Parse input_params from JSON
            input_params = json.loads(entry.input_params) if entry.input_params else {}

            return templates.TemplateResponse(
                "history_detail.html",
                {"request": request, "entry": entry, "input_params": input_params},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to load history entry")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history/stats")
async def history_stats(days: int = 7):
    """Get usage statistics as JSON."""
    try:
        with get_db_session() as session:
            stats = HistoryRepository.get_statistics(session, days=days)
            return stats
    except Exception as e:
        logger.exception("Failed to get history statistics")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/history/{entry_id}")
async def delete_history_entry(entry_id: int):
    """Delete a history entry."""
    try:
        with get_db_session() as session:
            success = HistoryRepository.delete_entry(session, entry_id)
            if not success:
                raise HTTPException(status_code=404, detail="History entry not found")
            return {"status": "deleted", "id": entry_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete history entry")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
