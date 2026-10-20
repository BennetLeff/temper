#!/usr/bin/env python3
"""c54 desk pass: electrical ratings of the SIGNAL-class ledger lines (stdlib only).

    python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/net_stress.py      # first
    python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/signal_audit.py

Inputs: results/net_stress.json (static worst case per two-terminal part from the pin_absmax net model), the
pin_absmax per-pin rows (gates/pin_absmax.py run in-process against the frozen netlist), the datasheet records below
(every limit carries its PDF page; the PDFs are the sha-checked downloads listed in datasheets/records.json), and the
repo values named in each stress (file:line). Writes results/signal_audit.json (ledger-ready blocks, consumed by
apply_ledger.py), results/signal_audit.md (one line per stress: the ledger cites these lines) and results/ic_pins.md.

Rules (stated per line in derating_rule): resistors V <= max working voltage / RCWV and P <= 50 % of P70 (the RT /
RC1206 220 k lines' rule); MLCC / polymer V <= 80 % of VR in operation and <= 100 % at a rail's fault envelope (the
CL32B106 line's rule); ICs inside the recommended operating conditions and the abs max (the LM2901B / TPS70950 rule),
logic outputs <= 50 % of the abs-max IO; diodes VR and currents <= 50 % (the BAT54S rule); connector <= 80 % (the JST
VH rule).
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
C54 = HERE.parent
RES = C54 / "results"
UNIT = HERE.parents[3]
REL = "validation-results/11-candidates/c54-ledger-desk/results/"
sys.path.insert(0, str(UNIT / "native-21/layout/gates"))
import pin_absmax as pa  # noqa: E402

NS = {r["des"]: r for r in json.load(open(RES / "net_stress.json"))}
NSLINE = {}
for i, line in enumerate((RES / "net_stress.md").read_text().splitlines(), 1):
    tok = line.split(" ", 1)[0]
    if tok and tok[0] in "RCDUJ" and tok[1:2].isdigit():
        NSLINE[tok] = i

# ------------------------------------------------------------------------------------------------ datasheet records
DL = "/Users/bennet/Desktop/temper/worktrees/runs-native21"
TR = DL + "/s47/temp-ratings-dl"
FETCH = "2026-10-15 (temp-ratings lane download; sha re-verified by c54 on 2026-10-18)"
DS = {
    "uniroyal": dict(url="https://datasheet.lcsc.com/datasheet/pdf/0a975aaa49b7c97f38a963127be4a823.pdf",
                     revision="UniRoyal Thick Film Chip Resistors data sheet V.3 (Feb.12, 2019)", sha="11cd644d5d8a34a6",
                     local=TR + "/passives/uniroyal-1206/uniroyal-1206W4F.pdf"),
    "yageo_rc": dict(url="https://datasheet.lcsc.com/datasheet/pdf/b426be3ce22c6de3e0c3a2248e49159e.pdf?productCode=C130275",
                     revision="Yageo RC_L series 0075-2512 product specification V.12 (Aug 02, 2022)", sha="e7dbabb061192522",
                     local=TR + "/passives/yageo-rc/PYu-RC_Group_51_RoHS_L.pdf"),
    "yageo_rl": dict(url="https://store.comet.bg/download-file.php?id=22105",
                     revision="Yageo RL series 0402-2512 product specification V.3 (Apr 07, 2023), distributor mirror (Yageo URL 404)",
                     sha="a222719aba346137", local=TR + "/passives/yageo-rl/comet-22105.pdf"),
    "yageo_rt": dict(url="https://datasheet.lcsc.com/datasheet/pdf/46d7760c582640714d605308a25a220a.pdf?productCode=C95204",
                     revision="Yageo RT series 0100-2512 product specification V.16 (May 06, 2025)", sha="0a729d144519a702",
                     local=DL + "/s45/dl/yageo_rt.pdf"),
    "tnpw": dict(url="https://www.vishay.com/docs/28758/tnpw_e3.pdf", revision="Vishay TNPW e3 doc 28758, rev 10-Apr-2026",
                 sha="6f0508c568cb355a", local=DL + "/s45/dl/vishay_tnpw.pdf"),
    "kemet_c0g": dict(url="https://content.kemet.com/datasheets/KEM_C1003_C0G_SMD.pdf",
                      revision="KEMET C1003 C0G SMD commercial grade (2/20/2025)", sha="02d179914aeb9585",
                      local=TR + "/passives/kemet-c0g/KEM_C1003_C0G_SMD.pdf"),
    "yageo_cc": dict(url="https://datasheet.lcsc.com/datasheet/pdf/23ccee80ee542e7cf156a772bb589942.pdf?productCode=C14663",
                     revision="Yageo CC general purpose X7R 6.3-250 V, V.26 (Nov 19, 2024)", sha="61a606825ab314ea",
                     local=TR + "/passives/yageo-cc/yageo-cc-x7r-lcsc-C14663.pdf"),
    "CL05B104KB54PNC": dict(url="https://product.samsungsem.com/mlcc/CL05B104KB54PN.do (specsheet download)",
                            revision="Samsung SEM specification CL05B104KB54PN, issued JUL.15.2025", sha="92054b775800cad8",
                            local=TR + "/passives/samsung/CL05B104KB54PN-specsheet/CL05B104KB54PN-specsheet.pdf"),
    "CL10C101JB8NNNC": dict(url="https://product.samsungsem.com/mlcc/CL10C101JB8NNN.do (specsheet download)",
                            revision="Samsung SEM specification CL10C101JB8NNN, issued JUL.17.2020", sha="aec8f5c040150719",
                            local=TR + "/passives/samsung/CL10C101JB8NNN-specsheet/CL10C101JB8NNN-specsheet.pdf"),
    "CL10C331JB8NNNC": dict(url="https://product.samsungsem.com/mlcc/CL10C331JB8NNN.do (specsheet download)",
                            revision="Samsung SEM specification CL10C331JB8NNN, issued JUL.17.2020", sha="78b8db7110ad25cd",
                            local=TR + "/passives/samsung/CL10C331JB8NNN-specsheet/CL10C331JB8NNN-specsheet.pdf"),
    "CL21B105KBFNNNE": dict(url="https://product.samsungsem.com/mlcc/CL21B105KBFNNN.do (specsheet download)",
                            revision="Samsung SEM specification CL21B105KBFNNN, issued MAY.09.2024", sha="583b7deb63d39dd5",
                            local=TR + "/passives/samsung/CL21B105KBFNNN-specsheet/CL21B105KBFNNN-specsheet.pdf"),
    "GRM188R71E105KA12D": dict(url="https://store.comet.bg/download-file.php?id=22967",
                               revision="Murata product data sheet GRM188R71E105KA12#, last updated 04/27/2021 (distributor mirror)",
                               sha="5421aafe2e0574d4", local=TR + "/passives/murata/GRM188R71E105KA12D/comet-22967.pdf"),
    "GRM21BZ71E106KE15L": dict(url="https://datasheet.lcsc.com/datasheet/pdf/25c25013e9e59794670905e9d029f396.pdf?productCode=C237493",
                               revision="Murata reference sheet GRM21BZ71E106KE15-01A (as of Jan.9, 2025)", sha="8a398f916d26f901",
                               local=TR + "/passives/murata/GRM21BZ71E106KE15L/GRM21BZ71E106KE15L-lcsc-C237493.pdf"),
    "GRM31C5C1H104JA01L": dict(url="https://datasheet.lcsc.com/datasheet/pdf/357d841984a94b5db925be64cf2c2923.pdf?productCode=C97946",
                               revision="Murata reference sheet GRM31C5C1H104JA01_ (as of Mar.5, 2016)", sha="5c84ef333cecfe38",
                               local=TR + "/passives/murata/GRM31C5C1H104JA01L/GRM31C5C1H104JA01L-lcsc-C97946.pdf"),
    "svpc": dict(url="https://industrial.panasonic.com/cdbs/www-data/pdf/AAB8000/AAB8000C256.pdf",
                 revision="Panasonic OS-CON SVPC series AAB8000C256 (series pages 06-Feb-17, PDF 2025-10-29)", sha="1c506b7474c01158",
                 local=TR + "/passives/panasonic-svpc-official/AAB8000C256.pdf"),
    "bas116h": dict(url="https://datasheet.lcsc.com/datasheet/pdf/3effef0d92ac4111bb2691a2d714473d.pdf?productCode=C74210",
                    revision="Nexperia BAS116H Rev. 3, 31 May 2011 (LCSC copy; assets.nexperia.com 403)", sha="04966fbaa922997c",
                    local=TR + "/semis-a/bas116h/BAS116H_lcsc_C74210.pdf"),
    "pmeg": dict(url="https://datasheet.lcsc.com/datasheet/pdf/598a8a4be41fa942ad873c7b94285078.pdf?productCode=C456127",
                 revision="Nexperia PMEG6030EP product data sheet, 7 November 2017 (LCSC copy; assets.nexperia.com 403)",
                 sha="89bc99ad6f4835fb", local=TR + "/semis-a/pmeg6030ep/PMEG6030EP_lcsc_C456127.pdf"),
    "molex": dict(url="https://www.molex.com/pdm_docs/ps/PS-43045-001.pdf",
                  revision="Molex PS-43045 Micro-Fit 3.0 dual row product specification, Rev R (2025-11-14)", sha="b5f03865599a0576",
                  local=TR + "/conn/molex43045/PS-43045-001.pdf"),
    "sn74lvc1g00": dict(url="https://www.ti.com/lit/ds/symlink/sn74lvc1g00.pdf", revision="TI SCES212AC (April 1999, revised August 2026)",
                        sha="1264f79853e6119b", local=TR + "/semis-a/sn74lvc1g00/sn74lvc1g00.pdf"),
    "sn74lvc1g10": dict(url="https://www.ti.com/lit/ds/symlink/sn74lvc1g10.pdf", revision="TI SCES486E (September 2003, revised December 2013)",
                        sha="4902c8770413a400", local=TR + "/semis-a/sn74lvc1g10/sn74lvc1g10.pdf"),
    "sn74lvc1g17": dict(url="https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf", revision="TI SCES351Y (July 2001, revised October 2025)",
                        sha="c76fa723fac45024", local=TR + "/semis-a/sn74lvc1g17/sn74lvc1g17.pdf"),
    "sn74lvc1g332": dict(url="https://www.ti.com/lit/ds/symlink/sn74lvc1g332.pdf", revision="TI SCES489E (September 2003, revised December 2013)",
                         sha="5ecad3180cb93664", local=TR + "/semis-a/sn74lvc1g332/sn74lvc1g332.pdf"),
    "sn74lvc1g132": dict(url="https://www.ti.com/lit/ds/symlink/sn74lvc1g132.pdf", revision="TI SCES546E (February 2004, revised August 2026)",
                         sha="fae33d78fe46834a", local=TR + "/semis-a/sn74lvc1g132/sn74lvc1g132.pdf"),
    "tlv3201": dict(url="https://www.ti.com/lit/ds/symlink/tlv3201.pdf", revision="TI SBOS561C (March 2012, revised May 2024)",
                    sha="1777bba814c74772", local=TR + "/semis-a/tlv3201/tlv3201.pdf"),
    "tlvh431": dict(url="https://www.ti.com/lit/ds/symlink/tlvh431.pdf", revision="TI SLVS555N (November 2004, revised June 2024)",
                    sha="e30d628cb6475d48", local=DL + "/s16-monitor-dl/tlvh431.pdf"),
    "tps3700": dict(url="https://www.ti.com/lit/ds/symlink/tps3700.pdf", revision="TI SBVS187G (February 2012, revised February 2019)",
                    sha="3bb7daed20b154bf", local=DL + "/s16-fmea-b-dl/tps3700/tps3700.pdf"),
    "tps7a47": dict(url="https://www.ti.com/lit/ds/symlink/tps7a47.pdf", revision="TI SBVS204G (June 2012, revised May 2026)",
                    sha="8ca46a9968923d2e", local=DL + "/pin-absmax-dl/pdf/tps7a47.pdf"),
}

# ------------------------------------------------------------------------------------------------ repo inputs
V3V3 = (3.135, 3.465)        # pin_absmax_registry.json "v3v3" (J4.3 controller rail contract, FAULT-INTERFACE.md:28-29)
HOT5_MAX = 5.11              # pin_absmax_registry.json:135 (TPS70950-Q1 +-1 % + line 10 mV + load 50 mV)
I_TANK_FAULT = 155.7         # A, tank current at gate-off, CT failed / shunt OCP only (DECISIONS.md:2314-2315)
CT_N = 200                   # T1 CST3015-200ED 1:200 (ledger CST3015-200ED)
R_BURDEN_MAX = 3.0 * 1.01    # R39 RC1206FR-073RL 3.0 ohm 1 %
I_CH = (382.6e-9 + 61e-9) * 60e3 + 0.0044 + 0.003 + 0.0015 + 0.014   # make_heat_sources.py:222 (49.5 mA per channel)
I_U26 = 2 * I_CH + 0.030     # make_heat_sources.py:241 (U26 load = 2 I_ch + 30 mA)
R_SNK = 0.39                 # 2EDR8259X sink on-resistance (make_heat_sources.py:204-206 comment, Rev 1.7 p.15)
PUMP_PK_MA = 11.3            # heartbeat pump driver peak, every corner incl. one pump cap shorted (ledger BAT54S-7-F)
LINE_HI = 139.7              # Vrms, 127 V + 10 % (DECISIONS.md:306)
V_RV1_CLAMP = 455.0          # V, TMOV20RP175E Vc at 100 A (elec/src/parts.ato:85)

lines_md = ["# signal_audit.md: c54 stresses and derived numbers (generated by scripts/signal_audit.py; do not edit)",
            "# Each line: MPN | stress | value | derivation and inputs. The ledger cites these lines.", ""]


def emit(text):
    lines_md.append(text)
    return f"{REL}signal_audit.md:{len(lines_md)}"


def ns(des):
    return f"{REL}net_stress.md:{NSLINE[des]}"


def vmax(des, mode="op"):
    r = NS[des]
    return r["vmax_op"] if mode == "op" else r["vmax_fault"]


OUT = {}


def entry(mpn, ds, ratings, stresses, checks, rule, add_gaps=(), notes=None, function=None, drop_gaps=None):
    OUT[mpn] = dict(datasheet_key=ds, ratings=ratings, stresses=stresses, checks=checks, derating_rule=rule,
                    add_gaps=list(add_gaps), notes=notes, function=function, drop_gaps=drop_gaps)


def rt(p, lim, unit, basis, src):
    return dict(parameter=p, datasheet_limit=lim, unit=unit, basis=basis, source=src)


def st(p, val, unit, cond, ev):
    return dict(parameter=p, worst_case_value=round(val, 6), unit=unit, condition=cond, evidence=ev)


def ck(cid, r, s, mx, sev, rule):
    return dict(id=cid, rating=r, stress=s, max_ratio=mx, severity=sev, rule=rule)


def des_of(mpn):
    return [r["des"] for r in NS.values() if r["mpn"] == mpn]


def worst(dess, key):
    """(designator, value) with the largest net_stress value over dess."""
    best = max(dess, key=lambda d: NS[d].get(key) or 0.0)
    return best, NS[best].get(key) or 0.0


# ================================================================================================ resistors
def resistor_line(mpn, fam, p70, vmax_rating, vmax_basis, src_v, src_p, dess, manual=None, extra_rt=(), extra_st=(),
                  extra_ck=(), gaps=(), power_note=""):
    """Static worst case from net_stress for declared parts, manual (des -> (V, P_W, cond, ev)) for the rest."""
    rows = []
    for d in dess:
        if manual and d in manual:
            v, p, cond, ev = manual[d]
            rows.append((d, v, p, cond, ev))
        else:
            r = NS[d]
            vf = r["vmax_fault"]
            rows.append((d, vf, r["p_fault_mW"] / 1e3,
                         "static worst case over the registry rail ranges (fault envelopes included)", ns(d)))
    dv = max(rows, key=lambda x: x[1])
    dp = max(rows, key=lambda x: x[2])
    ratings = [rt("Max working voltage", vmax_rating, "V", vmax_basis, src_v),
               rt("Rated power P70", p70, "W", f"{p70} W at 70 C ambient, linear derating to 0 at 155 C", src_p)] + list(extra_rt)
    ev_v = emit(f"{mpn} | V across, worst {dv[0]} | {dv[1]:.4f} V | {dv[3]} | {dv[4]}")
    ev_p = emit(f"{mpn} | P, worst {dp[0]} | {dp[2] * 1e3:.4f} mW | {dp[3]}{power_note} | {dp[4]}")
    stresses = [st("Voltage across (worst ref)", dv[1], "V", f"{dv[0]}: {dv[3]}", [ev_v, dv[4]]),
                st("Power (worst ref)", dp[2], "W", f"{dp[0]}: {dp[3]}{power_note}", [ev_p, dp[4]])] + list(extra_st)
    checks = [ck("V working", "Max working voltage", "Voltage across (worst ref)", 1.0, "violation",
                 f"{dv[1]:.3g} V <= {vmax_rating:g} V ({dv[0]})"),
              ck("P <= 50 % P70", "Rated power P70", "Power (worst ref)", 0.5, "violation",
                 f"{dp[2] * 1e3:.3g} mW <= 50 % of {p70 * 1e3:g} mW ({dp[0]})")] + list(extra_ck)
    entry(mpn, fam, ratings, stresses, checks,
          "Voltage <= the maximum working voltage (or RCWV where lower); power <= 50 % of P70 at the static worst case "
          "(the temperature-dependent derating is the temp-ratings check at the B3 terminal estimate, 20 % margin).",
          add_gaps=gaps)
    return rows


UNI_V0603 = ("UniRoyal 0603: max working 75 V, overload 150 V (ratings table)", "p.5 ratings table")
UNI_P0603 = "p.4 power table (0603 1/10 W), p.5 sect. 9 derating"
UNI_V1206 = ("UniRoyal 1206: max working 200 V, overload 400 V (ratings table)", "p.5 ratings table")
UNI_P1206 = "p.4 power table (1206 W4 = 1/4 W), p.5 sect. 9 derating"
RT_V = ("Yageo RT0603: max working 75 V, overload 150 V (Table 2)", "p.5 Table 2")
RT_P = "p.5 Table 2 (RT0603 1/10 W), p.6 Fig. 6 derating"
RC_V = ("Yageo RC1206: max working 200 V, overload 400 V (Table 3)", "p.6 Table 3")
RC_P = "p.6 Table 3 (RC1206 1/4 W, '07' standard power p.2), p.7 Fig. 10-1"


def rcwv(p70, r, vmax_):
    return min(math.sqrt(p70 * r), vmax_)


def do_resistors():
    # --- UniRoyal 0603 lines whose parts are all declared nets
    for mpn, dess, val in [
        ("0603WAF1000T5E", ["R6", "R14"], 100.0),
        ("0603WAF1002T5E", ["R11", "R13", "R19", "R21", "R73", "R76", "R91", "R109", "R124"], 10e3),
        ("0603WAF1003T5E", ["R7", "R15", "R62", "R128", "R135", "R136", "R138", "R140", "R142"], 100e3),
        ("0603WAF2702T5E", ["R127", "R129", "R137", "R139", "R141", "R143"], 27e3),
        ("0603WAF3302T5E", ["R125"], 33e3),
        ("0603WAF4991T5E", ["R71", "R72", "R74", "R75", "R131"], 4.99e3),
        ("0603WAF5601T5E", ["R31"], 5.6e3),
    ]:
        vr = rcwv(0.1, val, 75.0)
        manual = {}
        if "R131" in dess:
            # R131 follows U45's output into C162 (hb_rc 'follow' net): DC 0 V; an edge puts the whole swing across it
            ev = emit(f"0603WAF4991T5E | R131 transient | {HOT5_MAX:.3f} V, {HOT5_MAX ** 2 / (4.99e3 * 0.99) * 1e3:.3f} mW "
                      f"| U45 (LS 5 V, ls_v5 max 5.11 V) edge across R131 into C162 330 pF, decays with 1.6 us; taken as "
                      f"continuous (bound) | pin_absmax_registry.json ls_v5")
            manual["R131"] = (HOT5_MAX, HOT5_MAX ** 2 / (4.99e3 * 0.99), "RC edge bound: full ls_v5 swing taken as continuous", ev)
        resistor_line(mpn, "uniroyal", 0.1, vr,
                      f"min(RCWV = sqrt(P70 x R) = {math.sqrt(0.1 * val):.3g} V, 75 V max working) ({UNI_V0603[0]})",
                      f"p.5 ratings table and RCWV = sqrt(P x R) (p.5)", UNI_P0603, dess, manual=manual)
    # --- 0603 1 k (R134 follow net, R47 CT monitor series)
    v47 = 4.09
    ev47 = emit(f"0603WAF1001T5E | R47 bound | {v47:.3f} V, {v47 ** 2 / 990 * 1e3:.3f} mW | ct_sense_mon at its CT-fault maximum "
                f"(see the TLV3201 CT-input line below) with the controller end (J4.14) shorted to SELV GND | this file")
    ev134 = emit(f"0603WAF1001T5E | R134 transient | {V3V3[1]:.3f} V, {V3V3[1] ** 2 / 990 * 1e3:.3f} mW | U9 output edge across "
                 f"R134 into C167 100 pF (bus_fault_flt 'follow' net, DC 0 V), taken as continuous (bound) | pin_absmax_registry.json v3v3")
    resistor_line("0603WAF1001T5E", "uniroyal", 0.1, rcwv(0.1, 1e3, 75.0),
                  f"min(RCWV = sqrt(0.1 W x 1 k) = 10 V, 75 V)", "p.5 ratings table and RCWV (p.5)", UNI_P0603, ["R47", "R134"],
                  manual={"R47": (v47, v47 ** 2 / 990, "CT-fault ct_sense_mon with J4.14 shorted (bound)", ev47),
                          "R134": (V3V3[1], V3V3[1] ** 2 / 990, "RC edge bound", ev134)})
    # --- 220 ohm R132 pump series
    v132 = PUMP_PK_MA * 1e-3 * 220 * 1.01
    ev = emit(f"0603WAF2200T5E | R132 | {v132:.3f} V peak, {(PUMP_PK_MA * 1e-3) ** 2 * 222.2 * 1e3:.3f} mW | 11.3 mA pump peak "
              f"(SPICE, every corner incl. one pump cap shorted) x 222.2 ohm, the peak taken as RMS (bound) | "
              f"validation-results/11-candidates/c24-monitor-fmea/results/m1_pump_spice.json")
    resistor_line("0603WAF2200T5E", "uniroyal", 0.1, rcwv(0.1, 220.0, 75.0), "min(RCWV = sqrt(0.1 W x 220) = 4.69 V, 75 V)",
                  "p.5 ratings table and RCWV (p.5)", UNI_P0603, ["R132"],
                  manual={"R132": (v132, (PUMP_PK_MA * 1e-3) ** 2 * 222.2, "pump peak taken as RMS (bound)", ev)})
    # --- 0 ohm jumper R38 (PE - SELV GND functional bond)
    ev = emit("0603WAF0000T5E | R38 operating current | 0.25 mA bound | functional PE-SELV bond: no circuit current; any operating "
              "current is leakage, bounded here by the product touch-current budget 0.25 mA (0.2412 mA computed) | "
              "validation-results/07-conducted-emi/leakage/README.md:12-13")
    entry("0603WAF0000T5E", "uniroyal",
          [rt("Jumper rated current", 1.0, "A", "0603 jumper: < 50 mOhm, rated current 1 A, max overload current 2 A", "p.5 ratings table")],
          [st("Operating current", 0.25e-3, "A", "functional bond; leakage bound (product budget)",
              [ev, "validation-results/07-conducted-emi/leakage/README.md:12-13"])],
          [ck("I", "Jumper rated current", "Operating current", 0.5, "violation", "0.25 mA << 1 A")],
          "Operating current <= 50 % of the jumper rating; fault and surge currents through the bond are a lab item.",
          add_gaps=["certifier / bench: surge and fault current through the PE-SELV bond (common-mode surge returning via "
                    "SELV GND, or a barrier fault) is not evidenced; the 0603 jumper is rated 1 A (2 A overload, p.5) and would "
                    "open, which leaves SELV unbonded (functional bond only): confirm in the surge / abnormal tests"])
    # --- 1206 UniRoyal: R42 (1 k CT series), R53/54/57/58 (1.00 ohm turn-off)
    v42 = 4.09
    ev = emit(f"1206W4F1001T5E | R42 bound | {v42:.3f} V, {v42 ** 2 / 990 * 1e3:.3f} mW | ct_s1 at the CT-fault maximum with "
              f"ct_sense_mon held at 0 V (bound; in operation D4 / D5 conduct only above the rails) | this file")
    resistor_line("1206W4F1001T5E", "uniroyal", 0.25, rcwv(0.25, 1e3, 200.0), "min(RCWV = sqrt(0.25 W x 1 k) = 15.8 V, 200 V)",
                  "p.5 ratings table and RCWV (p.5)", UNI_P1206, ["R42"],
                  manual={"R42": (v42, v42 ** 2 / 990, "CT-fault bound", ev)})
    p53 = 0.06304
    qoff = 443.6e-9
    vspan = 17.425
    ipk = vspan / (0.99 + R_SNK)
    e_edge = 0.5 * qoff * vspan * (1.0 / (1.0 + 0.1 + R_SNK + 2.7))
    ev1 = emit(f"1206W4F100KT5E | P (B3 heat row) | {p53 * 1e3:.2f} mW | R58 c17.5 / c28 heat row 0.0630 W | "
               f"validation-results/04-board-current-thermal/round5-native21/b3-ratings/temp-ratings-2026-10-15/results.md:40")
    ev2 = emit(f"1206W4F100KT5E | turn-off peak current bound | {ipk:.2f} A | span {vspan} V (v15_ls - n_ls max) over R53 min "
               f"0.99 + 2EDR sink 0.39 ohm, diode drop and Rg,int ignored (bound) | make_heat_sources.py:204-206")
    ev3 = emit(f"1206W4F100KT5E | energy per turn-off edge | {e_edge * 1e6:.3f} uJ | Q 443.6 nC x 17.4 V / 2 x R share "
               f"1.0 / (1.0 + 0.1 + 0.39 + 2.7) | validation-results/04-board-current-thermal/round5-native21/b3/make_heat_sources.py:196-206")
    entry("1206W4F100KT5E", "uniroyal",
          [rt("RCWV", 0.5, "V", "sqrt(0.25 W x 1.00 ohm)", "p.5 RCWV = sqrt(P x R)"),
           rt("Rated power P70", 0.25, "W", "1/4 W at 70 C, linear to 0 at 155 C", UNI_P1206),
           rt("5 s overload energy", 6.25 * 0.25 * 5, "J", "2.5 x RCWV for 5 s = 6.25 x P70 x 5 s (short-time overload, the "
              "nearest published pulse number; no single-pulse rating)", "p.5 overload rule; p.6 short-time overload")],
          [st("RMS voltage", math.sqrt(p53 * 1.01), "V", "sqrt(P x R) at the B3 heat row", [ev1]),
           st("Power", p53, "W", "B3 heat row (R58, c17.5 and c28)", [ev1, "validation-results/04-board-current-thermal/round5-native21/b3-ratings/temp-ratings-2026-10-15/results.md:40"]),
           st("Energy per turn-off edge", e_edge, "J", "gate-charge share per edge (ns pulse; peak bound "
              f"{ipk:.1f} A)", [ev2, ev3])],
          [ck("V", "RCWV", "RMS voltage", 1.0, "violation", "RMS within RCWV"),
           ck("P <= 50 % P70", "Rated power P70", "Power", 0.5, "violation", f"{p53 * 1e3:.1f} mW <= 125 mW"),
           ck("edge energy", "5 s overload energy", "Energy per turn-off edge", 0.5, "violation", "uJ per edge vs J")],
          "RMS within RCWV; power <= 50 % of P70; per-edge energy <= 50 % of the short-time overload energy (no pulse curve "
          "is published).",
          add_gaps=[f"owner (maker question): UniRoyal publishes no single-pulse rating; the {ipk:.1f} A, ns-wide turn-off "
                    f"peak is compared by energy ({e_edge * 1e6:.2f} uJ per edge) with the 5 s overload, the nearest published "
                    f"number (the same basis as 25121WF680JT4E)"])
    # --- Yageo RC1206: 2.2 k, 3.0 ohm, 16.5 k
    resistor_line("RC1206FR-072K2L", "yageo_rc", 0.25, rcwv(0.25, 2.2e3, 200.0), f"min(RCWV = sqrt(0.25 W x 2.2 k) = 23.5 V, 200 V) ({RC_V[0]})",
                  "p.6 Table 3; p.7 rated voltage = sqrt(P x R) or max working", RC_P, ["R59", "R63", "R65"])
    p39, p39c28 = 0.0506, 0.1297
    ev1 = emit(f"RC1206FR-073RL | P release / c28 | {p39 * 1e3:.1f} / {p39c28 * 1e3:.1f} mW | B3 heat rows (I_tank / 200)^2 x 3 ohm "
               f"at c17.5 / c28 | validation-results/04-board-current-thermal/round5-native21/b3-ratings/temp-ratings-2026-10-15/results.md:89")
    entry("RC1206FR-073RL", "yageo_rc",
          [rt("RCWV", math.sqrt(0.25 * 3.0), "V", "sqrt(0.25 W x 3.0 ohm)", "p.7 rated voltage = sqrt(P x R)"),
           rt("Rated power P70", 0.25, "W", "1/4 W at 70 C ('07' standard power)", RC_P)],
          [st("RMS voltage, c28", math.sqrt(p39c28 * 3.03), "V", "sqrt(P x R) at the c28 heat row", [ev1]),
           st("Power, release case", p39, "W", "B3 heat row at c17.5", [ev1]),
           st("Power, c28", p39c28, "W", "B3 heat row at c28 (28 A Kconfig ceiling)", [ev1])],
          [ck("V", "RCWV", "RMS voltage, c28", 1.0, "violation", "within RCWV at c28"),
           ck("P release", "Rated power P70", "Power, release case", 0.5, "violation", "50.6 mW <= 125 mW"),
           ck("P c28", "Rated power P70", "Power, c28", 0.5, "gap", "129.7 mW is 52 % of P70 at the 28 A ceiling")],
          "RMS within RCWV; power <= 50 % of P70 at the release case; the 28 A ceiling (c28) is reported.",
          add_gaps=["owner: at the 28 A Kconfig ceiling (c28 heat row 0.1297 W) the burden dissipates 52 % of P70, over the 50 % "
                    "rule (the temperature check at the c28 terminal still passes, 75.6 / 99.9 C); the firmware ships 17.5 A, where "
                    "it is 20 %. Raising the ceiling to 28 A needs a 1/2 W burden or the rule waived on the B3 terminal margin"])
    i67 = LINE_HI / (4 * 16.5e3 * 0.99)
    p67 = i67 ** 2 * 16.5e3 * 1.01
    v67 = i67 * 16.5e3 * 1.01
    ev1 = emit(f"RC1206FR-0716K5L | string current / P / V per resistor | {i67 * 1e3:.4f} mA rms, {p67 * 1e3:.2f} mW, {v67:.2f} Vrms "
               f"({v67 * math.sqrt(2):.1f} Vpk) | {LINE_HI} Vrms (DECISIONS.md:306) over 4 x 16.5 k -1 %, LED drop ignored (bound), "
               f"P at R +1 % | DECISIONS.md:306")
    vs = V_RV1_CLAMP / 4 * 1.01 / 0.99
    ev2 = emit(f"RC1206FR-0716K5L | surge V per resistor | {vs:.1f} V | RV1 clamp {V_RV1_CLAMP} V at 100 A (parts.ato:85) shared by "
               f"4 resistors, tolerance adverse | elec/src/parts.ato:85")
    entry("RC1206FR-0716K5L", "yageo_rc",
          [rt("Max working voltage", 200, "V", RC_V[0], RC_V[1]),
           rt("Max overload voltage", 400, "V", "RC1206 max overload 400 V (short-time)", "p.6 Table 3"),
           rt("Rated power P70", 0.25, "W", "1/4 W at 70 C", RC_P)],
          [st("Peak working voltage per resistor", v67 * math.sqrt(2), "V", "line high corner crest share", [ev1]),
           st("Surge voltage per resistor", vs, "V", "RV1 clamp 455 V at 100 A shared by the string (the clamp at 245-750 A is the "
              "R1/R2 desk item)", [ev2]),
           st("Power per resistor", p67, "W", "line high corner, string current bound", [ev1])],
          [ck("V working", "Max working voltage", "Peak working voltage per resistor", 1.0, "violation", "crest within the working voltage"),
           ck("surge", "Max overload voltage", "Surge voltage per resistor", 1.0, "violation", "455 V clamp / 4 <= overload"),
           ck("P <= 50 % P70", "Rated power P70", "Power per resistor", 0.5, "violation", f"{p67 * 1e3:.1f} mW <= 125 mW")],
          "Working voltage peak <= the maximum working voltage; surge share <= the overload voltage; power <= 50 % of P70.")
    # --- Yageo RL1206 0.68 ohm bias damp
    irms = 2 * I_CH
    p51 = irms ** 2 * 0.68 * 1.01
    ev = emit(f"RL1206FR-070R68L | I rms / P | {irms * 1e3:.1f} mA, {p51 * 1e3:.3f} mW | bias channel 49.5 mA mean (make_heat_sources "
              f"I_CH), RMS bounded at 2 x mean, 0.68 ohm +1 % | validation-results/04-board-current-thermal/round5-native21/b3/make_heat_sources.py:222")
    entry("RL1206FR-070R68L", "yageo_rl",
          [rt("Rated current", math.sqrt(0.25 / 0.68), "A", "sqrt(P70 / R) = sqrt(0.25 W / 0.68 ohm) (1/4 W normal power)",
              "p.5 Table 2 (RL1206 1/4 W, '07' standard power p.2)"),
           rt("Rated power P70", 0.25, "W", "1/4 W at 70 C, Fig. 5 to 0 at 155 C", "p.5 Table 2; p.6 Fig. 5")],
          [st("RMS current", irms, "A", "2 x the 49.5 mA mean channel current (bound)", [ev]),
           st("Power", p51, "W", "I_rms^2 x 0.687 ohm", [ev])],
          [ck("I", "Rated current", "RMS current", 0.5, "violation", "99 mA vs 0.61 A"),
           ck("P <= 50 % P70", "Rated power P70", "Power", 0.5, "violation", f"{p51 * 1e3:.2f} mW <= 125 mW")],
          "Current and power <= 50 % of the P70-derived ratings.")
    # --- Yageo RT0603 lines (fully declared unless noted)
    for mpn, dess, val in [
        ("RT0603BRD07105KL", ["R48"], 105e3), ("RT0603BRD0710KL", None, 10e3), ("RT0603BRD0711KL", None, 11e3),
        ("RT0603BRD07140KL", ["R37"], 140e3), ("RT0603BRD0715K8L", ["R30"], 15.8e3),
        ("RT0603BRD072K21L", ["R43", "R46"], 2.21e3), ("RT0603BRD074K42L", ["R79", "R97", "R112"], 4.42e3),
        ("RT0603BRD0763K4L", ["R92", "R94", "R144"], 63.4e3), ("RT0603BRD076K2L", ["R77", "R95", "R110"], 6.2e3),
    ]:
        if dess is None:
            dess = [r["des"] for r in NS.values() if r["mpn"] == mpn]
        resistor_line(mpn, "yageo_rt", 0.1, rcwv(0.1, val, 75.0),
                      f"min(RCWV = sqrt(0.1 W x R) = {math.sqrt(0.1 * val):.3g} V, 75 V max working) ({RT_V[0]})",
                      "p.5 Table 2; p.6 RATED VOLTAGE", RT_P, dess)
    # RT0603 1 k (CT bias) and 49.9 k (DT pins / hold node): undeclared nets, manual
    v40 = V3V3[1] * 1.001 / (2 * 0.999)
    ev = emit(f"RT0603BRD071KL | R40 / R41 | {v40:.4f} V, {v40 ** 2 / 999 * 1e3:.3f} mW | CT bias midpoint ct_s2 = v3v3 / 2 "
              f"(1 k / 1 k 0.1 %, v3v3 max 3.465 V); the CT current circulates in R39, not in the bias pair | pin_absmax_registry.json v3v3")
    resistor_line("RT0603BRD071KL", "yageo_rt", 0.1, rcwv(0.1, 1e3, 75.0), "min(RCWV = sqrt(0.1 W x 1 k) = 10 V, 75 V)",
                  "p.5 Table 2; p.6 RATED VOLTAGE", RT_P, ["R40", "R41"],
                  manual={d: (v40, v40 ** 2 / 999, "CT bias midpoint", ev) for d in ("R40", "R41")})
    ev = emit(f"RT0603BRD0749K9L | R9 / R17 / R133 | {V3V3[1]:.3f} V, {V3V3[1] ** 2 / 49.85e3 * 1e3:.4f} mW | the 2EDR8259X DT "
              f"pin (bounded by VDDI + 0.3 V, Table 9) and the heartbeat hold node (pump output <= the 3.3 V swing, ledger "
              f"BAT54S-7-F) taken at the v3v3 maximum (bound) | pin_absmax_registry.json undeclared_notes")
    resistor_line("RT0603BRD0749K9L", "yageo_rt", 0.1, rcwv(0.1, 49.9e3, 75.0), "min(RCWV = 70.6 V, 75 V)",
                  "p.5 Table 2; p.6 RATED VOLTAGE", RT_P, ["R9", "R17", "R133"],
                  manual={d: (V3V3[1] + (0.3 if d != "R133" else 0.0), (V3V3[1] + 0.3) ** 2 / 49.85e3, "DT pin / hold node bound", ev)
                          for d in ("R9", "R17", "R133")})
    # --- Vishay TNPW0603 11.7 k
    resistor_line("TNPW060311K7BEEA", "tnpw", 0.11, 100.0, "TNPW0603 operating voltage Umax 100 V (AC rms or DC); RCWV at the "
                  "General-mode 0.11 W is sqrt(0.11 x 11.7 k) = 35.9 V", "p.1 technical specifications",
                  "p.2 'Maximum resistance change at rated dissipation' (General operation 0.11 W at 70 C, 125 C film), p.1 P70 0.21 W",
                  ["R145"])
    # the existing RT lines that already carry V / P checks keep them; RT0603BRD0716KL / 077K5L only lose the stale gap


# ================================================================================================ capacitors
def cap_line(mpn, fam, vr, src_v, dess, manual=None, gaps=(), extra_rt=(), extra_st=(), extra_ck=(), rule_extra=""):
    rows = []
    for d in dess:
        if manual and d in manual:
            rows.append((d,) + manual[d])
        else:
            r = NS[d]
            rows.append((d, r["vmax_op"], r["vmax_fault"], "registry rail ranges (op) / fault envelopes", ns(d)))
    do = max(rows, key=lambda x: x[1])
    df = max(rows, key=lambda x: x[2])
    ev_o = emit(f"{mpn} | V operating, worst {do[0]} | {do[1]:.4f} V | {do[3]} | {do[4]}")
    ev_f = emit(f"{mpn} | V fault envelope, worst {df[0]} | {df[2]:.4f} V | {df[3]} | {df[4]}")
    ratings = [rt("Rated voltage", vr, "V", f"{vr:g} V DC rated", src_v)] + list(extra_rt)
    stresses = [st("DC voltage, operating (worst ref)", do[1], "V", f"{do[0]}: {do[3]}", [ev_o, do[4]]),
                st("DC voltage, rail fault envelope (worst ref)", df[2], "V", f"{df[0]}: {df[3]}", [ev_f, df[4]])] + list(extra_st)
    checks = [ck("V op <= 80 % VR", "Rated voltage", "DC voltage, operating (worst ref)", 0.8, "violation",
                 f"{do[1]:.3g} V <= 80 % of {vr:g} V ({do[0]})"),
              ck("V fault <= VR", "Rated voltage", "DC voltage, rail fault envelope (worst ref)", 1.0, "violation",
                 f"{df[2]:.3g} V <= {vr:g} V ({df[0]})")] + list(extra_ck)
    entry(mpn, fam, ratings, stresses, checks,
          "DC voltage <= 80 % of the rated voltage in operation and <= 100 % at a rail's fault envelope (PS2 OVP clamp on "
          "V24_RAW)" + rule_extra + "; dissipation negligible (temp-ratings).", add_gaps=gaps)


RECOM_GAP = ("certifier (abnormal operation): the HS rails p_ha / p_hb have no fault envelope; R24C2T25/R has no output "
             "over-voltage protection (Rev. 1-2024 p.2 lists only the 32 V VOUT+ to VOUT- pin abs max), so a feedback-open "
             "module could exceed this part's rating; the outcome (part damage, no hazard?) is a single-fault test item")
LDO_GAP = ("certifier (abnormal operation): a TPS7A4700 (U26) pass-element short puts V24_RAW (<= 32.4 V, PS2 OVP clamp) on "
           "V15_LS / NR; this part's rating is below that, so the single-fault outcome is a test item (the LM2901B line's "
           "stated case)")


def do_caps():
    cap_line("C0603C102J5GACTU", "kemet_c0g", 50, "p.1 ordering code '5 = 50' V (C0G 10-250 VDC family)",
             des_of("C0603C102J5GACTU"),
             manual={d: (2 * V3V3[1], 2 * V3V3[1], "heartbeat pump node: bounded by two v3v3 swings (pump of a 3.3 V buffer, "
                         "ledger BAT54S-7-F reverse 3.465 V per node)", "validation-results/11-candidates/c24-monitor-fmea/results/m1_pump_spice.json")
                     for d in ("C164", "C165", "C166")})
    cap_line("CC0603KRX7R9BB104", "yageo_cc", 50, "p.2 ordering code '9 = 50 V'",
             [r["des"] for r in NS.values() if r["mpn"] == "CC0603KRX7R9BB104"])
    cap_line("CC0805KRX7R9BB104", "yageo_cc", 50, "p.2 ordering code '9 = 50 V'", ["C8", "C10", "C15", "C17"])
    cap_line("CL05B104KB54PNC", "CL05B104KB54PNC", 50, "p.1 '(6) Rated Voltage 50V'",
             [r["des"] for r in NS.values() if r["mpn"] == "CL05B104KB54PNC"])
    cap_line("CL10C101JB8NNNC", "CL10C101JB8NNNC", 50, "p.1 '(6) Rated Voltage 50V'", ["C30", "C167"])
    cap_line("CL10C331JB8NNNC", "CL10C331JB8NNNC", 50, "p.1 '(6) Rated Voltage 50V'", ["C71", "C72", "C105", "C109", "C162"])
    cap_line("CL21B105KBFNNNE", "CL21B105KBFNNNE", 50, "p.1 '(6) Rated Voltage 50V'", ["C145", "C146", "C147", "C148", "C149", "C150"])
    cap_line("GRM188R71E105KA12D", "GRM188R71E105KA12D", 25, "p.2 'Rated Voltage 25Vdc'",
             ["C50", "C51", "C52", "C53", "C57", "C58", "C59", "C60", "C64"], gaps=[LDO_GAP.replace("this part's rating", "C64's 25 V rating")])
    cap_line("GRM21BZ71E106KE15L", "GRM21BZ71E106KE15L", 25, "p.2 Rated Value 'DC 25V'", ["C11", "C18"],
             gaps=[RECOM_GAP.replace("this part's rating", "C11 / C18's 25 V rating")])
    vb = 1.804 * 1.01
    cap_line("GRM31C5C1H104JA01L", "GRM31C5C1H104JA01L", 50, "p.1 rated value 'DC 50 V'", ["C42", "C43"],
             manual={"C42": (I_TANK_FAULT / CT_N * R_BURDEN_MAX, I_TANK_FAULT / CT_N * R_BURDEN_MAX,
                             "burden voltage at the 155.7 A CT-fault tank peak", "DECISIONS.md:2314-2315"),
                     "C43": (V3V3[1] * 1.001 / (2 * 0.999),) * 2 + ("ct_s2 bias midpoint", "native-21/layout/gates/pin_absmax_registry.json")})
    # polymer 6.3 V damp caps: V = negative-rail magnitude (R51-R56 carry no DC)
    rows = {}
    for c, src in (("C126", "C50"), ("C127", "C52"), ("C128", "C57"), ("C129", "C59")):
        rows[c] = (NS[src]["vmax_op"], NS[src]["vmax_fault"], f"damp node = the split rail (no DC in R51-R56): same nets as {src}", ns(src))
    irms = 2 * I_CH
    ev = emit(f"6SVPC220MV | ripple bound | {irms * 1e3:.1f} mA rms | the bias damp branch carries at most the channel current, "
              f"bounded at 2 x the 49.5 mA mean | validation-results/04-board-current-thermal/round5-native21/b3/make_heat_sources.py:222")
    cap_line("6SVPC220MV", "svpc", 6.3, "p.2 characteristics list row '6.3 ... 6SVPC220MV'", ["C126", "C127", "C128", "C129"], manual=rows,
             extra_rt=[rt("Ripple current at 10-100 kHz, 105 C", 3.16 * 0.7, "A", "3160 mA rms at 100 kHz / +105 C x frequency "
                          "factor 0.7 (10-100 kHz)", "p.2 row and frequency correction factor table")],
             extra_st=[st("Ripple current", irms, "A", "2 x mean bias channel current (bound)", [ev])],
             extra_ck=[ck("ripple", "Ripple current at 10-100 kHz, 105 C", "Ripple current", 0.5, "violation", "99 mA vs 2.2 A")],
             rule_extra="; ripple <= 50 % of the frequency-corrected 105 C rating")


# ================================================================================================ ICs
def ic_pins():
    r, _ = pa.run(UNIT, UNIT / "native-21/layout/gates/pin_absmax_registry.json", UNIT / "native-21/frozen/default.net", quiet=True)
    out, idx = ["# ic_pins.md: per-pin static worst case from gates/pin_absmax.py (op model; generated by signal_audit.py)", ""], {}
    for x in r["rows"]:
        lims = "; ".join(f"V vs {l['vs']} in [{l['iv'][0]:.4g}, {l['iv'][1]:.4g}] V, abs [{l['min']}, {l['max']}] (p.{l['page']})"
                         for l in x.get("limits", []))
        out.append(f"{x['part']}.{x['pin']} {x['mpn']} {x.get('function')} on {x['net']}: {x['status']}" + (f"; {lims}" if lims else ""))
        idx[(x["part"], x.get("function"))] = (len(out), x)
    (RES / "ic_pins.md").write_text("\n".join(out) + "\n")
    return idx


def pin_hi(idx, parts, fn, vs=None):
    """max over parts of the high end of V(pin) - V(ref) for function fn; returns (part, value, cite)."""
    best = None
    for p in parts:
        k = (p, fn)
        if k not in idx:
            continue
        ln, x = idx[k]
        for l in x.get("limits", []):
            if vs and l["vs"] != vs:
                continue
            if best is None or l["iv"][1] > best[1]:
                best = (p, l["iv"][1], f"{REL}ic_pins.md:{ln}")
    return best


def lvc_line(mpn, dsk, parts, ins, idx, page_abs, page_rec, out_loads, extra_gaps=(), extra_ck=(), extra_rt=(), extra_st=()):
    vcc = pin_hi(idx, parts, "VCC", "GND")
    vin = max((pin_hi(idx, parts, f, "GND") for f in ins if pin_hi(idx, parts, f, "GND")), key=lambda t: t[1])
    dmax = max(out_loads, key=lambda t: t[1])
    ev = emit(f"{mpn} | output current, worst {dmax[0]} | {dmax[1]:.4f} mA | {dmax[2]} | {dmax[3]}")
    ratings = [rt("VCC abs max", 6.5, "V", "supply voltage range -0.5..6.5 V", page_abs),
               rt("VCC recommended max", 5.5, "V", "operating 1.65..5.5 V", page_rec),
               rt("VI abs max", 6.5, "V", "input voltage range -0.5..6.5 V", page_abs),
               rt("VI recommended max", 5.5, "V", "input voltage 0..5.5 V", page_rec),
               rt("IO abs max", 50, "mA", "continuous output current +-50 mA", page_abs),
               rt("IOL recommended at VCC 3 V", 24, "mA", "IOL / -IOH 24 mA at VCC = 3 V (16 mA at 2.3 V, 32 mA at 4.5 V)", page_rec)] + list(extra_rt)
    stresses = [st("VCC", vcc[1], "V", f"{vcc[0]}: supply rail maximum (pin_absmax op model)", [vcc[2]]),
                st("Input voltage", vin[1], "V", f"{vin[0]}: highest input pin (pin_absmax op model)", [vin[2]]),
                st("Output current", dmax[1], "mA", f"{dmax[0]}: {dmax[2]}", [ev] + ([dmax[3]] if dmax[3] != "this file" else []))] + list(extra_st)
    checks = [ck("VCC rec", "VCC recommended max", "VCC", 1.0, "violation", f"{vcc[1]:.3g} V <= 5.5 V"),
              ck("VCC abs", "VCC abs max", "VCC", 1.0, "violation", "inside abs max"),
              ck("VI rec", "VI recommended max", "Input voltage", 1.0, "violation", f"{vin[1]:.3g} V <= 5.5 V"),
              ck("IO <= 50 % abs", "IO abs max", "Output current", 0.5, "violation", f"{dmax[1]:.3g} mA <= 25 mA"),
              ck("IOL rec", "IOL recommended at VCC 3 V", "Output current", 1.0, "violation", f"{dmax[1]:.3g} mA <= 24 mA")] + list(extra_ck)
    entry(mpn, dsk, ratings, stresses, checks,
          "VCC and inputs inside the recommended operating conditions (pin_absmax gates the abs max per pin); output current "
          "<= 50 % of the abs-max IO and inside the recommended IOL / IOH; input edges inside the recommended transition rate "
          "for non-Schmitt inputs.", add_gaps=extra_gaps)


def do_ics():
    idx = ic_pins()
    # output loads (mA): designator, current, derivation, evidence
    r73 = V3V3[1] / (10e3 * 0.99) * 1e3
    lvc_line("SN74LVC1G00DBVR", "sn74lvc1g00", ["U22", "U23"], ["A", "B"], idx, "p.4 5.1 Absolute Maximum Ratings",
             "p.5 5.3 Recommended Operating Conditions",
             [("U22", r73 + 0.027, "Y low sinks the R73 10 k pull-up from v3v3 (3.465 V / 9.9 k) plus the 2EDR8259X DIS input "
               "(<= 27 uA high-level leakage, 2EDR8259X Rev 1.7 p.14)", ns("R73"))])
    lvc_line("SN74LVC1G10DBVR", "sn74lvc1g10", ["U8"], ["A", "B", "C"], idx, "p.2 Absolute Maximum Ratings",
             "p.3 Recommended Operating Conditions",
             [("U8", 0.020, "Y drives the U9 CA-IS3720 input only (IIH / IIL <= 20 uA, CA-IS372x v1.02 p.10)", "this file")])
    lvc_line("SN74LVC1G17DBVR", "sn74lvc1g17", ["U15", "U24", "U40"], ["A"], idx, "p.4 5.1 Absolute Maximum Ratings",
             "p.5 5.3 Recommended Operating Conditions",
             [("U15", 0.005, "Y drives U8.C (LVC input leakage +-5 uA)", "this file"),
              ("U40", V3V3[1] / (220e3 * 0.99) * 1e3 + 0.010, "Y drives R146 220 k to J4.1 plus U22.B / U23.B", "this file"),
              ("U24", 0.0, "Y drives J4.16 LINE_ZC only; the controller-side load is not in the repo (gap)", "this file")],
             extra_gaps=["owner (interface contract): the controller-side load on J4.16 (LINE_ZC from U24) is not in the repo; "
                         "the check covers the board side only. The J4 logic contract (FAULT-INTERFACE.md:28-33) states "
                         "~350 uA for BUS_FAULT; record the LINE_ZC / CT_ZC input loads in the controller's interface document"])
    # U13 LVC1G332: A input behind R134 1 k / C167 100 pF (tau 100 ns, DECISIONS.md:1108)
    tau = 1e3 * 1.01 * 100e-12 * 1.05
    dtdv_fall = tau / 0.8 * 1e9
    dtdv_rise = tau / (V3V3[0] - 2.0) * 1e9
    ev_t = emit(f"SN74LVC1G332DBVR | U13.A input transition rate | {dtdv_fall:.1f} ns/V (falling, at VIL 0.8 V); "
                f"{dtdv_rise:.1f} ns/V (rising, at VIH 2.0 V, v3v3 min) | RC tau = 1.01 k x 105 pF = {tau * 1e9:.1f} ns (R134 1 k "
                f"1 %, C167 100 pF C0G 5 %); slope at a level Vx is (Vfinal - Vx) / tau | DECISIONS.md:1108")
    lvc_line("SN74LVC1G332DBVR", "sn74lvc1g332", ["U13"], ["A", "B", "C"], idx, "p.2 Absolute Maximum Ratings",
             "p.3 Recommended Operating Conditions",
             [("U13", 0.350, "Y drives J4.10 BUS_FAULT into the controller interlock (~350 uA maximum pull-up load)",
               "FAULT-INTERFACE.md:32")],
             extra_rt=[rt("Input transition rate, recommended max", 10, "ns/V", "dt/dv 10 ns/V at VCC 3.3 V +- 0.3 V (non-Schmitt inputs)",
                          "p.3 Recommended Operating Conditions")],
             extra_st=[st("Input transition rate, U13.A", dtdv_fall, "ns/V", "R134 / C167 RC edge (tau 106 ns) at the VIL "
                          "band edge; 64-71 ns/V at the ~1.5 V switching point", [ev_t, "DECISIONS.md:1108"])],
             extra_ck=[ck("dt/dv U13.A", "Input transition rate, recommended max", "Input transition rate, U13.A", 1.0, "gap",
                          f"{dtdv_fall:.0f} ns/V against the 10 ns/V recommended maximum (functional, not an abs-max overstress)")],
             extra_gaps=[f"finding (c54, recommended-operating-condition exceedance, not an abs-max overstress): U13.A is a "
                         f"non-Schmitt LVC1G332 input fed through the R134 1 k / C167 100 pF CMTI filter (DECISIONS.md:1108); its "
                         f"edge crosses the input band at {dtdv_rise:.0f}-{dtdv_fall:.0f} ns/V against TI's 10 ns/V recommended "
                         f"maximum (SCES489E p.3), so the output may chatter while BUS_FAULT crosses threshold (a fault-direction "
                         f"level into the controller latch: nuisance double edges, not a missed trip). Owner: accept with the bench "
                         f"probe of DECISIONS.md:1128 item 4, or move the RC behind a Schmitt input (e.g. an LVC1G17 or a Schmitt "
                         f"OR) at the next spin; bench: scope U13.Y on BUS_FAULT edges with R134 / C167 fitted"])
    # G132 (U45 LS oscillator / U46 SELV pump buffer): U46 sources the pump (11.3 mA peak)
    lvc_line("SN74LVC1G132DBVR", "sn74lvc1g132", ["U45", "U46"], ["A", "B"], idx, "p.4 5.1 Absolute Maximum Ratings",
             "p.5 5.3 Recommended Operating Conditions",
             [("U46", PUMP_PK_MA, "Y sources / sinks the heartbeat pump through R132 220 ohm: 11.3 mA SPICE peak, every corner incl. "
               "one pump cap shorted (ledger BAT54S-7-F)", "validation-results/11-candidates/c24-monitor-fmea/results/m1_pump_spice.json"),
              ("U45", HOT5_MAX / (4.99e3 * 0.99) * 1e3, "Y charges C162 through R131 4.99 k (edge peak)", ns("R131"))])
    # TLV3201 U6 U7 (HOT5, OCP / OVP) U10-U12 (v3v3, CT)
    vs = pin_hi(idx, ["U6", "U7", "U10", "U11", "U12"], "VCC", "GND")
    vin = max((pin_hi(idx, [u], f, "GND") for u in ("U6", "U7", "U10", "U11", "U12") for f in ("IN+", "IN-")
               if pin_hi(idx, [u], f, "GND")), key=lambda t: t[1])
    vb = I_TANK_FAULT / CT_N * R_BURDEN_MAX
    s2max = V3V3[1] * 1.001 / (2 * 0.999)
    s2min = V3V3[0] * 0.999 / (2 * 1.001)
    s1max, s1min = s2max + vb, s2min - vb
    over = s1max - V3V3[0]
    iclamp = max(s1max - V3V3[0], -s1min) / (1e3 * 0.99) * 1e3
    ev_ct = emit(f"TLV3201AIDBVR | CT inputs U10-U12 (ct_sense_mon) | ct_s1 {s1min:.3f}..{s1max:.3f} V; {over:.3f} V above v3v3 min; "
                 f"clamp current <= {iclamp:.3f} mA | burden {vb:.3f} V = 155.7 A / 200 x 3.03 ohm (CT failed, shunt OCP only: tank "
                 f"current at gate-off <= 155.7 A) on the ct_s2 bias {s2min:.3f}..{s2max:.3f} V (1 k / 1 k 0.1 % from v3v3); current into "
                 f"the input / D4 / D5 clamps limited by R42 1 k (worst: the whole excess over 990 ohm, diode drops ignored) | DECISIONS.md:2314-2315")
    entry("TLV3201AIDBVR", "tlv3201",
          [rt("Supply recommended max", 5.5, "V", "VS 2.7..5.5 V", "p.4 6.3 Recommended Operating Conditions"),
           rt("Supply abs max", 7, "V", "supply voltage 7 V", "p.4 6.1 Absolute Maximum Ratings"),
           rt("Input pin current abs max", 10, "mA", "signal input pins +-10 mA; inputs swinging > 0.5 V beyond the rails must be "
              "current-limited to 10 mA (note 2)", "p.4 6.1 and note (2)"),
           rt("Common-mode range above VCC", 0.2, "V", "VCM (VEE) - 0.2 .. (VCC) + 0.2 V over -40..125 C", "p.5 6.5 Electrical Characteristics"),
           rt("Output short-circuit current abs max", 100, "mA", "output short circuit to ground 100 mA", "p.4 6.1")],
          [st("Supply", vs[1], "V", f"{vs[0]}: HOT5 / v3v3 maximum (pin_absmax op model)", [vs[2]]),
           st("Input above VCC, CT fault", over, "V", "U10-U12 on ct_sense_mon at the 155.7 A CT-fault peak (diode-clamped, "
              "current-limited)", [ev_ct, "DECISIONS.md:2314-2315"]),
           st("Input clamp current, CT fault", iclamp, "mA", "R42 1 k limits it", [ev_ct]),
           st("Input, highest declared pin", vin[1], "V", f"{vin[0]} (pin_absmax op model: OCP / OVP / CT reference inputs)", [vin[2]]),
           st("Output load", 0.02, "mA", "outputs drive LVC / CA-IS3720 inputs (<= 20 uA) and J4.13 (CT_ZC, controller side not in "
              "the repo)", ["native-21/frozen/default.net"])],
          [ck("VS rec", "Supply recommended max", "Supply", 1.0, "violation", f"{vs[1]:.3g} V <= 5.5 V"),
           ck("VS abs", "Supply abs max", "Supply", 1.0, "violation", "inside 7 V"),
           ck("CT input current", "Input pin current abs max", "Input clamp current, CT fault", 0.5, "violation",
              f"{iclamp:.2f} mA <= 50 % of 10 mA (note 2 permits > 0.5 V beyond the rail at <= 10 mA)"),
           ck("CT input in CM range", "Common-mode range above VCC", "Input above VCC, CT fault", 1.0, "gap",
              f"{over:.2f} V above VCC at the 155.7 A fault peak: outside the specified VCM (+0.2 V) and the 0.5 V abs max, "
              "allowed by note 2 at <= 10 mA; comparator output is not specified there"),
           ck("output", "Output short-circuit current abs max", "Output load", 0.5, "violation", "uA loads")],
          "Supply inside the recommended range; declared inputs inside abs max (pin_absmax); inputs that swing beyond the rails "
          "current-limited to <= 50 % of the 10 mA note-2 limit; outputs far below the short-circuit rating.",
          add_gaps=[f"bench: at the 155.7 A CT-fault tank peak the CT inputs (U10 / U11 / U12) reach {over:.2f} V above VCC, beyond "
                    f"the specified common-mode range (VCC + 0.2 V), current-limited to {iclamp:.2f} mA by R42 (inside note 2's 10 mA); "
                    f"the comparators' outputs are unspecified there (phase reversal not excluded by the sheet). In operation "
                    f"(OCP band top 119.09 A) the excursion is smaller; inject primary current past the trip and watch CT_OC / CT_ZC",
                    "owner (interface contract): J4.13 CT_ZC (U12) controller-side load is not in the repo"])
    # TLVH431 split shunts U16 / U18 / U20
    vka = pin_hi(idx, ["U16", "U18", "U20"], "K", "A")
    ikmax = (17.425 - 1.9638) / (4.99e3 * 0.99) * 1e3
    ikmin = (16.5484 - 2.0773) / (4.99e3 * 1.01) * 1e3 - 2.0773 / (16.2e3 * 0.999) * 1e3
    ev = emit(f"TLVH431BQDBZR | IK max / min | {ikmax:.3f} / {ikmin:.3f} mA | max: the whole 4.99 k bleed (R71 / R72 / R74 / R75) from "
              f"the span max 17.425 V less V_split min 1.964 V over 4.94 k flows in the shunt (b3_ratings_gate MONITOR_SELF basis); min: "
              f"span min 16.548 V less V_split max 2.077 V over 5.04 k, less the 6.2 k + 10 k feedback string | "
              f"validation-results/04-board-current-thermal/round5-native21/b3-ratings/b3_ratings_gate.py:133-134")
    entry("TLVH431BQDBZR", "tlvh431",
          [rt("Cathode voltage recommended max", 18, "V", "VKA VREF..18 V", "p.5 5.3 Recommended Operating Conditions"),
           rt("Cathode current recommended max", 70, "mA", "IK (continuous) 0.1..70 mA", "p.5 5.3"),
           rt("Cathode current abs max", 80, "mA", "IK -25..80 mA", "p.5 5.1 Absolute Maximum Ratings"),
           rt("Cathode current recommended min", 0.1, "mA", "IK min 0.1 mA (IK(min) <= 100 uA, p.8)", "p.5 5.3")],
          [st("VKA", vka[1], "V", f"{vka[0]}: split voltage maximum (pin_absmax op model)", [vka[2]]),
           st("IK max", ikmax, "mA", "whole bleed current (bound)", [ev]),
           st("IK min", ikmin, "mA", f"floor of the shunt current ({ikmin:.2f} mA >= the 0.1 mA recommended minimum; a floor, so "
              "not a stress/limit check)", [ev])],
          [ck("VKA rec", "Cathode voltage recommended max", "VKA", 1.0, "violation", f"{vka[1]:.3g} V <= 18 V"),
           ck("IK rec", "Cathode current recommended max", "IK max", 1.0, "violation", f"{ikmax:.2f} mA <= 70 mA"),
           ck("IK abs 50 %", "Cathode current abs max", "IK max", 0.5, "violation", "<= 40 mA")],
          "VKA and IK inside the recommended operating conditions (IK >= 0.1 mA); IK <= 50 % of the abs max.")
    # TPS3700 U14 (HOT5 window)
    vdd = pin_hi(idx, ["U14"], "VDD", "GND")
    vin = max(pin_hi(idx, ["U14"], "INA+", "GND"), pin_hi(idx, ["U14"], "INB-", "GND"), key=lambda t: t[1])
    vout = pin_hi(idx, ["U14"], "OUTA", "GND")
    iout = HOT5_MAX / (10e3 * 0.999) * 1e3
    ev = emit(f"TPS3700DDCR | output sink current | {iout:.4f} mA | OUTA / OUTB wired on hot5_uv_raw, R50 10 k 0.1 % pull-up to HOT5 "
              f"5.11 V max, plus the U15 Schmitt input (uA) | {ns('R50')}")
    entry("TPS3700DDCR", "tps3700",
          [rt("VDD recommended max", 18, "V", "VDD 1.8..18 V", "p.5 6.3 Recommended Operating Conditions"),
           rt("Input recommended max", 6.5, "V", "VI INA+, INB- 0..6.5 V", "p.5 6.3"),
           rt("Output voltage recommended max", 18, "V", "VO OUTA, OUTB 0..18 V", "p.5 6.3"),
           rt("Output terminal current abs max", 40, "mA", "output terminal current 40 mA", "p.5 6.1 Absolute Maximum Ratings")],
          [st("VDD", vdd[1], "V", "HOT5 maximum (pin_absmax op model)", [vdd[2]]),
           st("Input voltage", vin[1], "V", f"{vin[0]} INA+ / INB- divider taps (pin_absmax op model)", [vin[2]]),
           st("Output voltage", vout[1], "V", "pull-up to HOT5", [vout[2]]),
           st("Output sink current", iout, "mA", "R50 pull-up", [ev, ns("R50")])],
          [ck("VDD rec", "VDD recommended max", "VDD", 1.0, "violation", "5.11 V <= 18 V"),
           ck("VI rec", "Input recommended max", "Input voltage", 1.0, "violation", "< 0.5 V <= 6.5 V"),
           ck("VO rec", "Output voltage recommended max", "Output voltage", 1.0, "violation", "5.11 V <= 18 V"),
           ck("IO 50 %", "Output terminal current abs max", "Output sink current", 0.5, "violation", "0.51 mA <= 20 mA")],
          "Supply, inputs and outputs inside the recommended operating conditions; output current <= 50 % of the abs max.")
    # TPS7A4700 U26
    vin_op = pin_hi(idx, ["U26"], "IN", "GND")
    vout = pin_hi(idx, ["U26"], "OUT", "GND")
    ev = emit(f"TPS7A4700RGWR | IN fault envelope / load | 32.4 V / {I_U26 * 1e3:.1f} mA | V24_RAW fault envelope = PS2 MPM-20-24 OVP "
              f"clamp top 27.6-32.4 V (registry v24_raw 'fault'); load = 2 I_ch + 30 mA (I_ch 49.5 mA, make_heat_sources) | "
              f"validation-results/04-board-current-thermal/round5-native21/b3/make_heat_sources.py:241")
    entry("TPS7A4700RGWR", "tps7a47",
          [rt("VIN recommended max", 35, "V", "VI 3.0..35 V", "p.5 5.3 Recommended Operating Conditions"),
           rt("VIN abs max", 36, "V", "IN pin to GND -0.4..+36 V", "p.4 5.1 Absolute Maximum Ratings"),
           rt("VOUT recommended max", 34, "V", "VO 1.4..34 V", "p.5 5.3"),
           rt("IOUT recommended max", 1.0, "A", "IO 0..1.0 A", "p.5 5.3")],
          [st("VIN operating", vin_op[1], "V", "V24_RAW maximum (PS2 24 V +-2 %, pin_absmax op model)", [vin_op[2]]),
           st("VIN fault envelope", 32.4, "V", "PS2 OVP clamp top (MPM-20-SPEC p.2)", [ev, "native-21/layout/gates/pin_absmax_registry.json"]),
           st("VOUT", vout[1], "V", "V15_LS maximum", [vout[2]]),
           st("IOUT", I_U26, "A", "2 I_ch + 30 mA", [ev])],
          [ck("VIN rec", "VIN recommended max", "VIN operating", 1.0, "violation", "24.57 V <= 35 V"),
           ck("VIN fault abs", "VIN abs max", "VIN fault envelope", 1.0, "violation", "32.4 V <= 36 V"),
           ck("VOUT rec", "VOUT recommended max", "VOUT", 1.0, "violation", "17.4 V <= 34 V"),
           ck("IOUT 50 %", "IOUT recommended max", "IOUT", 0.5, "violation", f"{I_U26 * 1e3:.0f} mA <= 500 mA")],
          "VIN, VOUT, IOUT inside the recommended conditions in operation; VIN at the PS2 OVP clamp inside the abs max; "
          "IOUT <= 50 % of 1 A; TJ <= 125 C (the temp-ratings / B3 gate row).",
          function="low-noise LDO U26 (V15_LS, the LS span from V24_RAW); TJ is the B3 body-model row: 120.6 / 125 C at the release "
                   "case (+4.4 K) and 124.9 C at c28 (+0.1 K), temp-ratings 2026-10-15 results.md:38 (the old 'Tj 89 C, 36 K margin', "
                   "DECISIONS.md:825, was the superseded stage-15 h25 model)")


# ================================================================================================ diodes, connector
def do_discretes():
    # BAS116H D4 / D5 CT clamps
    vr = V3V3[1] + 1.0
    ifw = 4.09 / (1e3 * 0.99) * 1e3
    ev = emit(f"BAS116H,115 | VR / IF bound | {vr:.3f} V / {ifw:.3f} mA | VR: one diode reverse-biased by v3v3 max plus the other's "
              f"VF <= 1.00 V at 10 mA (p.3); IF: the whole CT-fault ct_s1 maximum 4.09 V over R42 990 ohm (bound) | this file")
    entry("BAS116H,115", "bas116h",
          [rt("VR", 75, "V", "reverse voltage 75 V (VRRM 85 V)", "p.2 Table 5 Limiting values"),
           rt("IF", 215, "mA", "forward current 215 mA (FR4, standard footprint)", "p.2 Table 5"),
           rt("IFRM", 500, "mA", "repetitive peak forward current 500 mA", "p.2 Table 5")],
          [st("Reverse voltage", vr, "V", "clamp pair across v3v3", [ev]),
           st("Forward current (peak bound)", ifw, "mA", "CT-fault excursion through R42", [ev])],
          [ck("VR 50 %", "VR", "Reverse voltage", 0.5, "violation", "4.5 V <= 37.5 V"),
           ck("IF 50 %", "IFRM", "Forward current (peak bound)", 0.5, "violation", "4.1 mA <= 250 mA")],
          "Reverse voltage and peak forward current <= 50 % of the limiting values.")
    # PMEG6030EP D6-D9 turn-off diodes
    span = 17.425
    qf = 443.6e-9 * 60e3 * 1e3
    ipk = span / (0.99 + R_SNK)
    ev1 = emit(f"PMEG6030EP,115 | VR | {span:.3f} V | cathode on the turn-off node (follows the driver output), anode on the gate: at "
               f"turn-on the output is at P while the gate is still at N, so VR <= the driver span max (v15_ls - n_ls 17.425 V) | "
               f"{ns('C65')}")
    ev2 = emit(f"PMEG6030EP,115 | IF average / peak bound | {qf:.2f} mA / {ipk:.2f} A | average: turn-off charge 443.6 nC x 60 kHz; "
               f"peak: span over R53 min 0.99 + 2EDR sink 0.39 ohm (diode drop, Rg,int ignored: bound; ns wide) | "
               f"validation-results/04-board-current-thermal/round5-native21/b3/make_heat_sources.py:196-206")
    entry("PMEG6030EP,115", "pmeg",
          [rt("VR", 60, "V", "reverse voltage 60 V (Tj 25 C)", "p.3 Table 5 Limiting values"),
           rt("IF(AV)", 3.0, "A", "average forward current 3 A (square wave, delta 0.5, 20 kHz)", "p.3 Table 5"),
           rt("IFSM", 50, "A", "non-repetitive peak forward current 50 A (tp 8 ms square); no repetitive peak (IFRM) is published",
              "p.3 Table 5")],
          [st("Reverse voltage", span, "V", "driver span maximum", [ev1, ns("C65")]),
           st("Average forward current", qf / 1e3, "A", "turn-off charge x 60 kHz", [ev2]),
           st("Peak forward current (bound)", ipk, "A", "ns-wide turn-off peak", [ev2])],
          [ck("VR 50 %", "VR", "Reverse voltage", 0.5, "violation", "17.4 V <= 30 V"),
           ck("IF(AV) 50 %", "IF(AV)", "Average forward current", 0.5, "violation", "27 mA <= 1.5 A"),
           ck("peak vs IFSM", "IFSM", "Peak forward current (bound)", 0.5, "violation", "12.6 A <= 25 A (IFSM as the nearest published peak)")],
          "VR, average and peak current <= 50 % of the limiting values (the peak against IFSM, no IFRM being published).",
          add_gaps=["owner (maker question): Nexperia publishes no repetitive peak forward current; the ns-wide 12.6 A turn-off "
                    "peak bound is compared with the 8 ms non-repetitive IFSM (50 A), whose I2t is about seven orders larger"])
    # J4 Micro-Fit 43045-1612
    loads = [("2EDR8259X VDDI x 2 (U1, U2)", 2 * 2 * 2.12, "2EDR8259X Rev 1.7 p.12 IVDDIq max 2.12 mA (no switching), doubled as a "
              "switching allowance because only a typical switching curve is published (p.24)"),
             ("AMC1311 IDD2 (U4)", 7.2, "SBAS786C p.11 IDD2 max 7.2 mA at 3.0-3.6 V"),
             ("CA-IS3720 side B x 2 (U9, U32)", 2 * 3.2, "CA-IS372x v1.02 p.11 IDDB max 3.2 mA at 1 Mbps"),
             ("TLV3201 x 3 (U10-U12)", 3 * 0.065, "SBOS561C p.5 IQ max 65 uA"),
             ("LVC1G x 6 (U13, U22, U23, U24, U40, U46) ICC", 6 * 0.010, "ICC max 10 uA (TI LVC1G EC tables)"),
             ("pump peak (U46 via R132)", PUMP_PK_MA, "ledger BAT54S-7-F, SPICE peak"),
             ("R73 + R76 pull-ups", 2 * V3V3[1] / 9.9, "3.465 V / 9.9 k each"),
             ("R40 / R41 CT bias", V3V3[1] / 1.998, "3.465 V / 2 k"),
             ("R43 + R44, R45 + R46 CT references", 2 * V3V3[1] / 12.2, "3.465 V / 12.2 k each"),
             ("R125 ZC pull-up", V3V3[1] / 32.67, "3.465 V / 32.7 k")]
    itot = sum(x[1] for x in loads)
    ev = emit(f"0430451612 | J4.3 v3v3 contact current bound | {itot:.2f} mA | sum of datasheet maxima of every v3v3 load "
              f"(netlist v3v3 members): " + "; ".join(f"{a} {b:.3f} mA ({c})" for a, b, c in loads) + " | native-21/frozen/default.net")
    entry("0430451612", "molex",
          [rt("UL voltage rating", 600, "V", "UL 1977 / CSA C22.2 No. 182.3: 600 V AC rms or DC (series 43045)", "sheet 7 sect. 4.1 Safety agency ratings"),
           rt("Contact current, 24-circuit 30 AWG W-B", 1.0, "A", "current derating reference, 24 circuits, 30 AWG, wire-to-board: 1 A "
              "(the lowest cell; 30 C rise; UL / CSA single circuit 8 A)", "sheet 8 sect. 4.3 current derating")],
          [st("SELV voltage", V3V3[1], "V", "J4 carries SELV logic and the 3.3 V controller rail", ["native-21/frozen/default.net"]),
           st("Contact current, J4.3 v3v3", itot / 1e3, "A", "all v3v3 loads at datasheet maximum (bound)", [ev])],
          [ck("V 80 %", "UL voltage rating", "SELV voltage", 0.8, "violation", "3.5 V <= 480 V"),
           ck("I 80 %", "Contact current, 24-circuit 30 AWG W-B", "Contact current, J4.3 v3v3", 0.8, "violation",
              f"{itot:.0f} mA <= 800 mA (the lowest derating cell)")],
          "Voltage and per-contact current <= 80 % of the lowest applicable rating (the JST VH rule); the UL 1977 / CSA basis applies.")


def main():
    do_resistors()
    do_caps()
    do_ics()
    do_discretes()
    RES.mkdir(exist_ok=True)
    for k, v in OUT.items():
        v["datasheet"] = dict(DS[v["datasheet_key"]])
    (RES / "signal_audit.json").write_text(json.dumps(OUT, indent=1) + "\n")
    (RES / "signal_audit.md").write_text("\n".join(lines_md) + "\n")
    print(f"{len(OUT)} ledger lines prepared; {len(lines_md)} md lines")


if __name__ == "__main__":
    main()
