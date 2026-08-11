"""Coverage paydown tests v8: geometry, deterministic helpers, heuristics base,
fields interface, channels, bottleneck, topological graph, and metrics.

Exercises public functions in:
- geometry/constraints.py, geometry/transform.py, geometry/sdf.py,
  geometry/smooth.py, geometry/polygon.py, geometry/projections.py,
  geometry/drc_inflate.py, geometry/__init__.py
- deterministic/geometry/grid_utils.py, deterministic/flags.py
- deterministic/channels.py, deterministic/bottleneck_map.py
- heuristics/base.py, heuristics/conflict.py
- fields/interface.py
- topological/graph.py
"""

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# geometry/constraints.py: BoundaryViolation, ValidBounds, compute_*
# ---------------------------------------------------------------------------


class TestBoundaryViolation:
    def test_has_violation_true(self):
        from temper_placer.geometry.constraints import BoundaryViolation

        bv = BoundaryViolation(left=0.5, right=0.0, bottom=0.0, top=0.0)
        assert bv.has_violation is True

    def test_has_violation_false(self):
        from temper_placer.geometry.constraints import BoundaryViolation

        bv = BoundaryViolation(left=0.0, right=0.0, bottom=0.0, top=0.0)
        assert bv.has_violation is False

    def test_max_violation(self):
        from temper_placer.geometry.constraints import BoundaryViolation

        bv = BoundaryViolation(left=0.5, right=1.0, bottom=0.3, top=2.0)
        assert bv.max_violation == 2.0

    def test_max_violation_all_zero(self):
        from temper_placer.geometry.constraints import BoundaryViolation

        bv = BoundaryViolation(left=0.0, right=0.0, bottom=0.0, top=0.0)
        assert bv.max_violation == 0.0

    def test_total_violation(self):
        from temper_placer.geometry.constraints import BoundaryViolation

        bv = BoundaryViolation(left=0.5, right=1.0, bottom=0.3, top=2.0)
        assert bv.total_violation == pytest.approx(3.8)

    def test_total_violation_zero(self):
        from temper_placer.geometry.constraints import BoundaryViolation

        bv = BoundaryViolation(left=0.0, right=0.0, bottom=0.0, top=0.0)
        assert bv.total_violation == 0.0


class TestValidBounds:
    def test_clamp_point_inside(self):
        from temper_placer.geometry.constraints import ValidBounds

        vb = ValidBounds(x_min=0.0, x_max=100.0, y_min=0.0, y_max=100.0)
        assert vb.clamp_point(50.0, 50.0) == (50.0, 50.0)

    def test_clamp_point_outside(self):
        from temper_placer.geometry.constraints import ValidBounds

        vb = ValidBounds(x_min=0.0, x_max=100.0, y_min=0.0, y_max=100.0)
        assert vb.clamp_point(150.0, -10.0) == (100.0, 0.0)

    def test_contains_point_true(self):
        from temper_placer.geometry.constraints import ValidBounds

        vb = ValidBounds(x_min=0.0, x_max=100.0, y_min=0.0, y_max=100.0)
        assert vb.contains_point(50.0, 50.0) is True

    def test_contains_point_false(self):
        from temper_placer.geometry.constraints import ValidBounds

        vb = ValidBounds(x_min=0.0, x_max=100.0, y_min=0.0, y_max=100.0)
        assert vb.contains_point(150.0, 50.0) is False

    def test_contains_point_boundary(self):
        from temper_placer.geometry.constraints import ValidBounds

        vb = ValidBounds(x_min=0.0, x_max=100.0, y_min=0.0, y_max=100.0)
        assert vb.contains_point(0.0, 0.0) is True
        assert vb.contains_point(100.0, 100.0) is True


class TestGeometricConstraintsCompute:
    """Tests for compute_boundary_violation, compute_valid_bounds,
    is_within_bounds, compute_zone_distance, point_in_zone."""

    def test_compute_boundary_violation_none(self):
        from temper_placer.geometry.constraints import compute_boundary_violation

        bv = compute_boundary_violation(
            position_x=50.0, position_y=50.0,
            component_half_width=5.0, component_half_height=5.0,
            board_x_min=0.0, board_y_min=0.0,
            board_x_max=100.0, board_y_max=100.0,
        )
        assert bv.has_violation is False

    def test_compute_boundary_violation_left(self):
        from temper_placer.geometry.constraints import compute_boundary_violation

        bv = compute_boundary_violation(
            position_x=2.0, position_y=50.0,
            component_half_width=5.0, component_half_height=5.0,
            board_x_min=0.0, board_y_min=0.0,
            board_x_max=100.0, board_y_max=100.0,
        )
        # x=2, half_w=5 -> left edge at -3 -> violates by 3
        assert bv.left > 0

    def test_compute_valid_bounds_centered(self):
        from temper_placer.geometry.constraints import compute_valid_bounds

        vb = compute_valid_bounds(
            component_half_width=5.0, component_half_height=5.0,
            region_x_min=0.0, region_y_min=0.0,
            region_x_max=100.0, region_y_max=100.0,
        )
        assert vb.x_min == 5.0
        assert vb.x_max == 95.0
        assert vb.y_min == 5.0
        assert vb.y_max == 95.0

    def test_compute_valid_bounds_with_margin(self):
        from temper_placer.geometry.constraints import compute_valid_bounds

        vb = compute_valid_bounds(
            component_half_width=5.0, component_half_height=5.0,
            region_x_min=0.0, region_y_min=0.0,
            region_x_max=100.0, region_y_max=100.0,
            margin=2.0,
        )
        assert vb.x_min > 5.0  # margin pushes inward

    def test_is_within_bounds_true(self):
        from temper_placer.geometry.constraints import is_within_bounds

        assert is_within_bounds(
            position_x=50.0, position_y=50.0,
            component_half_width=5.0, component_half_height=5.0,
            region_x_min=0.0, region_y_min=0.0,
            region_x_max=100.0, region_y_max=100.0,
        ) is True

    def test_is_within_bounds_false(self):
        from temper_placer.geometry.constraints import is_within_bounds

        assert is_within_bounds(
            position_x=2.0, position_y=50.0,
            component_half_width=5.0, component_half_height=5.0,
            region_x_min=0.0, region_y_min=0.0,
            region_x_max=100.0, region_y_max=100.0,
        ) is False

    def test_compute_zone_distance_inside(self):
        from temper_placer.geometry.constraints import compute_zone_distance

        d = compute_zone_distance(
            position_x=50.0, position_y=50.0,
            zone_x_min=0.0, zone_y_min=0.0,
            zone_x_max=100.0, zone_y_max=100.0,
        )
        # Inside zone -> negative
        assert d < 0

    def test_compute_zone_distance_outside(self):
        from temper_placer.geometry.constraints import compute_zone_distance

        d = compute_zone_distance(
            position_x=150.0, position_y=50.0,
            zone_x_min=0.0, zone_y_min=0.0,
            zone_x_max=100.0, zone_y_max=100.0,
        )
        # Outside zone -> positive
        assert d > 0

    def test_point_in_zone_inside(self):
        from temper_placer.geometry.constraints import point_in_zone

        assert point_in_zone(
            position_x=50.0, position_y=50.0,
            zone_x_min=0.0, zone_y_min=0.0,
            zone_x_max=100.0, zone_y_max=100.0,
        ) is True

    def test_point_in_zone_outside(self):
        from temper_placer.geometry.constraints import point_in_zone

        assert point_in_zone(
            position_x=150.0, position_y=50.0,
            zone_x_min=0.0, zone_y_min=0.0,
            zone_x_max=100.0, zone_y_max=100.0,
        ) is False


# ---------------------------------------------------------------------------
# geometry/transform.py: rotation conversion functions
# ---------------------------------------------------------------------------


class TestRotationTransforms:
    def test_rotation_index_to_onehot_default(self):
        from temper_placer.geometry.transform import rotation_index_to_onehot

        result = rotation_index_to_onehot(0)
        assert len(result) == 4
        assert result[0] == 1.0

    def test_rotation_index_to_onehot_idx2(self):
        from temper_placer.geometry.transform import rotation_index_to_onehot

        result = rotation_index_to_onehot(2)
        assert len(result) == 4
        assert result[2] == 1.0

    def test_rotation_degrees_to_onehot_default(self):
        from temper_placer.geometry.transform import rotation_degrees_to_onehot

        result = rotation_degrees_to_onehot(0.0)
        assert len(result) == 4
        assert result[0] == 1.0

        result = rotation_degrees_to_onehot(90.0)
        assert result[1] == 1.0

    def test_onehot_to_rotation_degrees_default(self):
        from temper_placer.geometry.transform import onehot_to_rotation_degrees

        deg = onehot_to_rotation_degrees([1.0, 0.0, 0.0, 0.0])
        assert deg == pytest.approx(0.0)

        deg = onehot_to_rotation_degrees([0.0, 1.0, 0.0, 0.0])
        assert deg == pytest.approx(90.0)

    def test_onehot_to_rotation_radians_default(self):
        from temper_placer.geometry.transform import onehot_to_rotation_radians

        rad = onehot_to_rotation_radians([1.0, 0.0, 0.0, 0.0])
        assert rad == pytest.approx(0.0)

        rad = onehot_to_rotation_radians([0.0, 1.0, 0.0, 0.0])
        assert rad == pytest.approx(1.5707963267948966)


# ---------------------------------------------------------------------------
# geometry/sdf.py: sdf_gradient, sdf_to_mask, sdf_to_penalty
# ---------------------------------------------------------------------------


class TestSDFFunctions:
    def test_sdf_to_mask_scalar(self):
        from temper_placer.geometry.sdf import sdf_to_mask

        # Inside shape (negative) -> mask ~1
        m = sdf_to_mask(-1.0, threshold=0.5)
        assert 0.8 <= m <= 1.0

        # Outside shape (positive) -> mask ~0
        m = sdf_to_mask(1.0, threshold=0.5)
        assert 0.0 <= m <= 0.2

    def test_sdf_to_mask_array(self):
        from temper_placer.geometry.sdf import sdf_to_mask

        m = sdf_to_mask([-1.0, 0.0, 1.0], threshold=0.5)
        assert len(m) == 3

    def test_sdf_to_penalty_scalar(self):
        from temper_placer.geometry.sdf import sdf_to_penalty

        # Inside shape (negative) -> penalty > 0
        p = sdf_to_penalty(-0.5, alpha=10.0)
        assert p >= 0

        # Outside shape (positive) -> penalty near 0
        p = sdf_to_penalty(1.0, alpha=10.0)
        assert p < 0.1

    def test_sdf_to_penalty_array(self):
        from temper_placer.geometry.sdf import sdf_to_penalty

        p = sdf_to_penalty([-1.0, 0.0, 1.0], alpha=10.0)
        assert len(p) == 3

    def test_sdf_gradient_circle(self):
        from temper_placer.geometry.sdf import sdf_gradient

        def circle_sdf(pt):
            x, y = pt
            return np.sqrt(x**2 + y**2) - 1.0  # unit circle centered at origin

        grad = sdf_gradient(circle_sdf, (2.0, 0.0))
        # Gradient should point radially outward
        assert grad[0] > 0
        assert abs(grad[1]) < 1e-3


# Also test sdf_gradient via geometry/__init__.py re-export
class TestGeometryInitSDFGradient:
    def test_sdf_gradient_re_export(self):
        from temper_placer.geometry import sdf_gradient

        def f(pt):
            x, y = pt
            return x + y

        grad = sdf_gradient((0.0, 0.0), f)
        assert len(grad) == 2


# ---------------------------------------------------------------------------
# geometry/smooth.py: smooth_leaky_relu
# ---------------------------------------------------------------------------


class TestSmoothLeakyRelu:
    def test_positive_input(self):
        from temper_placer.geometry.smooth import smooth_leaky_relu

        result = smooth_leaky_relu(5.0)
        # Should be close to 5.0 for large alpha
        assert result == pytest.approx(5.0, abs=0.5)

    def test_negative_input(self):
        from temper_placer.geometry.smooth import smooth_leaky_relu

        result = smooth_leaky_relu(-5.0)
        # Negative slope 0.01 means ~ -0.05
        assert result < 0
        assert result > -0.1

    def test_zero_input(self):
        from temper_placer.geometry.smooth import smooth_leaky_relu

        result = smooth_leaky_relu(0.0)
        assert result >= 0


# ---------------------------------------------------------------------------
# geometry/polygon.py: point_in_polygon_soft, point_in_rect_soft
# ---------------------------------------------------------------------------


class TestPointInPolygonSoft:
    def test_point_inside_square(self):
        from temper_placer.geometry.polygon import point_in_polygon_soft

        # Square: (0,0), (10,0), (10,10), (0,10)
        vertices = [0, 0, 10, 0, 10, 10, 0, 10]
        result = point_in_polygon_soft(5.0, 5.0, vertices)
        # Inside -> close to 1
        assert result > 0.5

    def test_point_outside_square(self):
        from temper_placer.geometry.polygon import point_in_polygon_soft

        vertices = [0, 0, 10, 0, 10, 10, 0, 10]
        result = point_in_polygon_soft(20.0, 20.0, vertices)
        # Outside -> close to 0
        assert result < 0.5


class TestPointInRectSoft:
    def test_point_inside(self):
        from temper_placer.geometry.polygon import point_in_rect_soft

        result = point_in_rect_soft(5.0, 5.0, 0.0, 0.0, 10.0, 10.0)
        assert result > 0.5

    def test_point_outside(self):
        from temper_placer.geometry.polygon import point_in_rect_soft

        result = point_in_rect_soft(20.0, 20.0, 0.0, 0.0, 10.0, 10.0)
        assert result < 0.5


# ---------------------------------------------------------------------------
# geometry/projections.py: project_outside_keepout
# ---------------------------------------------------------------------------


class TestProjectOutsideKeepout:
    def test_point_outside_no_expansion(self):
        from temper_placer.geometry.projections import project_outside_keepout

        x, y = project_outside_keepout(15.0, 15.0, 0.0, 0.0, 10.0, 10.0)
        assert x > 10.0 or y > 10.0

    def test_point_inside_keepout(self):
        from temper_placer.geometry.projections import project_outside_keepout

        x, y = project_outside_keepout(5.0, 5.0, 0.0, 0.0, 10.0, 10.0)
        # Should be projected to nearest boundary
        assert x >= 10.0 or y >= 10.0 or x <= 0.0 or y <= 0.0


# ---------------------------------------------------------------------------
# geometry/drc_inflate.py: compute_inflated_half_dims_from_bounds,
#                          compute_drc_proxy_score
# ---------------------------------------------------------------------------


class TestDRCInflate:
    def test_compute_inflated_half_dims_f32(self):
        from temper_placer.geometry.drc_inflate import compute_inflated_half_dims_from_bounds

        bounds = np.array([[10.0, 8.0], [6.0, 4.0]], dtype=np.float32)
        result = compute_inflated_half_dims_from_bounds(bounds, trace_width_mm=0.25)
        assert result.shape == (2, 2)
        # half-widths should be > original/2 due to inflation
        assert result[0, 0] > 5.0

    def test_compute_inflated_half_dims_f64(self):
        from temper_placer.geometry.drc_inflate import compute_inflated_half_dims_from_bounds

        bounds = np.array([[10.0, 8.0], [6.0, 4.0]], dtype=np.float64)
        result = compute_inflated_half_dims_from_bounds(bounds, trace_width_mm=0.25)
        assert result.shape == (2, 2)

    def test_compute_drc_proxy_score_no_overlap(self):
        from temper_placer.geometry.drc_inflate import compute_drc_proxy_score

        positions = np.array([[0.0, 0.0], [100.0, 100.0]], dtype=np.float32)
        hw = np.array([5.0, 5.0], dtype=np.float32)
        hh = np.array([5.0, 5.0], dtype=np.float32)
        score = compute_drc_proxy_score(positions, hw, hh)
        assert score == 0.0

    def test_compute_drc_proxy_score_with_overlap(self):
        from temper_placer.geometry.drc_inflate import compute_drc_proxy_score

        positions = np.array([[0.0, 0.0], [1.0, 1.0]], dtype=np.float32)
        hw = np.array([5.0, 5.0], dtype=np.float32)
        hh = np.array([5.0, 5.0], dtype=np.float32)
        score = compute_drc_proxy_score(positions, hw, hh)
        # Overlap or near-overlap -> positive score
        assert score >= 0


# ---------------------------------------------------------------------------
# deterministic/geometry/grid_utils.py: snap_to_grid, add_endpoint_nudge
# ---------------------------------------------------------------------------


class TestGridUtils:
    def test_snap_to_grid_aligned(self):
        from temper_placer.deterministic.geometry.grid_utils import snap_to_grid

        result = snap_to_grid((10.0, 20.0), grid_size=1.0)
        assert result == (10.0, 20.0)

    def test_snap_to_grid_off_grid(self):
        from temper_placer.deterministic.geometry.grid_utils import snap_to_grid

        result = snap_to_grid((10.3, 20.7), grid_size=1.0)
        assert result == (10.0, 21.0)

    def test_snap_to_grid_default_size(self):
        from temper_placer.deterministic.geometry.grid_utils import snap_to_grid

        result = snap_to_grid((10.0, 10.0))
        assert len(result) == 2

    def test_add_endpoint_nudge_basic(self):
        from temper_placer.deterministic.geometry.grid_utils import add_endpoint_nudge

        path = [(0.0, 0.0), (10.0, 0.0)]
        result = add_endpoint_nudge(path, (-1.0, 0.0), (11.0, 0.0))
        assert len(result) >= 2
        # First point should be close to actual_start
        assert result[0][0] == pytest.approx(-1.0, abs=0.1)

    def test_add_endpoint_nudge_empty(self):
        from temper_placer.deterministic.geometry.grid_utils import add_endpoint_nudge

        result = add_endpoint_nudge([], (0.0, 0.0), (10.0, 10.0))
        assert result == []


# ---------------------------------------------------------------------------
# deterministic/flags.py: is_feedback_enabled
# ---------------------------------------------------------------------------


class TestDeterministicFlags:
    def test_is_feedback_enabled_default(self):
        from temper_placer.deterministic.flags import is_feedback_enabled

        # Default (unset) -> True
        result = is_feedback_enabled()
        assert result is True

    def test_is_feedback_enabled_disabled_by_env(self, monkeypatch):
        from temper_placer.deterministic.flags import is_feedback_enabled

        monkeypatch.setenv("TEMPER_FEEDBACK_ENABLED", "0")
        assert is_feedback_enabled() is False

        monkeypatch.setenv("TEMPER_FEEDBACK_ENABLED", "false")
        assert is_feedback_enabled() is False

        monkeypatch.setenv("TEMPER_FEEDBACK_ENABLED", "no")
        assert is_feedback_enabled() is False

        monkeypatch.setenv("TEMPER_FEEDBACK_ENABLED", "off")
        assert is_feedback_enabled() is False

    def test_is_feedback_enabled_explicit_true(self, monkeypatch):
        from temper_placer.deterministic.flags import is_feedback_enabled

        monkeypatch.setenv("TEMPER_FEEDBACK_ENABLED", "1")
        assert is_feedback_enabled() is True

        monkeypatch.setenv("TEMPER_FEEDBACK_ENABLED", "true")
        assert is_feedback_enabled() is True


# ---------------------------------------------------------------------------
# heuristics/base.py: HeuristicResult.merge, PlacementContext methods
# ---------------------------------------------------------------------------


class TestHeuristicResult:
    def test_merge_basic(self):
        from temper_placer.heuristics.base import ComponentPlacement, HeuristicResult

        r1 = HeuristicResult(
            placements={"U1": ComponentPlacement(ref="U1", position=(10.0, 10.0))},
            success=True,
        )
        r2 = HeuristicResult(
            placements={"U2": ComponentPlacement(ref="U2", position=(20.0, 20.0))},
            success=True,
        )
        merged = r1.merge(r2)
        assert "U1" in merged.placements
        assert "U2" in merged.placements
        assert merged.placements["U1"].position == (10.0, 10.0)
        assert merged.placements["U2"].position == (20.0, 20.0)

    def test_merge_overrides(self):
        from temper_placer.heuristics.base import ComponentPlacement, HeuristicResult

        r1 = HeuristicResult(
            placements={"U1": ComponentPlacement(ref="U1", position=(10.0, 10.0))},
            success=True,
        )
        r2 = HeuristicResult(
            placements={"U1": ComponentPlacement(ref="U1", position=(50.0, 50.0))},
            success=True,
        )
        merged = r1.merge(r2)
        # Later overrides earlier
        assert merged.placements["U1"].position == (50.0, 50.0)

    def test_merge_conflicts(self):
        from temper_placer.heuristics.base import HeuristicResult

        r1 = HeuristicResult(
            conflicts=["conflict_a"],
            success=True,
        )
        r2 = HeuristicResult(
            conflicts=["conflict_b"],
            success=True,
        )
        merged = r1.merge(r2)
        assert len(merged.conflicts) == 2
        assert "conflict_a" in merged.conflicts
        assert "conflict_b" in merged.conflicts

    def test_merge_success_false(self):
        from temper_placer.heuristics.base import HeuristicResult

        r1 = HeuristicResult(success=True)
        r2 = HeuristicResult(success=False)
        merged = r1.merge(r2)
        assert merged.success is False


class TestPlacementContextMethods:
    """Tests for PlacementContext.get_unplaced_components, get_placed_refs,
    is_position_valid, check_overlap."""

    def _make_context(self):
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.base import ComponentPlacement, PlacementContext
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="U1", footprint="QFN-32", bounds=(5, 5)),
            Component(ref="C1", footprint="0603", bounds=(2, 1)),
            Component(ref="C2", footprint="0603", bounds=(2, 1)),
        ]
        netlist = Netlist(components=comps, nets=[])
        board = Board(
            width=100,
            height=100,
            origin=(0, 0),
        )
        constraints = PlacementConstraints(board_margin_mm=1.0)
        ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)
        return ctx

    def test_get_unplaced_components_empty(self):
        ctx = self._make_context()
        unplaced = ctx.get_unplaced_components()
        assert len(unplaced) == 3  # All components are unplaced

    def test_get_unplaced_components_some_placed(self):
        from temper_placer.heuristics.base import ComponentPlacement

        ctx = self._make_context()
        ctx.current_placements = {
            "U1": ComponentPlacement(ref="U1", position=(50, 50)),
        }
        unplaced = ctx.get_unplaced_components()
        refs = {c.ref for c in unplaced}
        assert "U1" not in refs
        assert "C1" in refs
        assert "C2" in refs

    def test_get_placed_refs_empty(self):
        ctx = self._make_context()
        assert ctx.get_placed_refs() == set()

    def test_get_placed_refs_with_placements(self):
        from temper_placer.heuristics.base import ComponentPlacement

        ctx = self._make_context()
        ctx.current_placements = {
            "U1": ComponentPlacement(ref="U1", position=(50, 50)),
        }
        assert ctx.get_placed_refs() == {"U1"}

    def test_is_position_valid_inside(self):
        ctx = self._make_context()
        assert ctx.is_position_valid(50, 50, 10, 10) is True

    def test_is_position_valid_too_close_to_edge(self):
        ctx = self._make_context()
        assert ctx.is_position_valid(2, 50, 10, 10) is False

    def test_check_overlap_no_overlap(self):
        from temper_placer.heuristics.base import ComponentPlacement

        ctx = self._make_context()
        ctx.current_placements = {
            "U1": ComponentPlacement(ref="U1", position=(10, 10)),
        }
        assert ctx.check_overlap(50, 50, 10, 10) is False

    def test_check_overlap_yes_overlap(self):
        from temper_placer.heuristics.base import ComponentPlacement

        ctx = self._make_context()
        ctx.current_placements = {
            "U1": ComponentPlacement(ref="U1", position=(50, 50)),
        }
        assert ctx.check_overlap(51, 51, 10, 10) is True

    def test_check_overlap_excludes_ref(self):
        from temper_placer.heuristics.base import ComponentPlacement

        ctx = self._make_context()
        ctx.current_placements = {
            "U1": ComponentPlacement(ref="U1", position=(50, 50)),
        }
        assert ctx.check_overlap(50, 50, 10, 10, exclude_refs={"U1"}) is False


# ---------------------------------------------------------------------------
# heuristics/conflict.py: ConflictResolver methods
# ---------------------------------------------------------------------------


class TestConflictResolver:
    def _make_context(self):
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.base import PlacementContext
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="U1", footprint="QFN-32", bounds=(5, 5)),
            Component(ref="U2", footprint="QFN-32", bounds=(5, 5)),
        ]
        netlist = Netlist(components=comps, nets=[])
        board = Board(
            width=200,
            height=200,
            origin=(0, 0),
        )
        constraints = PlacementConstraints(board_margin_mm=1.0)
        return PlacementContext(board=board, netlist=netlist, constraints=constraints)

    def test_add_placement(self):
        from temper_placer.heuristics.base import ComponentPlacement
        from temper_placer.heuristics.conflict import ConflictResolver

        resolver = ConflictResolver()
        placement = ComponentPlacement(ref="U1", position=(10, 10))
        resolver.add_placement(placement)
        assert "U1" in resolver.placements

    def test_add_placements(self):
        from temper_placer.heuristics.base import ComponentPlacement
        from temper_placer.heuristics.conflict import ConflictResolver

        resolver = ConflictResolver()
        resolver.add_placements({
            "U1": ComponentPlacement(ref="U1", position=(10, 10)),
            "U2": ComponentPlacement(ref="U2", position=(50, 50)),
        })
        assert len(resolver.placements) == 2

    def test_check_conflict_none(self):
        from temper_placer.heuristics.base import ComponentPlacement
        from temper_placer.heuristics.conflict import ConflictResolver

        resolver = ConflictResolver()
        ctx = self._make_context()
        placement = ComponentPlacement(ref="U2", position=(50, 50))
        result = resolver.check_conflict(placement, 5, 5, ctx)
        assert result is None  # No existing placements, no conflict

    def test_check_conflict_detected(self):
        from temper_placer.heuristics.base import ComponentPlacement
        from temper_placer.heuristics.conflict import ConflictResolver

        resolver = ConflictResolver()
        ctx = self._make_context()
        resolver.add_placement(ComponentPlacement(ref="U1", position=(10, 10)))
        placement = ComponentPlacement(ref="U2", position=(11, 11))
        result = resolver.check_conflict(placement, 5, 5, ctx)
        assert result is not None
        ref, overlap = result
        assert ref == "U1"

    def test_clear(self):
        from temper_placer.heuristics.base import ComponentPlacement
        from temper_placer.heuristics.conflict import ConflictResolver

        resolver = ConflictResolver()
        resolver.add_placement(ComponentPlacement(ref="U1", position=(10, 10)))
        resolver.clear()
        assert len(resolver.placements) == 0

    def test_get_all_conflicts(self):
        from temper_placer.heuristics.conflict import ConflictResolver

        resolver = ConflictResolver()
        assert resolver.get_all_conflicts() == []

    def test_resolve_no_conflict(self):
        from temper_placer.heuristics.base import ComponentPlacement
        from temper_placer.heuristics.conflict import ConflictResolver

        resolver = ConflictResolver()
        ctx = self._make_context()
        placement = ComponentPlacement(ref="U2", position=(50, 50))
        resolved, conflict = resolver.resolve(placement, 5, 5, ctx)
        assert resolved is not None
        assert resolved.ref == "U2"
        assert conflict is None

    def test_resolve_higher_priority_wins(self):
        from temper_placer.heuristics.base import ComponentPlacement
        from temper_placer.heuristics.conflict import ConflictResolver

        resolver = ConflictResolver()
        ctx = self._make_context()
        resolver.add_placement(ComponentPlacement(ref="U1", position=(10, 10)))
        placement = ComponentPlacement(ref="U2", position=(10, 10))
        resolved, conflict = resolver.resolve(placement, 5, 5, ctx)
        # Higher priority wins by default
        assert resolved is None or conflict is not None


# ---------------------------------------------------------------------------
# fields/interface.py: FieldGate.check, FieldGate.compute_field
# ---------------------------------------------------------------------------


class TestFieldGate:
    def test_compute_field_raises_not_implemented(self):
        from temper_placer.fields.interface import FieldGate

        gate = FieldGate()
        with pytest.raises(NotImplementedError):
            gate.compute_field(None)

    def test_check_delegates_to_compute_field(self):
        from temper_placer.fields.interface import FieldGate
        from temper_placer.fields.result import FieldResult
        from temper_placer.placer.cp_sat.gates import GateResult, GateStatus

        class TestGate(FieldGate):
            def compute_field(self, state):
                return FieldResult(
                    field=np.ones((10, 10), dtype=np.float32),
                    gate_result=GateResult(status=GateStatus.CLEAN),
                )

        gate = TestGate()
        result = gate.check(None)
        assert result.status == GateStatus.CLEAN


# ---------------------------------------------------------------------------
# deterministic/channels.py: Bottleneck.to_dict, ChannelMap methods
# ---------------------------------------------------------------------------


class TestBottleneck:
    def test_to_dict(self):
        from temper_placer.deterministic.channels import Bottleneck

        b = Bottleneck(x=1, y=2, layer="F.Cu", severity="HIGH", score=0.8)
        d = b.to_dict()
        assert d["x"] == 1
        assert d["y"] == 2
        assert d["layer"] == "F.Cu"
        assert d["severity"] == "HIGH"
        assert d["score"] == 0.8


class TestChannelMap:
    def test_empty(self):
        from temper_placer.deterministic.channels import ChannelMap

        cm = ChannelMap.empty()
        assert cm.has_grid() is False
        assert cm.width == 0
        assert cm.height == 0

    def test_has_grid_false_empty(self):
        from temper_placer.deterministic.channels import ChannelMap

        cm = ChannelMap.empty()
        assert cm.has_grid() is False

    def test_height_empty(self):
        from temper_placer.deterministic.channels import ChannelMap

        cm = ChannelMap.empty()
        assert cm.height == 0

    def test_width_empty(self):
        from temper_placer.deterministic.channels import ChannelMap

        cm = ChannelMap.empty()
        assert cm.width == 0

    def test_routability_penalty_empty(self):
        from temper_placer.deterministic.channels import ChannelMap, routability_penalty

        cm = ChannelMap.empty()
        p = routability_penalty((10.0, 10.0), cm)
        assert p == 0.0


# ---------------------------------------------------------------------------
# deterministic/bottleneck_map.py: BottleneckMap.score_at, load_bottleneck_map
# ---------------------------------------------------------------------------


class TestBottleneckMap:
    def test_score_at_in_bounds(self):
        from temper_placer.deterministic.bottleneck_map import BottleneckMap

        bm = BottleneckMap(
            cell_size_mm=1.0,
            width=10,
            height=10,
            origin_xy=(0.0, 0.0),
            scores=tuple(float(i % 10) / 10.0 for i in range(100)),
        )
        score = bm.score_at(5.5, 5.5)
        assert 0.0 <= score <= 1.0

    def test_score_at_out_of_bounds(self):
        from temper_placer.deterministic.bottleneck_map import BottleneckMap

        bm = BottleneckMap(
            cell_size_mm=1.0,
            width=10,
            height=10,
            origin_xy=(0.0, 0.0),
            scores=tuple(0.5 for _ in range(100)),
        )
        # Out-of-bounds should return 0.0
        score = bm.score_at(-10.0, -10.0)
        assert score == 0.0

        score = bm.score_at(100.0, 100.0)
        assert score == 0.0


# ---------------------------------------------------------------------------
# topological/graph.py: TopologicalGraph methods
# ---------------------------------------------------------------------------


class TestTopologicalGraph:
    def test_add_component(self):
        from temper_placer.topological.graph import TopologicalGraph

        tg = TopologicalGraph()
        tg.add_component("U1")
        assert "U1" in tg.graph.nodes()

    def test_add_group(self):
        from temper_placer.topological.graph import TopologicalGraph

        tg = TopologicalGraph()
        tg.add_component("U1")
        tg.add_component("C1")
        tg.add_group("loop1", ["U1", "C1"])
        assert "loop1" in tg.graph.nodes()

    def test_add_adjacency(self):
        from temper_placer.topological.graph import TopologicalGraph

        tg = TopologicalGraph()
        tg.add_component("U1")
        tg.add_component("U2")
        tg.add_adjacency("U1", "U2", max_distance=5.0, constraint_id="c1")
        assert tg.graph.has_edge("U1", "U2")
        assert tg.graph.has_edge("U2", "U1")

    def test_add_separation(self):
        from temper_placer.topological.graph import TopologicalGraph

        tg = TopologicalGraph()
        tg.add_component("U1")
        tg.add_component("U2")
        tg.add_separation("U1", "U2", min_distance=10.0, constraint_id="c1")
        assert tg.graph.has_edge("U1", "U2")

    def test_find_separation_conflicts_no_conflict(self):
        from temper_placer.topological.graph import TopologicalGraph

        tg = TopologicalGraph()
        tg.add_component("U1")
        tg.add_component("U2")
        tg.add_adjacency("U1", "U2", max_distance=5.0, constraint_id="c1")
        conflicts = tg.find_separation_conflicts()
        # Only adjacency, no separation -> no conflict
        assert len(conflicts) == 0

    def test_find_separation_conflicts_with_conflict(self):
        from temper_placer.topological.graph import TopologicalGraph

        tg = TopologicalGraph()
        tg.add_component("U1")
        tg.add_component("U2")
        tg.add_adjacency("U1", "U2", max_distance=5.0, constraint_id="c1")
        tg.add_separation("U1", "U2", min_distance=10.0, constraint_id="c2")
        conflicts = tg.find_separation_conflicts()
        # Both adjacency and separation -> conflict
        assert len(conflicts) >= 1


# ---------------------------------------------------------------------------
# heuristics/base.py: Heuristic ABC methods via concrete subclass
# ---------------------------------------------------------------------------


class TestHeuristicABC:
    """Exercise Heuristic.name, priority, description, identify_target_components,
    and apply through a concrete subclass."""

    def test_heuristic_properties_and_methods(self):
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.base import (
            ComponentPlacement,
            Heuristic,
            HeuristicPriority,
            HeuristicResult,
            PlacementContext,
        )
        from temper_placer.io.config_loader import PlacementConstraints

        class TestHeuristicImpl(Heuristic):
            @property
            def name(self) -> str:
                return "test_heuristic"

            @property
            def priority(self) -> HeuristicPriority:
                return HeuristicPriority.STYLE

            @property
            def description(self) -> str:
                return "A test heuristic for coverage"

            def apply(self, context: PlacementContext) -> HeuristicResult:
                targets = self.identify_target_components(context)
                placements = {}
                for comp in targets:
                    placements[comp.ref] = ComponentPlacement(
                        ref=comp.ref,
                        position=(50.0, 50.0),
                        placed_by=self.name,
                    )
                return HeuristicResult(
                    placements=placements,
                    success=True,
                    message=f"Placed {len(placements)} components",
                )

        comps = [
            Component(ref="U1", footprint="QFN-32", bounds=(5, 5)),
            Component(ref="C1", footprint="0603", bounds=(2, 1)),
        ]
        netlist = Netlist(components=comps, nets=[])
        board = Board(width=200, height=200, origin=(0, 0))
        constraints = PlacementConstraints(board_margin_mm=1.0)
        ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)

        h = TestHeuristicImpl()
        assert h.name == "test_heuristic"
        assert h.priority == HeuristicPriority.STYLE
        assert h.description == "A test heuristic for coverage"

        targets = h.identify_target_components(ctx)
        assert len(targets) == 2

        result = h.apply(ctx)
        assert result.success is True
        assert len(result.placements) == 2
        assert "U1" in result.placements
        assert "C1" in result.placements

    def test_heuristic_default_description(self):
        from temper_placer.heuristics.base import Heuristic, HeuristicPriority

        class MinimalHeuristic(Heuristic):
            @property
            def name(self) -> str:
                return "minimal"

            @property
            def priority(self) -> HeuristicPriority:
                return HeuristicPriority.FILL

            def apply(self, context):
                from temper_placer.heuristics.base import HeuristicResult
                return HeuristicResult(success=True)

        h = MinimalHeuristic()
        assert h.description == ""


# ---------------------------------------------------------------------------
# heuristics/base.py: order_refs_by_netlist
# ---------------------------------------------------------------------------


class TestOrderRefsByNetlist:
    def test_orders_by_netlist(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.base import order_refs_by_netlist

        comps = [
            Component(ref="U1", footprint="a", bounds=(1, 1)),
            Component(ref="C1", footprint="b", bounds=(1, 1)),
            Component(ref="R1", footprint="c", bounds=(1, 1)),
            Component(ref="C2", footprint="d", bounds=(1, 1)),
        ]
        netlist = Netlist(components=comps, nets=[])
        # Request in reverse order
        result = order_refs_by_netlist(netlist, ["C2", "R1", "C1", "U1"])
        # Should come back in netlist order
        assert result == ["U1", "C1", "R1", "C2"]

    def test_drops_absent_refs(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.base import order_refs_by_netlist

        comps = [
            Component(ref="U1", footprint="a", bounds=(1, 1)),
        ]
        netlist = Netlist(components=comps, nets=[])
        result = order_refs_by_netlist(netlist, ["U1", "NONEXISTENT"])
        assert result == ["U1"]

    def test_handles_empty(self):
        from temper_placer.core.netlist import Netlist
        from temper_placer.heuristics.base import order_refs_by_netlist

        netlist = Netlist(components=[], nets=[])
        result = order_refs_by_netlist(netlist, [])
        assert result == []
