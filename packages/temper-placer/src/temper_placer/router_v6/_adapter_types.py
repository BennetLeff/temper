"""Types and protocols used by the router_v6 adapter."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "_AdapterRoutePath",
    "_NetLike",
    "CongestionRegion",
    "DrcViolation",
    "ParsedPcbLike",
    "RoutingResult",
]


@runtime_checkable
class _NetLike(Protocol):
    """Minimal shape ``route_pcb`` needs from each entry of ``parsed.nets``."""

    name: str


@runtime_checkable
class ParsedPcbLike(Protocol):
    """The contract ``route_pcb`` actually depends on for its ``parsed`` argument.

    ``nets`` matters even though many callers omit it: without it,
    per-net layer-constraint resolution (``layer_assignments_from_netclass``,
    the netclass-SSOT-driven layer assignment) silently no-ops -- every net
    stays on its default layer and DesignRules' ``layer`` field is never
    consulted, with no error or warning. A caller that only cares about
    routing behavior unrelated to layer assignment can still omit ``nets``
    (route_pcb falls back gracefully via getattr), but production-quality
    measurement call sites must supply it or their results silently don't
    reflect real multi-layer routing. See
    docs/solutions/logic-errors/parsed-stub-missing-nets-silently-disables-layer-constraints-2026-07-22.md.
    """

    source_path: Path | str
    nets: Sequence[_NetLike]


@dataclass
class DrcViolation:
    """DRC violation from routing or manufacturing check.

    Attributes:
        net_name: Net name associated with the violation.
        message: Human-readable description.
        location: (x, y) position of the violation in mm.
        comp_a: First component ref (for separation violations).
        comp_b: Second component ref (for separation violations).
        required_mm: Required clearance distance.
        components: Component refs involved.
    """

    net_name: str = ""
    message: str = ""
    location: tuple[float, float] = (0.0, 0.0)
    comp_a: str = ""
    comp_b: str = ""
    required_mm: float = 6.0
    components: list[str] = field(default_factory=list)
    count: int = 0
    type: str = "unknown"


@dataclass
class CongestionRegion:
    """Bottleneck congestion region between components.

    Attributes:
        net_name: Net affected by congestion.
        comp_a: First component ref.
        comp_b: Second component ref.
        current_distance_mm: Current gap between components.
        positions: (pos_a, pos_b) positions in mm.
        bbox: Optional bounding box (x_min, y_min, x_max, y_max).
    """

    net_name: str = ""
    comp_a: str = ""
    comp_b: str = ""
    current_distance_mm: float = 0.0
    positions: tuple[tuple[float, float], tuple[float, float]] = ((0.0, 0.0), (0.0, 0.0))
    bbox: tuple[float, float, float, float] | None = None


@dataclass
class RoutingResult:
    """Result from route_pcb call.

    Attributes:
        completion_rate: Fraction of nets successfully routed (0.0 to 1.0).
        unrouted_nets: List of net names that failed to route.
        drc_violations: List of DrcViolation details from per-net reports
            and optional manufacturing report.
        congestion_regions: List of CongestionRegion details from
            bottleneck geometry analysis.
    """

    completion_rate: float = 0.0
    unrouted_nets: list[str] = field(default_factory=list)
    drc_violations: list[DrcViolation] = field(default_factory=list)
    congestion_regions: list[CongestionRegion] = field(default_factory=list)
    routed_pcb_content: str | None = None
    enable_zone_pours: bool = False
    connectivity: dict[str, Any] | None = None
    # Always [] as of docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md:
    # no net class produces a forced segment anymore (all fail closed).
    # Left in place -- removing it is a larger API-surface change tracked
    # as separate follow-up work, not part of that plan.
    forced_segment_nets: list[str] = field(default_factory=list)


@dataclass
class _AdapterRoutePath:
    """RoutePath-compatible result for consumer compatibility."""

    net: str
    cells: list[Any] = field(default_factory=list)
    length: float = 0.0
    via_count: int = 0
    success: bool = False
    cell_size: float = 0.2
    difficulty: float = 0.0
    cell_difficulties: list[float] = field(default_factory=list)
    failure_reason: str | None = None
    smooth_points: list[Any] = field(default_factory=list)
    trace_width: float = 0.2
    via_diameter: float = 0.6
    via_drill: float = 0.3
    explicit_vias: list[Any] = field(default_factory=list)
