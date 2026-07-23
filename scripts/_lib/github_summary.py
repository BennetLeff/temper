"""GitHub Actions step-summary path helper."""

from __future__ import annotations

import os


def get_github_summary_path() -> str | None:
    """Return ``$GITHUB_STEP_SUMMARY`` if set, otherwise ``None``.

    Callers can check the return value to decide whether to write job-summary
    markdown.  This centralises the ``os.environ.get`` pattern used by
    several CI gate scripts.
    """
    return os.environ.get("GITHUB_STEP_SUMMARY")
