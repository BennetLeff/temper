#!/usr/bin/env python3 -I
"""G01 F1/BR1 options vs the F2 containment criteria (reads ../../02-protection-timing/shoot-through-f1/result.json).
Every fuse number is tagged with where it came from; '(est)' rows are assumptions, not data - they need the datasheet
or a bench test.  stdlib only; writes fuse_br1_g01_results.json."""
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
R = json.load(open(HERE.parents[1] / "02-protection-timing/shoot-through-f1/result.json"))
segs = {}
for s in R["boards"]["19b_record"]["segments"]:
    segs[s.get("segment") or s.get("name") or str(len(segs))] = s["I2t_conservative"]
# real conductor necks (terminal-limited rows are floors, ignored for pass/fail as in the F1 study README)
NECKS = {"shunt R5 -> J10 (HV_RET In1 isthmus)": 355.5, "J8 -> Q2/Q5 drain (BUS_P In2)": 884.0,
         "Q3 source -> R5": 2080.0, "L1 -> BR1 AC1": 1747.0, "F1 -> L1": 4554.0}
BR1_I2T = 510.0     # GBJ2510-F, Diodes DS21221 p.2
SCORE_NECK = 355.5  # scorecard fuse_copper_fusing_ratio = 355/1710 = 0.208
opts = []
def opt(name, melt, clear, src, carry_A, price500, clips500, note):
    opts.append(dict(name=name, melt=melt, clear=clear, src=src, carry_A=carry_A, price500=price500, clips500=clips500, note=note))
# carrying capacity = rating x 0.75 (repo margin) x temp derate at 50 C
opt("KLDR025 (as built)", 226.0, 1710.0, "KLDR datasheet Rev 092821 p.5 (F1 study)", 25 * .75 * .90, 29.412, 6.498, "Class CC TD, 200 kA")
opt("KLKR025 Class CC fast (clearing interpolated)", None, 1244.0,
    "(est) geometric mean of KLKR020 900 and KLKR030 1720 A2s, Littelfuse KLKR datasheet table as quoted by distributor copies", 25 * .75 * .90, None, 6.498, "price not found")
opt("KLKR020 Class CC fast", None, 900.0, "KLKR datasheet table (distributor copy)", 20 * .75 * .90, None, 6.498, "REJECT: carries 13.5 A < 15 A")
for ratio in (1.5, 2.0, 3.0):
    opt(f"Littelfuse 0505025.MXP 6.3x32 fast (clearing = {ratio} x melt) (est)", 145.0, 145.0 * ratio,
        "melt 145 A2s: third-party catalogue text (novapart/e-streloy), datasheet 403 - UNVERIFIED; clearing ratio ASSUMED",
        25 * .75 * .95, 3.0, 3.0, "500 V 20 kA (unverified); supplemental fuse, not UL 248-4 branch fuse")
rows = []
for o in opts:
    c = o["clear"]
    row = dict(o)
    row["BR1_half_ok"] = c < 0.5 * BR1_I2T
    row["fusing_ratio_scorecard"] = SCORE_NECK / c
    row["copper_target_2x"] = 2 * c
    row["necks_failing_1x"] = [k for k, v in NECKS.items() if v < c]
    row["necks_failing_2x"] = [k for k, v in NECKS.items() if v < 2 * c]
    row["carries_15A"] = o["carry_A"] >= 15.0
    if o["price500"] is not None:
        row["F1_plus_clips_500"] = o["price500"] + o["clips500"]
    rows.append(row)
    print(f"{o['name'][:70]:70s} clear {c:7.0f}  ratio {SCORE_NECK/c:5.2f}  BR1<255 {row['BR1_half_ok']!s:5}  carry {o['carry_A']:.1f} A  "
          f"2x-target {2*c:6.0f}  necks failing at 2x: {len(row['necks_failing_2x'])}")
# inrush/surge as % of melting I2t (F1-RECOMMENDATION 3.4 estimates, 'my estimates')
for nm, i2t in (("plug-in at crest (<=0.99)", 0.99), ("IRM cold start (~1)", 1.0), ("1 kA 8/20 surge via RV1", 12.2)):
    print(f"  {nm:28s} {i2t:5.2f} A2s = {100*i2t/145:.1f} % of 145 A2s melt")
# BR1 required survival I2t at 2x margin
print("BR1 I2t needed for survival (clearing/0.5): " + ", ".join(f"{c}->{c/0.5:.0f}" for c in (218, 290, 435, 1244, 1710)))
print("Best single-phase bridge I2t found: KBPC5010 (MDD newer rev) IFSM 500 A -> 1038 A2s (distributor/aggregator text, unverified); GBJ3510 374; GBJ2510 510")
json.dump(dict(rows=rows, necks=NECKS, BR1_I2t=BR1_I2T), open(HERE / "fuse_br1_g01_results.json", "w"), indent=1)
