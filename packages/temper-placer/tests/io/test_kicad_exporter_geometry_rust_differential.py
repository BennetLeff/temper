"""Differential test: Rust KiCad-exporter geometry kernels
(``temper_design_bundle_python.kicad_exporter_geometry``) vs the pinned
Python oracle.

Wave 4, Phase 3 (formats/IO) — migrates the two GEOMETRY/matching kernels out
of ``temper_placer/io/kicad_exporter.py``: ``snap_to_nearest_pad`` and
``_generate_connector_segments``. See
``packages/temper-design-bundle/src/kicad_exporter_geometry.rs``'s module
docstring for what was and was not ported, and why.

The Rust symbols must reproduce the pre-migration implementation of
``kicad_exporter.py`` bit-identically, pinned verbatim as the oracle
(``_kicad_exporter_py_oracle.py``, commit ``71790a0e5``). Floats are compared
as exact bit patterns via ``float.hex()``.

RED before GREEN: this file is written and committed BEFORE
``kicad_exporter_geometry.rs`` is registered into the built extension, so
``_tdb.kicad_exporter_geometry`` does not exist yet and every test here
fails at collection. That failure is the proof the differential was never
vacuously green.
"""

from __future__ import annotations

import pytest
import temper_design_bundle_python as _tdb

import tests.io._kicad_exporter_py_oracle as _oracle
from temper_placer.io.export_types import TraceSegment

# Rust symbols under test — must exist or this file fails to collect (RED).
# Kept `_py`-suffixed (unrenamed) to match the shipped delegation in
# kicad_exporter.py — see kicad_exporter_geometry.rs's module docstring on
# why these are not renamed via `#[pyo3(name = ...)]`.
_GEOM = _tdb.kicad_exporter_geometry
SNAP_TO_NEAREST_PAD = _GEOM.snap_to_nearest_pad_py
GENERATE_CONNECTOR_SEGMENTS = _GEOM.generate_connector_segments_py


def _f(value: float) -> str:
    """Bit-exact float key."""
    return float(value).hex()


def _pos(pos: tuple[float, float]) -> tuple[str, str]:
    return (_f(pos[0]), _f(pos[1]))


def _seg_key(seg: TraceSegment) -> tuple:
    return (seg.net, _pos(seg.start), _pos(seg.end), _f(seg.width), seg.layer)


def _seg_to_tuple(seg: TraceSegment) -> tuple:
    return (seg.net, seg.start, seg.end, seg.width, seg.layer)


# ---------------------------------------------------------------------------
# snap_to_nearest_pad
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "x,y,pad_centers,tolerance",
    [
        (0.0, 0.0, [(0.05, 0.05)], 0.15),
        (0.0, 0.0, [(1.0, 0.0), (0.0, 1.0), (0.05, 0.05)], 0.15),
        (0.0, 0.0, [(5.0, 5.0)], 0.15),  # outside tolerance -> unchanged
        (0.0, 0.0, [], 0.15),  # empty pad_centers -> unchanged
        (1.2345, -6.789, [(1.23, -6.79), (1.3, -6.8)], 0.15),
        # Boundary: dist exactly == tolerance is EXCLUDED (strict <).
        (0.0, 0.0, [(0.15, 0.0)], 0.15),
        # Default tolerance (0.15) exercised via omission below.
    ],
)
def test_snap_to_nearest_pad_identical(x, y, pad_centers, tolerance):
    py_result = _oracle.snap_to_nearest_pad(x, y, pad_centers, tolerance)
    rust_result = SNAP_TO_NEAREST_PAD(x, y, pad_centers, tolerance)
    assert _pos(rust_result) == _pos(py_result)


def test_snap_to_nearest_pad_default_tolerance_identical():
    pad_centers = [(0.1, 0.0), (0.02, 0.0)]
    py_result = _oracle.snap_to_nearest_pad(0.0, 0.0, pad_centers)
    rust_result = SNAP_TO_NEAREST_PAD(0.0, 0.0, pad_centers)
    assert _pos(rust_result) == _pos(py_result)


def test_snap_to_nearest_pad_first_wins_on_exact_tie():
    """Two pads at the EXACT same distance: the oracle's strict `<` never
    replaces an equal-distance candidate, so the FIRST one in list order
    wins. Verified identical on both sides — not merely asserted."""
    pad_centers = [(0.1, 0.0), (-0.1, 0.0)]
    py_result = _oracle.snap_to_nearest_pad(0.0, 0.0, pad_centers, 0.15)
    rust_result = SNAP_TO_NEAREST_PAD(0.0, 0.0, pad_centers, 0.15)
    assert py_result == (0.1, 0.0)
    assert _pos(rust_result) == _pos(py_result)


# ---------------------------------------------------------------------------
# _generate_connector_segments
# ---------------------------------------------------------------------------


def _run_both(segments: list[TraceSegment], pad_centers: dict, max_dist: float = 2.0):
    py_connectors = _oracle._generate_connector_segments(segments, pad_centers, max_dist)

    seg_tuples = [_seg_to_tuple(s) for s in segments]
    pad_tuples = list(pad_centers.items())
    rust_tuples = GENERATE_CONNECTOR_SEGMENTS(seg_tuples, pad_tuples, max_dist)
    rust_connectors = [
        TraceSegment(net=n, start=st, end=en, width=w, layer=layer)
        for (n, st, en, w, layer) in rust_tuples
    ]

    py_keys = [_seg_key(s) for s in py_connectors]
    rust_keys = [_seg_key(s) for s in rust_connectors]
    assert rust_keys == py_keys
    return py_connectors


def test_connector_bridges_dangling_endpoint():
    segments = [TraceSegment(net="GND", start=(0.0, 0.0), end=(1.0, 0.0), width=0.25, layer="F.Cu")]
    pad_centers = {"GND": [(2.5, 0.0)]}
    connectors = _run_both(segments, pad_centers, max_dist=2.0)
    assert len(connectors) == 1


def test_connector_skips_already_connected_pad_exact_match():
    segments = [TraceSegment(net="GND", start=(0.0, 0.0), end=(1.0, 0.0), width=0.25, layer="F.Cu")]
    pad_centers = {"GND": [(1.0, 0.0)]}
    connectors = _run_both(segments, pad_centers)
    assert connectors == []


def test_connector_boundary_exact_match_tolerance_0_01_is_exclusive():
    """`abs(ex-px) < 0.01` — at EXACTLY 0.01 the pad is NOT considered
    already-connected (so it becomes a bridge candidate instead)."""
    segments = [TraceSegment(net="GND", start=(0.0, 0.0), end=(1.0, 0.0), width=0.25, layer="F.Cu")]
    pad_centers = {"GND": [(1.01, 0.0)]}
    connectors = _run_both(segments, pad_centers)
    # Not treated as connected (0.01 is not < 0.01), so a short bridge is
    # generated -- exercising the "near miss" boundary on both sides.
    assert len(connectors) == 1


def test_connector_skips_pad_beyond_max_dist():
    segments = [TraceSegment(net="GND", start=(0.0, 0.0), end=(1.0, 0.0), width=0.25, layer="F.Cu")]
    pad_centers = {"GND": [(10.0, 0.0)]}
    connectors = _run_both(segments, pad_centers, max_dist=2.0)
    assert connectors == []


def test_connector_skips_net_with_no_segments():
    segments: list[TraceSegment] = []
    pad_centers = {"GND": [(1.0, 0.0)]}
    connectors = _run_both(segments, pad_centers)
    assert connectors == []


def test_connector_sequential_pads_same_net_second_bridges_from_first():
    """Second pad on the same net can bridge from the connector endpoint the
    FIRST pad just added -- exercises the oracle's `endpoints.add((px, py))`
    sequential state update."""
    segments = [TraceSegment(net="GND", start=(0.0, 0.0), end=(1.0, 0.0), width=0.25, layer="F.Cu")]
    pad_centers = {"GND": [(2.0, 0.0), (3.5, 0.0)]}
    connectors = _run_both(segments, pad_centers, max_dist=2.0)
    assert len(connectors) == 2


def test_connector_multi_net_preserves_pad_centers_order():
    segments = [
        TraceSegment(net="GND", start=(0.0, 0.0), end=(1.0, 0.0), width=0.25, layer="F.Cu"),
        TraceSegment(net="VCC", start=(0.0, 5.0), end=(1.0, 5.0), width=0.3, layer="B.Cu"),
    ]
    pad_centers = {
        "VCC": [(2.5, 5.0)],
        "GND": [(2.5, 0.0)],
    }
    connectors = _run_both(segments, pad_centers, max_dist=2.0)
    assert len(connectors) == 2
    # Emission order follows pad_centers' dict order: VCC before GND.
    assert connectors[0].net == "VCC"
    assert connectors[1].net == "GND"


def test_connector_uses_ref_seg_width_and_layer_from_matched_endpoint():
    segments = [
        TraceSegment(net="SIG", start=(0.0, 0.0), end=(1.0, 0.0), width=0.15, layer="F.Cu"),
        TraceSegment(net="SIG", start=(1.0, 0.0), end=(1.0, 5.0), width=0.4, layer="In1.Cu"),
    ]
    pad_centers = {"SIG": [(1.0, 6.5)]}
    connectors = _run_both(segments, pad_centers, max_dist=2.0)
    assert len(connectors) == 1
    assert connectors[0].width == 0.4
    assert connectors[0].layer == "In1.Cu"


def test_connector_empty_inputs():
    connectors = _run_both([], {})
    assert connectors == []
