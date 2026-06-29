#!/usr/bin/env python3
"""
Demo: Running the full deterministic pipeline with constraint-aware placement.

This script demonstrates:
1. Loading a PCB and configuration
2. Running the deterministic pipeline with PhasedComponentAssignmentStage
3. Checking constraint satisfaction in the final placement
4. Comparing phased vs simple placement

Usage:
    python3 demo_integrated_pipeline.py
"""

import time
from pathlib import Path

from temper_placer.constraints import ConstraintReporter
from temper_placer.deterministic import BoardState, create_drc_aware_pipeline
from temper_placer.io.config_loader import constraints_to_design_rules, load_constraints
from temper_placer.io.kicad_metadata import extract_kicad_metadata
from temper_placer.io.kicad_parser import parse_kicad_pcb


def demo_phased_placement():
    """Run pipeline with phased constraint-aware placement."""
    print("=" * 70)
    print("DEMO: Constraint-Aware Placement in Deterministic Pipeline")
    print("=" * 70)

    # Paths
    project_root = Path(__file__).parents[3]
    config_path = project_root / "configs" / "temper_deterministic_config.yaml"
    pcb_path = project_root / "pcb" / "temper_agent_optimized.kicad_pcb"

    if not config_path.exists():
        print(f"Config not found: {config_path}")
        return

    if not pcb_path.exists():
        print(f"PCB not found: {pcb_path}")
        return

    print("\nInput files:")
    print(f"  Config: {config_path.name}")
    print(f"  PCB:    {pcb_path.name}")

    # Load constraints to show what's configured
    print("\nLoading constraints...")
    constraints = load_constraints(config_path)

    print(f"  Board: {constraints.board_width_mm}x{constraints.board_height_mm}mm")
    print(f"  Zones: {len(constraints.zones)} ({', '.join(z.name for z in constraints.zones)})")
    print(f"  Spacing rules: {len(constraints.component_spacing_rules)}")
    print(f"  Groups: {len(constraints.component_groups)}")

    # Show sample constraints
    if constraints.component_spacing_rules:
        print("\n  Sample spacing rules:")
        for rule in constraints.component_spacing_rules[:3]:
            print(
                f"    - {rule.component_a} <-> {rule.component_b}: "
                f"{rule.min_separation_mm}mm [{rule.tier}]"
            )

    if constraints.component_groups:
        print("\n  Sample groups:")
        for group in constraints.component_groups[:2]:
            print(f"    - {group.name}: {', '.join(group.components[:4])}")
            if group.proximity_rules:
                for prox in group.proximity_rules[:2]:
                    print(
                        f"      -> {prox.component_a} <-> {prox.component_b}: "
                        f"max {prox.max_distance_mm}mm [{prox.tier}]"
                    )

    # Load PCB and metadata
    print("\nLoading PCB...")
    parse_result = parse_kicad_pcb(pcb_path)
    design_rules = constraints_to_design_rules(constraints)
    metadata = extract_kicad_metadata(pcb_path)

    print(f"  Components: {len(parse_result.netlist.components)}")
    print(f"  Nets: {len(parse_result.netlist.nets)}")
    print(f"  Board: {metadata.board_width}x{metadata.board_height}mm")

    # Create pipeline with constraint-aware placement
    print("\nCreating pipeline with PhasedComponentAssignmentStage...")
    pipeline = create_drc_aware_pipeline(
        design_rules=design_rules,
        config=constraints,
        metadata=metadata,
        zone_aware=True,
    )

    # Show which stages are in the pipeline
    stage_names = [s.name for s in pipeline.stages]
    print(f"\n  Pipeline stages ({len(stage_names)}):")
    for i, name in enumerate(stage_names[:8], 1):
        print(f"    {i}. {name}")
    if len(stage_names) > 8:
        print(f"    ... and {len(stage_names) - 8} more")

    # Check if we're using phased placement
    if "phased_component_assignment" in stage_names:
        print("\n  Using PhasedComponentAssignmentStage (constraint-aware)")
    else:
        print("\n  Using ComponentAssignmentStage (simple greedy)")

    # Run placement stages only for demo
    print("\nRunning placement stages...")
    initial_state = BoardState(board=parse_result.board, netlist=parse_result.netlist)
    state = initial_state

    start = time.perf_counter()
    try:
        # Run placement stages (first 6 stages typically)
        for stage in pipeline.stages[:6]:
            stage_start = time.perf_counter()
            state = stage.run(state)
            stage_time = time.perf_counter() - stage_start
            print(f"    {stage.name}: {stage_time:.3f}s")

        elapsed = time.perf_counter() - start

        print(f"\nPlacement completed in {elapsed:.2f}s")
        print("\nResults:")

        if state.placements:
            placements_dict = dict(state.placements)
            print(f"  Components placed: {len(placements_dict)}")

            # Check constraint satisfaction
            print("\nConstraint satisfaction:")
            reporter = ConstraintReporter(constraints)
            report = reporter.check(placements_dict)

            violations = report.violations
            warnings = report.warnings
            satisfied = report.satisfied

            print(f"  Satisfied: {len(satisfied)}")
            print(f"  Warnings (soft): {len(warnings)}")
            print(f"  Violations (hard): {len(violations)}")

            if violations:
                print("\n  Hard violations:")
                for v in violations[:5]:
                    print(f"    - {v.constraint_type}: {v.message}")
                if len(violations) > 5:
                    print(f"    ... and {len(violations) - 5} more")

            if warnings:
                print("\n  Soft constraint warnings:")
                for w in warnings[:3]:
                    print(f"    - {w.constraint_type}: {w.message}")
                if len(warnings) > 3:
                    print(f"    ... and {len(warnings) - 3} more")

        else:
            print("  No placements generated")

    except Exception as e:
        print(f"\nPipeline failed: {e}")
        import traceback

        traceback.print_exc()


def demo_comparison():
    """Compare phased vs simple placement."""
    print("\n" + "=" * 70)
    print("COMPARISON: Phased vs Simple Placement")
    print("=" * 70)

    project_root = Path(__file__).parents[3]
    config_path = project_root / "configs" / "temper_deterministic_config.yaml"
    pcb_path = project_root / "pcb" / "temper_agent_optimized.kicad_pcb"

    if not config_path.exists() or not pcb_path.exists():
        print("Input files not found")
        return

    # Load data once
    parse_result = parse_kicad_pcb(pcb_path)
    constraints = load_constraints(config_path)
    design_rules = constraints_to_design_rules(constraints)
    metadata = extract_kicad_metadata(pcb_path)
    reporter = ConstraintReporter(constraints)

    results = {}

    # Test with constraints (phased placement)
    print("\nTesting Phased (constraint-aware)...")
    pipeline_phased = create_drc_aware_pipeline(
        design_rules=design_rules,
        config=constraints,
        metadata=metadata,
    )

    state = BoardState(board=parse_result.board, netlist=parse_result.netlist)
    start = time.perf_counter()
    for stage in pipeline_phased.stages[:6]:
        state = stage.run(state)
    elapsed = time.perf_counter() - start

    if state.placements:
        placements_dict = dict(state.placements)
        report = reporter.check(placements_dict)
        results["Phased"] = {
            "time": elapsed,
            "placed": len(placements_dict),
            "violations": len(report.violations),
            "warnings": len(report.warnings),
        }
        print(f"  Completed in {elapsed:.2f}s, {len(placements_dict)} placed")

    # Test without constraints (simple placement)
    print("\nTesting Simple (greedy)...")
    pipeline_simple = create_drc_aware_pipeline(
        design_rules=design_rules,
        config=None,  # No constraints -> uses ComponentAssignmentStage
        metadata=metadata,
    )

    state = BoardState(board=parse_result.board, netlist=parse_result.netlist)
    start = time.perf_counter()
    for stage in pipeline_simple.stages[:6]:
        state = stage.run(state)
    elapsed = time.perf_counter() - start

    if state.placements:
        placements_dict = dict(state.placements)
        report = reporter.check(placements_dict)
        results["Simple"] = {
            "time": elapsed,
            "placed": len(placements_dict),
            "violations": len(report.violations),
            "warnings": len(report.warnings),
        }
        print(f"  Completed in {elapsed:.2f}s, {len(placements_dict)} placed")

    # Compare
    print("\nComparison:")
    print(f"  {'Mode':<20} {'Time (s)':>10} {'Placed':>8} {'Violations':>12} {'Warnings':>10}")
    print(f"  {'-' * 20} {'-' * 10} {'-' * 8} {'-' * 12} {'-' * 10}")

    for mode_name, data in results.items():
        print(
            f"  {mode_name:<20} {data['time']:>10.2f} {data['placed']:>8} "
            f"{data['violations']:>12} {data['warnings']:>10}"
        )

    print("\nNote: Phased placement should have fewer violations by respecting constraints.")


def main():
    """Run demos."""
    demo_phased_placement()

    # Uncomment to run comparison
    # demo_comparison()

    print("\n" + "=" * 70)
    print("Demo complete!")
    print("=" * 70)
    print("\nSee also:")
    print("  - demo_constraint_builder.py  - Build constraints programmatically")
    print("  - demo_constraint_reporting.py - Check constraint satisfaction")
    print("  - tests/integration/test_phased_placement_pipeline.py - Integration tests")


if __name__ == "__main__":
    main()
