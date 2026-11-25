#!/usr/bin/env python3
"""Stage 56 ledger edits (OPEN-ITEMS S22): R127 / R129 move from 0603WAF2702T5E (27 k) to RT0603BRD0716KL (16 k).

    python3 -I validation-results/11-candidates/c56-s56-scope/scripts/apply_ledger56.py   -> ledger.json (in place, idempotent)

Temperatures: the temp-ratings per-reference rows (the pads do not move and the new dissipation is lower). Electrical: the CTRL
corners of results/s56-scope.json for the moved pair, c54's net_stress rows for the four that stay.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PS = HERE.parents[2]
LED = PS / "native-21/verification/datasheet-ledger/ledger.json"
REL = str(HERE.relative_to(PS))
TR = "validation-results/04-board-current-thermal/round5-native21/b3-ratings/temp-ratings-2026-10-15/results.json"
NS = "validation-results/11-candidates/c54-ledger-desk/results/net_stress.md"
scope = json.loads((HERE / "results/s56-scope.json").read_text())["ctrl_divider"]["16k (RT0603BRD0716KL, R34's line)"]
temps = {}


def walk(o):
    if isinstance(o, dict):
        if "ref" in o and "cases" in o:
            temps[o["ref"]] = {c: r["est_c"] for c, r in o["cases"].items()}
        for v in o.values():
            walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)


walk(json.loads((PS / TR).read_text()))
led = json.loads(LED.read_text())
E = led["entries"]


def row(rows, key, start):
    hit = [r for r in rows if r[key].startswith(start)]
    assert len(hit) == 1, (start, len(hit))
    return hit[0]


# ---- 0603WAF2702T5E: R137 / R139 / R141 / R143 stay
e, stay = E["0603WAF2702T5E"], ["R137", "R139", "R141", "R143"]
e["designators"] = stay
e["function"] = "27 k: the TPS70950 LDO EN divider bottoms (stage 48); the R24C2T25 CTRL pair R127 / R129 went to 16 k at stage 56"
t28, w28 = max((temps[r]["c28_h10"], r) for r in stay)
ns = {}
for line in (PS / NS).read_text().splitlines():
    if line.split(" ")[0] in stay:
        ns[line.split(" ")[0]] = (float(line.split("|V|max ")[1].split(" V;")[0].split(" / ")[1]), float(line.split("; P ")[1].split(" mW")[0].split(" / ")[1]))
vmax, vr = max((v[0], r) for r, v in ns.items())
pmax, pr = max((v[1], r) for r, v in ns.items())
lim = row(e["ratings"], "parameter", "Terminal temperature limit at P (derating line, 20 % margin), c28")
lim["parameter"] = f"Terminal temperature limit at P (derating line, 20 % margin), c28 worst ref {w28}"
lim["datasheet_limit"] = 154.5
lim["basis"] = "same line at 0.0004657 W (U3 EN divider bottom)"
s = row(e["stresses"], "parameter", "Local temperature, c28")
s["worst_case_value"] = t28
s["condition"] = s["condition"].replace("R127:", f"{w28}:").replace("worst of 6 ref(s)", "worst of 4 ref(s)")
r = row(e["stresses"], "parameter", "Local temperature, release")
r["condition"] = r["condition"].replace("worst of 6 ref(s)", "worst of 4 ref(s)")
for start, val, ref in (("Voltage across", vmax, vr), ("Power (worst", round(pmax / 1e3, 7), pr)):
    s = row(e["stresses"], "parameter", start)
    s["worst_case_value"] = val
    s["condition"] = f"{ref}: static worst case over the registry rail ranges (fault envelopes included)"
    s["evidence"] = [f"{NS}:{i}" for i, ln in enumerate((PS / NS).read_text().splitlines(), 1) if ln.startswith(ref + " ")]
c = row(e["checks"], "id", "temperature, c28")
c.update(rating=lim["parameter"], rule=f"{t28} C <= 154.5 C ({w28}); an overrun is the airflow-route (c22/c28) owner gap", ratio=round(t28 / 154.5, 4))
c = row(e["checks"], "id", "V working")
c.update(rule=f"{vmax:g} V <= 51.9615 V ({vr})", ratio=round(vmax / 51.96152422706632, 4))
c = row(e["checks"], "id", "P <=")
c.update(rule=f"{pmax:.3g} mW <= 50 % of 100 mW ({pr})", ratio=round(pmax / 100, 4))

# ---- RT0603BRD0716KL: R34 plus the CTRL pair, rated at the PS2-clamp case
e, pair = E["RT0603BRD0716KL"], ["R127", "R129"]
e["designators"] = pair + ["R34"]
e["function"] = "16 k 0.1 %: R34 OCP threshold top (REF25 to ocp_thresh; S23 B'-1.02 V); R127 / R129 R24C2T25 CTRL divider bottoms (stage 56, S22)"
e["designators"].sort(key=lambda d: int(d[1:]))
v = scope["V_max_at_PS2_clamp"]
p = v * v / (16e3 * 0.999)
limit = int((155 - 85 * p / 0.08) * 10) / 10
tl = row(e["ratings"], "parameter", "Terminal temperature limit at P")
tl["datasheet_limit"] = limit
tl["basis"] = f"155 - (155 - 70) x {p:.6f} W / (0.8 x 0.1 W): operating -55..+155 C and the Fig. 6 derating line with the G6 20 % power margin (R127 / R129 at the PS2 clamp, the worst of the line)"
for start, name, val, cond in (("V across", "V across (worst ref)", v, f"R127 / R129: CTRL at PS2's 32.4 V clamp (R34 1.491 V)"),
                               ("P in", "P (worst ref)", round(p, 7), "V^2 / 15.984 k at the PS2 clamp (R34 0.139 mW)")):
    s = row(e["stresses"], "parameter", "V across" if start == "V across" else ("P in" if any(x["parameter"].startswith("P in") for x in e["stresses"]) else "P (worst"))
    s.update(parameter=name, worst_case_value=val, condition=cond, evidence=f"{REL}/results/s56-scope.json; elec/src/f6_bias.ato; audit.rs stage56")
for case, start in (("c17.5_h10", "Local temperature, release"), ("c28_h10", "Local temperature, c28")):
    s = row(e["stresses"], "parameter", start)
    t, ref = max((temps[x][case], x) for x in pair)
    bay = "61" if case == "c17.5_h10" else "55"
    s.update(worst_case_value=t, condition=f"{ref}: terminal (pad), B3 hot-copper estimate, {case} still air at bay {bay} C; board s52 rows, pads unmoved since (R34 {'97.29' if bay == '61' else '103.65'} C, board s49)", evidence=f"{TR}; validation-results/11-candidates/c49-c34-bank/results/bands-s49.json")
    k = row(e["checks"], "id", "temperature, release" if bay == "61" else "temperature, c28")
    k.update(rule=f"{t} C <= {limit} C ({ref})" + ("" if bay == "61" else "; an overrun is the airflow-route (c22/c28) owner gap"), ratio=round(t / limit, 4))
k = row(e["checks"], "id", "V")
k.update(stress="V across (worst ref)", rule=f"{v} V <= half the 75 V working voltage", ratio=round(v / 75, 4))
k = row(e["checks"], "id", "P")
k.update(stress="P (worst ref)", rule=f"{p * 1e3:.3f} mW <= half of 0.1 W", ratio=round(p / 0.1, 4))
note = " S56 (2026-11-24, 11-candidates/c56-s56-scope): R127 / R129 join this line (CTRL dividers, S22)."
if note not in e["notes"]:
    e["notes"] += note
LED.write_text(json.dumps(led, indent=1, ensure_ascii=False) + "\n")
print("ledger: stage 56 applied")
