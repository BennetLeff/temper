#!/usr/bin/env python3
"""Same recipe as measure_connectivity.py, but routes the PR #1299
5-move scratch board (.scratch/temper-pr1299-moved.kicad_pcb) instead of
the committed pcb/temper.kicad_pcb. Never touches the committed board.
"""
import json
import sys
import time
from pathlib import Path

WT = Path("/home/bennet/Desktop/temper-wt-agent-routing-completeness-recon")
sys.path.insert(0, str(WT / "scripts"))

from route_board import route_once, DEFAULT_RULES  # noqa: E402

PCB_PATH = WT / ".scratch" / "temper-pr1299-moved.kicad_pcb"
assert PCB_PATH.exists(), f"run apply_pr1299_moves.py first -- {PCB_PATH} missing"

t0 = time.perf_counter()
r = route_once(
    PCB_PATH,
    DEFAULT_RULES,
    enable_geographic_pruning=False,
    enable_net_batching=False,  # same recipe as the baseline measurement
    net_batch_size=10,
)
wall = time.perf_counter() - t0

out_path = WT / ".scratch" / "live-route-pr1299.kicad_pcb"
out_path.write_text(r["routed_pcb_content"], encoding="utf-8")

pc = r["pad_connectivity"]
nrr = r.get("net_route_results") or {}

summary = {
    "wall_s": wall,
    "routed": r["routed"],
    "attempted": r["attempted"],
    "completion_rate": r["completion_rate"],
    "audited_nets": pc["audited"],
    "fully_connected": pc["fully_connected"],
    "fully_connected_nets": pc["fully_connected_nets"],
    "fake_completion": pc["fake_completion"],
    "fake_completion_nets": pc["fake_completion_nets"],
    "honest_gap": pc["honest_gap"],
    "unrouted_nets_stage4": sorted(r["unrouted_nets"]),
    "net_route_result_summary": {
        "connected": sorted(n for n, v in nrr.items() if v.disposition == "connected"),
        "partial": sorted(n for n, v in nrr.items() if v.disposition == "partial"),
        "zone_dependent": sorted(n for n, v in nrr.items() if v.disposition == "zone_dependent"),
        "failed": sorted(n for n, v in nrr.items() if v.disposition == "failed"),
    },
}

out_json = WT / ".scratch" / "live-route-pr1299-summary.json"
out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

print(f"wall={wall:.1f}s")
print(f"fully_connected: {pc['fully_connected']}/{pc['audited']}")
print(f"fake_completion: {pc['fake_completion']}  honest_gap: {pc['honest_gap']}")
if nrr:
    s = summary["net_route_result_summary"]
    print(f"NetRouteResult: connected={len(s['connected'])} partial={len(s['partial'])} "
          f"zone_dependent={len(s['zone_dependent'])} failed={len(s['failed'])} of {len(nrr)}")
print(f"wrote {out_path} and {out_json}")
