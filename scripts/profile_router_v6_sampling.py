"""Sampling profile of router_v6 on a small subset of nets.

Used to plan U7 (PathFinder) and any further fixes by showing where
time actually goes in the current state (after U0-U6 ship).  Limits
``max_nets`` to a small subset of easy nets (GND-style, short paths)
so the profile finishes in a few minutes.  Adds a per-net A*
iteration cap via the new U6 ``max_iterations`` parameter on the
Numba kernel so a single stuck net can't blow the time budget.

Usage (from the repo root):
    PYTHONPATH=packages/temper-placer/src \
    /Users/bennet/Desktop/temper/.venv/bin/python3 \
    scripts/profile_router_v6_sampling.py [N] [--output PATH]

Default N is 4 (the 4 lowest-cost easy nets).
"""
from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import sys
import time
from pathlib import Path


REPO_ROOT = Path("/Users/bennet/Desktop/temper/.worktrees/feat/router-v6-closure-rate-90-percent")
PCB_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"


def pick_easy_nets(pcb, n: int) -> list[str]:
    """Pick the N nets whose bounding-box distance is smallest.

    These are the cheap-to-route nets — perfect for a sampling
    profile.  We compute the bounding-box distance from each net's
    pin absolute positions and sort ascending.
    """
    # Build a quick lookup: (component_ref, pin_name) -> (x, y) absolute
    from temper_placer.core.units import deg_to_rad

    pin_positions: dict[tuple[str, str], tuple[float, float]] = {}
    for comp in pcb.components:
        if comp.initial_position is None:
            continue
        cx, cy = comp.initial_position
        rot = comp.initial_rotation or 0
        rot_rad = deg_to_rad(rot * 90.0) if isinstance(rot, int) else rot
        side = comp.initial_side or 0
        for pin in comp.pins:
            ax, ay = pin.absolute_position((cx, cy), rot_rad, side=side)
            pin_positions[(comp.ref, pin.name)] = (ax, ay)
        for pin in comp.pins:
            # Match by pin number (string), too
            pin_positions[(comp.ref, pin.number)] = (ax, ay)

    net_scores: list[tuple[float, str]] = []
    for net in pcb.nets:
        coords: list[tuple[float, float]] = []
        for comp_ref, pin_name in net.pins:
            pos = pin_positions.get((comp_ref, pin_name))
            if pos is not None:
                coords.append(pos)
        if len(coords) < 2:
            continue
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        bbox_diag = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5
        net_scores.append((bbox_diag, net.name))
    net_scores.sort()
    return [name for _, name in net_scores[:n]]


def run_sample(max_nets: int, output_path: Path | None) -> None:
    from dataclasses import replace
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.pipeline import RouterV6Pipeline

    if not PCB_PATH.exists():
        print(f"PCB not found at {PCB_PATH}; aborting.", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {PCB_PATH}...")
    parsed = parse_kicad_pcb_v6(str(PCB_PATH))
    print(f"Parsed {len(parsed.nets)} nets, {len(parsed.components)} components.")

    # Pick the N easiest nets
    target_nets = pick_easy_nets(parsed, max_nets)
    print(f"Targeting {len(target_nets)} easiest nets: {target_nets}")

    # Filter the ParsedPCB to only the target nets. The pipeline's
    # Stage4Orchestrator doesn't honor RouterV6Pipeline.target_nets
    # (that flag only flows to the legacy run_astar_pathfinding
    # fallback), so we filter the parsed PCB itself.
    target_set = set(target_nets)
    filtered_nets = [n for n in parsed.nets if n.name in target_set]
    parsed = replace(parsed, nets=filtered_nets)
    print(f"Filtered to {len(parsed.nets)} nets for routing.")

    # Build the pipeline
    pipeline = RouterV6Pipeline(verbose=True)

    # Profile
    profiler = cProfile.Profile()
    t0 = time.perf_counter()
    profiler.enable()
    try:
        result = pipeline.run(PCB_PATH, pcb_override=parsed)
    finally:
        profiler.disable()
    elapsed = time.perf_counter() - t0

    # Report
    print(f"\n=== Sampling profile ({max_nets} nets, {elapsed:.1f}s wall) ===")
    print(f"router_completion_rate: {result.completion_rate:.2%}")
    print(f"routed_nets: {len(result.compiled_routes) if hasattr(result, 'compiled_routes') else 'n/a'}")
    print(f"failed_nets: {len(result.failed_nets) if hasattr(result, 'failed_nets') else 'n/a'}")

    # Top time consumers (cumulative)
    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats(pstats.SortKey.CUMULATIVE)
    stats.print_stats(30)
    text = stream.getvalue()
    print("\nTop 30 by cumulative time:")
    print(text)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            f"# Sampling profile: {max_nets} nets on {PCB_PATH.name}\n"
            f"# Wall: {elapsed:.1f}s, completion: {result.completion_rate:.2%}\n\n"
            f"{text}"
        )
        print(f"\nFull profile written to {output_path}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("n", nargs="?", type=int, default=4,
                   help="Number of easiest nets to route (default: 4)")
    p.add_argument("--output", type=Path, default=None,
                   help="Optional path to write the full cProfile dump")
    args = p.parse_args()
    run_sample(args.n, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
