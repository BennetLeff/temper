#!/usr/bin/env python3.11
"""
Unified placement quality report.

Evaluates all quality metrics for a placed PCB, combining:
- Placement loss evaluation (HPWL, overlap, thermal, etc.)
- KiCad DRC validation
- Optional routing analysis (adds 5-15 min)
- Composite quality score (0-100)

Usage:
    # Basic usage (placement + DRC only)
    python scripts/placement_quality_report.py --pcb temper.kicad_pcb

    # With constraints for loss evaluation
    python scripts/placement_quality_report.py --pcb temper.kicad_pcb --config constraints.yaml

    # With routing (adds 5-15 min)
    python scripts/placement_quality_report.py --pcb temper.kicad_pcb --route

    # JSON output
    python scripts/placement_quality_report.py --pcb temper.kicad_pcb --json --output report.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Add temper-placer to path
REPO_ROOT = Path(__file__).parent.parent
PLACER_PATH = REPO_ROOT / "packages" / "temper-placer" / "src"
sys.path.insert(0, str(PLACER_PATH))

from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.io import (
    load_constraints,
    parse_kicad_pcb,
    netlist_to_placement_state,
    infer_quality_config,
    load_reference_pcb,
)
from temper_placer.losses.base import LossContext
from temper_placer.metrics.quality import compute_quality_report
from temper_placer.routing.analysis import analyze_routability


@dataclass
class PlacementMetrics:
    """Placement quality metrics."""

    hpwl_mm: float
    thermal_score: float
    zone_compliance_score: float
    hv_lv_clearance_score: float
    loop_area_score: float
    congestion_score: float
    compactness_score: float
    connectivity_clustering_score: float
    overall_placement_score: float


@dataclass
class DRCMetrics:
    """DRC validation metrics."""

    violations: int
    errors: int
    warnings: int
    drc_available: bool
    error_message: str | None = None


@dataclass
class RoutingMetrics:
    """Routing analysis metrics."""

    completion_pct: float
    total_congestion: float
    max_congestion: float
    bottleneck_count: int
    unrouted_estimate: int
    routing_available: bool
    advice: list[str]


@dataclass
class QualityReport:
    """Complete quality report."""

    input_file: str
    timestamp: str
    placement_metrics: PlacementMetrics
    drc_metrics: DRCMetrics
    routing_metrics: RoutingMetrics | None
    quality_score: float
    passed: bool
    notes: list[str]


def run_kicad_drc(pcb_path: Path) -> DRCMetrics:
    """
    Run KiCad DRC and extract metrics.

    Args:
        pcb_path: Path to .kicad_pcb file.

    Returns:
        DRCMetrics with violation counts.
    """
    try:
        # Check if kicad-cli is available
        result = subprocess.run(
            ["which", "kicad-cli"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return DRCMetrics(
                violations=0,
                errors=0,
                warnings=0,
                drc_available=False,
                error_message="kicad-cli not found in PATH",
            )

        # Create temp file for DRC output
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            drc_output = Path(tmp.name)

        try:
            # Run DRC
            result = subprocess.run(
                [
                    "kicad-cli",
                    "pcb",
                    "drc",
                    "--output",
                    str(drc_output),
                    "--format",
                    "json",
                    "--severity-all",
                    str(pcb_path),
                ],
                capture_output=True,
                text=True,
                timeout=300,  # 5 min timeout
            )

            # Parse DRC output
            if drc_output.exists():
                with open(drc_output) as f:
                    drc_data = json.load(f)

                # Count violations by severity
                errors = 0
                warnings = 0

                for violation in drc_data.get("violations", []):
                    severity = violation.get("severity", "").lower()
                    if severity == "error":
                        errors += 1
                    elif severity == "warning":
                        warnings += 1

                violations = errors + warnings

                return DRCMetrics(
                    violations=violations,
                    errors=errors,
                    warnings=warnings,
                    drc_available=True,
                )
            else:
                return DRCMetrics(
                    violations=0,
                    errors=0,
                    warnings=0,
                    drc_available=False,
                    error_message=f"DRC output not created: {result.stderr}",
                )

        finally:
            # Cleanup temp file
            if drc_output.exists():
                drc_output.unlink()

    except subprocess.TimeoutExpired:
        return DRCMetrics(
            violations=0,
            errors=0,
            warnings=0,
            drc_available=False,
            error_message="DRC timeout (>5 min)",
        )
    except Exception as e:
        return DRCMetrics(
            violations=0,
            errors=0,
            warnings=0,
            drc_available=False,
            error_message=f"DRC error: {e}",
        )


def analyze_placement(
    pcb_path: Path,
    config_path: Path | None,
) -> tuple[PlacementMetrics, Netlist, PlacementState, LossContext]:
    """
    Analyze placement quality using loss functions.

    Args:
        pcb_path: Path to .kicad_pcb file.
        config_path: Optional path to constraints YAML.

    Returns:
        Tuple of (PlacementMetrics, Netlist, PlacementState, LossContext).
    """
    # Load PCB as reference design
    design = load_reference_pcb(str(pcb_path))
    netlist = design.netlist
    board = design.board
    state = design.state

    # Load constraints if provided, otherwise infer from PCB
    if config_path and config_path.exists():
        constraints = load_constraints(str(config_path))
        quality_config = {
            "thermal_components": set(constraints.thermal_constraint.components),
            "hv_components": set(constraints.hv_components),
            "lv_components": set(constraints.lv_components),
            "zone_assignments": constraints.zone_assignments,
            "loop_components": [loop.components for loop in constraints.critical_loops],
            "min_hv_lv_clearance": 8.0,  # Default from spec
        }
    else:
        # Infer quality config from PCB content
        quality_config = infer_quality_config(design)

    # Create loss context using factory method
    context = LossContext.from_netlist_and_board(
        netlist=netlist,
        board=board,
        constraints=None,  # We're evaluating, not optimizing
    )

    # Compute quality report
    report = compute_quality_report(state, netlist, board, context, quality_config)

    metrics = PlacementMetrics(
        hpwl_mm=report["total_wirelength"],
        thermal_score=report["thermal_score"],
        zone_compliance_score=report["zone_compliance_score"],
        hv_lv_clearance_score=report["hv_lv_clearance_score"],
        loop_area_score=report["loop_area_score"],
        congestion_score=report["congestion_score"],
        compactness_score=report["compactness_score"],
        connectivity_clustering_score=report["connectivity_clustering_score"],
        overall_placement_score=report["overall_score"],
    )

    return metrics, netlist, state, context


def analyze_routing_demand(
    state: PlacementState,
    context: LossContext,
) -> RoutingMetrics:
    """
    Analyze routing demand without actual routing.

    Args:
        state: Current placement state.
        context: Pre-computed loss context.

    Returns:
        RoutingMetrics with congestion analysis.
    """
    report = analyze_routability(
        state.positions,
        context,
        grid_shape=(20, 20),
        capacity_per_cell=10.0,
    )

    # Estimate completion percentage based on congestion
    # High congestion → lower completion estimate
    if report.total_congestion == 0:
        completion_pct = 100.0
    else:
        # Heuristic: each unit of congestion reduces completion by 1%
        completion_pct = max(0.0, 100.0 - report.total_congestion)

    return RoutingMetrics(
        completion_pct=completion_pct,
        total_congestion=report.total_congestion,
        max_congestion=report.max_congestion,
        bottleneck_count=len(report.bottleneck_cells),
        unrouted_estimate=report.unrouted_estimate,
        routing_available=True,
        advice=report.advice,
    )


def compute_composite_score(
    placement: PlacementMetrics,
    drc: DRCMetrics,
    routing: RoutingMetrics | None,
) -> tuple[float, list[str]]:
    """
    Compute composite quality score (0-100).

    Scoring rubric:
    - Placement quality: 50 points (from overall_placement_score)
    - DRC compliance: 30 points (zero violations = 30, each violation -1)
    - Routing feasibility: 20 points (from congestion_score or completion_pct)

    Args:
        placement: Placement metrics.
        drc: DRC metrics.
        routing: Optional routing metrics.

    Returns:
        Tuple of (score, notes).
    """
    notes = []

    # Placement quality (50 points)
    placement_points = placement.overall_placement_score * 50.0
    notes.append(f"Placement quality: {placement_points:.1f}/50.0")

    # DRC compliance (30 points)
    if drc.drc_available:
        # Each violation costs 1 point, capped at -30
        drc_penalty = min(30.0, float(drc.violations))
        drc_points = max(0.0, 30.0 - drc_penalty)
        notes.append(f"DRC compliance: {drc_points:.1f}/30.0 ({drc.violations} violations)")
    else:
        # If DRC not available, give benefit of doubt but note it
        drc_points = 20.0  # Partial credit
        notes.append(
            f"DRC compliance: {drc_points:.1f}/30.0 (DRC unavailable: {drc.error_message})"
        )

    # Routing feasibility (20 points)
    if routing and routing.routing_available:
        # Use congestion score directly
        routing_points = placement.congestion_score * 20.0
        notes.append(
            f"Routing feasibility: {routing_points:.1f}/20.0 "
            f"(congestion: {routing.total_congestion:.1f})"
        )
    else:
        # No routing analysis, use placement congestion score
        routing_points = placement.congestion_score * 20.0
        notes.append(f"Routing feasibility: {routing_points:.1f}/20.0 (estimated from placement)")

    total_score = placement_points + drc_points + routing_points

    return total_score, notes


def generate_report(
    pcb_path: Path,
    config_path: Path | None,
    enable_routing: bool,
) -> QualityReport:
    """
    Generate complete quality report.

    Args:
        pcb_path: Path to .kicad_pcb file.
        config_path: Optional path to constraints YAML.
        enable_routing: Whether to perform routing analysis.

    Returns:
        QualityReport with all metrics.
    """
    timestamp = datetime.now().isoformat()

    # Analyze placement
    placement_metrics, netlist, state, context = analyze_placement(pcb_path, config_path)

    # Run DRC
    drc_metrics = run_kicad_drc(pcb_path)

    # Analyze routing if enabled
    routing_metrics = None
    if enable_routing:
        routing_metrics = analyze_routing_demand(state, context)

    # Compute composite score
    score, notes = compute_composite_score(placement_metrics, drc_metrics, routing_metrics)

    # Determine pass/fail (score >= 70 = pass)
    passed = score >= 70.0 and drc_metrics.errors == 0

    return QualityReport(
        input_file=str(pcb_path),
        timestamp=timestamp,
        placement_metrics=placement_metrics,
        drc_metrics=drc_metrics,
        routing_metrics=routing_metrics,
        quality_score=score,
        passed=passed,
        notes=notes,
    )


def print_report(report: QualityReport):
    """Print human-readable report."""
    print("=" * 80)
    print(f"Placement Quality Report")
    print("=" * 80)
    print(f"File: {report.input_file}")
    print(f"Generated: {report.timestamp}")
    print(f"Overall Score: {report.quality_score:.1f}/100.0")
    print(f"Status: {'✓ PASS' if report.passed else '✗ FAIL'}")
    print()

    print("Placement Metrics:")
    print(f"  HPWL: {report.placement_metrics.hpwl_mm:.1f} mm")
    print(f"  Thermal: {report.placement_metrics.thermal_score:.3f}")
    print(f"  Zone Compliance: {report.placement_metrics.zone_compliance_score:.3f}")
    print(f"  HV-LV Clearance: {report.placement_metrics.hv_lv_clearance_score:.3f}")
    print(f"  Loop Area: {report.placement_metrics.loop_area_score:.3f}")
    print(f"  Congestion: {report.placement_metrics.congestion_score:.3f}")
    print(f"  Compactness: {report.placement_metrics.compactness_score:.3f}")
    print(f"  Connectivity: {report.placement_metrics.connectivity_clustering_score:.3f}")
    print(f"  Overall: {report.placement_metrics.overall_placement_score:.3f}")
    print()

    print("DRC Metrics:")
    if report.drc_metrics.drc_available:
        print(f"  Violations: {report.drc_metrics.violations}")
        print(f"  Errors: {report.drc_metrics.errors}")
        print(f"  Warnings: {report.drc_metrics.warnings}")
    else:
        print(f"  ⚠ DRC unavailable: {report.drc_metrics.error_message}")
    print()

    if report.routing_metrics:
        print("Routing Metrics:")
        print(f"  Completion Estimate: {report.routing_metrics.completion_pct:.1f}%")
        print(f"  Total Congestion: {report.routing_metrics.total_congestion:.1f}")
        print(f"  Max Congestion: {report.routing_metrics.max_congestion:.1f}")
        print(f"  Bottlenecks: {report.routing_metrics.bottleneck_count}")
        print(f"  Unrouted Estimate: {report.routing_metrics.unrouted_estimate}")
        if report.routing_metrics.advice:
            print("  Advice:")
            for advice in report.routing_metrics.advice[:5]:  # Top 5
                print(f"    - {advice}")
        print()

    print("Score Breakdown:")
    for note in report.notes:
        print(f"  {note}")
    print()


def report_to_dict(report: QualityReport) -> dict[str, Any]:
    """Convert report to JSON-serializable dict."""
    return {
        "input_file": report.input_file,
        "timestamp": report.timestamp,
        "placement_metrics": asdict(report.placement_metrics),
        "drc_metrics": asdict(report.drc_metrics),
        "routing_metrics": asdict(report.routing_metrics) if report.routing_metrics else None,
        "quality_score": report.quality_score,
        "passed": report.passed,
        "notes": report.notes,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Unified placement quality report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--pcb",
        type=Path,
        required=True,
        help="Path to .kicad_pcb file",
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to constraints YAML (optional, will infer if not provided)",
    )

    parser.add_argument(
        "--route",
        action="store_true",
        help="Enable routing analysis (adds congestion metrics)",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output file (stdout if not specified)",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.pcb.exists():
        print(f"Error: PCB file not found: {args.pcb}", file=sys.stderr)
        sys.exit(1)

    if args.config and not args.config.exists():
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    # Generate report
    try:
        report = generate_report(args.pcb, args.config, args.route)
    except Exception as e:
        print(f"Error generating report: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Output report
    if args.json:
        output_data = json.dumps(report_to_dict(report), indent=2)
        if args.output:
            args.output.write_text(output_data)
        else:
            print(output_data)
    else:
        if args.output:
            # Redirect stdout to file
            import io

            original_stdout = sys.stdout
            sys.stdout = io.StringIO()
            print_report(report)
            output_data = sys.stdout.getvalue()
            sys.stdout = original_stdout
            args.output.write_text(output_data)
        else:
            print_report(report)

    # Exit with appropriate code
    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
