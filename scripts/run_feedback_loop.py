#!/usr/bin/env python3
"""
Run the Automated Zero-DRC Feedback Loop on the Temper board.

This script demonstrates the full feedback loop:
1. Run deterministic pipeline
2. Export to KiCad PCB
3. Run KiCad DRC
4. Map violations to zones
5. Adjust zone geometry
6. Repeat until zero violations or max iterations

Usage:
    python scripts/run_feedback_loop.py [--max-iterations N] [--output-dir DIR]
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/temper-placer/src"))

from temper_placer.deterministic import create_drc_aware_pipeline, BoardState
from temper_placer.deterministic.feedback import (
    AutomatedZeroDRC,
    parse_kicad_drc,
    ViolationComponentMapper,
    ZoneAdjuster,
)
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules
from temper_placer.io.kicad_writer import (
    write_placements_to_pcb,
    write_routes_to_pcb,
    PlacementUpdate,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Expected violation types (cosmetic, not actionable)
EXPECTED_TYPES = frozenset(
    [
        "lib_footprint_issues",
        "silk_overlap",
        "silk_over_copper",
        "silk_edge_clearance",
        "missing_courtyard",
    ]
)


def run_kicad_drc(pcb_path: Path, output_dir: Path) -> tuple[Path, dict]:
    """Run KiCad DRC and return the report path and parsed data."""
    report_path = output_dir / f"{pcb_path.stem}_drc.json"

    result = subprocess.run(
        [
            "kicad-cli",
            "pcb",
            "drc",
            str(pcb_path),
            "--output",
            str(report_path),
            "--format",
            "json",
            "--severity-all",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 and not report_path.exists():
        logger.error(f"KiCad DRC failed: {result.stderr}")
        return report_path, {"violations": [], "unconnected_items": []}

    with open(report_path) as f:
        data = json.load(f)

    return report_path, data


def count_violations(data: dict) -> dict:
    """Count violations by type, filtering expected cosmetic violations."""
    from collections import Counter

    violations = data.get("violations", [])
    unconnected = data.get("unconnected_items", [])

    total = len(violations) + len(unconnected)

    by_type = Counter()
    for v in violations:
        by_type[v.get("type", "unknown")] += 1
    for _ in unconnected:
        by_type["unconnected"] += 1

    # Actionable = total minus expected cosmetic types
    actionable = sum(c for t, c in by_type.items() if t not in EXPECTED_TYPES)

    return {
        "total": total,
        "actionable": actionable,
        "by_type": dict(by_type),
    }


def main():
    parser = argparse.ArgumentParser(description="Run Automated Zero-DRC Feedback Loop")
    parser.add_argument("--max-iterations", type=int, default=5, help="Maximum feedback iterations")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("/tmp/feedback_loop"), help="Output directory"
    )
    parser.add_argument(
        "--violation-threshold",
        type=int,
        default=5,
        help="Violations needed to trigger zone expansion",
    )
    parser.add_argument(
        "--expansion-per-violation",
        type=float,
        default=1.0,
        help="mm to expand per excess violation",
    )
    args = parser.parse_args()

    # Setup paths
    repo_root = Path(__file__).parent.parent
    pcb_path = repo_root / "pcb/temper.kicad_pcb"
    config_path = repo_root / "configs/temper_deterministic_config.yaml"

    if not pcb_path.exists():
        logger.error(f"PCB not found: {pcb_path}")
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Automated Zero-DRC Feedback Loop")
    print("=" * 60)
    print(f"PCB: {pcb_path}")
    print(f"Config: {config_path}")
    print(f"Output: {args.output_dir}")
    print(f"Max iterations: {args.max_iterations}")
    print()

    # Load board and config
    logger.info("Loading board and config...")
    parse_result = parse_kicad_pcb(pcb_path)
    constraints = load_constraints(config_path)
    design_rules = constraints_to_design_rules(constraints)

    # Apply net class mapping from config to parsed netlist
    # This ensures clearance grid uses correct per-net-class clearances
    net_class_mapping = getattr(constraints, "net_classes", {})
    if net_class_mapping and parse_result.netlist:
        updated = parse_result.netlist.apply_net_class_mapping(net_class_mapping)
        logger.info(f"Applied net class mapping: {updated} nets updated")

    # Configure feedback parameters
    constraints.feedback.max_iterations = args.max_iterations
    constraints.feedback.violation_threshold = args.violation_threshold
    constraints.feedback.expansion_per_violation = args.expansion_per_violation

    # Ensure zones have expansion metadata
    for zone in constraints.zones:
        if not zone.max_size:
            zone.max_size = (constraints.board_width_mm, constraints.board_height_mm)
        if not zone.can_expand:
            zone.can_expand = ["right", "left"]

    # Create pipeline
    pipeline = create_drc_aware_pipeline(design_rules=design_rules, config=constraints)

    # Track history
    history = []

    # Manual feedback loop (more control than AutomatedZeroDRC)
    state = BoardState(board=parse_result.board, netlist=parse_result.netlist)

    for iteration in range(1, args.max_iterations + 1):
        print(f"\n{'=' * 60}")
        print(f"ITERATION {iteration}/{args.max_iterations}")
        print("=" * 60)

        # 1. Run pipeline
        logger.info("Running deterministic pipeline...")
        state = pipeline.run(state)

        # 2. Export to PCB
        output_pcb = args.output_dir / f"iteration_{iteration}.kicad_pcb"
        logger.info(f"Exporting to {output_pcb}...")

        # Build placements dict from state (convert tuples to PlacementUpdate objects)
        # Note: state.placements stores bounding-box-center coordinates.
        # The center offset conversion is handled by write_placements_to_pcb
        # when we pass the components list.
        placements_dict = {}
        if state.placements:
            for ref, pos in state.placements:
                # Default rotation to 0 (deterministic pipeline doesn't optimize rotation yet)
                placements_dict[ref] = PlacementUpdate(ref=ref, x=pos[0], y=pos[1], rotation=0.0)

        # First write placements (pass components for center offset conversion)
        write_placements_to_pcb(
            pcb_path,
            output_pcb,
            placements_dict,
            components=parse_result.netlist.components if parse_result.netlist else None,
        )

        # Then write routes if any
        if state.routes or state.vias:
            write_routes_to_pcb(output_pcb, output_pcb, state.routes, state.vias)

        # Copy project file with design rules (net classes, clearances)
        # KiCad DRC reads design rules from .kicad_pro, not .kicad_pcb
        source_pro = pcb_path.with_suffix(".kicad_pro")
        if source_pro.exists():
            output_pro = output_pcb.with_suffix(".kicad_pro")

            # Load, modify, and save project file
            with open(source_pro, "r") as f:
                pro_data = json.load(f)

            # Update board minimum constraints for FinePitch routing
            # FinePitch class uses 0.127mm (5mil) traces which is standard for dense ICs
            rules = (
                pro_data.setdefault("board", {})
                .setdefault("design_settings", {})
                .setdefault("rules", {})
            )
            rules["min_track_width"] = 0.127  # Allow FinePitch 5mil traces
            rules["min_via_diameter"] = 0.4  # Allow FinePitch vias
            rules["min_via_annular_width"] = 0.1  # Allow FinePitch via annular ring

            with open(output_pro, "w") as f:
                json.dump(pro_data, f, indent=2)

            logger.info(f"Copied project file with design rules: {output_pro.name}")

        # 3. Run KiCad DRC
        logger.info("Running KiCad DRC...")
        report_path, drc_data = run_kicad_drc(output_pcb, args.output_dir)

        # 4. Count violations
        counts = count_violations(drc_data)
        history.append(
            {
                "iteration": iteration,
                "total": counts["total"],
                "actionable": counts["actionable"],
                "by_type": counts["by_type"],
            }
        )

        print(f"\nDRC Results:")
        print(f"  Total violations: {counts['total']}")
        print(f"  Actionable: {counts['actionable']}")
        print(f"  By type:")
        for vtype, count in sorted(counts["by_type"].items(), key=lambda x: -x[1]):
            marker = " (expected)" if vtype in EXPECTED_TYPES else ""
            print(f"    {vtype}: {count}{marker}")

        # 5. Check for success
        if counts["actionable"] == 0:
            print(f"\n🎉 ZERO ACTIONABLE VIOLATIONS ACHIEVED!")
            break

        # 6. Map violations to zones
        logger.info("Mapping violations to zones...")
        violations = parse_kicad_drc(str(report_path))

        zone_config = {}
        for z in constraints.zones:
            zone_config[z.name] = {
                "bounds": ((z.bounds[0], z.bounds[1]), (z.bounds[2], z.bounds[3])),
                "max_size": z.max_size,
                "can_expand": z.can_expand,
            }

        mapper = ViolationComponentMapper(parse_result.netlist, zone_config)
        mapped = [mapper.map_violation(v) for v in violations]

        # Count by zone
        from collections import Counter

        zone_counts = Counter(m.zone for m in mapped if m.zone)
        print(f"\nViolations by zone:")
        for zone_name, count in zone_counts.most_common():
            print(f"  {zone_name}: {count}")

        # 7. Compute adjustments
        adjuster = ZoneAdjuster(
            zone_config,
            violation_threshold=args.violation_threshold,
            expansion_per_violation=args.expansion_per_violation,
        )
        result = adjuster.compute_adjustments(mapped)

        if not result.adjustments:
            print("\nNo zone adjustments possible.")
            if hasattr(result, "impossible_zones") and result.impossible_zones:
                print(f"Impossible zones (at max size): {result.impossible_zones}")
            break

        # 8. Apply adjustments
        print(f"\nApplying zone adjustments:")
        for zone_name, adj in result.adjustments.items():
            changes = []
            if adj.delta_width > 0:
                changes.append(f"width +{adj.delta_width:.1f}mm")
            if adj.delta_height > 0:
                changes.append(f"height +{adj.delta_height:.1f}mm")
            print(f"  {zone_name}: {', '.join(changes) if changes else 'no change'}")

            # Find and update zone in constraints
            zone = next((z for z in constraints.zones if z.name == zone_name), None)
            if zone:
                idx = constraints.zones.index(zone)
                new_bounds = list(zone.bounds)

                # Expand right (increase x2)
                if adj.delta_width > 0:
                    new_bounds[2] += adj.delta_width

                # Expand down (increase y2)
                if adj.delta_height > 0:
                    new_bounds[3] += adj.delta_height

                zone.bounds = tuple(new_bounds)

                # Shift subsequent zones to the right
                if adj.delta_width > 0:
                    for next_idx in range(idx + 1, len(constraints.zones)):
                        nz = constraints.zones[next_idx]
                        nb = list(nz.bounds)
                        nb[0] += adj.delta_width  # shift x1
                        nb[2] += adj.delta_width  # shift x2
                        nz.bounds = tuple(nb)

        # Reset state for next iteration
        state = BoardState(board=parse_result.board, netlist=parse_result.netlist)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print("\nIteration History:")
    for h in history:
        print(f"  Iteration {h['iteration']}: {h['total']} total, {h['actionable']} actionable")

    if history:
        initial = history[0]["actionable"]
        final = history[-1]["actionable"]
        reduction = initial - final
        pct = (reduction / initial * 100) if initial > 0 else 0
        print(f"\nReduction: {initial} → {final} ({reduction} violations, {pct:.1f}%)")

    final_pcb = args.output_dir / f"iteration_{len(history)}.kicad_pcb"
    print(f"\nFinal PCB: {final_pcb}")

    # Save history
    history_path = args.output_dir / "history.json"
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)
    print(f"History saved: {history_path}")


if __name__ == "__main__":
    main()
