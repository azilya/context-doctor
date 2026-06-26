"""Browser-facing routes for the Context Doctor FastAPI app."""

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main analysis form.

    Args:
        request: Incoming browser request used by Jinja templates.

    Returns:
        Rendered main application page.
    """
    # Import lazily so existing tests can keep monkeypatching fastapi_app globals.
    from context_doctor import fastapi_app

    return fastapi_app.templates.TemplateResponse("index.html", {"request": request})


@router.get("/history", response_class=HTMLResponse)
async def history_list(
    request: Request,
    flow: str | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 20,
):
    """Display query history with filtering and pagination.

    Args:
        request: Incoming browser request used by Jinja templates.
        flow: Optional flow-type filter.
        status: Optional execution-status filter.
        search: Optional free-text search term.
        page: One-based page number.
        limit: Maximum entries per page.

    Returns:
        Rendered history list page.
    """
    # Keep pagination math flat and identical to the original route.
    offset = (page - 1) * limit
    # Import once before the guarded DB work so error rendering is reliable.
    from context_doctor import fastapi_app

    try:
        with fastapi_app.get_db_session() as session:
            entries, total = fastapi_app.HistoryRepository.list_entries(
                session=session,
                flow_type=flow,
                status=status,
                search_query=search,
                limit=limit,
                offset=offset,
            )

            # Statistics ride with the page so the template stays unchanged.
            stats = fastapi_app.HistoryRepository.get_statistics(session, days=7)
            total_pages = (total + limit - 1) // limit if total > 0 else 1

            return fastapi_app.templates.TemplateResponse(
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
        return fastapi_app.templates.TemplateResponse(
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


@router.get("/history/{entry_id}", response_class=HTMLResponse)
async def history_detail(request: Request, entry_id: int):
    """Display detailed view of a single history entry.

    Args:
        request: Incoming browser request used by Jinja templates.
        entry_id: Database identifier for the history entry.

    Returns:
        Rendered history detail page.

    Raises:
        HTTPException: If the entry is missing or cannot be loaded.
    """
    # Import once before the guarded DB work so exception handling is predictable.
    from context_doctor import fastapi_app

    try:
        with fastapi_app.get_db_session() as session:
            entry = fastapi_app.HistoryRepository.get_by_id(session, entry_id)
            if not entry:
                raise HTTPException(status_code=404, detail="History entry not found")

            # Decode stored form parameters for the existing detail template.
            input_params = json.loads(entry.input_params) if entry.input_params else {}

            return fastapi_app.templates.TemplateResponse(
                "history_detail.html",
                {"request": request, "entry": entry, "input_params": input_params},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to load history entry")
        raise HTTPException(status_code=500, detail=str(e))
