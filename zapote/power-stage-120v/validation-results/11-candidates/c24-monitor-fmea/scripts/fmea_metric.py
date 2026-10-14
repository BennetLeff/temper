#!/usr/bin/env python3
"""Candidate 24 FMEA: quantify the dormant (latent) "bias fault masked, drivers stay enabled" exposure of the
BIAS_GOOD chain for four variants, and size the heartbeat mitigation.

    python3 -I validation-results/11-candidates/c24-monitor-fmea/scripts/fmea_metric.py

Writes ../results/fmea_metric.json and ../results/fmea_metric.md. Offline, deterministic, stdlib only.
Exit 1 if an invariant breaks (listed at the end of main()).

Variants
  A   today (native-21 stage 22): three monitors, three ISO7710 (U32 LS, U33 HS-A, U34 HS-B), OR3 U25 on SELV,
      10 k / 1 nF RC, U40 SN74LVC1G14 -> BIAS_GOOD -> U22/U23 NAND with PERMIT.
  P1  g05-g07 P1 (reference only): notice stage -> one SN74LVC1G10 inverter per rail, rest as A.
  P2  g05-g07 P2 as proposed: HS 'good' -> ISO6721FB (default LOW) -> LS NAND3 (+LS good) -> U32 ISO7710 -> RC -> U40.
  P2H P2 + heartbeat (this FMEA's mitigation M1): HS ISO6721FB outputs veto the LS wired-AND 'good' node through a
      BAT54A diode pair; that node gates an SN74LVC1G132 Schmitt-NAND RC oscillator; U32 carries the square wave;
      on SELV two series 100 nF + BAT54S charge pump + 1 nF / 100 k hold -> U40 as SN74LVC1G17 -> BIAS_GOOD.

Metric
  For every component failure mode: lambda_mode = FIT x fraction x k, where k is the probability that the mode leaves
  the chain reporting 'good' while a rail is out of window (a masking, dormant fault). n_rails is how many of the three
  rails' faults it hides. Only DORMANT modes count: a mode that disables the drivers by itself is announced (the hob
  stops) and is k = 0 here.
  RWL = sum(lambda_mode x n_rails)  [FIT x rails]. With no diagnostic anywhere in the chain (true for A, P1, P2: BIAS_GOOD
  reaches no J4 pin, power_stage_120v.ato:646-662), the probability that a rail fault meets an already-present masking
  fault over a life T is ~ RWL x lambda_rail x T^2 / 2, so RWL ratios are hazard-rate ratios (lambda_rail cancels).
  U22/U23 (DIS NAND, per leg) are identical in all variants; they are reported but separated so they do not dilute the
  comparison.

Sources (fetched 2026-10-13, text in ../evidence/ds/, see MANIFEST.txt)
  ISO7710 DW-16: 26 FIT (IEC TR 62380), FMD undetermined 40 / out-of-spec 30 / stuck-default 24 / high 3 / low 3 %
                 (TI SLLA504 Tables 2-3, 3-1).
  ISO6721(F) D-8: 10 FIT, FMD 35 / 30 / 25 / 5 / 5 % (TI SFFS130 Tables 2-1, 3-1).
  LVC1G logic: proxy SN74LVC1G125-Q1 SOT-23, 6 FIT, FMD output stuck-at 20 / open (Hi-Z) 20 / out-of-spec 40 /
                 short any two pins 20 % (TI SFFS754 Tables 2-1, 3-1). No FS document exists for G10/G14/G17/G132/G332;
                 the proxy is the same LVC1G process and package class.
ASSUMED (no committed source; engineering judgement, varied in the sensitivity block):
  chip resistor 0.5 FIT (open 80 %, drift 20 %), MLCC 0.5 FIT (short 50 / open 30 / drift 20 %), small-signal diode
  1 FIT (short 50 / open 30 / drift 20 %), SOT-23 NPN 1 FIT (C-E short 40 / open 40 / drift 20 %), TPS70950 LDO 10 FIT
  with 20 % 'output to input' (over-voltage) mode; stuck-at split 50/50 high/low; k_u (undetermined / Hi-Z masks)
  0.5; k_o (out-of-spec masks) 0.
"""
import json, math, os, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "results")

ISO7710 = dict(fit=26.0, und=0.40, oos=0.30, dflt=0.24, hi=0.03, lo=0.03)   # SLLA504
ISO6721 = dict(fit=10.0, und=0.35, oos=0.30, dflt=0.25, hi=0.05, lo=0.05)   # SFFS130
LVC = dict(fit=6.0, stuck=0.20, hiz=0.20, oos=0.40, pins=0.20)              # SFFS754 proxy


def base_params():
    return dict(k_u=0.5, k_o=0.0, R=0.5, C=0.5, D=1.0, Q=1.0, LDO=10.0, ldo_ov=0.2)


def rows_for(variant, p):
    """-> list of (ref, mode, lambda_FIT, k, n_rails, group). group: 'chain' (compared) or 'dis' (identical, U22/U23)."""
    ku, ko = p["k_u"], p["k_o"]
    r = []
    add = lambda ref, mode, lam, k, n, g="chain": r.append((ref, mode, lam, k, n, g))
    lvc = LVC["fit"]
    rails = ("LS", "HA", "HB")

    if variant in ("A", "P1"):
        for rl, iso in zip(rails, ("U32", "U33", "U34")):
            f = ISO7710["fit"]
            add(f"{iso} ISO7710 ({rl})", "OUT stuck low (= good)", f * ISO7710["lo"], 1.0, 1)
            add(f"{iso} ISO7710 ({rl})", "OUT undetermined", f * ISO7710["und"], ku, 1)
            add(f"{iso} ISO7710 ({rl})", "OUT out of V/t spec", f * ISO7710["oos"], ko, 1)
            if variant == "A":
                add(f"Q7-9 MMBT3904 ({rl})", "C-E short: ISO IN held low", p["Q"] * 0.4, 1.0, 1)
                add(f"D14-16 1N4148W ({rl})", "short: NPN base at LM339B VOL <= 0.4 V", p["D"] * 0.5, 0.5, 1)
            else:  # P1 per-rail inverter
                add(f"G10 inverter ({rl})", "output stuck low (= good)", lvc * LVC["stuck"] / 2, 1.0, 1)
                add(f"G10 inverter ({rl})", "out of spec", lvc * LVC["oos"], ko, 1)
            add(f"U37-39 TPS70950 ({rl})", "output to input (15-17 V on ISO side 1): damage, state unknown",
                p["LDO"] * p["ldo_ov"], ku, 1)
        # SELV common path
        add("U25 SN74LVC1G332 OR3", "Y stuck low (= no fault)", lvc * LVC["stuck"] / 2, 1.0, 3)
        add("U25 SN74LVC1G332 OR3", "Y open (RC node floats)", lvc * LVC["hiz"], ku, 3)
        add("U25 SN74LVC1G332 OR3", "out of spec", lvc * LVC["oos"], ko, 3)
        # SOT-23-6 A1 GND2 B3 Y4 VCC5 C6: adjacent pairs 1-2, 2-3 tie an input low (= that rail good) ; 4-5, 5-6 safe
        add("U25 SN74LVC1G332 OR3", "adjacent-pin short A-GND or B-GND (2 of 4 pairs)", lvc * LVC["pins"] * 2 / 4, 1.0, 1)
        add("R_bias_flt 10k", "open: U40 input floats on 1 nF", p["R"] * 0.8, ku, 3)
        add("C_bias_flt 1nF", "short: BIAS_BAD_FLT held low", p["C"] * 0.5, 1.0, 3)
        u40_inverting = True
    elif variant in ("P2", "P2H"):
        for rl in ("HA", "HB"):
            f = ISO6721["fit"]
            add(f"ISO6721FB ({rl})", "OUTB stuck high (= good)", f * ISO6721["hi"], 1.0, 1)
            add(f"ISO6721FB ({rl})", "OUTB undetermined", f * ISO6721["und"], ku, 1)
            add(f"ISO6721FB ({rl})", "out of V/t spec", f * ISO6721["oos"], ko, 1)
            add(f"U38/U39 TPS70950 ({rl})", "output to input: ISO6721 side 1 damaged, state unknown",
                p["LDO"] * p["ldo_ov"], ku, 1)
        if variant == "P2":
            # LS 5 V (U37) now feeds NAND3, both ISO6721 side 2 and U32 side 1
            add("U37 TPS70950 (LS 5 V)", "output to input: NAND3 / ISO6721 side 2 / U32 side 1 damaged, state unknown",
                p["LDO"] * p["ldo_ov"], ku, 3)
            add("NAND3 SN74LVC1G10", "Y stuck low (= all good)", lvc * LVC["stuck"] / 2, 1.0, 3)
            add("NAND3 SN74LVC1G10", "Y open: U32 IN open -> ISO7710 default HIGH (bad)", lvc * LVC["hiz"], 0.0, 3)
            add("NAND3 SN74LVC1G10", "out of spec", lvc * LVC["oos"], ko, 3)
            # A1 GND2 B3 Y4 VCC5 C6: 1-2, 2-3 tie an input low -> NAND high = bad (safe); 4-5 Y high = bad; 5-6 C high masks 1
            add("NAND3 SN74LVC1G10", "adjacent-pin short C-VCC (1 of 4 pairs)", lvc * LVC["pins"] / 4, 1.0, 1)
            f = ISO7710["fit"]
            add("U32 ISO7710 (combined)", "OUT stuck low (= good)", f * ISO7710["lo"], 1.0, 3)
            add("U32 ISO7710 (combined)", "OUT undetermined", f * ISO7710["und"], ku, 3)
            add("U32 ISO7710 (combined)", "OUT out of V/t spec", f * ISO7710["oos"], ko, 3)
            add("R_bias_flt 10k", "open: U40 input floats on 1 nF", p["R"] * 0.8, ku, 3)
            add("C_bias_flt 1nF", "short: BIAS_BAD_FLT held low", p["C"] * 0.5, 1.0, 3)
            u40_inverting = True
        else:  # P2H heartbeat
            add("D_and BAT54A (per HS rail)", "open: that HS rail's veto lost", 2 * p["D"] * 0.3, 1.0, 1)
            add("D_and BAT54A (per HS rail)", "short: ISO6721 OUTB fights LM339B on the LS node", 2 * p["D"] * 0.5, 0.5, 1)
            # The oscillator, U32, the pump and U37 have no dormant masking mode: any stuck, open, Hi-Z or supply fault
            # stops the square wave and the hold collapses (announced). Only out-of-spec of the gate that decides
            # 'oscillate or not' is kept, at k_o, for symmetry with the static gates.
            add("U_osc SN74LVC1G132", "out of spec (input threshold corrupted)", lvc * LVC["oos"], ko, 3)
            add("C_pump 2 x 100 nF series", "one short: DC block degraded to one cap (dormant, needs a 2nd fault)", 0.0, 0.0, 3)
            add("R_bleed 100k", "open: hold keeps its charge when the wave stops", p["R"] * 0.8, ku, 3)
            u40_inverting = False
    else:
        raise ValueError(variant)

    # U40 Schmitt -> BIAS_GOOD (SOT-23-5: 1 NC, 2 A, 3 GND, 4 Y, 5 VCC)
    name = "U40 SN74LVC1G14 (inverting)" if u40_inverting else "U40 SN74LVC1G17 (non-inverting)"
    add(name, "Y stuck high (BIAS_GOOD = 1)", lvc * LVC["stuck"] / 2, 1.0, 3)
    add(name, "Y open (U22/U23 inputs float)", lvc * LVC["hiz"], ku, 3)
    add(name, "out of spec", lvc * LVC["oos"], ko, 3)
    # pairs 1-2 (NC) harmless; 4-5 Y-VCC masks; 2-3 A-GND masks only when inverting
    add(name, "adjacent-pin short (Y-VCC%s)" % (", A-GND" if u40_inverting else ""),
        lvc * LVC["pins"] * (2 if u40_inverting else 1) / 3, 1.0, 3)
    # DIS NAND per leg (identical in every variant): Y stuck low enables that leg regardless of BIAS_GOOD and PERMIT.
    for leg, rr in (("U22 (leg A)", 2), ("U23 (leg B)", 2)):
        add(leg + " SN74LVC1G00", "Y stuck low (DIS low = enabled)", lvc * LVC["stuck"] / 2, 1.0, rr, "dis")
    return r


def score(rows):
    chain = sum(lam * k * n for _, _, lam, k, n, g in rows if g == "chain")
    three = sum(lam * k for _, _, lam, k, n, g in rows if g == "chain" and n == 3)
    dis = sum(lam * k * n for _, _, lam, k, n, g in rows if g == "dis")
    return dict(RWL_chain=round(chain, 3), FIT_masking_all_three=round(three, 3), RWL_dis_identical=round(dis, 3))


def heartbeat_sizing():
    """Charge-pump / hold sizing for M1 with datasheet thresholds. Values to be confirmed in SPICE and on the bench."""
    v3_min = 3.135                      # J4.3 contract minimum (FAULT-INTERFACE.md)
    voh_drop = 0.3                      # ISO7710 VOH >= VCC2 - 0.3 V (FAULT-INTERFACE.md, SLLSER9E)
    vf = 0.35                           # BAT54 class Schottky at ~0.1-1 mA (assumed; not a cited figure)
    vpk = v3_min - voh_drop - 2 * vf    # pump peak into the hold node
    c_pump = 100e-9 / 2                 # two 100 nF 0603 in series (existing C100n0603 line); one short still blocks DC
    c_hold = 1e-9                       # 1 nF C0G (existing line)
    r_bleed = 100e3                     # existing R100k0603 line
    r_osc, c_osc = 4.99e3, 330e-12      # existing Bias4k99 and C330pC0G0603 lines
    # SN74LVC1G132 at 4.5 V (SCES546E 5.5): VT+ 2.16-2.74, VT- 1.41-1.84 V. Period of a Schmitt RC oscillator:
    vcc = 4.75
    def period(vtp, vtm):
        return r_osc * c_osc * (math.log((vcc - vtm) / (vcc - vtp)) + math.log(vtp / vtm))
    t_lo, t_hi = sorted((period(2.16, 1.84), period(2.74, 1.41)))
    f_min = 1 / t_hi
    i_bleed = vpk / r_bleed
    v_hold = vpk - i_bleed / (f_min * c_pump)          # peak after refill: charge in per cycle = bleed charge per cycle
    ripple = i_bleed / (f_min * c_hold)                 # droop between refills
    g17_vtp_max, g17_vtm_min, g17_vtm_max = 1.92, 0.89, 1.20   # SN74LVC1G17 at 3 V, SCES351Y Table 5-1
    tau = r_bleed * c_hold
    t_detect = tau * math.log(v_hold / g17_vtm_min) + t_hi      # slowest: lowest VT-, one oscillator period
    diode_and_low = 0.4 + vf             # ISO6721 VOL <= 0.4 V at 4 mA (SLLSFJ0F) + Schottky
    g132_vtm_min = 1.41
    return dict(
        pump_peak_V=round(vpk, 3), osc_period_us=[round(t_lo * 1e6, 2), round(t_hi * 1e6, 2)],
        hold_equilibrium_V=round(v_hold, 3), hold_ripple_V=round(ripple, 3),
        start_margin_over_G17_VTplus_max_V=round(v_hold - ripple - g17_vtp_max, 3),
        run_margin_over_G17_VTminus_max_V=round(v_hold - ripple - g17_vtm_max, 3),
        detect_latency_us_max=round(t_detect * 1e6, 1),
        today_rc_latency_us="~5.95-10 (10 k / 1 nF into G14; PROPOSALS.md P3)",
        diode_and_low_V=round(diode_and_low, 2), g132_VTminus_min_V=g132_vtm_min,
        diode_and_margin_V=round(g132_vtm_min - diode_and_low, 2),
        notes="vf 0.35 V assumed; LS 5 V taken as 4.75 V; all margins to be confirmed in SPICE with the real ISO7710 "
              "output impedance and on the bench (B4 timing endpoint: comparator -> driver output, ECO.md).")


def placements():
    """Placement / line deltas against the stage-22 board, from PROPOSALS.md P2 and this FMEA's M1."""
    p2 = dict(placements=-12, lines=-1, usd_dk=-1.9, usd_jlc=-4.1,
              basis="PROPOSALS.md:116 (notice stage 12 out; U25/C88 out, NAND3 + cap in; U33/U34 -> ISO6721FB)")
    m1 = dict(
        removed=["NAND3 SN74LVC1G10 (P2's)", "its 100 nF", "R_bias_flt 10k", "C_bias_flt 1 nF"],
        added=["BAT54A dual diode (HS veto into the LS 'good' node)", "SN74LVC1G132", "its 100 nF",
               "R_osc 4.99k", "C_osc 330 pF C0G", "C_pump 100 nF x2 (series)", "BAT54S dual diode (pump)",
               "C_hold 1 nF C0G", "R_bleed 100k"],
        swapped=["U40 SN74LVC1G14 -> SN74LVC1G17 (in place, same SOT-23-5 footprint; G17 line exists: U15, U24)"],
        lines_added=["BAT54A", "BAT54S", "SN74LVC1G132"], lines_removed=["SN74LVC1G14 (U40 was its only user)"],
        usd_est=+0.15, usd_note="estimate: G132 ~$0.10, BAT54A/S ~$0.02 each, passives ~$0.005; NAND3 (~$0.1) out. "
                               "Prices NOT looked up for this FMEA; JLC class (Basic/Extended) to check.")
    m1["placements"] = len(m1["added"]) + 1 - len(m1["removed"])   # C_pump is two parts
    m1["lines"] = len(m1["lines_added"]) - len(m1["lines_removed"])
    net = dict(placements=p2["placements"] + m1["placements"], lines=p2["lines"] + m1["lines"],
               usd_dk=round(p2["usd_dk"] + m1["usd_est"], 2), usd_jlc=round(p2["usd_jlc"] + m1["usd_est"], 2))
    return dict(P2=p2, M1=m1, P2_plus_M1=net)


def main():
    variants = ("A", "P1", "P2", "P2H")
    base = base_params()
    res = {v: score(rows_for(v, base)) for v in variants}
    sens_cases = {
        "base": {},
        "undetermined always masks (k_u=1)": dict(k_u=1.0),
        "undetermined never masks (k_u=0)": dict(k_u=0.0),
        "out-of-spec masks half (k_o=0.5)": dict(k_o=0.5),
        "passives x5": dict(R=2.5, C=2.5, D=5.0, Q=5.0),
        "LDO OV x3 (30 FIT x 20 %)": dict(LDO=30.0),
        "worst (k_u=1, k_o=0.5, passives x5)": dict(k_u=1.0, k_o=0.5, R=2.5, C=2.5, D=5.0, Q=5.0),
    }
    sens = {}
    for name, ch in sens_cases.items():
        p = dict(base, **ch)
        sens[name] = {v: score(rows_for(v, p))["RWL_chain"] for v in variants}
    hb = heartbeat_sizing()
    pl = placements()
    out = dict(base_params=base, scores=res, sensitivity_RWL_chain=sens, heartbeat=hb, placements=pl,
               rows={v: [dict(ref=a, mode=b, fit=round(c, 3), k=d, n_rails=e, group=g)
                         for a, b, c, d, e, g in rows_for(v, base)] for v in variants})
    os.makedirs(OUT, exist_ok=True)
    json.dump(out, open(os.path.join(OUT, "fmea_metric.json"), "w"), indent=1)

    L = ["# Candidate 24: dormant-masking exposure (generated by scripts/fmea_metric.py)", "",
         "RWL = sum over failure modes of FIT x P(mode masks) x rails hidden. Lower is better. U22/U23 (identical in all",
         "variants) are reported separately.", "",
         "| variant | RWL chain [FIT x rails] | FIT of modes hiding all three rails | RWL U22/U23 (same in all) |",
         "|---|---:|---:|---:|"]
    names = dict(A="A: today (stage 22)", P1="P1 (reference)", P2="P2 as proposed", P2H="P2 + M1 heartbeat")
    for v in variants:
        s = res[v]
        L.append(f"| {names[v]} | {s['RWL_chain']} | {s['FIT_masking_all_three']} | {s['RWL_dis_identical']} |")
    L += ["", "## Sensitivity (RWL chain)", "", "| case | " + " | ".join(names[v] for v in variants) + " |",
          "|---|" + "---:|" * len(variants)]
    for name, d in sens.items():
        L.append(f"| {name} | " + " | ".join(str(d[v]) for v in variants) + " |")
    for v in variants:
        L += ["", f"## Rows: {names[v]}", "", "| ref | mode | FIT of mode | P(masks) | rails hidden | contribution |",
              "|---|---|---:|---:|:-:|---:|"]
        for a, b, c, d, e, g in rows_for(v, base):
            L.append(f"| {a} | {b} | {c:.3f} | {d} | {e} | {c * d * e:.3f}{' (U22/U23)' if g == 'dis' else ''} |")
    L += ["", "## Heartbeat (M1) sizing", "", "```", json.dumps(hb, indent=1), "```",
          "", "## Placements and lines", "", "```", json.dumps(pl, indent=1), "```"]
    open(os.path.join(OUT, "fmea_metric.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L[:14 + len(sens) + 3]))
    print("heartbeat:", json.dumps(hb))
    print("placements:", json.dumps(pl["P2_plus_M1"]), "M1:", pl["M1"]["placements"], "placements,", pl["M1"]["lines"], "lines")

    # invariants
    bad = []
    if not res["P2"]["FIT_masking_all_three"] > res["A"]["FIT_masking_all_three"]:
        bad.append("expected P2 to add all-three masking exposure (U32 becomes common)")
    for name, d in sens.items():
        if not d["P2H"] < d["A"]:
            bad.append(f"P2H not better than today in case {name}")
    if hb["start_margin_over_G17_VTplus_max_V"] <= 0 or hb["diode_and_margin_V"] <= 0:
        bad.append("heartbeat sizing has no threshold margin")
    if pl["M1"]["placements"] != 6:
        bad.append("M1 placement count drifted")
    print("invariants:", bad if bad else "all hold")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
