#!/usr/bin/env python3
"""Every external number this FMEA uses, checked against the downloaded document text.

    python3 -I scripts/sources.py   -> results/sources.json, results/sources.md ; exit 1 if any needle is missing

Each entry: (key, doc, regex that must match on the cited PDF page, value(s) used, what it is).  The text files are
pdftotext -layout extractions of the PDFs in dl/ (untrusted data, read only).  Page numbers are PDF page indices
(1-based), which equal the printed page numbers in every TI document used here.  The TI MTBF/FIT estimator pages are
parsed from the saved HTML.
"""
import html, json, os, re, sys
sys.dont_write_bytecode = True
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DL, OUT = os.path.join(ROOT, "dl"), os.path.join(ROOT, "results")

S = [
    # --- TI functional-safety documents (IEC TR 62380 / ISO 26262-11 FIT, die FMD) --------------------------------
    ("TL431_FIT", "snva914", 1, r"Total FIT Rate\s+6\b[\s\S]*Die FIT Rate\s+4\b[\s\S]*Package FIT Rate\s+2\b",
     {"total": 6, "die": 4, "package": 2}, "TL431-Q1/TL432-Q1 FIT, IEC TR 62380 (TI SNVA914 p.1; package not named)"),
    ("TL431_FMD", "snva914", 1, r"open \(HIZ\)\s+25%[\s\S]*Anode short\s+35%[\s\S]*voltage or current\s+40%",
     {"open": 0.25, "short": 0.35, "out_of_spec": 0.40}, "TL431-Q1 die FMD (SNVA914 p.1)"),
    ("TL431_SN29500", "snva914", 1, r"Simple Analog / HF\s+3 FIT\s+45 C", {"ref_FIT": 3, "ref_TJ_C": 45},
     "TL431-Q1 SN 29500-2 reference rate (SNVA914 p.1)"),
    ("LM2901B_FIT", "slca004", 3, r"Total Component FIT Rate\s+10\s+16[\s\S]*Die FIT Rate\s+2\s+2[\s\S]*Package FIT Rate\s+8\s+14",
     {"SOIC14_total": 16, "die": 2, "SOIC14_package": 14}, "LM2901/LM2901B family, SOIC-14 (SLCA004 Table 1-1 p.3); "
     "LM339B and LM2901B share data sheet SLCS006Z and die family; used as the LM339BIDR proxy"),
    ("LM2901B_FMD", "slca004", 4, r"Out open \(HIZ\)\s+15%[\s\S]*saturate high\s+25%[\s\S]*saturate low\s+25%[\s\S]*not in specification\s+30%[\s\S]*any two pins\s+5%",
     {"hiz": 0.15, "sat_high": 0.25, "sat_low": 0.25, "out_of_spec": 0.30, "pin_short": 0.05}, "SLCA004 Table 1-3 p.4"),
    ("LM2901B_PIN_OPEN", "slca004", 6, r"GND\s+12\s+Lowest voltage pin will drive GND pin internally", {},
     "pin-open FMA: GND open is class A; input open 'output may be low or high'; VCC open 'no power' (SLCA004 Table 1-6 p.6)"),
    ("TPS3700Q1_FIT", "slvaem2a", 3, r"Total Component FIT Rate\s+4[\s\S]*Die FIT Rate\s+2[\s\S]*Package FIT Rate\s+2",
     {"total": 4, "die": 2, "package": 2}, "TPS3700-Q1 DDC, IEC TR 62380 (SLVAEM2A Table 2-1 p.3); TPS3701 proxy"),
    ("TPS3700Q1_SN29500", "slvaem2a", 3, r"20 FIT\s+55°C", {"ref_FIT": 20, "ref_TJ_C": 55}, "SLVAEM2A Table 2-2 p.3"),
    ("TPS3700Q1_FMD", "slvaem2a", 5, r"Output HiZ\s+30%[\s\S]*Output stuck low\s+30%[\s\S]*outside of specification\s+40%",
     {"hiz": 0.30, "stuck_low": 0.30, "out_of_spec": 0.40}, "SLVAEM2A Table 3-1 p.5"),
    ("TPS3700Q1_PINOPEN_INB", "slvaem2a", 7, r"overvoltage sense input pin nonfunctional, OUTB indicates no overvoltage\s+INB-\s+4",
     {}, "INB open -> OUTB 'no overvoltage' (masked); INA open -> OUTA 'undervoltage' (announced); VDD/GND open -> "
     "'device unpowered, nonfunctional' (SLVAEM2A Table 4-3 p.7)"),
    ("TPS3700Q1_ASSUMPTION", "slvaem2a", 6, r"VDD = 5 V", {}, "pin FMA assumes all pins in the recommended range and VDD = 5 V "
     "(SLVAEM2A §4 p.6); on this board VDD = P = 17 V, so the INx-to-VDD rows do not transfer"),
    ("TPS3702_FMD", "sffs074", 4, r"output HiZ\s+30%[\s\S]*stuck low\s+30%[\s\S]*outside of specification\s+40%",
     {"hiz": 0.30, "stuck_low": 0.30, "out_of_spec": 0.40}, "TPS3702 DDC (SFFS074 Table 3-1 p.4); same as TPS3700-Q1"),
    ("TPS3703_FIT", "sffs944", 3, r"Total component FIT rate\s+4[\s\S]*Die FIT rate\s+2[\s\S]*Package FIT rate\s+2",
     {"total": 4, "die": 2, "package": 2}, "TPS3703 DSE (SFFS944 Table 2-1 p.3)"),
    ("TPS3703_FMD", "sffs944", 4, r"fails to trip\s+15[\s\S]*false trip\s+15[\s\S]*outside specification \(voltage or time\)\s+65[\s\S]*delay outside specification\s+5",
     {"fail_to_trip": 0.15, "false_trip": 0.15, "trip_out_of_spec": 0.65, "delay": 0.05}, "SFFS944 Table 3-1 p.4 (alternative proxy)"),
    ("FS_NOT_61508", "slvaem2a", 2, r"not developed in\s+accordance with the IEC 61508 or ISO 26262", {},
     "TI FS documents: quality-managed process, not developed to IEC 61508 / ISO 26262 (same statement in each)"),
    ("FS_RANDOM_ONLY", "slvaem2a", 5, r"do not include failures due to misuse or\s+overstress", {},
     "FMDs are random failures only; overstress (the C5 case) is outside them"),
    # --- TPS3701 data sheet (SBVS240C) ---------------------------------------------------------------------------
    ("TPS3701_ABSMAX_IN", "tps3701", 4, r"VINA, VINB\s+–0\.3\s+\+7", {"VIN_abs_max_V": 7.0}, "SBVS240C §6.1 p.4"),
    ("TPS3701_ABSMAX_VDD", "tps3701", 4, r"VDD\s+–0\.3\s+\+40", {"VDD_abs_max_V": 40.0}, "SBVS240C §6.1 p.4"),
    ("TPS3701_NO_IN_CURRENT_RATING", "tps3701", 4, r"Current\s+Output pin current\s+40", {"output_pin_current_mA": 40},
     "the only current abs-max is the output pin; no input-pin current or clamp rating (SBVS240C §6.1 p.4)"),
    ("TPS3701_ROC_IN", "tps3701", 4, r"VINA, VINB\s+Input pin voltage\s+0\s+6\.5", {"VIN_recommended_max_V": 6.5},
     "SBVS240C §6.3 p.4"),
    ("TPS3701_ROC_NOTE", "tps3701", 4, r"2\.4 V or higher and at 125°C continuously for 10 years", {},
     "INx >= 2.4 V at 125 C for 10 years degrades accuracy to 1.5 % (SBVS240C §6.3 note 1 p.4)"),
    ("TPS3701_VIT", "tps3701", 5, r"VIT–\(INA\)\s+INA pin negative input threshold voltage VDD = 1\.8 V to 36 V\s+397\s+400\s+403", {},
     "VIT-(INA) 397/400/403 mV etc. (SBVS240C §6.5 p.5)"),
    ("TPS3701_UVLO", "tps3701", 5, r"When VDD falls below UVLO, OUTA is driven low and OUTB goes to high impedance", {},
     "UVLO 1.3-1.7 V falling; OUTA low below UVLO (SBVS240C §6.5 note 2 p.5)"),
    ("TPS3701_POR", "tps3701", 11, r"both outputs are in a high-impedance state", {"VPOR_max_V": 0.8},
     "VDD < V(POR) (0.8 V max, p.5): both outputs Hi-Z (SBVS240C §7.4.3 p.11)"),
    ("TPS3701_TPD", "tps3701", 6, r"High-to-low propagation delay[\s\S]*9\.9[\s\S]*Low-to-high propagation delay[\s\S]*28\.1[\s\S]*Startup delay[\s\S]*155",
     {"tpd_HL_typ_us": 9.9, "tpd_LH_typ_us": 28.1, "td_start_typ_us": 155},
     "typical only, VDD 24 V, +-10 mV overdrive; no minimum or maximum column entry (SBVS240C §6.6 p.6)"),
    ("TPS3701_TPD_FIG", "tps3701", 8, r"Figure 12\. Propagation Delay vs Temperature", {"HL_us_range_fig12": [5.4, 9.6], "LH_us_range_fig13": [1.75, 2.5]},
     "read off Figures 12-13 (+-200 mV step, -40..125 C, VDD 1.8 and 36 V; typical curves; values are a figure reading)"),
    ("TPS3701_SHARED_REF", "tps3701", 11, r"the other input is connected to the internal reference\. The rising threshold on INB and the falling threshold\s+on INA are designed and trimmed to be equal to the reference voltage",
     {}, "one internal reference serves INA and INB (SBVS240C §7.3.1 p.11)"),
    ("TPS3701_IN_SWING", "tps3701", 11, r"The INA and INB inputs swings from ground to 1\.7 V \(7\.0 V absolute maximum\), regardless of the device supply\s+voltage",
     {}, "SBVS240C §7.3.1 p.11"),
    ("TPS3701_OUT25", "tps3701", 11, r"The TPS3701 outputs can be\s+pulled up to 25 V, independent of the device supply voltage", {},
     "outputs are not clamped to VDD (SBVS240C §7.3.2 p.11)"),
    # --- LM339B data sheet (SLCS006Z) ----------------------------------------------------------------------------
    ("LM339B_ABSMAX_IN", "lm339b", 5, r"Input pins \(IN\+, IN–\)\s+-0\.3\s+38", {"VIN_abs_max_V": 38.0}, "SLCS006Z §6.1 p.5"),
    ("LM339B_ROC", "lm339b", 6, r"Supply voltage: VS = \(V\+\) – \(V–\)\s+2\s+36[\s\S]*Input Voltage Range, VIVR\s+\(V–\) – 0\.1\s+\(V\+\) – 2\.0",
     {"VS_min_V": 2.0}, "SLCS006Z §6.4 p.6"),
    ("LM339B_ONE_INPUT", "lm339b", 7, r"only one input needs to be\s+in the valid common mode range, the other input can go up the maximum VCC level and the comparator provides a proper output state",
     {}, "SLCS006Z p.7 note 1"),
    ("LM339B_TRESP", "lm339b", 12, r"Input overdrive = 5mV, Input step = 100mV\s+1000", {"tresponse_typ_ns": 1000},
     "typical only (SLCS006Z §6.13 p.12)"),
    # --- TPS709 (local 5 V LDO U37-U39, TPS70950DBVR; sliver question) ---------------------------------------------
    ("TPS709_VIN_MIN", "tps709", 4, r"VIN\s+Input voltage\s+2\.7\s+30", {"VIN_min_V": 2.7},
     "recommended input 2.7-30 V: below 2.7 V the local 5 V output is unspecified (SBVS186H §6.3 p.4)"),
    # --- TPS7A47 (test-hook question) ------------------------------------------------------------------------------
    ("TPS7A47_3P2V", "tps7a47", 3, r"3P2V\s+6\s+I", {"pin": 6}, "ANY-OUT 3.2 V pin is pin 6 (SBVS204G p.3); unconnected in f6_bias.ato:64-77"),
    ("TPS7A47_ANYOUT_EQ", "tps7a47", 12, r"VOUT = VREF \+ \(S ANY-OUT Pins to Ground\)", {"VREF_V": 1.4}, "SBVS204G §6.5.1 Eq. 2"),
]


def page_text(doc, page):
    t = open(os.path.join(DL, doc, doc + ".txt"), encoding="utf-8", errors="replace").read().split("\f")
    return t[page - 1]


def estimator(opn):
    s = open(os.path.join(DL, "ti-estimator", f"est_{opn}.html"), encoding="utf-8", errors="replace").read()
    i = s.find('id="resultstable"')
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", s[i:i + 15000], flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "|", t))
    t = re.sub(r"(\|\s*)+", "|", re.sub(r"\s+", " ", t))
    m = re.search(re.escape(opn) + r"\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|", t)
    f = [x.strip() for x in m.groups()]
    # MTBF renders as '1.25x 10|8' (mantissa x 10 ^ exponent): fields shift by one
    return {"MTBF_h": float(f[0].split("x")[0]) * 10 ** int(f[1]), "FIT": float(f[2]), "usage_temp_C": float(f[3]),
            "conf_level_pct": float(f[4]), "Ea_eV": float(f[5]), "test_temp_C": float(f[6]), "test_hours": float(f[7]),
            "sample_size": int(f[8]), "fails": int(f[9])}


def main():
    out, bad = {}, []
    for key, doc, page, rx, val, what in S:
        ok = re.search(rx, page_text(doc, page)) is not None
        if not ok:
            bad.append(key)
        out[key] = {"doc": doc, "page": page, "values": val, "what": what, "verified_in_text": ok}
    est = {opn: estimator(opn) for opn in ("TPS3701DDCR", "TL431AIDBZR", "TL431BIDBZR", "LM339BIDR")}
    for opn, e in est.items():   # independent check: 60 % CL, 0 fails, Arrhenius Ea 0.7 eV 125 -> 55 C
        af = __import__("math").exp(e["Ea_eV"] / 8.617333e-5 * (1 / (e["usage_temp_C"] + 273.15) - 1 / (e["test_temp_C"] + 273.15)))
        e["recomputed_FIT_chi2_60pct_0fail"] = round(0.9163 / (e["sample_size"] * e["test_hours"] * af) * 1e9, 3)
    out["TI_ESTIMATOR"] = {"doc": "ti-estimator", "values": est, "verified_in_text": True,
                           "what": "TI MTBF/FIT estimator (HTOL, 60 % confidence, 0 fails, Ea 0.7 eV, 55 C use). TI: 'failure rates "
                                   "are highly dependent on the number of units tested, therefore, it is not recommended to compare failure rates'."}
    os.makedirs(OUT, exist_ok=True)
    json.dump(out, open(os.path.join(OUT, "sources.json"), "w"), indent=1, sort_keys=True)
    L = ["# Sources checked against the downloaded text (generated by scripts/sources.py)", "",
         "| key | document | page | values | what | found |", "|---|---|---:|---|---|:-:|"]
    for k, v in out.items():
        if k == "TI_ESTIMATOR":
            continue
        L.append(f"| {k} | {v['doc']} | {v['page']} | {json.dumps(v['values'])} | {v['what']} | {'yes' if v['verified_in_text'] else 'NO'} |")
    L += ["", "## TI MTBF/FIT estimator (saved HTML)", "", "| part | FIT | MTBF h | use C | CL % | Ea | test C | h | units | fails | FIT recomputed |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for opn, e in est.items():
        L.append(f"| {opn} | {e['FIT']} | {e['MTBF_h']:.3g} | {e['usage_temp_C']:g} | {e['conf_level_pct']:g} | {e['Ea_eV']} | "
                 f"{e['test_temp_C']:g} | {e['test_hours']:g} | {e['sample_size']} | {e['fails']} | {e['recomputed_FIT_chi2_60pct_0fail']} |")
    open(os.path.join(OUT, "sources.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    print("missing:", bad if bad else "none")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
