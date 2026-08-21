"""Tests for deduplication key collision issues."""

from temper_placer.core.board import Trace, Via
from temper_placer.deterministic.stages import TrackDeduplicationStage
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
                    start=(i * 0.25, 0.0),
                    end=((i + 1) * 0.25, 0.0),
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

    def test_dedup_via_before_duplicates_remaps_indices(self):
        """A Via before duplicate traces must not corrupt the dedup index.

        The kernel's kept indices reference the marshalled Trace list, NOT
        the state.routes positions; the shim remaps them back. A Via (a
        non-Trace route entry) anywhere among routes must not shift the
        mapping — the pre-migration dedup kept the FIRST of the two
        duplicate traces (the near-duplicate `b` rounds to the same key)
        plus the Via. `BoardState.routes` is a `frozenset` field (the owned
        `RouteSet` is a `HashSet`, order-losing by design — see
        temper-data-model/src/collections.rs's `set_newtype!` doc), so both
        orderings below marshal to the same set; the loop is retained as a
        regression check that dedup is insertion-order-independent either way.
        """
        via = Via(position=(0.0, 0.0), drill=0.3, width=0.6, net="GND")
        a = Trace(start=(0.0, 0.0), end=(10.0, 0.0), width=0.2, layer="B.Cu", net="N")
        b = Trace(start=(0.0, 0.02), end=(10.0, 0.0), width=0.2, layer="B.Cu", net="N")

        for routes in ([via, a, b], [a, via, b]):
            state = BoardState(routes=frozenset(routes))
            result = TrackDeduplicationStage(tolerance_mm=0.05).run(state)
            assert result.routes == frozenset({via, a}), (
                f"order {[type(r).__name__ for r in routes]}: got "
                f"{sorted(repr(r) for r in result.routes)}"
            )

    def test_dedup_keeps_first_trace_deterministically_across_hash_seeds(self):
        """The "first of two duplicates" tie-break must not depend on
        `PYTHONHASHSEED`.

        `BoardState.routes` is a `frozenset[Trace]`; `Trace.__hash__` mixes
        the `net`/`layer` string fields, so CPython's per-process string-hash
        randomization makes raw frozenset iteration order vary run-to-run.
        `TrackDeduplicationStage` (and `deduplicate_traces_py`) resolve a
        near-duplicate collision by keeping the FIRST element in the order
        they read `routes` -- so without a canonical, content-derived order
        imposed before that read, WHICH of two near-duplicate traces
        survives is process-dependent, even though this process's own run is
        internally consistent.

        This reproduces the mechanism with Trace-only input (no Via) so it
        does not also depend on the separate non-Trace/Via `routes`
        marshalling gap tracked elsewhere (PR #1136) -- this test's subject
        is purely the tie-break's determinism, not that gap.

        `a` is defined first and must always be the survivor: this process
        may run under any `PYTHONHASHSEED` (this test does not fix one), so
        this assertion is the actual proof the tie-break no longer depends
        on it -- run this test (or the suite) under several
        `PYTHONHASHSEED` values to confirm.
        """
        a = Trace(start=(0.0, 0.0), end=(10.0, 0.0), width=0.2, layer="B.Cu", net="N")
        b = Trace(start=(0.0, 0.02), end=(10.0, 0.0), width=0.2, layer="B.Cu", net="N")

        state = BoardState(routes=frozenset([a, b]))
        result = TrackDeduplicationStage(tolerance_mm=0.05).run(state)

        assert result.routes == frozenset({a}), (
            f"expected the first-defined trace 'a' to survive, got "
            f"{sorted(repr(r) for r in result.routes)}"
        )
