import json
import logging
from importlib import resources

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .services.context_service import ContextService
from .database.repository import HistoryRepository
from .database.session import get_db_session, init_db
from .logic import AnalysisParams, run_analysis
from .services.history_service import HistoryService
from .task_manager import TaskManager
from .utils import prettify_html
from .routers import api, web
from . import settings

logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(
    directory=str(resources.files("context_doctor").joinpath("templates"))
)
templates.env.filters["fromjson"] = json.loads
task_manager = TaskManager()
# Compatibility alias remains available to integrations during the rename.
ContextStore = ContextService
# Package-relative static mounting keeps wheel and Docker installations runnable
# without depending on the process working directory.
app.mount(
    "/static",
    StaticFiles(directory=str(resources.files("context_doctor").joinpath("static"))),
    name="static",
)
app.include_router(web.router)
app.include_router(api.router)

__all__ = [
    "AnalysisParams",
    "ContextService",
    "ContextStore",
    "HistoryRepository",
    "HistoryService",
    "app",
    "get_db_session",
    "logger",
    "prettify_html",
    "run_analysis",
    "task_manager",
    "templates",
]


@app.on_event("startup")
async def startup_event():
    """Initialize persistence and expire stale cached contexts.

    Database and cache maintenance are best-effort startup concerns so history or
    cache failures never prevent the analysis UI from becoming available.
    """
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.exception(f"Failed to initialize database: {e}")
        # Don't fail startup - history is non-critical

    try:
        # Keep cache cleanup isolated from schema initialization so its failure is
        # reported accurately and cannot mask a successful database setup.
        ContextService.delete_expired(settings.CONTEXT_CACHE_TTL_SECONDS)
    except Exception as e:
        logger.exception(f"Failed to expire cached contexts: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
