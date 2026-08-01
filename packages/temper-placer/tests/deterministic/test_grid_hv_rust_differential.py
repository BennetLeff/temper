"""Differential tests: HV creepage-factor application and zone→component
selection, Rust vs oracle.

Wave 3 candidate #1: the pure compute of
``temper_placer/deterministic/stages/_grid_hv.py`` moved to the
``temper-geometry`` crate (``packages/temper-geometry/src/grid_raster.rs``):

- ``effective_creepage`` → ``effective_creepage_py(is_outer, base)``.
  The ``layer ∈ OUTER_COPPER_LAYERS`` membership test stays Python (it
  resolves against the board's layer constants — configuration, not
  compute); the factor application (identity vs ``base * 0.30``) is Rust.
- the spatial fallback of ``hv_pad_set`` (in-bounds filter + closest
  component by squared distance, first-min tie-breaking) →
  ``closest_component_for_zone_py``.  The ConfigError raising and the
  explicit-refdes path stay Python.

Bit-exactness notes:
- ``INTERNAL_LAYER_CREEPAGE_FACTOR = 0.30`` is the same f64 literal on
  both sides; ``base * 0.30`` is a single rounded multiply.
- ``(x - zx) ** 2`` in the reference is libm ``pow(x - zx, 2.0)``
  (CPython float_pow); the Rust kernel resolves ``pow`` via ``dlsym``.
- Python's ``min`` keeps the FIRST minimal element in iteration order;
  the Rust scan updates only on strict ``<``, preserving it.  The wrapper
  passes positions in dict-insertion order.
"""

from __future__ import annotations

import random

import pytest
import temper_geometry as _tg

from temper_placer.deterministic.stages._grid_hv import effective_creepage, hv_pad_set

# ---------------------------------------------------------------------------
# Oracles: the pre-migration implementations, verbatim
# ---------------------------------------------------------------------------

_INTERNAL_LAYER_CREEPAGE_FACTOR: float = 0.30


def _oracle_effective_creepage(is_outer: bool, base_creepage_mm: float) -> float:
    if is_outer:
        return base_creepage_mm
    return base_creepage_mm * _INTERNAL_LAYER_CREEPAGE_FACTOR


def _oracle_closest_component_for_zone(positions, zx, zy, half_w, half_h):
    """The spatial fallback of hv_pad_set, verbatim.

    ``positions`` is the ordered list of ``(ref, (x, y))`` from
    ``component_positions.items()``.
    """
    candidates = [
        (ref, pos)
        for ref, pos in positions
        if (zx - half_w) <= pos[0] <= (zx + half_w) and (zy - half_h) <= pos[1] <= (zy + half_h)
    ]
    if not candidates:
        return None
    closest_ref, _ = min(
        candidates,
        key=lambda item: (item[1][0] - zx) ** 2 + (item[1][1] - zy) ** 2,
    )
    return closest_ref


# ---------------------------------------------------------------------------
# effective_creepage
# ---------------------------------------------------------------------------


def test_effective_creepage_matches_oracle_on_random_inputs():
    rng = random.Random(20260731)
    for _ in range(500):
        is_outer = rng.random() < 0.5
        base = rng.uniform(0.0, 30.0)
        rust = _tg.effective_creepage_py(is_outer, base)
        oracle = _oracle_effective_creepage(is_outer, base)
        assert rust == oracle
    # exact boundary values
    for base in (0.0, 0.3, 1.0, 6.0, 1e-9, 1e9, 2.5e-308):
        assert _tg.effective_creepage_py(True, base) == _oracle_effective_creepage(True, base)
        assert _tg.effective_creepage_py(False, base) == _oracle_effective_creepage(False, base)


def test_effective_creepage_wrapper_matches_layer_names():
    # The wrapper resolves OUTER_COPPER_LAYERS membership; factor application
    # is Rust.  Standard names from the board constants exercise both arms.
    assert effective_creepage("F.Cu", 6.0) == 6.0
    assert effective_creepage("B.Cu", 6.0) == 6.0
    assert effective_creepage("In1.Cu", 6.0) == pytest.approx(6.0 * 0.30)
    assert effective_creepage("In2.Cu", 6.0) == pytest.approx(6.0 * 0.30)


# ---------------------------------------------------------------------------
# closest_component_for_zone
# ---------------------------------------------------------------------------


def _rust_closest(positions, zx, zy, half_w, half_h):
    return _tg.closest_component_for_zone_py(
        [(ref, x, y) for ref, (x, y) in positions], zx, zy, half_w, half_h
    )


def test_closest_component_matches_oracle_on_random_inputs():
    rng = random.Random(31337)
    for _ in range(500):
        n = rng.randrange(0, 15)
        positions = []
        for i in range(n):
            x = rng.uniform(-50.0, 50.0)
            y = rng.uniform(-50.0, 50.0)
            positions.append((f"C{i}", (x, y)))
        zx, zy = rng.uniform(-30.0, 30.0), rng.uniform(-30.0, 30.0)
        half_w, half_h = rng.uniform(0.0, 40.0), rng.uniform(0.0, 40.0)
        rust = _rust_closest(positions, zx, zy, half_w, half_h)
        oracle = _oracle_closest_component_for_zone(positions, zx, zy, half_w, half_h)
        assert rust == oracle


def test_closest_component_tie_keeps_first_in_order():
    # Two candidates at exactly the same squared distance: min keeps the
    # first in iteration order, and the Rust first-min scan must agree.
    positions = [("A", (10.0, 0.0)), ("B", (10.0, 0.0))]
    assert _rust_closest(positions, 10.0, 0.0, 1.0, 1.0) == "A"
    positions = [("B", (10.0, 0.0)), ("A", (10.0, 0.0))]
    assert _rust_closest(positions, 10.0, 0.0, 1.0, 1.0) == "B"


def test_closest_component_bounds_and_empty():
    positions = [("C0", (5.0, 5.0)), ("C1", (50.0, 50.0))]
    # C1 is outside the zone bounds -> never selected even though closer
    assert _rust_closest(positions, 0.0, 0.0, 10.0, 10.0) == "C0"
    # No component inside the zone
    assert _rust_closest(positions, 100.0, 100.0, 1.0, 1.0) is None
    # Empty position list
    assert _rust_closest([], 0.0, 0.0, 10.0, 10.0) is None


def test_hv_pad_set_wrapper_end_to_end():
    """hv_pad_set keeps its public behaviour through the Rust fallback."""
    pads = [
        {"ref": "U3", "name": "1"},
        {"ref": "U3", "name": "2"},
        {"ref": "R1", "name": "1"},
        {"ref": "R1", "name": "2"},
    ]
    component_positions = {"U3": (10.0, 10.0), "R1": (40.0, 40.0)}
    zones = [
        type(
            "Z",
            (),
            {
                "component_refdes": None,
                "center": (10.0, 10.0),
                "size": (6.0, 6.0),
                "name": "HV_Z1",
            },
        )()
    ]
    result = hv_pad_set(pads, zones, component_positions)
    assert result == {("U3", "1"), ("U3", "2")}

    # Explicit refdes path is untouched (orchestration stays Python)
    zones[0].component_refdes = "R1"
    result = hv_pad_set(pads, zones, component_positions)
    assert result == {("R1", "1"), ("R1", "2")}
