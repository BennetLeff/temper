#!/usr/bin/env python3
"""Write patches/open-items-S21-J1.patch: the J1 clauses of OPEN-ITEMS S21 re-stated on the c54 result.

    python3 -I scripts/make_open_items_patch.py

Reads PS/OPEN-ITEMS.md and results/j1_thermal.json; replaces three J1 clauses of the S21 row (finding, status, next) and
writes a unified diff. Nothing in PS is modified. Stops if a clause is not found verbatim (the row moved on).
"""
import difflib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PS = ROOT.parents[2]
SRC = PS / "OPEN-ITEMS.md"
OUT = ROOT / "patches" / "open-items-S21-J1.patch"


def main():
    t = json.loads((ROOT / "results" / "j1_thermal.json").read_text())
    rel, trip, fb = t["release_14awg_13p5A"], t["trip_14awg_15A"], t["fixes"]["b_neutral_copper"]
    s = SRC.read_text()
    subs = [
        ("J1 MKDS 5/2-9,5 104.6 / 105 °C (+0.4 K; own rise scaled from Phoenix's 6 mm² curve, so with the 14 AWG cord it "
         "is larger: not a demonstrated pass);",
         f"J1 MKDS 5/2-9,5 clamp {rel['low']['t_c']:.1f}–{rel['high']['t_c']:.1f} °C (central {rel['central']['t_c']:.1f}) "
         f"/ 105 °C on the s53 board with the real 14 AWG lead (**+{105 - rel['high']['t_c']:.1f} K** at the high bound; "
         "c54-j1-thermal two-node model: the lead in bay air is a heat sink because the B3 pad, 99.0 °C, is hotter than "
         "the lead; the earlier 104.6 / 103.1 °C was pad + the 6 mm² curve scaled, not a bound); at a sustained 15 A "
         f"{trip['high']['t_c']:.1f} °C ({105 - trip['high']['t_c']:+.1f} K);"),
        ("J1: bench + cord-size thermal;", "J1: c54 fix (b) layout + bench;"),
        ("**Ledger done; J1 open**", "**Ledger done; J1 modelled (c54), fix (b) proposed, bench open**"),
        ("Measure or model J1 with the real cord (14 AWG) and torque; if it fails, the derated-current or a larger "
         "terminal (J1 is the line inlet);",
         "J1 (c54-j1-thermal): land the J1.2 neutral F.Cu strip (fix (b): release high bound "
         f"{fb['release_13p5A']['high']['t_c']:.1f} °C, +{105 - fb['release_13p5A']['high']['t_c']:.1f} K; 15 A "
         f"{fb['trip_15A']['high']['t_c']:.1f} °C) with the B3 J1 gated row (`patches/b3-gate-j1-row.patch`) and the "
         "ledger patch; bench per c54 README §6 (mV drop at 13.5 A on 14 AWG, thermocouples on the screws, J1.2 pad and "
         "the lead); 12 AWG cord is the fallback;"),
    ]
    new = s
    for old, rep in subs:
        if new.count(old) != 1:
            raise SystemExit(f"make_open_items_patch: clause not found once: {old[:60]}...")
        new = new.replace(old, rep)
    diff = difflib.unified_diff(s.splitlines(keepends=True), new.splitlines(keepends=True),
                                fromfile="a/zapote/power-stage-120v/OPEN-ITEMS.md",
                                tofile="b/zapote/power-stage-120v/OPEN-ITEMS.md", n=1)
    OUT.write_text("".join(diff))
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
