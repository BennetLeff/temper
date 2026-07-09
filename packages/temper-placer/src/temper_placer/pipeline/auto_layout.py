"""Unified automated PCB layout pipeline.

This module provides the main entry point for zero-input automated placement and routing.
"""

from typing import TYPE_CHECKING, TypeAlias

import numpy as np
from numpy.typing import NDArray

Array: TypeAlias = NDArray

if TYPE_CHECKING:
    from temper_placer.io.config_loader import PlacementConstraints

from temper_placer.core.board import Board
from temper_placer.core.loop import LoopCollection
from temper_placer.core.netlist import Netlist


# JAX retirement stubs for deleted losses module
class BoundaryLoss:
    def __call__(self, *a, **kw): raise NotImplementedError("JAX losses removed.")
class BusAlignmentLoss:
    def __call__(self, *a, **kw): raise NotImplementedError("JAX losses removed.")
class MCUClusteringLoss:
    def __call__(self, *a, **kw): raise NotImplementedError("JAX losses removed.")
class OverlapLoss:
    def __call__(self, *a, **kw): raise NotImplementedError("JAX losses removed.")
class RoutingChannelLoss:
    def __call__(self, *a, **kw): raise NotImplementedError("JAX losses removed.")
class ConflictLocation:
    pass
class RoutingCongestionLoss:
    def __call__(self, *a, **kw): raise NotImplementedError("JAX losses removed.")
def compute_congestion_heatmap(*a, **kw):
    raise NotImplementedError("JAX losses removed.")
from temper_placer.pipeline.convergence import is_converged
from temper_placer.router_v6 import V6RouterAdapter
from temper_placer.router_v6 import _AdapterRoutePath as RoutePath
from temper_placer.router_v6.layer_assignment import assign_layers
from temper_placer.router_v6.net_ordering import order_nets


def initial_placement(netlist: Netlist, board: Board) -> Array:
    """Compute initial component placement."""
    # Start with components at their initial positions if available, otherwise board center
    positions = []
    for comp in netlist.components:
        if comp.initial_position:
            positions.append(comp.initial_position)
        else:
            positions.append((board.width / 2, board.height / 2))
    return np.array(positions)

def auto_layout_pcb(
    netlist: Netlist,
    board: Board,
    max_outer_iterations: int = 10,
    cell_size_mm: float = 0.5,
    num_layers: int = 2,
    initial_positions: Array | None = None,
    constraints: "PlacementConstraints | None" = None,
) -> tuple[Array, dict[str, RoutePath]]:
    """
    Fully automated placement and routing.

    Returns:
        Final component positions and routing results.
    """
    print(f"Starting auto_layout_pcb with {max_outer_iterations} outer iterations...")

    # Stage 1: Initial placement
    if initial_positions is not None:
        positions = initial_positions
    else:
        positions = initial_placement(netlist, board)

    # Prepare routing metadata
    loops = LoopCollection()
    net_order = order_nets(netlist, loops)
    assignments = assign_layers(netlist, component_positions=positions)

    # Exclude power/ground nets from routing (they should be handled by planes)
    POWER_NET_PATTERNS = ['GND', 'VCC', 'VDD', '3V3', '5V', '12V', '15V']
    net_order = [n for n in net_order if not any(p in n.upper() for p in POWER_NET_PATTERNS)]

    prev_results = None
    best_positions = positions
    best_conflicts = float('inf')
    congestion_heatmap = None

    # Stage 2: Placement-routing loop
    for outer_iter in range(max_outer_iterations):
        print(f"\nOuter loop iteration {outer_iter + 1}/{max_outer_iterations}")

        # 2a. Placement Optimization (if we have feedback)
        if congestion_heatmap is not None:
            positions = optimize_placement_with_feedback(
                netlist, board, positions, congestion_heatmap, cell_size_mm
            )

        # 2b. Routing pass
        if constraints:
            from temper_placer.io.config_loader import constraints_to_design_rules
            design_rules = constraints_to_design_rules(constraints)
        else:
            from temper_placer.core.design_rules import create_temper_design_rules
            design_rules = create_temper_design_rules()

        router = V6RouterAdapter.from_board(
            board,
            cell_size_mm=cell_size_mm,
            num_layers=num_layers,
            soft_blocking=True,
            design_rules=design_rules
        )
        router.block_components(netlist.components, positions)

        # Route all nets with Rip-up and Reroute
        results = router.rrr_route_all_nets(
            netlist,
            positions,
            net_order,
            assignments,
            _max_iterations=5 # Inner RRR iterations
        )

        # 2c. Check convergence
        if is_converged(results, prev_results):
            print("Convergence detected. Stopping loop.")
            break

        # Update best result
        conflict_locs = router.get_conflict_locations()
        num_conflicts = len(conflict_locs)
        if num_conflicts < best_conflicts:
            best_conflicts = num_conflicts
            best_positions = positions

        if num_conflicts == 0:
            print("Perfect routing achieved!")
            break

        # 2d. Prepare feedback for next iteration
        conflicts = [
            ConflictLocation(x=loc['x'], y=loc['y'], layer=loc['layer'], nets=loc['nets'])
            for loc in conflict_locs
        ]
        congestion_heatmap = compute_congestion_heatmap(
            conflicts,
            grid_size=router.grid_size,
            _cell_size_mm=cell_size_mm,
        _origin=board.origin
        )
        prev_results = results

    # Stage 3: Final routing pass with maximum effort
    print("\nStarting final high-effort routing pass...")
    if constraints:
        from temper_placer.io.config_loader import constraints_to_design_rules
        design_rules = constraints_to_design_rules(constraints)
    else:
        from temper_placer.core.design_rules import create_temper_design_rules
        design_rules = create_temper_design_rules()
    router = V6RouterAdapter.from_board(
        board,
        cell_size_mm=cell_size_mm,
        num_layers=num_layers,
        design_rules=design_rules
    )
    router.block_components(netlist.components, best_positions)
    final_results = router.rrr_route_all_nets(
        netlist,
        best_positions,
        net_order,
        assignments,
        _max_iterations=50
    )

    return best_positions, final_results

def optimize_placement_with_feedback(
    netlist: Netlist,
    board: Board,
    current_positions: Array,
    congestion_heatmap: Array,
    cell_size_mm: float,
    steps: int = 100
) -> Array:
    """DEPRECATED: JAX gradient-descent placement optimization removed (JAX retirement).

    This used jax.grad / jax.lax.scan over the (now-removed) differentiable
    loss system. Use the CP-SAT placer for placement optimization instead.
    """
    raise NotImplementedError(
        "optimize_placement_with_feedback removed (JAX retirement). "
        "Use the CP-SAT placer for placement optimization."
    )
