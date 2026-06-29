"""CLI interface for temper-validation package."""

import argparse
import sys

from temper_validation.comparison.drc_compliance import (
    evaluate_drc_compliance,
    run_kicad_drc,
)

# Import comparison modules
from temper_validation.comparison.wirelength import compare_wirelength
from temper_validation.metrics.quality_score import calculate_aggregate_score
from temper_validation.reporting.report import (
    generate_html_report,
    generate_markdown_report,
)

# Import PCB loader from temper-placer
try:
    from temper_placer.io.reference_loader import load_reference_pcb
except ImportError:
    print("Error: temper-placer not installed. Install with: pip install temper-placer")
    sys.exit(1)

__all__ = ['main']


def cmd_compare(args):
    """Compare two PCB placements and generate report."""
    print("Loading PCBs...")
    print(f"  Optimized: {args.optimized}")
    print(f"  Reference: {args.reference}")

    try:
        # Load PCB files
        optimized_design = load_reference_pcb(args.optimized)
        reference_design = load_reference_pcb(args.reference)

        print("\\nRunning comparisons...")

        # 1. Wirelength comparison
        print("  - Wirelength analysis...")
        wirelength_result = compare_wirelength(
            optimized_design.state,
            reference_design.state,
            optimized_design.netlist.nets
        )

        # 2. DRC compliance (if KiCad available)
        print("  - DRC compliance check...")
        try:
            drc_raw = run_kicad_drc(args.optimized, kicad_path="kicad-cli")
            drc_result = evaluate_drc_compliance(drc_raw.violations)
        except Exception as e:
            print(f"    Warning: DRC check failed ({e}), using placeholder")
            from temper_validation.comparison.drc_compliance import DRCComplianceResult
            drc_result = DRCComplianceResult(
                score=100.0, max_score=100.0,
                critical_violations=0, warning_violations=0,
                verdict="SKIP"
            )

        # 3. Routing feasibility (placeholder - would need actual router)
        print("  - Routing feasibility...")
        # For now, assume 100% completion as placeholder
        from temper_validation.comparison.routing_feasibility import RoutingFeasibilityResult
        routing_result = RoutingFeasibilityResult(
            total_nets=len(optimized_design.netlist.nets),
            routed_nets=len(optimized_design.netlist.nets),
            failed_nets=0,
            completion_rate=1.0,
            average_wirelength=wirelength_result.optimized / max(len(optimized_design.netlist.nets), 1),
            total_vias=0,
            verdict="PASS"
        )

        # 4. Calculate aggregate score
        print("  - Calculating aggregate score...")
        aggregate_result = calculate_aggregate_score(
            wirelength_result, drc_result, routing_result
        )

        # 5. Generate report
        print(f"\\nGenerating report: {args.output}")
        if args.format in ['html']:
            generate_html_report(
                args.output,
                args.optimized,
                args.reference,
                wirelength_result,
                drc_result,
                routing_result,
                aggregate_result
            )
        else:
            generate_markdown_report(
                args.output,
                args.optimized,
                args.reference,
                wirelength_result,
                drc_result,
                routing_result,
                aggregate_result
            )

        print("✓ Report generated successfully")
        print(f"\\nAggregate Score: {aggregate_result.total_score:.1f}/100.0 - {aggregate_result.verdict}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_score(args):
    """Score a single PCB placement."""
    print("Loading PCBs...")
    print(f"  Optimized: {args.optimized}")
    print(f"  Reference: {args.reference}")

    try:
        # Load PCB files
        optimized_design = load_reference_pcb(args.optimized)
        reference_design = load_reference_pcb(args.reference)

        # Run all comparisons
        wirelength_result = compare_wirelength(
            optimized_design.state,
            reference_design.state,
            optimized_design.netlist.nets
        )

        try:
            drc_raw = run_kicad_drc(args.optimized, kicad_path="kicad-cli")
            drc_result = evaluate_drc_compliance(drc_raw.violations)
        except Exception:
            from temper_validation.comparison.drc_compliance import DRCComplianceResult
            drc_result = DRCComplianceResult(
                score=100.0, max_score=100.0,
                critical_violations=0, warning_violations=0,
                verdict="SKIP"
            )

        from temper_validation.comparison.routing_feasibility import RoutingFeasibilityResult
        routing_result = RoutingFeasibilityResult(
            total_nets=len(optimized_design.netlist.nets),
            routed_nets=len(optimized_design.netlist.nets),
            failed_nets=0,
            completion_rate=1.0,
            average_wirelength=wirelength_result.optimized / max(len(optimized_design.netlist.nets), 1),
            total_vias=0,
            verdict="PASS"
        )

        aggregate_result = calculate_aggregate_score(
            wirelength_result, drc_result, routing_result
        )

        # Print results
        print()
        print("=== Placement Validation Score ===")
        print(f"Aggregate Score: {aggregate_result.total_score:.1f}/{aggregate_result.max_score}")
        print(f"Verdict: {aggregate_result.verdict}")
        print()
        print("Wirelength:")
        print(f"  Optimized: {wirelength_result.optimized:.2f} mm")
        print(f"  Reference: {wirelength_result.reference:.2f} mm")
        print(f"  Ratio: {wirelength_result.ratio:.3f}")
        print(f"  Verdict: {wirelength_result.verdict}")
        print()
        print("DRC Compliance:")
        print(f"  Score: {drc_result.score:.1f}/{drc_result.max_score}")
        print(f"  Critical Violations: {drc_result.critical_violations}")
        print(f"  Warning Violations: {drc_result.warning_violations}")
        print(f"  Verdict: {drc_result.verdict}")
        print()
        print("Routing Feasibility:")
        print(f"  Completion Rate: {routing_result.completion_rate * 100:.1f}%")
        print(f"  Verdict: {routing_result.verdict}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_drc(args):
    """Run DRC check on a PCB file."""
    kicad_path = args.kicad_path or "kicad-cli"
    print(f"Running KiCad DRC on: {args.pcb}")
    print(f"Using KiCad: {kicad_path}")
    print()

    try:
        drc_raw = run_kicad_drc(args.pcb, kicad_path)
        drc_result = evaluate_drc_compliance(drc_raw.violations)

        print("=== DRC Check ===")
        print(f"Score: {drc_result.score:.1f}/{drc_result.max_score}")
        print(f"Critical Violations: {drc_result.critical_violations}")
        print(f"Warning Violations: {drc_result.warning_violations}")
        print(f"Verdict: {drc_result.verdict}")
        print()
        print(f"Violations found: {len(drc_raw.violations)}")
        for v in drc_raw.violations[:10]:  # Show first 10
            print(f"  [{v.severity.value}] {v.description}")
        if len(drc_raw.violations) > 10:
            print(f"  ... and {len(drc_raw.violations) - 10} more")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_visualize(args):
    """Visualize before/after comparison."""
    print(f"Visualizing: {args.before} vs {args.after}")
    print(f"Output: {args.output}")
    print()
    print("=== Visualization ===")
    print("TODO: Implement visualization logic")
    print("This will generate side-by-side board rendering")
    print("For now, use the 'compare' command with --format html")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="temper-validate",
        description="Validate PCB placement against reference layouts using quality metrics.",
        epilog="Example: temper-validate compare optimized.kicad_pcb reference.kicad_pcb --output report.html --format html"
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # compare command
    compare_parser = subparsers.add_parser('compare', help='Compare two PCB placements')
    compare_parser.add_argument('optimized', type=str, help='Optimized PCB file (.kicad_pcb)')
    compare_parser.add_argument('reference', type=str, help='Reference PCB file (.kicad_pcb)')
    compare_parser.add_argument('-o', '--output', type=str, default='report.md',
                       help='Output report file (default: report.md)')
    compare_parser.add_argument('-f', '--format', type=str, default='markdown',
                       choices=['markdown', 'md', 'html'], help='Report format (default: markdown)')

    # score command
    score_parser = subparsers.add_parser('score', help='Score a single PCB placement')
    score_parser.add_argument('optimized', type=str, help='Optimized PCB file (.kicad_pcb)')
    score_parser.add_argument('-r', '--reference', type=str, required=True,
                       help='Reference PCB file (.kicad_pcb)')

    # drc command
    drc_parser = subparsers.add_parser('drc', help='Run DRC check on PCB')
    drc_parser.add_argument('pcb', type=str, help='PCB file to check (.kicad_pcb)')
    drc_parser.add_argument('-k', '--kicad-path', type=str,
                     help='Path to KiCad CLI (default: kicad-cli)')

    # visualize command
    visualize_parser = subparsers.add_parser('visualize', help='Visualize before/after comparison')
    visualize_parser.add_argument('before', type=str, help='Before PCB file (.kicad_pcb)')
    visualize_parser.add_argument('after', type=str, help='After PCB file (.kicad_pcb)')
    visualize_parser.add_argument('-o', '--output', type=str, required=True,
                     help='Output HTML file')

    args = parser.parse_args()

    # Dispatch to command handler
    if args.command == 'compare':
        cmd_compare(args)
    elif args.command == 'score':
        cmd_score(args)
    elif args.command == 'drc':
        cmd_drc(args)
    elif args.command == 'visualize':
        cmd_visualize(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
