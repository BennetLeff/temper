"""
Instrumentation utilities for debugging pipeline trace/route loss.

Provides wrappers to track trace counts through pipeline stages.
"""

import logging
from dataclasses import dataclass

from temper_placer.deterministic.state import BoardState

logger = logging.getLogger(__name__)


@dataclass
class TraceLogEntry:
    """Log entry for trace counts at a pipeline stage."""

    stage_name: str
    route_counts: dict[str, int]  # net_name -> count
    routes_lost: dict[str, int]  # net_name -> count (negative = loss)
    routes_gained: dict[str, int]  # net_name -> count (positive = gain)


class InstrumentedStage:
    """
    Wrapper around a pipeline stage that logs route counts before/after execution.

    Usage:
        original_stage = ClearanceGridStage(...)
        instrumented = InstrumentedStage(original_stage, track_nets=['USB_D+', 'USB_D-'])
        state = instrumented.run(state)
    """

    def __init__(self, inner_stage, track_nets: list[str] | None = None):
        """
        Initialize instrumented stage.

        Args:
            inner_stage: The actual stage to wrap
            track_nets: List of net names to track (None = track all)
        """
        self.inner_stage = inner_stage
        self.track_nets = set(track_nets) if track_nets else None
        self.stage_name = inner_stage.__class__.__name__

    def _count_routes(self, state: BoardState) -> dict[str, int]:
        """Count routes by net name."""
        counts: dict[str, int] = {}
        for route in state.routes:
            # Route objects should have a net_name attribute
            net_name = getattr(route, "net_name", None)
            if net_name and (self.track_nets is None or net_name in self.track_nets):
                counts[net_name] = counts.get(net_name, 0) + 1
        return counts

    def run(self, state: BoardState, *args, **kwargs) -> BoardState:
        """Run inner stage with before/after route counting."""
        # Count before
        counts_before = self._count_routes(state)
        logger.info(f"[{self.stage_name}] BEFORE:")
        for net_name, count in sorted(counts_before.items()):
            logger.info(f"  {net_name}: {count} routes")

        # Run actual stage
        result = self.inner_stage.run(state, *args, **kwargs)

        # Count after
        counts_after = self._count_routes(result)
        logger.info(f"[{self.stage_name}] AFTER:")

        # Calculate deltas
        all_nets = set(counts_before.keys()) | set(counts_after.keys())
        for net_name in sorted(all_nets):
            before = counts_before.get(net_name, 0)
            after = counts_after.get(net_name, 0)
            delta = after - before

            if delta < 0:
                logger.warning(f"  {net_name}: {after} routes (LOST {-delta})")
            elif delta > 0:
                logger.info(f"  {net_name}: {after} routes (GAINED {delta})")
            else:
                logger.info(f"  {net_name}: {after} routes (no change)")

        return result


def instrument_pipeline(pipeline, track_nets: list[str] | None = None):
    """
    Wrap all stages in a pipeline with instrumentation.

    Args:
        pipeline: Pipeline object with .stages attribute
        track_nets: List of net names to track (None = track all)

    Returns:
        New pipeline with instrumented stages
    """
    instrumented_stages = [
        InstrumentedStage(stage, track_nets=track_nets) for stage in pipeline.stages
    ]

    # Create new pipeline with instrumented stages
    instrumented_pipeline = type(pipeline)()
    instrumented_pipeline.stages = instrumented_stages
    return instrumented_pipeline


def run_with_trace_log(
    pipeline, state: BoardState, track_nets: list[str] | None = None
) -> tuple[BoardState, list[TraceLogEntry]]:
    """
    Run pipeline and collect detailed trace log.

    Args:
        pipeline: Pipeline to run
        state: Initial board state
        track_nets: Nets to track (None = all)

    Returns:
        (final_state, trace_log)
    """
    trace_log = []
    current_state = state

    for stage in pipeline.stages:
        stage_name = stage.__class__.__name__

        # Count before
        counts_before: dict[str, int] = {}
        for route in current_state.routes:
            net_name = getattr(route, "net_name", None)
            if net_name and (track_nets is None or net_name in track_nets):
                counts_before[net_name] = counts_before.get(net_name, 0) + 1

        # Run stage
        current_state = stage.run(current_state)

        # Count after
        counts_after: dict[str, int] = {}
        for route in current_state.routes:
            net_name = getattr(route, "net_name", None)
            if net_name and (track_nets is None or net_name in track_nets):
                counts_after[net_name] = counts_after.get(net_name, 0) + 1

        # Calculate deltas
        all_nets = set(counts_before.keys()) | set(counts_after.keys())
        routes_lost = {}
        routes_gained = {}

        for net_name in all_nets:
            before = counts_before.get(net_name, 0)
            after = counts_after.get(net_name, 0)
            delta = after - before

            if delta < 0:
                routes_lost[net_name] = -delta
            elif delta > 0:
                routes_gained[net_name] = delta

        # Record entry
        entry = TraceLogEntry(
            stage_name=stage_name,
            route_counts=counts_after,
            routes_lost=routes_lost,
            routes_gained=routes_gained,
        )
        trace_log.append(entry)

    return current_state, trace_log
