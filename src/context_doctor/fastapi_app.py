import json
import logging
from importlib import resources

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from .context_store import ContextStore
from .database.repository import HistoryRepository
from .database.session import get_db_session, init_db
from .logic import AnalysisParams, run_analysis
from .services.history_service import HistoryService
from .task_manager import TaskManager
from .utils import prettify_html
from .routers import api, web

logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(
    directory=str(resources.files("context_doctor").joinpath("templates"))
)
templates.env.filters["fromjson"] = json.loads
task_manager = TaskManager()
app.include_router(web.router)
app.include_router(api.router)

__all__ = [
    "AnalysisParams",
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
    """Initialize database on application startup."""
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.exception(f"Failed to initialize database: {e}")
        # Don't fail startup - history is non-critical


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
