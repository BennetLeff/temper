"""Tests for multi-layer path reconstruction with via landing segments.

When a route changes layers via a via, if the XY position also changes,
we need to create a "landing segment" on the new layer connecting the
via position to the next point. Without this, traces end up "dangling"
with no connection to the via.

These tests verify that the multi-layer A* path reconstruction correctly
handles all layer transition scenarios.
"""

import pytest
from dataclasses import dataclass

from temper_placer.deterministic.stages.multilayer_astar import (
    MultiLayerAStar,
    MultiLayerPath,
    RouteSegment,
)
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid


@pytest.fixture
def minimal_grid():
    """Create minimal clearance grid for testing."""
    return ClearanceGrid(
        width_mm=100.0,
        height_mm=100.0,
        cell_size_mm=1.0,  # 1mm cells for easy math
        layer_count=4,
    )


@pytest.fixture
def pathfinder(minimal_grid):
    """Create pathfinder instance."""
    return MultiLayerAStar(
        grid=minimal_grid,
        drc_oracle=None,
        net_name="TEST",
        trace_width=0.2,
        via_cost=5.0,
        allowed_layers=[0, 3],  # F.Cu and B.Cu
    )


def _pos_equal(p1, p2, tol=0.5):
    """Check if two positions are equal within tolerance."""
    return abs(p1[0] - p2[0]) < tol and abs(p1[1] - p2[1]) < tol


def _round_pos(p, decimals=1):
    """Round position for comparison."""
    return (round(p[0], decimals), round(p[1], decimals))


class TestSameLayerPaths:
    """Tests for paths that stay on the same layer."""

    def test_same_layer_path_no_vias(self, pathfinder):
        """Path staying on same layer should have no vias."""
        # Simple horizontal path on layer 0
        result = pathfinder.find_path(
            start=(10.0, 50.0), end=(20.0, 50.0), start_layer=0, end_layer=0
        )

        assert result is not None
        assert len(result.via_positions) == 0
        assert len(result.segments) >= 1
        # All segments on same layer
        assert all(s.layer == 0 for s in result.segments)

    def test_diagonal_path_no_vias(self, pathfinder):
        """Diagonal path on same layer should have no vias."""
        result = pathfinder.find_path(
            start=(10.0, 10.0), end=(30.0, 30.0), start_layer=0, end_layer=0
        )

        assert result is not None
        assert len(result.via_positions) == 0


class TestLayerTransitions:
    """Tests for paths that transition between layers."""

    def test_layer_transition_creates_via(self, pathfinder):
        """Path that must change layers should create at least one via."""
        result = pathfinder.find_path(
            start=(10.0, 50.0),
            end=(90.0, 50.0),
            start_layer=0,
            end_layer=3,  # Force layer change
        )

        assert result is not None
        assert len(result.via_positions) >= 1

    def test_via_has_valid_layers(self, pathfinder):
        """Via should connect between two different layers."""
        result = pathfinder.find_path(
            start=(10.0, 50.0), end=(90.0, 50.0), start_layer=0, end_layer=3
        )

        if result and result.via_positions:
            for vx, vy, from_layer, to_layer in result.via_positions:
                assert from_layer != to_layer, "Via must connect different layers"
                assert from_layer in [0, 3], "Via from_layer must be allowed layer"
                assert to_layer in [0, 3], "Via to_layer must be allowed layer"


class TestViaLandingSegments:
    """Tests for landing segment creation after layer transitions."""

    def test_via_has_connected_segment(self, pathfinder):
        """Every via must have at least one segment touching it."""
        result = pathfinder.find_path(
            start=(10.0, 50.0), end=(90.0, 50.0), start_layer=0, end_layer=3
        )

        if result is None:
            pytest.skip("No path found")

        for vx, vy, from_layer, to_layer in result.via_positions:
            via_pos = (vx, vy)

            # Find segments that touch this via position
            segments_at_via = [
                s
                for s in result.segments
                if _pos_equal(s.start, via_pos) or _pos_equal(s.end, via_pos)
            ]

            # Must have at least one segment touching the via
            # (unless via is at start/end of path)
            is_at_start = _pos_equal(via_pos, (10.0, 50.0))
            is_at_end = _pos_equal(via_pos, (90.0, 50.0))

            assert len(segments_at_via) >= 1 or is_at_start or is_at_end, (
                f"Via at {via_pos} has no connected segments"
            )

    def test_no_dangling_segments(self, pathfinder):
        """No segment should be disconnected from the path."""
        result = pathfinder.find_path(
            start=(10.0, 50.0), end=(90.0, 50.0), start_layer=0, end_layer=3
        )

        if result is None or not result.segments:
            pytest.skip("No path or segments found")

        start_pos = _round_pos((10.0, 50.0))
        end_pos = _round_pos((90.0, 50.0))

        for seg in result.segments:
            seg_start = _round_pos(seg.start)
            seg_end = _round_pos(seg.end)

            # Count connections at start endpoint
            start_connections = sum(
                1
                for s in result.segments
                if s != seg and (_pos_equal(s.start, seg.start) or _pos_equal(s.end, seg.start))
            )

            # Count connections at end endpoint
            end_connections = sum(
                1
                for s in result.segments
                if s != seg and (_pos_equal(s.start, seg.end) or _pos_equal(s.end, seg.end))
            )

            # Check via connections
            via_at_start = any(
                _pos_equal((vx, vy), seg.start) for vx, vy, _, _ in result.via_positions
            )
            via_at_end = any(_pos_equal((vx, vy), seg.end) for vx, vy, _, _ in result.via_positions)

            # Start endpoint must connect to something
            start_valid = (
                _pos_equal(seg.start, start_pos)  # Path start
                or _pos_equal(seg.start, end_pos)  # Path end
                or start_connections > 0  # Another segment
                or via_at_start  # Via
            )

            # End endpoint must connect to something
            end_valid = (
                _pos_equal(seg.end, start_pos)  # Path start
                or _pos_equal(seg.end, end_pos)  # Path end
                or end_connections > 0  # Another segment
                or via_at_end  # Via
            )

            assert start_valid, (
                f"Dangling segment start: {seg.start} -> {seg.end} on layer {seg.layer}"
            )
            assert end_valid, f"Dangling segment end: {seg.start} -> {seg.end} on layer {seg.layer}"

    def test_via_bridges_both_layers(self, pathfinder):
        """Via should have segments on both connected layers (or be at endpoint)."""
        result = pathfinder.find_path(
            start=(10.0, 50.0), end=(90.0, 50.0), start_layer=0, end_layer=3
        )

        if result is None or not result.via_positions:
            pytest.skip("No path with vias found")

        for vx, vy, from_layer, to_layer in result.via_positions:
            via_pos = (vx, vy)

            # Find segments touching this via
            segments_at_via = [
                s
                for s in result.segments
                if _pos_equal(s.start, via_pos) or _pos_equal(s.end, via_pos)
            ]

            # Get layers of touching segments
            layers_connected = set(s.layer for s in segments_at_via)

            # Via should connect to at least one of its layers
            # (unless it's at start or end point which connects to pad)
            is_at_endpoint = _pos_equal(via_pos, (10.0, 50.0)) or _pos_equal(via_pos, (90.0, 50.0))

            if not is_at_endpoint:
                assert from_layer in layers_connected or to_layer in layers_connected, (
                    f"Via at {via_pos} ({from_layer}->{to_layer}) has no connected segments on either layer. Found layers: {layers_connected}"
                )


class TestPathContinuity:
    """Tests for overall path continuity from start to end."""

    def test_path_is_continuous(self, pathfinder):
        """Path should be traceable from start to end."""
        result = pathfinder.find_path(
            start=(10.0, 50.0), end=(90.0, 50.0), start_layer=0, end_layer=3
        )

        if result is None or not result.segments:
            pytest.skip("No path found")

        # Build connectivity graph
        # Node = (x, y, layer)
        # Edge = segment or via
        connections = {}  # node -> set of connected nodes

        def add_connection(n1, n2):
            if n1 not in connections:
                connections[n1] = set()
            if n2 not in connections:
                connections[n2] = set()
            connections[n1].add(n2)
            connections[n2].add(n1)

        # Add segment edges
        for seg in result.segments:
            n1 = (_round_pos(seg.start), seg.layer)
            n2 = (_round_pos(seg.end), seg.layer)
            add_connection(n1, n2)

        # Add via edges (connect same XY across layers)
        for vx, vy, from_layer, to_layer in result.via_positions:
            pos = _round_pos((vx, vy))
            n1 = (pos, from_layer)
            n2 = (pos, to_layer)
            add_connection(n1, n2)

        # BFS from start to find reachable nodes
        start_node = (_round_pos((10.0, 50.0)), 0)
        end_node = (_round_pos((90.0, 50.0)), 3)

        if start_node not in connections:
            pytest.skip("Start node not in graph")

        visited = set()
        queue = [start_node]

        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)

            if node in connections:
                for neighbor in connections[node]:
                    if neighbor not in visited:
                        queue.append(neighbor)

        # Check if end is reachable (or nearby position on correct layer)
        end_reachable = any(pos == end_node[0] and layer == end_node[1] for pos, layer in visited)

        # Allow some tolerance for end position
        if not end_reachable:
            end_reachable = any(
                abs(pos[0] - end_node[0][0]) < 2.0
                and abs(pos[1] - end_node[0][1]) < 2.0
                and layer == end_node[1]
                for pos, layer in visited
            )

        assert end_reachable, "Path is not continuous from start to end"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
