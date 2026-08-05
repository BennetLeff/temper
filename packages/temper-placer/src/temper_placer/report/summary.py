"""
Summary report generation for DRC check results.

Moved from ``temper_drc.report.summary``.

Wave 4, Phase 5: the summary compute now lives in the ``temper-io-types``
Rust crate (``report.rs``); this module is a delegation shim. The
pre-migration implementation is pinned verbatim as
``tests/report/_summary_py_oracle.py`` and driven bit-identical by
``test_summary_rust_differential.py``. The `Board Size` line's int-vs-float
rendering is pinned by the differential (Python ``str()`` of the dims is
called back from Rust).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import temper_io_types as _rust

if TYPE_CHECKING:
    from temper_placer.validation.drc_result import RunResult
    from temper_placer.validation.drc_types import ConstraintSet, Placement


def generate_summary(
    result: RunResult,
    placement: Placement,
    _constraints: ConstraintSet,
) -> str:
    """Generate a high-level summary of check results with key metrics."""
    return _rust.report_generate_summary(result, placement)


def _extract_key_metrics(result: RunResult) -> list[tuple[str, float | int]]:
    """Extract key metrics from check results."""
    return list(_rust.report_extract_key_metrics(result))
