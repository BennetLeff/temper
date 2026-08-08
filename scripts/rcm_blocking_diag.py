#!/usr/bin/env python3
"""Problem-3 spot-check diagnostic: for the COMBINED (Fix A + Fix B) router
state, capture per-failing-net blocking_nets and classify whether each
blocker is a large-clearance-envelope (HighVoltage/HighVoltageIsolated/
ACMains-class) net or an ordinary-clearance net -- distinguishing "real
placement congestion" from "HV clearance envelope crowding out SELV
routing," which need different remedies.

Monkeypatches route_stage.run_astar_pathfinding to capture the real
PathfindingResult.failure_reports (never touches production code), then
runs one full route_pcb() pass identical to the main measurement runs.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from route_board import _make_parsed_stub, strip_existing_copper  # noqa: E402

captured: dict[str, object] = {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "rcm_blocking_diag.json",
        help="Where to write the JSON report (default: repo-root/rcm_blocking_diag.json).",
    )
    args = parser.parse_args()

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.netclass_loader import load_netclass_rules
    from temper_placer.router_v6 import astar_pathfinding

    pcb_path = REPO_ROOT / "pcb" / "temper.kicad_pcb"
    rules_path = (
        REPO_ROOT / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
    )
    rules = load_netclass_rules(rules_path)
    netlist = parse_kicad_pcb(pcb_path).netlist

    content = pcb_path.read_text(encoding="utf-8")
    cleaned, _ = strip_existing_copper(content)
    import tempfile

    tmp = tempfile.NamedTemporaryFile("w", suffix=".kicad_pcb", delete=False, encoding="utf-8")
    tmp.write(cleaned)
    tmp.close()
    route_src = Path(tmp.name)
    parsed_stub = _make_parsed_stub(route_src, netlist)

    real_run_astar = astar_pathfinding.run_astar_pathfinding

    def _capturing_run_astar(*args, **kwargs):
        result = real_run_astar(*args, **kwargs)
        captured["failure_reports"] = result.failure_reports
        captured["failed_nets"] = list(result.failed_nets)
        captured["design_rules"] = kwargs.get("design_rules")
        return result

    astar_pathfinding.run_astar_pathfinding = _capturing_run_astar
    try:
        from temper_placer.router_v6.adapter import route_pcb

        t0 = time.perf_counter()
        result = route_pcb(
            parsed_stub,
            {},
            design_rules=rules.design_rules,
            enable_geographic_pruning=False,
            enable_net_batching=True,
            net_batch_size=10,
        )
        wall_s = time.perf_counter() - t0
    finally:
        astar_pathfinding.run_astar_pathfinding = real_run_astar

    design_rules = captured.get("design_rules") or rules.design_rules
    failure_reports = captured.get("failure_reports") or {}

    LARGE_CLEARANCE_CLASSES = {
        "HighVoltage",
        "HighVoltageIsolated",
        "ACMains",
    }

    rows = []
    for net_name, report in sorted(failure_reports.items()):
        blockers = sorted(getattr(report, "blocking_nets", []) or [])
        own_rule = design_rules.get_rules_for_net(net_name)
        blocker_classes = []
        large_clearance_blocker_count = 0
        for b in blockers:
            b_rule = design_rules.get_rules_for_net(b)
            is_large = b_rule.name in LARGE_CLEARANCE_CLASSES or (
                b_rule.clearance_mm >= 1.0
            )
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
        "completion_rate": result.completion_rate,
        "unrouted_count": len(result.unrouted_nets),
        "unrouted_nets": sorted(result.unrouted_nets),
        "failed_net_count": len(failure_reports),
        "rows": rows,
    }
    args.output.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {args.output} ({len(rows)} failure rows, wall={wall_s:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
