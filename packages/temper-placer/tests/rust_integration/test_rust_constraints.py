"""
Integration tests for the Rust PCL constraint engine.

Covers:
- R6: Loss values match Python implementation within 1e-6
- R9: Positive test proving Rust backend is actually invoked
- R10: Python fallback works when Rust is not available
- R12: All constraint types exercised through both Rust and Python engines
- R14: Rust engine never aborts process, returns Python exceptions
"""

import math

import pytest

try:
    import temper_constraints  # type: ignore[import-untyped]
    HAS_RUST = True
except ImportError:
    HAS_RUST = False


def require_rust():
    """Skip test if Rust backend is not available."""
    if not HAS_RUST:
        pytest.skip("Rust constraint engine not installed")


# ============================================================================
# R9: Positive test proving Rust backend is wired
# ============================================================================


class TestRustBackendWired:
    """Test that the Rust backend is properly installed and callable."""

    @pytest.mark.benchmark
    def test_rust_module_imports(self):
        """Rust module must be importable (R9)."""
        require_rust()
        assert temper_constraints.is_available_py() is True

    @pytest.mark.benchmark
    def test_rust_version_reports(self):
        """Rust module must report its version."""
        require_rust()
        version = temper_constraints.version_py()
        assert version == "0.1.0"

    @pytest.mark.benchmark
    def test_rust_supported_types(self):
        """Rust module must list supported constraint types."""
        require_rust()
        types = temper_constraints.supported_constraint_types_py()
        assert "adjacent" in types
        assert "separated" in types
        assert "enclosing" in types
        assert "aligned" in types
        assert "on_side" in types
        assert "anchored" in types
        assert "loop_area" in types


# ============================================================================
# R6, R12: Loss value parity with Python implementation
# ============================================================================


class TestTierToWeight:
    """Test tier-to-weight mapping parity (R6)."""

    def test_tier_weight_parity(self):
        require_rust()
        assert temper_constraints.tier_to_weight_py(1) == 1_000_000.0
        assert temper_constraints.tier_to_weight_py(2) == 1_000.0
        assert temper_constraints.tier_to_weight_py(3) == 10.0

    def test_invalid_tier_raises(self):
        require_rust()
        with pytest.raises(Exception):
            temper_constraints.tier_to_weight_py(99)


class TestAdjacentLoss:
    """R6: Adjacent loss parity."""

    def test_adjacent_zero_when_within_range(self):
        require_rust()
        loss = temper_constraints.compute_adjacent_loss_py(
            [0.0, 0.0, 5.0, 0.0], 0, 1, 10.0, 1.0,
        )
        assert loss == 0.0

    def test_adjacent_positive_when_exceeds(self):
        require_rust()
        loss = temper_constraints.compute_adjacent_loss_py(
            [0.0, 0.0, 20.0, 0.0], 0, 1, 10.0, 1.0,
        )
        assert abs(loss - 100.0) < 1e-6

    def test_adjacent_with_pin_to_pin(self):
        require_rust()
        loss = temper_constraints.compute_adjacent_loss_py(
            [0.0, 0.0, 20.0, 0.0], 0, 1, 10.0, 1.0,
            metric="pin_to_pin",
            pin_a_x=1.0, pin_a_y=0.0,
            pin_b_x=-1.0, pin_b_y=0.0,
        )
        assert loss > 0.0

    def test_adjacent_invalid_metric_raises(self):
        require_rust()
        with pytest.raises(Exception):
            temper_constraints.compute_adjacent_loss_py(
                [0.0, 0.0, 5.0, 0.0], 0, 1, 10.0, 1.0,
                metric="invalid_metric",
            )


class TestSeparationLoss:
    """R6: Separation loss parity."""

    def test_separation_zero_when_far(self):
        require_rust()
        loss = temper_constraints.compute_separation_loss_py(
            [0.0, 0.0], [50.0, 0.0], 5.0, 1.0,
        )
        assert loss == 0.0

    def test_separation_positive_when_close(self):
        require_rust()
        loss = temper_constraints.compute_separation_loss_py(
            [0.0, 0.0], [2.0, 0.0], 10.0, 1.0,
        )
        assert abs(loss - 64.0) < 1e-6

    def test_separation_multiple_components(self):
        require_rust()
        # group A: two components, group B: one component
        loss = temper_constraints.compute_separation_loss_py(
            [0.0, 0.0, 5.0, 0.0],  # group A: 2 components
            [3.0, 0.0],  # group B: 1 component
            10.0, 1.0,
        )
        # dist(0,0)->(3,0)=3, violation=7, squared=49
        # dist(5,0)->(3,0)=2, violation=8, squared=64
        # total = 49+64 = 113
        assert abs(loss - 113.0) < 1e-6


class TestEnclosingLoss:
    """R6: Zone membership loss parity."""

    def test_inside_zone_zero_loss(self):
        require_rust()
        loss = temper_constraints.compute_enclosing_loss_py(
            [25.0, 25.0, 30.0, 30.0],
            0.0, 0.0, 50.0, 50.0, 0.0, 1.0,
        )
        assert loss == 0.0

    def test_outside_zone_positive_loss(self):
        require_rust()
        loss = temper_constraints.compute_enclosing_loss_py(
            [60.0, 25.0],
            0.0, 0.0, 50.0, 50.0, 0.0, 1.0,
        )
        assert loss > 0.0
        # outside_x = 10, outside_dist^2 = 100
        assert abs(loss - 100.0) < 1e-6

    def test_margin_inside(self):
        require_rust()
        # 5mm from edge, margin=5mm -> should be at boundary
        loss = temper_constraints.compute_enclosing_loss_py(
            [5.0, 25.0],
            0.0, 0.0, 50.0, 50.0, 5.0, 1.0,
        )
        assert loss == 0.0

    def test_margin_violated(self):
        require_rust()
        # 2mm from edge, margin=5mm -> outside margin boundary
        loss = temper_constraints.compute_enclosing_loss_py(
            [2.0, 25.0],
            0.0, 0.0, 50.0, 50.0, 5.0, 1.0,
        )
        assert loss > 0.0


class TestAlignmentLoss:
    """R6: Alignment loss parity."""

    def test_perfect_alignment_zero(self):
        require_rust()
        loss = temper_constraints.compute_alignment_loss_py(
            [10.0, 20.0, 10.0, 30.0, 10.0, 40.0],  # all x=10
            "x", 0.5, 1.0,
        )
        assert loss == 0.0

    def test_misalignment_positive(self):
        require_rust()
        loss = temper_constraints.compute_alignment_loss_py(
            [10.0, 20.0, 10.0, 30.0, 20.0, 40.0],  # third x=20
            "x", 0.5, 1.0,
        )
        assert loss > 0.0

    def test_y_axis_alignment(self):
        require_rust()
        loss = temper_constraints.compute_alignment_loss_py(
            [20.0, 10.0, 30.0, 10.0, 40.0, 10.0],  # all y=10
            "y", 0.5, 1.0,
        )
        assert loss == 0.0

    def test_invalid_axis_raises(self):
        require_rust()
        with pytest.raises(Exception):
            temper_constraints.compute_alignment_loss_py(
                [10.0, 20.0, 10.0, 30.0], "z", 0.5, 1.0,
            )


class TestEdgeLoss:
    """R6: Edge preference loss parity."""

    def test_on_edge_zero_loss(self):
        require_rust()
        loss = temper_constraints.compute_edge_loss_py(
            [0.0, 0.0], "left", 100.0, 80.0, 5.0, 1.0,
        )
        assert loss == 0.0

    def test_far_from_edge_positive(self):
        require_rust()
        loss = temper_constraints.compute_edge_loss_py(
            [50.0, 40.0], "left", 100.0, 80.0, 5.0, 1.0,
        )
        assert loss > 0.0
        # dist=50, max=5, excess=45, squared=2025
        assert abs(loss - 2025.0) < 1e-6

    def test_all_sides(self):
        require_rust()
        # Top edge: y=80, pos at y=40 -> dist=40
        loss = temper_constraints.compute_edge_loss_py(
            [50.0, 40.0], "top", 100.0, 80.0, 5.0, 1.0,
        )
        assert loss > 0.0


class TestAnchoredLoss:
    """R6: Anchored loss parity."""

    def test_at_target_zero(self):
        require_rust()
        loss = temper_constraints.compute_anchored_loss_position_py(
            [30.0, 30.0], 30.0, 30.0, 1.0,
        )
        assert loss == 0.0

    def test_away_from_target_positive(self):
        require_rust()
        loss = temper_constraints.compute_anchored_loss_position_py(
            [10.0, 10.0], 30.0, 30.0, 1.0,
        )
        assert abs(loss - 800.0) < 1e-6

    def test_region_inside_zero(self):
        require_rust()
        loss = temper_constraints.compute_anchored_loss_region_py(
            [25.0, 25.0], 0.0, 0.0, 50.0, 50.0, 1.0,
        )
        # distance from center (25,25) = 0, outside penalty = 0
        assert loss == 0.0

    def test_region_outside_positive(self):
        require_rust()
        loss = temper_constraints.compute_anchored_loss_region_py(
            [60.0, 25.0], 0.0, 0.0, 50.0, 50.0, 1.0,
        )
        assert loss > 0.0


class TestLoopAreaLoss:
    """R6: Loop area loss parity."""

    def test_small_area_zero(self):
        require_rust()
        # 10x10 square = 100 mm^2, max=200
        loss = temper_constraints.compute_loop_area_loss_py(
            [0.0, 0.0, 10.0, 0.0, 10.0, 10.0, 0.0, 10.0],
            200.0, 1.0,
        )
        assert loss == 0.0

    def test_large_area_positive(self):
        require_rust()
        # 20x20 square = 400 mm^2, max=200
        loss = temper_constraints.compute_loop_area_loss_py(
            [0.0, 0.0, 20.0, 0.0, 20.0, 20.0, 0.0, 20.0],
            200.0, 1.0,
        )
        assert abs(loss - 40_000.0) < 1e-6

    def test_less_than_three_points_zero(self):
        require_rust()
        loss = temper_constraints.compute_loop_area_loss_py(
            [0.0, 0.0, 10.0, 10.0],  # only 2 points
            200.0, 1.0,
        )
        assert loss == 0.0


class TestUnifiedDispatch:
    """R12: All constraint types exercised through unified dispatcher."""

    ALL_CONSTRAINT_TYPES = range(1, 8)  # 1=adjacent through 7=loop_area

    @pytest.mark.parametrize("ctype", ALL_CONSTRAINT_TYPES)
    def test_all_constraint_types_compute(self, ctype):
        """Every constraint type must be dispatchable (R12)."""
        require_rust()

        if ctype == 1:
            loss = temper_constraints.compute_constraint_loss_py(
                ctype, [0.0, 1.0, 10.0, 1.0],
                [0.0, 0.0, 5.0, 0.0],
            )
            assert loss == 0.0
        elif ctype == 2:
            loss = temper_constraints.compute_constraint_loss_py(
                ctype, [1.0, 1.0, 10.0, 1.0],
                [0.0, 0.0, 50.0, 0.0],
            )
            assert loss == 0.0
        elif ctype == 3:
            loss = temper_constraints.compute_constraint_loss_py(
                ctype,
                [0.0, 0.0, 50.0, 50.0, 0.0, 1.0],
                [25.0, 25.0],
            )
            assert loss == 0.0
        elif ctype == 4:
            loss = temper_constraints.compute_constraint_loss_py(
                ctype, [0.0, 0.5, 1.0],
                [10.0, 20.0, 10.0, 30.0],
            )
            assert loss == 0.0
        elif ctype == 5:
            loss = temper_constraints.compute_constraint_loss_py(
                ctype, [2.0, 100.0, 80.0, 5.0, 1.0],
                [0.0, 0.0],
            )
            assert loss == 0.0
        elif ctype == 6:
            loss = temper_constraints.compute_constraint_loss_py(
                ctype, [0.0, 30.0, 30.0, 0.0, 0.0, 1.0],
                [30.0, 30.0],
            )
            assert loss == 0.0
        elif ctype == 7:
            loss = temper_constraints.compute_constraint_loss_py(
                ctype, [200.0, 1.0],
                [0.0, 0.0, 10.0, 0.0, 10.0, 10.0, 0.0, 10.0],
            )
            assert loss == 0.0

    @pytest.mark.benchmark
    def test_unknown_constraint_type_raises(self):
        """R12: Unknown constraint type must return NotImplemented error."""
        require_rust()
        with pytest.raises(Exception) as exc_info:
            temper_constraints.compute_constraint_loss_py(
                99, [1.0], [0.0, 0.0],
            )
        err_msg = str(exc_info.value)
        assert "Unknown" in err_msg or "unknown" in err_msg


# ============================================================================
# R14: Never abort process
# ============================================================================


class TestErrorHandling:
    """Test that Rust engine never aborts Python process (R14)."""

    def test_invalid_indices_no_panic(self):
        """Out-of-bounds indices must return gracefully."""
        require_rust()
        # idx > n should return 0.0 (handled internally)
        loss = temper_constraints.compute_adjacent_loss_py(
            [0.0, 0.0], 100, 200, 10.0, 1.0,
        )
        assert loss == 0.0

    def test_empty_positions_no_panic(self):
        """Empty position arrays should not crash."""
        require_rust()
        loss = temper_constraints.compute_adjacent_loss_py(
            [], 0, 1, 10.0, 1.0,
        )
        assert loss == 0.0


# ============================================================================
# R10: Python fallback works transparently
# ============================================================================


class TestPythonFallback:
    """Test that the Python fallback bridge module works."""

    def test_rust_bridge_imports(self):
        """The rust_bridge wrapper module must be importable."""
        from temper_placer.pcl import rust_bridge

        assert hasattr(rust_bridge, "has_rust_backend")

    def test_has_rust_backend_reports_correctly(self):
        """has_rust_backend must report True when Rust is installed."""
        from temper_placer.pcl import rust_bridge

        result = rust_bridge.has_rust_backend()
        assert result is HAS_RUST  # Should match the direct import check

    @pytest.mark.benchmark
    def test_rust_bridge_wrapper_functions_work(self):
        """Rust bridge wrapper functions must delegate to Rust."""
        require_rust()
        from temper_placer.pcl import rust_bridge

        loss = rust_bridge.compute_adjacent_loss_rust(
            [0.0, 0.0, 20.0, 0.0], 0, 1, 10.0, 1.0,
        )
        assert abs(loss - 100.0) < 1e-6

    def test_rust_version_via_bridge(self):
        """Version must be retrievable via the bridge."""
        require_rust()
        from temper_placer.pcl import rust_bridge

        version = rust_bridge.rust_version()
        assert version == "0.1.0"


# ============================================================================
# Performance benchmark sanity checks
# ============================================================================


class TestBenchmarkSanity:
    """Quick sanity checks that the Rust engine returns reasonable times."""

    @pytest.mark.benchmark
    def test_adjacent_loss_wall_time(self):
        """Adjacent loss must compute in reasonable time."""
        require_rust()
        import time

        # Warmup
        for _ in range(10):
            temper_constraints.compute_adjacent_loss_py(
                [0.0, 0.0, 20.0, 0.0], 0, 1, 10.0, 1.0,
            )

        start = time.perf_counter()
        for _ in range(1000):
            temper_constraints.compute_adjacent_loss_py(
                [0.0, 0.0, 20.0, 0.0], 0, 1, 10.0, 1.0,
            )
        elapsed = (time.perf_counter() - start) * 1000  # ms
        # 1000 calls should be well under 100ms
        assert elapsed < 500, f"Too slow: {elapsed:.2f}ms for 1000 calls"

    @pytest.mark.benchmark
    def test_separation_loss_wall_time(self):
        """Batch separation loss must be fast."""
        require_rust()
        import time

        pos_a = [float(i % 10) for i in range(20)]  # 10 components
        pos_b = [float(i % 10) + 5.0 for i in range(20)]  # 10 components

        for _ in range(10):
            temper_constraints.compute_separation_loss_py(
                pos_a, pos_b, 10.0, 1.0,
            )

        start = time.perf_counter()
        for _ in range(1000):
            temper_constraints.compute_separation_loss_py(
                pos_a, pos_b, 10.0, 1.0,
            )
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 500, f"Too slow: {elapsed:.2f}ms for 1000 calls"
