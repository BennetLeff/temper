"""Tests for U4 cost-field abstraction and fail-closed FieldResult."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from temper_placer.fields import (
    CostField,
    CostFieldInput,
    FieldGate,
    FieldNotReadyError,
    FieldResult,
)
from temper_placer.placer.cp_sat.gates import (
    GateResult,
    GateStatus,
    Violation,
    ViolationType,
)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestFieldResultHappy:
    """CLEAN GateResult-backed field whose grid matches the occupancy-grid shape."""

    def test_clean_field_result_has_matching_grid_shape(self):
        grid = np.full((30, 40), 0.0, dtype=np.float32)
        result = FieldResult(
            gate_result=GateResult(GateStatus.CLEAN),
            field=grid,
        )
        assert result.status is GateStatus.CLEAN
        assert result.is_usable
        assert result.field.shape == (30, 40)

    def test_clean_field_to_cost_field_input(self):
        grid = np.full((30, 40), 0.5, dtype=np.float32)
        result = FieldResult(
            gate_result=GateResult(GateStatus.CLEAN),
            field=grid,
            weight=2.0,
        )
        cfi = result.to_cost_field_input()
        assert isinstance(cfi, CostFieldInput)
        assert cfi.cost_flat.shape == (30 * 40,)
        assert cfi.cost_flat.dtype == np.float32
        assert cfi.weight == 2.0
        assert cfi.cost_flat[0] == pytest.approx(0.5)

    def test_cost_field_to_flat_congestion_flat_compatible(self):
        cf = CostField(
            grid=np.ones((25, 50), dtype=np.float32) * 3.0,
            cell_size_mm=0.5,
            origin_mm=(10.0, 20.0),
        )
        flat = cf.to_flat()
        assert flat.shape == (25 * 50,)
        assert flat.dtype == np.float32
        assert flat[0] == pytest.approx(3.0)
        np.testing.assert_array_equal(flat, np.full(25 * 50, 3.0, dtype=np.float32))

    def test_cost_field_shape_properties(self):
        cf = CostField(
            grid=np.zeros((15, 35), dtype=np.float32),
            cell_size_mm=0.25,
            origin_mm=(0.0, 0.0),
        )
        assert cf.height_cells == 15
        assert cf.width_cells == 35
        assert cf.shape == (15, 35)
        assert cf.total_cells == 15 * 35

    def test_field_result_shortcuts(self):
        v = Violation(type=ViolationType.THERMAL, description="hot")
        gr = GateResult(GateStatus.VIOLATIONS, violations=(v,))
        result = FieldResult(gate_result=gr, field=np.zeros((5, 5), dtype=np.float32))
        assert result.status is GateStatus.VIOLATIONS
        assert len(result.violations) == 1
        assert result.violations[0].type is ViolationType.THERMAL
        assert result.error_message == ""
        assert result.is_usable


# ---------------------------------------------------------------------------
# Edge: no silent-flat / zero-grid path
# ---------------------------------------------------------------------------

class TestFieldResultNoSilentFlat:
    """A VIOLATIONS/failed result with an implicit zero grid is impossible."""

    def test_violations_result_must_have_field(self):
        with pytest.raises(ValueError, match="requires a non-None field"):
            FieldResult(
                gate_result=GateResult(
                    GateStatus.VIOLATIONS,
                    violations=(Violation(type=ViolationType.THERMAL),),
                ),
                field=None,
            )

    def test_clean_result_must_have_field(self):
        with pytest.raises(ValueError, match="requires a non-None field"):
            FieldResult(
                gate_result=GateResult(GateStatus.CLEAN),
                field=None,
            )

    def test_unmeasured_result_must_not_have_field(self):
        with pytest.raises(ValueError, match="UNMEASURED.*field=None"):
            FieldResult(
                gate_result=GateResult(
                    GateStatus.UNMEASURED,
                    error_message="solver diverged",
                ),
                field=np.zeros((10, 10), dtype=np.float32),
            )

    def test_unmeasured_cannot_be_converted_to_cost_field_input(self):
        result = FieldResult(
            gate_result=GateResult(
                GateStatus.UNMEASURED,
                error_message="thermal solver did not converge",
            ),
            field=None,
        )
        assert not result.is_usable
        with pytest.raises(FieldNotReadyError, match="UNMEASURED.*thermal solver"):
            result.to_cost_field_input()

    def test_gate_result_empty_violations_is_rejected(self):
        with pytest.raises(ValueError, match="must have at least one Violation"):
            GateResult(GateStatus.VIOLATIONS, violations=())


# ---------------------------------------------------------------------------
# Error / UNMEASURED
# ---------------------------------------------------------------------------

class TestFieldResultUnmeasured:
    """A non-converged solve yields UNMEASURED with reason;  consumers must branch."""

    def test_unmeasured_stores_reason(self):
        result = FieldResult(
            gate_result=GateResult(
                GateStatus.UNMEASURED,
                error_message="laplacian solver did not converge after 1000 iters",
            ),
        )
        assert result.status is GateStatus.UNMEASURED
        assert result.error_message == "laplacian solver did not converge after 1000 iters"
        assert result.field is None
        assert not result.is_usable

    def test_consumer_branches_on_status(self):
        def consume(fr: FieldResult) -> str | None:
            if not fr.is_usable:
                return f"skip: {fr.error_message}"
            return "use_field"

        assert consume(
            FieldResult(
                gate_result=GateResult(
                    GateStatus.UNMEASURED,
                    error_message="not converged",
                ),
            )
        ) == "skip: not converged"

        assert consume(
            FieldResult(
                gate_result=GateResult(GateStatus.CLEAN),
                field=np.ones((5, 5), dtype=np.float32),
            )
        ) == "use_field"

    def test_no_code_path_yields_cost_flat_from_unmeasured(self):
        result = FieldResult(
            gate_result=GateResult(
                GateStatus.UNMEASURED,
                error_message="solver failed",
            ),
        )
        with pytest.raises(FieldNotReadyError):
            result.to_cost_field_input()


# ---------------------------------------------------------------------------
# Property-based: CostField grid alignment (no off-by-one)
# ---------------------------------------------------------------------------

class TestCostFieldAlignment:
    """For any grid shape, a CostField aligns 1:1 with the occupancy grid."""

    @given(
        h=st.integers(min_value=1, max_value=200),
        w=st.integers(min_value=1, max_value=200),
    )
    def test_cost_field_shape_matches(self, h, w):
        grid = np.zeros((h, w), dtype=np.float32)
        cf = CostField(grid=grid, cell_size_mm=1.0, origin_mm=(0.0, 0.0))
        assert cf.height_cells == h
        assert cf.width_cells == w
        assert cf.shape == (h, w)
        assert cf.total_cells == h * w

    @given(
        h=st.integers(min_value=1, max_value=200),
        w=st.integers(min_value=1, max_value=200),
    )
    def test_to_flat_no_off_by_one(self, h, w):
        grid = np.arange(h * w, dtype=np.float32).reshape(h, w)
        cf = CostField(grid=grid, cell_size_mm=1.0, origin_mm=(0.0, 0.0))
        flat = cf.to_flat()
        assert flat.shape == (h * w,)
        expected = np.arange(h * w, dtype=np.float32)
        np.testing.assert_array_equal(flat, expected)

    @given(
        h=st.integers(min_value=1, max_value=100),
        w=st.integers(min_value=1, max_value=100),
    )
    def test_roundtrip_flat_reshape(self, h, w):
        original = np.random.RandomState(42).rand(h, w).astype(np.float32)
        cf = CostField(grid=original, cell_size_mm=0.5, origin_mm=(0.0, 0.0))
        flat = cf.to_flat()
        restored = flat.reshape(h, w)
        np.testing.assert_array_equal(restored, original)


# ---------------------------------------------------------------------------
# FieldGate extension point
# ---------------------------------------------------------------------------

class TestFieldGateExtensionPoint:
    """FieldGate is an abstract base for U5 — concrete subclasses override compute_field."""

    def test_field_gate_check_delegates_to_compute_field(self):
        class StubFieldGate(FieldGate):
            name = "stub"

            def compute_field(self, state):
                from temper_placer.placer.cp_sat.gates import BoardState

                return FieldResult(
                    gate_result=GateResult(GateStatus.CLEAN),
                    field=np.ones((3, 3), dtype=np.float32),
                )

        gate = StubFieldGate()
        from temper_placer.placer.cp_sat.gates import BoardState

        result = gate.check(BoardState())
        assert result.status is GateStatus.CLEAN
        assert len(result.violations) == 0

    def test_field_gate_default_to_delta_returns_none(self):
        gate = FieldGate()
        assert gate.to_delta(Violation(type=ViolationType.THERMAL)) is None

    def test_field_gate_default_compute_field_raises(self):
        gate = FieldGate()
        from temper_placer.placer.cp_sat.gates import BoardState

        with pytest.raises(NotImplementedError):
            gate.compute_field(BoardState())


# ---------------------------------------------------------------------------
# CostFieldInput contract
# ---------------------------------------------------------------------------

class TestCostFieldInput:
    """CostFieldInput bundles flat cost + weight for U8/U9 routing."""

    def test_default_weight_is_one(self):
        cfi = CostFieldInput(cost_flat=np.array([0.0, 1.0, 2.0], dtype=np.float32))
        assert cfi.weight == 1.0

    def test_custom_weight_preserved(self):
        cfi = CostFieldInput(
            cost_flat=np.ones(100, dtype=np.float32),
            weight=3.5,
        )
        assert cfi.weight == 3.5

    def test_frozen(self):
        cfi = CostFieldInput(cost_flat=np.ones(10, dtype=np.float32))
        with pytest.raises(Exception):
            cfi.weight = 2.0  # type: ignore[misc]
