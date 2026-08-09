"""Topological initialization heuristic.

This heuristic generates initial placements from topological relationships
(zone assignments, adjacency clusters) using force-directed refinement.

It runs at INITIALIZATION priority (before other heuristics) to provide
a good starting point for the placement optimization.

Wave 4: the feasibility arithmetic of ``_check_feasibility`` (per-component
fit decision over both orientations, the two compensated ``sum()`` area
totals) is implemented in Rust in the ``temper-geometry`` crate
(``temper_geometry.feasibility_check``); see
``packages/temper-geometry/src/heuristics.rs``. Graph building,
zone assignment and message formatting stay Python. Pinned oracle:
``packages/temper-placer/tests/heuristics/_topological_init_py_oracle.py``;
differential:
``packages/temper-placer/tests/heuristics/test_heuristics_rust_differential.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from temper_placer.heuristics.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)
from temper_placer.topological.graph import TopologicalGraph
from temper_placer.topological.initial_placement import (
    PlacementError,
    generate_initial_placement,
)
from temper_placer.topological.zone_solver import ZoneAssignment


@dataclass
class FeasibilityResult:
    """Result of feasibility checking.

    Attributes:
        is_feasible: Whether placement is feasible
        message: Human-readable description of result
        conflicts: List of specific conflict descriptions
    """

    is_feasible: bool
    message: str = ""
    conflicts: list[str] = field(default_factory=list)


class TopologicalInitializationHeuristic(Heuristic):
    """Heuristic that generates initial placements from topological analysis.

    This heuristic:
    1. Builds a topological graph from PCL constraints
    2. Propagates constraints to infer relationships
    3. Assigns components to zones
    4. Generates initial positions with force refinement

    Attributes:
        _force_iterations: Number of force refinement iterations
        _backend: Computation backend ("numpy" or "jax")
    """

    def __init__(
        self,
        force_iterations: int = 100,
        backend: str = "numpy",
    ) -> None:
        """Initialize the heuristic.

        Args:
            force_iterations: Number of force refinement iterations
            backend: Computation backend ("numpy" or "jax")

        Raises:
            ValueError: If backend is not "numpy" or "jax"
        """
        if backend not in ("numpy", "jax"):
            raise ValueError(f"Invalid backend: {backend}. Must be 'numpy' or 'jax'")

        self._force_iterations = force_iterations
        self._backend = backend

    @property
    def name(self) -> str:
        """Unique name for this heuristic."""
        return "topological_initialization"

    @property
    def priority(self) -> HeuristicPriority:
        """Priority level - runs before other heuristics."""
        return HeuristicPriority.INITIALIZATION

    @property
    def description(self) -> str:
        """Human-readable description."""
        return (
            "Generates initial placements from topological relationships "
            "(zone assignments, adjacency clusters) using force-directed refinement."
        )

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Apply topological initialization to generate placements.

        Args:
            context: PlacementContext with board, netlist, constraints

        Returns:
            HeuristicResult with generated placements
        """
        # Get unplaced, non-fixed components, in netlist order.
        # This must be an ordered sequence, not a set: it seeds the zone
        # assignment's insertion order, which becomes the cluster order, which
        # selects each cluster's sub-region via `cluster_index`. A set here makes
        # those sub-regions depend on PYTHONHASHSEED.
        unfixed_components = [c for c in context.netlist.components if not c.fixed]
        unplaced_refs = [
            c.ref for c in unfixed_components if c.ref not in context.current_placements
        ]

        if not unplaced_refs:
            return HeuristicResult(
                success=True,
                message="No components to place",
            )

        # Fail-fast feasibility check
        feasibility = self._check_feasibility(context, unplaced_refs)
        if not feasibility.is_feasible:
            return HeuristicResult(
                success=False,
                message=feasibility.message,
                conflicts=feasibility.conflicts,
            )

        # Build topological graph from constraints/netlist
        graph = self._build_graph(context, unplaced_refs)

        # Build zone assignment
        zone_assignment = self._build_zone_assignment(context, graph, unplaced_refs)

        # Get component sizes
        unplaced_set = set(unplaced_refs)
        component_sizes = {
            c.ref: (c.width, c.height) for c in context.netlist.components if c.ref in unplaced_set
        }

        # Get zones from board
        zones = context.board.zones

        # Handle case with no zones - use board bounds
        board_bounds = None
        if not zones:
            board_bounds = (
                context.board.origin[0],
                context.board.origin[1],
                context.board.origin[0] + context.board.width,
                context.board.origin[1] + context.board.height,
            )
            # Create virtual zone assignment to _BOARD_
            zone_assignment = ZoneAssignment(
                assignments=dict.fromkeys(unplaced_refs, "_BOARD_"),
                unassigned=[],
                conflicts=[],
            )

        try:
            # Generate initial placement
            placement = generate_initial_placement(
                graph=graph,
                zone_assignment=zone_assignment,
                zones=zones,
                component_sizes=component_sizes,
                board_bounds=board_bounds,
                force_iterations=self._force_iterations,
                backend=self._backend,
            )
        except PlacementError as e:
            return HeuristicResult(
                success=False,
                message=str(e),
                conflicts=[str(e)],
            )

        # Convert to HeuristicResult
        placements: dict[str, ComponentPlacement] = {}
        for ref, (x, y) in placement.positions.items():
            placements[ref] = ComponentPlacement(
                ref=ref,
                position=(x, y),
                rotation=placement.rotation_hints.get(ref, 0),
                confidence=0.5,  # Moderate confidence for initial placement
                placed_by=self.name,
            )

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Placed {len(placements)} components using topological initialization",
        )

    def _build_graph(
        self,
        context: PlacementContext,
        component_refs: list[str],
    ) -> TopologicalGraph:
        """Build topological graph from context.

        Uses netlist connectivity to infer adjacency relationships.

        Args:
            context: Placement context
            component_refs: Components to include in graph, in netlist order

        Returns:
            TopologicalGraph with components and constraints
        """
        graph = TopologicalGraph()

        # Add components. Insertion order fixes the graph's node order, which
        # downstream clustering iterates.
        for ref in component_refs:
            graph.add_component(ref)

        ref_set = set(component_refs)

        # Infer adjacency from nets - components sharing a net should be close
        for net in context.netlist.nets:
            # Get component refs from pins
            net_refs = set()
            for pin in net.pins:
                # Pin is a tuple (component_ref, pin_name)
                ref = pin[0]
                if ref in ref_set:
                    net_refs.add(ref)

            # Add adjacency constraints between components on same net
            refs_list = sorted(net_refs)
            for i, ref_a in enumerate(refs_list):
                for ref_b in refs_list[i + 1 :]:
                    # Only add if not already connected (use internal networkx graph)
                    if not graph.graph.has_edge(ref_a, ref_b):
                        graph.add_adjacency(
                            ref_a,
                            ref_b,
                            max_distance=20.0,  # Default adjacency distance
                            constraint_id=f"net_{net.name}_{ref_a}_{ref_b}",
                        )

        return graph

    def _build_zone_assignment(
        self,
        context: PlacementContext,
        _graph: TopologicalGraph,
        component_refs: list[str],
    ) -> ZoneAssignment:
        """Build zone assignment from context.

        Uses board zones and component metadata to assign zones.

        Args:
            context: Placement context
            graph: Topological graph
            component_refs: Components to assign

        Returns:
            ZoneAssignment mapping components to zones
        """
        zones = context.board.zones

        if not zones:
            # No zones defined - all components unassigned
            return ZoneAssignment(
                assignments={},
                unassigned=list(component_refs),
                conflicts=[],
            )

        # Simple assignment: use first zone, or zone that explicitly lists component
        assignments: dict[str, str] = {}
        unassigned: list[str] = []

        for ref in component_refs:
            assigned = False

            # Check if any zone explicitly lists this component
            for zone in zones:
                if ref in zone.components:
                    assignments[ref] = zone.name
                    assigned = True
                    break

            if not assigned:
                # Default to first zone if not explicitly assigned
                if zones:
                    assignments[ref] = zones[0].name
                else:
                    unassigned.append(ref)

        return ZoneAssignment(
            assignments=assignments,
            unassigned=unassigned,
            conflicts=[],
        )

    def _check_feasibility(
        self,
        context: PlacementContext,
        component_refs: list[str],
    ) -> FeasibilityResult:
        """Check if placement is feasible before attempting.

        Performs fail-fast checks:
        1. Any component larger than available zones/board
        2. Total component area exceeds zone area

        Args:
            context: Placement context
            component_refs: Components to place

        Returns:
            FeasibilityResult with is_feasible flag and conflicts
        """
        from temper_geometry import feasibility_check

        conflicts: list[str] = []

        # Get component sizes
        ref_set = set(component_refs)
        component_sizes: dict[str, tuple[float, float]] = {}
        for c in context.netlist.components:
            if c.ref in ref_set:
                component_sizes[c.ref] = (c.width, c.height)

        # Get available placement area (zones or board)
        zones = context.board.zones
        if zones:
            # Calculate zone bounds: list of (x, y, width, height)
            zone_bounds = []
            for zone in zones:
                zx, zy, zw, zh = zone.bounds
                zone_bounds.append((zw, zh))
        else:
            # Use board bounds
            zone_bounds = [(context.board.width, context.board.height)]

        # Apply margin if constraints specify one
        margin = 0.0
        if context.constraints and hasattr(context.constraints, "board_margin_mm"):
            margin = context.constraints.board_margin_mm or 0.0

        # The per-component fit decision (both orientations, margin-eroded
        # zone dims) and the two compensated area totals are the Rust kernel;
        # the netlist/zone extraction above and the message formatting below
        # stay here, so CPython renders every float string.
        fits, total_component_area, total_zone_area = feasibility_check(
            list(component_sizes.values()), zone_bounds, margin
        )

        # Check 1: Is any component larger than all zones?
        for (ref, (cw, ch)), fits_in_any_zone in zip(component_sizes.items(), fits):
            if not fits_in_any_zone:
                conflicts.append(
                    f"Component {ref} ({cw:.1f}x{ch:.1f}mm) is larger than available placement area"
                )

        # Check 2: Total component area vs total zone area
        # Use a packing efficiency estimate (70% is typical for rectangular packing)
        PACKING_EFFICIENCY = 0.7
        if total_component_area > total_zone_area * PACKING_EFFICIENCY:
            conflicts.append(
                f"Total component area ({total_component_area:.1f}mm²) exceeds "
                f"~{PACKING_EFFICIENCY * 100:.0f}% of available zone area ({total_zone_area:.1f}mm²)"
            )

        if conflicts:
            return FeasibilityResult(
                is_feasible=False,
                message=f"Placement infeasible: {len(conflicts)} conflict(s) detected",
                conflicts=conflicts,
            )

        return FeasibilityResult(
            is_feasible=True,
            message="Feasibility check passed",
        )
