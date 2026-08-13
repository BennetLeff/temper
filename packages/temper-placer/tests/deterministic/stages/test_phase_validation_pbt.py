"""Property-based tests for the migrated _phase_validation compute.

Wave 4, Phase 5, final leaves. Properties exercise the migrated
``temper_design_bundle_python.deterministic_phase.find_critical_bottleneck_violations_py``
(the delegation shim ``deterministic/stages/_phase_validation.py`` calls it);
bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_phase_validation_rust_differential.py``.

Five properties (R1c):

- P1. Every violation flags a critical cell: its (x, y) is the floored grid
  cell of a placement AND that cell holds a CRITICAL bottleneck.
- P2. Completeness: every in-grid placement whose cell holds a CRITICAL
  bottleneck produces exactly one violation.
- P3. Out-of-grid silence: placements whose floored cell is outside the grid
  never produce a violation.
- P4. Determinism.
- P5. Order preservation: violations appear in placements dict insertion
  order.

Three metamorphic relations (R1d):

- MR1. Unrelated-placement independence: adding an in-grid placement in a
  non-critical cell does not change the existing violations.
- MR2. Removal: deleting a placement removes exactly its own violations.
- MR3. Score-tie first-wins: two CRITICAL bottlenecks with EQUAL score on
  the same cell keep the FIRST bottleneck's layer (deterministic and
  independent of the later one's layer).
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

_DP = _tdb.deterministic_phase
RS = _DP.find_critical_bottleneck_violations_py

_MM = st.floats(min_value=-3.0, max_value=20.0, allow_nan=False, allow_infinity=False)
_SCORE = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_CELL_UM = st.sampled_from([100.0, 250.0, 500.0, 1000.0, 2540.0])
_BOTTLENECK = st.tuples(
    st.integers(min_value=-2, max_value=25),
    st.integers(min_value=-2, max_value=25),
    st.text(min_size=1, max_size=6),
    st.sampled_from(["CRITICAL", "HIGH", "MEDIUM", "LOW"]),
    _SCORE,
)


def _critical_cells(bottlenecks):
    # {cell: (layer, score)} with first-wins-on-tie, mirroring the kernel's
    # per-cell worst-score map (used only for property cross-checks).
    cells = {}
    for x, y, layer, sev, score in bottlenecks:
        if sev != "CRITICAL":
            continue
        key = (x, y)
        if key not in cells or score > cells[key][1]:
            cells[key] = (layer, score)
    return cells


def _floor_cell(mm, cell_um):
    from math import floor

    return floor((float(mm) * 1000.0) / cell_um)


@given(
    st.dictionaries(st.text(min_size=1, max_size=5), st.tuples(_MM, _MM), max_size=6),
    st.lists(_BOTTLENECK, max_size=10),
    _CELL_UM,
    st.integers(min_value=2, max_value=30),
    st.integers(min_value=2, max_value=30),
)
@settings(max_examples=200, deadline=None)
def test_p1_violations_flag_critical_cells(placements, bottlenecks, cell_um, width, height):
    cells = _critical_cells(bottlenecks)
    got = RS(placements, list(bottlenecks), cell_um, width, height)
    for v in got:
        assert (v["x"], v["y"]) in cells
        assert _floor_cell(placements[v["ref"]][0], cell_um) == v["x"]
        assert _floor_cell(placements[v["ref"]][1], cell_um) == v["y"]


@given(
    st.dictionaries(st.text(min_size=1, max_size=5), st.tuples(_MM, _MM), max_size=6),
    st.lists(_BOTTLENECK, max_size=10),
    _CELL_UM,
    st.integers(min_value=2, max_value=30),
    st.integers(min_value=2, max_value=30),
)
@settings(max_examples=200, deadline=None)
def test_p2_completeness(placements, bottlenecks, cell_um, width, height):
    cells = _critical_cells(bottlenecks)
    got = RS(placements, list(bottlenecks), cell_um, width, height)
    got_refs = {v["ref"] for v in got}
    expected = set()
    for ref, (x_mm, y_mm) in placements.items():
        gx = _floor_cell(x_mm, cell_um)
        gy = _floor_cell(y_mm, cell_um)
        if 0 <= gx < width and 0 <= gy < height and (gx, gy) in cells:
            expected.add(ref)
    assert got_refs == expected


@given(
    st.dictionaries(st.text(min_size=1, max_size=5), st.tuples(_MM, _MM), max_size=6),
    st.lists(_BOTTLENECK, max_size=10),
    _CELL_UM,
    st.integers(min_value=2, max_value=30),
    st.integers(min_value=2, max_value=30),
)
@settings(max_examples=200, deadline=None)
def test_p3_out_of_grid_silent(placements, bottlenecks, cell_um, width, height):
    got = RS(placements, list(bottlenecks), cell_um, width, height)
    for v in got:
        assert 0 <= v["x"] < width and 0 <= v["y"] < height


@given(
    st.dictionaries(st.text(min_size=1, max_size=5), st.tuples(_MM, _MM), max_size=6),
    st.lists(_BOTTLENECK, max_size=10),
    _CELL_UM,
    st.integers(min_value=2, max_value=30),
    st.integers(min_value=2, max_value=30),
)
@settings(max_examples=200, deadline=None)
def test_p4_determinism(placements, bottlenecks, cell_um, width, height):
    a = RS(placements, list(bottlenecks), cell_um, width, height)
    b = RS(placements, list(bottlenecks), cell_um, width, height)
    assert a == b


@given(
    st.dictionaries(st.text(min_size=1, max_size=5), st.tuples(_MM, _MM), max_size=6),
    st.lists(_BOTTLENECK, max_size=10),
    _CELL_UM,
    st.integers(min_value=2, max_value=30),
    st.integers(min_value=2, max_value=30),
)
@settings(max_examples=200, deadline=None)
def test_p5_order_preserved(placements, bottlenecks, cell_um, width, height):
    got = RS(placements, list(bottlenecks), cell_um, width, height)
    refs = [v["ref"] for v in got]
    assert refs == [r for r in placements if r in refs]


@given(
    st.dictionaries(st.text(min_size=1, max_size=5), st.tuples(_MM, _MM), max_size=5),
    st.lists(_BOTTLENECK, max_size=8),
    _CELL_UM,
    st.integers(min_value=4, max_value=20),
    st.integers(min_value=4, max_value=20),
)
@settings(max_examples=150, deadline=None)
def test_mr1_unrelated_placement_independence(placements, bottlenecks, cell_um, width, height):
    base = RS(placements, list(bottlenecks), cell_um, width, height)
    # Place a component in a cell with no CRITICAL bottleneck (guaranteed by
    # a cell boundary of the grid that no bottleneck occupies).
    free_x = next((c for c in range(width) if not any(
        x == c and 0 <= y < height and sev == "CRITICAL" for x, y, _, sev, _ in bottlenecks
    )), None)
    if free_x is None:
        return  # every column has a critical bottleneck -- vacuous skip
    if "EXTRA" in placements:
        return  # ref collision with an existing placement -- vacuous skip
    # The nudge into the free_x cell must be a FRACTION of the cell's own
    # width, not a flat mm constant: `_CELL_UM` samples cell_um=100.0 (a
    # 0.1mm-wide cell), and a flat `+0.2` mm push overshoots that cell by 2
    # full cells, landing EXTRA in an arbitrary (possibly CRITICAL) column
    # instead of the intended free one -- this is what falsified the
    # property (placements={}, bottlenecks with (0, 0, ..., 'CRITICAL', 0.0)
    # occupying column 0 and (3, 5, ..., 'CRITICAL', 0.0) occupying column
    # 3, cell_um=100.0, width=4: free_x resolves to 1, but the flat +0.2mm
    # nudge put EXTRA's grid cell at (3, 5) -- exactly the second critical
    # cell). `grid_index`'s `floor(mm * 1000.0 / cell_um)` (deterministic_
    # phase.rs) matches the P1-P5 properties above, which all still pass;
    # production was never wrong here, only this fixture's un-scaled offset.
    cell_mm = cell_um / 1000.0
    extra = {"EXTRA": (free_x * cell_mm + 0.2 * cell_mm, 0.5)}
    combined = dict(placements)
    combined["EXTRA"] = extra["EXTRA"]
    got = RS(combined, list(bottlenecks), cell_um, width, height)
    assert got == base


@given(
    st.dictionaries(st.text(min_size=1, max_size=5), st.tuples(_MM, _MM), max_size=5),
    st.lists(_BOTTLENECK, max_size=8),
    _CELL_UM,
    st.integers(min_value=4, max_value=20),
    st.integers(min_value=4, max_value=20),
)
@settings(max_examples=150, deadline=None)
def test_mr2_removal_removes_only_own(placements, bottlenecks, cell_um, width, height):
    if not placements:
        return
    victim = next(iter(placements))
    full = RS(placements, list(bottlenecks), cell_um, width, height)
    rest = {r: p for r, p in placements.items() if r != victim}
    partial = RS(rest, list(bottlenecks), cell_um, width, height)
    assert partial == [v for v in full if v["ref"] != victim]


@given(
    st.tuples(_MM, _MM),
    st.text(min_size=1, max_size=5),
    _CELL_UM,
    st.integers(min_value=4, max_value=20),
    st.integers(min_value=4, max_value=20),
)
@settings(max_examples=150, deadline=None)
def test_mr3_score_tie_first_wins(pos, ref, cell_um, width, height):
    x = _floor_cell(pos[0], cell_um)
    y = _floor_cell(pos[1], cell_um)
    if not (0 <= x < width and 0 <= y < height):
        return
    score = 0.5
    first = (x, y, "FIRST", "CRITICAL", score)
    second = (x, y, "SECOND", "CRITICAL", score)
    got = RS({ref: pos}, [first, second], cell_um, width, height)
    assert len(got) == 1
    assert got[0]["layer"] == "FIRST"
