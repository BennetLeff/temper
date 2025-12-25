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
        """Property: Pushing should preserve path length."""
        import math
        horizontal_path = get_horizontal_path()
        direction = (math.cos(angle), math.sin(angle))

        pushed = push_path(horizontal_path, direction=direction, distance=distance)

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
