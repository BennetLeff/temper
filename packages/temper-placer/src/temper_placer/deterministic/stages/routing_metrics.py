"""Routing metrics collection for benchmarking and debugging.

This module provides dataclasses for collecting detailed routing statistics
that help identify bottlenecks and measure improvement.
"""

import json
from dataclasses import dataclass, field


@dataclass
class SegmentMetrics:
    """Metrics for a single routing segment (pin-to-pin connection)."""

    net_name: str
    segment_idx: int  # Which MST edge (0, 1, 2...)
    start_pin: str  # e.g., "U1.5"
    end_pin: str  # e.g., "R3.1"
    distance_mm: float  # Euclidean distance
    distance_cells: int  # Grid cells

    # Outcome
    success: bool
    method: str  # "single_layer", "multi_layer", "failed"

    # Search stats
    iterations_used: int
    iterations_limit: int
    timeout: bool  # Hit iteration limit?

    # Result details (if successful)
    path_length_mm: float = 0.0
    via_count: int = 0
    layers_used: list[str] = field(default_factory=list)


@dataclass
class NetMetrics:
    """Aggregated metrics for a complete net."""

    net_name: str
    net_class: str
    pin_count: int

    # Segment breakdown
    segments_total: int
    segments_completed: int
    segments_failed: int
    segments_timeout: int  # Failed due to iteration limit

    # Totals
    total_iterations: int
    total_path_length_mm: float
    total_vias: int

    # Timing
    elapsed_seconds: float

    # Detailed segment data
    segment_details: list[SegmentMetrics] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        if self.segments_total == 0:
            return 1.0
        return self.segments_completed / self.segments_total

    @property
    def is_fully_routed(self) -> bool:
        return self.segments_completed == self.segments_total


@dataclass
class RoutingMetrics:
    """Complete routing metrics for a board."""

    # Summary
    nets_total: int = 0
    nets_fully_routed: int = 0
    nets_partially_routed: int = 0
    nets_failed: int = 0
    nets_plane: int = 0  # Skipped (power/ground planes)

    # Segment totals
    segments_total: int = 0
    segments_completed: int = 0
    segments_failed: int = 0
    segments_timeout: int = 0

    # Search stats
    total_iterations: int = 0
    avg_iterations_per_segment: float = 0.0
    timeout_rate: float = 0.0

    # Output stats
    total_traces: int = 0
    total_vias: int = 0
    total_trace_length_mm: float = 0.0

    # Timing
    total_elapsed_seconds: float = 0.0

    # Per-net details
    net_metrics: dict[str, NetMetrics] = field(default_factory=dict)

    # Failure analysis
    failed_nets: list[str] = field(default_factory=list)
    timeout_nets: list[str] = field(default_factory=list)

    def add_net(self, net: NetMetrics) -> None:
        """Add a net's metrics and update totals."""
        self.net_metrics[net.net_name] = net

        self.nets_total += 1
        if net.is_fully_routed:
            self.nets_fully_routed += 1
        elif net.segments_completed > 0:
            self.nets_partially_routed += 1
        else:
            self.nets_failed += 1
            self.failed_nets.append(net.net_name)

        if net.segments_timeout > 0:
            self.timeout_nets.append(net.net_name)

        self.segments_total += net.segments_total
        self.segments_completed += net.segments_completed
        self.segments_failed += net.segments_failed
        self.segments_timeout += net.segments_timeout

        self.total_iterations += net.total_iterations
        self.total_vias += net.total_vias
        self.total_trace_length_mm += net.total_path_length_mm
        self.total_elapsed_seconds += net.elapsed_seconds

    def finalize(self) -> None:
        """Compute derived metrics after all nets added."""
        if self.segments_total > 0:
            self.avg_iterations_per_segment = self.total_iterations / self.segments_total
            self.timeout_rate = self.segments_timeout / self.segments_total

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "summary": {
                "nets_total": self.nets_total,
                "nets_fully_routed": self.nets_fully_routed,
                "nets_partially_routed": self.nets_partially_routed,
                "nets_failed": self.nets_failed,
                "nets_plane": self.nets_plane,
                "net_completion_rate": (self.nets_fully_routed / max(self.nets_total, 1)),
            },
            "segments": {
                "total": self.segments_total,
                "completed": self.segments_completed,
                "failed": self.segments_failed,
                "timeout": self.segments_timeout,
                "completion_rate": (self.segments_completed / max(self.segments_total, 1)),
                "timeout_rate": self.timeout_rate,
            },
            "search": {
                "total_iterations": self.total_iterations,
                "avg_iterations_per_segment": round(self.avg_iterations_per_segment, 1),
            },
            "output": {
                "total_traces": self.total_traces,
                "total_vias": self.total_vias,
                "total_trace_length_mm": round(self.total_trace_length_mm, 2),
            },
            "timing": {
                "total_elapsed_seconds": round(self.total_elapsed_seconds, 2),
            },
            "failures": {
                "failed_nets": self.failed_nets,
                "timeout_nets": self.timeout_nets,
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def print_summary(self) -> None:
        """Print human-readable summary."""
        print("\n" + "=" * 60)
        print("ROUTING METRICS SUMMARY")
        print("=" * 60)

        print("\nNets:")
        print(f"  Total:           {self.nets_total}")
        print(
            f"  Fully routed:    {self.nets_fully_routed} ({self.nets_fully_routed / max(self.nets_total, 1):.1%})"
        )
        print(f"  Partial:         {self.nets_partially_routed}")
        print(f"  Failed:          {self.nets_failed}")
        print(f"  Plane (skipped): {self.nets_plane}")

        print("\nSegments:")
        print(f"  Total:           {self.segments_total}")
        print(
            f"  Completed:       {self.segments_completed} ({self.segments_completed / max(self.segments_total, 1):.1%})"
        )
        print(f"  Failed:          {self.segments_failed}")
        print(f"  Timeout:         {self.segments_timeout} ({self.timeout_rate:.1%})")

        print("\nSearch:")
        print(f"  Total iterations:    {self.total_iterations:,}")
        print(f"  Avg per segment:     {self.avg_iterations_per_segment:.0f}")

        print("\nOutput:")
        print(f"  Traces:          {self.total_traces}")
        print(f"  Vias:            {self.total_vias}")
        print(f"  Trace length:    {self.total_trace_length_mm:.1f} mm")

        print("\nTiming:")
        print(f"  Total:           {self.total_elapsed_seconds:.1f}s")

        if self.failed_nets:
            print(f"\nFailed nets ({len(self.failed_nets)}):")
            for net in self.failed_nets[:10]:
                print(f"  - {net}")
            if len(self.failed_nets) > 10:
                print(f"  ... and {len(self.failed_nets) - 10} more")
