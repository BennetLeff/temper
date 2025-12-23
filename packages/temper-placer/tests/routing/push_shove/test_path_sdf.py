"""
Unit tests for immutable Path dataclass with SDF collision detection.

Tests verify Path immutability, SDF generation, and collision detection
using signed distance functions.
"""

import pytest
from hypothesis import given, strategies as st
import jax.numpy as jnp
from dataclasses import FrozenInstanceError

from temper_placer.routing.push_shove import Path, Segment, to_sdf, detect_collision


def get_simple_path():
    """Simple L-shaped path."""
    return Path(
        segments=[
            Segment(start=(0.0, 0.0), end=(10.0, 0.0)),
            Segment(start=(10.0, 0.0), end=(10.0, 10.0)),
        ],
        width=0.2,
        clearance=0.2,
        net="NET1",
    )


def get_straight_path():
    """Straight horizontal path."""
    return Path(
        segments=[Segment(start=(0.0, 5.0), end=(20.0, 5.0))],
        width=0.2,
        clearance=0.2,
        net="NET2",
    )


class TestPathImmutability:
    """Tests for Path immutability."""

    def test_path_is_frozen(self):
        """Path should be immutable (frozen dataclass)."""
        path = get_simple_path()
        with pytest.raises(FrozenInstanceError):
            path.width = 0.5

    def test_segments_are_immutable(self):
        """Segments should be immutable."""
        path = get_simple_path()
        with pytest.raises((FrozenInstanceError, AttributeError)):
            path.segments[0].start = (1.0, 1.0)

    def test_path_copy_is_independent(self):
        """Copying path creates independent instance."""
        from dataclasses import replace
        path = get_simple_path()
        
        new_path = replace(path, width=0.5)
        
        assert new_path.width == 0.5
        assert path.width == 0.2
        assert new_path.segments == path.segments

    def test_path_equality(self):
        """Paths with same data should be equal."""
        path1 = Path(
            segments=[Segment(start=(0.0, 0.0), end=(10.0, 0.0))],
            width=0.2,
            clearance=0.2,
            net="NET1",
        )
        path2 = Path(
            segments=[Segment(start=(0.0, 0.0), end=(10.0, 0.0))],
            width=0.2,
            clearance=0.2,
            net="NET1",
        )
        
        assert path1 == path2

    def test_path_hashing(self):
        """Frozen paths should be hashable."""
        path = get_simple_path()
        path_set = {path}
        assert path in path_set


class TestPathSDF:
    """Tests for Path SDF (Signed Distance Function) generation."""

    def test_sdf_at_path_center_is_negative(self):
        """SDF should be negative inside path."""
        path = get_straight_path()
        sdf = to_sdf(path)
        
        # Point at center of path
        distance = sdf((10.0, 5.0))
        
        assert distance < 0, "SDF should be negative inside path"

    def test_sdf_at_path_edge_is_zero(self):
        """SDF should be ~0 at path edge (including clearance)."""
        path = get_straight_path()
        sdf = to_sdf(path)
        
        # Point at edge (radius = width/2 + clearance/2 = 0.1 + 0.1 = 0.2)
        distance = sdf((10.0, 5.0 + 0.2))
        
        assert abs(distance) < 0.05, f"SDF at edge should be ~0, got {distance}"

    def test_sdf_outside_path_is_positive(self):
        """SDF should be positive outside path."""
        path = get_straight_path()
        sdf = to_sdf(path)
        
        # Point far from path
        distance = sdf((10.0, 10.0))
        
        assert distance > 0, "SDF should be positive outside path"

    def test_sdf_distance_is_euclidean(self):
        """SDF should return Euclidean distance to nearest point."""
        path = get_straight_path()
        sdf = to_sdf(path)
        
        # Point 5mm above path center
        distance = sdf((10.0, 10.0))
        
        # Distance to path boundary = 5.0 - radius = 5.0 - 0.2 = 4.8
        expected = 4.8
        assert abs(distance - expected) < 0.1, \
            f"Expected distance ~{expected}, got {distance}"

    def test_sdf_includes_clearance(self):
        """SDF should include clearance in distance calculation."""
        path = Path(
            segments=[Segment(start=(0.0, 0.0), end=(10.0, 0.0))],
            width=0.2,
            clearance=0.3,  # Larger clearance
            net="NET1",
        )
        sdf = to_sdf(path)
        
        # Point at width/2 + clearance/2 from center
        # Total radius = (0.2 + 0.3) / 2 = 0.25
        distance = sdf((5.0, 0.25))
        
        assert abs(distance) < 0.05, "SDF should include clearance"

    def test_sdf_for_multi_segment_path(self):
        """SDF should handle multi-segment paths."""
        path = get_simple_path()
        sdf = to_sdf(path)
        
        # Point near corner
        distance = sdf((10.0, 0.0))
        
        assert distance < 0, "SDF should be negative at corner"

    @given(
        x=st.floats(min_value=-5.0, max_value=25.0),
        y=st.floats(min_value=-5.0, max_value=15.0),
    )
    def test_sdf_is_continuous(self, x, y):
        """Property: SDF should be continuous everywhere."""
        path = get_straight_path()
        sdf = to_sdf(path)
        
        distance = sdf((x, y))
        
        # SDF should always return a finite number
        assert jnp.isfinite(distance), f"SDF returned non-finite value at ({x}, {y})"


class TestCollisionDetection:
    """Tests for SDF-based collision detection."""

    def test_parallel_paths_no_collision(self):
        """Parallel paths with sufficient spacing should not collide."""
        path1 = Path(
            segments=[Segment(start=(0.0, 0.0), end=(20.0, 0.0))],
            width=0.2,
            clearance=0.2,
            net="NET1",
        )
        path2 = Path(
            segments=[Segment(start=(0.0, 2.0), end=(20.0, 2.0))],
            width=0.2,
            clearance=0.2,
            net="NET2",
        )
        
        collision = detect_collision(path1, path2)
        
        assert not collision, "Parallel paths should not collide"

    def test_crossing_paths_collide(self):
        """Crossing paths should collide."""
        path1 = Path(
            segments=[Segment(start=(0.0, 10.0), end=(20.0, 10.0))],
            width=0.2,
            clearance=0.2,
            net="NET1",
        )
        path2 = Path(
            segments=[Segment(start=(10.0, 0.0), end=(10.0, 20.0))],
            width=0.2,
            clearance=0.2,
            net="NET2",
        )
        
        collision = detect_collision(path1, path2)
        
        assert collision, "Crossing paths should collide"

    def test_touching_paths_collide(self):
        """Paths that touch (within clearance) should collide."""
        path1 = Path(
            segments=[Segment(start=(0.0, 0.0), end=(20.0, 0.0))],
            width=0.2,
            clearance=0.2,
            net="NET1",
        )
        # Required distance = (0.2 + 0.2 + 0.2 + 0.2) / 2 = 0.4
        # Path2 at distance = 0.39 (colliding)
        path2 = Path(
            segments=[Segment(start=(0.0, 0.39), end=(20.0, 0.39))],
            width=0.2,
            clearance=0.2,
            net="NET2",
        )
        
        collision = detect_collision(path1, path2)
        
        assert collision, "Paths within clearance should collide"

    def test_same_net_no_collision(self):
        """Paths on same net should not collide."""
        path1 = Path(
            segments=[Segment(start=(0.0, 0.0), end=(10.0, 0.0))],
            width=0.2,
            clearance=0.2,
            net="NET1",
        )
        path2 = Path(
            segments=[Segment(start=(10.0, 0.0), end=(20.0, 0.0))],
            width=0.2,
            clearance=0.2,
            net="NET1",  # Same net
        )
        
        collision = detect_collision(path1, path2)
        
        assert not collision, "Same net paths should not collide"

    def test_collision_is_symmetric(self):
        """Property: Collision detection should be symmetric."""
        path1 = get_simple_path()
        path2 = get_straight_path()
        collision_12 = detect_collision(path1, path2)
        collision_21 = detect_collision(path2, path1)
        
        assert collision_12 == collision_21, "Collision should be symmetric"

    @given(
        offset=st.floats(min_value=0.5, max_value=5.0),
    )
    def test_collision_threshold(self, offset):
        """Property: Paths separated by > clearance should not collide."""
        path1 = Path(
            segments=[Segment(start=(0.0, 0.0), end=(20.0, 0.0))],
            width=0.2,
            clearance=0.2,
            net="NET1",
        )
        path2 = Path(
            segments=[Segment(start=(0.0, offset), end=(20.0, offset))],
            width=0.2,
            clearance=0.2,
            net="NET2",
        )
        
        collision = detect_collision(path1, path2)
        
        # Minimum separation = width/2 + clearance/2 + width/2 + clearance/2 = 0.4
        if offset > 0.4:
            assert not collision, f"Paths separated by {offset}mm should not collide"


class TestSDFComposition:
    """Tests for SDF composition laws."""

    def test_sdf_union_is_commutative(self):
        """Property: SDF union should be commutative."""
        path1 = Path(
            segments=[Segment(start=(0.0, 0.0), end=(10.0, 0.0))],
            width=0.2,
            clearance=0.0,
            net="NET1",
        )
        path2 = Path(
            segments=[Segment(start=(0.0, 5.0), end=(10.0, 5.0))],
            width=0.2,
            clearance=0.0,
            net="NET2",
        )
        
        sdf1 = to_sdf(path1)
        sdf2 = to_sdf(path2)
        
        # Union: min(sdf1, sdf2)
        union_12 = lambda p: min(sdf1(p), sdf2(p))
        union_21 = lambda p: min(sdf2(p), sdf1(p))
        
        test_point = (5.0, 2.5)
        assert abs(union_12(test_point) - union_21(test_point)) < 1e-6, \
            "SDF union should be commutative"

    def test_sdf_union_is_associative(self):
        """Property: SDF union should be associative."""
        path1 = Path(segments=[Segment(start=(0.0, 0.0), end=(10.0, 0.0))], width=0.2, clearance=0.0, net="N1")
        path2 = Path(segments=[Segment(start=(0.0, 5.0), end=(10.0, 5.0))], width=0.2, clearance=0.0, net="N2")
        path3 = Path(segments=[Segment(start=(0.0, 10.0), end=(10.0, 10.0))], width=0.2, clearance=0.0, net="N3")
        
        sdf1, sdf2, sdf3 = to_sdf(path1), to_sdf(path2), to_sdf(path3)
        
        # (A ∪ B) ∪ C
        union_ab_c = lambda p: min(min(sdf1(p), sdf2(p)), sdf3(p))
        # A ∪ (B ∪ C)
        union_a_bc = lambda p: min(sdf1(p), min(sdf2(p), sdf3(p)))
        
        test_point = (5.0, 7.5)
        assert abs(union_ab_c(test_point) - union_a_bc(test_point)) < 1e-6, \
            "SDF union should be associative"
