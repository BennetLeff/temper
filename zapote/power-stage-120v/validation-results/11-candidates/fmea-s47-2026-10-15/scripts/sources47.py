#!/usr/bin/env python3
"""Stage-47 FMEA: every new external number, checked against the downloaded document text (page, regex).

    python3 -I scripts/sources47.py   -> results/sources47.json, results/sources47.md ; exit 1 if a needle is missing

Documents (untrusted data, read only; pdftotext -layout text, page = PDF page index, 1-based):
  FMEA_DL  = runs-native21/s47/fmea-dl         (this study's downloads: SNOAA49A, TI estimator pages, TI calculator page)
  S47_DL   = runs-native21/s47/dl              (stage-47 lane: SNOS455H LM4050-N)
  S46_DL   = runs-native21/s46/dl/txt          (stage-46 lane: SLVS543S TL431)
  S16_DL   = ../s16copy/dl                     (private copy of runs-native21/s16-fmea-b-dl: SLCS006Z, SLCA004, SNVA914,
                                                SLVAEM2A, SBVS187G TPS3700)
The TI MTBF/FIT estimator pages are parsed from the saved HTML with the same parser as the S16 FMEA's sources.py.
"""
import html, json, math, os, re, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
OUT = os.path.join(ROOT, "results")
W = "/Users/bennet/Desktop/temper/worktrees/runs-native21"
FMEA_DL = os.path.join(W, "s47/fmea-dl")
DOCS = {
    "snoaa49": os.path.join(FMEA_DL, "snoaa49/snoaa49.txt"),
    "snos455h": os.path.join(W, "s47/dl/ti_lm4050n.txt"),
    "slvs543s": os.path.join(W, "s46/dl/txt/tl431.txt"),
    "slcs006z": os.path.join(ROOT, "s16copy/dl/lm339b/lm339b.txt"),
    "slca004": os.path.join(ROOT, "s16copy/dl/slca004/slca004.txt"),
    "snva914": os.path.join(ROOT, "s16copy/dl/snva914/snva914.txt"),
    "slvaem2a": os.path.join(ROOT, "s16copy/dl/slvaem2a/slvaem2a.txt"),
    "sbvs187g": os.path.join(ROOT, "s16copy/dl/tps3700/tps3700.txt"),
}

S = [
    # ---- LM4050-N-Q1 functional-safety document (die family of LM4050AEM3-2.5/NOPB, SNOS455H covers both)
    ("LM4050_FIT", "snoaa49", 3, r"Total component FIT rate\s+4[\s\S]*Die FIT rate\s+3[\s\S]*Package FIT rate\s+1",
     {"total": 4, "die": 3, "package": 1}, "LM4050-N-Q1 SOT-23, IEC TR 62380 / ISO 26262-11 (SNOAA49A Table 2-1 p.3)"),
    ("LM4050_SN29500", "snoaa49", 3, r"20 FIT\s+55°C", {"ref_FIT": 20, "ref_TJ_C": 55}, "SNOAA49A Table 2-2 p.3"),
    ("LM4050_FMD", "snoaa49", 4, r"VR voltage accuracy outside of the specifications\s+40[\s\S]*dynamic impedance specification\s+20[\s\S]*Minimum regulation current exceeds maximum value of the\s+40",
     {"vr_out_of_spec": 0.40, "dyn_impedance": 0.20, "irmin_high": 0.40}, "SNOAA49A Table 3-1 p.4 (no open / short die mode)"),
    ("LM4050_PIN_OPEN", "snoaa49", 6, r"Cathode\s+1\s+The device is unpowered\.[\s\S]*Anode\s+2\s+The output does not regulate and is held low\.",
     {}, "SNOAA49A Table 4-3 p.6: cathode open 'device is unpowered'; anode open 'does not regulate and is held low'"),
    ("LM4050_PIN_ADJ", "snoaa49", 6, r"Cathode\s+1\s+Anode\s+The output does not regulate and cathode pin is held low\.[\s\S]*NC\s+3\s+Cathode\s+Not recommended connection\. Iq can increase\.",
     {}, "SNOAA49A Table 4-4 p.6: K-A short held low (B); NC-K 'Iq can increase' (C)"),
    ("LM4050_PIN_ASSUME", "snoaa49", 5, r"Cathode is connected to supply with 2\.2k\S{1,2} resistor", {},
     "pin FMA assumes the cathode fed through 2.2 k (SNOAA49A p.5); here 5.6 k (R31) with 10-150 k loads"),
    ("LM4050_REVHIST", "snoaa49", 7, r"Changed total component FIT rate from 5 to 6", {},
     "SNOAA49A p.7 revision history says 5 -> 6 FIT, but Table 2-1 p.3 prints 4: internal inconsistency; 4 used, 6 as sensitivity"),
    ("LM4050_STABLE_ANY_C", "snos455h", 1, r"stabilizing capacitor while maintaining\s+[\s\S]*stability with any capacitive load", {},
     "SNOS455H p.1 description: no external stabilising capacitor, 'stability with any capacitive load'"),
    ("LM4050_NO_CAP", "snos455h", 14, r"internally compensated to be stable without the use of an output\s+capacitor", {},
     "SNOS455H 7.3 p.14"),
    ("LM4050_BYPASS_OK", "snos455h", 15, r"If, however, a bypass capacitor is used, the LM4050-N remains stable", {}, "SNOS455H 8.1 p.15"),
    ("LM4050_PIN3", "snos455h", 15, r"parasitic Schottky diode between pin 2 \(−\) and pin 3", {}, "SNOS455H 8.1 p.15"),
    ("LM4050_VR_EXT", "snos455h", 7, r"LM4050AEM3\s+±15", {"VR_tol_ext_mV": 15}, "SNOS455H 5.6 p.7, extended range"),
    ("LM4050_IRMIN", "snos455h", 7, r"TA = TJ = TMIN to TMAX\s+65", {"IRMIN_uA": 65}, "SNOS455H 5.6 p.7"),
    ("LM4050_DVR_DIR", "snos455h", 7, r"1\.2\s*\n\s*TA = TJ = TMIN to TMAX", {"dVR_dIR_mV": 1.2}, "SNOS455H 5.6 p.7, IRMIN..1 mA"),
    ("LM4050_ZR", "snos455h", 7, r"Reverse dynamic impedance\s+IR = 1mA, f = 120Hz, IAC = 0\.1 IR\s+0\.3", {"ZR_typ_ohm": 0.3},
     "SNOS455H 5.6 p.7 (typical only)"),
    # ---- LM2901B (SLCS006Z) and its FS document (direct, no longer a proxy)
    ("LM2901B_TA", "slcs006z", 6, r"Ambient temperature, TA, LM2901B\s+–40\s+125", {"TA_max_C": 125}, "SLCS006Z 6.4 p.6"),
    ("LM2901B_VIVR", "slcs006z", 6, r"Input Voltage Range, VIVR\s+\(V–\) – 0\.1\s+\(V\+\) – 2\.0", {}, "SLCS006Z 6.4 p.6"),
    ("LM2901B_VIO", "slcs006z", 8, r"6\.8 Electrical Characteristics for LM2901B[\s\S]*TA = –40°C to \+125°C\s+–5\.5\s+5\.5", {"VIO_mV": 5.5},
     "SLCS006Z 6.8 p.8"),
    ("LM2901B_VCM", "slcs006z", 8, r"VS = 3 to 36V, TA = –40°C to \+125°C\s+\(V–\)\s+\(V\+\) – 2\.0", {}, "SLCS006Z 6.8 p.8"),
    ("LM2901B_IOH", "slcs006z", 8, r"\(V\+\) = VO = 36V; VID = 1V\s+100", {"IOH_lkg_nA_25C": 100},
     "SLCS006Z 6.8 p.8 (no over-temperature row; leakage only pulls 'good' low)"),
    ("LM2901B_ONEINPUT", "slcs006z", 8, r"only one input needs to be\s+in the valid common mode range", {}, "SLCS006Z 6.8 note 1 p.8"),
    ("LM2901B_FIT", "slca004", 3, r"Total Component FIT Rate\s+10\s+16[\s\S]*Die FIT Rate\s+2\s+2[\s\S]*Package FIT Rate\s+8\s+14",
     {"SOIC14_total": 16, "die": 2, "package": 14}, "SLCA004 Table 1-1 p.3 (names LM2901B: direct)"),
    ("LM2901B_SN29500", "slca004", 3, r"6 FIT\s+55°C", {"ref_FIT": 6, "ref_TJ_C": 55}, "SLCA004 Table 1-2 p.3"),
    ("LM2901B_FMD", "slca004", 4, r"Out open \(HIZ\)\s+15%[\s\S]*saturate high\s+25%[\s\S]*saturate low\s+25%[\s\S]*not in specification\s+30%[\s\S]*any two pins\s+5%",
     {}, "SLCA004 Table 1-3 p.4"),
    ("LM2901B_PINS", "slca004", 5, r"1OUT\s+1\s+14\s+OUT3[\s\S]*VC C\s+3\s+12\s+GND[\s\S]*1IN\+\s+7\s+8\s+3IN−", {},
     "SLCA004 Figure 1-2 p.5 = the LM339B pinout the fault simulation uses"),
    # ---- TL431BQ and TL431-Q1 FS
    ("TL431BQ_VREF", "slvs543s", 14, r"6\.13 Electrical Characteristics, TL431BQ[\s\S]*2483 2495 2507[\s\S]*14\s+34", {"v25": [2.483, 2.507], "videv": 0.034},
     "SLVS543S 6.13 p.14"),
    ("TL431_FIT", "snva914", 1, r"Total FIT Rate\s+6\b[\s\S]*Die FIT Rate\s+4\b[\s\S]*Package FIT Rate\s+2\b", {"total": 6}, "SNVA914 p.1"),
    ("TL431_SN29500", "snva914", 1, r"Simple Analog / HF\s+3 FIT\s+45 C", {"ref_FIT": 3, "ref_TJ_C": 45}, "SNVA914 p.1"),
    ("TPS3700Q1_SN29500", "slvaem2a", 3, r"20 FIT\s+55°C", {"ref_FIT": 20, "ref_TJ_C": 55}, "SLVAEM2A Table 2-2 p.3 (TPS3701 proxy)"),
    # ---- TPS3700 (U14) for the REF25 watchdog hook
    ("TPS3700_INB_FUNC", "sbvs187g", 4, r"INB–\s+4\s+3\s+I\s+divider\. When the voltage at this terminal exceeds the threshold voltage \(VITP\), OUTB is", {},
     "SBVS187G pin functions p.4: INB exceeds VIT+ -> OUTB low (DDC pin 4 INB, 5 VDD, 6 OUTB)"),
    ("TPS3700_ABSMAX_IN", "sbvs187g", 5, r"INA\+, INB–\s+–0\.3\s+7", {"VIN_abs_max_V": 7.0}, "SBVS187G 6.1 p.5"),
    ("TPS3700_VITP", "sbvs187g", 6, r"VIT\+\s+Positive-going input threshold voltage\s+\n?[\s\S]{0,80}?VDD = 18 V\s+396\s+400\s+404", {"VITP_V": [0.396, 0.404]},
     "SBVS187G 6.5 p.6, TJ -40..125 C"),
    ("TPS3700_IINB", "sbvs187g", 6, r"I\(INB–\)\s+Input current \(at the INB– terminal\)\s+VDD = 1\.8 V and 18 V, VI = 0\.1 V\s+–15\s+1\s+15", {"IINB_nA": 15},
     "SBVS187G 6.5 p.6"),
    ("TPS3700_UVLO", "sbvs187g", 6, r"When VDD falls below UVLO, OUTA is driven low and OUTB goes to high impedance", {}, "SBVS187G 6.5 note 3 p.6"),
]


def page_text(doc, page):
    return open(DOCS[doc], encoding="utf-8", errors="replace").read().split("\f")[page - 1]


def estimator(path, opn):
    s = open(path, encoding="utf-8", errors="replace").read()
    i = s.find('id="resultstable"')
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", s[i:i + 15000], flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "|", t))
    t = re.sub(r"(\|\s*)+", "|", re.sub(r"\s+", " ", t))
    m = re.search(re.escape(opn) + r"\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|", t)
    if not m:
        return None
    f = [x.strip() for x in m.groups()]
    return {"MTBF_h": float(f[0].split("x")[0]) * 10 ** int(f[1]), "FIT": float(f[2]), "usage_temp_C": float(f[3]),
            "conf_level_pct": float(f[4]), "Ea_eV": float(f[5]), "test_temp_C": float(f[6]), "test_hours": float(f[7]),
            "sample_size": int(f[8]), "fails": int(f[9])}


KB = 8.617333e-5


def af(t_from_c, t_to_c, ea=0.7):
    return math.exp(ea / KB * (1 / (t_from_c + 273.15) - 1 / (t_to_c + 273.15)))


def main():
    out, bad = {}, []
    for key, doc, page, rx, val, what in S:
        ok = re.search(rx, page_text(doc, page)) is not None
        if not ok:
            bad.append(key)
        out[key] = {"doc": doc, "page": page, "values": val, "what": what, "verified_in_text": ok}
    est = {}
    for opn, fn in (("TL431BQDBZR", "est_TL431BQDBZR.html"), ("LM2901BIDR", "est_LM2901BIDR.html"),
                    ("LM4040A25IDBZR", "est_LM4040A25IDBZR.html"), ("LM4050AEM3X-2.5/NOPB", "est_LM4050AEM3X-2.5_NOPB.html")):
        e = estimator(os.path.join(FMEA_DL, "ti-estimator", fn), opn)
        if e is None:
            bad.append("ESTIMATOR " + opn)
            continue
        a = af(e["usage_temp_C"], e["test_temp_C"], e["Ea_eV"])
        e["recomputed_FIT_chi2_60pct_0fail"] = round(0.9163 / (e["sample_size"] * e["test_hours"] * a) * 1e9, 3)
        est[opn] = e
    # LM4050AEM3-2.5/NOPB itself: the estimator serves an empty table (saved page) and an empty .xlsx
    e0 = estimator(os.path.join(FMEA_DL, "ti-estimator", "est_LM4050AEM3-2.5_NOPB.html"), "LM4050AEM3-2.5/NOPB")
    out["TI_ESTIMATOR"] = {"doc": "ti-estimator (fetched 2026-10-15/16)", "values": est, "verified_in_text": True,
                           "LM4050AEM3-2.5/NOPB_row_served": e0 is not None,
                           "what": "HTOL, 60 % CL, 0 fails, Ea 0.7 eV, 55 C use. LM4050AEM3-2.5/NOPB has no row; its 3k-reel "
                                   "twin LM4050AEM3X-2.5/NOPB (same die, package, marking) is used."}
    # TI 'Temperature change FIT' calculator example: 16.7 FIT at 55 C -> 69.2 at 75 C with 0.7 eV (Arrhenius)
    calc = open(os.path.join(FMEA_DL, "ti-estimator", "temperature-change-FIT.html"), encoding="utf-8", errors="replace").read()
    ok = re.search(r"FIT of 16\.7 at a reference temperature of 55C, you can predict FIT at application temperature of 75C to be 69\.2 with 0\.7Ea", calc) is not None
    got = round(16.7 * af(55, 75), 1)
    out["TI_ARRHENIUS"] = {"doc": "ti.com/support-quality/reliability/temperature-change-FIT.html", "values": {"example_reproduced": got},
                           "verified_in_text": ok and abs(got - 69.2) < 0.05,
                           "what": "TI's temperature-change FIT calculator (Arrhenius, Ea 0.7 eV); its own example reproduced"}
    if not out["TI_ARRHENIUS"]["verified_in_text"]:
        bad.append("TI_ARRHENIUS")
    os.makedirs(OUT, exist_ok=True)
    json.dump(out, open(os.path.join(OUT, "sources47.json"), "w"), indent=1, sort_keys=True)
    L = ["# Sources checked against the downloaded text (generated by scripts/sources47.py)", "",
         "| key | document | page | values | what | found |", "|---|---|---:|---|---|:-:|"]
    for k, v in out.items():
        if k in ("TI_ESTIMATOR",):
            continue
        L.append(f"| {k} | {v['doc']} | {v.get('page', '')} | {json.dumps(v['values'])} | {v['what']} | {'yes' if v['verified_in_text'] else 'NO'} |")
    L += ["", "## TI MTBF/FIT estimator (saved HTML, fmea-dl/ti-estimator)", "",
          "| part | FIT | MTBF h | use C | CL % | Ea | test C | h | units | fails | FIT recomputed |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for opn, e in est.items():
        L.append(f"| {opn} | {e['FIT']} | {e['MTBF_h']:.3g} | {e['usage_temp_C']:g} | {e['conf_level_pct']:g} | {e['Ea_eV']} | "
                 f"{e['test_temp_C']:g} | {e['test_hours']:g} | {e['sample_size']} | {e['fails']} | {e['recomputed_FIT_chi2_60pct_0fail']} |")
    L.append(f"\nLM4050AEM3-2.5/NOPB row served by the estimator: {e0 is not None} (empty table and empty .xlsx, 2026-10-15).")
    open(os.path.join(OUT, "sources47.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    print("missing:", bad if bad else "none")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
