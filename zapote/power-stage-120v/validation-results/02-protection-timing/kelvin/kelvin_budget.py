#!/usr/bin/env python3
"""Shunt-OCP trip shift from HOT-side current returning on the Kelvin net (native-20).

Combines the plane solve (`plane-native20.json`, kelvin_plane.py: mOhm that 1 A
returned at each pad raises at R35.2 relative to R5.2) with a census of DC
currents returned at each pad, at datasheet maxima and HOT5 = 5.25 V (MC78L05AC
maximum). e_th = sum I_j T_j; trip shift = e_th * dI/de_th (about -1.03 A/mV).
A positive e_th lowers the trip, so the shift is applied to the band minimum.
`retune.py` (D-31) gives the band before this shift: 49.73-97.98 A.

Census: CENSUS below (pad, mA, what, source).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOT5 = 5.25
CENSUS = [  # pad, mA, what, source
    ("U3.2", 6.0 + 1.5 + 0.1, "MC78L05AC input bias (ground-pin) current, 25 C max 6.0 mA + line (1.5) + load (0.1) change",
     "onsemi MC78L00A/D p2, table MC78L05AC; committed validation-results/03-loss-thermal-budget/round3/sources/mc78l00a.pdf"),
    ("U4.3", 9.7, "AMC1311B IDD1, 4.5 V < VDD1 < 5.5 V, max", "TI SBAS781 (amc1311.pdf) 6.10 Electrical Characteristics, IDD1"),
    ("U9.1", 2.4, "ISO7710 ICC1, 5 V supply, DC signal, max (input state that draws more)", "TI iso7710.pdf 5.10, ICC1 DC"),
    ("U6.2", 0.065, "TLV3201 IQ max, -40..125 C", "TI tlv3201.pdf, IQ"),
    ("U7.2", 0.065, "TLV3201 IQ max, -40..125 C", "TI tlv3201.pdf, IQ"),
    ("U8.2", 0.010, "SN74LVC1G10 ICC max", "TI sn74lvc1g10.pdf, ICC"),
    ("U15.3", 0.010, "SN74LVC1G17 ICC max", "TI sn74lvc1g17.pdf, ICC"),
    ("U14.2", 0.013 + HOT5 / (10e3 * 0.99) * 1e3, "TPS3700 IDD max (VDD 18 V) + 10 k pull-up when OUTA asserted low",
     "TI tps3700.pdf, IDD; r_hot5_uv_pull 10 k 1 %"),
    ("U5.2", (HOT5 - 2.5) / (5.6e3 * 0.99) * 1e3, "all current through the 5.6 k reference bias (LM4040 + dividers), bounded as returned at the anode",
     "r_ref_bias 5.6 k 1 %; LM4040 2.5 V"),
    ("R49.2", HOT5 / (115e3 * 0.99) * 1e3, "HOT5 UV divider 105 k + 10 k", "power_stage_120v.ato r_hot5_uv_top/bot"),
    ("R30.2", 400 / (4 * 470e3 * 0.99 + 15.8e3 * 0.999) * 1e3, "bus divider at 400 V (above the 280 V maximum)", "power_stage_120v.ato r_div_top x4 / r_div_bot"),
]


# Native-21 replaces the MC78L05 HOT5 regulator (U3) with a TPS70950 (D-33, native-21/ECO.md):
# its ground-pin current is in the microamp range; 0.1 mA here is a deliberate over-bound.
CENSUS21 = [row if row[0] != "U3.2" else
            ("U3.2", 0.1, "TPS70950 ground-pin current, over-bounded at 0.1 mA (datasheet IQ is microamp-class)",
             "TI tps709.pdf (native-21/ECO.md sources)") for row in CENSUS]
# Stage 48 correction (11-candidates/band-terms-2026-10-15/results/kelvin_census.md): U9 has been the CA-IS3720HW since stage 31
# (DECISIONS 34), not the ISO7710 the row still carried (2.4 mA). Its side-A supply current returns on GNDA (U9.1 / U9.7).
CENSUS21 = [row if row[0] != "U9.1" else
            ("U9.1", 4.1, "CA-IS3720HW IDDA max, healthy state: INA = bus_fault_hot low (VIN = 0 V, H version), VDDA 5 V +-10 %, "
             "TA -40..125 C (fault state VIN = VDDA: 1.3 mA max)",
             "Chipanalog CA-IS372x v1.05 7.9.1 p.11 (EN v1.02 p.11, same table): IDDA 4.1 mA max, 'VIN = 0V (CA-IS3720H)'")
            for row in CENSUS21]
# Stage 48 (c48-ldo-en-ref-watch): two new returns on the Kelvin net, counted where the board has the pads (native21s48 on).
#  - R137.2: U3's EN divider (OPEN-ITEMS S19), R136 100 k / R137 27 k 1 % from V15_LS, at IN - GND 15.46 V max
#    (S16 rail model, s20-286v-recite 1.6);
#  - R145.2: the REF25 watchdog divider (B13 H1), R144 63.4 k + R145 11.7 k 0.1 % at VR max 2.5162 V. That current is also inside
#    the U5.2 row (all of R31's current, bounded at the anode), so it is counted twice: conservative by its 5 uV.
#  U14 VDD moves V15_LS -> HOT5 at stage 48; its IDD still returns at U14.2 (row unchanged), and U14.4 (INB-) leaves the net.
CENSUS48 = [
    ("R137.2", 15.46 / ((100e3 + 27e3) * 0.99) * 1e3, "U3 EN divider R136 100 k / R137 27 k from V15_LS (15.46 V max above GND)",
     "power_stage_120v.ato r_ldo_en_top / r_ldo_en_bot (0603WAF 1 %); IN - GND from the S16 rail model"),
    ("R145.2", 2.5162 / (75.1e3 * 0.999) * 1e3, "REF25 watchdog R144 63.4 k + R145 11.7 k (also inside the U5.2 bound)",
     "power_stage_120v.ato r_ref_wd_top / r_ref_wd_bot (0.1 %); LM4050AEM3 VR max 2.5162 V (SNOS455H 5.6 p.7)"),
]


BAND_BEFORE = {"native21s13": (49.53, 97.77), "native21s13b": (49.53, 97.77), "native21s14": (49.53, 97.77),
               "native21s15": (68.58, 118.74), "native21s15b": (68.58, 118.74), "native21s16": (68.58, 118.74),
               "native21s17": (69.89, 116.44), "native21s17b": (69.89, 116.44),
               "native21s18": (69.89, 116.44),
               "native21s19": (69.89, 116.44), "native21s19b": (69.89, 116.44), "native21s19c": (69.89, 116.44), "native21s20": (69.89, 116.44), "native21s21": (69.89, 116.44), "native21s21b": (69.89, 116.44), "native21s22": (69.89, 116.44), "native21s26": (69.89, 116.44), "native21s27": (69.89, 116.44), "native21s28": (69.89, 116.44), "native21s29": (69.89, 116.44), "native21s30": (69.89, 116.44), "native21s31": (69.89, 116.44), "native21s32": (69.89, 116.44), "native21s33": (69.89, 116.44), "native21s35": (69.89, 116.44), "native21s38": (69.89, 116.44), "native21s40": (69.89, 116.44), "native21s41": (69.89, 116.44), "native21s42": (69.89, 116.44), "native21s43": (69.89, 116.44), "native21s44": (69.89, 116.44), "native21s45": (69.89, 116.44), "native21s46": (69.89, 116.44),
               # s47: U5 LM4050AEM3-2.5 (+-15 mV + 1.2 mV over -40..125 C) with the network at its hot-copper B3 solve at the
               # c17.5 @ 61 release case (R32-R35 93-96 C, R5 element 124 C; the -10 C corner as before):
               # 11-candidates/c47-ref25-grade/scripts/bands47.py (committed -10/85 C basis: 70.01-116.27 A)
               "native21s47": (68.87, 117.45),
               # s48: the band network is unchanged (only the watchdog divider joins REF25, inside U5's current window)
               "native21s48": (68.63, 117.70),
               # s49 (S23 B'-1.02 V: R33 7.5 k, R34 16 k, R35 11 k): the committed bands47 engine with the B' divider and
               # S23's TLV3201 PSRR term (HOT5 Q1), R0 reading, on this board's own release solve (board 73702f18;
               # 11-candidates/c49-c34-bank/scripts/bands49.py -> results/bands-s49.json, band_basis_s49). The s48 entry
               # above is s48's own solve (328fe4edc, s23-ocp-cm-2026-10-16; it was the s47 solve 68.87-117.45 A before).
               "native21s49": (71.59, 114.58)}   # 12.6 k / 11.7 k (stage 15; scratchpad stage15/ocp_bands.py -> task 02); s17: R5 CSS2H 75 ppm (round5-native21/stage17-r5/ocp_band17.py)
# Low-corner floor after the shift. 44 A until stage 14; stage 15 (28 A ceiling): 59.17 A envelope peak + 3.0 A
# coil-pickup stack (DECISIONS item 9) + 2 A margin = 64.17 A (round 6 rule; basis A of the stage-15 plan).
FLOOR = {"native21s15": 64.17, "native21s15b": 64.17, "native21s16": 64.17, "native21s17": 64.17, "native21s17b": 64.17, "native21s18": 64.17, "native21s19": 64.17, "native21s19b": 64.17, "native21s19c": 64.17, "native21s20": 64.17, "native21s21": 64.17, "native21s21b": 64.17, "native21s22": 64.17, "native21s26": 64.17, "native21s27": 64.17, "native21s28": 64.17, "native21s29": 64.17, "native21s30": 64.17, "native21s31": 64.17, "native21s32": 64.17, "native21s33": 64.17, "native21s35": 64.17, "native21s38": 64.17, "native21s40": 64.17, "native21s41": 64.17, "native21s42": 64.17, "native21s43": 64.17, "native21s44": 64.17, "native21s45": 64.17, "native21s46": 64.17, "native21s47": 64.17, "native21s48": 64.17, "native21s49": 64.17}


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "native20"
    census = CENSUS21 if tag.startswith("native21") else CENSUS
    plane = json.loads((HERE / f"plane-{tag}.json").read_text())
    T = plane["transfer_mohm_to_R35_2"]
    if tag.startswith("native21"):
        census = census + [row for row in CENSUS48 if row[0] in T]
    a_per_mv = plane["trip_shift_A_per_mV_at_R35_2"]
    # Band before the Kelvin shift: D-31 retune (10.6 k / 10 k), or 12.4 k / 11.7 k from stage 13
    # (../../08-manufacturing-package/native-21/bom-simplification/calc_protection_bands.py).
    lo, hi = BAND_BEFORE.get(tag, (49.73, 97.98))
    rows, e = [], 0.0
    for pad, ma, what, src in census:
        mv = ma * 1e-3 * T[pad]        # mA * mOhm = uV -> here mA*1e-3 A * mOhm = mV
        e += mv
        rows.append({"pad": pad, "mA": round(ma, 4), "transfer_mohm": T[pad], "mV_at_R35_2": round(mv, 4), "what": what, "source": src})
    total_ma = sum(r["mA"] for r in rows)
    bound = total_ma * 1e-3 * plane["max_transfer"]["mohm"]
    res = {"rows": rows, "total_mA": round(total_ma, 3), "e_th_mV": round(e, 4), "trip_shift_A": round(e * a_per_mv, 3),
           "bound_all_at_max_transfer": {"e_th_mV": round(bound, 4), "trip_shift_A": round(bound * a_per_mv, 3)},
           "band_before_A": [lo, hi],
           "band_after_A": [round(lo + e * a_per_mv, 2), hi],
           "meets_44A_min": lo + e * a_per_mv >= 44.0,
           "floor_A": FLOOR.get(tag, 44.0),
           "meets_floor_at_bound": lo + bound * a_per_mv >= FLOOR.get(tag, 44.0),
           "note": "shift ranges from 0 (no load current) to the census value, so it widens the band downward"}
    (HERE / f"budget-{tag}.json").write_text(json.dumps(res, indent=1) + "\n")
    lines = ["| pad | mA (max) | mΩ to R35.2 | mV at R35.2 | what |", "| --- | ---: | ---: | ---: | --- |"]
    lines += [f"| {r['pad']} | {r['mA']} | {r['transfer_mohm']} | {r['mV_at_R35_2']} | {r['what']} |" for r in rows]
    lines.append(f"| **total** | **{res['total_mA']}** | | **{res['e_th_mV']}** | trip shift **{res['trip_shift_A']} A**; band {res['band_after_A'][0]}–{res['band_after_A'][1]} A |")
    (HERE / f"budget-{tag}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(json.dumps({k: res[k] for k in ("total_mA", "e_th_mV", "trip_shift_A", "bound_all_at_max_transfer", "band_after_A", "meets_44A_min", "floor_A", "meets_floor_at_bound")}))


if __name__ == "__main__":
    main()
