"""Tests for deduplication key collision issues."""

from temper_placer.core.board import Trace
from temper_placer.deterministic.stages.drc_sweep import TrackDeduplicationStage
from temper_placer.deterministic.state import BoardState


class TestDeduplicationCollision:
    """Tests for deduplication key collision issues."""

    def test_adjacent_segments_not_deduplicated(self):
        """Adjacent segments sharing an endpoint should NOT be deduplicated."""
        # Two adjacent segments: A->B and B->C
        traces = [
            Trace(
                start=(70.00, 15.00),
                end=(70.25, 15.00),
                width=0.2,
                layer="B.Cu",
                net="USB_D+",
            ),
            Trace(
                start=(70.25, 15.00),
                end=(70.50, 15.00),
                width=0.2,
                layer="B.Cu",
                net="USB_D+",
            ),
        ]

        stage = TrackDeduplicationStage(tolerance_mm=0.05)
        state = BoardState(routes=frozenset(traces))
        result = stage.run(state)

        assert len(result.routes) == 2, (
            f"Adjacent segments should not be deduplicated, got {len(result.routes)}"
        )

    def test_opposite_direction_segments_deduplicated(self):
        """Same segment in opposite direction SHOULD be deduplicated."""
        # Same segment, different direction: A->B and B->A
        traces = [
            Trace(
                start=(70.00, 15.00),
                end=(70.25, 15.00),
                width=0.2,
                layer="B.Cu",
                net="USB_D+",
            ),
            Trace(
                start=(70.25, 15.00),
                end=(70.00, 15.00),
                width=0.2,
                layer="B.Cu",
                net="USB_D+",
            ),
        ]

        stage = TrackDeduplicationStage(tolerance_mm=0.05)
        state = BoardState(routes=frozenset(traces))
        result = stage.run(state)

        assert len(result.routes) == 1, (
            f"Opposite direction segments should be deduplicated, got {len(result.routes)}"
        )

    def test_continuous_path_preserved(self):
        """A continuous 10-segment path should remain intact after deduplication."""
        # Create 10 adjacent segments: (0,0)->(0.25,0)->(0.5,0)->...->(2.5,0)
        traces = []
        for i in range(10):
            traces.append(
                Trace(
                    start=(i * 0.25, 0),
                    end=((i + 1) * 0.25, 0),
                    width=0.2,
                    layer="B.Cu",
                    net="USB_D+",
                )
            )

        stage = TrackDeduplicationStage(tolerance_mm=0.05)
        state = BoardState(routes=frozenset(traces))
        result = stage.run(state)

        assert len(result.routes) == 10, f"Continuous path lost {10 - len(result.routes)} segments"

    def test_floating_point_precision_no_collision(self):
        """Floating point precision should not cause false collisions."""
        # Test with values that might have precision issues
        traces = []
        for i in range(100):
            x = i * 0.25  # 0, 0.25, 0.5, ...
            traces.append(
                Trace(
                    start=(x, 15.0),
                    end=(x + 0.25, 15.0),
                    width=0.2,
                    layer="B.Cu",
                    net="USB_D+",
                )
            )

        stage = TrackDeduplicationStage(tolerance_mm=0.05)
        state = BoardState(routes=frozenset(traces))
        result = stage.run(state)

        assert len(result.routes) == 100, (
            f"Lost {100 - len(result.routes)} segments to precision issues"
        )

    def test_tolerance_boundary_no_collision(self):
        """Segments just outside tolerance should not be deduplicated."""
        # Two segments 0.06mm apart (just outside 0.05mm tolerance)
        traces = [
            Trace(
                start=(70.00, 15.00),
                end=(70.25, 15.00),
                width=0.2,
                layer="B.Cu",
                net="USB_D+",
            ),
            Trace(
                start=(70.00, 15.06),
                end=(70.25, 15.06),
                width=0.2,
                layer="B.Cu",
                net="USB_D+",
            ),
        ]

        stage = TrackDeduplicationStage(tolerance_mm=0.05)
        state = BoardState(routes=frozenset(traces))
        result = stage.run(state)

        assert len(result.routes) == 2, (
            f"Segments outside tolerance should not be deduplicated, got {len(result.routes)}"
        )

    def test_exact_duplicate_deduplicated(self):
        """Exact duplicate segments SHOULD be deduplicated."""
        # Two identical segments
        traces = [
            Trace(
                start=(70.00, 15.00),
                end=(70.25, 15.00),
                width=0.2,
                layer="B.Cu",
                net="USB_D+",
            ),
            Trace(
                start=(70.00, 15.00),
                end=(70.25, 15.00),
                width=0.2,
                layer="B.Cu",
                net="USB_D+",
            ),
        ]

        stage = TrackDeduplicationStage(tolerance_mm=0.05)
        state = BoardState(routes=frozenset(traces))
        result = stage.run(state)

        assert len(result.routes) == 1, (
            f"Exact duplicates should be deduplicated, got {len(result.routes)}"
        )

    def test_different_nets_not_deduplicated(self):
        """Same position but different nets should NOT be deduplicated."""
        # Same segment, different nets
        traces = [
            Trace(
                start=(70.00, 15.00),
                end=(70.25, 15.00),
                width=0.2,
                layer="B.Cu",
                net="USB_D+",
            ),
            Trace(
                start=(70.00, 15.00),
                end=(70.25, 15.00),
                width=0.2,
                layer="B.Cu",
                net="USB_D-",
            ),
        ]

        stage = TrackDeduplicationStage(tolerance_mm=0.05)
        state = BoardState(routes=frozenset(traces))
        result = stage.run(state)

        assert len(result.routes) == 2, (
            f"Different nets should not be deduplicated, got {len(result.routes)}"
        )
