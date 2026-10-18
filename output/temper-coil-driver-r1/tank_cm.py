"""Coil common-mode (winding-mean) voltage and pan touch current: one-sided vs split resonant bank.

Series tank driven by a full bridge (legs 180 deg apart), bank C = 0.54 uF.
The coil winding potential runs linearly between its terminals, so its mean
potential (what couples to the pan and to PE) is the average of the two
terminal voltages:
  one-sided bank (native-21): terminals SW_A and SW_B + V_C -> mean = Vbus/2 + V_C/2
  split bank (2C each side):  terminals SW_A - V_C/2 and SW_B + V_C/2 -> mean = Vbus/2
The fundamental of (V_A + V_B) cancels for 180-deg legs, so the one-sided bank
leaves V_C/2 at the switching frequency on the whole winding.

Touch current through an earthed pan (user's hand) = w * C_wp * |V_mean,ac|,
with C_wp = 72.0 pF (70.1-81.2) winding-to-pan from enclosure study 16
(output/temper-r33-studies/16-coil-pe-capacitance/REPORT.md). Unweighted:
UL 101 / IEC 60990 frequency weighting would reduce the reading at 35-60 kHz;
that weighting is NOT applied here, so this is an upper-bound current, not a
compliance number. Run: python3 tank_cm.py -> tank_cm.json
"""
import json
from math import pi
from pathlib import Path

C_RES = 0.54e-6
C_WP = {"nominal": 72.0e-12, "low": 70.1e-12, "high": 81.2e-12}
PEAK_PER_RMS = 2.17          # firmware TANK_PEAK_PER_RMS (line-crest peak / line-average rms)
CEILINGS = {"22A_default": 22.0, "28A_commissioned": 28.0}


def main():
    rows = []
    for name, irms in CEILINGS.items():
        ipk = PEAK_PER_RMS * irms
        for fs in (35e3, 45e3, 60e3):
            w = 2 * pi * fs
            vc_pk = ipk / (w * C_RES)
            vmean_pk = {"one_sided": vc_pk / 2, "split": 0.0}
            r = {"ceiling": name, "fs_kHz": fs / 1e3, "tank_ipk_A": round(ipk, 1), "Vc_pk_V": round(vc_pk, 0)}
            for topo, v in vmean_pk.items():
                r[f"{topo}_Vmean_pk_V"] = round(v, 0)
                for k, c in C_WP.items():
                    r[f"{topo}_touch_mA_rms_{k}"] = round(w * c * v / 2**0.5 * 1e3, 2)
            rows.append(r)
    out = {"scope": __doc__.strip(), "rows": rows}
    Path(__file__).with_name("tank_cm.json").write_text(json.dumps(out, indent=1) + "\n")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
