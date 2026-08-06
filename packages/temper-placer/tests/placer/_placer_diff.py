"""Shared comparison helpers for the placer Wave-4 Phase-4 differential suites.

The R1a bar is bit-identical: numpy arrays are compared via ``tobytes()``
(byte-for-byte, dtype-including), floats via ``float.hex()`` (exact binary
pattern), ints by value, and placements dicts on (keys, ordered, typed
values). These helpers exist so every differential file uses the same
comparison conventions and no test can quietly compare with an
``pytest.approx`` that would mask a 1-ULP drift.
"""

from __future__ import annotations

from typing import Any


def assert_array_identical(a, b) -> None:
    """Byte-identical numpy arrays, dtype included."""
    assert a.dtype == b.dtype, f"dtype {a.dtype} != {b.dtype}"
    assert a.shape == b.shape, f"shape {a.shape} != {b.shape}"
    assert a.tobytes() == b.tobytes(), "arrays differ at the byte level"


def float_hex(v: Any) -> str:
    """Exact binary pattern of any float-like (numpy scalars included)."""
    if hasattr(v, "item"):
        v = v.item()
    return float(v).hex()


def assert_placement_equal(placements_a: dict, placements_b: dict) -> None:
    """Placements dicts from ``template.apply``: same keys, same order, and
    each ``(x, y, rot)`` value bit-identical on the floats and equal on the
    int rotation."""
    assert list(placements_a) == list(placements_b), (
        f"key order differs: {list(placements_a)} != {list(placements_b)}"
    )
    for ref, (x_a, y_a, rot_a) in placements_a.items():
        x_b, y_b, rot_b = placements_b[ref]
        assert float_hex(x_a) == float_hex(x_b), f"{ref}: x {x_a!r} != {x_b!r}"
        assert float_hex(y_a) == float_hex(y_b), f"{ref}: y {y_a!r} != {y_b!r}"
        assert rot_a == rot_b, f"{ref}: rot {rot_a} != {rot_b}"


def assert_result_equal(r_a, r_b) -> None:
    """``PlacementResult`` dataclasses: positions/rotations byte-identical,
    placed/unplaced lists equal in order."""
    assert_array_identical(r_a.positions, r_b.positions)
    assert_array_identical(r_a.rotations, r_b.rotations)
    assert list(r_a.placed_refs) == list(r_b.placed_refs)
    assert list(r_a.unplaced_refs) == list(r_b.unplaced_refs)
