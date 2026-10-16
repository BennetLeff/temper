#!/usr/bin/env python3
"""Rail-monitor probe rows and the unrated-semiconductor sweep (OPEN-ITEMS S16; report only, no gating here).

    python3 -I monitor_sweep.py [--runs ../../runs] [--margins ../../margins.json] [--out ../monitor-sweep.json]

Inputs: the hot-copper BASIS run files (run_basis.py default, body_runs probes = pad-copper temperature of every
footprint), b3-ratings/margins.json (which refs already have a B3 row), native-21/frozen/default.csv (the s42 BOM; it
matches the s42 c42b schematic value fields), native-21/verification/datasheet-ledger/ledger.json (read only).

1. Monitor rows: the gate's probe rows (b3_ratings_gate.MONITORS, gated) per BASIS case, plus each monitor IC's margin
   against the 125 C grade of the same pinout (TL431BQDBZR SLVS543S p.4 / 6.4 p.5 TL43xxQ; LM2901BIDR SLCS006Z 6.4 p.6,
   LM2901B TA -40..125; the TLVH431BQ already is the Q grade).
2. Sweep: every BOM semiconductor (U, Q, D, BR, PS) with no B3 row. Rating = the ledger's temperature ratings, else a
   TA grade read this session from a TI / Infineon datasheet in runs-native21/s16-monitor-dl (VERIFIED below), else
   none. Listed: rating <= 105 C (margin = rating - pad estimate, the gate's estimator, no self-heat), and every part
   with no rating anywhere (pad temperature only). A TJ rating against a pad temperature is optimistic by the part's
   self-heat; a TA rating against the pad is the gate's local-ambient proxy.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAT = HERE.parents[1]
UNIT = RAT.parents[3]
sys.dont_write_bytecode = True
sys.path.insert(0, str(RAT))
import b3_ratings_gate as gate  # noqa: E402

DL = "worktrees/runs-native21/s16-monitor-dl (MANIFEST.json sha256)"
VERIFIED = {   # MPN -> (TA max C, source); read 2026-10-15 from the datasheet text extracts in DL
    "TL431AIDBZR": (85.0, "TI SLVS543S 6.4 p.5, TL43xxI TA -40..85"),
    "TLVH431BQDBZR": (125.0, "TI SLVS555N 5.3 p.5, TLVH43x_Q TA -40..125"),
    "LM339BIDR": (85.0, "TI SLCS006Z 6.4 p.6, LM339B TA -40..85"),
    "LM4040A25IDBZR": (85.0, "TI SLOS456Q 6.3 p.5, LM4040xxxI TA -40..85"),
    "2EDR8259XXUMA1": (125.0, "Infineon 2EDRx259X Rev 1.7 TA -40..125"),
}
GRADE125 = {"tl431": ("TL431BQDBZR", 125.0), "lm339b": ("LM2901BIDR", 125.0), "tlvh431": ("TLVH431BQDBZR (as built)", 125.0)}
SEMI = re.compile(r"^(U|Q|D|BR|PS)\d+$")
TEMP = re.compile(r"(^T[_ ]?[JA]\b|^Tj|^TJ|T working|ambient|junction|operating temp)", re.I)


def load_case(runs, c):
    return [json.loads((runs / f"{c}_p0p{m}.json").read_text()) for m in ("25", "5")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(RAT / "runs"))
    ap.add_argument("--margins", default=str(RAT / "margins.json"))
    ap.add_argument("--out", default=str(HERE.parent / "monitor-sweep.json"))
    a = ap.parse_args()
    runs = Path(a.runs)
    m = json.loads(Path(a.margins).read_text())
    cases = {c: v["bay_c"] for c, v in m["basis"]["cases"].items()}
    data = {c: load_case(runs, c) for c in cases}
    for c, (r25, r05) in data.items():
        assert r25["board_sha256"] == r05["board_sha256"] == m["board_sha256"][c], c
        assert r25["copper_temp_model"]["model"] == "hot-iterated", c

    def pad_est(c, ref):
        r25, r05 = data[c]
        return gate.est(r25["probes"][ref]["pad_max_cell_c"], r05["probes"][ref]["pad_max_cell_c"], cases[c])

    # ---- 1. monitor rows
    mon = []
    for ref, (kind, basis, lim, _) in gate.MONITORS.items():
        sh = gate.MONITOR_SELF[kind] * gate.RTHJA[kind][0]
        g_mpn, g_lim = GRADE125[kind]
        row = {"ref": ref, "row": basis, "limit_c": lim, "self_heat_w": round(gate.MONITOR_SELF[kind], 5),
               "rthja": gate.RTHJA[kind], "self_heat_k": round(sh, 2), "grade125": g_mpn, "cases": {}}
        for c in cases:
            t = pad_est(c, ref) + sh
            row["cases"][c] = {"bay_c": cases[c], "pad_est_c": round(pad_est(c, ref), 1), "est_c": round(t, 1),
                               "margin_k": round(lim - t, 1), "margin_125_k": round(g_lim - t, 1)}
        mon.append(row)

    # ---- 2. sweep
    led = json.loads((UNIT / "native-21/verification/datasheet-ledger/ledger.json").read_text())["entries"]
    led_by_ref = {}
    for e in led.values():
        temps = [(r["parameter"], float(r["datasheet_limit"]), r.get("source", "")) for r in e.get("ratings", [])
                 if TEMP.search(r["parameter"]) and isinstance(r.get("datasheet_limit"), (int, float))
                 and r.get("unit") in ("C", "°C", "degC")]
        for d in e["designators"]:
            led_by_ref[d] = (e["mpn"], e["status"], temps)
    bom = {}
    for r in csv.DictReader(open(UNIT / "native-21/frozen/default.csv")):
        for d in r["Designator"].split(","):
            bom[d.strip()] = r["Comment"]
    has_row = {it["item"].split(":")[0] for rows in m["cases"].values() for it in rows}
    c_rel = next(c for c, v in m["basis"]["cases"].items() if v["role"] == "release")
    c28 = "c28_h10"
    rated, unrated, skipped = [], [], []
    for ref in sorted((r for r in bom if SEMI.match(r)), key=lambda r: (re.match(r"\D+", r).group(), int(re.sub(r"\D", "", r)))):
        mpn = bom[ref]
        if ref in has_row:
            skipped.append(ref)
            continue
        if ref not in data[c_rel][0]["probes"]:
            raise SystemExit(f"{ref} has no probe on the board")
        lm = led_by_ref.get(ref)
        rating = None
        if lm and lm[2]:
            p, v, src = min(lm[2], key=lambda t: t[1])
            rating = {"limit_c": v, "parameter": p, "source": f"ledger ({lm[1]}): {src}"}
        elif mpn in VERIFIED:
            rating = {"limit_c": VERIFIED[mpn][0], "parameter": "TA max", "source": VERIFIED[mpn][1] + f"; {DL}"}
        row = {"ref": ref, "mpn": mpn, "ledger_status": lm[1] if lm else "absent",
               "pad_est_c": {c_rel: round(pad_est(c_rel, ref), 1), c28: round(pad_est(c28, ref), 1)}}
        if rating is None:
            unrated.append(row)
            continue
        if rating["limit_c"] > 105.0:
            continue
        row.update(rating=rating, margin_k={c: round(rating["limit_c"] - t, 1) for c, t in row["pad_est_c"].items()},
                   in_gate=ref in gate.MONITORS)
        rated.append(row)
    out = {"board_sha256": m["board_sha256"][c_rel], "cases": cases, "release_case": c_rel,
           "estimator": "gate.est(pad max 0.25, pad max 0.5, bay): Q25 + 3|Q25 - Q05| + (bay - 50); probes = pad-copper "
                        "maximum over all pads on the mounting layer (hot-copper BASIS run files)",
           "monitor_rows": mon,
           "sweep_rated_le_105c": rated,
           "sweep_unrated": sorted(unrated, key=lambda r: -r["pad_est_c"][c_rel]),
           "semis_with_b3_rows": sorted(skipped)}
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"{'ref':5} {'row':62} " + " ".join(f"{c:>18}" for c in cases))
    for r in mon:
        print(f"{r['ref']:5} {r['row'][:62]:62} " + " ".join(
            f"{r['cases'][c]['est_c']:6.1f} {r['cases'][c]['margin_k']:+6.1f}/{r['cases'][c]['margin_125_k']:+5.1f}" for c in cases))
    print("\nsweep, rated <= 105 C, no B3 row:")
    for r in rated:
        print(f"  {r['ref']:5} {r['mpn']:18} {r['rating']['limit_c']:5.0f} C  {c_rel} {r['pad_est_c'][c_rel]:6.1f} "
              f"({r['margin_k'][c_rel]:+.1f} K)  {c28} {r['pad_est_c'][c28]:6.1f} ({r['margin_k'][c28]:+.1f} K)  "
              f"{'[gated monitor]' if r['in_gate'] else ''} {r['rating']['source'][:60]}")
    print(f"\nsweep, no rating in the ledger or the datasheets read ({len(unrated)}):")
    for r in out["sweep_unrated"]:
        print(f"  {r['ref']:5} {r['mpn']:18} {c_rel} {r['pad_est_c'][c_rel]:6.1f}  {c28} {r['pad_est_c'][c28]:6.1f}  "
              f"ledger {r['ledger_status']}")


if __name__ == "__main__":
    main()
