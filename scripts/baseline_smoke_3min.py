"""Mini-baseline smoke: 3-minute bounded run on temper.kicad_pcb.

Captures a partial SM1 (the easy nets) and a wall-time estimate
without running the full 30+ min closure test.  Useful as a
"is the system alive and what does it look like right now" check,
NOT as a real baseline.

How it bounds the budget:
- A per-A*-call iteration cap (``max_iter`` arg) prevents a
  single hard net from blowing the time.  With 10k iters and
  Numba A* (~50ns/op) that's ~0.5s per A* call.  Worst case
  with rip-up retries: 3 retries × 10k = 30k iters × 50ns = 1.5s
  per net.  24 nets × 1.5s = 36s for A* plus 3s Stage 2 = 39s.
  Real worst case is higher (hard nets hit the cap and fail),
  but well under 3 min.
- No signal-based interruption.  The hard nets just fail to
  route within ``max_iter`` and count as failed.

Limitations:
- Result is a LOWER BOUND on completion rate (hard nets that
  would have routed with more time count as failed)
- The closure test gate (SM1/SM2/SM6) is not exercised; this
  is a smoke check of RouterV6Pipeline end-to-end
- The 33% completion floor is a legacy fixture number; the
  real baseline requires the full closure test

Usage (from repo root):
    PYTHONPATH=packages/temper-placer/src \\
    /Users/bennet/Desktop/temper/.venv/bin/python3 \\
    scripts/baseline_smoke_3min.py [--budget 180] [--max-iter 10000] \\
                                    [--output PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path("/Users/bennet/Desktop/temper/.worktrees/feat/router-v6-closure-rate-90-percent")
PCB_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"


@dataclass
class MiniBaseline:
    """Result of the bounded run."""
    wall_seconds: float = 0.0
    routed_nets: list[str] = field(default_factory=list)
    failed_nets: list[str] = field(default_factory=list)
    completion_rate: float = 0.0
    notes: str = ""


def run_mini_baseline(max_iter: int) -> MiniBaseline:
    """Run RouterV6Pipeline on temper.kicad_pcb with a per-A* cap."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.pipeline import RouterV6Pipeline
    from temper_placer.router_v6.astar_core_numba import _astar_search_numba

    result = MiniBaseline()

    if not PCB_PATH.exists():
        result.notes = f"PCB not found at {PCB_PATH}"
        return result

    print(f"Parsing {PCB_PATH}...")
    parsed = parse_kicad_pcb_v6(str(PCB_PATH))
    print(f"Parsed {len(parsed.nets)} nets, {len(parsed.components)} components.")
    print(f"Per-A* cap: {max_iter} iterations (hard nets fail to route, count as failed)")
    print(f"skip_stage3=True (saves the 5s SAT timeout per cycle)")

    # Monkey-patch the Numba kernel's max_iterations default to
    # bound the worst-case A* cost.  The kernel signature already
    # accepts max_iterations; the wrapper just defaults to 1M.
    # We wrap the call to thread our smaller cap.
    import temper_placer.router_v6.astar_core_numba as acn
    _original_kernel = acn._get_kernel
    _cap = max_iter

    def _patched_get_kernel():
        # Lazy build the kernel once, then wrap it
        k = _original_kernel()
        if k is None:
            return None
        # Return the kernel as-is; cap is enforced via the wrapper
        return k
    # We'll set max_iterations on every call by wrapping the
    # public function instead.

    _original_search = _astar_search_numba

    def _capped_search(
        start, goal, grid, neighbor_tensor=None,
        max_iterations=_cap, congestion_tensor=None,
    ):
        # Translate the high-level congestion_tensor kwarg (used by
        # _dispatch_search) into the low-level congestion_flat,
        # congestion_weight, max_congestion_cost kwargs the Numba
        # kernel actually expects.
        if congestion_tensor is not None:
            congestion_flat = congestion_tensor.array.reshape(-1)
            return _original_search(
                start, goal, grid,
                neighbor_tensor=neighbor_tensor,
                max_iterations=max_iterations,
                congestion_flat=congestion_flat,
                congestion_weight=congestion_tensor.weight,
                max_congestion_cost=congestion_tensor.max_cost,
            )
        return _original_search(
            start, goal, grid,
            neighbor_tensor=neighbor_tensor,
            max_iterations=max_iterations,
        )

    # Patch the symbol in BOTH the source module and the pathfinding
    # module's namespace.  The pathfinding module does
    # ``from .astar_core_numba import _astar_search_numba`` at
    # module load time, so the imported reference is what gets
    # called at runtime.
    acn._astar_search_numba = _capped_search
    import temper_placer.router_v6.astar_pathfinding as ap
    ap._astar_search_numba = _capped_search
    _original_dispatch = ap._dispatch_search

    def _capped_dispatch(grid, start, goal, use_theta_star,
                        use_lazy_theta_star, congestion_tensor=None):
        return _capped_search(
            start, goal, grid, congestion_tensor=congestion_tensor,
        )
    ap._dispatch_search = _capped_dispatch

    pipeline = RouterV6Pipeline(verbose=True, skip_stage3=True)

    t0 = time.perf_counter()
    try:
        closure_result = pipeline.run(PCB_PATH, pcb_override=parsed)
    except Exception as e:
        result.notes = f"Pipeline failed: {type(e).__name__}: {e}"
        result.wall_seconds = time.perf_counter() - t0
        print(f"\n*** PIPELINE FAILED: {result.notes} ***")
        return result

    result.wall_seconds = time.perf_counter() - t0

    # Extract metrics.  RouterV6Result nests the routing results
    # under stage4.routing_results (a RoutingResults dataclass with
    # compiled_routes and failed_nets).
    pr = closure_result
    rr = getattr(getattr(pr, "stage4", None), "routing_results", None)
    if rr is not None:
        if hasattr(rr, "compiled_routes"):
            result.routed_nets = list(rr.compiled_routes.keys())
        if hasattr(rr, "failed_nets"):
            result.failed_nets = list(rr.failed_nets)
    if hasattr(pr, "completion_rate"):
        result.completion_rate = pr.completion_rate * 100

    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--max-iter", type=int, default=10_000,
                   help="Per-A* iteration cap (default 10k; lower = "
                        "faster smoke but more hard nets fail)")
    p.add_argument("--output", type=Path, default=None,
                   help="Optional path to write the JSON result")
    args = p.parse_args()

    result = run_mini_baseline(args.max_iter)

    print(f"\n=== Mini-baseline smoke ===")
    print(f"Wall: {result.wall_seconds:.1f}s")
    print(f"Routed: {len(result.routed_nets)} / {len(result.routed_nets) + len(result.failed_nets)} "
          f"({result.completion_rate:.1f}%)")
    if result.failed_nets:
        print(f"Failed nets: {', '.join(result.failed_nets[:10])}"
              f"{'...' if len(result.failed_nets) > 10 else ''}")
    if result.notes:
        print(f"Notes: {result.notes}")

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump({
                "wall_seconds": result.wall_seconds,
                "routed_nets": result.routed_nets,
                "failed_nets": result.failed_nets,
                "completion_rate": result.completion_rate,
                "notes": result.notes,
            }, f, indent=2)
        print(f"Result written to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
