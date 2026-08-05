"""Backward-compatible imports for the renamed context service boundary."""

from .services.context_service import AnalysisContext, ContextService

# Keep the old public name for downstream imports while all internal call sites
# migrate to the service module without a flag-day breaking change.
ContextStore = ContextService

__all__ = ["AnalysisContext", "ContextService", "ContextStore"]
