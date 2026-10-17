#!/usr/bin/env python3 -I
"""Collect the result JSONs into results/summary.md (tables quoted in ANALYSIS.md)."""
import json, sys
sys.dont_write_bytecode = True
from pathlib import Path
from collections import defaultdict
R = Path(__file__).resolve().parent.parent/"results"
L = lambda n: json.load(open(R/n))
out = []
gs = L("gate_sens.json"); agg = defaultdict(lambda: [-1e9, -1e9])
for r in gs:
    k = (r["leg"], r["dL"]); agg[k][0] = max(agg[k][0], r["vds_pk"]); agg[k][1] = max(agg[k][1], r["off_V"])
out.append("## Worst S4 cases (top 3 die VDS + top 3 off-gate per leg), dL added in series with both gate ports\n")
out.append("| dL (nH) | leg A die VDS (V) | leg A off-gate (V) | leg B die VDS (V) | leg B off-gate (V) |\n|---:|---:|---:|---:|---:|")
for dl in sorted({k[1] for k in agg}):
    a, b = agg[("A", dl)], agg[("B", dl)]
    out.append(f"| {dl:g} | {a[0]:.1f} | {a[1]:.3f} | {b[0]:.1f} | {b[1]:.3f} |")
if (R/"gate_full.json").exists():
    gf = L("gate_full.json"); by = defaultdict(list)
    for r in gf: by[(r["leg"], r["dL"])].append(r)
    out.append("\n## Whole decision + startup set (S1/S2/S4/S5, 27/100/150 C, both legs), dL in both gate ports\n")
    out.append("| leg | dL (nH) | cases | indeterminate | max die VDS (V) | VDS limit fails | max off-gate (V) | 1.9 V fails | ZVS fails (S1 only) | worst |VGS| (V) |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for (leg, dl) in sorted(by):
        rows = by[(leg, dl)]; ok = [r for r in rows if r["status"] == "complete"]
        z = [r for r in ok if r["case"]["case"] == "S1" and not r["zvs"]]
        out.append(f"| {leg} | {dl:g} | {len(rows)} | {len(rows)-len(ok)} | {max(r['vds_pk'] for r in ok):.1f} | {sum(not r['pass_vds'] for r in ok)} | {max(r['off_V'] for r in ok):.3f} | {sum(not r['pass_1p9'] for r in ok)} | {len(z)} | {max(r['vgs_abs'] for r in ok):.2f} |")
    # base ZVS failures for reference
    out.append("\nBase (dL = 0) S1 ZVS flags come from the committed results; S1 rows with `base_zvs` false: " + str(sum(1 for r in gf if r['status']=='complete' and r['case']['case']=='S1' and r.get('base_zvs') is False)) + " of " + str(sum(1 for r in gf if r['status']=='complete' and r['case']['case']=='S1')))
if (R/"gate_sens_drv.json").exists():
    dv = L("gate_sens_drv.json"); key = lambda r: (r["leg"], r["dL"], tuple(sorted(r["case"].items())))
    pm = {key(r): r for r in gs if r["status"] == "complete"}
    diffs = [abs(r["vds_pk"]-pm[key(r)]["vds_pk"]) for r in dv if r["status"] == "complete" and key(r) in pm]
    diffo = [abs(r["off_V"]-pm[key(r)]["off_V"]) for r in dv if r["status"] == "complete" and key(r) in pm]
    out.append(f"\nL at the driver output node instead of the gate port ({len(diffs)} matched cases, {sum(r['status']!='complete' for r in dv)} indeterminate): max |dVDS| = {max(diffs):.3f} V, max |d off-gate| = {max(diffo):.4f} V")
ci = L("conn_inductance.json")
out.append("\n## Connector loop inductance added per gate path (computed)\n")
out.append("| connector | signal/return pairs in parallel | connector loop (nH) | vias (nH) | breakout stubs 2x10 mm (nH) | total (nH) |\n|---|---:|---:|---:|---:|---:|")
for r in ci["rows"]:
    out.append(f"| {r['connector']} | {r['pairs']} | {r['loop_conn_nH']} | {r['vias_nH']} | {r['stubs_nH']} | {r['total_added_nH']} |")
(R/"summary.md").write_text("\n".join(out)+"\n"); print("\n".join(out))
