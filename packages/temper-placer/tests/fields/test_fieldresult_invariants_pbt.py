"""Property-based fail-closed contract tests for ``FieldResult`` (R20).

Validates the sum-type invariant and grid↔flat round-trip across
Hypothesis-generated inputs per the four-layer PBT pattern.

R20 invariants:
  - UNMEASURED ⟺ field is None (equivalence, both directions).
  - CLEAN/VIOLATIONS ⟺ field present (non-None grid).
  - No construction path yields UNMEASURED-with-grid or
    CLEAN/VIOLATIONS-without-grid.
  - UNMEASURED cannot be coerced to a flat/zero field
    (to_cost_field_input raises FieldNotReadyError).
  - Grid↔flat round-trip: for any grid shape, CostField grid →
    to_flat → reshape is the identity.

Fail-capable: deliberately-inconsistent constructions are rejected
at the ``__post_init__`` guard; no construction path can bypass the
guard because the dataclass is ``frozen=True``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis.strategies import floats, integers, sampled_from

from temper_placer.fields import CostField, FieldNotReadyError, FieldResult
from temper_placer.placer.cp_sat.gates import GateResult, GateStatus, Violation, ViolationType

_MAX_GRID_DIM = 200


def _gate_result(status: GateStatus) -> GateResult:
    """Construct a GateResult with the given status."""
    if status is GateStatus.VIOLATIONS:
        return GateResult(
            GateStatus.VIOLATIONS,
            violations=(Violation(type=ViolationType.THERMAL, description="hot"),),
        )
    if status is GateStatus.UNMEASURED:
        return GateResult(
            GateStatus.UNMEASURED,
            error_message="synthetic error for PBT",
        )
    return GateResult(GateStatus.CLEAN)


# ---------------------------------------------------------------------------
# R20: Constructor-fuzz — sum-type invariant over all construction paths
# ---------------------------------------------------------------------------


class TestFieldResultSumTypeInvariant:
    """Theorem: UNMEASURED ⟺ field is None; CLEAN/VIOLATIONS ⟺ field present.

    Across ALL construction paths (Hypothesis generates all three statuses
    with both field=None and field=Some(grid)), the ``__post_init__`` guard
    enforces the equivalence.
    """

    @pytest.mark.property
    @given(
        status=sampled_from([GateStatus.CLEAN, GateStatus.VIOLATIONS, GateStatus.UNMEASURED]),
        has_field=sampled_from([True, False]),
    )
    @settings(max_examples=200, deadline=30000)
    def test_post_init_rejects_invalid_combinations(self, status, has_field):
        """Every construction that violates the invariant raises ValueError."""
        gr = _gate_result(status)
        field = np.ones((3, 3), dtype=np.float32) if has_field else None

        is_valid = (status is GateStatus.UNMEASURED) == (field is None)

        if is_valid:
            # Must construct successfully
            fr = FieldResult(gate_result=gr, field=field)
            assert fr.status is status
            assert (field is None) == (fr.field is None)
            if field is not None:
                np.testing.assert_array_equal(fr.field, field)
        else:
            # Must raise ValueError — guard rejects inconsistent construction
            with pytest.raises(ValueError):
                FieldResult(gate_result=gr, field=field)

    @pytest.mark.property
    @given(
        h=integers(min_value=1, max_value=_MAX_GRID_DIM),
        w=integers(min_value=1, max_value=_MAX_GRID_DIM),
        status=sampled_from([GateStatus.CLEAN, GateStatus.VIOLATIONS]),
    )
    @settings(max_examples=100, deadline=30000)
    def test_clean_or_violations_always_has_grid(self, h, w, status):
        """CLEAN/VIOLATIONS FieldResult always has a non-None field."""
        grid = np.zeros((h, w), dtype=np.float32)
        gr = _gate_result(status)
        fr = FieldResult(gate_result=gr, field=grid)
        assert fr.field is not None
        assert fr.field.shape == (h, w)
        assert fr.is_usable

    def test_unmeasured_always_has_none_field(self):
        """UNMEASURED FieldResult always has field=None."""
        gr = _gate_result(GateStatus.UNMEASURED)
        fr = FieldResult(gate_result=gr)
        assert fr.field is None
        assert not fr.is_usable
        assert fr.status is GateStatus.UNMEASURED

    def test_clean_without_grid_rejected(self):
        """Fail-capable: CLEAN without field is rejected at the guard."""
        with pytest.raises(ValueError, match="requires a non-None field"):
            FieldResult(gate_result=GateResult(GateStatus.CLEAN), field=None)

    def test_violations_without_grid_rejected(self):
        """Fail-capable: VIOLATIONS without field is rejected at the guard."""
        gr = GateResult(
            GateStatus.VIOLATIONS,
            violations=(Violation(type=ViolationType.THERMAL),),
        )
        with pytest.raises(ValueError, match="requires a non-None field"):
            FieldResult(gate_result=gr, field=None)

    def test_unmeasured_with_grid_rejected(self):
        """Fail-capable: UNMEASURED with a grid is rejected at the guard."""
        gr = GateResult(GateStatus.UNMEASURED, error_message="solver failed")
        grid = np.zeros((10, 10), dtype=np.float32)
        with pytest.raises(ValueError, match="UNMEASURED.*field=None"):
            FieldResult(gate_result=gr, field=grid)


# ---------------------------------------------------------------------------
# R20: UNMEASURED cannot be coerced to a flat/zero field
# ---------------------------------------------------------------------------


class TestUnmeasuredCannotBeCoercedToFlat:
    """Theorem: An UNMEASURED FieldResult cannot be coerced to a usable
    CostFieldInput — to_cost_field_input() always raises FieldNotReadyError.
    """

    @pytest.mark.property
    @given(
        error_msg=sampled_from(
            [
                "solver did not converge",
                "import failed",
                "no PCB available",
                "measurement timeout",
                "",
            ]
        ),
    )
    @settings(max_examples=100, deadline=30000)
    def test_to_cost_field_input_raises_for_unmeasured(self, error_msg):
        gr = GateResult(GateStatus.UNMEASURED, error_message=error_msg)
        fr = FieldResult(gate_result=gr)
        assert not fr.is_usable
        with pytest.raises(FieldNotReadyError):
            fr.to_cost_field_input()

    @pytest.mark.property
    @given(
        h=integers(min_value=1, max_value=100),
        w=integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100, deadline=30000)
    def test_to_cost_field_input_succeeds_for_clean(self, h, w):
        """CLEAN FieldResult coerces to CostFieldInput without error."""
        grid = np.zeros((h, w), dtype=np.float32)
        fr = FieldResult(gate_result=GateResult(GateStatus.CLEAN), field=grid)
        cfi = fr.to_cost_field_input()
        assert cfi.cost_flat.shape == (h * w,)
        assert cfi.cost_flat.dtype == np.float32

    @pytest.mark.property
    @given(
        h=integers(min_value=1, max_value=100),
        w=integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100, deadline=30000)
    def test_to_cost_field_input_succeeds_for_violations(self, h, w):
        """VIOLATIONS FieldResult coerces to CostFieldInput without error
        (the field is still usable for routing even though the gate flagged violations)."""
        grid = np.zeros((h, w), dtype=np.float32)
        gr = GateResult(
            GateStatus.VIOLATIONS,
            violations=(Violation(type=ViolationType.THERMAL),),
        )
        fr = FieldResult(gate_result=gr, field=grid)
        cfi = fr.to_cost_field_input()
        assert cfi.cost_flat.shape == (h * w,)
        assert cfi.cost_flat.dtype == np.float32


# ---------------------------------------------------------------------------
# R20: Grid↔flat round-trip identity (catches row/col-major, off-by-one)
# ---------------------------------------------------------------------------


class TestCostFieldGridFlatRoundTrip:
    """Theorem: For any grid shape, CostField grid → to_flat → reshape is
    the identity (catches row/col-major confusion and off-by-one errors).
    """

    @pytest.mark.property
    @given(
        h=integers(min_value=1, max_value=_MAX_GRID_DIM),
        w=integers(min_value=1, max_value=_MAX_GRID_DIM),
    )
    @settings(max_examples=200, deadline=30000, suppress_health_check=[HealthCheck.too_slow])
    def test_roundtrip_flat_reshape_identity(self, h, w):
        """Grid → to_flat → reshape(h, w) reproduces the original grid."""
        original = np.arange(h * w, dtype=np.float32).reshape(h, w)
        cf = CostField(grid=original, cell_size_mm=1.0, origin_mm=(0.0, 0.0))
        flat = cf.to_flat()
        assert flat.shape == (h * w,)
        restored = flat.reshape(h, w)
        np.testing.assert_array_equal(restored, original)

    @pytest.mark.property
    @given(
        h=integers(min_value=1, max_value=100),
        w=integers(min_value=1, max_value=100),
    )
    @settings(max_examples=200, deadline=30000)
    def test_roundtrip_preserves_dtype_and_values(self, h, w):
        """Any float32 grid survives round-trip with identity values and dtype."""
        rng = np.random.RandomState(42)
        original = rng.rand(h, w).astype(np.float32)
        cf = CostField(grid=original.copy(), cell_size_mm=0.5, origin_mm=(10.0, 20.0))
        flat = cf.to_flat()
        assert flat.dtype == np.float32
        restored = flat.reshape(h, w)
        np.testing.assert_array_equal(restored, original)

    @pytest.mark.property
    @given(
        h=integers(min_value=1, max_value=100),
        w=integers(min_value=1, max_value=100),
        fill_value=floats(min_value=-1000.0, max_value=1000.0),
    )
    @settings(max_examples=200, deadline=30000)
    def test_roundtrip_constant_grid(self, h, w, fill_value):
        """A constant-filled grid of any value survives round-trip (off-by-one check)."""
        original = np.full((h, w), fill_value, dtype=np.float32)
        cf = CostField(grid=original.copy(), cell_size_mm=0.25, origin_mm=(0.0, 0.0))
        flat = cf.to_flat()
        restored = flat.reshape(h, w)
        np.testing.assert_array_equal(restored, original)
        assert cf.total_cells == h * w

    @pytest.mark.property
    @given(
        h=integers(min_value=1, max_value=_MAX_GRID_DIM),
        w=integers(min_value=1, max_value=_MAX_GRID_DIM),
    )
    @settings(max_examples=200, deadline=30000, suppress_health_check=[HealthCheck.too_slow])
    def test_to_flat_cell_index_matches_row_major(self, h, w):
        """Each cell at (r, c) maps to flat index r * cols + c (row-major)."""
        grid = np.arange(h * w, dtype=np.float32).reshape(h, w)
        cf = CostField(grid=grid, cell_size_mm=1.0, origin_mm=(0.0, 0.0))
        flat = cf.to_flat()
        for r in range(h):
            for c in range(w):
                idx = r * w + c
                assert flat[idx] == grid[r, c], f"Cell ({r},{c}) mismatched"

    # -------------------------------------------------------------------
    # Fail-capable: row/col-major off-by-one would break the round-trip
    # -------------------------------------------------------------------

    def test_fail_capable_col_major_flatten_would_fail_roundtrip(self):
        """Demonstrate that a col-major flatten would NOT round-trip."""
        original = np.arange(6, dtype=np.float32).reshape(2, 3)
        cf = CostField(grid=original, cell_size_mm=1.0, origin_mm=(0.0, 0.0))
        flat = cf.to_flat()
        # Col-major reshape would produce a different order
        restored_row_major = flat.reshape(2, 3, order="C")
        np.testing.assert_array_equal(restored_row_major, original)
        # If someone used F-order reshape, it would NOT match
        restored_col_major = flat.reshape(2, 3, order="F")
        assert not np.array_equal(restored_col_major, original), (
            "Fortran-order reshape MUST differ (proves col-major is wrong for this data)"
        )

    def test_fail_capable_wrong_dimension_reshape_would_fail(self):
        """Off-by-one shape error (e.g. w vs h swap) would break round-trip."""
        original = np.arange(12, dtype=np.float32).reshape(3, 4)
        cf = CostField(grid=original, cell_size_mm=1.0, origin_mm=(0.0, 0.0))
        flat = cf.to_flat()
        # Correct reshape matches
        assert flat.reshape(3, 4).shape == (3, 4)
        # Swapped dims would NOT be equal content-wise
        swapped = flat.reshape(4, 3)
        assert not np.array_equal(swapped, original), (
            "Height/width swap MUST produce different layout (proves off-by-one would be caught)"
        )


# ---------------------------------------------------------------------------
# R20: Construction-path audit — no path can bypass the fail-closed guard
# ---------------------------------------------------------------------------


class TestFieldResultNoSilentBypass:
    """Audit: verify no construction path can bypass the ``__post_init__`` guard.

    ``FieldResult`` is ``@dataclass(frozen=True)``.  Frozen dataclasses use
    ``object.__setattr__`` to set fields and always invoke ``__post_init__``.
    There is no code path (including ``dataclasses.replace``) that skips
    ``__post_init__`` on a frozen dataclass, so the fail-closed invariant
    holds for every constructed instance.
    """

    def test_frozen_instance_cannot_be_mutated_via_normal_setattr(self):
        """A valid FieldResult is frozen — normal attribute mutation raises."""
        grid = np.ones((5, 5), dtype=np.float32)
        fr = FieldResult(gate_result=GateResult(GateStatus.CLEAN), field=grid)
        with pytest.raises(FrozenInstanceError):
            fr.field = None  # type: ignore[misc]

    def test_frozen_instance_cannot_have_status_changed_via_normal_setattr(self):
        """A CLEAN FieldResult cannot be flipped via normal setattr."""
        grid = np.ones((5, 5), dtype=np.float32)
        fr = FieldResult(gate_result=GateResult(GateStatus.CLEAN), field=grid)
        with pytest.raises(FrozenInstanceError):
            fr.gate_result = GateResult(GateStatus.UNMEASURED)  # type: ignore[misc]

    def test_object_setattr_can_bypass_frozen_guard_documented(self):
        """`object.__setattr__` can bypass the frozen guard — this is a known
        Python limitation of frozen dataclasses (not a FieldResult-specific bug).
        The post_init invariant is the real guard; frozen is defense-in-depth."""
        grid = np.ones((5, 5), dtype=np.float32)
        fr = FieldResult(gate_result=GateResult(GateStatus.CLEAN), field=grid)
        # Known bypass: object-level setattr sidesteps the frozen __setattr__
        object.__setattr__(fr, "field", None)
        # After bypass, field is now None but gate_result status is still CLEAN —
        # this violates the invariant but is a Python limitation, not a
        # FieldResult design flaw. The __post_init__ guard catches bad
        # construction; frozen is defense-in-depth, not a security boundary.
        assert fr.field is None
