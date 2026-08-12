"""
Golden fixture diff engine for DSN/SES/JSON comparison.

Provides coordinate-aware comparison with per-boundary geometric tolerance.
Produces structured DiffReport with triage categories:
  BINARY       - structural mismatch (missing net, component, etc.)
  WITHIN_TOLERANCE - within threshold (informational)
  BEYOND_TOLERANCE - exceeds threshold (gate-failing)

Wave 4 (PORT): the parsing + tolerance-diff kernels now live in Rust --
``temper-io-types``'s ``golden_diff`` module, exposed as
``temper_io_types.golden_diff_dsn`` / ``golden_diff_ses`` /
``golden_diff_json``, ported verbatim from this module's pre-migration
body. This file is a pure-delegation shim: ``diff_golden`` (the dispatcher)
and the ``DiffEntry``/``DiffReport`` dataclasses (public API, incl.
``to_json`` presentation) stay here; the per-format kernels delegate to the
Rust compute. The pre-migration implementation is pinned verbatim as the
differential oracle in
``tests/testing/test_golden_diff_rust_differential.py`` (see the crate
``VERIFICATION.md`` for the parity proof). The DSN regexes used by the
pre-migration parser were NOT reused from the existing ``dsn`` module --
that module is a DSN *formatter*, not a place/net structural parser
(evidence in ``VERIFICATION.md``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import temper_io_types as _rs


@dataclass
class DiffEntry:
    board: str
    stage: str
    category: str  # "BINARY" | "WITHIN_TOLERANCE" | "BEYOND_TOLERANCE"
    entity: str  # e.g., "net 'HV_IN'" or "component 'Q1'"
    field: str  # e.g., "X coordinate" or "pin count"
    golden_value: str
    candidate_value: str
    delta: float | None = None
    tolerance: float | None = None


@dataclass
class DiffReport:
    board: str
    stage: str
    passed: bool
    entries: list[DiffEntry] = field(default_factory=list)
    summary: str = ""

    def to_json(self) -> list:
        return [
            {
                "board": e.board,
                "stage": e.stage,
                "category": e.category,
                "entity": e.entity,
                "field": e.field,
                "golden_value": e.golden_value,
                "candidate_value": e.candidate_value,
                "delta": e.delta,
                "tolerance": e.tolerance,
            }
            for e in self.entries
        ]


class GoldenDiffParseError(Exception):
    """Raised when golden/candidate content cannot be parsed."""


def diff_golden(
    board: str,
    stage: str,
    golden_content: str,
    candidate_content: str,
    output_format: str,
    tolerance_mm: float,
) -> DiffReport:
    if output_format == "dsn":
        return _diff_dsn(board, stage, golden_content, candidate_content, tolerance_mm)
    elif output_format == "ses":
        return _diff_ses(board, stage, golden_content, candidate_content, tolerance_mm)
    elif output_format == "json":
        return _diff_json(board, stage, golden_content, candidate_content, tolerance_mm)
    else:
        return DiffReport(
            board=board,
            stage=stage,
            passed=False,
            entries=[
                DiffEntry(
                    board=board,
                    stage=stage,
                    category="BINARY",
                    entity=f"format:{output_format}",
                    field="output_format",
                    golden_value=output_format,
                    candidate_value=output_format,
                )
            ],
            summary=f"Unknown output format: {output_format}",
        )


def _report_from_rust(board: str, stage: str, result: tuple) -> DiffReport:
    """Convert a Rust ``(entries, passed, summary)`` result into a
    ``DiffReport``.  Each Rust entry dict mirrors the ``DiffEntry`` fields
    exactly, so ``DiffEntry(**e)`` is lossless (including ``delta`` /
    ``tolerance`` as ``None`` or ``float``)."""
    entries, passed, summary = result
    return DiffReport(
        board=board,
        stage=stage,
        passed=passed,
        entries=[DiffEntry(**e) for e in entries],
        summary=summary,
    )


def _diff_dsn(board, stage, golden, candidate, tolerance):
    """Component-place tolerance comparison + net pin-count comparison.

    Delegates to ``temper_io_types.golden_diff_dsn``.
    """
    return _report_from_rust(board, stage, _rs.golden_diff_dsn(board, stage, golden, candidate, tolerance))


def _diff_ses(board, stage, golden, candidate, tolerance):
    """Per-wire point comparison by Euclidean distance.

    Delegates to ``temper_io_types.golden_diff_ses``.
    """
    return _report_from_rust(board, stage, _rs.golden_diff_ses(board, stage, golden, candidate, tolerance))


def _diff_json(board, stage, golden, candidate, tolerance):
    """Tolerance-aware recursive JSON diff.

    Delegates to ``temper_io_types.golden_diff_json``.
    """
    return _report_from_rust(board, stage, _rs.golden_diff_json(board, stage, golden, candidate, tolerance))
