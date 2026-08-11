#!/usr/bin/env python3
"""Stage4-placement-congestion spike (2026-08-11): reproduce the current
production `--net-batching` route despite a live regression that makes the
real subprocess-per-batch path 100% fail on this HEAD.

**Why this script exists, stated first.** `net_batching.run_net_batched_stage3`
unconditionally calls `_write_shared_context(pcb, skeletons)` before its batch
loop even starts (net_batching.py:947), which unconditionally
`pickle.dump`s `skeletons` (net_batching.py:549-557). Since
`feat(wave4): migrate channel_skeleton.py nx.Graph to Rust SkeletonGraph`
(commit 281aa747b), `skeletons` values are
`temper_design_bundle_python.channel_skeleton_contracts.SkeletonGraph` pyo3
objects, which are not picklable:

    _pickle.PicklingError: Can't pickle <class
    'temper_design_bundle_python.channel_skeleton_contracts.SkeletonGraph'>:
    import of module 'temper_design_bundle_python.channel_skeleton_contracts'
    failed

Reproduced live, twice, independently (plain `route_board.py --net-batching`
and `rcm_blocking_diag.py`), both crashing at the identical line, before this
script was written. This means **every** `--net-batching` invocation of
`route_pcb()` on this HEAD fails before Stage 3 solves a single batch --
100%, not degraded. `net_batching.py` is inside
`router_v6/**`, which this spike's task boundary explicitly forbids editing
(another agent is mid-migration there) -- so this script does not fix it.

**The workaround, and why it is faithful to production behaviour.** Before
subprocess isolation was added (2026-08-08,
docs/evidence/2026-08-08-net-batching-subprocess-isolation.md), every batch's
build+solve ran in-process; subprocess isolation was added only to stop
cross-batch RSS creep from accumulating into a crash on an *8GB-constrained*
CI-like environment (peak batch RSS measured there: 5.0-5.5GB, creeping
5.21->5.78GB across batches in the very first, non-isolated prototype run
before it died). This machine has 62GB RAM -- comfortably clear of that
failure mode even with zero isolation. This script monkeypatches exactly the
two functions that cross the (broken) subprocess/pickle boundary --
`_write_shared_context` (skip serialising; stash the live objects instead)
and `_run_subset_subprocess` (call `_solve_subset` in-process instead of
spawning a child) -- and leaves every other line of `net_batching.py`
(ordering, capacity bookkeeping, retry/singleton-fallback policy,
`Stage3Output` construction) untouched and running for real. The body of the
patched `_run_subset_subprocess` is copy-pasted verbatim from
`_batch_worker_entry` (net_batching.py:594-677) minus the pickle
read/subprocess `Connection.send` -- same build call (`_solve_subset`), same
result-dict shape, same `MemoryError` handling. This is a measurement
workaround for this spike only, not a proposed fix.

Combines rcm_blocking_diag.py's astar-failure capture with route_board.py's
route_once()/audit_pad_connectivity() so one route produces: completion
rate, segments/vias/zones, nets_carrying_copper-style unexplained-gap audit,
the PRIMARY pad-connectivity metric, and full per-net Stage-4 blocker
classification -- in one pass, instead of two.
"""
from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def main() -> int:
    from temper_placer.router_v6 import astar_pathfinding, net_batching

    out_path = Path(
        sys.argv[sys.argv.index("--output") + 1]
        if "--output" in sys.argv
        else REPO_ROOT / "spike_inprocess_netbatch.json"
    )
    board_out_path = Path(
        sys.argv[sys.argv.index("--board-output") + 1]
        if "--board-output" in sys.argv
        else REPO_ROOT / "spike_inprocess_netbatch_routed.kicad_pcb"
    )

    # ---- Patch 1: skip the crashing pickle, stash live objects instead ----
    _stash: dict[str, object] = {}

    def _patched_write_shared_context(pcb, skeletons):  # noqa: ANN001
        _stash["pcb"] = pcb
        _stash["skeletons"] = skeletons
        return "unused-inprocess-sentinel"

    # ---- Patch 2: run each batch in-process, verbatim _batch_worker_entry
    # logic, minus the pickle read / subprocess Connection.send ----
    def _patched_run_subset_subprocess(
        *,
        ctx_path,  # unused -- see _patched_write_shared_context
        net_names,
        channel_widths,
        diff_pairs_subset,
        enable_geographic_pruning,
        sat_conflict_limit,
        sat_time_limit_ms,
        timeout_s,  # unused -- no subprocess, nothing to time out
    ):
        pcb = _stash["pcb"]
        skeletons = _stash["skeletons"]
        name_to_net = {n.name: n for n in pcb.nets}
        nets_subset = [name_to_net[name] for name in net_names]

        t0 = time.perf_counter()
        try:
            cm, rust_result = net_batching._solve_subset(
                skeletons=skeletons,
                nets_subset=nets_subset,
                channel_widths=channel_widths,
                design_rules=pcb.design_rules,
                diff_pairs_subset=diff_pairs_subset,
                pcb=pcb,
                enable_geographic_pruning=enable_geographic_pruning,
                sat_conflict_limit=sat_conflict_limit,
                sat_time_limit_ms=sat_time_limit_ms,
            )
            status = rust_result.get("status", "unknown")
            n_net_channel = sum(1 for v in cm.variables if type(v).__name__ == "NetChannelVar")
            n_via = sum(1 for v in cm.variables if type(v).__name__ == "ViaVar")
            result = {
                "status": status,
                "topology_graph": rust_result.get("topology_graph", {}),
                "primary_vars": cm.variable_count,
                "net_channel_vars": n_net_channel,
                "via_vars": n_via,
                "constraints": cm.constraint_count,
                "wall_s": time.perf_counter() - t0,
                "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
        except MemoryError:
            result = {
                "status": "memory_error",
                "topology_graph": {},
                "primary_vars": 0,
                "net_channel_vars": 0,
                "via_vars": 0,
                "constraints": 0,
                "wall_s": time.perf_counter() - t0,
                "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }

        return net_batching._SubprocessOutcome(
            got_result=True,
            result=result,
            crashed=False,
            crash_reason=None,
            exitcode=0,
            external_peak_rss_kb=result["peak_rss_kb"],
            wall_s_wall=time.perf_counter() - t0,
        )

    net_batching._write_shared_context = _patched_write_shared_context
    net_batching._run_subset_subprocess = _patched_run_subset_subprocess

    # ---- Capture Stage 4's real failure reports (same technique as
    # rcm_blocking_diag.py) ----
    captured: dict[str, object] = {}
    real_run_astar = astar_pathfinding.run_astar_pathfinding

    def _capturing_run_astar(*args, **kwargs):
        result = real_run_astar(*args, **kwargs)
        captured["failure_reports"] = result.failure_reports
        captured["failed_nets"] = list(result.failed_nets)
        captured["design_rules"] = kwargs.get("design_rules")
        return result

    astar_pathfinding.run_astar_pathfinding = _capturing_run_astar

    import route_board as rb

    pcb_path = REPO_ROOT / "pcb" / "temper.kicad_pcb"
    rules_path = (
        REPO_ROOT / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
    )

    t0 = time.perf_counter()
    r = rb.route_once(
        pcb_path,
        rules_path,
        enable_net_batching=True,
        net_batch_size=10,
    )
    wall_s = time.perf_counter() - t0

    if r.get("routed_pcb_content"):
        board_out_path.write_text(r["routed_pcb_content"], encoding="utf-8")

    if captured.get("design_rules") is not None:
        design_rules = captured["design_rules"]
    else:
        from temper_placer.io.netclass_loader import load_netclass_rules

        design_rules = load_netclass_rules(rules_path).design_rules
    failure_reports = captured.get("failure_reports") or {}

    LARGE_CLEARANCE_CLASSES = {"HighVoltage", "HighVoltageIsolated", "ACMains"}
    rows = []
    for net_name, report in sorted(failure_reports.items()):
        blockers = sorted(getattr(report, "blocking_nets", []) or [])
        own_rule = design_rules.get_rules_for_net(net_name)
        blocker_classes = []
        large_clearance_blocker_count = 0
        for b in blockers:
            b_rule = design_rules.get_rules_for_net(b)
            is_large = b_rule.name in LARGE_CLEARANCE_CLASSES or b_rule.clearance_mm >= 1.0
            if is_large:
                large_clearance_blocker_count += 1
            blocker_classes.append(
                {
                    "name": b,
                    "class": b_rule.name,
                    "clearance_mm": b_rule.clearance_mm,
                    "trace_width_mm": b_rule.trace_width_mm,
                }
            )
        rows.append(
            {
                "net": net_name,
                "own_class": own_rule.name,
                "own_clearance_mm": own_rule.clearance_mm,
                "rule_id": getattr(report, "rule_id", None),
                "blocker_count": len(blockers),
                "large_clearance_blocker_count": large_clearance_blocker_count,
                "blockers": blocker_classes,
            }
        )

    out = {
        "wall_s": wall_s,
        "completion_rate": r["completion_rate"],
        "routed": r["routed"],
        "attempted": r["attempted"],
        "unrouted": r["unrouted"],
        "unrouted_nets": r["unrouted_nets"],
        "segments": r["segments"],
        "vias": r["vias"],
        "zones": r["zones"],
        "total_router_nets": r["total_router_nets"],
        "should_route_excluded_nets": r["should_route_excluded_nets"],
        "unexplained_copper_gap": r["unexplained_copper_gap"],
        "pad_connectivity": r["pad_connectivity"],
        "failed_net_count": len(failure_reports),
        "rows": rows,
    }
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(
        f"Wrote {out_path} ({len(rows)} failure rows) and {board_out_path}, "
        f"wall={wall_s:.1f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
