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


def main():
    plane = json.loads((HERE / "plane-native20.json").read_text())
    T = plane["transfer_mohm_to_R35_2"]
    a_per_mv = plane["trip_shift_A_per_mV_at_R35_2"]
    rows, e = [], 0.0
    for pad, ma, what, src in CENSUS:
        mv = ma * 1e-3 * T[pad]        # mA * mOhm = uV -> here mA*1e-3 A * mOhm = mV
        e += mv
        rows.append({"pad": pad, "mA": round(ma, 4), "transfer_mohm": T[pad], "mV_at_R35_2": round(mv, 4), "what": what, "source": src})
    total_ma = sum(r["mA"] for r in rows)
    bound = total_ma * 1e-3 * plane["max_transfer"]["mohm"]
    res = {"rows": rows, "total_mA": round(total_ma, 3), "e_th_mV": round(e, 4), "trip_shift_A": round(e * a_per_mv, 3),
           "bound_all_at_max_transfer": {"e_th_mV": round(bound, 4), "trip_shift_A": round(bound * a_per_mv, 3)},
           "band_before_A": [49.73, 97.98],
           "band_after_A": [round(49.73 + e * a_per_mv, 2), 97.98],
           "meets_44A_min": 49.73 + e * a_per_mv >= 44.0,
           "note": "shift ranges from 0 (no load current) to the census value, so it widens the band downward"}
    (HERE / "budget-native20.json").write_text(json.dumps(res, indent=1) + "\n")
    lines = ["| pad | mA (max) | mΩ to R35.2 | mV at R35.2 | what |", "| --- | ---: | ---: | ---: | --- |"]
    lines += [f"| {r['pad']} | {r['mA']} | {r['transfer_mohm']} | {r['mV_at_R35_2']} | {r['what']} |" for r in rows]
    lines.append(f"| **total** | **{res['total_mA']}** | | **{res['e_th_mV']}** | trip shift **{res['trip_shift_A']} A**; band {res['band_after_A'][0]}–{res['band_after_A'][1]} A |")
    (HERE / "budget-native20.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(json.dumps({k: res[k] for k in ("total_mA", "e_th_mV", "trip_shift_A", "bound_all_at_max_transfer", "band_after_A", "meets_44A_min")}))


if __name__ == "__main__":
    main()
