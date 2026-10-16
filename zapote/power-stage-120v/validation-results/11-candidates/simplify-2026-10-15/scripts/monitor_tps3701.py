#!/usr/bin/env python3
"""Candidate B: rail-monitor core (TL431A + LM339B + rref + halfref divider) -> two TPS3701 window detectors per rail,
one per window, each threshold on its OWN two-resistor divider (no shared ladder; see README 'ladders').

    python3 -I scripts/monitor_tps3701.py [SNAP_PS_DIR]          -> results/monitor_tps3701.json

Control: the benchmark bands are computed by the committed g05-g07 P4 script's old_band() (imported read-only from the
snapshot); they must reproduce its committed results/tps3700_band.json 'old' block.
New bands: TPS3701 SBVS240C Table 6.5: INA falling VIT-(INA) 397..403 mV (UV), INB rising VIT+(INB) 397..403 mV (OV),
input current +-25 nA; resistors 0.1 % + 25 ppm/K over 125 K (the P4 script's TOL/TCR), all vertices.
A design passes when every new band lies inside the benchmark band (dominance: any rail qualification that passes against
the benchmark thresholds passes against these).
Resistor values are restricted to Yageo RT0603BRD07 parts found in JLC stock >= 1,500 (3 per board x 500) in the cached
search records (dl/jlc-raw); the script queries JLC for a value only when its record is not cached (pass --offline to forbid).
"""
import sys as _s; _s.dont_write_bytecode = True  # never write .pyc next to the read-only snapshot sources
import importlib.util, itertools, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jlc  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
ONLINE = "--offline" not in sys.argv
PS = Path(args[0]) if args else Path(__file__).resolve().parents[4]
G = PS / "validation-results/11-candidates/g05-g07-drive-monitor"
spec = importlib.util.spec_from_file_location("p4", G / "scripts/tps3700_band.py")
p4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p4)

TOL, TCR = p4.TOL, p4.TCR
OLD_TOPS = {"neg UV": 4.42, "neg OV": 7.68, "span UV": 120.0, "span OV": 133.0}
VIT_UV = (0.397, 0.403)     # TPS3701 VIT-(INA), falling (trip)
VIT_OV = (0.397, 0.403)     # TPS3701 VIT+(INB), rising (trip)
REL_UV = (0.400, 0.413)     # TPS3701 VIT+(INA): UV release / start-up threshold (hysteresis 2..12 mV)
REL_OV = (0.387, 0.400)     # TPS3701 VIT-(INB): OV release
IIN = 25e-9
# Rail tolerance the windows must clear (repo values, not re-derived here):
#   span: LS TPS7A4700 17.0 V +-2.5 % (ALT-BIAS.md R6) and HS RECOM 16.91 V +-1.5 % (ALT-BIAS.md RECOM row) -> union
#   neg (SRC-N): TLVH431 split with the fitted 6.2 k, 1.9684..2.0589 V (bom-simplification out/neg_rail.json)
RAIL = {"span": (17.0 * 0.975, 17.0 * 1.025), "neg": (1.9684, 2.0589)}


def band(top_k, bot_k, vit):
    lo, hi = 1e9, -1e9
    e = TOL + TCR
    for st, sb in itertools.product((-1, 1), repeat=2):
        t, b = top_k * 1e3 * (1 + st * e), bot_k * 1e3 * (1 + sb * e)
        for v in vit:
            for i in (-IIN, IIN):
                x = (v + i * t * b / (t + b)) * (t + b) / b
                lo, hi = min(lo, x), max(hi, x)
    return lo, hi


def yageo_code(k):
    """value in kohm -> Yageo RT0603BRD07 value code"""
    if k >= 1000:
        s = f"{k / 1000:g}"
        return (s.replace(".", "M") if "." in s else s + "M") + "L"
    s = f"{k:g}"
    return (s.replace(".", "K") if "." in s else s + "K") + "L"


# 0.1 % parts already on the s43 BOM (value kohm -> MPN, per-board qty today); stock from SNAPSHOT-2026-10-15.csv
BOM_01 = {10.0: ("RT0603BRD0710KL", 28), 11.0: ("RT0603BRD0711KL", 2), 2.21: ("RT0603BRD072K21L", 2),
          1.0: ("RT0603BRD071KL", 2), 12.6: ("RT0603BRD0712K6L", 1), 11.7: ("TNPW060311K7BEEA", 1),
          15.8: ("RT0603BRD0715K8L", 1), 7.68: ("RT0603BRD077K68L", 3)}


def _snapshot():
    import csv
    p = PS / "validation-results/08-manufacturing-package/native-21/sourcing/SNAPSHOT-2026-10-15.csv"
    return {r["mpn"]: r for r in list(csv.DictReader(open(p)))[:93]}


SNAP = _snapshot()


def stocked(k, need=1500):
    if k in BOM_01:
        mpn, q = BOM_01[k]
        r = SNAP.get(mpn) or {}
        stock = int(float(r.get("jlc_stock") or 0))
        ok = stock >= need + q * 500
        return {"mpn": mpn, "lcsc": r.get("lcsc_code"), "class": r.get("jlc_library"), "jlc_stock": stock,
                "on_s43_bom": True} if ok else None
    mpn = "RT0603BRD07" + yageo_code(k)
    rows = [r for r in jlc.search(mpn, online=ONLINE) if r[3] == mpn]
    if not rows:
        return None
    code, lib, stock = rows[0][0], rows[0][1], rows[0][2] or 0
    return {"mpn": mpn, "lcsc": code, "class": lib, "jlc_stock": stock} if stock >= need else None


E192 = [1.00,1.01,1.02,1.04,1.05,1.06,1.07,1.09,1.10,1.11,1.13,1.14,1.15,1.17,1.18,1.20,1.21,1.23,1.24,1.26,1.27,1.29,1.30,
        1.32,1.33,1.35,1.37,1.38,1.40,1.42,1.43,1.45,1.47,1.49,1.50,1.52,1.54,1.56,1.58,1.60,1.62,1.64,1.65,1.67,1.69,1.72,1.74,
        1.76,1.78,1.80,1.82,1.84,1.87,1.89,1.91,1.93,1.96,1.98,2.00,2.03,2.05,2.08,2.10,2.13,2.15,2.18,2.21,2.23,2.26,2.29,2.32,
        2.34,2.37,2.40,2.43,2.46,2.49,2.52,2.55,2.58,2.61,2.64,2.67,2.71,2.74,2.77,2.80,2.84,2.87,2.91,2.94,2.98,3.01,3.05,3.09,
        3.12,3.16,3.20,3.24,3.28,3.32,3.36,3.40,3.44,3.48,3.52,3.57,3.61,3.65,3.70,3.74,3.79,3.83,3.88,3.92,3.97,4.02,4.07,4.12,
        4.17,4.22,4.27,4.32,4.37,4.42,4.48,4.53,4.59,4.64,4.70,4.75,4.81,4.87,4.93,4.99,5.05,5.11,5.17,5.23,5.30,5.36,5.42,5.49,
        5.56,5.62,5.69,5.76,5.83,5.90,5.97,6.04,6.12,6.19,6.26,6.34,6.42,6.49,6.57,6.65,6.73,6.81,6.90,6.98,7.06,7.15,7.23,7.32,
        7.41,7.50,7.59,7.68,7.77,7.87,7.96,8.06,8.16,8.25,8.35,8.45,8.56,8.66,8.76,8.87,8.98,9.09,9.20,9.31,9.42,9.53,9.65,9.76,
        9.88]


def e96_decades(lo, hi):
    """E192 values (a superset of E96) in [lo, hi] kohm"""
    return [round(m * d, 4) for d in (1, 10, 100, 1000) for m in E192 if lo <= m * d <= hi]


def main():
    committed = json.load(open(G / "results/tps3700_band.json"))["old"]
    old = {k: p4.old_band(v) for k, v in OLD_TOPS.items()}
    for k in old:                                            # control
        assert all(abs(a - b) < 1e-9 for a, b in zip(old[k], committed[k])), k
    nominal = {k: p4.nominal_old(v) for k, v in OLD_TOPS.items()}
    bottoms = [10.0, 11.0, 2.21, 1.0, 12.6, 11.7, 15.8]      # values already on the s43 BOM first
    out = {"control": "old bands reproduce g05-g07 results/tps3700_band.json", "old_bands": old, "old_nominal": nominal,
           "design": {}}
    for name in ("neg UV", "neg OV", "span UV", "span OV"):
        vit = VIT_UV if "UV" in name else VIT_OV
        cands = []
        for b in bottoms:
            ideal = (nominal[name] / 0.400 - 1) * b
            for t in e96_decades(ideal * 0.92, ideal * 1.08):
                lo, hi = band(t, b, vit)
                rlo, rhi = band(t, b, REL_UV if "UV" in name else REL_OV)
                inside = lo >= old[name][0] and hi <= old[name][1]
                nom = 0.400 * (t + b) / b
                rail = RAIL["span" if "span" in name else "neg"]
                margin = (rail[0] - rhi) if "UV" in name else (rlo - rail[1])   # release side binds (hysteresis)
                cands.append((not inside, -round(margin, 3), b, t, lo, hi, nom))
        cands.sort()
        chosen = None
        for c in cands:
            if c[0]:
                break
            st_t, st_b = stocked(c[3]), stocked(c[2])
            if st_t and st_b:
                chosen = c + (st_t, st_b)
                break
        if not chosen:
            out["design"][name] = {"result": "no stocked in-band pair"}
            continue
        _, negm, b, t, lo, hi, nom, st_t, st_b = chosen
        rlo, rhi = band(t, b, REL_UV if "UV" in name else REL_OV)
        rail = RAIL["span" if "span" in name else "neg"]
        o_lo, o_hi = old[name]
        old_margin = (rail[0] - o_hi) if "UV" in name else (o_lo - rail[1])   # LM339B: no hysteresis, release = trip
        out["design"][name] = {"top_k": t, "bottom_k": b, "nominal_V": round(nom, 4), "old_nominal_V": round(nominal[name], 4),
                               "band_V": [round(lo, 4), round(hi, 4)], "old_band_V": [round(x, 4) for x in old[name]],
                               "inside_old_band": True, "band_width_vs_old": round((hi - lo) / (old[name][1] - old[name][0]), 3),
                               "top_part": st_t, "bottom_part": st_b,
                               "divider_current_uA_at_nominal": round(nom / ((t + b) * 1e3) * 1e6, 1),
                               "release_band_V": [round(rlo, 4), round(rhi, 4)], "rail_V": rail,
                               "rail_margin_V_new_release_side": round(-negm, 4), "rail_margin_V_old": round(old_margin, 4)}
        print(f"{name:8s} top {t:7.2f}k / bottom {b:5.2f}k  nominal {nom:7.4f} V (old {nominal[name]:7.4f})  "
              f"band {lo:7.4f}..{hi:7.4f}  old {old[name][0]:7.4f}..{old[name][1]:7.4f}  width x{(hi-lo)/(old[name][1]-old[name][0]):.2f}"
              f"  {st_t['mpn']} ({st_t['jlc_stock']}) / {st_b['mpn']}\n         release {rlo:7.4f}..{rhi:7.4f}  rail {rail[0]:.4f}..{rail[1]:.4f}"
              f"  margin to rail: new {-negm:+.3f} V (release side), old {old_margin:+.3f} V")
    # supply current removed from each 17 V rail: TL431 branch (rref 2.2 k) + halfref divider (20 k)
    i_ref = (17.0 - 2.495) / 2.2e3 + 2.495 / 20e3
    out["ref_branch_removed_mA_per_rail"] = round(i_ref * 1e3, 2)
    out["tps3701_idd_max_uA_per_rail"] = 2 * 11
    print(f"reference branch removed: {i_ref*1e3:.2f} mA per rail at 17.0 V ({i_ref*17:.3f} W); TPS3701 IDD 2 x 11 uA max")
    Path(HERE.parent / "results").mkdir(exist_ok=True)
    json.dump(out, open(HERE.parent / "results/monitor_tps3701.json", "w"), indent=1)


if __name__ == "__main__":
    main()
