"""Differential tests: temper-quality-oracle aesthetic kernel vs the pinned
Python reference (Wave 4 — ``metrics/aesthetic.py``).

The pre-migration implementation is pinned verbatim below in the
``_oracle_*`` block (a character-identical copy of ``compute_aesthetic_score``
as committed at ``origin/main``).  Every float assertion is **bit-exact**:
compared through ``float.hex()`` via the ``key()`` normaliser, never a
tolerance.

Recorded divergence (the Wave-4 tie-break rule: report and record, do not fake)
-------------------------------------------------------------------------------
The committed module contains a **dead branch**: its ``get_prefix_groups``
helper was retired with the JAX migration and now raises
``NotImplementedError``, so ``compute_aesthetic_score`` could never complete
for a non-empty placement — the only reachable pre-migration behavior was
the ``n == 0`` early return.  The consumer
(``validation.human_reference_extractor``) swallows the exception and emits
no aesthetic metrics, which is why the module was never observed failing.

The migration therefore cannot assert bit-parity against the *verbatim*
oracle on non-empty inputs — the oracle raises.  The honest resolution:

- ``test_empty_input_bit_identical_to_oracle`` — the one truly reachable
  pre-migration behavior, asserted bit-for-bit against the verbatim oracle.
- ``test_oracle_raises_on_nonempty`` — pins that the committed module
  raises, so the divergence is a measured fact, not an assumption.
- ``test_nonempty_arithmetic_bit_exact`` — asserts the Rust kernel against
  ``_module_formula_reference``, a clearly-labelled evaluation of the
  **module's own formulas** (grid snap, orientation, aggregate) with the
  dead call resolved to its specified consequence: with no prefix groups the
  module's ``else`` branch makes ``alignment_score`` its vacuous ``1.0``.
  The reference arm is numpy, the tested arm is Rust — a true differential
  for the substantive compute.
- ``test_flags_are_load_bearing`` — pins the NEP 50 dtype discriminators
  (the grid-snap and argmax coordinates that genuinely differ between the
  f32 and f64 chains), so the flags are not decorative.

Bit-exactness notes (catalog: ``docs/wave4-discipline-contract.md`` §2):

- **B1 — ``np.log`` is host libm ``log``.**  Measured on numpy 2.3.5
  (200k random samples): ``np.log`` is bit-identical to the host C library
  ``log``, which the Rust kernel resolves through ``dlsym``.
- **B11 — the 4-term entropy ``np.sum`` is naive.**  numpy sums naively
  below 8 elements, so the entropy reduction is a plain left-to-right fold.
- **B12 — numpy ufunc comparisons.**  ``np.minimum`` propagates NaN from
  either operand and returns the *second* argument on ``a == b``; ``np.clip``
  expands to ``min(max(x, lo), hi)``.  The Rust side replicates both.
- **NEP 50 — the grid-snap and argmax chains run in the source dtype.**
  ``PlacementState.positions`` is float32 by default; ``np.mod`` /
  ``np.minimum`` / ``< 0.01`` and ``np.argmax`` all operate in f32 then.
  The kernel receives ``positions_are_f32`` / ``rotations_are_f32`` flags and
  reproduces the two dtype chains exactly.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest
import temper_quality_oracle as _tqo

from temper_placer.metrics import aesthetic as mod

# ---------------------------------------------------------------------------
# VERBATIM pre-migration oracle — do not edit, they are the reference.
#
# Copied character-for-character from
# `packages/temper-placer/src/temper_placer/metrics/aesthetic.py` as
# committed at origin/main.  The only change is the `_oracle_` name prefix
# and the `get_prefix_groups` stub left exactly as committed (it raises).
# ---------------------------------------------------------------------------


def _oracle_compute_aesthetic_score(
    state,
    netlist,
    grid_size: float = 0.5,
) -> dict[str, float]:
    """
    Compute a multi-factor aesthetic score for a placement.

    Scores range from 0.0 (poor) to 1.0 (perfect).

    Factors:
    1. Grid Snap: Fraction of components perfectly on grid.
    2. Alignment: How well components with same prefix align to axes.
    3. Orientation: Entropy of rotation distribution (lower is better).
    4. Compactness: Ratio of component area to bounding box area.

    Returns:
        Dictionary of individual scores and an aggregated 'aesthetic_index'.
    """
    positions = np.array(state.positions)
    rotations = np.array(state.rotation_logits)
    n = positions.shape[0]

    if n == 0:
        return {"aesthetic_index": 1.0}

    # 1. Grid Snap Score
    x_off = np.mod(positions[:, 0], grid_size)
    y_off = np.mod(positions[:, 1], grid_size)
    dist_x = np.minimum(x_off, grid_size - x_off)
    dist_y = np.minimum(y_off, grid_size - y_off)

    # Components within 0.01mm of grid are considered "snapped"
    snapped = (dist_x < 0.01) & (dist_y < 0.01)
    grid_score = np.mean(snapped)

    # 2. Orientation Score
    # Get dominant rotations
    rotation_indices = np.argmax(rotations, axis=1)
    counts = np.bincount(rotation_indices, minlength=4)
    probs = counts / n
    entropy = -np.sum(probs * np.log(probs + 1e-8))

    # Normalized entropy (max is log(4) approx 1.38)
    # Score is 1.0 if all same rotation, ~0.0 if perfectly mixed
    orientation_score = np.clip(1.0 - (entropy / 1.386), 0.0, 1.0)

    # 3. Alignment Score (Prefix-based)
    def get_prefix_groups(*a, **kw):
        raise NotImplementedError("get_prefix_groups removed (JAX retirement)")

    prefix_groups_arr = get_prefix_groups(netlist)
    prefix_groups = []
    if prefix_groups_arr.shape[0] > 0:
        for i in range(prefix_groups_arr.shape[0]):
            group = prefix_groups_arr[i]
            valid = group[group != -1]
            if len(valid) > 1:
                prefix_groups.append(valid)

    alignment_scores = []
    for group in prefix_groups:
        group_pos = positions[group]
        var = np.var(group_pos, axis=0)
        # If variance in either axis is very low (< 0.1mm), it's aligned
        is_aligned = np.min(var) < 0.01
        alignment_scores.append(1.0 if is_aligned else 0.0)

    alignment_score = np.mean(alignment_scores) if alignment_scores else 1.0

    # Aggregate
    aesthetic_index = (grid_score * 0.4) + (orientation_score * 0.3) + (alignment_score * 0.3)

    return {
        "grid_snap_score": float(grid_score),
        "orientation_score": float(orientation_score),
        "prefix_alignment_score": float(alignment_score),
        "aesthetic_index": float(aesthetic_index),
    }


# ---------------------------------------------------------------------------
# Module-formula reference for the substantive (non-empty) path
# ---------------------------------------------------------------------------


def _module_formula_reference(positions, rotations, grid_size: float = 0.5) -> dict[str, float]:
    """The module's own grid/orientation/aggregate formulas, evaluated by
    numpy, with the dead ``get_prefix_groups`` call resolved to its
    specified consequence (no prefix groups -> the module's vacuous
    ``alignment_score = 1.0`` default).

    Every arithmetic expression below is copied from the oracle block; the
    only difference is that the alignment section is replaced by its
    ``else``-branch value.  This is the reference the Rust kernel is pinned
    to for non-empty inputs, because the verbatim oracle raises there.
    """
    positions = np.array(positions)
    rotations = np.array(rotations)
    n = positions.shape[0]
    assert n > 0

    x_off = np.mod(positions[:, 0], grid_size)
    y_off = np.mod(positions[:, 1], grid_size)
    dist_x = np.minimum(x_off, grid_size - x_off)
    dist_y = np.minimum(y_off, grid_size - y_off)
    snapped = (dist_x < 0.01) & (dist_y < 0.01)
    grid_score = np.mean(snapped)

    rotation_indices = np.argmax(rotations, axis=1)
    counts = np.bincount(rotation_indices, minlength=4)
    probs = counts / n
    entropy = -np.sum(probs * np.log(probs + 1e-8))
    orientation_score = np.clip(1.0 - (entropy / 1.386), 0.0, 1.0)

    alignment_score = 1.0

    aesthetic_index = (grid_score * 0.4) + (orientation_score * 0.3) + (alignment_score * 0.3)

    return {
        "grid_snap_score": float(grid_score),
        "orientation_score": float(orientation_score),
        "prefix_alignment_score": float(alignment_score),
        "aesthetic_index": float(aesthetic_index),
    }


# ---------------------------------------------------------------------------
# Bit-exact comparison helpers
# ---------------------------------------------------------------------------


def key(value):
    """A comparison key that cannot conflate types or float bit patterns.

    Floats become ``("float", <hex>)`` — ``float.hex()`` is a lossless,
    exactly-round-tripping rendering, so ``==`` on the key is ``==`` on the
    bit pattern (with ``nan``/``inf`` spelled out rather than compared).
    Dicts are keyed recursively; other leaves carry ``type`` so ``0`` and
    ``0.0`` never compare equal.
    """
    if isinstance(value, float):
        if math.isnan(value):
            return ("float", "nan", math.copysign(1.0, value))
        return ("float", value.hex())
    if isinstance(value, dict):
        return ("dict", tuple((k, key(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(key(v) for v in value))
    return (type(value).__name__, value)


def assert_bit_identical(got, expected, what: str) -> None:
    assert key(got) == key(expected), (
        f"{what}: Rust result is not bit-identical to the reference.\n"
        f"  rust    = {got!r}  key={key(got)}\n"
        f"  ref     = {expected!r}  key={key(expected)}"
    )


def _state(positions, rotations):
    """A PlacementState-compatible object carrying numpy arrays."""
    return SimpleNamespace(
        positions=np.asarray(positions),
        rotation_logits=np.asarray(rotations),
    )


def _rust_direct(positions, rotations, grid_size, positions_are_f32, rotations_are_f32):
    """The Rust pyfunction directly (bypassing the shim)."""
    return dict(
        _tqo.aesthetic_score_py(
            [tuple(r) for r in np.asarray(positions).tolist()],
            [tuple(r) for r in np.asarray(rotations).tolist()],
            grid_size,
            bool(positions_are_f32),
            bool(rotations_are_f32),
        )
    )


# ---------------------------------------------------------------------------
# Differential bit-exactness
# ---------------------------------------------------------------------------


def test_empty_input_bit_identical_to_oracle():
    """The one truly reachable pre-migration path: n == 0 returns only
    ``{"aesthetic_index": 1.0}``.  Verbatim oracle vs both the Rust
    pyfunction and the public shim."""
    state = _state(np.zeros((0, 2), dtype=np.float32), np.zeros((0, 4), dtype=np.float32))
    expected = _oracle_compute_aesthetic_score(state, None)
    assert key(expected) == ("dict", (("aesthetic_index", ("float", "0x1.0000000000000p+0")),))

    via_rust = _rust_direct([], [], 0.5, True, True)
    assert_bit_identical(via_rust, expected, "empty (Rust pyfunction)")

    via_shim = mod.compute_aesthetic_score(state, None)
    assert_bit_identical(via_shim, expected, "empty (public shim)")


def test_oracle_raises_on_nonempty():
    """Pins the dead branch: the committed module raises
    NotImplementedError for any non-empty placement.  This is the measured
    fact behind the recorded divergence (see the module docstring)."""
    state = _state([[0.0, 0.0]], [[1.0, 0.0, 0.0, 0.0]])
    with pytest.raises(NotImplementedError):
        _oracle_compute_aesthetic_score(state, None)


@pytest.mark.parametrize(
    "dtype",
    [np.float32, np.float64],
    ids=["f32", "f64"],
)
def test_nonempty_arithmetic_bit_exact(dtype):
    """The substantive compute (grid + orientation + aggregate, alignment
    resolved to its vacuous default) is bit-identical to the module's own
    formulas, in both source dtypes, for randomized inputs."""
    rng = np.random.default_rng(20260808)
    for _ in range(300):
        n = int(rng.integers(1, 9))
        positions = rng.uniform(-500.0, 500.0, size=(n, 2)).astype(dtype)
        rotations = rng.uniform(-3.0, 3.0, size=(n, 4)).astype(dtype)
        is_f32 = dtype == np.float32

        expected = _module_formula_reference(positions, rotations)
        got = _rust_direct(
            positions, rotations, 0.5, is_f32, is_f32
        )
        assert_bit_identical(got, expected, f"non-empty {dtype.__name__} n={n}")

        via_shim = mod.compute_aesthetic_score(
            _state(positions, rotations), None
        )
        assert_bit_identical(via_shim, expected, f"shim {dtype.__name__} n={n}")


def test_crafted_edge_cases_bit_exact():
    """NaN/inf positions, negative and huge coordinates, all-equal
    rotations, degenerate single-component inputs — both dtypes."""
    cases = [
        # NaN position: mod -> NaN -> comparison False -> not snapped.
        (np.array([[np.nan, 0.0]], dtype=np.float64), np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float64)),
        # +inf position -> mod is NaN -> not snapped.
        (np.array([[np.inf, 0.0]], dtype=np.float64), np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float64)),
        # Negative and huge coordinates (floored mod reaches negative x).
        (np.array([[-1.3, -0.25], [1e15, -1e15], [578.5, 0.01]], dtype=np.float64),
         np.array([[0.0, 0.0, 1.0, 0.0], [1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float64)),
        # All-equal rotations -> argmax first index; NaN logits -> NaN wins.
        (np.array([[0.0, 0.0], [0.5, 0.5]], dtype=np.float64),
         np.array([[0.5, 0.5, 0.5, 0.5], [np.nan, 1.0, 0.0, 0.0]], dtype=np.float64)),
        # Single component.
        (np.array([[0.25, 0.25]], dtype=np.float64), np.array([[0.0, 0.0, 0.0, 1.0]], dtype=np.float64)),
    ]
    for positions, rotations in cases:
        is_f32 = positions.dtype == np.float32
        expected = _module_formula_reference(positions, rotations)
        got = _rust_direct(positions, rotations, 0.5, is_f32, is_f32)
        assert_bit_identical(got, expected, f"crafted {positions.dtype}")
        via_shim = mod.compute_aesthetic_score(_state(positions, rotations), None)
        assert_bit_identical(via_shim, expected, f"crafted shim {positions.dtype}")


def test_flags_are_load_bearing():
    """The dtype flags change real results — the NEP 50 chain is not a
    cosmetic distinction."""
    # Grid-snap discriminator: f64-snapped, f32-not.
    pos = [(578.5099839972382, 0.0)]
    rot = [(0.0, 0.0, 1.0, 0.0)]
    f64 = _rust_direct(pos, rot, 0.5, False, False)
    f32 = _rust_direct(pos, rot, 0.5, True, False)
    assert f64["grid_snap_score"] == 1.0
    assert f32["grid_snap_score"] == 0.0

    # Argmax discriminator: two rows tie under f32 rounding and collapse
    # into one histogram bin, changing the entropy multiset and therefore
    # orientation_score (f64 keeps [1,0,2], f32 collapses to [0,0,2]).
    pos3 = [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]
    rot3 = [
        (0.9999999999999999, 1.0, 0.0, 0.0),
        (1.0, 0.9999999999999999, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
    ]
    f64c = _rust_direct(pos3, rot3, 0.5, False, False)
    f32c = _rust_direct(pos3, rot3, 0.5, False, True)
    assert f64c["orientation_score"].hex() != f32c["orientation_score"].hex()
    # And the f64 arm matches numpy's own f64 computation exactly.
    expected = _module_formula_reference(
        np.array(pos3, dtype=np.float64), np.array(rot3, dtype=np.float64)
    )
    assert_bit_identical(f64c, expected, "argmax f64 arm")
