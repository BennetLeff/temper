"""FFI spike C7 — wrapper↔Rust int-enum / flat-array conversion pins.

The pyo3 boundaries of temper-geometry / temper-thermal / temper-constraints
now accept int enums (pad shape, heatsink edge, metric/axis/side) and flat
arrays instead of Python-object-tagged types (strings, lists of tuples).
The public Python API is unchanged — the wrappers convert once. These tests
pin the conversion helpers themselves (the single place each tagged type is
mapped), so a drift between a Python mapping dict and the Rust match arms is
caught here even when the differential suites' inputs happen to use only the
canonical values.

The end-to-end bit-exact parity through the wrappers is covered by the
existing differential suites (isolation-barrier, grid-fence, clearance,
corridor, copper-coverage, spice, congestion-tensor, bottleneck-geometry,
thermal-fdm, thermal-scorer, encoder, ipc); this module only pins the
mapping layer.
"""

from __future__ import annotations

import numpy as np
import pytest
import temper_geometry as _tg
import temper_thermal as _tt

from temper_placer.core.pad_geometry import SHAPE_CODES, SHAPE_UNKNOWN_CODE, shape_code
from temper_placer.pcl.rust_bridge import _axis_code, _metric_code, _side_code
from temper_placer.physics.thermal_fdm import _HEATSINK_EDGE_CODES, _heatsink_edge_code

# ---------------------------------------------------------------------------
# Pad-shape enum (pad_geometry.py -> pad_geometry.rs `SHAPE_*`)
# ---------------------------------------------------------------------------


def test_shape_code_maps_known_shapes():
    assert SHAPE_CODES == {"circle": 0, "oval": 1, "rect": 2, "roundrect": 3, "thru_hole": 4}
    for name, code in SHAPE_CODES.items():
        assert shape_code(name) == code


def test_shape_code_unknown_maps_to_sentinel():
    assert shape_code("custom") == SHAPE_UNKNOWN_CODE == 99
    assert shape_code("") == 99


@pytest.mark.parametrize(
    ("code", "width", "height", "expected"),
    [
        (0, 2.0, 2.0, 1.0),  # circle -> width.max/2
        (4, 3.0, 3.0, 1.5),  # thru_hole normalizes to circle
        (1, 4.0, 2.0, 1.0),  # oval -> width.min/2
        (3, 4.0, 2.0, 0.5),  # roundrect -> ratio * width.min
        (2, 4.0, 2.0, 0.0),  # rect -> r=0
        (99, 4.0, 2.0, 0.0),  # unknown -> r=0 (safe fallback)
    ],
)
def test_shape_codes_reach_rust_identically(code, width, height, expected):
    assert _tg.pad_corner_radius_py(width, height, code, 0.25) == expected


def test_fence_samples_shape_codes_match_old_string_semantics():
    # rect-ish codes (oval/rect/roundrect) -> 8 corner+edge samples;
    # circle / thru_hole / unknown -> sample_count_circle points.
    for code in (1, 2, 3):
        assert len(_tg.fence_samples_py(code, 0.0, 0.0, 0.0, 4.0, 2.0, 0.5, 0.25, 16)) == 16
    for code in (0, 4, 99):
        assert len(_tg.fence_samples_py(code, 0.0, 0.0, 1.0, 4.0, 2.0, 0.5, 0.0, 4)) == 8


def test_barrier_pad_tuple_shape_code_matches_string_behavior():
    # (x, y, w, h, shape_code, ratio) — thru_hole (4) behaves as circle.
    gap_th = _tg.barrier_axis_gap_py([(0.0, 0.0, 2.0, 2.0, 4, 0.25)], [(10.0, 0.0, 2.0, 2.0, 4, 0.25)], 0)
    gap_c = _tg.barrier_axis_gap_py([(0.0, 0.0, 2.0, 2.0, 0, 0.25)], [(10.0, 0.0, 2.0, 2.0, 0, 0.25)], 0)
    assert gap_th == gap_c == 8.0


# ---------------------------------------------------------------------------
# Heatsink-edge enum (thermal_fdm.py -> fdm.rs `HEATSINK_*`)
# ---------------------------------------------------------------------------


def test_heatsink_edge_codes_match_rust_contract():
    assert _HEATSINK_EDGE_CODES == {"TOP": 0, "BOTTOM": 1, "LEFT": 2, "RIGHT": 3}
    assert _heatsink_edge_code("TOP") == 0
    assert _heatsink_edge_code(" bottom ") == 1  # .upper().strip() preserved
    assert _heatsink_edge_code("NORTH") == 99  # unrecognized -> no heatsink
    assert _heatsink_edge_code("") == 99


def test_heatsink_edge_code_semantics_reach_rust():
    k = np.asarray([0.3 + 0.1 * i for i in range(20)], dtype=np.float64).tobytes()
    q = np.asarray([0.01 * i for i in range(20)], dtype=np.float64).tobytes()
    # TOP (0) puts a Dirichlet face on the top row; unknown (99) is all
    # Neumann -> the assembled systems differ.
    a_top = _tt.assemble_system_py(k, q, None, 4, 5, 40.0, 0.5, 0)
    a_unknown = _tt.assemble_system_py(k, q, None, 4, 5, 40.0, 0.5, 99)
    assert a_top != a_unknown
    # The four canonical codes are distinct from one another.
    systems = [
        _tt.assemble_system_py(k, q, None, 4, 5, 40.0, 0.5, c) for c in (0, 1, 2, 3)
    ]
    assert len({tuple(vals) for _, _, vals, _ in systems}) == 4


# ---------------------------------------------------------------------------
# Constraint metric/axis/side enums (rust_bridge.py -> temper_constraints lib.rs)
# ---------------------------------------------------------------------------


def test_metric_axis_side_codes():
    assert _metric_code("edge_to_edge") == 0
    assert _metric_code("center_to_center") == 1
    assert _metric_code("pin_to_pin") == 2
    assert _axis_code("x") == 0
    assert _axis_code("y") == 1
    assert _axis_code("major") == 2
    assert _axis_code("minor") == 3
    assert _side_code("top") == 0
    assert _side_code("bottom") == 1
    assert _side_code("left") == 2
    assert _side_code("right") == 3
    for bad, fn in [("bogus", _metric_code), ("z", _axis_code), ("center", _side_code)]:
        with pytest.raises(ValueError):
            fn(bad)


def test_constraint_code_results_match_string_api():
    import temper_constraints as _tc

    positions = [0.0, 0.0, 20.0, 0.0]
    # metric 1 == center_to_center (default), 2 == pin_to_pin.
    assert _tc.compute_adjacent_loss_py(positions, 0, 1, 10.0, 1.0, 1) == 100.0
    assert _tc.compute_adjacent_loss_py(positions, 0, 1, 10.0, 1.0, 2, 1.0, 0.0, -1.0, 0.0) > 0.0


# ---------------------------------------------------------------------------
# Flat-array surfaces keep bit-parity with the pre-conversion element order
# ---------------------------------------------------------------------------


def test_corridor_flat_pairs_bit_parity():
    # The wrapper flattens [(cx, cy), ...] into one int array; the mask
    # must be identical to a reference built from the same cells.
    path = [(2, 3), (5, 1), (0, 0)]
    raw = _tg.extract_corridor_mask([v for cell in path for v in cell], 4, 1, 40, 40)
    mask = np.frombuffer(raw, dtype=np.bool_).reshape(40, 40)
    # cells (2,3) and (0,0) both cover fine (0,0); (5,1) is separate.
    assert mask[12, 8] and mask[15, 11]  # cell (2,3) rect: rows 11..17, cols 7..13
    assert mask[0, 0] and mask[4, 4]  # cell (0,0) rect: rows 0..5, cols 0..5
    assert mask[5, 22] and mask[8, 24]  # cell (5,1) rect: rows 3..9, cols 19..25
    assert not mask[2, 22] and not mask[9, 22]  # outside cell (5,1)'s band
    assert not mask[39, 39]


def test_spice_flat_positions_bit_parity():
    positions = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    flat = [v for pos in positions for v in pos]
    l1 = _tg.spice_loop_inductance_py(flat, 0.035)
    expected = 4.0 * 3.14159265359e-7 * 1e-4 / 3.5e-5
    assert abs(l1 - expected) < 1e-12
    # Reversing the vertex order flips the signed shoelace sum; abs keeps
    # the inductance identical (order parity preserved in the flat form).
    l2 = _tg.spice_loop_inductance_py(list(reversed(flat)), 0.035)
    assert l1 == l2


def test_bottleneck_flat_triples_bit_parity():
    cells = [(0, 1, 1), (0, 0, 0)]
    caps = _tg.cell_capacity_batch_py(
        [v for c in cells for v in c], [0] * 9, [0] * 9, [0] * 9, 3, 3, 1, -1
    )
    assert caps == [4, 4]
    blocked = _tg.hard_blocked_batch_py(
        [v for c in cells for v in c], [0] * 9, [0] * 9, 3, 3, 1
    )
    assert blocked == [False, False]
