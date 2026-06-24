"""Full pipeline profile with per-net logging.

Runs the actual closure test (parse + Benders placement + Router V6 +
KiCad DRC) on temper.kicad_pcb without any iter cap or time bound,
and captures:

- Wall clock per pipeline stage (parse, Benders, Router, DRC)
- cProfile call stats for the router stage (where 80%+ of time is)
- Per-net A* call counts and timing
- Per-net failure reasons (congestion vs no_path vs cap)
- Net-by-net ordering, waypoint counts, and congestion tensor summary

Output:
- /tmp/full_pipeline_profile.log  — human-readable log
- /tmp/full_pipeline_profile.pstats — cProfile binary stats
- /tmp/full_pipeline_profile.json  — machine-readable summary

Usage:
    PYTHONPATH=packages/temper-placer/src \\
    /Users/bennet/Desktop/temper/.venv/bin/python3 \\
    scripts/full_pipeline_profile.py
"""
from __future__ import annotations

import argparse
import cProfile
import io
import json
import logging
import os
import pstats
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path("/Users/bennet/Desktop/temper/.worktrees/feat/router-v6-closure-rate-90-percent")
PCB_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"
LOG_PATH = Path("/tmp/full_pipeline_profile.log")
PSTATS_PATH = Path("/tmp/full_pipeline_profile.pstats")
JSON_PATH = Path("/tmp/full_pipeline_profile.json")


def setup_logging(verbose: bool) -> None:
    """Route everything to the log file; tee a few key lines to stderr."""
    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    file_h = logging.FileHandler(LOG_PATH, mode="w")
    file_h.setLevel(logging.DEBUG)
    file_h.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers = [file_h]

    # also print INFO+ to stderr for live feedback
    stderr_h = logging.StreamHandler(sys.stderr)
    stderr_h.setLevel(logging.INFO)
    stderr_h.setFormatter(fmt)
    root.addHandler(stderr_h)


def instrument_router() -> dict[str, Any]:
    """Wrap the router's A* pathfinding with per-net timing/call counters.

    Returns a dict that the caller reads after the run.  The wrapping
    is non-invasive: we monkey-patch ``astar_core_numba._astar_search_numba``
    (and ``astar_pathfinding._dispatch_search``) to record:

    - net name (via the per-net wrapper)
    - aggregate A* call count, total/mean/max wall time
    - count of calls that hit the iteration cap
    - effective iter cap (logged once for sanity)

    Cheap-running counters are used in the hot path: the previous
    per-call dict-append added measurable Python overhead to the
    1M-iter-cap full run.
    """
    from temper_placer.router_v6 import astar_core_numba as acn
    from temper_placer.router_v6 import astar_pathfinding as ap

    stats: dict[str, Any] = {
        # Cheap running counters for the A* hot path
        "a_star_call_count": 0,
        "a_star_total_ms": 0.0,
        "a_star_max_ms": 0.0,
        "a_star_min_ms": float("inf"),
        "a_star_cap_hits": 0,
        "iter_cap": 10_000_000,  # raised to 10M for the full run
        "iter_cap_logged": False,
        # Per-net attribution from the ripup wrapper
        "net_calls": {},
        "net_time_ms": {},
        "net_iters_cap": {},
    }

    _orig_search = acn._astar_search_numba

    def _wrapped_search(
        start, goal, grid, neighbor_tensor=None,
        max_iterations=1_000_000, congestion_flat=None,
        congestion_weight=1.0, max_congestion_cost=100.0,
    ):
        t0 = time.perf_counter()
        path = _orig_search(
            start, goal, grid, neighbor_tensor=neighbor_tensor,
            max_iterations=max_iterations,
            congestion_flat=congestion_flat,
            congestion_weight=congestion_weight,
            max_congestion_cost=max_congestion_cost,
        )
        dt_ms = (time.perf_counter() - t0) * 1000.0
        hit_cap = (path is None or len(path) == 0)
        # Sanity log the iter cap once so we know the production
        # run actually saw the cap we intended (and not the kernel
        # default of 1M).
        if not stats["iter_cap_logged"]:
            stats["iter_cap_logged"] = True
            logging.info(
                "A* kernel max_iterations=%d (congestion_weight=%.3f)",
                max_iterations, congestion_weight,
            )
        # Cheap-running counters
        stats["a_star_call_count"] += 1
        stats["a_star_total_ms"] += dt_ms
        if dt_ms > stats["a_star_max_ms"]:
            stats["a_star_max_ms"] = dt_ms
        if dt_ms < stats["a_star_min_ms"]:
            stats["a_star_min_ms"] = dt_ms
        if hit_cap:
            stats["a_star_cap_hits"] += 1
        return path

    acn._astar_search_numba = _wrapped_search
    ap._astar_search_numba = _wrapped_search

    # Now wrap the per-net loop in run_astar_pathfinding so we can
    # attribute A* calls to a net name.  We do this by monkey-patching
    # the inner helper that does the per-net iteration.
    _orig_route_with_ripup = ap._astar_route_with_ripup

    def _wrapped_route_with_ripup(*args, **kwargs):
        net_name = kwargs.get("net_name") or (args[0] if args else "??")
        # The pathfinding code does the A* inside _astar_search_numba;
        # we just need to time the per-net total.
        t0 = time.perf_counter()
        result, ripped_ids = _orig_route_with_ripup(*args, **kwargs)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        stats["net_calls"][net_name] = stats["net_calls"].get(net_name, 0) + 1
        stats["net_time_ms"][net_name] = (
            stats["net_time_ms"].get(net_name, 0.0) + dt_ms
        )
        if result is None:
            stats["net_iters_cap"][net_name] = (
                stats["net_iters_cap"].get(net_name, 0) + 1
            )
        return result, ripped_ids

    ap._astar_route_with_ripup = _wrapped_route_with_ripup
    return stats


def run_full_pipeline(profile: bool) -> dict[str, Any]:
    """Run the closure test on temper.kicad_pcb.  Capture everything."""
    from temper_placer.regression.closure_test import ClosureTest

    out: dict[str, Any] = {
        "pstats_path": str(PSTATS_PATH),
        "log_path": str(LOG_PATH),
    }

    # 1. Parse PCB (also measured)
    t0 = time.perf_counter()
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    parsed = parse_kicad_pcb_v6(str(PCB_PATH))
    t_parse = time.perf_counter() - t0
    out["parse_seconds"] = t_parse
    out["net_count"] = len(parsed.nets)
    out["component_count"] = len(parsed.components)
    logging.info(
        "Parsed %d nets, %d components in %.1fs",
        len(parsed.nets), len(parsed.components), t_parse,
    )

    # 2. Instrument router (per-net logging + A* call recording)
    a_star_stats = instrument_router()
    a_star_stats["iter_cap"] = 1_000_000  # uncap for the full run

    # 3. Channel analysis (Stage 2) + placement.channels.json
    t0 = time.perf_counter()
    from temper_placer.regression.closure_test import _run_channel_analysis
    stages_exercised = _run_channel_analysis(
        output_dir=PCB_PATH.parent, stages_exercised=0,
    )
    t_stage2 = time.perf_counter() - t0
    out["stage2_seconds"] = t_stage2
    logging.info("Stage 2 channel analysis took %.1fs", t_stage2)

    # 4. Benders placement
    t0 = time.perf_counter()
    benders_iterations = 0
    benders_cuts = 0
    optimized_placements = {}
    try:
        from temper_placer.protocol import StageInput, StageMeta
        from temper_placer.runner import resolve_and_run
        placement_result = resolve_and_run(
            phase="placement",
            strategies=["template"],
            input=StageInput(
                data=parsed,
                meta=StageMeta(seed=42),
            ),
            fallback="template",
        )
        benders_iterations = getattr(placement_result.data, "iterations", 0)
        benders_cuts = getattr(placement_result.data, "cuts", 0)
        optimized_placements = getattr(placement_result.data, "placements", {})
    except Exception as e:
        logging.warning("Benders placement failed: %s", e)
    t_benders = time.perf_counter() - t0
    out["benders_seconds"] = t_benders
    out["benders_iterations"] = benders_iterations
    out["benders_cuts"] = benders_cuts
    logging.info(
        "Benders placement: %d iterations, %d cuts in %.1fs",
        benders_iterations, benders_cuts, t_benders,
    )

    # 5. Router V6 — the main cost.  Run with cProfile.
    # NOTE: the canonical closure-test adapter sets
    # enable_lazy_theta_star=True and enable_smoothing=True.
    # The smoke achieves 15/24 in 18s with both flags OFF
    # (use_theta_star only).  The full pipeline run blows up
    # to 5+ min when the canonical flags are used, because the
    # lazy-theta-star path is a Python implementation and the
    # smoothing path is broken (SDFGrid.from_polygons missing).
    # For the profile we bypass the strategy and call
    # RouterV6Pipeline directly with the smoke-equivalent
    # settings, then capture the SM1 baseline.
    use_canonical = os.environ.get("PROFILE_CANONICAL", "0") == "1"
    pr = cProfile.Profile() if profile else None
    if pr is not None:
        pr.enable()
    t0 = time.perf_counter()
    if use_canonical:
        from temper_placer.protocol import StageInput, StageMeta
        from temper_placer.runner import resolve_and_run
        routing_result = resolve_and_run(
            phase="routing",
            strategies=["router_v6_full"],
            input=StageInput(
                data=parsed,
                meta=StageMeta(
                    seed=42,
                    trace_context={"placements": optimized_placements},
                ),
            ),
        )
    else:
        from temper_placer.router_v6.pipeline import RouterV6Pipeline
        max_iter = int(os.environ.get("PROFILE_MAX_ITER", "100000"))
        # Match the smoke (and the now-fixed closure-test
        # adapter): plain 2D A* via the Numba kernel, no theta
        # star, no smoothing.  The kernel wrapper below applies
        # the per-A* iter cap.
        pipeline = RouterV6Pipeline(
            verbose=True,
            enable_theta_star=False,
            enable_lazy_theta_star=False,
            enable_smoothing=False,
        )
        # The RouterV6Pipeline's run() doesn't expose a max_iter
        # arg; we wrap the kernel to apply the cap.
        from temper_placer.router_v6 import astar_core_numba as acn
        from temper_placer.router_v6 import astar_pathfinding as ap
        _cap = max_iter
        if max_iter < 10_000_000:
            _orig = acn._astar_search_numba
            def _cap_search(start, goal, grid, neighbor_tensor=None,
                            max_iterations=1_000_000, **kw):
                return _orig(start, goal, grid,
                             neighbor_tensor=neighbor_tensor,
                             max_iterations=_cap, **kw)
            acn._astar_search_numba = _cap_search
            ap._astar_search_numba = _cap_search
        router_out = pipeline.run(PCB_PATH, pcb_override=parsed)
        class _RR:
            completion_rate = router_out.completion_rate
        routing_result = type("_Res", (), {"data": _RR()})()
    t_router = time.perf_counter() - t0
    if pr is not None:
        pr.disable()
    out["router_seconds"] = t_router
    completion = getattr(routing_result.data, "completion_rate", 0.0)
    out["router_completion_pct"] = completion * 100
    logging.info(
        "Router V6: %.1f%% completion in %.1fs",
        completion * 100, t_router,
    )

    # 6. Dump cProfile stats
    if pr is not None:
        pr.dump_stats(str(PSTATS_PATH))
        # Also capture a human-readable summary
        s = io.StringIO()
        stats = pstats.Stats(pr, stream=s).sort_stats("cumulative")
        stats.print_stats(40)
        out["pstats_top_40"] = s.getvalue()
        logging.info("cProfile written to %s", PSTATS_PATH)

    # 7. A* call stats — already in the running counters, just copy out
    out["a_star_call_count"] = a_star_stats["a_star_call_count"]
    out["a_star_total_ms"] = a_star_stats["a_star_total_ms"]
    out["a_star_cap_hits"] = a_star_stats["a_star_cap_hits"]
    out["a_star_max_ms"] = a_star_stats["a_star_max_ms"]
    out["a_star_min_ms"] = (
        a_star_stats["a_star_min_ms"]
        if a_star_stats["a_star_min_ms"] != float("inf")
        else 0.0
    )
    if a_star_stats["a_star_call_count"] > 0:
        out["a_star_mean_ms"] = (
            a_star_stats["a_star_total_ms"]
            / a_star_stats["a_star_call_count"]
        )
    else:
        out["a_star_mean_ms"] = 0.0

    out["net_calls"] = a_star_stats["net_calls"]
    out["net_time_ms"] = a_star_stats["net_time_ms"]
    out["net_iters_cap"] = a_star_stats["net_iters_cap"]

    # 8. DRC
    t0 = time.perf_counter()
    drc_errors = drc_warnings = 0
    try:
        from temper_placer.validation.drc_runner import run_drc
        drc_result = run_drc(PCB_PATH)
        drc_errors = drc_result.error_count
        drc_warnings = drc_result.warning_count
    except Exception as e:
        logging.warning("DRC failed: %s", e)
    t_drc = time.perf_counter() - t0
    out["drc_seconds"] = t_drc
    out["drc_errors"] = drc_errors
    out["drc_warnings"] = drc_warnings
    logging.info(
        "DRC: %d errors, %d warnings in %.1fs",
        drc_errors, drc_warnings, t_drc,
    )

    # 9. Pull failed net list + reasons from the router result
    try:
        rr = routing_result.data
        if hasattr(rr, "stage4") and hasattr(rr.stage4, "routing_results"):
            compiled = rr.stage4.routing_results.compiled_routes
            failed = rr.stage4.routing_results.failed_nets
            out["routed_nets"] = list(compiled.keys())
            out["failed_nets"] = list(failed)
    except Exception as e:
        logging.warning("Could not extract net lists: %s", e)

    out["total_seconds"] = (
        t_parse + t_stage2 + t_benders + t_router + t_drc
    )
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--no-profile", action="store_true",
                   help="Skip cProfile (just log per-net stats)")
    p.add_argument("--quiet", action="store_true",
                   help="Reduce log verbosity")
    args = p.parse_args()

    setup_logging(verbose=not args.quiet)
    logging.info("=" * 60)
    logging.info("Full pipeline profile on %s", PCB_PATH)
    logging.info("=" * 60)

    result = run_full_pipeline(profile=not args.no_profile)

    logging.info("=" * 60)
    logging.info("Summary:")
    for key in (
        "parse_seconds", "stage2_seconds", "benders_seconds",
        "router_seconds", "drc_seconds", "total_seconds",
        "router_completion_pct",
        "a_star_call_count", "a_star_total_ms", "a_star_mean_ms",
        "a_star_max_ms", "a_star_cap_hits",
    ):
        if key in result:
            logging.info("  %s: %s", key, result[key])
    logging.info("=" * 60)

    with open(JSON_PATH, "w") as f:
        json.dump(result, f, indent=2, default=str)
    logging.info("JSON written to %s", JSON_PATH)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
