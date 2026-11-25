#!/usr/bin/env python3
"""Pad-centre fit of the s56 BOM lines that cpl-rotation-audit had no JLC geometry for.

    python3 -I compare_lands.py EASYEDA_RAW_DIR     (raw <LCSC>.json from the public EasyEDA/LCEDA component API)
    -> jlc-pads.json (distilled, committed) and results.json; without an argument it re-reads jlc-pads.json.

Same measure as zapote/controller/tools/check_land_patterns.py: RMS pad-centre distance at the best 90 degree rotation,
limit 0.30 mm. It does not check pad size, courtyard, height or which pin is which; pads whose numbers differ between
JLC and KiCad are reported, not passed. C-codes JLC's library does not have are listed as NOT CHECKED."""
import json, math, sys, pathlib
HERE = pathlib.Path(__file__).resolve().parent
AUD = HERE.parents[1] / "08-manufacturing-package/native-21/cpl-rotation-audit/sources/kicad-footprints.json"
BOM = HERE.parents[1] / "08-manufacturing-package/native-21/fab/bom-jlcpcb.csv"
import csv
CODES = ("C3299886 C3802167 C138687 C85980 C128504 C3163739 C92145 C6708126 C160900 C5481600 C7084710 C6675337 C4175647 "
         "C2793964 C728597 C326732 C137279 C728510 C4036134 C1382388 C22962 C50132500 C17455725 C145344 C9900245652 C5216431").split()
LIMIT = 0.30
# JLC pad number -> KiCad pad number where the two libraries number differently (each read by hand, 2026-11-25):
#   C5   two pads per terminal, 3/4 swapped on one net (both hv_ret)
#   PS2  JLC symbol C6675337: 1 = -V, 2 = +V, 3 = AC/N, 4 = AC/L; KiCad 1 = AC/L (tco_l), 2 = AC/N (n_filt), 3 = -V (n_ls),
#        4 = +V (v24_raw)
#   U1   2EDR8259X pins 12/13/14 on the DWK footprint's pads 14/15/16 (DECISIONS 31)
#   J3   2-position VH at 7.92 mm: JLC keeps the 3-way numbering
REMAP = {"C5": {"3": "4", "4": "3"}, "PS2": {"1": "3", "2": "4", "3": "2", "4": "1"},
         "U1": {"12": "14", "13": "15", "14": "16"}, "J3": {"3": "2"}}
KELVIN = {"R5": ("1", "4")}   # the force pads of a 4-pad Kelvin land against JLC's two pads (geometry of the ends only)


def distil(raw):
    out = {}
    for c in CODES:
        f = raw / f"{c}.json"
        if not f.exists() or f.read_bytes()[:16] != b'{"success":true,':
            continue
        r = json.loads(f.read_text())["result"]
        pads = []
        for s in r["packageDetail"]["dataStr"]["shape"]:
            if s.startswith("PAD~"):
                v = s.split("~")
                pads.append({"n": v[8], "x": float(v[2]) * .254, "y": float(v[3]) * .254, "w": float(v[4]) * .254, "h": float(v[5]) * .254})
        out[c] = {"package": r["packageDetail"]["title"], "title": r.get("title"), "pads": pads}
    return out


def fit(k, j):
    if set(k) != set(j) or len(k) < 2:
        return None
    n = len(k)
    kc = [sum(v[i] for v in k.values()) / n for i in (0, 1)]
    jc = [sum(v[i] for v in j.values()) / n for i in (0, 1)]
    best = 1e9
    for d in (0, 90, 180, 270):
        a, s = math.radians(d), 0.0
        for m in k:
            x, y = j[m][0] - jc[0], j[m][1] - jc[1]
            s += (x * math.cos(a) + y * math.sin(a) - k[m][0] + kc[0]) ** 2 + (-x * math.sin(a) + y * math.cos(a) - k[m][1] + kc[1]) ** 2
        best = min(best, math.sqrt(s / n))
    return best


def centres(p, key):
    g = {}
    for q in p:
        if q[key]:
            g.setdefault(str(q[key]), []).append((q["x"], q["y"]))
    return {n: (sum(a for a, _ in v) / len(v), sum(b for _, b in v) / len(v)) for n, v in g.items()}


def main():
    if len(sys.argv) > 1:
        (HERE / "jlc-pads.json").write_text(json.dumps(distil(pathlib.Path(sys.argv[1])), indent=1, sort_keys=True) + "\n")
    jlc = json.loads((HERE / "jlc-pads.json").read_text())
    kic = json.loads(AUD.read_text())
    rows = []
    for r in csv.reader(BOM.open()):
        code = next((c for c in r if c in CODES), None)
        if not code:
            continue
        ref = r[1].split(",")[0]
        row = {"lcsc": code, "mpn": r[0], "ref": ref, "footprint": kic[ref]["lib"]}
        if code not in jlc:
            row["verdict"] = "NOT CHECKED (no JLC geometry read)"
        else:
            k, j = centres(kic[ref]["pads"], "num"), centres(jlc[code]["pads"], "n")
            j = {REMAP.get(ref, {}).get(n, n): c for n, c in j.items()}
            if ref in KELVIN:
                a, b = KELVIN[ref]
                k, j = {"1": k[a], "2": k[b]}, {"1": j["1"], "2": j["2"]}
            v = fit(k, j)
            row.update(jlc_package=jlc[code]["package"], rms_mm=v if v is None else round(v, 3), kicad_pads=sorted(k), jlc_pads=sorted(j))
            row["verdict"] = "PAD NUMBERS DIFFER" if v is None else ("PASS" if v <= LIMIT else "FAIL")
        rows.append(row)
    (HERE / "results.json").write_text(json.dumps(rows, indent=1) + "\n")
    for x in rows:
        print(x["verdict"], x["ref"], x["mpn"], x.get("rms_mm"), x["footprint"], x.get("jlc_package", ""))


main()
