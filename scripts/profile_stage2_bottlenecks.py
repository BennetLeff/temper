"""Focused profile of Stage 2 bottleneck functions.

Profile ``extract_channel_skeleton`` and ``compute_channel_widths``
in isolation to find Shapely-specific quick wins.  These two
functions take 69% of the full closure run (40% + 29%) on
``temper.kicad_pcb``.

Usage (from repo root):
    PYTHONPATH=packages/temper-placer/src \\
    /Users/bennet/Desktop/temper/.venv/bin/python3 \\
    scripts/profile_stage2_bottlenecks.py [--output PATH]
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


def profile_skeleton_extraction(parsed, profile: cProfile.Profile) -> dict:
    """Profile ``extract_channel_skeleton`` across F.Cu and B.Cu.

    Returns timing breakdown (per layer).
    """
    from temper_placer.router_v6.routing_space import compute_routing_space
    from temper_placer.router_v6.channel_skeleton import extract_channel_skeleton

    print("Computing routing spaces (F.Cu, B.Cu)...")
    t0 = time.perf_counter()
    routing_spaces = compute_routing_space(parsed)
    print(f"  Routing space: {time.perf_counter()-t0:.2f}s")

    results = {}
    for layer_name in ("F.Cu", "B.Cu"):
        rs = routing_spaces.get(layer_name)
        if rs is None:
            print(f"  {layer_name}: no routing space; skipping")
            continue
        print(f"Profiling extract_channel_skeleton on {layer_name}...")
        t0 = time.perf_counter()
        profile.enable()
        try:
            skel = extract_channel_skeleton(rs, pcb=parsed)
        finally:
            profile.disable()
        elapsed = time.perf_counter() - t0
        results[layer_name] = (elapsed, skel, rs)
        print(f"  {layer_name}: {elapsed:.2f}s, {skel.node_count} nodes")
    return results


def profile_channel_widths(skeleton_results: dict, profile: cProfile.Profile) -> dict:
    """Profile ``compute_channel_widths`` across F.Cu and B.Cu."""
    from temper_placer.router_v6.channel_widths import compute_channel_widths

    results = {}
    for layer_name, (skel_time, skel, rs) in skeleton_results.items():
        print(f"Profiling compute_channel_widths on {layer_name}...")
        t0 = time.perf_counter()
        profile.enable()
        try:
            cw = compute_channel_widths(rs, skel)
        finally:
            profile.disable()
        elapsed = time.perf_counter() - t0
        results[layer_name] = (elapsed, cw)
        print(f"  {layer_name}: {elapsed:.2f}s, min_w={cw.min_width:.2f}, max_w={cw.max_width:.2f}")
    return results


def report(profile: cProfile.Profile, output_path: Path | None) -> None:
    stream = io.StringIO()
    stats = pstats.Stats(profile, stream=stream)
    stats.sort_stats(pstats.SortKey.CUMULATIVE)
    stats.print_stats(50)
    text = stream.getvalue()
    print("\n=== Top 50 by cumulative time (Stage 2 bottlenecks) ===")
    print(text)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            f"# Stage 2 bottleneck profile: {PCB_PATH.name}\n\n{text}"
        )
        print(f"\nFull profile written to {output_path}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=None,
                   help="Optional path to write the full cProfile dump")
    args = p.parse_args()

    if not PCB_PATH.exists():
        print(f"PCB not found at {PCB_PATH}; aborting.", file=sys.stderr)
        sys.exit(1)

    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    print(f"Parsing {PCB_PATH}...")
    parsed = parse_kicad_pcb_v6(str(PCB_PATH))
    print(f"Parsed {len(parsed.nets)} nets, {len(parsed.components)} components.")

    profile = cProfile.Profile()
    skel_results = profile_skeleton_extraction(parsed, profile)
    width_results = profile_channel_widths(skel_results, profile)
    report(profile, args.output)

    total_skel = sum(t for t, _, _ in skel_results.values())
    total_width = sum(t for t, _ in width_results.values())
    print(f"\n=== Summary ===")
    print(f"extract_channel_skeleton total: {total_skel:.2f}s")
    print(f"compute_channel_widths   total: {total_width:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
