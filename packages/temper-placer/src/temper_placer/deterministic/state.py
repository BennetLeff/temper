from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:

    from temper_placer.core.board import Board
    from temper_placer.core.design_rules import DesignRules
    from temper_placer.core.loop import LoopCollection
    from temper_placer.core.netlist import Netlist
    from temper_placer.router_v6.bottleneck_analysis import BottleneckAnalysis
    from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
    from temper_placer.router_v6.channel_widths import ChannelWidths
    from temper_placer.router_v6.constraint_model import ConstraintModel
    from temper_placer.router_v6.constraints_drc_oracle import DRCOracle, Violation
    from temper_placer.router_v6.layer_capacity import LayerCapacity
    from temper_placer.router_v6.occupancy_grid import OccupancyGrid
    from temper_placer.router_v6.routing_demand import RoutingDemand
    from temper_placer.router_v6.routing_space import RoutingSpace
    from temper_placer.router_v6.topology_extraction import TopologyGraph
    from temper_placer.router_v6.topology_solver import TopologicalSolution

    from .stages.clearance_grid import ClearanceGrid
    from .stages.connectivity_validation import ConnectivityViolation
    from .stages.placement_validation import PlacementViolation


@dataclass(frozen=True)
class BoardState:
    """Immutable snapshot of board at any pipeline stage."""

    board: Board | None = None
    netlist: Netlist | None = None
    loops: LoopCollection | None = None
    grid: ClearanceGrid | None = None
    drc_oracle: DRCOracle | None = None
    drc_violations: tuple[Violation, ...] | None = None
    # U3: optional design rules.  Set by PhasedComponentAssignmentStage so
    # stage validators can check creepage / HV invariants without the
    # pipeline having to thread the SSOT through every hook point.
    # Default None preserves the existing schema for older stages.
    design_rules: DesignRules | None = None
    connectivity_violations: tuple[ConnectivityViolation, ...] | None = None
    placement_violations: tuple[PlacementViolation, ...] | None = None
    placements: frozenset = frozenset()
    # U3: set of grid slots reserved by the placer (footprint + HV rings).
    # Set by PhasedComponentAssignmentStage so the post-stage DRC fence
    # validator can check the actual reservation set rather than
    # re-deriving it from placements.
    used_slots: frozenset = frozenset()
    # Optional configuration block (parsed PlacementConstraints dict).
    # Populated by ConfigAttachStage at the head of the pipeline so downstream
    # stages (HvLvPartitionStage, etc.) can read their own block from
    # ``state.config`` without the orchestrator threading the raw config
    # through every hook point. Default None preserves older pipeline
    # callers that construct BoardState() with no config.
    config: Any = None
    # feat/hv-lv-guard-strip: per-component HV/LV domain assignment (set
    # by HvLvPartitionStage). FrozenSet of (component_ref, domain_name)
    # tuples where domain_name is one of {"HV_edge", "LV_interior", "iso"}.
    component_domain_map: frozenset = frozenset()
    # feat/hv-lv-guard-strip: tuple of corridor polygons between HV_edge
    # and LV_interior domains. Used by the placer to keep component slots
    # out of routing channels.
    routing_corridors: tuple = ()
    # feat/hv-lv-guard-strip: tuple of (domain_name, polygon) pairs for
    # the computed HV/LV regions. The placer's domain filter consults
    # this map when assigning a slot to a component.
    domain_regions: tuple = ()
    routes: frozenset = frozenset()
    vias: frozenset = frozenset()
    violations: frozenset = frozenset()
    net_order: tuple[str, ...] = field(default_factory=tuple)
    zones: frozenset = frozenset()  # Set of Zone objects
    component_zone_map: frozenset = frozenset()  # Set of (component_ref, zone_name) tuples
    zone_slots: frozenset = (
        frozenset()
    )  # Set of (zone_name, tuple_of_slots) - each zone maps to tuple of (x,y) positions
    layer_assignments: frozenset = frozenset()  # Set of LayerAssignment objects (net_name, layer)
    # EXP-5: Route locking - nets that have been successfully routed and should be preserved
    locked_routes: frozenset[str] = field(default_factory=frozenset)
    # Router V6 Stage 2 channel-analysis fields
    obstacle_maps: dict[str, Any] | None = None
    routing_spaces: dict[str, RoutingSpace] | None = None
    channel_skeletons: dict[str, ChannelSkeleton] | None = None
    channel_widths: dict[str, ChannelWidths] | None = None
    occupancy_grids: dict[str, OccupancyGrid] | None = None
    layer_capacities: dict[str, LayerCapacity] | None = None
    routing_demand: RoutingDemand | None = None
    bottleneck_analysis: BottleneckAnalysis | None = None
    # Bridge fields for Stage2Orchestrator (pending protocol unification)
    _parsed_pcb: Any | None = None
    _escape_vias: Any | None = None
    # Router V6 Stage 4 A* pathfinding fields
    parsed_grids: dict[str, Any] | None = None
    net_route_order: list[str] | None = None
    per_net_results: dict[str, Any] | None = None
    tht_locations: frozenset = frozenset()
    pad_centers_per_net: dict[str, Any] | None = None
    net_ids: dict[str, int] | None = None
    failed_nets: list[str] | None = None
    failure_reports: dict[str, Any] | None = None
    pathfinding_result: Any | None = None
    channel_mapping: Any = None
    escape_vias_map: dict[str, Any] | None = None
    enable_theta_star: bool = False
    enable_lazy_theta_star: bool = False
    # U7 / R11: PathFinder-style history cost.  0.0 disables
    # (no detour behavior).  Non-zero values push later nets
    # around already-routed channels.  Empirically 0.0 closes
    # more nets than 0.1 or 1.0 on temper.kicad_pcb because
    # the hard signal nets need direct paths.
    congestion_weight: float = 0.0
    # Router V6 Stage 3 topological-routing fields
    constraint_model: ConstraintModel | None = None
    sat_variable_map: dict[str, Any] | None = None
    topological_solution: TopologicalSolution | None = None
    assignment_valid: bool | None = None
    topology_graph: TopologyGraph | None = None
    # Router V6 Stage 4 A* pathfinding fields
    parsed_grids: dict[str, Any] | None = None
    net_route_order: list[str] | None = None
    per_net_results: dict[str, Any] | None = None
    # @req(2026-06-23-007, R2): Per-(component, lv_pin, hv_pin) clearance
    # reclaim (mm) emitted by ZoneAwareSlotGenerationStage when an isolation
    # cutout is present. The DRC oracle (U3) reads this dict to apply a
    # reduced clearance inside the slot's reclaimed band. Optional so older
    # pipelines that don't run the zone-aware stage still type-check.
    reclaim_by_pin_pair: dict[tuple[str, str, str], float] | None = None

    def with_locked_route(self, net_name: str) -> BoardState:
        """Return new state with the given net marked as locked.

        Locked routes are preserved across feedback iterations and not re-routed.
        This is used by EXP-5 to prevent zone expansion from breaking working routes.

        Args:
            net_name: Name of the net to lock

        Returns:
            New BoardState with the net added to locked_routes
        """
        from dataclasses import replace

        new_locked = frozenset(self.locked_routes | {net_name})
        return replace(self, locked_routes=new_locked)

    def with_locked_routes(self, net_names: set) -> BoardState:
        """Return new state with multiple nets marked as locked.

        Args:
            net_names: Set of net names to lock

        Returns:
            New BoardState with the nets added to locked_routes
        """
        from dataclasses import replace

        new_locked = frozenset(self.locked_routes | net_names)
        return replace(self, locked_routes=new_locked)

    def is_route_locked(self, net_name: str) -> bool:
        """Check if a route is locked and should not be re-routed.

        Args:
            net_name: Name of the net to check

        Returns:
            True if the route is locked
        """
        return net_name in self.locked_routes

    def with_config(self, config: Mapping[str, Any] | None) -> BoardState:
        """Return new state with ``config`` populated for stage-local config lookups.

        Used by the pipeline factory (and the feedback orchestrator)
        to attach the parsed configuration to a state so stages such as
        ``HvLvPartitionStage`` can read their own block from
        ``state.config``. Preserves every other field; safe to call before
        any stages run.

        Args:
            config: Raw config dict (typically parsed YAML) or None.

        Returns:
            New BoardState with ``config`` set.
        """
        from dataclasses import replace

        return replace(self, config=config)
