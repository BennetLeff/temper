#!/usr/bin/env python3
"""F6 / AOE-29: CMTI table for every isolation crossing of the native-21 power stage.

Rerun:  python3 -I validation-results/06-controller-interface/cmti/cmti_table.py
Writes cmti.csv next to this file, prints PASS / FAIL / OPEN per row.

Every number is either (a) quoted from a cited datasheet / repo document (DATA below,
with page + URL) or (b) computed here.  The crossing list is cross-checked against
elec/src/*.ato (instance counts and the time-filter R/C are read from the source).

Verdict rules (RESOLUTION-PLAN F6):
  GATE     upset can produce a gate command  -> PASS iff CMTI >= 1.5 x dv/dt_hard
  FILTERED upset reaches only a time-filtered line (tau >= 10 us) -> PASS on the filter
  BIAS     isolated bias module (upset = regulation upset, not logic) -> ratio rule, plus
           injected C*dv/dt reported
  OPEN     no datasheet number, or the consumer is off-board / not in this repo, so the
           rule cannot be closed from this repository
"""
import csv
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[2]                      # .../zapote/power-stage-120v
SRC = PS / "elec" / "src"

MARGIN = 1.5                              # F6 pass margin
DVDT_HARD = 95.0                          # V/ns, S4/S5 hard edges (ALT-BIAS.md R10; ECO.md:72)
DVDT_ZVS = 10.0                           # V/ns, ZVS edges        (ALT-BIAS.md R10)
V_SW_PEAK = 520.0                         # V, <=520 V transient target (ALT-BIAS.md R9)
# 1 V/ns == 1 kV/us, so a "V/ns" CMTI and a "kV/us" CMTI compare directly.

DV_SRC = ("ALT-BIAS.md R10 (08-manufacturing-package/native-21/sourcing/alt-circuits-2026-10-09/"
          "ALT-BIAS.md:49): 10 V/ns ZVS, up to 95 V/ns hard edges S4/S5; native-21/ECO.md:72; "
          "01-switching-parasitics/FINDINGS.md F2/F11 (S4 hard turn-on, S5 burst-start edge)")

URL_UCC = "https://www.ti.com/lit/ds/symlink/ucc21550.pdf"
URL_2EDR = "https://www.infineon.com/assets/row/public/documents/24/49/infineon-eicedriver-2edr8259h-2edrx259x-2edrx258x-datasheet-en.pdf"
# Stage 29 (DECISIONS 31): the legs carry the Infineon 2EDR8259X. Table 23: static |CM_H| = |CM_L| >= 150 V/ns at VCM = 1500 V
# (specified by characterisation, not production tested); CIO 2 pF (Table 24). 8.2 ohm gates keep the as-built edge (c25-driver).
DRIVER_DATA = {
    "2EDR8259XXUMA1": dict(cmti=150.0, cio=2.0, url=URL_2EDR,
                           dyn="|CM_static,H| = |CM_static,L| >= 150 V/ns, VCM = 1500 V (characterisation, not production tested)",
                           cite="Infineon 2EDR8259H/2EDRx259X datasheet Rev 1.7 (2026-04-09) Table 23 p.17 (static CMTI min 150 V/ns, "
                                "VCM 1500 V); Table 24 CIO 2 pF; 8.2 ohm gate resistors hold the as-built edge (11-candidates/c25-driver)"),
    "UCC21550BDWKR": dict(cmti=125.0, cio=1.2, url=URL_UCC,
                          dyn="|CMH|=|CML|=125 V/ns min, VCM=1500 V (single figure; no separate static/dynamic)",
                          cite="UCC21550 SLUSE89C (Aug 2024) p.10 Table 5.9 Switching Characteristics rows |CMH| and |CML| (min 125 V/ns, VCM = 1500 V); p.1 Features/Description; CIO ~1.2 pF p.7 Table 5.6"),
}
URL_ISO = "https://www.ti.com/lit/ds/symlink/iso7710.pdf"
URL_AMC = "https://www.ti.com/lit/ds/symlink/amc1311.pdf"
URL_VOL = "https://www.vishay.com/docs/82401/vol628a.pdf"
URL_REC = "https://recom-power.com/pdf/Econoline/R24C2T25_R.pdf"
URL_CST = "https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf"
URL_LVC = "https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf"

# SN74LVC1G17 (SCES351Y, Oct 2025) p.6 Table 5.5 'DC Limit Changes': VT+ at VCC = 3 V,
# -40..125 C: min 1.48 V, max 1.92 V.  Used at 3.3 V (V3V3) -> the 3 V row is the conservative
# (lowest) bound because VT+ rises with VCC.
VT_PLUS_MIN_3V = 1.48
V3V3 = 3.3


def read(name):
    return (SRC / name).read_text()


def parse_value(text, name, unit_map):
    m = re.search(rf"^\s*{re.escape(name)}\.value\s*=\s*([0-9.]+)\s*([a-zA-Z]+)", text, re.M)
    if not m:
        raise SystemExit(f"cannot find {name}.value in .ato source")
    return float(m.group(1)) * unit_map[m.group(2)]


def schematic_facts():
    """Everything read from the .ato source, so the table cannot drift from the design."""
    top, bias = read("power_stage_120v.ato"), read("f6_bias.ato")
    parts = read("parts.ato") + read("f6_parts.ato")
    allsrc = top + bias
    n = lambda cls: len(re.findall(rf"=\s*new\s+{cls}\b", allsrc))
    n_highbias = n("HighBias")
    facts = {
        "bridge_legs": n("BridgeLeg"),
        "drivers_in_leg": len(re.findall(r"driver\s*=\s*new\s+(?:UCC21550BDWK|Driver2EDR8259X)\b", top)),
        "iso7710_rail_monitors": n("RailMonitor") + n_highbias * 0,   # RailMonitor sites (see below)
        "highbias": n_highbias,
        "iso7710_bus_fault": len(re.findall(r"u_iso\s*=\s*new\s+Iso7710", top)),
        "iso7710_in_railmonitor": len(re.findall(r"=\s*new\s+Iso7710", bias)),
        "amc1311": n("Amc1311"),
        "line_opto": len(re.findall(r"=\s*new\s+LineOpto\b", bias)),
        "ct": n("CST3015_200E") + n("CST3015_100E"),   # stage 20: the 1:200 CT
        "ps1": n("Irm20_15"),
        "ps2": n("HotSupply24"),
        "bias_opto_unused": n("BiasOpto"),
    }
    # RailMonitor instances: monitor_ls (top) + one inside each HighBias.
    facts["rail_monitors"] = len(re.findall(r"=\s*new\s+RailMonitor\b", top)) + \
        n_highbias * len(re.findall(r"=\s*new\s+RailMonitor\b", bias))
    facts["bias_modules"] = n_highbias * len(re.findall(r"=\s*new\s+IsoBiasModule\b", bias))
    um = {"ohm": 1.0, "kohm": 1e3, "nF": 1e-9, "uF": 1e-6, "pF": 1e-12, "nf": 1e-9}
    facts["filt_R"] = parse_value(top, "r_bias_flt", um)
    facts["filt_C"] = parse_value(top, "c_bias_flt", um)
    facts["ct_R"] = parse_value(top, "r_ct_burden", um)
    facts["ct_C"] = parse_value(top, "c_ct_burden", um)
    facts["filt_buf_mpn"] = re.search(r'component Hot5SchmittBuffer:.*?mpn = "([^"]+)"', parts, re.S).group(1)
    facts["amc_mpn"] = re.search(r'component Amc1311:.*?mpn = "([^"]+)"', parts, re.S).group(1)
    # the driver actually instantiated in the leg (stage 29: Driver2EDR8259X), and its MPN
    drv_comp = re.search(r"driver\s*=\s*new\s+(\w+)", top).group(1)
    facts["ucc_mpn"] = re.search(rf'component {drv_comp}:.*?mpn = "([^"]+)"', parts, re.S).group(1)
    facts["iso_mpn"] = re.search(r'component Iso7710:.*?mpn = "([^"]+)"', parts, re.S).group(1)
    facts["mod_mpn"] = re.search(r'component IsoBiasModule:.*?mpn = "([^"]+)"', parts, re.S).group(1)
    facts["opto_mpn"] = re.search(r'component LineOpto:.*?mpn = "([^"]+)"', parts, re.S).group(1)
    facts["ct_mpn"] = re.search(r'component CST3015_[0-9]+E:.*?mpn = "([^"]+)"', parts, re.S).group(1)
    # Completeness scan: any MPN in the source that looks like an isolator / isolated supply
    # must be one of the rows below (guards against a crossing being added without a row).
    watch = re.compile(r"ISO\d|UCC2|AMC\d|VOL?6|CST\d|IRM-|R24C|ADuM|Si8\d|TLP|PC817|HCPL|ACPL|SN6507|MGJ|UCC14", re.I)
    facts["watch_mpns"] = sorted({m for m in re.findall(r'mpn = "([^"]+)"', parts) if watch.search(m)})
    return facts


def rc_rejection(R, C, vt, v):
    """Single-pole RC driven by a step of height v: longest pulse that stays below vt."""
    tau = R * C
    t_max = -tau * math.log(1.0 - vt / v)
    v_at = lambda tg: v * (1.0 - math.exp(-tg / tau))
    return tau, t_max, v_at


def build_rows(f):
    R, C = f["filt_R"], f["filt_C"]
    tau, tg_max, v_at = rc_rejection(R, C, VT_PLUS_MIN_3V, V3V3)
    filt_txt = (f"R_BIAS_FLT {R/1e3:g}k x C_BIAS_FLT {C*1e9:g}nF, tau={tau*1e6:.1f}us; rejects any glitch "
                f"<{tg_max*1e6:.2f}us at SN74LVC1G17 VT+min {VT_PLUS_MIN_3V} V (SCES351Y p.6); "
                f"1us glitch reaches {v_at(1e-6):.2f} V, 5us {v_at(5e-6):.2f} V")
    rows = []

    def row(**k):
        k.setdefault("cmti_dyn", "not specified")
        k.setdefault("cio_pf", None)
        k.setdefault("filter", "none")
        rows.append(k)

    # ------------------------------------------------------------------ gate drivers
    for ref, leg, node in (("U1", "A", "SW_A"), ("U2", "B", "SW_B")):
        row(ref=ref, mpn=f["ucc_mpn"], role=f"Gate driver, leg {leg} (INA/INB/DIS -> OUTA/OUTB)", cls="GATE",
            node=f"{node} (channel A VSS rides the switch node; channel B on N_LS/LEG_RET)",
            cmti_static=DRIVER_DATA[f["ucc_mpn"]]["cmti"], cmti_dyn=DRIVER_DATA[f["ucc_mpn"]]["dyn"],
            cio_pf=DRIVER_DATA[f["ucc_mpn"]]["cio"],
            cite=DRIVER_DATA[f["ucc_mpn"]]["cite"],
            url=DRIVER_DATA[f["ucc_mpn"]]["url"],
            effect="FALSE GATE COMMAND: a barrier upset on INA/INB is downstream of the dead-time logic, so it can turn on a "
                   "FET (the DT interlock sits on the input side; this reasoning is mine, not a datasheet claim). DIS upset: "
                   "outputs forced low (off), the safe direction.")
    # ------------------------------------------------------------------ rail monitors (filtered)
    for ref, nm, node in (("U32", "LS rail monitor", "N_LS/LEG_RET (not a switch node; 95 V/ns applied as a conservative bound)"),
                          ("U33", "HS-A rail monitor", "SW_A"), ("U34", "HS-B rail monitor", "SW_B")):
        row(ref=ref, mpn=f["iso_mpn"], role=f"Digital isolator, {nm} (HOT5 side 1 -> V3V3 side 2)", cls="FILTERED",
            node=node, cmti_static=85.0,
            cmti_dyn="85 kV/us min, 100 typ, VCM=1200 V (single figure); ISO7710 default output HIGH = 'bad'",
            cio_pf=0.4,
            cite="ISO7710 SLLSER9E (Dec 2024) p.11 Table 5.9 (5-V supply), p.12 Table 5.11 (3.3-V supply): CMTI min 85 / typ 100 kV/us, VCM = 1200 V; CIO ~0.4 pF p.8",
            url=URL_ISO, filter=filt_txt, tau=tau, tg_max=tg_max,
            effect="Rail-monitor OUT -> OR3 (SN74LVC1G332) BIAS_BAD_RAW -> R_BIAS_FLT/C_BIAS_FLT -> Schmitt U-buffer -> BIAS_BAD -> "
                   "DisOr (SN74LVC1G32) -> UCC21550 DIS of both legs. A glitch HIGH disables the drivers (off = safe nuisance "
                   "trip); a glitch LOW only delays a real rail-fault flag (rail faults are ms-scale, reservoirs).")
    # ------------------------------------------------------------------ bus fault isolator
    row(ref="U9", mpn=f["iso_mpn"], role="Digital isolator, BUS_FAULT (OCP/OVP/HOT5-OK NAND -> J4 pin 10)", cls="OPEN",
        node="OCP_KELVIN_P/LEG_RET (not a switch node; 95 V/ns applied as a conservative bound)", cmti_static=85.0,
        cmti_dyn="85 kV/us min, 100 typ, VCM=1200 V", cio_pf=0.4,
        cite="ISO7710 SLLSER9E p.11/12 (as above)", url=URL_ISO, filter="none on the power board (BUS_FAULT_ISO goes straight to J4)",
        effect="Fault line to the controller. High = fault: a false HIGH is a nuisance trip (safe direction); a false LOW "
               "during a real fault lasts only the glitch (fault persists). No gate command on the power board, but whether the "
               "controller debounces BUS_FAULT is not in this repo (06 README: no controller counterpart) -> OPEN.",
        open_reason="consumer (controller) filter not in repo")
    # ------------------------------------------------------------------ AMC1311
    row(ref="U4", mpn=f["amc_mpn"], role="Isolated amplifier, bus-voltage sense (VINP -> VOUTP/N -> VBUS_P/N on J4)", cls="OPEN",
        node="OCP_KELVIN_P/LEG_RET (not a switch node; 95 V/ns applied as a conservative bound)", cmti_static=100.0,
        cmti_dyn="AMC1311B: 100 kV/us min, 150 typ (AMC1311 non-B: 15 min, 30 typ)", cio_pf=1.5,
        cite="AMC1311 SBAS786C (Jun 2022) p.10 Table 7.9 CMTI row (AMC1311B 100 min / 150 typ) and p.4 Table 5 (100 kV/us min B-grade); the BOM MPN is the B grade; revision note p.2: 'changed CMTI from 75 min'",
        url=URL_AMC, filter="none on the board (VOUTP/N straight to J4; ADC filter is on the controller)",
        effect="MEASUREMENT upset (a spurious VBUS sample), not a gate command; the OVP comparator is HOT-side and independent. "
               "Whether firmware acts on a single VBUS sample is outside this repo -> OPEN.",
        open_reason="consumer (controller ADC/firmware) not in repo")
    # ------------------------------------------------------------------ line ZC opto
    row(ref="U36", mpn=f["opto_mpn"], role="Optocoupler, line zero-cross (L_FILT/N_FILT -> LINE_ZC)", cls="OPEN",
        node="mains L/N side (not a switch node)", cmti_static=None,
        cmti_dyn="NO numeric CMTI in datasheet (only the feature bullet 'High common mode transient immunity')", cio_pf=None,
        cite="VOL628A Vishay doc 82401 Rev. 1.9 (10-Feb-2023) p.1 features list; no CMTI row in the characteristics tables (pp.1-9 searched)",
        url=URL_VOL, filter="33k pull-up + SN74LVC1G17 Schmitt, no deliberate RC",
        effect="A false edge = a false zero-cross timestamp for burst/line-synchronous timing in firmware; not a gate command "
               "by itself (PWM is generated by the controller). No datasheet number -> cannot compute a ratio.",
        open_reason="no datasheet CMTI number")
    # ------------------------------------------------------------------ bias modules
    for ref, hs, node in (("U41", "HS-A", "SW_A"), ("U42", "HS-B", "SW_B")):
        row(ref=ref, mpn=f["mod_mpn"], role=f"Isolated gate-bias module, {hs} (V24_RAW/N_LS -> 17 V P-N)", cls="BIAS",
            node=node, cmti_static=150.0,
            cmti_dyn="+/-150 V/ns (RECOM lists one value in a Min/Typ/Max table; the column is not recoverable from the PDF text, so it is treated as the rating)",
            cio_pf=3.5,
            cite="RECOM R24C2T25/R Rev.1-2024 p.7 'Common Mode Transient Immunity +/-150 V/ns'; p.8 'Isolation Capacitance input to output 3.5 pF'; also ALT-BIAS.md:144,160 (1.58x)",
            url=URL_REC, filter="reservoir + rail monitor (above); regulation ms-scale",
            effect="Not a logic path: an upset is a regulation / injected-charge event (Cio x dv/dt into the LS split), held by the "
                   "2x10uF+220uF reservoirs; ALT-BIAS.md section 2 runs 95 V/ns at 3.5 pF (369 mA / 0.98 nC / 192 mV at LS VSS).")
    # ------------------------------------------------------------------ transformer / mains supplies
    row(ref="T1", mpn=f["ct_mpn"], role="Current transformer, tank CT (P1 on SW_A -> CT_S1/S2 -> OCP comparators -> BUS_FAULT)", cls="OPEN",
        node="SW_A (primary P1 = SW_A)", cmti_static=None,
        cmti_dyn="transformer: no CMTI spec; interwinding capacitance NOT given", cio_pf=None,
        cite="Coilcraft CST3015 Doc 1608-1 rev 09/08/25: '5000 Vrms, one minute isolation (hipot)'; no interwinding-capacitance entry",
        url=URL_CST, filter="1.5 ohm burden + 100 nF across S1-S2; 1k series + BAS116H clamps",
        effect="Capacitive injection from SW_A into the secondary could in principle trip the ~70 A OCP comparators "
               "(fail-safe: shuts down); break-even Cww is computed in the derived block (about 190 pF, simple charge model).",
        open_reason="Cww not specified")
    row(ref="PS1", mpn="IRM-20-15", role="AC-DC module, SELV 15 V (mains -> SELV)", cls="OPEN",
        node="mains L/N (not a switch node)", cmti_static=None, cmti_dyn="no CMTI / Cio in the repo's cited material",
        cite="Mean Well IRM-20 spec (native-21/ECO.md:185); no CMTI figure", url="https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF",
        effect="Supply, not a signal path; sees mains common mode, not the bridge switch node.", open_reason="not on a switch node; no CMTI spec")
    row(ref="PS2", mpn="IRM-20-24", role="AC-DC module, HOT gate bias 24 V (mains -> N_LS)", cls="OPEN",
        node="mains L/N (not a switch node)", cmti_static=None, cmti_dyn="no CMTI / Cio in the repo's cited material",
        cite="Mean Well IRM-20 spec (native-21/ECO.md:185); no CMTI figure", url="https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF",
        effect="Supply, not a signal path; secondary is N_LS (HOT, LEG_RET), primary mains.", open_reason="not on a switch node; no CMTI spec")
    # ------------------------------------------------------------------ control
    row(ref="CTRL", mpn="HYPOTHETICAL-50kV/us", role="CONTROL: hypothetical 50 kV/us part on a gate path", cls="GATE",
        node="SW_A", cmti_static=50.0, cmti_dyn="hypothetical", cite="none (control row; must FAIL)", url="-",
        effect="Self-test of the verdict logic: must print FAIL.")
    return rows, (tau, tg_max, v_at)


def judge(r):
    c = r["cmti_static"]
    r["dvdt_hard"], r["dvdt_zvs"] = DVDT_HARD, DVDT_ZVS
    r["ratio_hard"] = None if c is None else c / DVDT_HARD
    r["ratio_zvs"] = None if c is None else c / DVDT_ZVS
    cls = r["cls"]
    if c is None:
        r["verdict"], r["why"] = "OPEN", r.get("open_reason", "no number")
    elif cls == "GATE":
        ok = c >= MARGIN * DVDT_HARD
        r["verdict"] = "PASS" if ok else "FAIL"
        r["why"] = (f"{c:g} >= {MARGIN}x{DVDT_HARD:g}={MARGIN*DVDT_HARD:g}" if ok else
                    f"{c:g} < {MARGIN}x{DVDT_HARD:g}={MARGIN*DVDT_HARD:g} (short by {MARGIN*DVDT_HARD-c:.1f} kV/us)")
    elif cls == "FILTERED":
        ok = r["tau"] >= 10e-6 - 1e-12
        r["verdict"] = "PASS" if ok else "FAIL"
        r["why"] = (f"time-filtered, tau={r['tau']*1e6:.1f}us>=10us (raw ratio {r['ratio_hard']:.2f}x<1.5 is covered by the filter; "
                    f"valid only while an upset lasts < {r['tg_max']*1e6:.2f}us - bench item)")
    elif cls == "BIAS":
        ok = c >= MARGIN * DVDT_HARD
        r["verdict"] = "PASS" if ok else "FAIL"
        r["why"] = f"{c:g} >= {MARGIN*DVDT_HARD:g}" if ok else f"{c:g} < {MARGIN*DVDT_HARD:g}"
    else:
        r["verdict"], r["why"] = "OPEN", r.get("open_reason", "consumer not in this repo")
    # injected charge: Cio * dv/dt (peak current) and Cio * V_SW (charge), simple and unfiltered
    if r.get("cio_pf"):
        cio = r["cio_pf"] * 1e-12
        r["i_inj_hard_mA"] = cio * DVDT_HARD * 1e9 * 1e3
        r["q_inj_nC"] = cio * V_SW_PEAK * 1e9
    else:
        r["i_inj_hard_mA"] = r["q_inj_nC"] = None
    return r


def main():
    f = schematic_facts()
    print("== schematic enumeration (read from elec/src/*.ato) ==")
    expect = {"drivers_in_leg": 1, "bridge_legs": 2, "rail_monitors": 3, "iso7710_bus_fault": 1,
              "amc1311": 1, "line_opto": 1, "bias_modules": 2, "ct": 1, "ps1": 1, "ps2": 1}
    bad = False
    for k, v in expect.items():
        ok = f[k] == v
        bad |= not ok
        print(f"  {k:20s} found {f[k]}  expected {v}  {'ok' if ok else 'MISMATCH'}")
    n_drv = f["drivers_in_leg"] * f["bridge_legs"]
    n_iso = f["rail_monitors"] + f["iso7710_bus_fault"]
    print(f"  => UCC21550 x{n_drv}, ISO7710 x{n_iso} (3 rail monitors + 1 bus fault), AMC1311 x1, VOL628A x1, "
          f"R24C2T25 x{f['bias_modules']}, CST3015 x1, IRM x2; BiasOpto (VO617A) defined but instantiated {f['bias_opto_unused']}x")
    print("  watch-listed MPNs defined in parts: " + ", ".join(f["watch_mpns"]))
    rows, (tau, tg_max, v_at) = build_rows(f)
    listed = {r["mpn"] for r in rows}
    unlisted = [m for m in f["watch_mpns"] if m not in listed and m not in ("IRM-05-15", "VO617A-3X017T")]
    # defined-but-unused parts are allowed; anything else unlisted is a missing row
    for m in unlisted:
        print(f"  UNLISTED isolator-like MPN: {m}")
        bad = True
    rows = [judge(r) for r in rows]

    print("\n== CMTI table (hard = %g V/ns, ZVS = %g V/ns, pass = CMTI >= %.1fx hard = %.1f kV/us) ==" % (DVDT_HARD, DVDT_ZVS, MARGIN, MARGIN * DVDT_HARD))
    print(f"{'ref':5s} {'MPN':22s} {'class':8s} {'CMTI':>6s} {'hard x':>7s} {'ZVS x':>6s}  {'verdict':7s} reason")
    for r in rows:
        c = "n/a" if r["cmti_static"] is None else f"{r['cmti_static']:g}"
        rh = "n/a" if r["ratio_hard"] is None else f"{r['ratio_hard']:.2f}"
        rz = "n/a" if r["ratio_zvs"] is None else f"{r['ratio_zvs']:.1f}"
        print(f"{r['ref']:5s} {r['mpn'][:22]:22s} {r['cls']:8s} {c:>6s} {rh:>7s} {rz:>6s}  {r['verdict']:7s} {r['why']}")

    ctrl = [r for r in rows if r["ref"] == "CTRL"][0]
    print(f"\ncontrol row (50 kV/us on a gate path) -> {ctrl['verdict']} (must be FAIL)")
    if ctrl["verdict"] != "FAIL":
        print("CONTROL ROW DID NOT FAIL: verdict logic broken")
        return 2

    # ------------------------------------------------------------- derived numbers
    ucc = 125.0
    print("\n== derived ==")
    print(f"UCC21550 allowed dv/dt at {MARGIN}x margin = {ucc/MARGIN:.1f} V/ns -> the modelled 95 V/ns hard edge must drop "
          f"{(1-(ucc/MARGIN)/DVDT_HARD)*100:.1f}% (to <= {ucc/MARGIN:.1f}) or be shown by bench measurement to be below it")
    print(f"UCC21550 at ZVS: {ucc/DVDT_ZVS:.1f}x (PASS); hard: {ucc/DVDT_HARD:.2f}x (FAIL, bare datasheet ratio > 1 so no upset is "
          f"*predicted* - the rating is simply not demonstrated with margin)")
    print(f"hard-edge duration for a {V_SW_PEAK:g} V swing at {DVDT_HARD:g} V/ns = {V_SW_PEAK/DVDT_HARD:.2f} ns; at {DVDT_ZVS:g} V/ns = {V_SW_PEAK/DVDT_ZVS:.0f} ns")
    print(f"monitor filter: tau = {tau*1e6:.2f} us; longest rejected glitch = {tg_max*1e6:.2f} us "
          f"(VT+min {VT_PLUS_MIN_3V} V of {V3V3} V); glitch 0.1/1/5/10 us -> "
          + " / ".join(f"{v_at(t*1e-6):.2f} V" for t in (0.1, 1, 5, 10)))
    print("injected current/charge across each barrier (Cio x 95 V/ns; Cio x 520 V), simple C*dv/dt:")
    for r in rows:
        if r["i_inj_hard_mA"] is not None and r["ref"] != "CTRL":
            print(f"  {r['ref']:4s} Cio {r['cio_pf']:g} pF -> {r['i_inj_hard_mA']:.0f} mA peak, {r['q_inj_nC']:.2f} nC")
    n_ct = int(re.search(r"CST3015-(\d+)E", f["ct_mpn"]).group(1))   # stage 20: 1:200 (CST3015-200ED)
    i_sec = 64.55 / n_ct                        # A; OCP trip-band minimum / CT turns
    v_trip = i_sec * f["ct_R"]
    q_per_pf = 1e-12 * V_SW_PEAK                # C per pF of Cww for a full 520 V swing
    dv_per_pf = q_per_pf / f["ct_C"]
    print(f"CST3015: OCP trip-band min 64.55 A (power_stage_120v.ato comment) / {n_ct} turns = {i_sec*1e3:.0f} mA x burden "
          f"{f['ct_R']:g} ohm = {v_trip:.3f} V trip level; burden C {f['ct_C']*1e9:g} nF, burden RC = {f['ct_R']*f['ct_C']*1e9:.0f} ns "
          f"(>> {V_SW_PEAK/DVDT_HARD:.1f} ns edge, so the edge is charge-dominated)")
    print(f"  each pF of unspecified Cww moves the burden node by {dv_per_pf*1e3:.2f} mV (Q = Cww x {V_SW_PEAK:g} V into the burden C); "
          f"break-even Cww = {v_trip/dv_per_pf:.0f} pF (datasheet gives no Cww; vendor query / bench item)")

    # ------------------------------------------------------------- CSV
    cols = ["ref", "mpn", "role", "cls", "node", "cmti_min_kV_per_us", "cmti_note", "cio_pF", "datasheet_cite", "url",
            "dvdt_hard_V_per_ns", "dvdt_zvs_V_per_ns", "ratio_hard", "ratio_zvs", "required_hard", "verdict", "why",
            "i_inj_hard_mA", "q_inj_nC", "filter", "upset_effect", "dvdt_source"]
    with open(HERE / "cmti.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            fmt = lambda x, p=3: "" if x is None else (f"{x:.{p}f}" if isinstance(x, float) else x)
            w.writerow([r["ref"], r["mpn"], r["role"], r["cls"], r["node"], fmt(r["cmti_static"], 1), r["cmti_dyn"],
                        fmt(r["cio_pf"], 2), r["cite"], r["url"], r["dvdt_hard"], r["dvdt_zvs"], fmt(r["ratio_hard"]),
                        fmt(r["ratio_zvs"], 2), MARGIN * DVDT_HARD, r["verdict"], r["why"], fmt(r["i_inj_hard_mA"], 1),
                        fmt(r["q_inj_nC"], 3), r["filter"], r["effect"], DV_SRC])
    real = [r for r in rows if r["ref"] != "CTRL"]
    n = lambda v: sum(1 for r in real if r["verdict"] == v)
    print(f"\nSUMMARY: {n('PASS')} PASS, {n('FAIL')} FAIL, {n('OPEN')} OPEN (control excluded); wrote {HERE/'cmti.csv'}")
    fails = [r["ref"] for r in real if r["verdict"] == "FAIL"]
    print("OVERALL: " + ("FAIL - gate-command crossing(s) below 1.5x at 95 V/ns: " + ", ".join(fails) if fails else "no FAIL rows"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
