"""Benchmark runner for Router V6 multi-board test suite.

This module runs the router on multiple test boards and collects
structured metrics for comparison and regression testing.

Usage:
    python -m temper_placer.router_v6.benchmark --router v5
    python -m temper_placer.router_v6.benchmark --router v6
    python -m temper_placer.router_v6.benchmark --board Piantor
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from temper_placer.deterministic.pipeline import DeterministicPipeline
from temper_placer.deterministic.stages.clearance_grid import ClearanceGridStage
from temper_placer.deterministic.stages.layer_assignment import LayerAssignmentStage
from temper_placer.deterministic.stages.net_ordering import NetOrderingStage
from temper_placer.deterministic.stages.sequential_routing import SequentialRoutingStage
from temper_placer.deterministic.state import BoardState
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.router_v6.diagnostics import (
    BoardRoutingReport,
    FailureReason,
    NetRoutingReport,
    RoutingStatus,
    aggregate_board_score,
    calculate_routing_score,
)
from temper_placer.router_v6.test_boards import get_available_boards, get_board_by_name


def run_v5_router(pcb_path: Path) -> BoardRoutingReport:
    """Run V5 router on a board and generate diagnostic report.

    Args:
        pcb_path: Path to .kicad_pcb file

    Returns:
        BoardRoutingReport with structured diagnostics
    """
    board_name = pcb_path.stem
    print(f"\n{'='*60}")
    print(f"Running V5 router on: {board_name}")
    print(f"{'='*60}")

    # Parse board
    start_time = time.time()
    result = parse_kicad_pcb(pcb_path)
    parse_time = time.time() - start_time
    print(f"Parsed: {len(result.netlist.nets)} nets in {parse_time:.2f}s")

    # Filter out zone nets (nets with copper pours)
    zone_nets = set()
    for zone in result.board.zones:
        for net_name in zone.net_classes:
            if net_name and net_name != "Signal":
                zone_nets.add(net_name)

    trace_nets = [n for n in result.netlist.nets if n.name not in zone_nets]
    print(f"Trace nets: {len(trace_nets)} (excluding {len(zone_nets)} zone nets)")

    # Create state and pipeline
    from temper_placer.core.netlist import Netlist
    filtered_netlist = Netlist(
        components=result.netlist.components,
        nets=trace_nets,
    )

    state = BoardState(board=result.board, netlist=filtered_netlist)
    pipeline = DeterministicPipeline(stages=[
        ClearanceGridStage(cell_size_mm=0.25, layer_count=2),
        LayerAssignmentStage(),
        NetOrderingStage(),
        SequentialRoutingStage(),
    ])

    # Route
    route_start = time.time()
    final_state = pipeline.run(state)
    route_time = time.time() - route_start

    # Generate per-net reports
    net_reports: list[NetRoutingReport] = []

    routed_nets = set()
    for route in final_state.routes:
        routed_nets.add(route.net)

    for net in trace_nets:
        if net.name in routed_nets:
            # Successfully routed
            routed_count = sum(1 for r in final_state.routes if r.net == net.name)
            route_length = sum(
                ((r.end[0] - r.start[0])**2 + (r.end[1] - r.start[1])**2)**0.5
                for r in final_state.routes if r.net == net.name
            )

            # Estimate direct distance (simplified)
            pin_positions = []
            for pin_ref in net.pins:
                for pad in result.pads:
                    pad_id = f"{pad.component_ref}.{pad.number}"
                    if pad_id == pin_ref:
                        pin_positions.append(pad.position)
                        break

            if len(pin_positions) >= 2:
                direct = ((pin_positions[0][0] - pin_positions[-1][0])**2 +
                         (pin_positions[0][1] - pin_positions[-1][1])**2)**0.5
            else:
                direct = route_length

            detour = route_length / direct if direct > 0 else 1.0
            score = calculate_routing_score(routed_count, len(net.pins) - 1, 0)

            report = NetRoutingReport(
                net_name=net.name,
                status=RoutingStatus.SUCCESS,
                score=score,
                pins=len(net.pins),
                routed_segments=routed_count,
                total_segments=len(net.pins) - 1,
                route_length_mm=route_length,
                direct_distance_mm=direct,
                detour_ratio=detour,
                message=f"Routed {routed_count} segments, {route_length:.1f}mm total"
            )
        else:
            # Failed to route
            score = calculate_routing_score(0, len(net.pins) - 1, 0)
            report = NetRoutingReport(
                net_name=net.name,
                status=RoutingStatus.FAILED,
                score=score,
                pins=len(net.pins),
                routed_segments=0,
                total_segments=len(net.pins) - 1,
                failure_reason=FailureReason.NO_PATH,
                message="V5 router failed to find path"
            )

        net_reports.append(report)

    # Aggregate board statistics
    auto_routed = sum(1 for r in net_reports if r.status == RoutingStatus.SUCCESS)
    flagged = sum(1 for r in net_reports if r.status == RoutingStatus.FLAGGED)
    failed = sum(1 for r in net_reports if r.status == RoutingStatus.FAILED)
    total_nets = len(net_reports)
    completion_rate = auto_routed / total_nets if total_nets > 0 else 0.0

    total_route_length = sum(r.route_length_mm for r in net_reports if r.route_length_mm > 0)
    routed_with_detour = [r for r in net_reports if r.detour_ratio < float('inf')]
    avg_detour = (sum(r.detour_ratio for r in routed_with_detour) / len(routed_with_detour)
                  if routed_with_detour else 0.0)

    overall_score = aggregate_board_score(net_reports)

    board_report = BoardRoutingReport(
        board_name=board_name,
        net_reports=net_reports,
        overall_score=overall_score,
        auto_routed_count=auto_routed,
        flagged_count=flagged,
        failed_count=failed,
        total_nets=total_nets,
        completion_rate=completion_rate,
        total_route_length_mm=total_route_length,
        avg_detour_ratio=avg_detour,
        total_drc_violations=0,  # V5 doesn't report this
        runtime_seconds=route_time
    )

    # Print summary
    print(f"\n{board_report}")
    print(f"  Route time: {route_time:.1f}s")
    print(f"  Overall score: {overall_score:.3f}")

    return board_report


def run_benchmark_suite(
    router: str = "v5",
    board_filter: str | None = None,
    output_file: Path | None = None
) -> list[BoardRoutingReport]:
    """Run benchmark suite on all available boards.

    Args:
        router: Router version to use ("v5" or "v6")
        board_filter: Optional board name to run on single board only
        output_file: Optional path to write JSON results

    Returns:
        List of BoardRoutingReport, one per board
    """
    print("\nRouter V6 Benchmark Suite")
    print(f"Router: {router}")
    print(f"{'='*60}\n")

    # Get boards to test
    if board_filter:
        board = get_board_by_name(board_filter)
        if not board:
            print(f"ERROR: Board '{board_filter}' not found")
            sys.exit(1)
        if not board.exists():
            print(f"ERROR: Board file not found: {board.path}")
            sys.exit(1)
        boards = [board]
    else:
        boards = get_available_boards()

    if not boards:
        print("ERROR: No test boards available")
        sys.exit(1)

    print(f"Testing {len(boards)} boards:")
    for board in boards:
        print(f"  - {board.name} ({board.domain}, {board.layers}L)")
    print()

    # Run router on each board
    reports = []
    for board in boards:
        if router == "v5":
            report = run_v5_router(board.path)
        elif router == "v6":
            # TODO: Implement V6 router
            print("ERROR: V6 router not yet implemented")
            sys.exit(1)
        else:
            print(f"ERROR: Unknown router version: {router}")
            sys.exit(1)

        reports.append(report)

    # Print summary
    print(f"\n{'='*60}")
    print("BENCHMARK SUMMARY")
    print(f"{'='*60}\n")

    for report in reports:
        print(f"{report.board_name}:")
        print(f"  Score: {report.overall_score:.3f}")
        print(f"  Completion: {report.completion_rate*100:.1f}% ({report.auto_routed_count}/{report.total_nets})")
        print(f"  Runtime: {report.runtime_seconds:.1f}s")
        print()

    # Geometric mean across boards
    if reports:
        geo_mean = 1.0
        for report in reports:
            geo_mean *= report.overall_score
        geo_mean = geo_mean ** (1.0 / len(reports))
        print(f"Geometric mean score: {geo_mean:.3f}")

    # Write JSON output
    if output_file:
        results = {
            "router": router,
            "timestamp": time.time(),
            "boards": [report.to_dict() for report in reports],
            "summary": {
                "board_count": len(reports),
                "geometric_mean_score": geo_mean if reports else 0.0,
            }
        }

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults written to: {output_file}")

    return reports


def main():
    parser = argparse.ArgumentParser(description="Run Router V6 benchmark suite")
    parser.add_argument(
        "--router",
        choices=["v5", "v6"],
        default="v5",
        help="Router version to benchmark"
    )
    parser.add_argument(
        "--board",
        type=str,
        help="Run on single board only (by name)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="JSON output file path"
    )

    args = parser.parse_args()

    run_benchmark_suite(
        router=args.router,
        board_filter=args.board,
        output_file=args.output
    )


if __name__ == "__main__":
    main()
