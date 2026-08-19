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
    uv run --no-sync python scripts/full_pipeline_profile.py

What this does and does NOT measure (read before quoting a number):

- By default (``PROFILE_CANONICAL`` unset) it bypasses the strategy
  registry and drives ``RouterV6Pipeline`` directly with smoke-equivalent
  flags. That configuration routes the LEGACY 2-grid path
  (``_astar_route_with_ripup``), not the N-layer path
  (``_astar_route_nlayer``) that the production/closure route takes on
  this board. Its completion rate is therefore NOT the production closure
  figure and must never be quoted as one. Check
  ``instrumentation_fired`` in the JSON to see which seam actually ran.
- ``PROFILE_CANONICAL=1`` runs the real ``router_v6_full`` strategy.
- ``PROFILE_MAX_ITER`` caps per-A* iterations (default 100000); a low cap
  manufactures failures that are cap artifacts, not routing failures.
- The run aborts rather than publishing figures if no instrumented seam
  was entered -- see :func:`assert_instrumentation_fired`.
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

# Resolve from this file, not from one author's 2026-06 macOS worktree.
# The hardcoded "/Users/bennet/Desktop/temper/.worktrees/feat/
# router-v6-closure-rate-90-percent" this replaced exists on no machine
# that runs this repo today, so PCB_PATH resolved to a missing board and
# the script died in parse before reaching any of its instrumentation.
# NOTE: branch agent/vacuous-gates-orphan-scripts makes this identical
# edit; the conflict is textual only.
REPO_ROOT = Path(__file__).resolve().parents[1]
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
    """Wrap the router's A* seams with per-net timing/call counters.

    2026-08-18 REPAIR. As written on 2026-06-23 this function measured
    NOTHING, in three independent ways, and reported plausible-looking
    zeros for it:

    1. It patched ``astar_pathfinding._astar_route_with_ripup``.
       ``astar_pathfinding`` became a pure re-export shim; the real
       function lives in ``_astar_search`` and its only production caller
       (``_astar_reconstruct``) binds it via ``from ... import`` at import
       time. Rebinding the shim's attribute moves nothing, so
       ``net_calls`` / ``net_time_ms`` / ``net_iters_cap`` were always
       ``{}`` -- and were still written to the JSON as if measured.
    2. Even reached, the wrapper unpacked two values from a function that
       returns three (``path, ripped_ids, fallback_count``) -- proof it had
       not run since that third value was added.
    3. On this board the production route is the N-layer path
       (>2 routable signal layers), which routes each net through
       ``_astar_nlayer._astar_route_nlayer`` and never calls
       ``_astar_route_with_ripup`` at all.

    It also set ``astar_pathfinding._astar_search_rust``, a name that
    module does not have and nothing reads, and its kernel wrapper
    declared a fixed signature that rejects the ``net_id`` /
    ``corridor_mask`` / ``thermal_flat`` / ``thermal_weight`` kwargs the
    live call site passes.

    The wrappers below are therefore signature- and return-agnostic
    (``*args, **kwargs``, no unpacking), and patch the bindings production
    actually reads:

    - ``astar_core_rust._astar_search_rust`` -- aggregate A* counters.
      This one binds because the call site re-imports it per call
      (function-local import in ``_astar_search``).
    - ``_astar_nlayer._astar_route_nlayer`` -- per-net attribution on the
      N-layer path (called by module-global name at _astar_nlayer.py:1363).
    - ``_astar_reconstruct._astar_route_with_ripup`` -- per-net attribution
      on the legacy 2-grid path.

    Call :func:`assert_instrumentation_fired` after the run: it raises if
    no counter moved, so this script can never again report a number for a
    seam it did not touch.
    """
    from temper_placer.router_v6 import _astar_nlayer as anl
    from temper_placer.router_v6 import _astar_reconstruct as arec
    from temper_placer.router_v6 import astar_core_rust as acn

    stats: dict[str, Any] = {
        # Cheap running counters for the A* hot path
        "a_star_call_count": 0,
        "a_star_total_ms": 0.0,
        "a_star_max_ms": 0.0,
        "a_star_min_ms": float("inf"),
        "a_star_cap_hits": 0,
        "iter_cap_logged": False,
        # Per-net attribution
        "net_calls": {},
        "net_time_ms": {},
        "net_iters_cap": {},
        # Which patch points actually fired (the anti-vacuity record).
        "patched": [],
        "fired": {},
    }

    _orig_search = acn._astar_search_rust

    def _wrapped_search(*args, **kwargs):
        t0 = time.perf_counter()
        path = _orig_search(*args, **kwargs)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        hit_cap = (path is None or len(path) == 0)
        if not stats["iter_cap_logged"]:
            stats["iter_cap_logged"] = True
            logging.info(
                "A* kernel max_iterations=%s (congestion_weight=%s)",
                kwargs.get("max_iterations", "<default>"),
                kwargs.get("congestion_weight", "<default>"),
            )
        stats["a_star_call_count"] += 1
        stats["a_star_total_ms"] += dt_ms
        if dt_ms > stats["a_star_max_ms"]:
            stats["a_star_max_ms"] = dt_ms
        if dt_ms < stats["a_star_min_ms"]:
            stats["a_star_min_ms"] = dt_ms
        if hit_cap:
            stats["a_star_cap_hits"] += 1
        stats["fired"]["_astar_search_rust"] = (
            stats["fired"].get("_astar_search_rust", 0) + 1
        )
        return path

    acn._astar_search_rust = _wrapped_search
    stats["patched"].append("astar_core_rust._astar_search_rust")

    def _make_per_net_wrapper(orig, label):
        """Time one net's routing call without touching its return shape."""

        def _wrapped(*args, **kwargs):
            net_name = kwargs.get("net_name") or (args[0] if args else "??")
            t0 = time.perf_counter()
            out = orig(*args, **kwargs)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            stats["net_calls"][net_name] = stats["net_calls"].get(net_name, 0) + 1
            stats["net_time_ms"][net_name] = (
                stats["net_time_ms"].get(net_name, 0.0) + dt_ms
            )
            # First element of the returned tuple is the route path on both
            # seams; None means the net did not close on this attempt.
            route = out[0] if isinstance(out, tuple) and out else out
            if route is None:
                stats["net_iters_cap"][net_name] = (
                    stats["net_iters_cap"].get(net_name, 0) + 1
                )
            stats["fired"][label] = stats["fired"].get(label, 0) + 1
            return out

        return _wrapped

    anl._astar_route_nlayer = _make_per_net_wrapper(
        anl._astar_route_nlayer, "_astar_route_nlayer"
    )
    stats["patched"].append("_astar_nlayer._astar_route_nlayer")

    arec._astar_route_with_ripup = _make_per_net_wrapper(
        arec._astar_route_with_ripup, "_astar_route_with_ripup"
    )
    stats["patched"].append("_astar_reconstruct._astar_route_with_ripup")

    return stats


def assert_instrumentation_fired(stats: dict[str, Any]) -> None:
    """Refuse to report numbers for seams that were never entered.

    A profiler that prints plausible figures while measuring nothing is
    worse than no profiler: this script did exactly that between
    2026-06-23 and 2026-08-18. Every counter below is expected to move on
    any real route; if none did, the patch points have drifted again and
    the output must not be believed.
    """
    if not stats["fired"]:
        raise RuntimeError(
            "instrumentation measured NOTHING -- none of the patched seams "
            f"({', '.join(stats['patched'])}) was entered. The router's "
            "internals have moved again; re-point instrument_router() "
            "before trusting any number this script prints."
        )
    if not stats["net_calls"]:
        raise RuntimeError(
            "per-net attribution is empty while the A* kernel ran "
            f"({stats['a_star_call_count']} calls) -- the per-net seam has "
            "drifted. Fix it rather than reporting aggregate-only numbers."
        )
    logging.info(
        "instrumentation self-check OK: %s",
        ", ".join(f"{k}={v}" for k, v in sorted(stats["fired"].items())),
    )


def run_full_pipeline(profile: bool) -> dict[str, Any]:
    """Run the closure test on temper.kicad_pcb.  Capture everything."""

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
        # adapter): plain 2D A* via the Rust kernel, no theta
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
        from temper_placer.router_v6 import astar_core_rust as acn
        _cap = max_iter
        if max_iter < 10_000_000:
            _orig = acn._astar_search_rust
            def _cap_search(*args, **kw):
                # Signature-agnostic: the kernel also takes net_id /
                # corridor_mask / thermal_flat / thermal_weight, and the
                # live call site passes them. The previous fixed signature
                # here (and in the instrumentation wrapper) would have
                # raised TypeError on the first call.
                kw["max_iterations"] = _cap
                return _orig(*args, **kw)
            acn._astar_search_rust = _cap_search
            # NOTE: astar_pathfinding has no _astar_search_rust attribute
            # and nothing reads one; the old `ap._astar_search_rust = ...`
            # here only created a name that never fired.
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

    # 7. A* call stats — already in the running counters, just copy out.
    # Refuse to publish them if no patched seam was entered.
    assert_instrumentation_fired(a_star_stats)
    out["instrumentation_fired"] = dict(a_star_stats["fired"])
    out["instrumentation_patched"] = list(a_star_stats["patched"])
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
