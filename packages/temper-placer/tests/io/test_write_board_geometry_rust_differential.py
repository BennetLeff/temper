"""Differential test: Rust write-board geometry/formatting kernels
(``temper_design_bundle_python.write_board_geometry``) vs the pinned Python
oracle.

Wave 4, Phase 3 (formats/IO) -- migrates the two numeric kernels embedded in
``temper_placer/io/_write_board.py``: ``_reorient_pads``'s per-pad angle
update and ``state_to_placements``'s original-angle offset preservation.
See ``packages/temper-design-bundle/src/write_board_geometry.rs``'s module
docstring for what was and was not ported, and why.

The Rust symbols must reproduce the pre-migration implementation of
``_write_board.py`` bit-identically, pinned verbatim (as statement-level
extractions) as the oracle (``_write_board_py_oracle.py``, commit
``550cab2a3``). Floats are compared as exact bit patterns via
``float.hex()``.

RED before GREEN: this file is written and committed BEFORE
``write_board_geometry.rs`` is registered into the built extension, so
``_tdb.write_board_geometry`` does not exist yet and every test here fails
at collection. That failure is the proof the differential was never
vacuously green.

The delegation tests at the bottom of this file are a SEPARATE proof from
the bit-exactness tests above: a green differential compares the oracle
against the Rust kernel directly and passes whether or not the SHIPPED
``_write_board.py`` module actually calls it. Monkeypatching the Rust
symbol to raise and calling the shipped entry point is the only thing that
proves the production code path was rewired, not left as a second,
unreachable implementation next to the first.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
import temper_design_bundle_python as _tdb

import tests.io._write_board_py_oracle as _oracle
from temper_placer.core.state import PlacementState
from temper_placer.io import _write_board as shipped

# Rust symbols under test -- must exist or this file fails to collect (RED).
_GEOM = _tdb.write_board_geometry
REORIENT_PAD_ANGLE = _GEOM.reorient_pad_angle_py
PRESERVE_ROTATION_OFFSET = _GEOM.preserve_rotation_offset_py


def _f(value) -> str:
    """Bit-exact float key; ``None`` passes through unchanged."""
    return "None" if value is None else float(value).hex()


# ---------------------------------------------------------------------------
# reorient_pad_angle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "current_angle,delta_deg",
    [
        (None, 90.0),
        (0.0, 90.0),
        (10.0, 90.0),
        (270.0, 90.0),  # wraps past 360 -> 0.0 -> None
        (0.0, -90.0),  # negative delta, CPython floored-mod sign quirk
        (10.0, -90.0),
        (350.0, 20.0),  # 370 % 360 == 10.0
        (45.0, 315.0),  # exact multiple -> 0.0 -> None
        (None, -90.0),  # None -> 0.0 -> -90 % 360 == 270.0
        (0.0, -720.0),  # exact-multiple negative delta: CPython gives +0.0
        (123.456, 37.125),
        (359.999, 0.002),  # crosses 360 by a hair
    ],
)
def test_reorient_pad_angle_matches_oracle_bit_exact(current_angle, delta_deg):
    py_result = _oracle.reorient_pad_angle(current_angle, delta_deg)
    rust_result = REORIENT_PAD_ANGLE(current_angle, delta_deg)
    assert _f(rust_result) == _f(py_result)


def test_reorient_pad_angle_exact_zero_result_is_none():
    """Dedicated named test: a result of exactly 0.0 must encode as None
    (kiutils omits the angle token, which means 0 in KiCad)."""
    py_result = _oracle.reorient_pad_angle(45.0, 315.0)
    rust_result = REORIENT_PAD_ANGLE(45.0, 315.0)
    assert py_result is None
    assert rust_result is None


def test_reorient_pad_angle_negative_delta_wraps_positive():
    """Dedicated named test: CPython's floored `%` always returns a
    non-negative result for a positive divisor -- Rust's raw `%` would
    return -90.0 here, which this kernel must NOT do."""
    py_result = _oracle.reorient_pad_angle(0.0, -90.0)
    rust_result = REORIENT_PAD_ANGLE(0.0, -90.0)
    assert py_result == 270.0
    assert rust_result == pytest.approx(270.0)


def test_reorient_pad_angle_none_current_treated_as_zero():
    """Dedicated named test: `current_angle=None` reads as 0.0 (Python's
    `pad.position.angle or 0.0`), matching a pad with no angle token."""
    py_result = _oracle.reorient_pad_angle(None, 45.0)
    rust_result = REORIENT_PAD_ANGLE(None, 45.0)
    assert py_result == 45.0
    assert rust_result == pytest.approx(45.0)


@pytest.mark.parametrize("delta_deg", [0.0, 360.0, -360.0, 720.0, -720.0])
def test_reorient_delta_is_noop_matches_oracle(delta_deg):
    """`reorient_delta_is_noop` is the caller-side early-exit guard -- pure
    control flow, not ported to Rust (see write_board_geometry.rs's module
    docstring). Pinned here anyway so a change to its semantics is caught."""
    assert _oracle.reorient_delta_is_noop(delta_deg) is True


# ---------------------------------------------------------------------------
# preserve_rotation_offset
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rotation_deg,original_angle",
    [
        (0.0, 90.0),  # exactly on a 90-multiple: no offset applied
        (0.0, 45.0),  # round-half-to-even TIE: round(0.5) -> 0 (even)
        (180.0, 135.0),  # TIE: round(1.5) -> 2 (even) -> quantized 180
        (180.0, 225.0),  # TIE: round(2.5) -> 2 (even) -> quantized 180
        (0.0, 315.0),  # TIE: round(3.5) -> 4 (even) -> quantized 360
        (90.0, 46.0),  # small offset > 0.1 threshold
        (0.0, 0.05),  # offset below the 0.1 threshold: NOT applied
        (270.0, -10.0),  # negative original angle
        (0.0, 359.95),  # near-360 wrap after offset application
        (90.0, 91.0),
    ],
)
def test_preserve_rotation_offset_matches_oracle_bit_exact(rotation_deg, original_angle):
    py_result = _oracle.preserve_rotation_offset(rotation_deg, original_angle)
    rust_result = PRESERVE_ROTATION_OFFSET(rotation_deg, original_angle)
    assert _f(rust_result) == _f(py_result)


def test_preserve_rotation_offset_below_threshold_unchanged():
    """Dedicated named test: an offset with |offset| <= 0.1 leaves
    rotation_deg untouched (strict `>` threshold, not `>=`)."""
    py_result = _oracle.preserve_rotation_offset(90.0, 90.1)
    rust_result = PRESERVE_ROTATION_OFFSET(90.0, 90.1)
    assert py_result == 90.0
    assert rust_result == pytest.approx(90.0)


def test_preserve_rotation_offset_exact_threshold_boundary_excluded():
    """Dedicated named test: |offset| exactly 0.1 is excluded (strict `>`)."""
    py_result = _oracle.preserve_rotation_offset(0.0, 90.1)
    rust_result = PRESERVE_ROTATION_OFFSET(0.0, 90.1)
    assert py_result == 0.0
    assert rust_result == pytest.approx(0.0)


def test_preserve_rotation_offset_45_degree_tie_matches_oracle():
    """Dedicated named test for the round-half-to-even tie this migration
    was specifically warned about: 45/90 == 0.5 exactly, and CPython's
    round() ties to the EVEN integer (0), not away from zero (1)."""
    py_result = _oracle.preserve_rotation_offset(0.0, 45.0)
    rust_result = PRESERVE_ROTATION_OFFSET(0.0, 45.0)
    # quantized = round(0.5) * 90 = 0.0 (ties-to-even); offset = 45.0 - 0.0
    # = 45.0, |offset| > 0.1, so rotation becomes (0.0 + 45.0) % 360 = 45.0.
    assert py_result == 45.0
    assert rust_result == pytest.approx(45.0)


def test_preserve_rotation_offset_wraps_modulo_360():
    """Dedicated named test: the final `% 360.0` wrap is exercised, not
    just the offset arithmetic."""
    py_result = _oracle.preserve_rotation_offset(270.0, 269.0)
    rust_result = PRESERVE_ROTATION_OFFSET(270.0, 269.0)
    assert py_result == pytest.approx(269.0)
    assert rust_result == pytest.approx(269.0)


# ---------------------------------------------------------------------------
# Shipped-module delegation proof -- NOT a bit-exactness check.
# ---------------------------------------------------------------------------


def test_reorient_pads_delegates_to_rust():
    """The SHIPPED `_write_board._reorient_pads` must reach the Rust
    kernel, not just have a differential proving the kernel is correct in
    isolation. Monkeypatch the Rust symbol to raise; call the shipped
    entry point; the raise must propagate.
    """
    sentinel = RuntimeError("REACHED_RUST_REORIENT")

    def boom(*_a, **_k):
        raise sentinel

    fp = SimpleNamespace(pads=[SimpleNamespace(position=SimpleNamespace(angle=10.0))])

    original = _GEOM.reorient_pad_angles_py
    _GEOM.reorient_pad_angles_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_REORIENT"):
            shipped._reorient_pads(fp, 0.0, 90.0)
    finally:
        _GEOM.reorient_pad_angles_py = original


def test_state_to_placements_delegates_to_rust():
    """The SHIPPED `state_to_placements` must reach the Rust
    `preserve_rotation_offset_py` kernel when an original (non-90°) angle
    is supplied, not just have a differential proving the kernel is
    correct in isolation."""
    sentinel = RuntimeError("REACHED_RUST_PRESERVE_OFFSET")

    def boom(*_a, **_k):
        raise sentinel

    state = PlacementState(
        positions=np.array([[10.0, 20.0]]),
        rotation_logits=np.array([[1.0, 0.0, 0.0, 0.0]]),
    )
    original_angles = {"U1": 45.0}

    original = _GEOM.preserve_rotation_offset_py
    _GEOM.preserve_rotation_offset_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_PRESERVE_OFFSET"):
            shipped.state_to_placements(state, ["U1"], original_angles=original_angles)
    finally:
        _GEOM.preserve_rotation_offset_py = original
