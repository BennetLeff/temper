#!/usr/bin/env python3
"""Write patches/ledger-1714971.patch: the datasheet-ledger entry for J1 (1714971) re-based on the c54 model.

    python3 -I scripts/make_ledger_patch.py [--check-root DIR]

Reads native-21/verification/datasheet-ledger/ledger.json (PS HEAD working tree) and results/j1_thermal.json, edits only
the 1714971 entry, re-serializes with the file's own format (json indent 1, ASCII; the script stops if the unmodified file
does not round-trip byte for byte) and writes a unified diff against the repo path. Nothing in PS is modified.
--check-root DIR: also write the patched ledger to DIR/ledger.json (for running gate.py --ledger on it).
"""
import argparse
import difflib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PS = ROOT.parents[2]
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
REPO_PATH = "zapote/power-stage-120v/native-21/verification/datasheet-ledger/ledger.json"
OUT = ROOT / "patches" / "ledger-1714971.patch"
C54 = "validation-results/11-candidates/c54-j1-thermal"
EVID = [f"{C54}/results/j1_thermal.json", f"{C54}/README.md", f"{C54}/scripts/j1_thermal.py"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-root")
    a = ap.parse_args()
    raw = LEDGER.read_text()
    led = json.loads(raw)
    if json.dumps(led, indent=1) + "\n" != raw:
        raise SystemExit("make_ledger_patch: ledger.json does not round-trip with indent=1; refusing to re-serialize")
    t = json.loads((ROOT / "results" / "j1_thermal.json").read_text())
    rel, c28, trip = t["release_14awg_13p5A"], t["c28_14awg_13p5A"], t["trip_14awg_15A"]
    fb = t["fixes"]["b_neutral_copper"]
    e = led["entries"]["1714971"] if isinstance(led["entries"], dict) else next(x for x in led["entries"] if x["mpn"] == "1714971")

    rating = next(r for r in e["ratings"] if r["unit"] == "C")
    rating["basis"] = ("Ambient (operation) -40..105 C 'depending on the current carrying capacity / derating curve' "
                       "(p.5); IEC 60947-7-4 rise test: ambient + rise <= upper limiting temperature (p.4). Applied to "
                       "the clamp (terminal point), where the inlet lead's 105 C insulation (F1-RECOMMENDATION.md:179) "
                       "is the same limit. The p.6 derating curve is for 6 mm2 conductors (nominal section 4 mm2, p.1) "
                       "and is not used for the 14 AWG lead [c54-j1-thermal 2026-10-18]. cULus E60425 (B/C 300 V 30 A) "
                       "and CSA 13631 state no temperature; UL 1059's component rise limit is 30 K at 25 C ambient "
                       "(Phoenix electrical-tests page), an approval test at 30 A, not an end-product limit")

    def stress(param, value, cond):
        s = next((x for x in e["stresses"] if x["parameter"] == param), None)
        new = {"parameter": param, "worst_case_value": value, "unit": "C", "condition": cond, "evidence": EVID}
        if s is None:
            e["stresses"].append(new)
        else:
            s.clear(); s.update(new)

    common = ("J1 clamp (terminal point), c54-j1-thermal two-node model with the 14 AWG inlet lead: B3 hot-pole pad "
              "(J1.2, nothing attached) through the 0.9 mm pin, clamp I^2 R_pole (0.4-1.0 mohm), the lead as a "
              "Joule-heated insulated fin in bay air, the PA housing to board-heated air; maximum over the input grid")
    stress("Local temperature, release case (c17.5_h10 @ 61 C)", rel["high"]["t_c"],
           f"{common} (low {rel['low']['t_c']} / central {rel['central']['t_c']} C); B3 pad {rel['high']['t_p0']} C at "
           "13.5 A, still air, bay 61 C; board s53 82af7bd9. Replaces temp-ratings' pad + 4.09 K (6 mm2 curve scaled)")
    stress("Local temperature, c28_h10 @ 55 C", c28["high"]["t_c"],
           f"{common} (low {c28['low']['t_c']} / central {c28['central']['t_c']} C); B3 pad {c28['high']['t_p0']} C, "
           "c28_h10 still air at bay 55 C; board s53 82af7bd9")
    stress("Local temperature at the 15 A trip (c17.5_h10 @ 61 C)", trip["high"]["t_c"],
           f"{common} (low {trip['low']['t_c']} / central {trip['central']['t_c']} C) at a sustained 15 A, B3 pad "
           f"scaled to {trip['t_p0_range_c'][0]}-{trip['t_p0_range_c'][1]} C (line-driven share x (15/13.5)^2); the "
           f"15 A trip is not a steady operating point. With c54 fix (b) (J1.2 neutral F.Cu strip): "
           f"{fb['trip_15A']['high']['t_c']} C")

    def check(cid, stress_p, sev, rule, value):
        c = next((x for x in e["checks"] if x["id"] == cid), None)
        new = {"id": cid, "rating": rating["parameter"], "stress": stress_p, "max_ratio": 1.0, "severity": sev,
               "rule": rule, "ratio": round(value / 105.0, 4)}
        if c is None:
            e["checks"].append(new)
        else:
            c.clear(); c.update(new)

    check("temperature, release case (temp-ratings 2026-10-15)", "Local temperature, release case (c17.5_h10 @ 61 C)",
          "violation", f"{rel['high']['t_c']} C <= 105.0 C (J1 clamp, c54 grid maximum)", rel["high"]["t_c"])
    check("temperature, c28 (temp-ratings 2026-10-15)", "Local temperature, c28_h10 @ 55 C", "gap",
          f"{c28['high']['t_c']} C <= 105.0 C (J1 clamp); an overrun is the airflow-route (c22/c28) owner gap",
          c28["high"]["t_c"])
    check("temperature, 15 A trip (c54)", "Local temperature at the 15 A trip (c17.5_h10 @ 61 C)", "gap",
          f"{trip['high']['t_c']} C <= 105.0 C (J1 clamp at a sustained 15 A; c54 fix (b) gives "
          f"{fb['trip_15A']['high']['t_c']} C)", trip["high"]["t_c"])

    e["gaps"] = [g for g in e["gaps"] if not g.startswith("[temp-ratings 2026-10-15]")] + [
        "[c54-j1-thermal 2026-10-18] the clamp temperature is a model bound (B3 pad, R_pole 0.4-1.0 mohm at 0.5-0.6 Nm, "
        "the 14 AWG lead in bay air within 5 K of the bay over its first 10 cm), not a measurement: bench (c54 README "
        "section 6) the mV drop clamp-to-pad at 13.5 A on the 14 AWG lead and thermocouples on both screws, the J1.2 pad "
        "and the lead 50 mm out; release margin +" + f"{105.0 - rel['high']['t_c']:.1f}" + " K at the high bound; at "
        f"a sustained 15 A the high bound is {trip['high']['t_c']} C ({105.0 - trip['high']['t_c']:+.1f} K), "
        f"{fb['trip_15A']['high']['t_c']} C with fix (b).",
        "[c54-j1-thermal 2026-10-18] certifier: UL 858 temperature-test limits for the terminal housing (RTI of the "
        "Phoenix PA, not published; UL Product iQ E60425 needs a login) and for the lead insulation were not read "
        "(standard not available); UL 1059's 30 K at 25 C is the component's own approval test.",
    ]
    lg = {"item": "J1 clamp <= 105 C at the release case (c54 two-node model on the B3 pad probe)",
          "enforced_by": "validation-results/04-board-current-thermal/round5-native21/b3-ratings/b3_ratings_gate.py"}
    if lg not in e["layout_guidance"]:
        e["layout_guidance"].append(lg)
    lg2 = {"item": "J1.2 neutral feed: ac_n_in F.Cu strip mirroring the B.Cu edge strip x 283.6-289.4, y 3.5-26.5, "
                   "landed on J1.2's F.Cu pad (c54 fix b)",
           "enforced_by": "UNCHECKED: layout change proposed for the integration session (c54-j1-thermal README 5)"}
    if lg2 not in e["layout_guidance"]:
        e["layout_guidance"].append(lg2)

    new = json.dumps(led, indent=1) + "\n"
    diff = difflib.unified_diff(raw.splitlines(keepends=True), new.splitlines(keepends=True),
                                fromfile=f"a/{REPO_PATH}", tofile=f"b/{REPO_PATH}", n=3)
    OUT.write_text("".join(diff))
    if a.check_root:
        Path(a.check_root).mkdir(parents=True, exist_ok=True)
        (Path(a.check_root) / "ledger.json").write_text(new)
    print(f"wrote {OUT.name}: release {rel['high']['t_c']} C, c28 {c28['high']['t_c']} C, 15 A {trip['high']['t_c']} C")


if __name__ == "__main__":
    main()
