"""
Report formatting for DRC check results.

Moved from ``temper_drc.report.formatter``.

Wave 4, Phase 5: the formatting compute now lives in the ``temper-io-types``
Rust crate (``report.rs``); this module is a delegation shim. The pre-migration
implementation is pinned verbatim as ``tests/report/_formatter_py_oracle.py``
and driven bit-identical by ``test_formatter_rust_differential.py``.
``json.dumps`` stays Python stdlib (the Rust side returns the JSON *data*);
``str(value)`` on arbitrary Python objects stays a Python runtime semantic
(the Rust side calls back).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import temper_io_types as _rust

if TYPE_CHECKING:
    from temper_placer.validation.drc_result import RunResult
    from temper_placer.validation.drc_types import ConstraintSet


def format_text(result: RunResult) -> str:
    """Format check results as human-readable text."""
    return _rust.report_format_text(result)


def format_json(result: RunResult) -> str:
    """Format check results as JSON."""
    return json.dumps(_rust.report_format_json_data(result), indent=2)


def format_html(result: RunResult, placement_name: str, _constraints: ConstraintSet) -> str:
    """Format check results as HTML report."""
    return _rust.report_format_html(result, placement_name)


def _severity_to_bootstrap(severity: Any) -> str:
    """Map severity to Bootstrap badge class (kept for import compat)."""
    mapping = {
        "CRITICAL": "danger",
        "ERROR": "warning",
        "WARNING": "info",
        "INFO": "secondary",
    }
    return mapping.get(getattr(severity, "name", str(severity)), "secondary")
