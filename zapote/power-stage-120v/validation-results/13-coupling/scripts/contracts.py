#!/usr/bin/env python3
"""Interface contracts for a proposed set of parallel workstreams (from combined.json's clustering).

    python3 -I validation-results/13-coupling/scripts/contracts.py      (after combine.py)

Workstreams (WS) are unions of today's groups. For every pair of workstreams joined by any group pair with combined
coupling >= 0.2 (the threshold table's 2/3-recall point), and for every workstream's outside boundary, the contract is
computed from the stage-32 data, not written by hand:
  nets      - every net with pins in both workstreams, with the pins (ref.pin) on each side and the net class;
  geometry  - routed copper of one workstream lying in the other's territory (mm2, physical.json), contested 10 mm
              corridor tiles both use, HOT / SELV net pairs within 9 mm that span the two (barrier floor);
  metrics   - the non-global gates / metrics both workstreams re-trigger (verification.json), with the stage-32 value
              from the scorecard where it has one: these must not move when either side changes.
BOM-only lane: per group, the pins and footprints that a part swap must keep, and the metrics it re-triggers.
Controls: every group is in exactly one workstream; every interface net listed has pins on both sides.
"""
import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

WS = {
    "WS1 mains / EMI": ["G01"],
    "WS2 power path": ["G02", "G03"],
    "WS3 resonant tank": ["G04"],
    "WS4 drive / bias / monitor / protect (LS, HS-A, HS-B islands)": ["G05", "G06", "G07", "G08"],
    "WS5 SELV side (CT / ZC detect, J4, PS1)": ["G09", "G10"],
}
TAU = 0.2


def main():
    ctl = C.Controls()
    asg = C.load("assignment.json")["assignment"]
    cb = C.load("combined.json")
    ph = C.load("physical.json")
    ve = C.load("verification.json")
    card = json.loads((C.VR / "10-benchmark/scorecard-native21s32.json").read_text())
    comps, nets = C.netlist()
    g2w = {g: w for w, gs in WS.items() for g in gs}
    ctl.check("every group in exactly one workstream", sorted(g2w) == C.GIDS and sum(len(v) for v in WS.values()) == 10)
    perf = card["performance"]
    gates = card["gates"]

    def value(m):
        if m in perf:
            return perf[m]
        if m in gates:
            return "PASS" if gates[m] else "FAIL"
        return None

    share = ve["group_x_metric_share"]
    glob = set(ve["global_metrics"])
    contracts = []
    for a, b in combinations(WS, 2):
        ga, gb = WS[a], WS[b]
        edges = sorted(((cb["combined"][i][j], f"{i}-{j}") for i in ga for j in gb), reverse=True)
        if edges[0][0] < TAU:
            continue
        inet = []
        for n, nodes in sorted(nets.items()):
            sa = sorted(f"{r}.{p}" for r, p in nodes if asg[r] in ga)
            sb = sorted(f"{r}.{p}" for r, p in nodes if asg[r] in gb)
            if sa and sb:
                inet.append({"net": n, "class": C.net_class(n), "pins_" + a.split()[0]: sa, "pins_" + b.split()[0]: sb})
        ok = all(x[k] for x in inet for k in x if k.startswith("pins_"))
        ctl.check(f"{a.split()[0]}-{b.split()[0]}: interface nets have pins on both sides", ok)
        rk = ph["interleave_mm2"]["by_layer_kind"]
        routed_ab = sum(rk[L]["routed"][i][j] for L in C.LAYERS for i in ga for j in gb)
        routed_ba = sum(rk[L]["routed"][j][i] for L in C.LAYERS for i in ga for j in gb)
        tiles = [t for t in ph["corridors"]["contested_tiles"] if set(t["groups"]) & set(ga) and set(t["groups"]) & set(gb)]
        bar = [r for r in ph["barrier"]["pairs_within_9mm"]
               if (set(r["hot_groups"]) & set(ga) and set(r["selv_groups"]) & set(gb)) or (set(r["hot_groups"]) & set(gb) and set(r["selv_groups"]) & set(ga))]
        bar_cross = [r for r in bar if not ((set(r["hot_groups"]) | set(r["selv_groups"])) <= set(ga)) and not ((set(r["hot_groups"]) | set(r["selv_groups"])) <= set(gb))]
        mets = sorted(m for m in share if m not in glob and any(share[m][i] > 0 for i in ga) and any(share[m][j] > 0 for j in gb))
        contracts.append({
            "between": [a, b], "max_edge": edges[0][0], "edges_at_or_above_0p2": [e[1] for e in edges if e[0] >= TAU],
            "interface_nets": inet, "n_interface_nets": len(inet),
            "routed_copper_in_other_territory_mm2": {f"{a.split()[0]}->{b.split()[0]}": routed_ab, f"{b.split()[0]}->{a.split()[0]}": routed_ba},
            "contested_corridor_tiles": [[t["x"], t["y"]] for t in tiles],
            "barrier_pairs_within_9mm": len(bar_cross), "barrier_min_mm": min((r["mm"] for r in bar_cross), default=None),
            "barrier_closest": [f"{r['hot_net']} / {r['selv_net']} {r['mm']} mm ({r['layer']})" for r in bar_cross[:6]],
            "must_not_move": [{"metric": m, "stage32": value(m)} for m in mets],
        })
    lane = {}
    for g in C.GIDS:
        mets = sorted(m for m in share if m not in glob and share[m][g] > 0)
        lane[g] = {"parts": sum(1 for r in asg if asg[r] == g),
                   "keep": "footprint, pad numbering and pin -> net map of every swapped part; courtyard and height inside "
                           "the enclosure envelopes; heat at or under the B3 c28 input; a datasheet-ledger row",
                   "retriggers": [{"metric": m, "share": share[m][g], "stage32": value(m)} for m in mets]}
    out = {"method": __doc__.split("Controls:")[0].strip(), "workstreams": WS, "threshold": TAU, "contracts": contracts,
           "bom_only_lane": lane, "controls": ctl.rows}
    h = C.write("contracts.json", out)
    for c in contracts:
        print(c["between"], round(c["max_edge"], 3), c["edges_at_or_above_0p2"], "nets", c["n_interface_nets"],
              "tiles", len(c["contested_corridor_tiles"]), "barrier", c["barrier_pairs_within_9mm"], c["barrier_min_mm"],
              "metrics", [m["metric"] for m in c["must_not_move"]])
    print("contracts.json", h[:12])
    ctl.finish()


if __name__ == "__main__":
    main()
