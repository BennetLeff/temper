#!/usr/bin/env python3
"""Round 5 (native-21) against round 4 (native-17), case by case, from both summary.json files.

    python3 compare_native17.py  ->  outputs/compare_native17.json and a printed table

Same imposed currents and pad names on both boards. Round 4 ran every net at 0.125 mm; round 5
runs leg_ret / sw_a / sw_b at 0.0625 mm (resistance a few % lower from pitch alone).
"""
import gzip
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEW = json.loads((HERE / "outputs" / "summary.json").read_text())
R4 = HERE.parent / "round4" / "reextract"
VIAS_NEW = json.loads((HERE / "outputs" / "via_currents.json").read_text())
# round 4 kept per-case results only: rebuild its rows, and tag barrels as vias from its export
_via_xy = {tuple(round(c, 3) for c in it["centre"]) for it in json.load(gzip.open(R4 / "inputs" / "power_copper.json.gz", "rt"))["primitives"]
           if it["kind"] == "via"}
OLD = {"rows": []}
VIAS_OLD = {}
for f in sorted((R4 / "outputs").glob("*-p0125-pl*.json")):
    d = json.loads(f.read_text())
    OLD["rows"].append({"name": f.stem, "r_mohm": d["r_ohm"] * 1e3, "loss_w": d["loss_w"],
                        "layer_max_a_per_mm": d["layer_max_a_per_mm"]})
    VIAS_OLD[f.stem] = [{"kind": "via" if tuple(round(c, 3) for c in v["xy"]) in _via_xy else "pad",
                         "peak_signed_amps": v.get("amps"),
                         "over_3a_flag": tuple(round(c, 3) for c in v["xy"]) in _via_xy and abs(v.get("amps") or 0) > 3}
                        for v in d.get("via_currents", [])]


def key(name):
    m = re.match(r"(.+)-p0\d+-pl(\d+)$", name)
    return (m.group(1), int(m.group(2))) if m else None


def flags(vias):
    return sum(1 for v in vias if v.get("over_3a_flag")), max((abs(v.get("peak_signed_amps") or 0) for v in vias
                                                              if v.get("kind") == "via"), default=0.0)


old = {key(r["name"]): r for r in OLD["rows"] if key(r["name"])}
out = []
for r in NEW["rows"]:
    k = key(r["name"])
    if not k:
        continue
    o = old.get(k)
    pk = max((v["amps_per_mm"], lay) for lay, v in r["layer_max_a_per_mm"].items())
    nf, nmax = flags(VIAS_NEW.get(r["name"], []))
    row = {"case": k[0], "plating_um": k[1], "pitch_mm": r["pitch_mm"], "r_mohm": r["r_mohm"], "loss_w": r["loss_w"],
           "peak_a_per_mm": pk[0], "peak_layer": pk[1], "vias_over_3a": nf, "max_via_a": nmax}
    if o:
        of, omax = flags(VIAS_OLD.get(o["name"], []))
        row["native17"] = {"r_mohm": o["r_mohm"], "loss_w": o["loss_w"], "vias_over_3a": of, "max_via_a": omax,
                           "peak_a_per_mm": max(v["amps_per_mm"] for v in o["layer_max_a_per_mm"].values())}
    out.append(row)
(HERE / "outputs" / "compare_native17.json").write_text(json.dumps(out, indent=1) + "\n")
print(f"{'case':14}{'pl':>3} {'R n17':>7} {'R n21':>7} {'loss n17':>8} {'loss n21':>8} {'A/mm n21':>8} {'via>3A n17/n21':>15} {'max via A n21':>13}")
for r in out:
    o = r.get("native17", {})
    print(f"{r['case']:14}{r['plating_um']:>3} {o.get('r_mohm', float('nan')):7.3f} {r['r_mohm']:7.3f} "
          f"{o.get('loss_w', float('nan')):8.3f} {r['loss_w']:8.3f} {r['peak_a_per_mm']:8.1f} "
          f"{str(o.get('vias_over_3a', '-')) + '/' + str(r['vias_over_3a']):>15} {r['max_via_a']:13.2f}")
