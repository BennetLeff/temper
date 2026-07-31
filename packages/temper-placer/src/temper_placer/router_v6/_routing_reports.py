"""Router V6: routing outcome and decline-reason reports.

The data types describing what a routing run produced and, when a net was
declined, why it was declined. This is deliberately dependency-light: it
imports geometry types for annotations and nothing from the A* search core,
so the decline-reason contract can be read, tested, and ported on its own.

Split out of _astar_reconstruct.py, which had grown past its size cap.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from temper_placer.router_v6.astar_core import RoutePath, RoutePath3D
from temper_placer.router_v6.tree_route_geometry import TreeRouteGeometry

# U1 (docs/plans/2026-07-28-001-feat-provable-safety-place-and-route-plan.md):
# decline-reason attribution. Today, exactly one mechanism in this module
# earns a specific, non-fabricated rule id: the forced-segment fail-closed
# gate (``_allow_forced_segments`` is unconditionally ``False``, and
# ``execute_terminal_tree`` -- see terminal_tree_execution.py -- always
# passes ``allow_forced_segments=False`` too). Every other failure path
# (rip-up budget exhaustion, a channel path with too few waypoints to
# search at all, or an unhandled exception during a discharge attempt) has
# no rule-level attribution today, so it honestly reports
# ``attribution_gap=True`` on ``RoutingFailureReport`` rather than
# inventing one. See that dataclass's docstring and
# docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md
# for the candor discipline this follows.
RULE_ID_FORCED_SEGMENT_FAIL_CLOSED = "forced_segment_fail_closed"
FAILURE_REASON_PROVER_ERROR = "prover_error"


def _forced_segment_decline(
    blockers: list[str],
    region: tuple[float, float] | None,
) -> tuple[bool, str, list[str], tuple[float, float] | None, str | None]:
    """Build the standard decline tuple for a forced-segment fail-closed refusal.

    Every call site that reaches this shares the same reason and rule_id;
    centralizing the pairing here means a future change to either only
    needs to happen once, not in lockstep across every return site.
    """
    return False, "no_path", blockers, region, RULE_ID_FORCED_SEGMENT_FAIL_CLOSED


@dataclass
class RoutingFailureReport:
    """Detailed failure report for a net that failed to route.

    ``rule_id``/``domain`` are U1's decline-reason attribution, following
    the UNSAT-core "because"-field candor pattern
    (docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md):
    never fabricate a rule attribution. ``attribution_gap`` is a computed
    property (``rule_id is None``) rather than a separately-threaded field
    -- there is exactly one source of truth for "was a specific rule
    named," so it cannot drift out of sync with ``rule_id`` the way a
    parallel stored field could.
    """

    net_name: str
    # "congestion", "no_path", "rip_up_limit", "no_channel", "prover_error",
    # "no_routable_layer" (b39b382d: a shared pad layer exists but the router
    # was given no occupancy grid for it -- a router-configuration gap, which
    # is why it carries no rule_id).
    failure_reason: str
    blocking_nets: list[str]  # Which nets are blocking
    attempted_ripups: int
    congestion_region: tuple[float, float] | None  # Approximate (x, y) of stuck location
    pin_count: int = 0  # Number of pins in the net
    rule_id: str | None = None  # Specific rule/mechanism name, e.g. RULE_ID_FORCED_SEGMENT_FAIL_CLOSED
    domain: str | None = None  # net_classification.classify_net_type(net_name) result

    @property
    def attribution_gap(self) -> bool:
        """True unless a specific rule_id is named. Never set directly."""
        return self.rule_id is None


@dataclass(frozen=True)
class TreeRoutingFailure:
    """Honest terminal-level outcome for a partially attempted route tree."""

    unresolved_terminal: tuple[float, float]
    completed_edge_count: int
    reason: str


@dataclass
class PathfindingResult:
    """Result of A* pathfinding."""

    routed_paths: dict[str, RoutePath | RoutePath3D]  # net_name -> RoutePath
    failed_nets: list[str]  # Nets that failed to route
    failure_reports: dict[str, RoutingFailureReport] | None = None  # Detailed failures
    net_ids: dict[str, int] | None = None  # Map of net_name -> net_id used in grid
    per_path_latency_ms: dict[str, float] | None = None  # Per-net routing latency
    coarse_to_fine_fallbacks: int = 0  # Number of times coarse-to-fine fell back to unrestricted A*
    tree_failures: dict[str, TreeRoutingFailure] = field(default_factory=dict)
    partial_paths: dict[str, RoutePath | RoutePath3D] = field(default_factory=dict)
    tree_routes: dict[str, TreeRouteGeometry] = field(default_factory=dict)
    partial_tree_routes: dict[str, TreeRouteGeometry] = field(default_factory=dict)

    @property
    def success_count(self) -> int:
        """Number of successfully routed nets."""
        return len(self.routed_paths) + len(self.tree_routes)

    @property
    def failure_count(self) -> int:
        """Number of failed nets."""
        return len(self.failed_nets)

    @property
    def completion_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def total_forced_segments(self) -> int:
        """Total number of forced segments across all routes.

        Always 0 as of docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md:
        no route with forced_segment_count > 0 reaches routed_paths anymore
        (every net class fails closed instead). Left in place rather than
        removed -- deleting it is a larger API-surface change tracked as
        separate follow-up work, not part of that plan.
        """
        return sum(path.forced_segment_count for path in self.routed_paths.values())

    def get_path(self, net_name: str) -> RoutePath | RoutePath3D | None:
        """Get routed path for a specific net."""
        return self.routed_paths.get(net_name)

    def print_failure_analysis(self) -> None:
        """Print a diagnostic summary of routing failures."""
        if not self.failure_reports:
            print("No detailed failure reports available.")
            return

        print(f"\n{'=' * 60}")
        print(f"ROUTING FAILURE ANALYSIS ({len(self.failed_nets)} failures)")
        print(f"{'=' * 60}")

        reasons: dict[str, int] = {}
        blocking_counts: dict[str, int] = {}

        for report in self.failure_reports.values():
            reasons[report.failure_reason] = reasons.get(report.failure_reason, 0) + 1
            for blocker in report.blocking_nets:
                blocking_counts[blocker] = blocking_counts.get(blocker, 0) + 1

        print("\n1. FAILURE REASONS:")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"   {reason}: {count} nets")

        print("\n2. TOP BLOCKING NETS (most frequently blocking others):")
        for net, count in sorted(blocking_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"   {net}: blocked {count} other nets")

        print("\n3. INDIVIDUAL FAILURES:")
        for report in self.failure_reports.values():
            region = (
                f"({report.congestion_region[0]:.1f}, {report.congestion_region[1]:.1f})"
                if report.congestion_region
                else "N/A"
            )
            print(f"   {report.net_name} ({report.pin_count} pins): {report.failure_reason}")
            print(f"      Region: {region}, Ripups: {report.attempted_ripups}")
            if report.blocking_nets:
                print(f"      Blocked by: {', '.join(report.blocking_nets[:5])}")
        print()
