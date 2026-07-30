"""SQLAlchemy models for query history tracking."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class QueryHistory(Base):
    """Model for storing query execution history.

    This table tracks all user queries including inputs, outputs, execution
    metadata, and timing information for both synchronous and asynchronous flows.
    """

    __tablename__ = "query_history"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Request metadata
    flow_type = Column(String(50), nullable=False, index=True)
    """Type of analysis flow: rule_analysis, all_rules_analysis, question_analysis, rule_generation"""

    execution_mode = Column(String(20), nullable=False)
    """Execution mode: 'sync' or 'async'"""

    # Input parameters (stored as JSON string)
    input_params = Column(Text)
    """JSON-encoded dictionary of input parameters (new_rule, question, problem)"""

    # Timing information
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    """Timestamp when the request was received"""

    started_at = Column(DateTime)
    """Timestamp when execution actually started"""

    completed_at = Column(DateTime)
    """Timestamp when execution completed (success, failure, or cancellation)"""

    duration_seconds = Column(Float)
    """Total execution duration in seconds"""

    # Status tracking
    status = Column(String(20), nullable=False, index=True)
    """Execution status: 'pending', 'running', 'completed', 'failed', 'cancelled'"""

    # Results
    result_html = Column(Text)
    """Rendered HTML output from the analysis"""

    error_message = Column(Text)
    """Error message if execution failed"""

    # Context data (snapshots of data used in analysis)
    rules_text = Column(Text)
    """Text of rules used in the analysis"""

    schema_json = Column(Text)
    """JSON representation of database schema"""

    guidelines_text = Column(Text)
    """Guidelines text used for validation"""

    # Async-specific fields
    task_id = Column(String(64), index=True)
    """Task ID for async flows (all_rules_analysis)"""

    total_rules = Column(Integer)
    """Total number of rules to analyze (for async flows)"""

    completed_rules = Column(Integer)
    """Number of rules completed so far (for async flows)"""

    # Metadata
    client_backend_url = Column(String(255))
    """URL of the backend API that was queried"""

    user_agent = Column(Text)
    """User agent string from the HTTP request"""

    ip_address = Column(String(45))
    """Client IP address (IPv4 or IPv6)"""

    def __repr__(self):
        return f"<QueryHistory(id={self.id}, flow_type='{self.flow_type}', status='{self.status}')>"


class StoredContext(Base):
    """Persisted uploaded context that can be reused across analysis runs."""

    __tablename__ = "analysis_contexts"

    # Context identifiers are opaque and remain stable across explicit replacement.
    context_id = Column(String(64), primary_key=True)
    raw_schema_json = Column(Text, nullable=False)
    schema_description_json = Column(Text, nullable=False)
    rules_text = Column(Text, nullable=False)
    sql_dialect = Column(String(100), nullable=False)
    schema_filename = Column(String(255))
    rules_filename = Column(String(255))
    created_at = Column(DateTime, nullable=False, index=True)
    last_used_at = Column(DateTime, nullable=False, index=True)
