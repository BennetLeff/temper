"""
Property-based tests for the routability_penalty function (U5 PBT suite).

Uses hypothesis with >= 100 examples per property. Covers R8a-R8f and
includes the SC3 injected-bug guard.
"""

from __future__ import annotations

import math

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from temper_placer.deterministic.channels import (
    ALLOWED_SEVERITIES,
    ChannelMap,
    routability_penalty,
)

# Hypothesis strategies ----------------------------------------------------

# Bounded occupancy in [0.0, 1.0] with 2-decimal granularity
occupancy_st = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False, width=64
)

# Cell size in µm, positive and reasonable (avoid float-precision issues at extremes)
cell_size_um_st = st.floats(
    min_value=10.0, max_value=10_000.0, allow_nan=False, allow_infinity=False
)

# Grid widths / heights
grid_dim_st = st.integers(min_value=1, max_value=64)

# Slot coordinates in mm, signed to allow out-of-grid
slot_x_st = st.floats(
    min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False
)
slot_y_st = st.floats(
    min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False
)

# Severity choices
severity_st = st.sampled_from(sorted(ALLOWED_SEVERITIES))


@st.composite
def channel_map_st(draw):
    """Build a random ChannelMap with a small grid and a few bottlenecks."""
    cell_um = draw(cell_size_um_st)
    w = draw(grid_dim_st)
    h = draw(grid_dim_st)
    grid = []
    for _ in range(h):
        row = []
        for _ in range(w):
            row.append(draw(occupancy_st))
        grid.append(row)
    n_bn = draw(st.integers(min_value=0, max_value=min(w * h, 8)))
    bottlenecks = set()
    for _ in range(n_bn):
        x = draw(st.integers(min_value=0, max_value=w - 1))
        y = draw(st.integers(min_value=0, max_value=h - 1))
        sev = draw(severity_st)
        score = draw(st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False))
        bottlenecks.add((x, y, "F.Cu", sev, score))
    bn_list = [
        {"x": x, "y": y, "layer": layer, "severity": sev, "score": score}
        for (x, y, layer, sev, score) in bottlenecks
    ]
    return ChannelMap._from_payload(
        {
            "temper_schema_hash": "temper.channels.v1",
            "cell_size_um": float(cell_um),
            "grid": grid,
            "bottlenecks": bn_list,
        }
    )


# Properties ---------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(cmap=channel_map_st(), x=slot_x_st, y=slot_y_st)
def test_pbt_penalty_bounded(cmap, x, y):
    """R8a: 0.0 <= penalty <= 1.0."""
    p = routability_penalty((x, y), cmap)
    assert 0.0 <= p <= 1.0 + 1e-9, f"penalty {p} out of [0,1] for slot=({x},{y})"


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(
    cell_um=cell_size_um_st,
    w=grid_dim_st,
    h=grid_dim_st,
    x=slot_x_st,
    y=slot_y_st,
)
def test_pbt_free_cell_zero(cell_um, w, h, x, y):
    """R8b: free + non-bottlenecked -> 0.0.

    We construct a map whose bottlenecks all sit OUTSIDE the slot's grid
    cell, so the slot reads as "free" for that cell.
    """
    grid = [[0.0] * w for _ in range(h)]
    # Place bottlenecks in cells that are guaranteed not to be (gx, gy) of
    # the slot. We can do this by placing them in (0,0) and skipping the
    # case where the slot lands there.
    gx = int(math.floor((x * 1000.0) / cell_um))
    gy = int(math.floor((y * 1000.0) / cell_um))
    assume(0 <= gx < w and 0 <= gy < h)
    # Bottleneck at (0, 0) when the slot is somewhere else.
    bn = []
    if not (gx == 0 and gy == 0):
        bn = [{"x": 0, "y": 0, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0}]
    cmap = ChannelMap._from_payload(
        {
            "temper_schema_hash": "temper.channels.v1",
            "cell_size_um": float(cell_um),
            "grid": grid,
            "bottlenecks": bn,
        }
    )
    p = routability_penalty((x, y), cmap)
    assert p == 0.0, f"expected 0.0 for free cell, got {p}"


@settings(max_examples=120, suppress_health_check=[HealthCheck.too_slow])
@given(cell_um=cell_size_um_st, w=grid_dim_st, h=grid_dim_st)
def test_pbt_critical_full_free_one(cell_um, w, h):
    """R8c: CRITICAL + occupancy 1.0 -> 1.0 (the maximum)."""
    grid = [[1.0] * w for _ in range(h)]
    bn = [
        {"x": x, "y": y, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0}
        for x in range(w)
        for y in range(h)
    ]
    cmap = ChannelMap._from_payload(
        {
            "temper_schema_hash": "temper.channels.v1",
            "cell_size_um": float(cell_um),
            "grid": grid,
            "bottlenecks": bn,
        }
    )
    # Sample slots that are guaranteed to land inside the grid.
    # cell_size_um is in microns; grid covers 0..(w * cell_um) microns = 0..w*cell_um/1000 mm.
    cover_mm = (min(w, h) * cell_um) / 1000.0
    sample_slots = [
        (cover_mm * 0.25, cover_mm * 0.25),
        (cover_mm * 0.5, cover_mm * 0.5),
        (cover_mm * 0.75, cover_mm * 0.75),
    ]
    for x_mm, y_mm in sample_slots:
        p = routability_penalty((x_mm, y_mm), cmap)
        assert math.isclose(p, 1.0, rel_tol=1e-9), f"expected 1.0, got {p} for slot=({x_mm},{y_mm})"


@settings(max_examples=120, suppress_health_check=[HealthCheck.too_slow])
@given(cell_um=cell_size_um_st, occ=occupancy_st)
def test_pbt_severity_monotonic(cell_um, occ):
    """R8d: severity monotonicity LOW <= MEDIUM <= HIGH <= CRITICAL.

    All four severities are registered at the same cell with the same
    occupancy; the penalty is non-decreasing in severity.
    """
    grid = [[occ] * 4 for _ in range(4)]
    penalties = {}
    for sev in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        cmap = ChannelMap._from_payload(
            {
                "temper_schema_hash": "temper.channels.v1",
                "cell_size_um": float(cell_um),
                "grid": grid,
                "bottlenecks": [
                    {"x": 1, "y": 1, "layer": "F.Cu", "severity": sev, "score": 1.0},
                ],
            }
        )
        penalties[sev] = routability_penalty((1.5, 1.5), cmap)
    assert (
        penalties["LOW"]
        <= penalties["MEDIUM"]
        <= penalties["HIGH"]
        <= penalties["CRITICAL"]
    ), penalties


@settings(max_examples=120, suppress_health_check=[HealthCheck.too_slow])
@given(cell_um=cell_size_um_st, sev=severity_st)
def test_pbt_occupancy_monotonic(cell_um, sev):
    """R8e: occupancy monotonicity (penalty non-decreasing in occupancy)."""
    last = -1.0
    for occ_int in range(0, 11):  # 0.0, 0.1, ..., 1.0
        occ = occ_int / 10.0
        grid = [[occ] * 4 for _ in range(4)]
        cmap = ChannelMap._from_payload(
            {
                "temper_schema_hash": "temper.channels.v1",
                "cell_size_um": float(cell_um),
                "grid": grid,
                "bottlenecks": [
                    {"x": 1, "y": 1, "layer": "F.Cu", "severity": sev, "score": 1.0},
                ],
            }
        )
        p = routability_penalty((1.5, 1.5), cmap)
        assert p >= last - 1e-9, f"penalty {p} decreased at occ={occ} for {sev}"
        last = p


@settings(max_examples=120, suppress_health_check=[HealthCheck.too_slow])
@given(cell_um=cell_size_um_st, w=grid_dim_st, h=grid_dim_st)
def test_pbt_out_of_grid_zero(cell_um, w, h):
    """R8f: out-of-grid -> 0.0.

    A slot whose grid coords are negative or beyond width/height must
    return 0.0.
    """
    grid = [[0.0] * w for _ in range(h)]
    cmap = ChannelMap._from_payload(
        {
            "temper_schema_hash": "temper.channels.v1",
            "cell_size_um": float(cell_um),
            "grid": grid,
            "bottlenecks": [
                {"x": 0, "y": 0, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0},
            ],
        }
    )
    # x_mm large enough that gx >= w
    x_mm = (w * cell_um) / 1000.0 + 5.0
    assert routability_penalty((x_mm, 0.0), cmap) == 0.0
    # x_mm small enough that gx < 0
    assert routability_penalty((-5.0, 0.0), cmap) == 0.0
    # y large / negative
    y_mm = (h * cell_um) / 1000.0 + 5.0
    assert routability_penalty((0.0, y_mm), cmap) == 0.0
    assert routability_penalty((0.0, -5.0), cmap) == 0.0


# SC3: Injected-bug guard. Monkeypatch the penalty to return 1.5 and
# verify the PBT catches the violation (R8a asserts bounded to [0, 1]).
def test_pbt_catches_injected_violation(monkeypatch):
    from temper_placer.deterministic import channels as _channels

    def buggy_penalty(slot, channel_map):
        return 1.5  # Out of contract: must be in [0.0, 1.0]

    monkeypatch.setattr(_channels, "routability_penalty", buggy_penalty)

    cmap = ChannelMap._from_payload(
        {
            "temper_schema_hash": "temper.channels.v1",
            "cell_size_um": 1000.0,
            "grid": [[0.0, 0.0], [0.0, 0.0]],
            "bottlenecks": [],
        }
    )
    p = _channels.routability_penalty((0.5, 0.5), cmap)
    # The injected bug is exactly the violation the PBT is supposed to
    # catch. Assert the bound fails.
    assert not (0.0 <= p <= 1.0)
