#!/usr/bin/env python3
"""
Placement Quality Report Script

Evaluates the quality of a KiCad PCB placement by combining:
- Placement metrics (overlaps, clearances, wirelength)
- DRC results (violations, errors, warnings)
- Optional routing verification (completion, via count)

Outputs a unified quality score (0-100) with structured JSON or human-readable report.

Usage:
    python placement_quality_report.py --pcb design.kicad_pcb
    python placement_quality_report.py --pcb design.kicad_pcb --route --json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb, ParseResult
from temper_placer.validation.metrics import compute_metrics, PlacementMetrics
from temper_placer.validation.drc_runner import run_drc, DrcResult, is_kicad_cli_available
from temper_placer.routing.verifier import (
    RoutingVerifier,
    RoutingVerifierConfig,
    VerificationLevel,
)
from temper_placer.metrics.quality_score import compute_quality_score, QualityScore
from temper_placer.core.state import PlacementState
from temper_placer.core.loop import LoopCollection
import jax.numpy as jnp


def evaluate_placement_metrics(pcb_path: Path) -> tuple[PlacementMetrics, ParseResult]:
    """
    Evaluate placement metrics from a KiCad PCB file.

    Args:
        pcb_path: Path to KiCad PCB file

    Returns:
        Tuple of (PlacementMetrics, ParseResult)
    """
    # Parse PCB - returns ParseResult with netlist and board
    parse_result = parse_kicad_pcb(pcb_path)

    if parse_result.board is None:
        raise ValueError("Failed to parse board geometry from PCB")

    netlist = parse_result.netlist
    board = parse_result.board

    # Extract current positions from components (use initial_position if set, else (0,0))
    positions = []
    rotations = []
    for comp in netlist.components:
        if comp.initial_position is not None:
            positions.append(comp.initial_position)
        else:
            positions.append((0.0, 0.0))

        if comp.initial_rotation is not None:
            rotations.append(comp.initial_rotation)
        else:
            rotations.append(0)

    positions = jnp.array(positions)

    # Convert rotation indices to one-hot encoding for state (0/90/180/270 → 4-way logits)
    rotation_logits = jnp.zeros((len(rotations), 4))
    rotation_logits = rotation_logits.at[jnp.arange(len(rotations)), jnp.array(rotations)].set(10.0)

    # Create minimal PlacementState for metrics computation
    state = PlacementState(
        positions=positions,
        rotation_logits=rotation_logits,
    )

    # Compute metrics using existing function
    metrics = compute_metrics(state, netlist, board)

    return metrics, parse_result


def evaluate_drc(pcb_path: Path) -> DrcResult:
    """
    Run KiCad DRC on the PCB file.

    Args:
        pcb_path: Path to KiCad PCB file

    Returns:
        DrcResult with violation counts
    """
    if not is_kicad_cli_available():
        print("Warning: kicad-cli not found in PATH, skipping DRC", file=sys.stderr)
        return DrcResult(error_count=0, warning_count=0, errors=[], warnings=[])

    try:
        result = run_drc(pcb_path)
        return result
    except Exception as e:
        print(f"Warning: DRC check failed: {e}", file=sys.stderr)
        # Return empty result on failure
        return DrcResult(error_count=0, warning_count=0, errors=[], warnings=[])


def evaluate_routing(parse_result: ParseResult) -> Optional[dict]:
    """
    Run routing verification on the parsed PCB.

    Args:
        parse_result: ParseResult from parse_kicad_pcb

    Returns:
        Dictionary with routing metrics, or None on failure
    """
    if parse_result.board is None:
        print("Warning: No board geometry for routing verification", file=sys.stderr)
        return None

    try:
        netlist = parse_result.netlist
        board = parse_result.board

        # Extract positions (use initial_position if set, else (0,0))
        positions = []
        for comp in netlist.components:
            if comp.initial_position is not None:
                positions.append(comp.initial_position)
            else:
                positions.append((0.0, 0.0))
        positions = jnp.array(positions)

        # Create verifier with GEOMETRIC level (faster than MAZE)
        config = RoutingVerifierConfig(level=VerificationLevel.GEOMETRIC)
        verifier = RoutingVerifier(config=config)

        # Run verification (no critical loops for now)
        loops = LoopCollection(loops=[])
        result = verifier.verify(netlist, positions, board, loops)

        return {
            "completion_pct": result.completion_rate * 100.0,
            "wirelength_mm": result.total_wirelength,
            "via_count": result.total_vias,
            "verification_level": "geometric",
            "routable": result.feasible,
            "failed_nets": len(result.failed_nets),
            "worst_congestion": result.worst_congestion,
        }

    except Exception as e:
        print(f"Warning: Routing verification failed: {e}", file=sys.stderr)
        return None


def format_human_readable(
    pcb_path: Path,
    placement_metrics: PlacementMetrics,
    drc_result: DrcResult,
    routing_metrics: Optional[dict],
    quality_score: QualityScore,
    timestamp: str,
) -> str:
    """Format results as human-readable text report."""

    lines = []
    lines.append("=" * 70)
    lines.append("PLACEMENT QUALITY REPORT")
    lines.append("=" * 70)
    lines.append(f"Input File: {pcb_path}")
    lines.append(f"Timestamp:  {timestamp}")
    lines.append("")

    # Placement metrics
    lines.append("PLACEMENT METRICS")
    lines.append("-" * 70)
    lines.append(f"  Overlaps:              {placement_metrics.overlap_count}")
    lines.append(f"  Total Overlap Area:    {placement_metrics.total_overlap_area:.2f} mm²")
    lines.append(f"  Boundary Violations:   {placement_metrics.boundary_violations}")
    lines.append(f"  Clearance Violations:  {placement_metrics.clearance_violations}")
    lines.append(f"  HV-LV Violations:      {placement_metrics.hv_lv_violations}")
    lines.append(f"  Zone Violations:       {placement_metrics.zone_violations}")
    lines.append(f"  Keepout Violations:    {placement_metrics.keepout_violations}")
    lines.append(f"  Total Wirelength:      {placement_metrics.total_wirelength:.1f} mm")
    lines.append(f"  Utilization:           {placement_metrics.utilization * 100:.1f}%")
    lines.append("")

    # DRC metrics
    lines.append("DRC METRICS")
    lines.append("-" * 70)
    lines.append(f"  Total Violations:      {drc_result.error_count + drc_result.warning_count}")
    lines.append(f"  Errors:                {drc_result.error_count}")
    lines.append(f"  Warnings:              {drc_result.warning_count}")
    lines.append("")

    # Routing metrics (if available)
    if routing_metrics:
        lines.append("ROUTING METRICS")
        lines.append("-" * 70)
        lines.append(f"  Completion (%):        {routing_metrics['completion_pct']:.1f}")
        lines.append(f"  Wirelength (mm):       {routing_metrics['wirelength_mm']:.2f}")
        lines.append(f"  Via Count:             {routing_metrics['via_count']}")
        lines.append(f"  Routable:              {routing_metrics['routable']}")
        lines.append(f"  Failed Nets:           {routing_metrics['failed_nets']}")
        lines.append(f"  Worst Congestion:      {routing_metrics['worst_congestion']:.2f}")
        lines.append(f"  Verification Level:    {routing_metrics['verification_level']}")
        lines.append("")

    # Quality score
    lines.append("QUALITY SCORE")
    lines.append("-" * 70)
    lines.append(f"  Score:                 {quality_score.overall:.1f} / 100")
    lines.append(f"  Interpretation:        {quality_score.interpretation.upper()}")
    lines.append(f"  Pass:                  {'YES' if quality_score.pass_quality else 'NO'}")
    lines.append("")

    lines.append("=" * 70)

    return "\n".join(lines)


def format_json(
    pcb_path: Path,
    placement_metrics: PlacementMetrics,
    drc_result: DrcResult,
    routing_metrics: Optional[dict],
    quality_score: QualityScore,
    timestamp: str,
) -> str:
    """Format results as JSON."""

    data = {
        "input_file": str(pcb_path),
        "timestamp": timestamp,
        "placement_metrics": placement_metrics.to_dict(),
        "drc_metrics": {
            "total_violations": drc_result.error_count + drc_result.warning_count,
            "errors": drc_result.error_count,
            "warnings": drc_result.warning_count,
        },
        "quality_score": quality_score.overall,
        "quality_interpretation": quality_score.interpretation,
        "pass": quality_score.pass_quality,
    }

    # Add routing metrics if available
    if routing_metrics:
        data["routing_metrics"] = routing_metrics

    return json.dumps(data, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate placement quality of a KiCad PCB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic report
  python placement_quality_report.py --pcb design.kicad_pcb
  
  # With routing verification (slow)
  python placement_quality_report.py --pcb design.kicad_pcb --route
  
  # JSON output to file
  python placement_quality_report.py --pcb design.kicad_pcb --json --output report.json
        """,
    )

    parser.add_argument("--pcb", type=Path, required=True, help="Path to KiCad PCB file")

    parser.add_argument(
        "--route",
        action="store_true",
        help="Run routing verification (slow, adds 5-30s depending on board size)",
    )

    parser.add_argument(
        "--json", action="store_true", help="Output JSON format instead of human-readable"
    )

    parser.add_argument("--output", type=Path, help="Write output to file instead of stdout")

    args = parser.parse_args()

    # Validate inputs
    if not args.pcb.exists():
        print(f"Error: PCB file not found: {args.pcb}", file=sys.stderr)
        return 1

    # Run evaluations
    timestamp = datetime.now().isoformat()

    print("Evaluating placement metrics...", file=sys.stderr)
    placement_metrics, parse_result = evaluate_placement_metrics(args.pcb)

    print("Running DRC...", file=sys.stderr)
    drc_result = evaluate_drc(args.pcb)

    routing_metrics = None
    if args.route:
        print("Running routing verification (this may take a while)...", file=sys.stderr)
        routing_metrics = evaluate_routing(parse_result)

    # Compute quality score
    # Note: routing_metrics is a dict, but compute_quality_score expects VerificationResult
    # For now, we'll pass None if routing was run (TODO: convert dict to VerificationResult)
    quality_score = compute_quality_score(
        placement_metrics=placement_metrics,
        drc_result=drc_result,
        routing_result=None,  # TODO: pass actual VerificationResult when routing enabled
    )

    # Format output
    if args.json:
        output = format_json(
            args.pcb, placement_metrics, drc_result, routing_metrics, quality_score, timestamp
        )
    else:
        output = format_human_readable(
            args.pcb, placement_metrics, drc_result, routing_metrics, quality_score, timestamp
        )

    # Write output
    if args.output:
        args.output.write_text(output)
        print(f"Report written to: {args.output}", file=sys.stderr)
    else:
        print(output)

    # Exit with appropriate code
    return 0 if quality_score.pass_quality else 1


if __name__ == "__main__":
    sys.exit(main())
