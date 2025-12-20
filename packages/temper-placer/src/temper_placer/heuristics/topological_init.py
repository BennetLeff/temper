"""Topological initialization heuristic.

This heuristic generates initial placements from topological relationships
(zone assignments, adjacency clusters) using force-directed refinement.

It runs at INITIALIZATION priority (before other heuristics) to provide
a good starting point for the placement optimization.
"""

from __future__ import annotations

from temper_placer.core.board import Zone
from temper_placer.heuristics.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)
from temper_placer.topological.graph import TopologicalGraph, build_topological_graph
from temper_placer.topological.initial_placement import (
    InitialPlacement,
    PlacementError,
    generate_initial_placement,
)
from temper_placer.topological.propagation import ConstraintPropagator
from temper_placer.topological.zone_solver import ZoneAssignment, ZoneSolver


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
        # Get unplaced, non-fixed components
        unfixed_components = [c for c in context.netlist.components if not c.fixed]
        unplaced_refs = set(
            c.ref for c in unfixed_components if c.ref not in context.current_placements
        )

        if not unplaced_refs:
            return HeuristicResult(
                success=True,
                message="No components to place",
            )

        # Build topological graph from constraints/netlist
        graph = self._build_graph(context, unplaced_refs)

        # Build zone assignment
        zone_assignment = self._build_zone_assignment(context, graph, unplaced_refs)

        # Get component sizes
        component_sizes = {
            c.ref: (c.width, c.height) for c in context.netlist.components if c.ref in unplaced_refs
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
                assignments={ref: "_BOARD_" for ref in unplaced_refs},
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
        component_refs: set[str],
    ) -> TopologicalGraph:
        """Build topological graph from context.

        Uses netlist connectivity to infer adjacency relationships.

        Args:
            context: Placement context
            component_refs: Components to include in graph

        Returns:
            TopologicalGraph with components and constraints
        """
        graph = TopologicalGraph()

        # Add components
        for ref in component_refs:
            graph.add_component(ref)

        # Infer adjacency from nets - components sharing a net should be close
        for net in context.netlist.nets:
            # Get component refs from pins
            net_refs = set()
            for pin in net.pins:
                # Pin is a tuple (component_ref, pin_name)
                ref = pin[0]
                if ref in component_refs:
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
        graph: TopologicalGraph,
        component_refs: set[str],
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
