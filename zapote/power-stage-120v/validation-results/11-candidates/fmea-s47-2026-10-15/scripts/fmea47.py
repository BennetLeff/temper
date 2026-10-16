#!/usr/bin/env python3
"""Stage-47 FMEA re-run: the DECISIONS 59 monitor FMEA (C1-C7 + N rows, c24 RWL metric) on the current parts at their
modelled temperatures, a new U5 (REF25) block, and the B13 proof-test hooks.

    python3 -I scripts/sources47.py && python3 -I scripts/fmea47.py   -> results/fmea47.{json,md} ; exit 1 on a failed control

Inputs (read only):
  ../s16copy/            a verbatim copy of PS validation-results/11-candidates/s16-fmea-b-2026-10-15/{scripts,inputs}
                         plus a private copy of runs-native21/s16-fmea-b-dl as dl/; `sh scripts/run_all.sh` there rewrites
                         its results/ byte-identical to the committed ones (control C0, checked by sha256 below).
  PS native-21/frozen/default.csv, default.net   frozen s47 BOM / netlist (MPNs, the REF25 node)
  PS b3-ratings/margins.json                     hot-copper B3 estimates (c17.5 @ 61 release case, c28 @ 55 ratchet)
  PS c47-ref25-grade/results/bands-s47.json      the s47 OCP / OVP bands
  results/sources47.json                          every new datasheet number, regex-checked on its page

Variants.  S47 = V1 (1c-4420) topology with TL431BQDBZR and LM2901BIDR (stage 46) - the board of record.  V2 and V2+F2+v5
are DECISIONS 59's candidate B (as drawn / amended), carried at the same island temperatures for the comparison.
"""
import csv, hashlib, json, math, os, re, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
S16 = os.path.join(ROOT, "s16copy")
OUT = os.path.join(ROOT, "results")
PS = "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v"
FMEA_B = os.path.join(PS, "validation-results/11-candidates/s16-fmea-b-2026-10-15")
sys.path.insert(0, os.path.join(S16, "scripts"))
_cwd = os.getcwd()
os.chdir(S16)
import model as m            # noqa: E402
import bands as bnd          # noqa: E402
import candidate_b as cb     # noqa: E402
import fmea_metric as fm     # noqa: E402
os.chdir(_cwd)
r3 = lambda x: round(x, 3)
r4 = lambda x: round(x, 4)
NAMES = ("neg UV", "neg OV", "span UV", "span OV")
KB = 8.617333e-5
BAD = []


def check(cond, msg):
    if not cond:
        BAD.append(msg)
    return cond


def af(t_from, t_to, ea=0.7):
    """Arrhenius acceleration, TI's temperature-change FIT calculator (sources47 TI_ARRHENIUS)."""
    return math.exp(ea / KB * (1 / (t_from + 273.15) - 1 / (t_to + 273.15)))


SRC47 = json.load(open(os.path.join(OUT, "sources47.json")))
check(all(v["verified_in_text"] for v in SRC47.values()), "sources47 has an unverified needle")
SRC16 = json.load(open(os.path.join(S16, "results", "sources.json")))


# ============================================================================================ C0 controls and freeze
def controls():
    out = {}
    same = []
    for f in sorted(os.listdir(os.path.join(FMEA_B, "results"))):
        if f == "datasheet-manifest.json":
            continue
        a = hashlib.sha256(open(os.path.join(FMEA_B, "results", f), "rb").read()).hexdigest()
        b = hashlib.sha256(open(os.path.join(S16, "results", f), "rb").read()).hexdigest()
        same.append(a == b)
    out["C0_s16_fmea_b_rerun_byte_identical"] = f"{sum(same)}/{len(same)} result files"
    check(all(same), "C0: the DECISIONS 59 FMEA copy does not rerun byte-identical")
    # freeze: the parts this FMEA is about
    bom = {}
    for row in csv.DictReader(open(os.path.join(PS, "native-21/frozen/default.csv"))):
        for d in row["Designator"].split(","):
            bom[d.strip()] = row["Comment"]
    want = {"U17": "TL431BQDBZR", "U19": "TL431BQDBZR", "U21": "TL431BQDBZR", "U29": "LM2901BIDR", "U30": "LM2901BIDR",
            "U31": "LM2901BIDR", "U5": "LM4050AEM3-2.5/NOPB", "U14": "TPS3700DDCR", "U6": "TLV3201AIDBVR", "U7": "TLV3201AIDBVR",
            "R31": "0603WAF5601T5E", "R32": "RT0603BRD0710KL", "R33": "RT0603BRD0710KL", "R34": "RT0603BRD0712K6L",
            "R35": "TNPW060311K7BEEA", "R36": "RT0603BRD0710KL", "R37": "RT0603BRD07140KL", "C30": "CL10C101JB8NNNC",
            "C31": "C0603C102J5GACTU", "C33": "C0603C102J5GACTU"}
    got = {k: bom.get(k) for k in want}
    out["frozen_bom"] = got
    check(got == want, f"frozen BOM differs: {got}")
    # REF25 node in the frozen netlist: no capacitor on it
    net = open(os.path.join(PS, "native-21/frozen/default.net")).read()
    blk = re.search(r'\(net \(code "\d+"\) \(name "ref25"\)(.*?)\(net \(code', net, re.S).group(1)
    nodes = re.findall(r'\(ref "([^"]+)"\) \(pin "([^"]+)"\)', blk)
    out["ref25_node"] = nodes
    check(sorted(nodes) == sorted([("R31", "2"), ("U5", "1"), ("R32", "1"), ("R34", "1"), ("R36", "1")]), f"ref25 node {nodes}")
    nc = re.search(r'\(net \(code "\d+"\) \(name "u_ref-nc"\)(.*?)\(net \(code', net, re.S).group(1)
    check(re.findall(r'\(ref "([^"]+)"\) \(pin "([^"]+)"\)', nc) == [("U5", "3")], "U5 pin 3 not floating alone")
    for capnet, cap, via in (("ocp_node", "C30", "R32"), ("ocp_thresh", "C31", "R34"), ("ovp_thresh", "C33", "R36")):
        b = re.search(r'\(net \(code "\d+"\) \(name "%s"\)(.*?)\(net \(code' % capnet, net, re.S).group(1)
        refs = [r for r, _ in re.findall(r'\(ref "([^"]+)"\) \(pin "([^"]+)"\)', b)]
        check(cap in refs and via in refs, f"{cap} not behind {via} on {capnet}")
    # U14 INB tied to ground, OUTB alone (the spare channel the REF25 watchdog would use)
    for nm, want_nodes in (("outb", [("U14", "6")]),):
        b = re.search(r'\(net \(code "\d+"\) \(name "%s"\)(.*?)\(net \(code' % nm, net, re.S).group(1)
        check(re.findall(r'\(ref "([^"]+)"\) \(pin "([^"]+)"\)', b) == want_nodes, "U14 OUTB not spare")
    b = re.search(r'\(net \(code "\d+"\) \(name "ocp_kelvin_p"\)(.*?)\(net \(code', net, re.S).group(1)
    check(("U14", "4") in re.findall(r'\(ref "([^"]+)"\) \(pin "([^"]+)"\)', b), "U14 INB (pin 4) not on ocp_kelvin_p")
    # J4 pin 1 spare (BIAS_GOOD readback hook)
    b = re.search(r'\(net \(code "\d+"\) \(name "[^"]*j4_nc1[^"]*"\)(.*?)\(net \(code', net, re.S | re.I)
    out["J4_pin1_net_nodes"] = re.findall(r'\(ref "([^"]+)"\) \(pin "([^"]+)"\)', b.group(1)) if b else None
    return out


# =============================================================================== temperatures (B3 hot copper, s47)
def temps():
    d = json.load(open(os.path.join(PS, "validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json")))
    out = {}
    for case in ("c17.5_h10", "c28_h10"):
        s = json.dumps(d["cases"][case])
        t = {}
        for ref in ("U17", "U19", "U21", "U29", "U30", "U31", "U5"):
            i = s.find(f'"item": "{ref}:')
            t[ref] = float(re.search(r'"est_c": ([\d.]+)', s[i:i + 400]).group(1))
            if ref in ("U29", "U30", "U31"):
                t[ref + "_selfheat"] = float(re.search(r'"self_heat_k": ([\d.]+)', s[i:i + 400]).group(1))
        out[case] = t
    check(out["c17.5_h10"]["U29"] == 102.6 and out["c17.5_h10"]["U17"] == 92.4 and out["c17.5_h10"]["U5"] == 89.1,
          "B3 temperatures differ from the brief (102.6 / 92.4 / 89.1)")
    return out


RAILS = {"LS": ("U17", "U29"), "HS-A": ("U19", "U30"), "HS-B": ("U21", "U31")}


# ========================================================================================= monitor rates per rail
def fs_parts(ch=None):
    """Base convention (D59 / c24): TI functional-safety FITs (IEC TR 62380), FMD on the total. LM2901B is now direct
    (SLCA004 names it); TL431BQ uses SNVA914 (TL431-Q1, the 125 C die family; the catalogue Q grade is not -Q1)."""
    return cb.parts(SRC16, {k: v for k, v in (ch or {}).items() if k == "tps3703_fmd"})


def scaled(P, k_tl=1.0, k_lm=1.0, k_tp=1.0, base=None):
    """Copy of P with each part's fit/die/pkg multiplied (base: optional per-part totals replacing the FS totals,
    keeping the FS die/package split)."""
    import copy
    Q = copy.deepcopy(P)
    for name, k in (("TL431", k_tl), ("LM339B", k_lm), ("TPS3701", k_tp)):
        d = Q[name]
        tot = d["fit"]
        new = (base[name] if base and name in base else tot) * k
        s = new / tot
        d["fit"], d["die"], d["pkg"] = new, d["die"] * s, d["pkg"] * s
    return Q


def rate_model(case, t, rail, ch=None):
    """-> P for one rail.  case: 'fs' | 'est55' | 'est_T' | 'sn_T'."""
    P = fs_parts(ch)
    tl_ref, cmp_ref = RAILS[rail]
    t_tl, t_cmp = t.get(tl_ref, 55.0), t.get(cmp_ref, 55.0)
    t_tps = t_cmp - t.get(cmp_ref + "_selfheat", 0.0)       # TPS3701 at the island, without the LM2901B's 3.14 K
    est = SRC47["TI_ESTIMATOR"]["values"]
    est16 = SRC16["TI_ESTIMATOR"]["values"]
    if case == "fs":
        return P
    if case == "est55":   # D59's sensitivity row (control): the estimator FITs at its own 55 C
        return scaled(P, base={"TL431": est16["TL431AIDBZR"]["FIT"], "LM339B": est16["LM339BIDR"]["FIT"],
                               "TPS3701": est16["TPS3701DDCR"]["FIT"]})
    if case == "est_T":   # the parts' own estimator rows (TL431BQDBZR, LM2901BIDR), moved 55 C -> T by TI's Arrhenius
        return scaled(P, af(55, t_tl), af(55, t_cmp), af(55, t_tps),
                      base={"TL431": est["TL431BQDBZR"]["FIT"], "LM339B": est["LM2901BIDR"]["FIT"],
                            "TPS3701": est16["TPS3701DDCR"]["FIT"]})
    if case == "sn_T":    # SN 29500-2 reference FIT at its reference TJ, moved to T with TI's 0.7 eV Arrhenius
        sn = {"TL431": (SRC47["TL431_SN29500"]["values"], t_tl), "LM339B": (SRC47["LM2901B_SN29500"]["values"], t_cmp),
              "TPS3701": (SRC47["TPS3700Q1_SN29500"]["values"], t_tps)}
        return scaled(P, *(af(v["ref_TJ_C"], T) for v, T in (sn["TL431"], sn["LM339B"], sn["TPS3701"])),
                      base={k: v["ref_FIT"] for k, (v, _) in sn.items()})
    raise ValueError(case)


def monitor_metric(sim, drift, t, case, ch=None, variants=("V1", "V2", "V2+F2+v5")):
    ch = ch or {}
    p = dict(fm.base_params(), **{k: v for k, v in ch.items() if k in ("k_u", "k_o", "R", "C", "D", "Q")})
    alloc = ch.get("alloc", "A")
    chain = fm.score(fm.rows_for("P2H", p))["RWL_chain"]
    res = {}
    for var in variants:
        per_rail, thr = {}, {n: 0.0 for n in NAMES}
        whole = 0.0
        for rail in RAILS:
            P = rate_model(case, t, rail, ch)
            rows = cb.frontend(var, sim, drift, p, P, alloc)
            s = cb.summarise(rows)
            per_rail[rail] = r3(s["RWL_per_rail"])
            for n in NAMES:
                thr[n] += s["per_threshold"][n]
            whole += s["FIT_whole_rail_per_rail"]
        fe = sum(per_rail.values())
        res["S47" if var == "V1" else var] = {"chain_RWL": chain, "frontend_RWL": r3(fe), "total_RWL": r3(chain + fe),
                                              "frontend_per_rail": per_rail, "per_threshold_FIT": {n: r3(v) for n, v in thr.items()},
                                              "FIT_whole_rail_masks": r3(whole)}
    return res


def monitors(T):
    sim = json.load(open(os.path.join(S16, "results", "fault_sim.json")))["variants"]
    drift16 = json.load(open(os.path.join(S16, "results", "bands.json")))["drift"]
    out = {}
    # ---- failure-mode assumptions for the new grades (datasheet identity of the model inputs)
    lm = SRC47["LM2901B_VIO"]["values"]["VIO_mV"] * 1e-3
    check(abs(lm - m.LM339B["vos"]) < 1e-12 and m.LM339B["ib"] == 50e-9, "LM2901B VIO / IB differ from the model's LM339B")
    tq = SRC47["TL431BQ_VREF"]["values"]
    check(tuple(tq["v25"]) == m.TL431["TL431BIDBZR"]["v25"] and tq["videv"] == m.TL431["TL431BIDBZR"]["videv"],
          "TL431BQ Vref / VI(dev) differ from the BI row")
    out["mode_assumptions"] = {
        "LM2901B": "same die family and data sheet as LM339B (SLCS006Z); SLCA004 FIT / FMD / pin FMA now name the part "
                   "directly (was a proxy); pinout SLCA004 Fig 1-2 = fault-sim mapping; VIO 5.5 mV / IB 50 nA / VCM (V+)-2 V "
                   "now over -40..125 C (6.8 p.8); open-collector output, 'one input in range' note unchanged; minimum "
                   "supply 2 V (6.4 p.6) so the C7 sliver is unchanged; IOH leakage specified only at 25 C, and leakage can "
                   "only pull 'good' low (announce), never mask. No failure-mode assumption changes.",
        "TL431BQ": "SLVS543S 6.13 p.14: Vref 2.483-2.507 V, VI(dev) 34 mV max, now over -40..125 C; same DBZ pinout; "
                   "FIT / FMD source unchanged (SNVA914, the -Q1 die family). The cathode node has no capacitor "
                   "(fault-sim netlist: rref 2.2 k + halfref divider only), so the stability-boundary question is "
                   "unchanged. No failure-mode assumption changes.",
    }
    out["fault_sim"] = "S47 uses the V1 fault-simulation rows unchanged (same topology, pinout, VIO band): " \
                       f"{len(sim['V1'])} single faults"
    # ---- C4 / reference drift at the 125 C basis (100 K TCR) - the bound that makes C4 'announced'
    m.TL431["TL431BQDBZR"] = {"v25": tuple(tq["v25"]), "videv": tq["videv"], "zka": 0.5, "cite": "SLVS543S 6.13 p.14"}
    s47 = dict(bnd.V1, ref="TL431BQDBZR")
    dt0 = m.DT
    ctl = bnd.judge_drift(bnd.drift_lm(bnd.V1))                    # control at 60 K: the committed V1 rows
    check(all(abs(ctl[k]["worst_dormant_threshold_V"] - drift16["V1"][k]["worst_dormant_threshold_V"]) < 1e-4 for k in ctl),
          "drift control (V1 at 60 K) does not reproduce bands.json")
    m.DT = 100.0
    dA = bnd.judge_drift(bnd.drift_lm(s47))                        # thresholds at 100 K, rails as S16 (60 K)
    neg0 = bnd.NEG
    bnd.NEG = m.neg_rail("LS", 100.0)["wc"]
    for n in ("neg UV", "neg OV"):
        bnd.RAIL[n] = bnd.NEG
    dB = bnd.judge_drift(bnd.drift_lm(s47))                        # rails hot as well
    bnd.NEG = neg0
    for n in ("neg UV", "neg OV"):
        bnd.RAIL[n] = neg0
    m.DT = dt0
    out["drift_125C"] = {"thresholds_100K_rails_60K": dA, "thresholds_and_neg_rail_100K": dB,
                         "control_V1_60K": "reproduces s16 bands.json to 1e-4"}
    silent = [k for d in (dA, dB) for k, v in d.items() if v["silent_mask_vs_H"]]
    out["drift_silent_vs_H"] = silent
    drift = dict(drift16)
    drift["V1"] = dA          # S47's C4 judgement uses the 125 C bound
    # ---- metric, every D59 case (S47 must equal V1: same modes, same FS rates)
    t0 = {}
    cases = {}
    for cname, ch in cb.CASES.items():
        if ch.get("estimator"):
            continue
        cases[cname] = monitor_metric(sim, drift, t0, "fs", ch)
    ref = json.load(open(os.path.join(FMEA_B, "results", "fmea_b_metric.json")))["cases"]
    for cname, r in cases.items():
        for var, rv in (("S47", "V1"), ("V2", "V2"), ("V2+F2+v5", "V2+F2+v5")):
            check(abs(r[var]["total_RWL"] - ref[cname][rv]["total_RWL"]) < 2e-3,
                  f"{cname} {var}: {r[var]['total_RWL']} vs D59 {ref[cname][rv]['total_RWL']}")
    cases["TI estimator FITs at 55 C (D59 row, control)"] = monitor_metric(sim, drift, t0, "est55")
    check(abs(cases["TI estimator FITs at 55 C (D59 row, control)"]["S47"]["total_RWL"] - ref["TI estimator FITs (8 / 8 / 0.1)"]["V1"]["total_RWL"]) < 2e-3,
          "estimator-55 control does not reproduce D59")
    for tc in ("c17.5_h10", "c28_h10"):
        cases[f"TI estimator, own rows, at {tc} temperatures"] = monitor_metric(sim, drift, T[tc], "est_T")
        cases[f"SN 29500 reference x Arrhenius 0.7 eV at {tc} temperatures"] = monitor_metric(sim, drift, T[tc], "sn_T")
    out["cases"] = cases
    out["D59_reference"] = {c: {v: ref[c][v]["total_RWL"] for v in ("V1", "V2", "V2+F2+v5")} for c in ref}
    # per-part FIT at temperature (for the table)
    est = SRC47["TI_ESTIMATOR"]["values"]
    tab = {}
    for tc in ("c17.5_h10", "c28_h10"):
        t = T[tc]
        tab[tc] = {ref_: {"T_C": t[ref_],
                          "est_FIT": r3((est["TL431BQDBZR"] if ref_ in ("U17", "U19", "U21") else est["LM2901BIDR"])["FIT"] * af(55, t[ref_])),
                          "SN29500_FIT": r3((3 * af(45, t[ref_])) if ref_ in ("U17", "U19", "U21") else 6 * af(55, t[ref_])),
                          "FS_FIT_base": 6 if ref_ in ("U17", "U19", "U21") else 16}
                   for ref_ in ("U17", "U19", "U21", "U29", "U30", "U31")}
    out["part_FIT_at_T"] = tab
    # front-end dormant rows (allocation B) for the hook coverage
    pB = fm.base_params()
    PB = fs_parts()
    out["_rowsB"] = cb.frontend("V1", sim, drift, pB, PB, "B")
    return out


# ================================================================================================== U5 (REF25)
R31, R32, R33, R34, R35, R36, R37 = 5.6e3, 10e3, 10e3, 12.6e3, 11.7e3, 10e3, 140e3
RSH = 1e-3
DIV = (4 * 470e3 + 15.8e3) / 15.8e3
HOT5 = (4.75, 5.15)                         # c47 README section 7 (U5's current window covers 4.75-5.15 V)
E31 = 0.01 + 100e-6 * 70                    # 0603WAF 1 % thick film; 100 ppm/K x (95 - 25) K (TCR assumed, not re-read)
ETH = 0.001 + 25e-6 * 100                   # 0.1 % / 25 ppm thin film over 100 K (S16 model THIN_01_25)
WD_RT, WD_RB = 54.2e3, 10e3                 # proposed REF25 watchdog divider into U14 INB (E192 0.1 %)


def ref_open(hot5, r31, rload, extra=None):
    g = sum(1 / r for r in rload) + (1 / extra if extra else 0.0)
    return hot5 / (1 + r31 * g)


def u5_block(T):
    bands = json.load(open(os.path.join(PS, "validation-results/11-candidates/c47-ref25-grade/results/bands-s47.json")))
    s = json.dumps(bands)
    vr = (2.5 - 0.015 - 0.0012, 2.5 + 0.015 + 0.0012)          # SNOS455H 5.6 p.7: +-15 mV ext range, +-1.2 mV IR window
    ocp_band, ovp_band, kelvin = (68.87, 117.45), (272.64, 287.45), -2.123   # bands-s47.md release row (s47 basis)
    k = R35 / (R34 + R35)
    i_per_v = (1 - 2 * k) / RSH
    ovp_per_v = R37 / (R36 + R37) * DIV
    loads = [(R32 + R33), (R34 + R35), (R36 + R37)]
    lo_l = [r * (1 + ETH) for r in loads]
    hi_l = [r * (1 - ETH) for r in loads]
    out = {"nominal": {"OCP_trip_A_per_V_REF": r3(i_per_v), "OCP_trip_A_at_2V5": r3(2.5 * i_per_v),
                       "OVP_trip_V_per_V_REF": r3(ovp_per_v), "OVP_trip_V_at_2V5": r3(2.5 * ovp_per_v)}}
    check(abs(2.5 * ovp_per_v - 280.0) < 0.5 and abs(2.5 * i_per_v - 92.6) < 0.1, "OCP / OVP nominal scale")
    # healthy current budget
    imin = (HOT5[0] - vr[1]) / (R31 * (1 + E31)) - sum(vr[1] / r for r in hi_l)
    imin_wd = imin - vr[1] / ((WD_RT + WD_RB) * (1 - ETH))
    out["U5_current_min_mA"] = {"today": r4(imin * 1e3), "with_watchdog": r4(imin_wd * 1e3), "IRMIN": 0.065}
    check(imin_wd > 65e-6, "watchdog load starves U5")
    # mode: U5 open (cathode or anode pin open): node set by R31 and the loads
    vo = {"today": (ref_open(HOT5[0], R31 * (1 + E31), hi_l), ref_open(HOT5[1], R31 * (1 - E31), lo_l)),
          "with_watchdog": (ref_open(HOT5[0], R31 * (1 + E31), hi_l, (WD_RT + WD_RB) * (1 - ETH)),
                            ref_open(HOT5[1], R31 * (1 - E31), lo_l, (WD_RT + WD_RB) * (1 + ETH)))}
    def eff(v):
        return {"REF_V": [r4(v[0]), r4(v[1])],
                "OCP_nominal_A": [r3(v[0] * i_per_v), r3(v[1] * i_per_v)],
                "OCP_band_scaled_A": [r3(ocp_band[0] * v[0] / vr[0]), r3(ocp_band[1] * v[1] / vr[1])],
                "OCP_low_after_Kelvin_A": r3(ocp_band[0] * v[0] / vr[0] + kelvin),
                "OVP_nominal_V": [r3(v[0] * ovp_per_v), r3(v[1] * ovp_per_v)],
                "OVP_band_scaled_V": [r3(ovp_band[0] * v[0] / vr[0]), r3(ovp_band[1] * v[1] / vr[1])]}
    out["open"] = {k_: eff(v) for k_, v in vo.items()}
    # mode: drift high - the REF at which each limit is reached (band corner scales with REF)
    lim = {"OVP top rule 288.02 V (c47 basis)": ("ovp", 288.02), "D3 MRT130KP295CV stand-off 295 V (DC-LINK-CLAMP.md)": ("ovp", 295.0),
           "R5 CSS2H pulse row 118.74 A (stage 16)": ("ocp", 118.74)}
    out["drift_high_REF_at_limit"] = {n: {"REF_V": r4(vr[1] * L / (ovp_band[1] if w == "ovp" else ocp_band[1])),
                                          "pct_over_VRmax": r3(100 * (L / (ovp_band[1] if w == "ovp" else ocp_band[1]) - 1))}
                                      for n, (w, L) in lim.items()}
    # watchdog trip window: INB = REF x rb/(rt+rb) crosses VIT+ (396..404 mV, SBVS187G 6.5 p.6); ratio tolerance and IINB
    rnom = WD_RB / (WD_RT + WD_RB)
    er = (WD_RT / (WD_RT + WD_RB)) * 2 * ETH
    rth = WD_RT * WD_RB / (WD_RT + WD_RB)
    vitp = SRC47["TPS3700_VITP"]["values"]["VITP_V"]
    iib = SRC47["TPS3700_IINB"]["values"]["IINB_nA"] * 1e-9
    trip = ((vitp[0] - iib * rth) / (rnom * (1 + er)), (vitp[1] + iib * rth) / (rnom * (1 - er)))
    out["watchdog"] = {"divider": "54.2 k / 10 k (0.1 %, 25 ppm) REF25 -> U14 INB (pin 4, today on ocp_kelvin_p); "
                                  "U14 OUTB (pin 6, today alone on net 'outb') -> HOT5_UV_RAW (wired with OUTA, R50 pull-up)",
                       "trip_REF_V": [r4(trip[0]), r4(trip[1])], "false_trip_margin_V": r4(trip[0] - vr[1]),
                       "U5_open_margin_V": r4(vo["with_watchdog"][0] - trip[1]),
                       "undetected_drift_up_to_REF_V": r4(trip[1]),
                       "OVP_top_at_that_REF_V": r3(ovp_band[1] * trip[1] / vr[1]),
                       "OCP_top_at_that_REF_A": r3(ocp_band[1] * trip[1] / vr[1]),
                       "INB_at_REF_open_max_V": r3(vo["with_watchdog"][1] * rnom)}
    check(trip[0] > vr[1], "watchdog would false-trip at VR max")
    check(vo["with_watchdog"][0] > trip[1], "watchdog would miss U5 open")
    # FIT rows: allocation A (D59 base: FMD on the total FIT) and B (die FMD on die FIT, package on pins)
    fit = SRC47["LM4050_FIT"]["values"]
    fmd = SRC47["LM4050_FMD"]["values"]
    est = SRC47["TI_ESTIMATOR"]["values"]["LM4050AEM3X-2.5/NOPB"]["FIT"]
    t5 = {tc: T[tc]["U5"] for tc in T}
    rates = {"FS (SNOAA49A Table 2-1, 4 FIT)": 4.0, "FS per revision history (6 FIT)": 6.0,
             "TI estimator LM4050AEM3X at c17.5 (89.1 C)": est * af(55, t5["c17.5_h10"]),
             "TI estimator LM4050AEM3X at c28 (104.7 C)": est * af(55, t5["c28_h10"]),
             "SN 29500 20 FIT @55 C x Arrhenius at c17.5": 20 * af(55, t5["c17.5_h10"]),
             "SN 29500 20 FIT @55 C x Arrhenius at c28": 20 * af(55, t5["c28_h10"])}
    MODES = [  # (id, mode, share-of: 'die'|'pkg', fraction, effect, class, detection_today, k_dormant_dangerous)
        ("U1", "VR out of specification, high (half of TI's 40 %)", "die", fmd["vr_out_of_spec"] / 2,
         "OCP and OVP thresholds rise together (both scale with REF); no companion announces; > +0.20 % breaks the 288.02 V "
         "OVP rule, > +1.1 % passes the 118.74 A R5 pulse row, > +2.6 % passes the 295 V D3 stand-off",
         "fail-dangerous (magnitude unknown)", "none", "k_o"),
        ("U2", "VR out of specification, low", "die", fmd["vr_out_of_spec"] / 2,
         "OCP and OVP thresholds fall: more protective; nuisance trip only if large (OVP trips below the ~170 V bus at "
         "-39 %, OCP below the 59 A envelope peak at -36 %)", "fail-safe", "announced only if large", "0"),
        ("U3", "dynamic impedance outside specification (TI 20 %); includes any oscillation", "die", fmd["dyn_impedance"],
         "VR moves with U5 current (0.11-0.48 mA window): static error of either sign, magnitude unknown; an AC "
         "component on REF25 reaches OCP_THRESH / OVP_THRESH through 6.1 k || 1 nF and 9.3 k || 1 nF (and OCP_NODE "
         "through 5 k || 100 pF), so ripple on the threshold side is a nuisance-trip risk, not a mask",
         "half fail-dangerous (k_o)", "none", "k_o/2"),
        ("U4", "minimum regulation current above specification (TI 40 %)", "die", fmd["irmin_high"],
         "if IRMIN rises above the 0.11-0.15 mA available, U5 leaves regulation below VR: thresholds fall", "fail-safe",
         "announced only if large", "0"),
        ("U5o", "cathode pin open (TI: 'device is unpowered')", "pkg_open", 1 / 3,
         "REF25 rises to the R31 / load divider: {0[REF_V][0]}-{0[REF_V][1]} V; OVP nominal {0[OVP_nominal_V][0]:.0f}-{0[OVP_nominal_V][1]:.0f} V "
         "(band {0[OVP_band_scaled_V][0]:.0f}-{0[OVP_band_scaled_V][1]:.0f} V) against the 288.02 V rule; OCP nominal "
         "{0[OCP_nominal_A][0]:.0f}-{0[OCP_nominal_A][1]:.0f} A (band top {0[OCP_band_scaled_A][1]:.0f} A) against the 117.45 A corner".format(out["open"]["today"]),
         "fail-dangerous", "none (FW VBUS over-range latch at 231 V is a diverse OVP layer, not a detection)", "1"),
        ("U6o", "anode pin open (TI: 'does not regulate and is held low')", "pkg_open", 1 / 3,
         "no DC path through U5 with the anode open: REF25 rises exactly as U5o. TI's 'held low' does not apply to this "
         "circuit (its pin FMA assumes 2.2 k feed, SNOAA49A p.5); taken as U5o", "fail-dangerous", "none", "1"),
        ("U7o", "pin 3 (NC) open", "pkg_open", 1 / 3, "no effect (pin 3 floats by design, SNOS455H p.15)", "no effect", "-", "0"),
        ("U8s", "cathode-anode short (and die short to anode)", "pkg_short", 1 / 3,
         "REF25 = 0: OVP_THRESH 0 < VSENSE_IN (bus/120) -> OVP trips at once; OCP node / threshold both 0 -> trips at any "
         "bus current above 2 x VOS / 1 mOhm", "fail-safe", "announced at power-up (BUS_FAULT)", "0"),
        ("U9s", "anode-NC short", "pkg_short", 1 / 3, "no effect (TI class D)", "no effect", "-", "0"),
        ("U10s", "NC-cathode short (TI: 'Iq can increase', class C)", "pkg_short", 1 / 3,
         "extra current through the pin-2/pin-3 parasitic Schottky; either REF25 unchanged or clamped low",
         "fail-safe", "announced if REF25 clamps", "0"),
    ]
    rows = []
    for (mid, mode, where, frac, effect, cls, det, kd) in MODES:
        lamA = fit["total"] * frac if where == "die" else 0.0
        lamB = fit["die"] * frac if where == "die" else fit["package"] * 0.5 * frac
        rows.append({"id": mid, "mode": mode, "FIT_alloc_A": r4(lamA), "FIT_alloc_B": r4(lamB), "effect": effect,
                     "class": cls, "detection_today": det, "k_dangerous_dormant": kd,
                     "FIT_at_rates_alloc_B": {n: r4(lamB * v / fit["total"]) for n, v in rates.items()}})
    out["rows"] = rows
    out["rates_total_FIT"] = {n: r3(v) for n, v in rates.items()}

    def dd(alloc, ko, ku=1.0):
        tot = 0.0
        for r in rows:
            lam = r["FIT_alloc_" + alloc]
            k_ = {"1": ku, "0": 0.0, "k_o": ko, "k_o/2": ko / 2}[r["k_dangerous_dormant"]]
            tot += lam * k_
        return r4(tot)
    out["dormant_dangerous_FIT"] = {"alloc A, k_o 0 (D59 base)": dd("A", 0.0), "alloc B, k_o 0": dd("B", 0.0),
                                    "alloc B, k_o 0.5": dd("B", 0.5), "alloc B, k_o 1": dd("B", 1.0),
                                    "alloc B, k_o 1, SN 29500 at 89.1 C": r4(dd("B", 1.0) * rates["SN 29500 20 FIT @55 C x Arrhenius at c17.5"] / 4)}
    # S / O / D on the c24 scales: S 7 = protection lost, 5 = partly lost, 3 = announced; D 9 dormant, 1 announced
    sod = []
    for r in rows:
        if r["class"].startswith("fail-dangerous"):
            S = 7 if r["id"] in ("U5o", "U6o") else 5
            D = 9
        elif r["class"].startswith("half"):
            S, D = 5, 9
        elif r["class"] == "no effect":
            continue
        else:
            S, D = 3, (1 if "announced at" in r["detection_today"] else 5)
        lam = max(r["FIT_alloc_A"], r["FIT_alloc_B"])
        O = cb.O_of(lam)
        sod.append({"id": r["id"], "S": S, "O": O, "D": D, "RPN": S * O * D, "FIT_used": lam})
    out["SOD"] = sod
    out["stability"] = {
        "verdict": "stable: TI states stability with any capacitive load (SNOS455H p.1), internal compensation with no "
                   "output capacitor (7.3 p.14) and stability with a bypass capacitor (8.1 p.15). The frozen netlist puts "
                   "no capacitor on REF25 at all (R31, U5.1, R32, R34, R36 only); the three filter caps sit behind "
                   ">= 10 k (C30 100 pF via R32, C31 1 nF via R34 12.6 k, C33 1 nF via R36 10 k), so the cathode sees at "
                   "most pad / trace parasitics directly. Load-capacitance range at the node: ~0 pF direct, 2.1 nF total "
                   "behind 10-12.6 k. Oscillation is not a credible mode; it is carried inside TI's 20 % "
                   "'dynamic impedance' mode (U3).",
        "node": "ref25: R31.2, U5.1, R32.1, R34.1, R36.1 (frozen default.net)"}
    return out


# ================================================================================================== B13 hooks
def hooks(mon, u5):
    rows = mon["_rowsB"]
    tot = sum(r["fit"] * sum(r["k"].values()) for r in rows)
    tap = sum(r["fit"] * sum(r["k"].values()) for r in rows if r["kind"] in ("die", "pin_open", "pin_short", "cap_short"))
    span_ov = sum(r["fit"] * r["k"].get("span OV", 0.0) for r in rows)
    union_ls = sum(r["fit"] * sum(v for t, v in r["k"].items() if r["kind"] in ("die", "pin_open", "pin_short", "cap_short") or t == "span OV")
                   for r in rows)

    def grp(r):   # halfref-shift test: detects a row only if it masks BOTH thresholds of the shifted group
        k = r["k"]
        g = 0.0
        for a, b in (("neg OV", "span OV"), ("neg UV", "span UV")):
            if k.get(a, 0) > 0 and k.get(b, 0) > 0:
                g += k[a] + k[b]
        return g
    shift = sum(r["fit"] * grp(r) for r in rows)
    chain = {r[0] + " | " + r[1]: (r[2] * r[3] * r[4]) for r in fm.rows_for("P2H", fm.base_params()) if r[5] == "chain"}
    ch_tot = sum(chain.values())
    bg_always = sum(v for k, v in chain.items() if "Y open" in k)
    bg_seq = sum(v for k, v in chain.items() if "U40" in k and ("stuck high" in k or "Y-VCC" in k))
    b8 = sum(v for k, v in chain.items() if ("ISO6721FB" in k and "stuck high" in k) or "veto lost" in k)
    out = {
        "frontend_dormant_FIT_thr_per_rail_allocB": r3(tot),
        "chain_RWL": r3(ch_tot),
        "hooks": [
            {"id": "H1", "name": "REF25 watchdog on U14's spare INB / OUTB (cheap hardware, continuous)",
             "what": u5["watchdog"]["divider"], "covers": "U5 cathode / anode open (U5o, U6o): 100 %; U5 drift high beyond "
             f"{u5['watchdog']['trip_REF_V'][0]}-{u5['watchdog']['trip_REF_V'][1]} V; R31 short (U5 overstress -> open)",
             "DC_field": "100 % of U5o/U6o; drift-high only above the trip (magnitude distribution unknown)",
             "cost": "2 x 0603 0.1 % (10 k on the BOM; 54.2 k new line, or 2 x existing values), INB / OUTB re-tied: copper change",
             "side effect": "U14 pins 4-5 (INB-VDD) are adjacent; with VDD = V15_LS a 4-5 short puts ~15 V on INB (7 V abs max, "
                            "SBVS187G 6.1 p.5): today that short collapses V15_LS (announced), with the hook it may damage U14 "
                            "(k_u). Removed if U14 VDD moves to HOT5 (5 V on INB, inside the rating; below UVLO OUTA is driven "
                            "low, SBVS187G note 3 p.6; below V(POR) the CA-IS3720HW defaults high)."},
            {"id": "H2", "name": "BIAS_GOOD readback on J4 pin 1 (spare since stage 38) + firmware POST",
             "what": "BIAS_GOOD -> 1 k -> J4.1 -> controller GPIO with a 100 k pull-down; POST requires BIAS_GOOD = 0 before "
                     "the bias rails are up and = 1 after, and BIAS_GOOD = 1 continuously while PERMIT is requested",
             "covers": "U40 Y open (reads 0): always; U40 Y stuck high / Y-VCC short: only if the MCU samples before the "
                       "heartbeat starts (power sequencing to confirm at bring-up); makes B8 an automated EOL step",
             "DC_field_chain": f"{r3(100 * bg_always / ch_tot)} % always, {r3(100 * (bg_always + bg_seq) / ch_tot)} % if sequencing allows",
             "cost": "1 resistor + 1 trace + controller GPIO; firmware: a POST step and a run-time plausibility check"},
            {"id": "H3", "name": "EOL per-threshold forcing through 12 tap test pads (+ B8 veto test), observed on J4.1",
             "covers": "comparator die / pins / tap caps present at manufacture", "DC_production": r3(tap / tot),
             "DC_field": 0.0, "cost": "12 test pads (copper) + fixture"},
            {"id": "H4", "name": "EOL LS rail-raise: ground TPS7A4700 3P2V (pin 6) through a fixture pad -> 20.2 V",
             "covers": "every LS span-OV mask incl. dividers", "DC_production_LS": r3(span_ov / tot),
             "DC_production_LS_with_H3": r3(union_ls / tot), "DC_field": 0.0, "cost": "1 test pad"},
            {"id": "H5", "name": "EOL REF25 pad check (2.4975-2.5025 V at 25 C, SNOS455H 5.6 p.7) + OVP ramp to 288 V on a DC "
                                 "source + OCP injection at the Kelvin pads",
             "covers": "U5 assembly opens / wrong part / OCP-OVP network defects at manufacture", "DC_field": 0.0,
             "cost": "1-3 test pads + HV DC source in the EOL station"},
            {"id": "H6", "name": "Field halfref-shift self-test (NOT recommended): U32 CA-IS3720HW -> CA-IS3721HW (1 fwd / 1 rev, "
                                 "pinout unchecked) for SELV -> LS, the ISO6721FB spare reverse channels for LS -> HS-A / HS-B, "
                                 "two switched resistors per monitor",
             "covers": "only faults that mask BOTH thresholds of the shifted group: the wired-AND 'good' node passes the test "
                       "on any one live channel", "DC_field": r3(shift / tot),
             "cost": "isolator swap + 6 switches + 6-9 resistors per board + three islands touched"},
        ],
        "notes": "Front-end coverage shares are of the allocation-B dormant FIT x thresholds of one rail (S47 = V1 rows). "
                 "H3 / H4 / H5 screen defects present at manufacture; the FIT model holds only random field failures, for "
                 "which their coverage is 0 (D59's B13 finding stands)."}
    return out


# ================================================================================================== report
def report(res):
    mon, u5, hk = res["monitors"], res["U5"], res["hooks"]
    L = ["# Stage-47 FMEA re-run (generated by scripts/fmea47.py; do not edit)", ""]
    L += ["## Controls", ""] + [f"- {k}: {v}" for k, v in res["controls"].items() if k != "frozen_bom"] + [""]
    L += ["## Monitor metric (RWL, FIT x rails; chain 13.0 in every row)", "",
          "| case | S47 total | S47 front end | V2 total | V2+F2+v5 total | V2+F2+v5 front end | D59 V1 / V2 / V2+F2+v5 total |", "|---|---:|---:|---:|---:|---:|---|"]
    for c, r in mon["cases"].items():
        d = mon["D59_reference"].get(c)
        if c.startswith("TI estimator FITs at 55"):
            d = mon["D59_reference"]["TI estimator FITs (8 / 8 / 0.1)"]
        dd = f"{d['V1']} / {d['V2']} / {d['V2+F2+v5']}" if d else "- (new)"
        L.append(f"| {c} | {r['S47']['total_RWL']} | {r['S47']['frontend_RWL']} | {r['V2']['total_RWL']} | {r['V2+F2+v5']['total_RWL']} | "
                 f"{r['V2+F2+v5']['frontend_RWL']} | {dd} |")
    L += ["", "Per rail front end (S47):", ""]
    for c, r in mon["cases"].items():
        L.append(f"- {c}: {r['S47']['frontend_per_rail']}; per threshold {r['S47']['per_threshold_FIT']}")
    L += ["", "## Part FIT at temperature", "", "| case | ref | T C | FS base | TI estimator at T | SN 29500 x Arrhenius |", "|---|---|---:|---:|---:|---:|"]
    for tc, tab in mon["part_FIT_at_T"].items():
        for ref_, v in tab.items():
            L.append(f"| {tc} | {ref_} | {v['T_C']} | {v['FS_FIT_base']} | {v['est_FIT']} | {v['SN29500_FIT']} |")
    L += ["", "## C4 reference drift at the 125 C basis (100 K TCR)", "",
          "| basis | drift / masked threshold | worst dormant (V) | to H (V) | to Q (V) | silent vs H |", "|---|---|---:|---:|---:|:-:|"]
    for b, d in (("thresholds 100 K", mon["drift_125C"]["thresholds_100K_rails_60K"]), ("thresholds + neg rail 100 K", mon["drift_125C"]["thresholds_and_neg_rail_100K"])):
        for k, v in d.items():
            L.append(f"| {b} | {k} | {v['worst_dormant_threshold_V']} | {v['vs_H_V']:+.3f} | {v['vs_Q_V']:+.3f} | {'YES' if v['silent_mask_vs_H'] else 'no'} |")
    L += ["", "## U5 (REF25)", "", "```", json.dumps({k: u5[k] for k in ("nominal", "U5_current_min_mA", "open", "drift_high_REF_at_limit", "watchdog", "rates_total_FIT", "dormant_dangerous_FIT")}, indent=1), "```", "",
          "| id | mode | FIT A | FIT B | effect | class | detection today |", "|---|---|---:|---:|---|---|---|"]
    for r in u5["rows"]:
        L.append(f"| {r['id']} | {r['mode']} | {r['FIT_alloc_A']} | {r['FIT_alloc_B']} | {r['effect']} | {r['class']} | {r['detection_today']} |")
    L += ["", "S-O-D: " + "; ".join(f"{s['id']} {s['S']}-{s['O']}-{s['D']} {s['RPN']}" for s in u5["SOD"]), "", "Stability: " + u5["stability"]["verdict"], ""]
    L += ["## B13 hooks", "", "```", json.dumps(hk, indent=1), "```"]
    open(os.path.join(OUT, "fmea47.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L[:60]))


def main():
    res = {"controls": controls()}
    T = temps()
    res["temperatures"] = T
    res["monitors"] = monitors(T)
    res["U5"] = u5_block(T)
    res["hooks"] = hooks(res["monitors"], res["U5"])
    res["monitors"].pop("_rowsB")
    res["failed_controls"] = BAD
    json.dump(res, open(os.path.join(OUT, "fmea47.json"), "w"), indent=1, sort_keys=True)
    report(res)
    print("controls:", BAD if BAD else "all hold")
    sys.exit(1 if BAD else 0)


if __name__ == "__main__":
    main()
