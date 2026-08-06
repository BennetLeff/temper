"""Differential test: Rust analysis kernels (temper_drc_rs) vs the pinned
Python oracle for ``temper_placer/analysis/_violation_report.py``.

Wave 4, Phase 4 — the analysis-surface migration (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``).
The Rust pyfunctions ``build_report_rows`` and ``render_report`` (in
``temper_drc_rs``, from the ``temper-drc-rs`` crate) must reproduce the
pre-migration Python implementation bit-identically.  The pre-migration
implementation is pinned verbatim as the oracle
(``_violation_report_py_oracle.py``, commit c5875adad) and every
assertion here drives IDENTICAL inputs through both sides.

Boundary ruling (argued in-source in the shim): the kiutils parse
(``KiBoard.from_file`` / ``_extract_component_positions``) and the
shapely/GEOS overlap-area kernel (``_compute_overlap_area_mm2``) stay
Python-side — kiutils object construction and GEOS intersection are
library semantics that cannot be crossed bit-exactly.  The Rust side owns
the report-building/shape logic: target-rule filtering, ref sorting, row
shaping, the overlap-area callback dispatch, the stable overlap-descending
sort, and the Markdown renderer (including CPython fixed-format float
rendering and the 120-char pipe-escaped message truncation).
"""

from __future__ import annotations

import random
from unittest.mock import MagicMock

import pytest
import temper_drc_rs as _drc

import tests.analysis._violation_report_py_oracle as _oracle
from temper_placer.analysis._violation_report import (
    _generate_report_rows as _shim_rows,
)
from temper_placer.analysis._violation_report import (
    _render_report as _shim_render,
)
from temper_placer.validation._drc_api import DrcError

# Rust symbols under test — must exist or this file fails to collect (RED).
BUILD_REPORT_ROWS = _drc.build_report_rows
RENDER_REPORT = _drc.render_report


# ---------------------------------------------------------------------------
# Fake meta / positions (mirror the existing unit tests: real shapely
# geometries so overlap areas are non-trivial floats).
# ---------------------------------------------------------------------------


class _FakeCourtyard:
    def __init__(self, area: float = 10.0, size: float = 5.0):
        self._polygon = MagicMock(area=area)
        self._size = size

    def get_global_polygon(self, x: float, y: float, rotation_idx: int):
        from shapely.geometry import Point

        return Point(x, y).buffer(self._size)


def _fake_meta(refs):
    return MagicMock(
        courtyards={ref: _FakeCourtyard(area=10.0 + i, size=5.0) for i, ref in enumerate(refs)}
    )


# ---------------------------------------------------------------------------
# Canonicalization helpers.
# ---------------------------------------------------------------------------


def _canon(value):
    """Recursive canonical key: floats via hex + type tag, lists via tuples."""
    if isinstance(value, float):
        return ("float", value.hex())
    if isinstance(value, int) and not isinstance(value, bool):
        return ("int", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, (list, tuple)):
        return tuple(_canon(v) for v in value)
    return (type(value).__name__, repr(value))


def _row_key(row):
    return tuple(sorted((k, _canon(row[k])) for k in row))


def _rows_key(rows):
    return tuple(_row_key(r) for r in rows)


def _err(rule, components, location=(10.0, 20.0), message="m"):
    return DrcError(
        rule=rule,
        severity="error",
        location=location,
        message=message,
        components=list(components),
    )


# ---------------------------------------------------------------------------
# build_report_rows vs oracle _generate_report_rows.
# ---------------------------------------------------------------------------


def test_rows_oracle_vs_shim_basic(tmp_path=None):
    errors = [
        _err("courtyards_overlap", ["D3", "C4"], (10.0, 20.0), "Courtyards overlap"),
        _err("clearance", ["R1"], (5.0, 5.0), "Clearance violation"),
        _err("pth_inside_courtyard", ["R7"], (30.0, 40.0), "PTH inside courtyard"),
        _err("courtyards_overlap", ["A1", "B2", "C3"], (1.0, 2.0), "triple"),
    ]
    meta = _fake_meta(["D3", "C4", "R7", "A1", "B2", "C3"])
    positions = {"D3": (50.0, 50.0, 0), "C4": (50.0, 50.0, 0)}
    oracle_rows = _oracle._generate_report_rows(errors, meta, positions)
    shim_rows = _shim_rows(errors, meta, positions)
    assert _rows_key(shim_rows) == _rows_key(oracle_rows)


def test_rows_empty_inputs():
    oracle_rows = _oracle._generate_report_rows([], _fake_meta([]), {})
    shim_rows = _shim_rows([], _fake_meta([]), {})
    assert _rows_key(shim_rows) == _rows_key(oracle_rows) == ()


def test_rows_sort_order_and_stability():
    """Equal overlap areas keep input order (Python list.sort is stable;
    Rust slice::sort_by is stable — same contract)."""
    errors = [
        _err("courtyards_overlap", ["P1", "P2"], (0.0, 0.0), "a"),
        _err("courtyards_overlap", ["Q1", "Q2"], (0.0, 0.0), "b"),
        _err("pth_inside_courtyard", ["R9"], (0.0, 0.0), "c"),
    ]
    meta = _fake_meta(["P1", "P2", "Q1", "Q2", "R9"])
    positions = {
        "P1": (0.0, 0.0, 0), "P2": (100.0, 100.0, 0),
        "Q1": (0.0, 0.0, 0), "Q2": (50.0, 50.0, 0),
    }
    oracle_rows = _oracle._generate_report_rows(errors, meta, positions)
    shim_rows = _shim_rows(errors, meta, positions)
    assert _rows_key(shim_rows) == _rows_key(oracle_rows)
    # Rows with zero overlap (non-overlapping courtyards) tie at 0.0 and must
    # keep input order.
    errs2 = [
        _err("courtyards_overlap", ["A", "B"], (0.0, 0.0), "x"),
        _err("pth_inside_courtyard", ["Z"], (0.0, 0.0), "y"),
        _err("courtyards_overlap", ["C", "D"], (0.0, 0.0), "z"),
    ]
    meta2 = _fake_meta(["A", "B", "C", "D", "Z"])
    pos2 = {"A": (0.0, 0.0, 0), "B": (200.0, 200.0, 0), "C": (0.0, 0.0, 0), "D": (300.0, 300.0, 0)}
    o2 = _oracle._generate_report_rows(errs2, meta2, pos2)
    s2 = _shim_rows(errs2, meta2, pos2)
    assert _rows_key(s2) == _rows_key(o2)
    # The 0.0-overlap rows preserve input order between the two courtyard rows.
    ids = [r["refs_sorted"] for r in s2]
    assert ids == [["A", "B"], ["C", "D"], ["Z"]] or ids == [["A", "B"], ["Z"], ["C", "D"]]


def test_rows_missing_meta_and_positions():
    """Missing courtyards / missing positions → overlap 0.0 (oracle's
    _compute_overlap_area_mm2 early returns)."""
    errors = [_err("courtyards_overlap", ["X", "Y"], (1.0, 1.0), "m")]
    meta = _fake_meta([])  # X/Y absent from courtyards
    o1 = _oracle._generate_report_rows(errors, meta, {})
    s1 = _shim_rows(errors, meta, {})
    assert _rows_key(s1) == _rows_key(o1)
    assert s1[0]["overlap_area_mm2"] == 0.0

    meta2 = _fake_meta(["X", "Y"])
    o2 = _oracle._generate_report_rows(errors, meta2, {})  # positions empty
    s2 = _shim_rows(errors, meta2, {})
    assert _rows_key(s2) == _rows_key(o2)
    assert s2[0]["overlap_area_mm2"] == 0.0


def test_rows_rule_attribute_absent_is_filtered():
    class _NoRule:
        components = ["A", "B"]
        location = (1.0, 2.0)
        message = "no rule attr"

    oracle_rows = _oracle._generate_report_rows([_NoRule()], _fake_meta([]), {})
    shim_rows = _shim_rows([_NoRule()], _fake_meta([]), {})
    assert _rows_key(shim_rows) == _rows_key(oracle_rows) == ()


# ---------------------------------------------------------------------------
# render_report vs oracle _render_report.
# ---------------------------------------------------------------------------


def _row(
    rule="courtyards_overlap",
    refs=("D3", "C4"),
    location_x=10.0,
    location_y=20.0,
    overlap=5.5,
    message="Courtyards overlap",
):
    return {
        "rule": rule,
        "refs_sorted": list(refs),
        "location_x": location_x,
        "location_y": location_y,
        "overlap_area_mm2": overlap,
        "message": message,
        "n_components": len(refs),
        "components": list(refs),
    }


def test_render_oracle_vs_shim_basic():
    rows = [
        _row(overlap=5.5, message="Courtyards overlap D3 and C4"),
        _row(rule="pth_inside_courtyard", refs=("R7",), overlap=0.0, message="PTH inside R7 courtyard"),
        _row(overlap=0.0, message="zero overlap pair"),
    ]
    assert _shim_render(rows) == _oracle._render_report(rows)


def test_render_empty_rows():
    assert _shim_render([]) == _oracle._render_report([])


def test_render_refs_empty_shows_none():
    rows = [_row(refs=(), overlap=0.0, message="no refs")]
    assert _shim_render(rows) == _oracle._render_report(rows)


def test_render_pipe_escaping_and_truncation():
    rows = [
        _row(message="a|b|c with pipe"),
        _row(message="x" * 200, overlap=3.0),
        _row(message="|" + "y" * 130, overlap=4.0),
    ]
    assert _shim_render(rows) == _oracle._render_report(rows)
    assert "\\|" in _shim_render(rows)


def test_render_rule_section_order_is_first_appearance():
    rows = [
        _row(rule="pth_inside_courtyard", refs=("R1",), overlap=0.0),
        _row(rule="courtyards_overlap", refs=("A", "B"), overlap=2.0),
        _row(rule="pth_inside_courtyard", refs=("R2",), overlap=0.0),
    ]
    rendered = _shim_render(rows)
    assert rendered == _oracle._render_report(rows)
    assert rendered.index("### pth_inside_courtyard") < rendered.index("### courtyards_overlap")


def test_render_float_formatting_matches_cpython():
    """Adversarial location/area values must render byte-identically to
    CPython's f"{x:.1f}" / f"{x:.2f}" (fixed-format, round-half-even)."""
    values = [
        0.0, -0.0, 2.675, 0.1, 1e16, 1e-16, 5e-324, 123.456, -0.05, 0.05,
        1.005, 2.5, 3.5, 0.35, 0.25, 1e-5, 1234567.89, -1234.5678, 1.0, -1.5,
    ]
    rng = random.Random(20260804)
    for _ in range(120):
        values.append(rng.uniform(-1e6, 1e6))
    for i, v in enumerate(values):
        rows = [
            _row(refs=(f"R{i}", "Q"), location_x=v, location_y=-v, overlap=0.0),
            _row(rule="pth_inside_courtyard", refs=(f"S{i}",), location_x=v, location_y=v, overlap=abs(v)),
        ]
        oracle_render = _oracle._render_report(rows)
        shim_render = _shim_render(rows)
        assert shim_render == oracle_render, (
            f"value {v!r}: {shim_render!r} != {oracle_render!r}"
        )


def test_render_missing_key_raises_keyerror():
    row = _row()
    del row["message"]
    with pytest.raises(KeyError):
        _oracle._render_report([row])
    with pytest.raises(KeyError):
        _shim_render([row])


def test_render_negative_and_nan_area_renders_emdash():
    rows = [_row(overlap=-3.0), _row(overlap=float("nan"))]
    rendered = _shim_render(rows)
    assert rendered == _oracle._render_report(rows)
    assert "| \u2014 |" in rendered


# ---------------------------------------------------------------------------
# Round-trip: build_report_rows output feeds render_report identically.
# ---------------------------------------------------------------------------


def test_rows_to_render_round_trip_oracle_vs_shim():
    errors = [
        _err("courtyards_overlap", ["D3", "C4"], (10.0, 20.0), "overlap with | pipe"),
        _err("courtyards_overlap", ["A1", "B2"], (1.0, 2.0), "another"),
        _err("pth_inside_courtyard", ["R7"], (30.0, 40.0), "PTH inside"),
        _err("clearance", ["R1"], (5.0, 5.0), "filtered out"),
    ]
    meta = _fake_meta(["D3", "C4", "A1", "B2", "R7"])
    positions = {"D3": (50.0, 50.0, 0), "C4": (50.0, 50.0, 0), "A1": (0.0, 0.0, 0), "B2": (300.0, 300.0, 0)}
    oracle_rows = _oracle._generate_report_rows(errors, meta, positions)
    shim_rows = _shim_rows(errors, meta, positions)
    assert _shim_render(shim_rows) == _oracle._render_report(oracle_rows)
