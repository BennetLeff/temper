#!/usr/bin/env python3
"""Item 2: full census of DC currents returned through the OCP Kelvin net (ocp_kelvin_p) on s47, and the trip shift.

    python3 -I kelvin_census.py [PS_DIR]   -> ../results/kelvin_census.json, ../results/kelvin_census.md

Read-only on PS. Method = the committed kelvin_budget.py (imported read-only; nothing written into PS):
    e_th = sum_j I_j * T_j     T_j = plane-native21s47.json transfer (mOhm at R35.2 per A returned at pad j, sink R5.2)
    trip shift = e_th * dI/de_th (-1.037 A/mV, same file);  bound = sum I_j * max T (152.90 mOhm, at R35.2)
Census membership comes from the frozen netlist (native-21/frozen/default.net): every node on ocp_kelvin_p, and every
node on hot5 (whose current must come back through ocp_kelvin_p; U3 OUT -> loads -> their ground pins).
Currents are datasheet maxima over temperature; page cites per row. HOT5 = 5.25 V as in the committed census
(conservative against the 5.11 V Q1-grade top; the 5.5 V physical-window row is a sensitivity).
"""
import sys
sys.dont_write_bytecode = True
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = Path(sys.argv[1] if len(sys.argv) > 1 else
          "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
OUT = HERE.parent / "results"
K = PS / "validation-results/02-protection-timing/kelvin"
sys.path.insert(0, str(HERE))
import netq  # noqa: E402  (this folder; KiCad netlist parser)

spec = importlib.util.spec_from_file_location("kb", K / "kelvin_budget.py")
kb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kb)        # top level only defines tables; main() (which writes) is not called
plane = json.loads((K / "plane-native21s47.json").read_text())
T = plane["transfer_mohm_to_R35_2"]
A_PER_MV = plane["trip_shift_A_per_mV_at_R35_2"]
TMAX = plane["max_transfer"]["mohm"]
committed = json.loads((K / "budget-native21s47.json").read_text())

HOT5 = 5.25
VR_MIN = 2.4838            # LM4050AEM3-2.5 VR min over -40..125 C (SNOS455H 5.6 p.7)
VR_MAX = 2.5162
R31 = 5.6e3 * 0.99         # 5.6 k 1 % low

# pad, mA, what, datasheet basis (page)
CENSUS = [
    ("U3.2", 0.1, "TPS70950 ground-pin current; over-bound kept from the committed census",
     "SBVS186H 6.5 p.5: IGND 2.25 uA max at IOUT 0; 350 uA typ (no max) at 150 mA, so ~35 uA typ at the ~15 mA load"),
    ("U4.4", 9.7, "AMC1311B IDD1 (GND1 return; SHTDN pin U4.3 tied to GND1, its <= 70 uA pull current is inside IDD1)",
     "SBAS786C 6.10 p.11: IDD1 9.7 mA max, 4.5 V < VDD1 < 5.5 V, SHTDN low; SHTDN IIN -70..1 uA (same table)"),
    ("U9.1", 4.1, "CA-IS3720HW IDDA (GNDA pins U9.1 / U9.7), healthy state: INA = bus_fault_hot low (VIN = 0 V, "
     "H version); unused INB floats to its default-high (low-current) state",
     "Chipanalog CA-IS372x v1.05 7.9.1 p.11 (EN v1.02 p.11 same table): IDDA 4.1 max, 'VIN = 0V (CA-IS3720H)', "
     "VDDA = VDDB = 5 V +-10 %, TA -40..125 C. Fault state (VIN = VDDA) 1.3 mA max"),
    ("U6.2", 0.065, "TLV3201 IQ (OCP comparator)", "SBOS561C 6.5 p.5: IQ 65 uA max, TA -40..125 C, VCC 5 V"),
    ("U7.2", 0.065, "TLV3201 IQ (OVP comparator)", "SBOS561C 6.5 p.5"),
    ("U8.2", 0.010, "SN74LVC1G10 ICC", "SCES486E p.4: ICC 10 uA max, VI = 5.5 V or GND"),
    ("U8.2", 0.015, "SN74LVC1G10 input leakage, 3 inputs driven from HOT5-powered outputs (U6, U7, U15)",
     "SCES486E p.4: II +-5 uA max each"),
    ("U15.3", 0.010, "SN74LVC1G17 ICC", "SCES351Y p.6: ICC 10 uA max"),
    ("U15.3", 0.005, "SN74LVC1G17 input leakage (A from hot5_uv_raw)", "SCES351Y p.6: II +-5 uA"),
    ("U14.2", 0.013, "TPS3700 IDD (supplied from V15_LS, returned on ocp_kelvin_p)",
     "SBVS187G 6.5 p.6: IDD 13 uA max at VDD 18 V"),
    ("U14.2", HOT5 / (10e3 * 0.99) * 1e3, "R50 10 k pull-up into OUTA, only while OUTA asserts (HOT5 UV); 0 in "
     "normal running (OUTA open-drain released). Kept at its asserted value, as committed",
     "R50 10 k 1 %; SBVS187G Table 1 p.10 (INA+ > VIT+ -> OUTA high, released)"),
    ("U5.2", (HOT5 - VR_MIN) / R31 * 1e3 - VR_MAX / (24.3e3 * 0.999) * 1e3 - VR_MAX / (150e3 * 0.999) * 1e3,
     "R31 current less the two threshold strings: U5 cathode current plus the R32/R33 string. The R32/R33 share "
     "(~0.133 mA) actually returns via ocp_kelvin_n into R5.3 and never crosses the plane: kept here (conservative)",
     "R31 5.6 k 1 %; LM4050AEM3 VR min 2.4838 V (SNOS455H 5.6 p.7)"),
    ("R35.2", VR_MAX / (24.3e3 * 0.999) * 1e3, "R34/R35 OCP-threshold string, returned at R35.2 (the probe pad)",
     "R34 12.6 k + R35 11.7 k, 0.1 %; VR max 2.5162 V"),
    ("R37.2", VR_MAX / (150e3 * 0.999) * 1e3, "R36/R37 OVP-threshold string, returned at R37.2",
     "R36 10 k + R37 140 k, 0.1 %; VR max 2.5162 V"),
    ("R49.2", HOT5 / (115e3 * 0.99) * 1e3, "HOT5 UV divider R48 105 k + R49 10 k", "power_stage_120v.ato; as committed"),
    ("R30.2", 400 / (4 * 470e3 * 0.99 + 15.8e3 * 0.999) * 1e3, "bus divider at 400 V (above the 287.62 V OVP top; "
     "kept as committed). U4 VIN input bias (+-15 nA, SBAS786C p.10) is inside this", "power_stage_120v.ato r_div_top x4 / r_div_bot"),
]
# Loads that are on the nets but carry no DC return (listed so the census is complete):
NO_DC = {
    "C25 C26 C27 C28 C30 C31 C32 C33 C34 C35 C36 C48 C49 C149": "decoupling / filter capacitors: MLCC insulation-"
    "resistance leakage is nA-class (e.g. 5.5 V / 10 GOhm = 0.55 nA); not counted",
    "U6/U7 inputs (ocp_node, ocp_thresh, ovp_thresh, vsense_in)": "TLV3201 IIB <= 5 nA (SBOS561C 6.5 p.5); inside the "
    "divider strings above",
    "U14.4 (INB-)": "TPS3700 I(INB-) <= 15 nA (SBVS187G p.6); OUTB unloaded (net outb has only U14.6)",
    "U9.4 (INA)": "CA-IS372x IIL <= 20 uA (7.8.1 p.10): flows out of U9.4 into U8.Y and returns at U8.2; it is part of "
    "the 4.1 mA IDDA test at VIN = 0 V, so it is not added again (U8.2 transfer 150.72 vs U9.1 150.00 mOhm: < 0.02 uV)",
}


def main():
    nets, _ = netq.load(PS / "native-21/frozen/default.net")
    kel = sorted(f"{r}.{p}" for r, p, *_ in nets["ocp_kelvin_p"])
    hot5 = sorted(f"{r}.{p}" for r, p, *_ in nets["hot5"])
    counted_refs = {pad.split(".")[0] for pad, *_ in CENSUS} | {"R5", "U9", "U4", "U14", "U8", "U15"}
    caps = {x.split(".")[0] for x in kel if x.startswith("C")}
    uncovered = sorted({x.split(".")[0] for x in kel} - counted_refs - caps - {"R5"})
    assert not uncovered, f"ocp_kelvin_p members not in the census: {uncovered}"
    hot5_refs = {x.split(".")[0] for x in hot5} - {"U3"} - {x.split(".")[0] for x in hot5 if x.startswith("C")}
    # every HOT5 consumer returns on the plane: U4, U6, U7, U8, U9, U15 directly; R31 (U5 + strings); R48 (R49.2);
    # R50 (U14.2 when asserted)
    assert hot5_refs <= {"U4", "U6", "U7", "U8", "U9", "U15", "R31", "R48", "R50"}, hot5_refs
    rows, e, i_tot = [], 0.0, 0.0
    for pad, ma, what, src in CENSUS:
        t = T[pad]
        mv = ma * 1e-3 * t
        e += mv
        i_tot += ma
        rows.append({"pad": pad, "mA": round(ma, 4), "transfer_mohm": t, "mV_at_R35_2": round(mv, 4), "what": what,
                     "source": src})
    shift = e * A_PER_MV
    bound_mv = i_tot * 1e-3 * TMAX
    # control: the committed census reproduces budget-native21s47.json
    ce = sum(ma * 1e-3 * T[pad] for pad, ma, *_ in kb.CENSUS21)
    assert abs(round(ce, 4) - committed["e_th_mV"]) < 1e-4, (ce, committed["e_th_mV"])
    assert abs(round(ce * A_PER_MV, 3) - committed["trip_shift_A"]) < 1e-3
    u9_only = (4.1 - 2.4) * 1e-3 * T["U9.1"]
    lo_before = kb.BAND_BEFORE["native21s47"][0]
    # c28 band (bands-s47.md:24) for the same shift
    c28_lo_before = 67.57
    out = {
        "plane": {"board_sha256": plane["board_sha256"], "sink": plane["sink"], "probe": plane["probe"],
                  "A_per_mV": A_PER_MV, "max_transfer_mohm": TMAX},
        "netlist_members": {"ocp_kelvin_p": kel, "hot5": hot5},
        "committed": {"total_mA": committed["total_mA"], "e_th_mV": committed["e_th_mV"],
                      "trip_shift_A": committed["trip_shift_A"], "bound": committed["bound_all_at_max_transfer"]},
        "rows": rows, "no_dc_return": NO_DC,
        "total_mA": round(i_tot, 3), "e_th_mV": round(e, 4), "trip_shift_A": round(shift, 3),
        "bound_all_at_max_transfer": {"e_th_mV": round(bound_mv, 4), "trip_shift_A": round(bound_mv * A_PER_MV, 3)},
        "delta_vs_committed": {"mA": round(i_tot - committed["total_mA"], 3), "mV": round(e - committed["e_th_mV"], 4),
                               "A": round(shift - committed["trip_shift_A"], 3)},
        "u9_iso7710_to_ca_is3720_only": {"mA": 1.7, "mV": round(u9_only, 4), "A": round(u9_only * A_PER_MV, 3)},
        "band_after": {
            "release c17.5 (68.87 before)": {"census": round(lo_before + shift, 2),
                                             "margin_census": round(lo_before + shift - 64.17, 2),
                                             "bound": round(lo_before + bound_mv * A_PER_MV, 2),
                                             "margin_bound": round(lo_before + bound_mv * A_PER_MV - 64.17, 2)},
            "c28 (67.57 before)": {"census": round(c28_lo_before + shift, 2),
                                   "margin_census": round(c28_lo_before + shift - 64.17, 2),
                                   "bound": round(c28_lo_before + bound_mv * A_PER_MV, 2),
                                   "margin_bound": round(c28_lo_before + bound_mv * A_PER_MV - 64.17, 2)}},
        "normal_running_credit": {"R50 not asserted": round(-rows[10]["mV_at_R35_2"] * A_PER_MV, 3)},
        "sensitivity_hot5_5p5V": None,
    }
    # HOT5 = 5.5 V sensitivity (physical window top): R31, R49 and R50 currents scale
    d = 0.0
    for pad, ma, what, src in CENSUS:
        if pad in ("U5.2",):
            ma2 = (5.5 - VR_MIN) / R31 * 1e3 - VR_MAX / (24.3e3 * 0.999) * 1e3 - VR_MAX / (150e3 * 0.999) * 1e3
        elif pad == "R49.2":
            ma2 = 5.5 / (115e3 * 0.99) * 1e3
        elif pad == "U14.2" and ma > 0.1:
            ma2 = 5.5 / (10e3 * 0.99) * 1e3
        else:
            ma2 = ma
        d += ma2 * 1e-3 * T[pad]
    out["sensitivity_hot5_5p5V"] = {"e_th_mV": round(d, 4), "trip_shift_A": round(d * A_PER_MV, 3)}
    OUT.mkdir(exist_ok=True)
    (OUT / "kelvin_census.json").write_text(json.dumps(out, indent=1) + "\n")
    L = ["| pad | mA (max) | mOhm to R35.2 | mV at R35.2 | what | datasheet basis |", "|---|---:|---:|---:|---|---|"]
    L += [f"| {r['pad']} | {r['mA']} | {r['transfer_mohm']} | {r['mV_at_R35_2']} | {r['what']} | {r['source']} |" for r in rows]
    L.append(f"| **total** | **{out['total_mA']}** | | **{out['e_th_mV']}** | trip shift **{out['trip_shift_A']} A** "
             f"(committed {committed['trip_shift_A']}); bound {out['bound_all_at_max_transfer']['trip_shift_A']} A | |")
    (OUT / "kelvin_census.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(json.dumps({k: out[k] for k in ("delta_vs_committed", "u9_iso7710_to_ca_is3720_only", "band_after",
                                          "normal_running_credit", "sensitivity_hot5_5p5V")}, indent=1))


if __name__ == "__main__":
    main()
