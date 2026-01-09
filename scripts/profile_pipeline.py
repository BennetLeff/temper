#!/usr/bin/env python3
"""
Profile the full pipeline with timeout detection and detailed stage timing.
"""

import sys
import time
import cProfile
import pstats
import io
from pathlib import Path

# Add temper-placer to path
sys.path.insert(0, "packages/temper-placer/src")

from temper_placer.deterministic import create_drc_aware_pipeline
from temper_placer.deterministic.state import BoardState
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_metadata import extract_kicad_metadata
from temper_placer.io.config_loader import load_constraints


def profile_pipeline():
    """Run pipeline with profiling and timeout detection."""

    print("=" * 70)
    print("PIPELINE PROFILER WITH TIMEOUT DETECTION")
    print("=" * 70)

    # Load config
    config_path = Path("configs/temper_deterministic_config.yaml")
    print(f"\nLoading config from {config_path}")
    config = load_constraints(config_path)
    print(f"  Differential pairs: {len(config.differential_pairs)}")
    for dp in config.differential_pairs:
        print(f"    - {dp.net_pos}/{dp.net_neg} spacing={dp.spacing_mm}mm")

    # Load board
    board_path = Path("pcb/temper.kicad_pcb")
    print(f"\nLoading board from {board_path}")
    result = parse_kicad_pcb(board_path)
    print(f"  Components: {len(result.netlist.components)}")
    print(f"  Nets: {len(result.netlist.nets)}")

    # Extract metadata
    metadata = extract_kicad_metadata(board_path)
    print(f"  Metadata: {len(metadata.courtyards)} courtyards, {len(metadata.pad_sizes)} pads")

    # Create initial state
    initial_state = BoardState(
        netlist=result.netlist,
        board=result.board,
    )

    # Create pipeline - pass parsed pads for correct DRC positions
    print("\nCreating pipeline...")
    pipeline = create_drc_aware_pipeline(
        config=config,
        metadata=metadata,
        parsed_pads=result.pads,  # Use actual KiCad pad positions for DRC
    )

    print(f"  Stages: {len(pipeline.stages)}")
    for i, stage in enumerate(pipeline.stages):
        print(f"    {i + 1}. {stage.name}")

    # Profile each stage
    print("\n" + "=" * 70)
    print("PROFILING STAGES")
    print("=" * 70)

    stage_times = []
    total_start = time.time()

    state = initial_state

    for i, stage in enumerate(pipeline.stages):
        stage_name = stage.name
        print(f"\n[Stage {i + 1}/{len(pipeline.stages)}] {stage_name}")
        print("-" * 70)

        stage_start = time.time()

        # Run stage with profiling
        profiler = cProfile.Profile()
        profiler.enable()

        try:
            state = stage.run(state)

            profiler.disable()
            stage_elapsed = time.time() - stage_start
            stage_times.append((stage_name, stage_elapsed))

            print(f"  ✓ Completed in {stage_elapsed:.2f}s")

            # Show top time consumers for this stage
            s = io.StringIO()
            ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
            ps.print_stats(15)  # Top 15 functions

            print("\n  Top 15 time consumers:")
            lines = s.getvalue().split("\n")
            # Find where the stats start (after header)
            stats_start = 0
            for idx, line in enumerate(lines):
                if "ncalls" in line or "filename" in line:
                    stats_start = idx + 1
                    break

            for line in lines[stats_start : stats_start + 15]:
                if line.strip():
                    print(f"    {line}")

            # Timeout warning
            if stage_elapsed > 30:
                print(f"\n  ⚠️  WARNING: Stage took {stage_elapsed:.1f}s (>30s threshold)")
            elif stage_elapsed > 60:
                print(f"\n  🔥 CRITICAL: Stage took {stage_elapsed:.1f}s (>60s threshold)")

        except Exception as e:
            profiler.disable()
            stage_elapsed = time.time() - stage_start
            print(f"  ✗ FAILED after {stage_elapsed:.2f}s: {e}")
            raise

    total_elapsed = time.time() - total_start

    # Summary
    print("\n" + "=" * 70)
    print("TIMING SUMMARY")
    print("=" * 70)

    print(f"\nTotal time: {total_elapsed:.2f}s ({total_elapsed / 60:.1f} minutes)")
    print(f"\nStage breakdown:")

    for stage_name, stage_time in sorted(stage_times, key=lambda x: x[1], reverse=True):
        pct = (stage_time / total_elapsed) * 100
        bar_len = int(pct / 2)
        bar = "█" * bar_len
        print(f"  {stage_name:40s} {stage_time:7.2f}s ({pct:5.1f}%) {bar}")

    # Identify bottlenecks
    print("\n" + "=" * 70)
    print("BOTTLENECK ANALYSIS")
    print("=" * 70)

    slow_stages = [(name, t) for name, t in stage_times if t > 10]
    if slow_stages:
        print("\nStages taking >10s:")
        for name, t in sorted(slow_stages, key=lambda x: x[1], reverse=True):
            print(f"  • {name}: {t:.1f}s")
    else:
        print("\nNo stages taking >10s")

    very_slow_stages = [(name, t) for name, t in stage_times if t > 30]
    if very_slow_stages:
        print("\n⚠️  TIMEOUT RISK - Stages taking >30s:")
        for name, t in sorted(very_slow_stages, key=lambda x: x[1], reverse=True):
            print(f"  • {name}: {t:.1f}s")

    critical_stages = [(name, t) for name, t in stage_times if t > 60]
    if critical_stages:
        print("\n🔥 CRITICAL TIMEOUT - Stages taking >60s:")
        for name, t in sorted(critical_stages, key=lambda x: x[1], reverse=True):
            print(f"  • {name}: {t:.1f}s")

    print("\n" + "=" * 70)
    return state


if __name__ == "__main__":
    try:
        final_state = profile_pipeline()
        print("\n✓ Pipeline completed successfully")
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Pipeline failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
