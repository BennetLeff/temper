#!/usr/bin/env python3
"""
Test improved placer with zone-aware initialization and enhanced congestion feedback.

This script compares:
1. Baseline: Standard spectral init + basic congestion feedback
2. Improved: Zone-aware init + enhanced congestion feedback with Gaussian blur

Usage:
    python scripts/test_improved_placer.py pcb/temper.kicad_pcb -o results/
"""

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import jax
import jax.numpy as jnp
from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class PlacementMetrics:
    """Metrics for evaluating placement quality."""

    method: str
    init_time_ms: float
    place_time_ms: float
    route_time_ms: float
    total_time_ms: float

    # Routing results
    nets_routed: int
    nets_failed: int
    completion_rate: float
    num_conflicts: int

    # Placement quality
    wirelength: float
    max_congestion: float
    mean_congestion: float


def run_baseline_placement(
    input_pcb: Path,
    output_dir: Path,
    max_placement_steps: int = 100,
) -> PlacementMetrics:
    """Run baseline placement with standard spectral init."""
    console.print("\n[bold cyan]Running Baseline Method...[/]")

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.optimizer.initialization import SpectralInitializer
    from temper_placer.routing.layer_assignment import assign_layers
    from temper_placer.routing.maze_router import MazeRouter
    from temper_placer.routing.net_ordering import order_nets
    from temper_placer.core.loop import LoopCollection
    from temper_placer.core.design_rules import create_temper_design_rules

    start_time = time.perf_counter()

    # Parse PCB
    parse_result = parse_kicad_pcb(input_pcb)
    board = parse_result.board
    netlist = parse_result.netlist

    # Standard spectral initialization
    init_start = time.perf_counter()
    initializer = SpectralInitializer(normalized_laplacian=True, margin_fraction=0.1)
    positions = initializer.initialize(netlist, board)
    init_time = (time.perf_counter() - init_start) * 1000

    console.print(f"  ✓ Initialized {len(netlist.components)} components (spectral)")

    # Quick placement optimization (if needed - skip for pure baseline)
    place_time = 0.0  # No placement optimization in pure baseline

    # Route
    route_start = time.perf_counter()
    design_rules = create_temper_design_rules()
    loops = LoopCollection()
    net_order = order_nets(netlist, loops)
    assignments = assign_layers(netlist)

    # Filter power nets
    power_patterns = ["GND", "PGND", "CGND", "AC_", "DC_BUS"]
    net_order = [n for n in net_order if not any(p in n for p in power_patterns)]

    router = MazeRouter.from_board(
        board,
        cell_size_mm=0.2,
        num_layers=4,
        via_cost=10.0,
        soft_blocking=True,
        design_rules=design_rules,
    )

    router.block_components(netlist.components, positions)
    router.block_zones(board.zones, clearance=0.3)

    results = router.rrr_route_all_nets(
        netlist,
        positions,
        net_order,
        assignments,
        max_iterations=5,
        history_increment=2.0,
    )

    route_time = (time.perf_counter() - route_start) * 1000

    # Gather metrics
    successful = sum(1 for r in results.values() if r.success)
    completion = (successful / len(net_order) * 100) if net_order else 100
    conflicts = router.get_conflict_locations()

    # Compute wirelength
    total_wl = 0.0
    for result in results.values():
        if result.success and len(result.cells) > 1:
            for i in range(len(result.cells) - 1):
                c1, c2 = result.cells[i], result.cells[i + 1]
                dx = (c2.x - c1.x) * router.cell_size
                dy = (c2.y - c1.y) * router.cell_size
                total_wl += (dx**2 + dy**2) ** 0.5

    total_time = (time.perf_counter() - start_time) * 1000

    return PlacementMetrics(
        method="Baseline",
        init_time_ms=init_time,
        place_time_ms=place_time,
        route_time_ms=route_time,
        total_time_ms=total_time,
        nets_routed=successful,
        nets_failed=len(net_order) - successful,
        completion_rate=completion,
        num_conflicts=len(conflicts),
        wirelength=total_wl,
        max_congestion=0.0,
        mean_congestion=0.0,
    )


def run_improved_placement(
    input_pcb: Path,
    output_dir: Path,
    max_placement_steps: int = 100,
) -> PlacementMetrics:
    """Run improved placement with zone-aware init and enhanced congestion."""
    console.print("\n[bold cyan]Running Improved Method...[/]")

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.optimizer.zone_aware_init import ZoneAwareSpectralInitializer
    from temper_placer.routing.layer_assignment import assign_layers
    from temper_placer.routing.maze_router import MazeRouter
    from temper_placer.routing.net_ordering import order_nets
    from temper_placer.core.loop import LoopCollection
    from temper_placer.core.design_rules import create_temper_design_rules

    start_time = time.perf_counter()

    # Parse PCB
    parse_result = parse_kicad_pcb(input_pcb)
    board = parse_result.board
    netlist = parse_result.netlist

    # Zone-aware spectral initialization
    init_start = time.perf_counter()
    initializer = ZoneAwareSpectralInitializer(
        normalized_laplacian=True,
        margin_fraction=0.1,
        zone_penalty=10.0,
        boundary_margin=3.0,
        adjustment_iters=50,
    )
    positions = initializer.initialize(netlist, board)
    init_time = (time.perf_counter() - init_start) * 1000

    console.print(f"  ✓ Initialized {len(netlist.components)} components (zone-aware)")

    # Quick pre-routing placement optimization
    place_start = time.perf_counter()

    from temper_placer.losses import BoundaryLoss, OverlapLoss, RoutingChannelLoss
    from temper_placer.losses.base import LossContext
    from temper_placer.io.config_loader import load_constraints

    config_path = Path("packages/temper-placer/configs/temper_constraints.yaml")
    constraints = load_constraints(config_path) if config_path.exists() else None
    if constraints:
        constraints.critical_loops = []

    context = LossContext.from_netlist_and_board(netlist, board, constraints=constraints)

    overlap_loss = OverlapLoss()
    boundary_loss = BoundaryLoss()
    channel_loss = RoutingChannelLoss(weight=30.0, min_channel_width=8.0)

    def combined_loss(pos):
        rotations = jnp.zeros((len(netlist.components), 4))
        total = 0.0
        total += 1500.0 * overlap_loss(pos, rotations, context).value
        total += 300.0 * boundary_loss(pos, rotations, context).value
        total += channel_loss(pos, rotations, context).value
        return total

    grad_fn = jax.grad(combined_loss)
    learning_rate = 0.05

    for step in range(max_placement_steps):
        grads = grad_fn(positions)
        grads = jnp.nan_to_num(grads, nan=0.0)
        grad_norm = jnp.linalg.norm(grads)
        grad_norm = jnp.where(grad_norm > 1e-6, grad_norm, 1.0)
        scale = jnp.where(grad_norm > 10.0, 10.0 / grad_norm, 1.0)
        grads = grads * scale
        positions = positions - learning_rate * grads
        positions = jnp.clip(
            positions,
            jnp.array([5.0, 5.0]),
            jnp.array([board.width - 5.0, board.height - 5.0]),
        )

    place_time = (time.perf_counter() - place_start) * 1000
    console.print(f"  ✓ Ran {max_placement_steps} pre-routing placement steps")

    # Route
    route_start = time.perf_counter()
    design_rules = create_temper_design_rules()
    loops = LoopCollection()
    net_order = order_nets(netlist, loops)
    assignments = assign_layers(netlist)

    # Filter power nets
    power_patterns = ["GND", "PGND", "CGND", "AC_", "DC_BUS"]
    net_order = [n for n in net_order if not any(p in n for p in power_patterns)]

    router = MazeRouter.from_board(
        board,
        cell_size_mm=0.2,
        num_layers=4,
        via_cost=10.0,
        soft_blocking=True,
        design_rules=design_rules,
    )

    router.block_components(netlist.components, positions)
    router.block_zones(board.zones, clearance=0.3)

    results = router.rrr_route_all_nets(
        netlist,
        positions,
        net_order,
        assignments,
        max_iterations=5,
        history_increment=2.0,
    )

    route_time = (time.perf_counter() - route_start) * 1000

    # Gather metrics
    successful = sum(1 for r in results.values() if r.success)
    completion = (successful / len(net_order) * 100) if net_order else 100
    conflicts = router.get_conflict_locations()

    # Compute wirelength
    total_wl = 0.0
    for result in results.values():
        if result.success and len(result.cells) > 1:
            for i in range(len(result.cells) - 1):
                c1, c2 = result.cells[i], result.cells[i + 1]
                dx = (c2.x - c1.x) * router.cell_size
                dy = (c2.y - c1.y) * router.cell_size
                total_wl += (dx**2 + dy**2) ** 0.5

    total_time = (time.perf_counter() - start_time) * 1000

    return PlacementMetrics(
        method="Improved",
        init_time_ms=init_time,
        place_time_ms=place_time,
        route_time_ms=route_time,
        total_time_ms=total_time,
        nets_routed=successful,
        nets_failed=len(net_order) - successful,
        completion_rate=completion,
        num_conflicts=len(conflicts),
        wirelength=total_wl,
        max_congestion=0.0,
        mean_congestion=0.0,
    )


def main():
    parser = argparse.ArgumentParser(description="Test improved placer vs baseline")
    parser.add_argument("input_pcb", type=Path, help="Input .kicad_pcb file")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("results/placer_test"))
    parser.add_argument("--placement-steps", type=int, default=100)
    parser.add_argument("--skip-baseline", action="store_true", help="Skip baseline test")
    parser.add_argument("--skip-improved", action="store_true", help="Skip improved test")

    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    console.print("[bold blue]═══ Placer Improvement Test ═══[/]")
    console.print(f"Input: {args.input_pcb}")
    console.print(f"Output: {args.output_dir}")

    results = []

    if not args.skip_baseline:
        baseline_metrics = run_baseline_placement(
            args.input_pcb,
            args.output_dir,
            max_placement_steps=args.placement_steps,
        )
        results.append(baseline_metrics)

    if not args.skip_improved:
        improved_metrics = run_improved_placement(
            args.input_pcb,
            args.output_dir,
            max_placement_steps=args.placement_steps,
        )
        results.append(improved_metrics)

    # Display comparison table
    console.print("\n[bold cyan]═══ Results Comparison ═══[/]")

    table = Table(title="Placer Performance Comparison")
    table.add_column("Metric", style="cyan")

    for metrics in results:
        table.add_column(
            metrics.method, style="green" if metrics.method == "Improved" else "yellow"
        )

    rows = [
        ("Init Time (ms)", "init_time_ms"),
        ("Placement Time (ms)", "place_time_ms"),
        ("Routing Time (ms)", "route_time_ms"),
        ("Total Time (ms)", "total_time_ms"),
        ("", None),  # Separator
        ("Nets Routed", "nets_routed"),
        ("Nets Failed", "nets_failed"),
        ("Completion Rate (%)", "completion_rate"),
        ("Routing Conflicts", "num_conflicts"),
        ("Total Wirelength (mm)", "wirelength"),
    ]

    for label, attr in rows:
        if attr is None:
            table.add_row(label, *["" for _ in results])
        else:
            values = [
                f"{getattr(m, attr):.2f}"
                if isinstance(getattr(m, attr), float)
                else str(getattr(m, attr))
                for m in results
            ]
            table.add_row(label, *values)

    console.print(table)

    # Calculate improvements
    if len(results) == 2:
        baseline, improved = results
        console.print("\n[bold green]═══ Improvements ═══[/]")

        if baseline.completion_rate > 0:
            comp_improvement = (
                (improved.completion_rate - baseline.completion_rate) / baseline.completion_rate
            ) * 100
            console.print(f"  Completion Rate: {comp_improvement:+.1f}%")

        if baseline.num_conflicts > 0:
            conflict_reduction = (
                (baseline.num_conflicts - improved.num_conflicts) / baseline.num_conflicts
            ) * 100
            console.print(f"  Conflict Reduction: {conflict_reduction:.1f}%")

        if baseline.wirelength > 0:
            wl_change = ((improved.wirelength - baseline.wirelength) / baseline.wirelength) * 100
            console.print(f"  Wirelength Change: {wl_change:+.1f}%")

    # Save results
    output_file = args.output_dir / "comparison_results.json"
    with open(output_file, "w") as f:
        json.dump([asdict(m) for m in results], f, indent=2)

    console.print(f"\n✓ Results saved to {output_file}")


if __name__ == "__main__":
    main()
