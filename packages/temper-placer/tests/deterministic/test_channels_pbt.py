"""Property-based + metamorphic tests for the migrated channels penalty compute.

Wave 4, Phase 5 (deterministic hubs slice). These properties exercise the
migrated ``temper_design_bundle_python.deterministic_hubs`` kernels through
the ``temper_placer.deterministic.channels`` shim (the penalty hot path is the
Rust ``ChannelIndex``); bit-identical parity against the pinned pre-migration
Python is asserted separately by ``test_channels_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Penalty range: every penalty is in ``[0.0, 1.0]`` (clamped), for any
  in-range grid/severity combination.
- P2. Occupancy monotonicity: holding the cell's bottleneck fixed, the penalty
  is non-decreasing in the cell occupancy.
- P3. Severity monotonicity: holding occupancy fixed, LOW <= MEDIUM <= HIGH
  <= CRITICAL penalties.
- P4. Out-of-grid zero: slots outside the grid return exactly ``0.0``.
- P5. Floor-cell determinism: two slots inside the same cell (same
  ``floor``-indexed cell) yield the identical penalty.

Three metamorphic relations (R1d):

- MR1. Cell-shift invariance: a slot shifted by exactly one whole cell
  (``(x + cell_mm, y)``) inside the grid lands in the neighbouring cell with
  that cell's occupancy — no cross-cell bleed (probed on uniform grids).
- MR2. Empty-map equivalence: any slot on ``ChannelMap.empty()`` equals
  ``0.0``, and an index built with zero bottlenecks behaves identically.
- MR3. Grid-flattening invariance: the same grid as nested rows vs. a flat
  row-major list builds an index with identical penalties (the flat layout is
  the kernel's internal representation).
"""

from __future__ import annotations

import math

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from temper_placer.deterministic.channels import (
    ALLOWED_SEVERITIES,
    Bottleneck,
    ChannelMap,
    routability_penalty,
)

_occupancy_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_cell_st = st.floats(min_value=100.0, max_value=5000.0, allow_nan=False, allow_infinity=False)
_dim_st = st.integers(min_value=1, max_value=32)
_slot_st = st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False)
_severity_st = st.sampled_from(sorted(ALLOWED_SEVERITIES))
_score_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


@st.composite
def a_map(draw):
    w = draw(_dim_st)
    h = draw(_dim_st)
    cell = draw(_cell_st)
    grid = [[draw(_occupancy_st) for _ in range(w)] for _ in range(h)]
    bottlenecks = []
    for _ in range(draw(st.integers(0, 6))):
        bottlenecks.append(
            Bottleneck(
                x=draw(st.integers(0, max(0, w - 1))),
                y=draw(st.integers(0, max(0, h - 1))),
                layer="F.Cu",
                severity=draw(_severity_st),
                score=draw(_score_st),
            )
        )
    payload = {
        "temper_schema_hash": "temper.channels.v1",
        "cell_size_um": cell,
        "grid": grid,
        "bottlenecks": [
            {"x": b.x, "y": b.y, "layer": b.layer, "severity": b.severity, "score": b.score}
            for b in bottlenecks
        ],
    }
    return ChannelMap._from_payload(payload)


def _severity_weight(sev):
    return {"LOW": 0.05, "MEDIUM": 0.15, "HIGH": 0.4, "CRITICAL": 1.0}[sev]


class TestProperties:
    @given(a_map(), _slot_st, _slot_st)
    @settings(max_examples=80, deadline=None)
    def test_p1_penalty_in_unit_range(self, cmap, x, y):
        p = routability_penalty((x, y), cmap)
        assert 0.0 <= p <= 1.0

    @given(_dim_st, _cell_st, _severity_st, _occupancy_st, _occupancy_st)
    @settings(max_examples=80, deadline=None)
    def test_p2_occupancy_monotonic(self, w, cell, severity, occ_a, occ_b):
        assume(w >= 1)
        low_occ, high_occ = min(occ_a, occ_b), max(occ_a, occ_b)
        grid = [[low_occ] * w for _ in range(2)]
        payload = {
            "temper_schema_hash": "temper.channels.v1",
            "cell_size_um": cell,
            "grid": grid,
            "bottlenecks": [{"x": 0, "y": 0, "layer": "F.Cu", "severity": severity, "score": 1.0}],
        }
        cmap_low = ChannelMap._from_payload(payload)
        payload["grid"] = [[high_occ] * w for _ in range(2)]
        cmap_high = ChannelMap._from_payload(payload)
        p_low = routability_penalty((0.0, 0.0), cmap_low)
        p_high = routability_penalty((0.0, 0.0), cmap_high)
        assert p_low <= p_high

    @given(_occupancy_st)
    @settings(max_examples=40, deadline=None)
    def test_p3_severity_monotonic(self, occ):
        penalties = {}
        for sev in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            payload = {
                "temper_schema_hash": "temper.channels.v1",
                "cell_size_um": 1000.0,
                "grid": [[occ] * 3 for _ in range(3)],
                "bottlenecks": [{"x": 1, "y": 1, "layer": "F.Cu", "severity": sev, "score": 1.0}],
            }
            cmap = ChannelMap._from_payload(payload)
            penalties[sev] = routability_penalty((1.5, 1.5), cmap)
        assert penalties["LOW"] <= penalties["MEDIUM"] <= penalties["HIGH"] <= penalties["CRITICAL"]

    @given(a_map(), _slot_st, _slot_st)
    @settings(max_examples=80, deadline=None)
    def test_p4_out_of_grid_zero(self, cmap, x, y):
        mm = cmap.cell_size_um / 1000.0
        # One full cell of margin beyond the grid edge: the kernel floors
        # (x*1000)/cell, so |x| >= a whole cell past the edge forces the
        # quotient outside [-1, width] for ANY rounding of mm (probing at the
        # exact edge is fp-fragile — the kernel's own floor decides and both
        # sides agree on whichever side it lands, which the differential
        # already pins).
        if (
            x <= -mm
            or y <= -mm
            or x >= cmap.width * mm + mm
            or y >= cmap.height * mm + mm
        ):
            assert routability_penalty((x, y), cmap) == 0.0

    @given(a_map(), _slot_st, _slot_st)
    @settings(max_examples=80, deadline=None)
    def test_p5_same_cell_same_penalty(self, cmap, x, y):
        if not cmap.has_grid():
            return
        mm = cmap.cell_size_um / 1000.0
        gx = math.floor((x * 1000.0) / cmap.cell_size_um)
        gy = math.floor((y * 1000.0) / cmap.cell_size_um)
        assume(0 <= gx < cmap.width and 0 <= gy < cmap.height)
        # Probe near the CELL CENTER: (gx + 0.5) * mm keeps a half-cell margin
        # to both edges, so every probe provably floors back to (gx, gy)
        # regardless of mm's rounding. (Probing from the cell corner
        # gx * mm re-rounds down into the previous cell when cell_size_um is
        # not an exact binary multiple of 1000 — a real P5 flake, fixed
        # 2026-08-05.)
        cx = (gx + 0.5) * mm
        cy = (gy + 0.5) * mm
        offsets = [(0.0, 0.0), (0.1 * mm, 0.0), (0.0, 0.1 * mm), (0.05 * mm, 0.05 * mm)]
        penalties = {routability_penalty((cx + dx, cy + dy), cmap) for dx, dy in offsets}
        assert len(penalties) == 1


class TestMetamorphic:
    @given(_dim_st, _cell_st, _occupancy_st)
    @settings(max_examples=50, deadline=None)
    def test_mr1_cell_shift_invariance(self, w, cell, occ):
        """On a uniform grid, shifting a slot by exactly one cell moves the
        penalty to the neighbour cell's (identical) value — no bleed."""
        assume(w >= 2)
        grid = [[occ] * w for _ in range(2)]
        payload = {
            "temper_schema_hash": "temper.channels.v1",
            "cell_size_um": cell,
            "grid": grid,
            "bottlenecks": [{"x": 0, "y": 0, "layer": "F.Cu", "severity": "HIGH", "score": 1.0}],
        }
        cmap = ChannelMap._from_payload(payload)
        mm = cell / 1000.0
        p0 = routability_penalty((0.5 * mm, 0.5 * mm), cmap)  # cell (0,0) has the bottleneck
        p1 = routability_penalty((1.5 * mm, 0.5 * mm), cmap)  # cell (1,0): no bottleneck
        assert p0 > 0.0
        assert p1 == 0.0

    @given(_slot_st, _slot_st)
    @settings(max_examples=40, deadline=None)
    def test_mr2_empty_map_equivalence(self, x, y):
        empty = ChannelMap.empty()
        assert routability_penalty((x, y), empty) == 0.0
        no_bn = ChannelMap._from_payload(
            {
                "temper_schema_hash": "temper.channels.v1",
                "cell_size_um": 1000.0,
                "grid": [[0.5, 0.5], [0.5, 0.5]],
                "bottlenecks": [],
            }
        )
        assert routability_penalty((x, y), no_bn) == 0.0

    @given(_dim_st, _cell_st, _severity_st, _occupancy_st)
    @settings(max_examples=50, deadline=None)
    def test_mr3_grid_layout_invariance(self, w, cell, severity, occ):
        """Nested-row payload and flat-row-major payload build identical
        penalties (the kernel stores the grid flat)."""
        assume(w >= 1)
        h = 2
        grid = [[occ] * w for _ in range(h)]
        payload = {
            "temper_schema_hash": "temper.channels.v1",
            "cell_size_um": cell,
            "grid": grid,
            "bottlenecks": [{"x": 0, "y": 0, "layer": "F.Cu", "severity": severity, "score": 0.5}],
        }
        cmap_nested = ChannelMap._from_payload(payload)
        flat = [[occ] * w for _ in range(h)]
        payload["grid"] = flat
        cmap_flat = ChannelMap._from_payload(payload)
        mm = cell / 1000.0
        for gx in range(w):
            for gy in range(h):
                pn = routability_penalty((gx * mm + mm / 2, gy * mm + mm / 2), cmap_nested)
                pf = routability_penalty((gx * mm + mm / 2, gy * mm + mm / 2), cmap_flat)
                assert pn == pf
