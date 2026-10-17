#!/usr/bin/env python3
"""Option P4 (rejected on cost): rail-monitor core TL431 + LM339B + 11 resistors -> 2 x TPS3700 + 6 resistors per rail.

    python3 -I validation-results/11-candidates/g05-g07-drive-monitor/scripts/tps3700_band.py
(1) worst-case trip bands of the four window thresholds, benchmark vs TPS3700 ladders (E96 values found by search);
    dominance test: the new band lies inside the old band for every threshold, so any rail qualification that passes
    against the benchmark thresholds passes against these;
(2) parts cost per board from JLC tiers in ../evidence/jlc-raw;
(3) monitor supply current removed from the 17 V bias rails (bias_sizing.py allocates 14 mA per rail to the monitor).
Datasheets: TL431 SLVS543S (AI grade: Vref 2470..2520 mV at 25 C, VI(dev) <= 34 mV (DBZ) over temperature),
LM339B SLCS006Z (Vos <= 5.5 mV, -40..85 C), TPS3700 2019 rev (VIT+ 396..404 mV, VIT- 387..400 mV, input current +-25 nA,
VDD 1.8..18 V recommended, 20 V absolute maximum, UVLO falling 1.3..1.7 V: OUTA low, OUTB Hi-Z).
"""
import itertools, json, glob, os, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = f"{HERE}/../evidence/jlc-raw"
TOL, TCR = 0.001, 25e-6 * 125            # 0.1 %, 25 ppm/K over 125 K (RT0603BRD07 / ARG03 class)
VREF = (2.470 - 0.034, 2.520 + 0.034)    # TL431AI DBZ
VOS = 0.0055

def corners(vals):
    """all +-(TOL+TCR) corners of a resistor tuple"""
    e = TOL + TCR
    for sgn in itertools.product((-1, 1), repeat=len(vals)):
        yield tuple(v * (1 + s * e) for v, s in zip(vals, sgn))

def old_band(rt_k, rb_k=10.0):
    """trip voltage band for one benchmark divider (halfref from 10k/10k of the TL431 ref)"""
    lo, hi = 1e9, -1e9
    for vref in VREF:
        for (rht, rhb, rt, rb) in corners((10.0, 10.0, rt_k, rb_k)):
            halfref = vref * rhb / (rht + rhb)
            for vos in (-VOS, VOS):
                v = (halfref + vos) * (rt + rb) / rb
                lo, hi = min(lo, v), max(hi, v)
    return lo, hi

def nominal_old(rt_k):
    return 2.495 * 0.5 * (rt_k + 10.0) / 10.0

E96 = [1.00,1.02,1.05,1.07,1.10,1.13,1.15,1.18,1.21,1.24,1.27,1.30,1.33,1.37,1.40,1.43,1.47,1.50,1.54,1.58,1.62,1.65,1.69,1.74,
       1.78,1.82,1.87,1.91,1.96,2.00,2.05,2.10,2.15,2.21,2.26,2.32,2.37,2.43,2.49,2.55,2.61,2.67,2.74,2.80,2.87,2.94,3.01,3.09,
       3.16,3.24,3.32,3.40,3.48,3.57,3.65,3.74,3.83,3.92,4.02,4.12,4.22,4.32,4.42,4.53,4.64,4.75,4.87,4.99,5.11,5.23,5.36,5.49,
       5.62,5.76,5.90,6.04,6.19,6.34,6.49,6.65,6.81,6.98,7.15,7.32,7.50,7.68,7.87,8.06,8.25,8.45,8.66,8.87,9.09,9.31,9.53,9.76]
def e96(lo_k, hi_k):
    out = []
    for dec in (0.1, 1, 10, 100, 1000):
        for m in E96:
            v = m * dec
            if lo_k <= v <= hi_k: out.append(round(v, 4))
    return out

VITN = (0.387, 0.400); VITP = (0.396, 0.404); IB = 25e-9
def new_band(r1, r2, r3):
    """(uv_lo, uv_hi, ov_lo, ov_hi): UV trips when INA+ (tap R2/R1... above R3+R2) falls to VIT-; OV when INB- (tap above R3) rises to VIT+"""
    uv = [1e9, -1e9]; ov = [1e9, -1e9]
    for (a, b, c) in corners((r1, r2, r3)):
        rt = a + b + c
        for vit in VITN:
            for ib in (-IB, IB):
                v = (vit + ib * (a * 1e3 * (b + c) * 1e3 / (rt * 1e3))) * rt / (b + c)
                uv = [min(uv[0], v), max(uv[1], v)]
        for vit in VITP:
            for ib in (-IB, IB):
                v = (vit + ib * ((a + b) * 1e3 * c * 1e3 / (rt * 1e3))) * rt / c
                ov = [min(ov[0], v), max(ov[1], v)]
    return uv[0], uv[1], ov[0], ov[1]

def design(vuv, vov, rt_range):
    """E96 triple whose nominal trips (VIT- 393.5 mV, VIT+ 400 mV) are closest to vuv / vov"""
    best = None
    for rt_tot in rt_range:
        r3_t = rt_tot * 0.400 / vov
        r23_t = rt_tot * 0.3935 / vuv
        for r3 in e96(r3_t * 0.9, r3_t * 1.1):
            for r23 in [r3 + x for x in e96(max(0.1, (r23_t - r3) * 0.8), (r23_t - r3) * 1.2 + 0.2)]:
                r2 = r23 - r3
                if r2 <= 0: continue
                for r1 in e96((rt_tot - r23) * 0.9, (rt_tot - r23) * 1.1):
                    rt = r1 + r23
                    e = max(abs(0.3935 * rt / r23 / vuv - 1), abs(0.400 * rt / r3 / vov - 1))
                    if best is None or e < best[0]:
                        best = (e, r1, round(r2, 3) if False else r2, r3)
    return best

if __name__ == "__main__":
    print("benchmark thresholds (nominal Vref 2.495 V) and worst-case bands, all four windows:")
    OLD = {}
    for name, rt in (("neg UV", 4.42), ("neg OV", 7.68), ("span UV", 120.0), ("span OV", 133.0)):
        OLD[name] = old_band(rt)
        print(f"  {name:8s} nominal {nominal_old(rt):7.4f} V   band {OLD[name][0]:7.4f} .. {OLD[name][1]:7.4f} V")
    res = {}
    for label, nuv, nov, rts in (("negative rail window (SRC-N)", nominal_old(4.42), nominal_old(7.68), [40, 50, 60, 80, 100]),
                                 ("span window (P-N)", nominal_old(120.0), nominal_old(133.0), [400, 500, 700, 1000])):
        d = design(nuv, nov, rts)
        e, r1, r2, r3 = d
        b = new_band(r1, r2, r3)
        keyuv, keyov = ("neg UV", "neg OV") if "negative" in label else ("span UV", "span OV")
        ok_uv = b[0] >= OLD[keyuv][0] and b[1] <= OLD[keyuv][1]
        ok_ov = b[2] >= OLD[keyov][0] and b[3] <= OLD[keyov][1]
        print(f"{label}: R1={r1}k R2={r2:.3f}k R3={r3}k  (nominal error {e*100:.2f} %)")
        print(f"   UV band {b[0]:.4f}..{b[1]:.4f} V inside benchmark {OLD[keyuv][0]:.4f}..{OLD[keyuv][1]:.4f}: {ok_uv}")
        print(f"   OV band {b[2]:.4f}..{b[3]:.4f} V inside benchmark {OLD[keyov][0]:.4f}..{OLD[keyov][1]:.4f}: {ok_ov}")
        res[label] = dict(R1_k=r1, R2_k=r2, R3_k=r3, uv_band=b[:2], ov_band=b[2:], dominated=bool(ok_uv and ok_ov))
    # cost
    def price(model, qpb):
        for f in glob.glob(f"{RAW}/detail_*.json"):
            d = json.load(open(f))["data"]
            if d["componentModelEn"].split("(")[0] == model:
                best = None
                for t in d["prices"]:
                    if qpb * 500 >= t["startNumber"]: best = t["productPrice"]
                return best
    tps, lm, tl = price("TPS3700DDCR", 6), price("LM339BIDR", 3), price("TL431AIDBZR", 3)
    print(f"\ncost per board at 500 boards: 6 x TPS3700DDCR @ {tps} = ${6*tps:.2f};  3 x LM339BIDR @ {lm} + 3 x TL431AIDBZR @ {tl} = ${3*lm+3*tl:.2f}")
    print(f"  delta parts = +${6*tps-3*lm-3*tl:.2f} per board.")
    n_old, n_new = 18, 14   # per rail, after P1 (notice stage already deleted): TL431+LM339B+11 R+4 C0G+1 C  ->  2 TPS3700+6 R+4 C0G+2 C
    print(f"  placements per rail {n_old} -> {n_new} (-{n_old-n_new}; -{3*(n_old-n_new)} per board on top of P1, -{3*(n_old+4-n_new)} vs the benchmark); Extended lines LM339BIDR and TL431AIDBZR gone, TPS3700DDCR line already on the board (U14)")
    # supply current
    vp, vref, rref = 17.0, 2.495, 2.2
    i_ref = (vp - vref) / rref
    print(f"\nmonitor current on the 17 V rail: reference branch (17-2.495)/2.2k = {i_ref:.2f} mA per rail; TPS3700 option: 2 x 13 uA max + ladders ({17/499.0:.3f} mA) -> about {i_ref-0.1:.1f} mA saved per rail ({3*(i_ref-0.1)*17:.0f} mW of 17 V bias power per board)")
    json.dump(dict(old=OLD, new=res, parts_delta_usd=round(6*tps-3*lm-3*tl, 2), ref_branch_mA=round(i_ref, 2)),
              open(f"{HERE}/../results/tps3700_band.json", "w"), indent=1, default=str)
