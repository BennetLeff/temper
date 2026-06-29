#!/usr/bin/env python3
"""
Diagnostic tool to analyze routing failures and recommend experiments.
"""
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Add temper-placer to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from temper_placer.router_v6.astar_pathfinding import (
    _extract_pad_centers_per_net,
    _find_access_node,
)
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.pipeline import RouterV6Pipeline


@dataclass
class DiagnosisReport:
    """Detailed diagnosis of why a net failed to route."""
    net_name: str
    failure_type: str  # "START_BLOCKED", "GOAL_BLOCKED", "CHANNEL_CONGESTED", "QUANTIZATION_ERROR"
    start_blocked: bool
    goal_blocked: bool
    blockers_at_start: list[str]
    blockers_at_goal: list[str]
    total_obstructions: int
    min_gap_along_path: float  # Minimum clearance found
    recommended_experiment: str  # "F", "G", or "H"


def get_blockers_in_radius(
    grid: OccupancyGrid,
    position: tuple[float, float],
    net_ids: dict[int, str],
    radius_mm: float = 0.3
) -> list[str]:
    """
    Find which nets are blocking within radius of position.

    Args:
        grid: Occupancy grid
        position: (x, y) world position
        net_ids: Mapping from net_id to net_name
        radius_mm: Search radius

    Returns:
        List of net names blocking this position
    """
    cx, cy = grid.world_to_grid(position[0], position[1])
    radius_cells = int(radius_mm / grid.cell_size) + 1

    blockers = set()
    for dy in range(-radius_cells, radius_cells + 1):
        for dx in range(-radius_cells, radius_cells + 1):
            gx, gy = cx + dx, cy + dy
            if not (0 <= gx < grid.width_cells and 0 <= gy < grid.height_cells):
                continue

            cell_value = grid.grid[gy, gx]
            if cell_value > 0:  # Positive = net ID
                net_name = net_ids.get(cell_value, f"Unknown-{cell_value}")
                blockers.add(net_name)

    return sorted(blockers)


def count_obstructions_along_path(
    grid: OccupancyGrid,
    waypoints: list[tuple[float, float]],
    samples_per_segment: int = 10
) -> int:
    """
    Count how many blocked cells exist along waypoint path.

    Args:
        grid: Occupancy grid
        waypoints: Path waypoints
        samples_per_segment: Sampling resolution

    Returns:
        Number of obstructed sample points
    """
    obstructions = 0

    for i in range(len(waypoints) - 1):
        p1, p2 = waypoints[i], waypoints[i + 1]

        for j in range(samples_per_segment):
            t = j / (samples_per_segment - 1) if samples_per_segment > 1 else 0.5
            x = p1[0] + t * (p2[0] - p1[0])
            y = p1[1] + t * (p2[1] - p1[1])

            gx, gy = grid.world_to_grid(x, y)
            if 0 <= gx < grid.width_cells and 0 <= gy < grid.height_cells and grid.grid[gy, gx] != 0:
                obstructions += 1

    return obstructions


def compute_min_gap_along_path(
    grid: OccupancyGrid,
    waypoints: list[tuple[float, float]],
    _net_ids: dict[int, str]
) -> float:
    """
    Compute minimum clearance gap along path to nearest obstacle.

    Returns:
        Minimum gap in mm (positive = clearance available)
    """
    min_gap = float('inf')
    cell_size = grid.cell_size

    for wp in waypoints:
        gx, gy = grid.world_to_grid(wp[0], wp[1])

        # Search in expanding circles for nearest obstacle
        for radius in range(1, 20):  # Up to 2mm
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if abs(dx) != radius and abs(dy) != radius:
                        continue  # Only check perimeter

                    x, y = gx + dx, gy + dy
                    if not (0 <= x < grid.width_cells and 0 <= y < grid.height_cells):
                        continue

                    if grid.grid[y, x] != 0:  # Found obstacle
                        gap_mm = (radius - 1) * cell_size
                        min_gap = min(min_gap, gap_mm)
                        break

    return min_gap if min_gap != float('inf') else 0.0


def diagnose_net_failure(
    net_name: str,
    grid: OccupancyGrid,
    pad_centers: dict[str, list[tuple[float, float, float, str]]],
    channel_mapping,
    net_ids: dict[str, int],
    id_to_net: dict[int, str]
) -> DiagnosisReport:
    """
    Determine exact failure cause for a net.

    Args:
        net_name: Net to diagnose
        grid: Primary occupancy grid (F.Cu)
        pad_centers: Pad positions per net
        channel_mapping: ChannelMapping from Stage 4
        net_ids: net_name -> net_id mapping
        id_to_net: net_id -> net_name mapping

    Returns:
        Detailed diagnosis report
    """
    net_pads = pad_centers.get(net_name, [])
    if len(net_pads) < 2:
        return DiagnosisReport(
            net_name=net_name,
            failure_type="INVALID",
            start_blocked=False,
            goal_blocked=False,
            blockers_at_start=[],
            blockers_at_goal=[],
            total_obstructions=0,
            min_gap_along_path=0.0,
            recommended_experiment="N/A"
        )

    start_pos = (net_pads[0][0], net_pads[0][1])
    goal_pos = (net_pads[-1][0], net_pads[-1][1])
    net_id = net_ids.get(net_name, -1)

    # Check 1: Is start accessible?
    start_node = _find_access_node(grid, start_pos, net_id, search_radius_cells=3)
    start_blocked = start_node is None

    # Check 2: Is goal accessible?
    goal_node = _find_access_node(grid, goal_pos, net_id, search_radius_cells=3)
    goal_blocked = goal_node is None

    # Check 3: What's blocking?
    blockers_at_start = get_blockers_in_radius(grid, start_pos, id_to_net, radius_mm=0.3)
    blockers_at_goal = get_blockers_in_radius(grid, goal_pos, id_to_net, radius_mm=0.3)

    # Check 4: Obstructions along path
    channel_path = channel_mapping.channel_paths.get(net_name)
    waypoints = channel_path.waypoints if channel_path else []
    obstructions = count_obstructions_along_path(grid, waypoints) if waypoints else 0

    # Check 5: Minimum gap
    min_gap = compute_min_gap_along_path(grid, waypoints, id_to_net) if waypoints else 0.0

    # Determine failure type and recommendation
    if start_blocked or goal_blocked:
        failure_type = "START_BLOCKED" if start_blocked else "GOAL_BLOCKED"
        recommended = "G"  # Geometry problem → Smoothing
    elif obstructions > len(waypoints) * 0.5:  # >50% waypoints blocked
        failure_type = "CHANNEL_CONGESTED"
        recommended = "H"  # Topology problem → SAT
    elif min_gap < 0.2 and min_gap > 0.1:  # Near-miss
        failure_type = "QUANTIZATION_ERROR"
        recommended = "F"  # Quantization → Theta* or Smoothing
    else:
        failure_type = "UNKNOWN"
        recommended = "G"  # Default to smoothing

    return DiagnosisReport(
        net_name=net_name,
        failure_type=failure_type,
        start_blocked=start_blocked,
        goal_blocked=goal_blocked,
        blockers_at_start=blockers_at_start,
        blockers_at_goal=blockers_at_goal,
        total_obstructions=obstructions,
        min_gap_along_path=min_gap,
        recommended_experiment=recommended
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Diagnose routing failures")
    parser.add_argument("pcb_file", type=Path, help="Input PCB file")
    parser.add_argument("--nets", type=str, help="Comma-separated net names to diagnose")
    parser.add_argument("--output", type=Path, help="Output JSON file")

    args = parser.parse_args()

    if not args.pcb_file.exists():
        print(f"ERROR: PCB file not found: {args.pcb_file}")
        sys.exit(1)

    # Run router to get failure data
    print("Running Router V6 pipeline...")
    pipeline = RouterV6Pipeline(verbose=True)
    result = pipeline.run(args.pcb_file)

    # Get failed nets
    failed_nets = result.routing_results.failed_nets
    if args.nets:
        failed_nets = [n.strip() for n in args.nets.split(",")]

    print(f"\nDiagnosing {len(failed_nets)} failed nets...")

    # Extract data structures needed for diagnosis
    stage4 = result.stage4_output
    grid = result.stage2_output.occupancy_grids.get("F.Cu")
    pad_centers = _extract_pad_centers_per_net(result.stage0_output.pcb)
    channel_mapping = stage4.channel_mapping

    # Build net ID mappings
    net_ids = {name: i + 1 for i, name in enumerate(channel_mapping.channel_paths.keys())}
    id_to_net = {v: k for k, v in net_ids.items()}

    # Diagnose each failed net
    diagnoses = {}
    for net_name in failed_nets:
        report = diagnose_net_failure(
            net_name, grid, pad_centers, channel_mapping, net_ids, id_to_net
        )
        diagnoses[net_name] = asdict(report)

        # Print summary
        print(f"\n{net_name}:")
        print(f"  Type: {report.failure_type}")
        print(f"  Start blocked: {report.start_blocked}")
        print(f"  Goal blocked: {report.goal_blocked}")
        print(f"  Obstructions: {report.total_obstructions}")
        print(f"  Min gap: {report.min_gap_along_path:.3f}mm")
        print(f"  → Recommended: Experiment {report.recommended_experiment}")

    # Write JSON output
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(diagnoses, f, indent=2)
        print(f"\nDiagnosis written to: {args.output}")

    # Summarize recommendations
    recommendations = {}
    for report in diagnoses.values():
        exp = report['recommended_experiment']
        recommendations[exp] = recommendations.get(exp, 0) + 1

    print("\n" + "="*60)
    print("EXPERIMENT RECOMMENDATIONS:")
    for exp, count in sorted(recommendations.items()):
        print(f"  Experiment {exp}: {count} nets")
    print("="*60)


if __name__ == "__main__":
    main()
