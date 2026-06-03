"""Database session management and connection handling."""

import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .. import settings

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_PATH = settings.CONTEXT_DOCTOR_DB_PATH
DATABASE_URL = settings.DATABASE_URL

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    pool_pre_ping=True,  # Verify connections before using them
    echo=False,  # Set to True for SQL query logging
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable SQLite optimizations for better concurrency and performance."""
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_conn.cursor()
        # WAL mode allows concurrent reads while writing
        cursor.execute("PRAGMA journal_mode=WAL")
        # NORMAL synchronous mode is faster while still being safe
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize the database by creating all tables.

    This function is idempotent - it's safe to call multiple times.
    If tables already exist, they won't be recreated.
    """
    from .models import Base

    try:
        Base.metadata.create_all(bind=engine)
        logger.info(f"Database initialized at {DATABASE_PATH}")
    except Exception as e:
        logger.exception(f"Failed to initialize database: {e}")
        raise


@contextmanager
def get_db_session() -> Session:
    """Context manager for database sessions.

    Usage:
        with get_db_session() as session:
            # Use session for queries
            result = session.query(QueryHistory).all()
            # Session is automatically committed on success

    The session will be automatically committed on successful completion
    and rolled back if an exception occurs.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
