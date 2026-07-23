"""Shared infrastructure for scripts/ — not a user-facing script.

Import via::

    from _lib.repo import find_repo_root
    from _lib.gate_allowlist import TICKET_PATTERN, load_allowlist

These modules are exempt from ``scripts/manifest.yaml`` entries.
"""

from _lib.repo import find_repo_root
from _lib.path_setup import setup_temper_placer_path
from _lib.gate_allowlist import (
    TICKET_PATTERN,
    check_shrink_mode,
    git_show_main_allowlist,
    load_allowlist,
)
from _lib.github_summary import get_github_summary_path
from _lib.argparse_helpers import add_standard_args

__all__ = [
    "find_repo_root",
    "setup_temper_placer_path",
    "TICKET_PATTERN",
    "check_shrink_mode",
    "git_show_main_allowlist",
    "load_allowlist",
    "get_github_summary_path",
    "add_standard_args",
]
