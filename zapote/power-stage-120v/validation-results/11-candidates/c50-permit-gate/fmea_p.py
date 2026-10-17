#!/usr/bin/env python3
"""Option P vs option S: BIAS_GOOD-chain FMEA delta, interface levels and timing (read-only, stdlib only).

    python3 -I fmea_p.py [PS_ROOT]   -> results/fmea_p.json, results/fmea_p.md

Basis:
- chain rows: the committed c24 fmea_metric.py P2H rows (the same rows fmea-s47 sec. 4 H2 scores: chain 13.0 FIT x rails,
  13.8 % 'always' / 36.9 % 'with sequencing'), imported unchanged;
- pump timing: results/pump_p_spice.json (run pump_p_spice.py first) on the committed design-J deck;
- thresholds: SN74LVC1G132 SCES546E 5.5 (-40..125 C), SN74LVC1G17 SCES351Y (as m1_pump_spice.py), LVC1G00/08 VIL 0.8 V,
  VIH 2.0 V (TI LVC at VCC 2.7-3.6 V, as DECISIONS 67 uses), LVC output <= 37.5 ohm from VOH 2.4 V at -16 mA, 3 V;
- J4.1 read-back: R146 220 k + controller 10 k series / 1 MOhm / 1 nF, as c49 bias_race.py j41_t() (ESP32-S3 VIH 0.75 VDD,
  VIL 0.25 VDD, Table 5-4).
Class tags in the output: G datasheet limit, C computed from G, S committed SPICE, E estimate.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True   # read-only on the repo: no __pycache__ beside the imported scripts

HERE = Path(__file__).resolve().parent
PS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
FM = PS / "validation-results/11-candidates/c24-monitor-fmea/scripts/fmea_metric.py"
spec = importlib.util.spec_from_file_location("fm", FM)
fm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fm)
LN = math.log


def interp(v, lo, hi):
    (v0, a), (v1, b) = lo, hi
    return a + (b - a) * (v - v0) / (v1 - v0)


VCC = (3.135, 3.465)                                   # v3v3 contract (c49)
G132 = dict(vtp_max=lambda v: interp(v, (3.0, 1.87), (4.5, 2.74)), vtm_min=lambda v: interp(v, (3.0, 0.84), (4.5, 1.41)),
            ii_uA=1.0)                                 # SCES546E 5.5, -40..125 C
G17 = dict(vtp_max=lambda v: interp(v, (3.0, 1.92), (4.5, 2.74)), vtm_min=lambda v: interp(v, (3.0, 0.89), (4.5, 1.51)),
           vtm_max=lambda v: interp(v, (3.0, 1.20), (4.5, 1.97)))
LVC_VIL, LVC_VIH, LVC_ROUT = 0.8, 2.0, (3.0 - 2.4) / 16e-3
R7_R15, R103 = 100e3, 10e3                             # native-21 PERMIT pull-downs (x2), controller R103
R_PD_PERMIT = 1 / (2 / R7_R15 + 1 / R103)


def interface(r135):
    """U46.A driven from PERMIT through r135 (worst VCC corners)."""
    out = {}
    for v in VCC:
        voh = v - 0.1 - 0.4e-3 * LVC_ROUT            # U37 LVC1G08 high into ~0.4 mA of pull-downs
        a_hi = voh - G132["ii_uA"] * 1e-6 * r135
        a_lo = 0.1 + G132["ii_uA"] * 1e-6 * r135
        out[f"VCC {v}"] = dict(U46A_high_V=round(a_hi, 3), VTplus_max_V=round(G132["vtp_max"](v), 3),
                               margin_high_V=round(a_hi - G132["vtp_max"](v), 3), U46A_low_V=round(a_lo, 3),
                               VTminus_min_V=round(G132["vtm_min"](v), 3),
                               margin_low_V=round(G132["vtm_min"](v) - a_lo, 3))
    vmax = VCC[1]
    # second faults that put a v3v3-level source on hsb_good (U46 pin 1-2 short to hb_rx, hsb_good to v3v3) while U37 is
    # Hi-Z (announced first fault: PERMIT then rests on its pull-downs)
    inj = vmax * R_PD_PERMIT / (R_PD_PERMIT + r135)
    out["PERMIT_undriven_plus_hsb_good_at_v3v3_V"] = round(inj, 3)
    out["below_U22_U23_VIL"] = inj < LVC_VIL
    out["PERMIT_driven_ripple_mV"] = round(vmax * LVC_ROUT / (LVC_ROUT + r135) * 1e3, 2)
    # hsb_good shorted to hb_hold (0.425 mm at C166.1): with the wave stopped and PERMIT high the hold rests at
    # VCC*Rbleed/(Rbleed+R135) (+ U40 leakage x Thevenin R); U40 must still see a low
    rb, ileak = 49.9e3, 5e-6
    rth = rb * r135 / (rb + r135)
    hold = [v * rb / (rb + r135) for v in VCC]
    out["hb_hold_short_hold_V_no_leak"] = [round(h, 3) for h in hold]
    out["hb_hold_short_hold_V_5uA_leak"] = [round(h + ileak * rth, 3) for h in hold]
    out["G17_VTminus_band_V"] = [[round(G17["vtm_min"](v), 3), round(G17["vtm_max"](v), 3)] for v in VCC]
    lo_ok = all(h + ileak * rth < G17["vtm_min"](v) for h, v in zip(hold, VCC))
    hi_mask = all(h > G17["vtm_max"](v) for h, v in zip(hold, VCC))
    out["hb_hold_short_verdict"] = ("non-masking (hold below VT-min at every corner)" if lo_ok else
                                    "masking (hold above VT-max: BIAS_GOOD = PERMIT)" if hi_mask else
                                    "indeterminate (hold inside U40's VT- band)")
    # U46.A RC: r135 x (Ci 3.5 pF + ~81.5 mm of hsb_good, taken as 15 pF total, E); Schmitt crossing at VT+max
    c = 15e-12
    v = VCC[0]
    out["U46A_rise_us_E"] = round(r135 * c * LN(1 / (1 - G132["vtp_max"](VCC[1]) / (v - 0.1))) * 1e6, 2)
    return out


def j41():
    """J4.1 -> GPIO35 RC (c49 j41_t): times to VIH 0.75 VDD (rise) and VIL 0.25 VDD (fall), us."""
    res = {}
    for name, (r146, rs, rpd, c) in {"fast": (220e3 * 0.99, 10e3 * 0.99, 1e6 * 1.01, 0.95e-9),
                                     "slow": (220e3 * 1.01, 10e3 * 1.01, 1e6 * 0.99, 1.05e-9)}.items():
        rsrc = r146 + rs
        vf = rpd / (rsrc + rpd)
        tau = c * rsrc * rpd / (rsrc + rpd)
        res[name] = dict(final_frac=round(vf, 4), tau_us=round(tau * 1e6, 1),
                         rise_to_VIH_us=round(tau * LN(vf / (vf - 0.75)) * 1e6, 1),
                         fall_to_VIL_us=round(tau * LN(vf / 0.25) * 1e6, 1))
    return res


def coverage():
    rows = [r for r in fm.rows_for("P2H", fm.base_params()) if r[5] == "chain"]
    total = sum(lam * k * n for _, _, lam, k, n, _ in rows)

    def cls(ref, mode):
        """-> (s48 as built, S, P guaranteed, P typical-leakage), each 1 = detected in the field."""
        if "U40" in ref and ("stuck high" in mode or "Y-VCC" in mode):
            return 0, 1, 1, 1      # as built: the boot sample loses the race (c49); S: once per power-on; P: every idle
        if "U40" in ref and "Y open" in mode:
            return 1, 1, 1, 1      # reads low -> start refused, in every variant
        if "R_bleed" in ref:
            return 0, 0, 0, 1      # P only: hold keeps its charge after PERMIT falls; caught if leakage < ~0.7 uA (E)
        return 0, 0, 0, 0          # HS link / diode / LDO-OV / out-of-spec rows: dormant in all three (B8 EOL only)
    out, sums = [], [0.0] * 4
    for ref, mode, lam, k, n, _ in rows:
        w = lam * k * n
        c = cls(ref, mode)
        for i in range(4):
            sums[i] += w * c[i]
        out.append(dict(ref=ref, mode=mode, RWL=round(w, 3), as_built=c[0], S=c[1], P_G=c[2], P_E=c[3]))
    pct = [round(100 * s / total, 2) for s in sums]
    return dict(chain_RWL=round(total, 3), rows=out,
                DC_pct={"s48 as built (boot race lost, c49)": pct[0], "S (TPS3808 delay, boot POST)": pct[1],
                        "P (PERMIT-gated heartbeat), guaranteed": pct[2],
                        "P, typical hold-node leakage (E)": pct[3]})


def sensitivity():
    cases = {"base": {}, "k_u = 0": {"k_u": 0.0}, "k_u = 1": {"k_u": 1.0}, "k_o = 0.5": {"k_o": 0.5},
             "passives x5": {"R": 2.5, "C": 2.5, "D": 5.0}}
    res = {}
    for name, ov in cases.items():
        p = fm.base_params()
        p.update(ov)
        rows = [r for r in fm.rows_for("P2H", p) if r[5] == "chain"]
        tot = sum(lam * k * n for _, _, lam, k, n, _ in rows)
        u40 = sum(lam * k * n for ref, mode, lam, k, n, _ in rows if "U40" in ref and
                  ("stuck high" in mode or "Y-VCC" in mode))
        yo = sum(lam * k * n for ref, mode, lam, k, n, _ in rows if "U40" in ref and "Y open" in mode)
        rb = sum(lam * k * n for ref, mode, lam, k, n, _ in rows if "R_bleed" in ref)
        res[name] = dict(chain_RWL=round(tot, 2), as_built=round(100 * yo / tot, 1), S=round(100 * (yo + u40) / tot, 1),
                         P_G=round(100 * (yo + u40) / tot, 1), P_E=round(100 * (yo + u40 + rb) / tot, 1))
    return res


def timing(spice):
    s = spice["summary"]
    rc = j41()
    pump_start = s["J T_OFF=1000.0us"]["t_start1_us_max"]
    pump_start_sh = s["J+1short T_OFF=1000.0us"]["t_start1_us_max"]
    trip = s["J T_OFF=1000.0us"]["t_trip_us_max"]
    trip_sh = s["J+1short T_OFF=1000.0us"]["t_trip_us_max"]
    a_rc = interface(100e3)["U46A_rise_us_E"]
    start_hw = pump_start + a_rc + 0.02           # + U46 / U40 / U22 tpd (ns, G)
    return dict(
        pump_start_from_PERMIT_us_S=[s["J T_OFF=1000.0us"]["t_start1_us_min"], pump_start],
        pump_start_one_cap_shorted_us_S=pump_start_sh,
        restart_after_short_off_us_S={k: v["t_start2_us_max"] for k, v in s.items()},
        stop_via_heartbeat_us_S=[trip, trip_sh],
        U46A_R135_rise_us_E=a_rc,
        drivers_enabled_after_PERMIT_us_C=f"<= {round(start_hw, 1)} + 2EDR8259X DIS-to-output (unpublished, C39)",
        GPIO35_high_after_PERMIT_us_C=round(start_hw + rc["slow"]["rise_to_VIH_us"], 0),
        GPIO35_low_after_PERMIT_fall_us_C=round(trip_sh + rc["slow"]["fall_to_VIL_us"], 0),
        J41_RC=rc,
        firmware_windows_ms=dict(T_START=2.0, T_IDLE=2.0, run_debounce=20.0,
                                 start_margin_x=round(2000 / (start_hw + rc["slow"]["rise_to_VIH_us"]), 1),
                                 idle_margin_x=round(2000 / (trip_sh + rc["slow"]["fall_to_VIL_us"]), 1)),
        # optional check (d): a J4.1-J4.9 short makes GPIO35 follow PERMIT through only the controller's 10 k / 1 nF
        # (tau 10 us, VIH in ~15 us); a healthy board cannot reach VIH before pump_min + the fast RC. Sampling inside
        # this window after RUN_EN rises separates the two.
        J41_J49_short_detect_window_us=[50, round(min(rc["fast"]["rise_to_VIH_us"],
                                                      rc["slow"]["rise_to_VIH_us"]) + s["J T_OFF=1000.0us"]["t_start1_us_min"]
                                                  - 40, 0)])


def main():
    sp = HERE / "results/pump_p_spice.json"
    spice = json.loads(sp.read_text()) if sp.exists() else None
    out = dict(fm_source=str(FM.relative_to(PS)), coverage=coverage(), sensitivity=sensitivity(),
               interface={f"R135 = {int(r / 1e3)} k": interface(r) for r in (10e3, 100e3, 140e3)},
               timing=timing(spice) if spice else "run pump_p_spice.py first")
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/fmea_p.json").write_text(json.dumps(out, indent=1) + "\n")
    L = ["# fmea_p.py output", "", f"Chain RWL {out['coverage']['chain_RWL']} FIT x rails (c24 P2H rows, base).", "",
         "| row | mode | RWL | s48 as built | S | P (G) | P (E) |", "|---|---|---:|:-:|:-:|:-:|:-:|"]
    for r in out["coverage"]["rows"]:
        L.append(f"| {r['ref']} | {r['mode']} | {r['RWL']} | {r['as_built']} | {r['S']} | {r['P_G']} | {r['P_E']} |")
    L += ["", "| field DC of the chain | % |", "|---|---:|"]
    L += [f"| {k} | {v} |" for k, v in out["coverage"]["DC_pct"].items()]
    L += ["", "| sensitivity | chain RWL | as built | S | P (G) | P (E) |", "|---|---:|---:|---:|---:|---:|"]
    L += [f"| {k} | {v['chain_RWL']} | {v['as_built']} | {v['S']} | {v['P_G']} | {v['P_E']} |"
          for k, v in out["sensitivity"].items()]
    (HERE / "results/fmea_p.md").write_text("\n".join(L) + "\n")
    print(json.dumps({k: out[k] for k in ("sensitivity", "interface", "timing")}, indent=1))
    print("\n".join(L))


if __name__ == "__main__":
    main()
