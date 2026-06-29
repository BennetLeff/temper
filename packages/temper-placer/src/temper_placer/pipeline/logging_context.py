"""Structured logging context for pipeline runs.

Provides context-var-based metadata injection so that all log lines
during a pipeline run carry ``{board, git_commit, stage, run_id}``
without per-module changes.  The filter is installed once on the root
logger at import time and reads the active context from the context var.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any


# @req(2026-06-28-011-feat-pipeline-observability, R4): Structured logging
# context bound via contextvars so that log lines from any stack depth
# inherit {board, git_commit, stage, run_id} during a run.
_RUN_METADATA_CTX: contextvars.ContextVar[dict[str, Any] | None] = (
    contextvars.ContextVar("temper_run_metadata", default=None)
)
_METADATA_FIELDS = ("board", "git_commit", "stage", "run_id")


class _RunContextFilter(logging.Filter):
    """Injects run metadata into every LogRecord when a pipeline run is active."""

    def filter(self, record: logging.LogRecord) -> bool:
        metadata = _RUN_METADATA_CTX.get(None)
        if metadata:
            for key in _METADATA_FIELDS:
                setattr(record, key, metadata.get(key, ""))
        else:
            for key in _METADATA_FIELDS:
                if not hasattr(record, key):
                    setattr(record, key, "")
        return True


# Install once at import time — the filter reads the contextvar, so it is
# cheap when no run is active and thread-safe during concurrent runs.
_logging_filter = _RunContextFilter()
logging.getLogger().addFilter(_logging_filter)


def set_run_context(metadata: dict[str, Any]) -> contextvars.Token:
    """Set per-run structured-logging metadata on the context variable.

    Returns a token that must be passed to :func:`clear_run_context` to
    restore the previous context.
    """
    return _RUN_METADATA_CTX.set(metadata)


def clear_run_context(token: contextvars.Token) -> None:
    """Restore the run-metadata context to the value before :func:`set_run_context`."""
    _RUN_METADATA_CTX.reset(token)
