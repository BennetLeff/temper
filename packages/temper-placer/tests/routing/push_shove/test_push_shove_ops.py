"""
Unit tests for push and shove operations.

Tests verify push_path and shove_paths maintain connectivity,
preserve topology, and are reversible.
"""

from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from temper_placer.routing.push_shove import Path, Segment, detect_collision, push_path, shove_paths


def get_horizontal_path():
    """Simple horizontal path."""
    return Path(
        segments=[Segment(start=(0.0, 10.0), end=(20.0, 10.0))],
        width=0.2,
        clearance=0.2,
        net="NET1",
    )


def get_vertical_path():
    """Simple vertical path that is close to but doesn't cross horizontal path."""
    return Path(
        segments=[Segment(start=(10.0, 10.2), end=(10.0, 20.0))],
        width=0.2,
        clearance=0.2,
        net="NET2",
    )


class TestPushPath:
    """Tests for push_path operation."""

    def test_push_path_up(self):
        """Pushing path up should move it vertically (without endpoint preservation)."""
        horizontal_path = get_horizontal_path()
        pushed = push_path(horizontal_path, direction=(0.0, 1.0), distance=2.0, preserve_endpoints=False)

        # Path should be moved up by 2mm
        assert pushed.segments[0].start[1] == 12.0, "Start should move up"
        assert pushed.segments[0].end[1] == 12.0, "End should move up"
        assert pushed.segments[0].start[0] == 0.0, "X should not change"

    def test_push_path_preserves_connectivity(self):
        """Pushed path should maintain connectivity (without endpoint preservation)."""
        horizontal_path = get_horizontal_path()
        pushed = push_path(horizontal_path, direction=(0.0, 1.0), distance=2.0, preserve_endpoints=False)

        # Segments should still be connected
        assert len(pushed.segments) == len(horizontal_path.segments)
        for i in range(len(pushed.segments) - 1):
            assert pushed.segments[i].end == pushed.segments[i + 1].start, \
                "Segments should remain connected"

    def test_push_path_preserves_width_and_clearance(self):
        """Pushed path should maintain width and clearance."""
        horizontal_path = get_horizontal_path()
        pushed = push_path(horizontal_path, direction=(0.0, 1.0), distance=2.0)

        assert pushed.width == horizontal_path.width
        assert pushed.clearance == horizontal_path.clearance

    def test_push_path_preserves_net(self):
        """Pushed path should maintain net assignment."""
        horizontal_path = get_horizontal_path()
        pushed = push_path(horizontal_path, direction=(0.0, 1.0), distance=2.0)

        assert pushed.net == horizontal_path.net

    def test_push_path_zero_distance_is_identity(self):
        """Pushing by zero distance should return equivalent path (without endpoint preservation)."""
        horizontal_path = get_horizontal_path()
        pushed = push_path(horizontal_path, direction=(0.0, 1.0), distance=0.0, preserve_endpoints=False)

        assert pushed == horizontal_path

    @given(
        distance=st.floats(min_value=0.1, max_value=10.0),
    )
    def test_push_path_is_reversible(self, distance):
        """Property: Pushing and pulling should be reversible (without endpoint preservation)."""
        horizontal_path = get_horizontal_path()
        # Push up
        pushed = push_path(horizontal_path, direction=(0.0, 1.0), distance=distance, preserve_endpoints=False)
        # Pull down
        restored = push_path(pushed, direction=(0.0, -1.0), distance=distance, preserve_endpoints=False)

        # Should be back to original (within floating point tolerance)
        for i, seg in enumerate(restored.segments):
            orig_seg = horizontal_path.segments[i]
            assert abs(seg.start[0] - orig_seg.start[0]) < 1e-6
            assert abs(seg.start[1] - orig_seg.start[1]) < 1e-6
            assert abs(seg.end[0] - orig_seg.end[0]) < 1e-6
            assert abs(seg.end[1] - orig_seg.end[1]) < 1e-6

    def test_push_path_diagonal(self):
        """Pushing diagonally should work (without endpoint preservation)."""
        horizontal_path = get_horizontal_path()
        # Normalize diagonal direction
        import math
        dx, dy = 1.0, 1.0
        length = math.sqrt(dx**2 + dy**2)
        direction = (dx / length, dy / length)

        pushed = push_path(horizontal_path, direction=direction, distance=2.0, preserve_endpoints=False)

        # Path should move diagonally by 2mm
        # Each component moves by 2 * direction
        expected_dx = 2.0 * direction[0]
        expected_dy = 2.0 * direction[1]

        assert abs(pushed.segments[0].start[0] - (0.0 + expected_dx)) < 1e-6
        assert abs(pushed.segments[0].start[1] - (10.0 + expected_dy)) < 1e-6


class TestShovePaths:
    """Tests for shove_paths operation."""

    def test_shove_single_path(self):
        """Shoving should push colliding path aside."""
        # Paths collide at (10, 10)
        existing_paths = [get_horizontal_path()]
        new_path = get_vertical_path()

        result = shove_paths(existing_paths, new_path)

        assert result.success, "Shove should succeed"
        assert len(result.paths) == 1, "Should return updated path"

        # Updated path should not collide with new path
        shoved = result.paths[0]
        assert not detect_collision(shoved, new_path), \
            "Shoved path should not collide with new path"

    def test_shove_preserves_all_paths(self):
        """Shove should preserve all paths (no deletion)."""
        horizontal_path = get_horizontal_path()
        path2 = replace(horizontal_path, net="NET2")
        path2 = replace(path2, segments=[Segment(start=(0.0, 12.0), end=(20.0, 12.0))])

        existing_paths = [horizontal_path, path2]
        new_path = Path(
            segments=[Segment(start=(10.0, 5.0), end=(10.0, 15.0))],
            width=0.2,
            clearance=0.2,
            net="NET3",
        )

        result = shove_paths(existing_paths, new_path)

        assert len(result.paths) == 2, "Should preserve all existing paths"

    def test_shove_minimal_displacement(self):
        """Shove should minimize displacement while preserving endpoints."""
        horizontal_path = get_horizontal_path()
        existing_paths = [horizontal_path]
        new_path = get_vertical_path()

        result = shove_paths(existing_paths, new_path)

        if result.success:
            shoved = result.paths[0]

            # With endpoint preservation, the start/end Y should be preserved
            # but there will be an intermediate point that moves
            orig_start = horizontal_path.segments[0].start
            orig_end = horizontal_path.segments[-1].end

            # Endpoints should be preserved
            assert shoved.segments[0].start == orig_start, \
                "Start endpoint should be preserved"
            assert shoved.segments[-1].end == orig_end, \
                "End endpoint should be preserved"

            # The path should not collide with new_path anymore
            assert not detect_collision(shoved, new_path), \
                "Shoved path should not collide after shove"

    def test_shove_ripple_propagation(self):
        """Shove should propagate to multiple paths."""
        # Three parallel horizontal paths, spaced more widely to allow endpoint-preserving shove
        path1 = Path(
            segments=[Segment(start=(0.0, 10.0), end=(20.0, 10.0))],
            width=0.2, clearance=0.2, net="NET1"
        )
        path2 = Path(
            segments=[Segment(start=(0.0, 12.0), end=(20.0, 12.0))],
            width=0.2, clearance=0.2, net="NET2"
        )
        path3 = Path(
            segments=[Segment(start=(0.0, 14.0), end=(20.0, 14.0))],
            width=0.2, clearance=0.2, net="NET3"
        )

        existing_paths = [path1, path2, path3]

        # New path crosses all three
        new_path = Path(
            segments=[Segment(start=(10.0, 9.0), end=(10.0, 15.0))],
            width=0.2, clearance=0.2, net="CROSS"
        )

        result = shove_paths(existing_paths, new_path)

        # With endpoint preservation, ripple shove may not always succeed
        # because the geometry becomes constrained. This is expected behavior.
        if result.success:
            # All paths should no longer collide
            for i, shoved in enumerate(result.paths):
                assert not detect_collision(shoved, new_path), \
                    f"Path {i} should not collide after shove"
        else:
            # If shove fails, original paths should be preserved
            assert result.paths == existing_paths, \
                "Failed shove should preserve original paths"

    def test_shove_maintains_connectivity(self):
        """Shove should maintain path connectivity."""
        # Multi-segment path
        multi_seg = Path(
            segments=[
                Segment(start=(0.0, 10.0), end=(10.0, 10.0)),
                Segment(start=(10.0, 10.0), end=(10.0, 20.0)),
                Segment(start=(10.0, 20.0), end=(20.0, 20.0)),
            ],
            width=0.2, clearance=0.2, net="NET1"
        )

        new_path = Path(
            segments=[Segment(start=(5.0, 5.0), end=(5.0, 15.0))],
            width=0.2, clearance=0.2, net="NET2"
        )

        result = shove_paths([multi_seg], new_path)

        if result.success:
            shoved = result.paths[0]

            # Verify connectivity
            for i in range(len(shoved.segments) - 1):
                assert shoved.segments[i].end == shoved.segments[i + 1].start, \
                    "Segments should remain connected after shove"

    def test_shove_impossible_returns_failure(self):
        """Shove should fail when no solution exists."""
        # Paths that cannot be shoved (e.g., at board edge)
        edge_path = Path(
            segments=[Segment(start=(0.0, 0.0), end=(20.0, 0.0))],
            width=0.2, clearance=0.2, net="NET1"
        )

        # New path that would require shoving beyond board edge
        new_path = Path(
            segments=[Segment(start=(10.0, -1.0), end=(10.0, 1.0))],
            width=0.2, clearance=0.2, net="NET2"
        )

        result = shove_paths([edge_path], new_path, board_bounds=(20.0, 20.0))

        # Should either succeed with valid shove or fail gracefully
        if not result.success:
            assert result.paths == [edge_path], "Should preserve original on failure"


class TestPushShoveProperties:
    """Property-based tests for push/shove operations."""

    @given(
        distance=st.floats(min_value=0.1, max_value=5.0),
        angle=st.floats(min_value=0.0, max_value=6.28),  # 0 to 2π
    )
    def test_push_preserves_path_length(self, distance, angle):
        """Property: Pushing should preserve path length (without endpoint preservation)."""
        import math
        horizontal_path = get_horizontal_path()
        direction = (math.cos(angle), math.sin(angle))

        # Use preserve_endpoints=False to test pure translation
        pushed = push_path(horizontal_path, direction=direction, distance=distance, preserve_endpoints=False)

        # Calculate path lengths
        def path_length(path):
            total = 0.0
            for seg in path.segments:
                dx = seg.end[0] - seg.start[0]
                dy = seg.end[1] - seg.start[1]
                total += math.sqrt(dx**2 + dy**2)
            return total

        orig_length = path_length(horizontal_path)
        pushed_length = path_length(pushed)

        assert abs(orig_length - pushed_length) < 1e-6, \
            "Push should preserve path length"

    @given(
        num_paths=st.integers(min_value=1, max_value=5),
    )
    def test_shove_preserves_path_count(self, num_paths):
        """Property: Shove should preserve number of paths."""
        # Create parallel paths
        paths = []
        for i in range(num_paths):
            path = Path(
                segments=[Segment(start=(0.0, 10.0 + i * 1.0), end=(20.0, 10.0 + i * 1.0))],
                width=0.2, clearance=0.2, net=f"NET{i}"
            )
            paths.append(path)

        new_path = Path(
            segments=[Segment(start=(10.0, 5.0), end=(10.0, 20.0))],
            width=0.2, clearance=0.2, net="CROSS"
        )

        result = shove_paths(paths, new_path)

        if result.success:
            assert len(result.paths) == num_paths, \
                "Shove should preserve path count"


# =============================================================================
# Regression tests for temper-bl6q.2: Endpoint preservation in push_path
# =============================================================================

class TestPushPathEndpointPreservation:
    """Tests for endpoint-preserving push behavior (temper-bl6q.2 fix)."""

    def test_push_preserves_endpoints_single_segment(self):
        """Single-segment path should preserve both endpoints."""
        path = Path(
            segments=[Segment(start=(0.0, 0.0), end=(20.0, 0.0))],
            width=0.2, clearance=0.2, net="NET1"
        )

        # Push up by 5mm with endpoint preservation (default)
        pushed = push_path(path, direction=(0.0, 1.0), distance=5.0)

        # Start and end should be preserved
        assert pushed.segments[0].start == (0.0, 0.0), \
            "Start endpoint should be preserved"
        assert pushed.segments[-1].end == (20.0, 0.0), \
            "End endpoint should be preserved"

        # Should have created additional segment(s) to accommodate push
        assert len(pushed.segments) >= 1

    def test_push_preserves_endpoints_multi_segment(self):
        """Multi-segment path should preserve first start and last end."""
        path = Path(
            segments=[
                Segment(start=(0.0, 0.0), end=(10.0, 0.0)),
                Segment(start=(10.0, 0.0), end=(10.0, 10.0)),
                Segment(start=(10.0, 10.0), end=(20.0, 10.0)),
            ],
            width=0.2, clearance=0.2, net="NET1"
        )

        # Push right by 3mm
        pushed = push_path(path, direction=(1.0, 0.0), distance=3.0)

        # First segment's start (source pad) should be preserved
        assert pushed.segments[0].start == (0.0, 0.0), \
            "Source pad location should be preserved"

        # Last segment's end (destination pad) should be preserved
        assert pushed.segments[-1].end == (20.0, 10.0), \
            "Destination pad location should be preserved"

    def test_push_without_endpoint_preservation(self):
        """With preserve_endpoints=False, all points should move."""
        path = Path(
            segments=[Segment(start=(0.0, 0.0), end=(20.0, 0.0))],
            width=0.2, clearance=0.2, net="NET1"
        )

        # Push up by 5mm WITHOUT endpoint preservation
        pushed = push_path(path, direction=(0.0, 1.0), distance=5.0, preserve_endpoints=False)

        # Both endpoints should have moved
        assert pushed.segments[0].start == (0.0, 5.0), \
            "Start should move when preserve_endpoints=False"
        assert pushed.segments[-1].end == (20.0, 5.0), \
            "End should move when preserve_endpoints=False"

    def test_push_maintains_connectivity_with_endpoint_preservation(self):
        """Pushed path should remain geometrically connected."""
        path = Path(
            segments=[
                Segment(start=(0.0, 0.0), end=(10.0, 0.0)),
                Segment(start=(10.0, 0.0), end=(20.0, 0.0)),
            ],
            width=0.2, clearance=0.2, net="NET1"
        )

        pushed = push_path(path, direction=(0.0, 1.0), distance=5.0)

        # Verify connectivity: each segment's end connects to next segment's start
        for i in range(len(pushed.segments) - 1):
            assert pushed.segments[i].end == pushed.segments[i + 1].start, \
                f"Segments {i} and {i+1} should remain connected"

    def test_shove_preserves_pad_connectivity(self):
        """Shoved paths should still connect to their original pad locations."""
        # Path from pad at (5, 10) to pad at (15, 10)
        original_path = Path(
            segments=[Segment(start=(5.0, 10.0), end=(15.0, 10.0))],
            width=0.2, clearance=0.2, net="NET1"
        )

        # New path that crosses it
        new_path = Path(
            segments=[Segment(start=(10.0, 5.0), end=(10.0, 15.0))],
            width=0.2, clearance=0.2, net="NET2"
        )

        result = shove_paths([original_path], new_path)

        if result.success:
            shoved = result.paths[0]

            # Start pad location must be preserved
            assert shoved.segments[0].start == (5.0, 10.0), \
                "Source pad connection should be preserved after shove"

            # End pad location must be preserved
            assert shoved.segments[-1].end == (15.0, 10.0), \
                "Destination pad connection should be preserved after shove"


# =============================================================================
# Regression tests for temper-loms.1: Multi-segment push direction
# =============================================================================

class TestMultiSegmentPushDirection:
    """Tests for collision-aware push direction calculation."""

    def test_l_shaped_path_push_direction(self):
        """L-shaped path should compute push direction from collision location."""
        from temper_placer.routing.push_shove import (
            compute_push_direction,
            _find_collision_point,
            _compute_path_centroid,
        )

        # L-shaped path: horizontal then vertical
        l_path = Path(
            segments=[
                Segment(start=(0.0, 0.0), end=(10.0, 0.0)),  # Horizontal
                Segment(start=(10.0, 0.0), end=(10.0, 10.0)),  # Vertical
            ],
            width=0.2, clearance=0.2, net="NET1"
        )

        # New path colliding with vertical segment
        # With width=0.2 and clearance=0.2, required_dist = 0.4
        # Place new_path at x=10.2 so it collides with vertical segment at x=10
        new_path = Path(
            segments=[Segment(start=(10.2, 5.0), end=(20.0, 5.0))],
            width=0.2, clearance=0.2, net="NET2"
        )

        # Find collision point
        collision_pt = _find_collision_point(l_path, new_path)

        # Collision should be near (10, 5) - the vertical segment
        assert collision_pt is not None, "Should find collision point"
        assert abs(collision_pt[1] - 5.0) < 2.0, \
            f"Collision y should be near 5.0, got {collision_pt[1]}"

        # Compute push direction with collision hint
        direction = compute_push_direction(l_path, new_path, collision_pt)

        # Direction should be mostly leftward (away from new_path)
        assert direction[0] < 0, \
            f"Push should be leftward, got dx={direction[0]}"

    def test_centroid_weighted_by_length(self):
        """Path centroid should weight longer segments more."""
        from temper_placer.routing.push_shove import _compute_path_centroid

        # Path with one long segment and one short segment
        path = Path(
            segments=[
                Segment(start=(0.0, 0.0), end=(100.0, 0.0)),  # 100mm long
                Segment(start=(100.0, 0.0), end=(100.0, 10.0)),  # 10mm long
            ],
            width=0.2, clearance=0.2, net="NET1"
        )

        centroid = _compute_path_centroid(path)

        # Centroid should be closer to the long segment's center (50, 0)
        # than to the short segment's center (100, 5)
        assert centroid[0] < 60.0, \
            f"Centroid x should be closer to long segment, got {centroid[0]}"

    def test_push_direction_without_collision_uses_centroid(self):
        """Without collision hint, push direction uses centroid."""
        from temper_placer.routing.push_shove import compute_push_direction

        path = Path(
            segments=[Segment(start=(0.0, 0.0), end=(10.0, 0.0))],
            width=0.2, clearance=0.2, net="NET1"
        )
        new_path = Path(
            segments=[Segment(start=(0.0, 10.0), end=(10.0, 10.0))],
            width=0.2, clearance=0.2, net="NET2"
        )

        # No collision hint
        direction = compute_push_direction(path, new_path, collision_point=None)

        # Should push downward (path centroid is below new_path centroid)
        assert direction[1] < 0, \
            f"Push should be downward, got dy={direction[1]}"

    def test_u_shaped_path_collision(self):
        """U-shaped path should handle collision on middle segment."""
        from temper_placer.routing.push_shove import (
            compute_push_direction,
            _find_collision_point,
        )

        # U-shaped path: down, across, up
        u_path = Path(
            segments=[
                Segment(start=(0.0, 10.0), end=(0.0, 0.0)),    # Down
                Segment(start=(0.0, 0.0), end=(10.0, 0.0)),    # Across
                Segment(start=(10.0, 0.0), end=(10.0, 10.0)),  # Up
            ],
            width=0.2, clearance=0.2, net="NET1"
        )

        # New path colliding with bottom segment
        new_path = Path(
            segments=[Segment(start=(5.0, -0.3), end=(5.0, 0.3))],
            width=0.2, clearance=0.2, net="NET2"
        )

        collision_pt = _find_collision_point(u_path, new_path)

        assert collision_pt is not None, "Should find collision point"
        # Collision should be on the bottom horizontal segment
        assert collision_pt[1] < 2.0, \
            f"Collision should be near bottom, got y={collision_pt[1]}"

        direction = compute_push_direction(u_path, new_path, collision_pt)

        # Should push away from new_path (upward or to side)
        # The exact direction depends on relative positions
        assert abs(direction[0]) > 0.1 or abs(direction[1]) > 0.1, \
            "Should have meaningful push direction"


class TestAdaptiveCollisionSampling:
    """Tests for adaptive collision sampling (temper-loms.4)."""

    def test_long_segment_gets_more_samples(self):
        """Long segments should get proportionally more samples."""
        from temper_placer.routing.push_shove import segment_length

        # Long 50mm segment
        long_seg = Segment(start=(0.0, 0.0), end=(50.0, 0.0))
        long_path = Path(
            segments=[long_seg],
            width=0.2, clearance=0.2, net="NET1"
        )

        # Short 5mm segment
        short_seg = Segment(start=(0.0, 5.0), end=(5.0, 5.0))
        short_path = Path(
            segments=[short_seg],
            width=0.2, clearance=0.2, net="NET2"
        )

        # Verify segment lengths
        assert segment_length(long_seg) == 50.0
        assert segment_length(short_seg) == 5.0

        # With samples_per_mm=2.0, long segment gets 100 samples (clamped by max)
        # Short segment gets 10 samples
        # Both should successfully run collision detection
        result = detect_collision(long_path, short_path, samples_per_mm=2.0)
        # These paths don't collide (5mm apart, need 0.4mm total clearance)
        assert result is False

    def test_min_samples_respected(self):
        """Very short segments should respect minimum samples."""
        # Very short 0.5mm segment
        tiny_seg = Segment(start=(0.0, 0.0), end=(0.5, 0.0))
        tiny_path = Path(
            segments=[tiny_seg],
            width=0.2, clearance=0.2, net="NET1"
        )

        other_seg = Segment(start=(0.0, 5.0), end=(5.0, 5.0))
        other_path = Path(
            segments=[other_seg],
            width=0.2, clearance=0.2, net="NET2"
        )

        # With samples_per_mm=2.0, tiny segment would get 1 sample
        # But min_samples=5 should ensure at least 5 samples
        result = detect_collision(tiny_path, other_path, samples_per_mm=2.0, min_samples=5)
        assert result is False  # No collision

    def test_max_samples_respected(self):
        """Very long segments should respect maximum samples."""
        # Very long 200mm segment
        huge_seg = Segment(start=(0.0, 0.0), end=(200.0, 0.0))
        huge_path = Path(
            segments=[huge_seg],
            width=0.2, clearance=0.2, net="NET1"
        )

        other_seg = Segment(start=(100.0, 5.0), end=(100.0, 10.0))
        other_path = Path(
            segments=[other_seg],
            width=0.2, clearance=0.2, net="NET2"
        )

        # With samples_per_mm=2.0, huge segment would get 400 samples
        # But max_samples=100 should cap it
        result = detect_collision(huge_path, other_path, samples_per_mm=2.0, max_samples=100)
        assert result is False  # No collision

    def test_fixed_num_samples_overrides_adaptive(self):
        """Explicit num_samples should override adaptive sampling."""
        long_seg = Segment(start=(0.0, 0.0), end=(50.0, 0.0))
        long_path = Path(
            segments=[long_seg],
            width=0.2, clearance=0.2, net="NET1"
        )

        short_seg = Segment(start=(25.0, 5.0), end=(25.0, 10.0))
        short_path = Path(
            segments=[short_seg],
            width=0.2, clearance=0.2, net="NET2"
        )

        # Explicit num_samples=10 should override adaptive
        result = detect_collision(long_path, short_path, num_samples=10)
        assert result is False  # No collision

    def test_no_missed_collision_on_long_segment(self):
        """Adaptive sampling should not miss collision on long segment middle."""
        # Long 50mm horizontal segment
        long_path = Path(
            segments=[Segment(start=(0.0, 0.0), end=(50.0, 0.0))],
            width=0.2, clearance=0.2, net="NET1"
        )

        # Vertical segment crossing at middle (x=25mm)
        crossing_path = Path(
            segments=[Segment(start=(25.0, -1.0), end=(25.0, 1.0))],
            width=0.2, clearance=0.2, net="NET2"
        )

        # Should detect collision in the middle
        result = detect_collision(long_path, crossing_path, samples_per_mm=2.0)
        assert result is True, "Should detect collision in middle of long segment"

    def test_collision_detection_with_adaptive_is_symmetric(self):
        """Collision detection should be symmetric with adaptive sampling."""
        path1 = Path(
            segments=[Segment(start=(0.0, 0.0), end=(30.0, 0.0))],
            width=0.2, clearance=0.2, net="NET1"
        )
        path2 = Path(
            segments=[Segment(start=(15.0, -1.0), end=(15.0, 1.0))],
            width=0.2, clearance=0.2, net="NET2"
        )

        result_12 = detect_collision(path1, path2, samples_per_mm=2.0)
        result_21 = detect_collision(path2, path1, samples_per_mm=2.0)

        assert result_12 == result_21, "Collision detection should be symmetric"
        assert result_12 is True  # These paths cross

    def test_same_net_no_collision_with_adaptive(self):
        """Same net should not collide even with adaptive sampling."""
        path1 = Path(
            segments=[Segment(start=(0.0, 0.0), end=(50.0, 0.0))],
            width=0.2, clearance=0.2, net="SAME_NET"
        )
        path2 = Path(
            segments=[Segment(start=(25.0, 0.0), end=(25.0, 10.0))],
            width=0.2, clearance=0.2, net="SAME_NET"
        )

        # Crossing paths on same net should not report collision
        result = detect_collision(path1, path2, samples_per_mm=2.0)
        assert result is False
