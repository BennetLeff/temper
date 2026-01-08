#!/usr/bin/env python3
"""
Demo: Running the full deterministic pipeline with constraint-aware placement.

This script demonstrates:
1. Loading a PCB and configuration
2. Running the MVP3 pipeline with PhasedComponentAssignmentStage
3. Checking constraint satisfaction in the final placement
4. Comparing phased vs simple placement

Usage:
    python3 demo_integrated_pipeline.py
"""

from pathlib import Path
import tempfile
import time

from temper_placer.pipeline.mvp3_runner import MVP3Runner, MVP3Config
from temper_placer.io.config_loader import load_constraints
from temper_placer.constraints import ConstraintReporter


def demo_phased_placement():
    """Run pipeline with phased constraint-aware placement."""
    print("=" * 70)
    print("DEMO: Constraint-Aware Placement in Full Pipeline")
    print("=" * 70)

    # Paths
    project_root = Path(__file__).parents[3]
    config_path = project_root / "configs" / "temper_deterministic_config.yaml"
    pcb_path = project_root / "pcb" / "temper_agent_optimized.kicad_pcb"

    if not config_path.exists():
        print(f"❌ Config not found: {config_path}")
        return

    if not pcb_path.exists():
        print(f"❌ PCB not found: {pcb_path}")
        return

    print(f"\n📁 Input files:")
    print(f"  Config: {config_path.name}")
    print(f"  PCB:    {pcb_path.name}")

    # Load constraints to show what's configured
    print(f"\n📋 Loading constraints...")
    constraints = load_constraints(config_path)

    print(f"  Board: {constraints.board_width_mm}x{constraints.board_height_mm}mm")
    print(f"  Zones: {len(constraints.zones)} ({', '.join(z.name for z in constraints.zones)})")
    print(f"  Spacing rules: {len(constraints.component_spacing_rules)}")
    print(f"  Groups: {len(constraints.component_groups)}")

    # Show sample constraints
    if constraints.component_spacing_rules:
        print(f"\n  📏 Sample spacing rules:")
        for rule in constraints.component_spacing_rules[:3]:
            print(
                f"    • {rule.component_a} <-> {rule.component_b}: "
                f"{rule.min_separation_mm}mm [{rule.tier}]"
            )

    if constraints.component_groups:
        print(f"\n  🔗 Sample groups:")
        for group in constraints.component_groups[:2]:
            print(f"    • {group.name}: {', '.join(group.components[:4])}")
            if group.proximity_rules:
                for prox in group.proximity_rules[:2]:
                    print(
                        f"      → {prox.component_a} <-> {prox.component_b}: "
                        f"max {prox.max_distance_mm}mm [{prox.tier}]"
                    )

    # Run pipeline with phased placement
    print(f"\n⚙️  Running pipeline with PhasedComponentAssignmentStage...")
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "output_phased.kicad_pcb"

        config = MVP3Config(
            use_phased_placement=True,  # Enable constraint-aware placement
            slot_spacing_mm=12.0,
            cell_size_mm=0.25,
            layer_count=4,
        )

        runner = MVP3Runner(
            pcb_path=pcb_path,
            config_path=config_path,
            output_path=output_path,
            mvp3_config=config,
        )

        start = time.perf_counter()
        try:
            result = runner.run()
            elapsed = time.perf_counter() - start

            print(f"\n✅ Pipeline completed in {elapsed:.2f}s")
            print(f"\n📊 Results:")
            print(f"  Components placed: {result.components_placed}/{result.total_components}")
            print(f"  Nets routed:       {result.nets_routed}/{result.total_nets}")
            print(f"  Success:           {result.success}")

            if result.error:
                print(f"  ⚠️  Error: {result.error}")

            # Note: To check constraint satisfaction, we would need to:
            # 1. Extract final placements from the output PCB
            # 2. Run ConstraintReporter.check(placements)
            # This is left as an exercise - see test_constraint_placement.py

        except Exception as e:
            print(f"\n❌ Pipeline failed: {e}")
            import traceback

            traceback.print_exc()


def demo_comparison():
    """Compare phased vs simple placement (timing only)."""
    print("\n" + "=" * 70)
    print("COMPARISON: Phased vs Simple Placement")
    print("=" * 70)

    project_root = Path(__file__).parents[3]
    config_path = project_root / "configs" / "temper_deterministic_config.yaml"
    pcb_path = project_root / "pcb" / "temper_agent_optimized.kicad_pcb"

    if not config_path.exists() or not pcb_path.exists():
        print("❌ Input files not found")
        return

    # Test both modes
    modes = [
        ("Phased (constraint-aware)", True),
        ("Simple (greedy)", False),
    ]

    results = {}

    for mode_name, use_phased in modes:
        print(f"\n🔄 Testing {mode_name}...")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / f"output_{mode_name}.kicad_pcb"

            config = MVP3Config(
                use_phased_placement=use_phased,
                slot_spacing_mm=12.0,
            )

            runner = MVP3Runner(
                pcb_path=pcb_path,
                config_path=config_path,
                output_path=output_path,
                mvp3_config=config,
            )

            start = time.perf_counter()
            try:
                result = runner.run()
                elapsed = time.perf_counter() - start

                results[mode_name] = {
                    "time": elapsed,
                    "placed": result.components_placed,
                    "routed": result.nets_routed,
                    "success": result.success,
                }

                print(f"  ✓ Completed in {elapsed:.2f}s")
                print(f"    Placed: {result.components_placed}, Routed: {result.nets_routed}")

            except Exception as e:
                print(f"  ✗ Failed: {e}")
                results[mode_name] = {"time": None, "error": str(e)}

    # Compare
    print(f"\n📈 Comparison:")
    print(f"  {'Mode':<30} {'Time (s)':>10} {'Placed':>8} {'Routed':>8}")
    print(f"  {'-' * 30} {'-' * 10} {'-' * 8} {'-' * 8}")

    for mode_name, data in results.items():
        if data.get("time"):
            print(
                f"  {mode_name:<30} {data['time']:>10.2f} {data.get('placed', '-'):>8} {data.get('routed', '-'):>8}"
            )
        else:
            print(f"  {mode_name:<30} {'ERROR':>10}")

    print(f"\n💡 Note: Both modes should produce valid placements.")
    print(f"   Phased placement additionally respects hard/soft constraints.")


def main():
    """Run all demos."""
    demo_phased_placement()

    # Uncomment to run comparison (takes longer)
    # demo_comparison()

    print(f"\n" + "=" * 70)
    print("✨ Demo complete!")
    print("=" * 70)
    print(f"\n📚 See also:")
    print(f"  • demo_constraint_builder.py  - Build constraints programmatically")
    print(f"  • demo_constraint_reporting.py - Check constraint satisfaction")
    print(f"  • test_phased_stage_integration.py - Integration tests")


if __name__ == "__main__":
    main()
