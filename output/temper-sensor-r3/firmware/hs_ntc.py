"""sensor-r3 heatsink NTC (Vishay NTCALUG01A104GA on the zapote/controller thermal-sense
block, HS_SENSE -> HS_ADC, GPIO6 / ADC1_CH5): the firmware's R-T table, the channel's
numbers, and the cold-soak error budget (DECISIONS.md D-HSNTC, D-SOAK).

The board (zapote/controller, read-only; branch controller-layout 300b8a934 and
controller-c1-crs 1f39c1933 agree on every part below):
  - elec/src/thermal_block.ato ThermalSenseUnit: hs_fixed 10 k 1 % (RC0603FR-0710KL)
    from vcc to HS_SENSE, the NTC (heatsink_probe J, external NTCALUG01A104GA lug)
    from HS_SENSE to gnd, hs_filter 100 nF at the node. The TLV3201 hot comparator
    (HS_HOT) and the TLV9031 open comparator (HS_OPEN: HS_SENSE above
    OPEN_REF = vcc * 100 k / 101.21 k) OR into HS_FAULT, a hardware latch input;
  - elec/src/controller.ato: thermal.vcc ~ v3v3; r_hs_filt 10 k + c_hs_filt 100 nF
    into the TLV9062 follower U6B (DECISIONS C13, C29); r_hs_adc 100 R + c_hs_adc
    100 nF into HS_ADC; mcu.IO6 ~ hs_adc, i.e. GPIO6 = ADC1_CH5. (GPIO3, which the
    legacy temper_pins.h and elec/src name ADC_CHANNEL_NTC, is the blower tach,
    mcu.IO3 ~ fan_tach, on this board.)
  - DECISIONS C13: "values above ATTEN3's 2.9 V occur only cold or open".

What this does
1. Holds the R-T table: Vishay NTCLE100E3 data sheet (doc 29049), 100 k / B25/85 4190 K
   column (NTCLE100E3104, Vishay material D, curve 11), -40..150 degC in 5 K steps, with
   its TCR and "dR/R due to B tolerance" columns. The NTCALUG01A data sheet (doc 29092)
   has no R-T table: its ordering table gives NTCALUG01A104GA as 100 k +/- 2 %,
   B25/85 4190 K +/- 1.5 % and points to Vishay's curve computation; 4190 K +/- 1.5 %
   is material D (doc 29049 p. 4, curve 11), whose 100 k R-T table this is.
   - checks the table against material D's own A1..D1 polynomial (doc 29049 p. 4,
     "interchangeable with an error of max. 0.005 degC (25..125) / 0.015 degC (-40..25)")
     and B25/85 from the table against 4190 K;
   - `--verify-pdf ntcle100.pdf` re-extracts the column with pdftotext;
     `--verify-lug-pdf ntcalug01a.pdf` checks the ordering-table line;
     `--verify-esp-pdf esp32-s3_datasheet_en.pdf` checks Table 5-6 (ATTEN3 0..2900 mV,
     +/-50 mV).
2. Writes firmware/components/sensors/hs_ntc_table.h (deterministic).
3. Writes hs-ntc.json:
   - the driver's interpolation error (leave-one-out over 10 K) and the chain through
     whole-mV ADC readings;
   - the channel: node voltage, attenuation, mV/K, the ATTEN3 saturation temperature
     over the v3v3 contract range, the short threshold, the over-temperature trip points;
   - the cold-soak error budget: the false-latch stack (heatsink reads high, Pt100 reads
     low, soak residual, standby offset) and the miss stack (the other way) over the band
     where the check can run (the heatsink channel VALID .. 45 degC), and the threshold
     the firmware uses (PCS_THRESHOLD_K, gated against pan_cold_soak.h);
   - the soak timing argument (N, W, flatness, residual bound).
   Exits 1 if a check fails.

Run: python3 hs_ntc.py [--verify-pdf ntcle100.pdf] [--verify-lug-pdf ntcalug01a.pdf]
                       [--verify-esp-pdf esp32-s3_datasheet_en.pdf]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
HEADER = REPO / "firmware" / "components" / "sensors" / "hs_ntc_table.h"
SOAK_H = REPO / "firmware" / "components" / "control" / "pan_cold_soak.h"

SOURCES = {
    "table": "Vishay NTCLE100E3 data sheet, document 29049, revision 07-May-2025, page 12 'Resistance "
             "values at intermediate temperatures with R25 at (33, 47, 50, 68, 100) kOhm', column "
             "NTCLE100E3104*** (100 kOhm, B25/85 4190 K), with its TCR and 'dR/R due to Btol.' columns; "
             "page 4 'Parameter for determining nominal resistance values', number 11, Mat. D, "
             "B25/85 4190 K +/- 1.5 %. https://www.vishay.com/docs/29049/ntcle100.pdf, retrieved "
             "2026-10-15, sha256 f9d6153738198dc705ed681c3b55e70a6571f8fee13a4ed7b2b41e49973cb9c9.",
    "part": "Vishay NTCALUG01A series data sheet, document 29092, revision 14-Jan-2026, page 2 ordering "
            "table: 100 000 Ohm, R25 tol. +/-2 %, B25/85 4190 K, B tol. +/-1.5 %, NTCALUG01A104GA (e4); "
            "page 1: -55..+150 degC, thermal time constant 5 s and dissipation factor 13 mW/K screwed "
            "on a 100 cm2 aluminium plate; no R-T table (it points to Vishay's NTC curve computation). "
            "https://www.vishay.com/docs/29092/ntcalug01a.pdf, retrieved 2026-10-15, sha256 "
            "a14f8704e47b483de359bbfc3195d9a2be002215fef82dfd00326cd2f717189b.",
    "adc": "Espressif ESP32-S3 Series Datasheet version 2.2, Table 5-6 'ADC Calibration Results': "
           "ATTEN3, effective measurement range of 0 ~ 2900 mV, total error -50..+50 mV (ATTEN0 "
           "0 ~ 850 +/-5, ATTEN2 0 ~ 1600 +/-10). https://www.espressif.com/sites/default/files/"
           "documentation/esp32-s3_datasheet_en.pdf, retrieved 2026-10-15, sha256 "
           "2d5a7cb7fd559d8d972bd88db32669c0196d23f22d7afaafb0f63d099b589a3f.",
    "board": "zapote/controller (read-only), controller-layout 300b8a934 = controller-c1-crs 1f39c1933 "
             "for these parts: thermal_block.ato hs_fixed 10 k 1 % RC0603FR-0710KL vcc->HS_SENSE, NTC "
             "HS_SENSE->gnd, hs_filter 100 nF; controller.ato r_hs_filt 10 k / c_hs_filt 100 nF -> "
             "TLV9062 U6B follower -> r_hs_adc 100 R / c_hs_adc 100 nF -> HS_ADC, mcu.IO6 ~ hs_adc "
             "(GPIO6 = ADC1_CH5), thermal.vcc ~ v3v3 (TPS62933 3.242-3.367 V, pcb/checks.py SRC v3v3).",
}

# NTCLE100E3104: R (kOhm), TCR (%/K), dR/R due to B tolerance (%), doc 29049 p. 12 (transcribed).
VISHAY_104_KOHM = {
    -40: 3666, -35: 2638, -30: 1917, -25: 1406, -20: 1041, -15: 777.8, -10: 586.1, -5: 445.3,
    0: 340.9, 5: 263.1, 10: 204.4, 15: 160.0, 20: 126.1, 25: 100.0, 30: 79.81, 35: 64.08, 40: 51.75,
    45: 42.02, 50: 34.31, 55: 28.16, 60: 23.22, 65: 19.25, 70: 16.02, 75: 13.40, 80: 11.26, 85: 9.496,
    90: 8.042, 95: 6.837, 100: 5.835, 105: 4.998, 110: 4.296, 115: 3.705, 120: 3.206, 125: 2.783,
    130: 2.423, 135: 2.116, 140: 1.854, 145: 1.628, 150: 1.434,
}
VISHAY_104_TCR = {
    -40: -6.69, -35: -6.49, -30: -6.29, -25: -6.10, -20: -5.92, -15: -5.75, -10: -5.58, -5: -5.42,
    0: -5.26, 5: -5.11, 10: -4.97, 15: -4.83, 20: -4.70, 25: -4.57, 30: -4.45, 35: -4.33, 40: -4.22,
    45: -4.11, 50: -4.00, 55: -3.90, 60: -3.80, 65: -3.71, 70: -3.62, 75: -3.53, 80: -3.45, 85: -3.36,
    90: -3.28, 95: -3.21, 100: -3.13, 105: -3.06, 110: -2.99, 115: -2.93, 120: -2.86, 125: -2.80,
    130: -2.74, 135: -2.68, 140: -2.62, 145: -2.57, 150: -2.51,
}
VISHAY_104_BTOL_PCT = {
    -40: 5.88, -35: 5.31, -30: 4.77, -25: 4.25, -20: 3.75, -15: 3.27, -10: 2.80, -5: 2.36, 0: 1.93,
    5: 1.52, 10: 1.12, 15: 0.73, 20: 0.36, 25: 0.00, 30: 0.35, 35: 0.68, 40: 1.01, 45: 1.33, 50: 1.63,
    55: 1.93, 60: 2.21, 65: 2.49, 70: 2.76, 75: 3.03, 80: 3.28, 85: 3.53, 90: 3.77, 95: 4.01, 100: 4.24,
    105: 4.46, 110: 4.68, 115: 4.89, 120: 5.09, 125: 5.29, 130: 5.49, 135: 5.68, 140: 5.87, 145: 6.05,
    150: 6.23,
}
# Material D (number 11) inverse polynomial, doc 29049 p. 4: 1/T = A1 + B1 ln(R/R25) + C1 ln^2 + D1 ln^3
MAT_D_INV = (3.354016e-03, 2.460382e-04, 3.405377e-06, 1.034240e-07)
B25_85_K = 4190.0
R25_TOL = 0.02          # NTCALUG01A104G: +/- 2 %
B_TOL = 0.015           # +/- 1.5 %

# Board
R_PULLUP = 10000.0      # hs_fixed 10 k 1 %
R_PULLUP_TOL = 0.01
R_PULLUP_TC = 100e-6    # RC0603FR (Yageo RC series) +/-100 ppm/K
BOARD_DT_K = 20.0       # board within 25 +/- 20 degC at soak (assumption)
V3V3_NOM, V3V3_MIN, V3V3_MAX = 3.300, 3.242, 3.367
ATTEN = ((0, 0.800, 0.850, 0.005), (2, 1.550, 1.600, 0.010), (3, None, 2.900, 0.050))  # CR-7 rule, FS, error
SHORT_BELOW_V = 0.25
BUF_VOS_V = 0.002       # TLV9062 follower offset allowance (assumption: TLV906x VOS +/-1.6 mV max at 25 C)
NTC_DISSIPATION_W_PER_K = 13e-3   # doc 29092 p. 1, on a 100 cm2 plate
OPEN_REF_FRAC = 100.0 / 101.21    # thermal_block.ato open_top 1.21 k / open_bottom 100 k
# The firmware's over-temperature uses of read_heatsink_temperature() (state_machine.c,
# state_handlers.c, config.yaml): 70 recovery, 95 OVER_TEMP_THRESHOLD (zapote DECISIONS C32; was 80),
# 125 FAULT_STATE_MAX_TEMP_C. 80 stays in the list as the earlier trip.
TRIP_POINTS_C = (50.0, 70.0, 80.0, 95.0, 125.0)

# Pt100 chain at soak (the other side of the comparison)
PT_CLASS_K = lambda t: 0.15 + 0.002 * abs(t)          # IST P0K1.202 class F0.15 (bench/bom.py), IEC 60751
PT_RREF_FRAC = 0.001 + 25e-6 * BOARD_DT_K             # captured Rref RT0805BRD 0.1 %, 25 ppm/K (pcb SRC)
PT_OFFSET_LSB = 3                                       # MAX31865 offset +/-3 LSB max (pcb SRC)
PT_LSB_OHM = 430.0 / 32768
PT_SH_CORR_K = 0.061                                    # rtd_convert self_heating_k, subtracted always
# Off-pan self-heating of the element at idle: P = (VBIAS/(Rref+R))^2 R into G_cold
# (cartridge-budget.json G_cold 0.553 mW/K). Reads high; counts only against detection.
VBIAS = 2.0
G_COLD_W_PER_K = 0.553e-3

# Soak timing (DECISIONS.md D-SOAK). Time constants (none measured; bench items):
#   glass 4 mm CERAN, rho 2550, c 800 (bench/plate_check.py:36) -> 8160 J/m2K; h 10 W/m2K
#   (cad/thermal_axisym.py h_eye) on one face 816 s, both faces 408 s;
#   heatsink ~1 kg aluminium (~900 J/K, plans/2026-07-16-001:118) at 0.5 K/W natural
#   convection (BOM.md HS1) 450 s;
#   cartridge off-pan 50-73 s, slaved to the glass (screen-results.json tau_off).
TAU_EST_S = {"glass_one_face": 816.0, "glass_two_faces": 408.0, "heatsink_fan_off": 450.0,
             "cartridge_off_pan": 73.0}
TAU_MAX_S = 1800.0      # >= 2x every estimate: the bound the flatness tests are sized for
SOAK_N_S = 1800.0       # coil off >= 30 min
WINDOW_S = 900.0        # flatness window 15 min
HS_FLAT_K = 1.0         # heatsink max - min over the window
PT_FLAT_K = 0.25        # Pt100 max - min over the window
STANDBY_OFFSET_K = 1.0  # heatsink above room at idle from the bay's standby dissipation (assumption)
HS_MAX_C = 45.0         # above: not a soaked unit in a 5-40 degC room
COOK_SINK_C = 88.6      # airflow-r1 DECISIONS sink setpoint at full power
AMBIENTS = (5.0, 15.0, 25.0, 30.0, 35.0, 40.0)


def r_table(t: float) -> float:
    return VISHAY_104_KOHM[int(t)] * 1e3


def t_of_r(r: float, pts=None) -> float:
    """The driver's rule: 1/T linear in ln R between neighbouring points (nan outside)."""
    pts = pts or VISHAY_104_KOHM
    ks = sorted(pts)
    for a, b in zip(ks, ks[1:]):
        ra, rb = pts[a] * 1e3, pts[b] * 1e3
        if ra >= r >= rb:
            ia, ib = 1.0 / (a + 273.15), 1.0 / (b + 273.15)
            return 1.0 / (ia + (math.log(r) - math.log(ra)) * (ib - ia) / (math.log(rb) - math.log(ra))) - 273.15
    return math.nan


def r_of_t(t: float) -> float:
    ks = sorted(VISHAY_104_KOHM)
    for a, b in zip(ks, ks[1:]):
        if a <= t <= b:
            ia, ib, it = 1 / (a + 273.15), 1 / (b + 273.15), 1 / (t + 273.15)
            la, lb = math.log(r_table(a)), math.log(r_table(b))
            return math.exp(la + (lb - la) * (it - ia) / (ib - ia))
    raise ValueError(t)


def btol_frac(t: float) -> float:
    """dR/R from the B tolerance, interpolated from the data-sheet column."""
    ks = sorted(VISHAY_104_BTOL_PCT)
    for a, b in zip(ks, ks[1:]):
        if a <= t <= b:
            return (VISHAY_104_BTOL_PCT[a] + (t - a) / (b - a) * (VISHAY_104_BTOL_PCT[b] - VISHAY_104_BTOL_PCT[a])) / 100
    raise ValueError(t)


def mat_d_t(r: float) -> float:
    a1, b1, c1, d1 = MAT_D_INV
    x = math.log(r / 100e3)
    return 1.0 / (a1 + b1 * x + c1 * x * x + d1 * x ** 3) - 273.15


def node_v(t: float, vdd: float = V3V3_NOM, r_scale: float = 1.0, rpu_scale: float = 1.0) -> float:
    r = r_of_t(t) * r_scale
    rp = R_PULLUP * rpu_scale
    return vdd * r / (r + rp)


def t_from_node(v: float, vdd_assumed: float = V3V3_NOM) -> float:
    x = v / vdd_assumed
    return t_of_r(R_PULLUP * x / (1 - x)) if 0 < x < 1 else math.nan


def atten_for(v: float):
    for a, below, fs, err in ATTEN:
        if below is None or v < below:
            return a, fs, err
    raise AssertionError


def solve_t(f, lo=-40.0, hi=149.9):
    """Root of f, increasing in T, by bisection."""
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    return 0.5 * (lo + hi)


def hs_errors(t: float):
    """Heatsink channel error terms at true temperature t (K, magnitude; each can go
    either way). Rail is reported per direction."""
    v = node_v(t)
    slope = (node_v(t - 0.05) - node_v(t + 0.05)) / 0.1    # V/K (falls with T)
    a, fs, err = atten_for(v)
    tcr = abs(r_of_t(t - 0.05) - r_of_t(t + 0.05)) / 0.1 / r_of_t(t)   # 1/K
    terms = {
        "ntc_R25_2pct": R25_TOL / tcr,
        "ntc_B_1p5pct": btol_frac(t) / tcr,
        "pullup_1pct_100ppm": (R_PULLUP_TOL + R_PULLUP_TC * BOARD_DT_K) / tcr,
        "adc_total_error": err / slope,
        "buffer_vos": BUF_VOS_V / slope,
        "ntc_self_heating": (V3V3_NOM / (r_of_t(t) + R_PULLUP)) ** 2 * r_of_t(t) / NTC_DISSIPATION_W_PER_K,
    }
    # rail: the driver divides by 3300 mV; true v3v3 at the contract limits
    hi = t_from_node(node_v(t, V3V3_MIN)) - t     # rail low  -> reads high
    lo = t_from_node(node_v(t, V3V3_MAX)) - t     # rail high -> reads low
    return terms, {"rail_low_reads_high": hi, "rail_high_reads_low": -lo}, v, slope, a


def pt_low_stack(t: float):
    r = 100 * (1 + 3.9083e-3 * t - 5.775e-7 * t * t)
    dr = 0.3851  # ohm/K near room
    return {"class_F0.15": PT_CLASS_K(t), "rref_0.1pct_25ppm": PT_RREF_FRAC * r / dr,
            "max31865_offset_3lsb": PT_OFFSET_LSB * PT_LSB_OHM / dr, "self_heating_correction": PT_SH_CORR_K}


def pt_off_pan_self_heating(t: float) -> float:
    r = 100 * (1 + 3.9083e-3 * t - 5.775e-7 * t * t)
    i = VBIAS / (430.0 + r)
    return i * i * r / G_COLD_W_PER_K


def residual(flat_k: float, tau: float = TAU_MAX_S, w: float = WINDOW_S) -> float:
    """Largest distance from the final value of a single exponential whose change over
    the last w seconds is at most flat_k: e = flat / (exp(w / tau) - 1)."""
    return flat_k / (math.exp(w / tau) - 1.0)


def verify_pdf(pdf: Path) -> list[str]:
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
    lines = txt.splitlines()
    i = next(k for k, l in enumerate(lines) if "WITH R25 AT (33, 47, 50, 68, 100)" in l)
    got = {}
    for l in lines[i:i + 60]:
        m = re.match(r"^\s*(-?\d+)\s+([\d.\s-]+)$", l)
        if m and len(m.group(2).split()) == 9:
            v = m.group(2).split()
            got[int(m.group(1))] = (float(v[6]), float(v[7]), float(v[8]))
    bad = []
    for t in VISHAY_104_KOHM:
        g = got.get(t)
        want = (VISHAY_104_KOHM[t], VISHAY_104_TCR[t], VISHAY_104_BTOL_PCT[t])
        if g is None or any(abs(x - y) > 1e-9 * max(1.0, abs(y)) for x, y in zip(g, want)):
            bad.append(f"{t}: pdf {g} vs transcribed {want}")
    j = next(k for k, l in enumerate(lines) if "Bn = 4190K" in l)
    if not any("4190" in l and "1.5" in l and "5459.339" in l and "2.460382E-04" in l for l in lines[j - 2:j + 1]):
        bad.append("material D (11) row not found")
    return bad


def verify_lug_pdf(pdf: Path) -> list[str]:
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
    ok = re.search(r"100 000\s+2\s+4190\s+1\.5\s.*NTCALUG01A104GA", txt)
    return [] if ok else ["NTCALUG01A104GA ordering line (100 000 / 2 / 4190 / 1.5) not found"]


def verify_esp_pdf(pdf: Path) -> list[str]:
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
    ok = re.search(r"ATTEN3, effective measurement range of 0 ~ 2900\s+[-–]50\s+50\s+mV", txt)
    return [] if ok else ["ESP32-S3 Table 5-6 ATTEN3 0~2900 +/-50 mV not found"]


def c_float(x: float) -> str:
    t = f"{x:.6g}"
    return (t if ("." in t or "e" in t) else t + ".0") + "f"


def write_header() -> None:
    ks = sorted(VISHAY_104_KOHM)
    lines = [
        "/* Generated by output/temper-sensor-r3/firmware/hs_ntc.py - do not edit. */",
        "/*",
        " * Vishay NTC material D (curve 11, B25/85 4190 K +/- 1.5 %), 100 k at 25 degC:",
        " * zero-load resistance (ohm) against temperature (degC). The heatsink sensor is the",
        " * NTCALUG01A104GA (100 k +/- 2 %, 4190 K +/- 1.5 %, doc 29092), which has no R-T table",
        " * of its own; this is the NTCLE100E3104 column of doc 29049 p. 12",
        " * (https://www.vishay.com/docs/29049/ntcle100.pdf, retrieved 2026-10-15,",
        " * sha256 f9d6153738198dc705ed681c3b55e70a6571f8fee13a4ed7b2b41e49973cb9c9).",
        " * Interpolation: 1/T linear in ln R between points (hs_ntc.c).",
        " */",
        "#ifndef HS_NTC_TABLE_H",
        "#define HS_NTC_TABLE_H",
        "",
        f"#define HS_NTC_TABLE_N {len(ks)}u",
        "",
        "static const float k_hs_ntc_table_c[HS_NTC_TABLE_N] = {",
    ]
    for i in range(0, len(ks), 8):
        lines.append("    " + " ".join(f"{float(t):.1f}f," for t in ks[i:i + 8]))
    lines += ["};", "", "static const float k_hs_ntc_table_ohm[HS_NTC_TABLE_N] = {"]
    for i in range(0, len(ks), 6):
        lines.append("    " + " ".join(f"{c_float(VISHAY_104_KOHM[t] * 1e3)}," for t in ks[i:i + 6]))
    lines += ["};", "", "#endif /* HS_NTC_TABLE_H */", ""]
    HEADER.write_text("\n".join(lines), encoding="utf-8")


def header_define(name: str) -> float:
    if not SOAK_H.exists():
        return math.nan
    m = re.search(rf"#define {name}\s+([0-9.]+)f?", SOAK_H.read_text(encoding="utf-8"))
    return float(m.group(1)) if m else math.nan


def budget():
    """The cold-soak stacks over the band where the check runs."""
    t_sat = {f"{v:.3f}": round(solve_t(lambda t: 2.900 - node_v(t, v)), 2) for v in (V3V3_MIN, V3V3_NOM, V3V3_MAX)}
    # The channel can read VALID below the exact-ADC saturation temperature: at the
    # corner where the node is lowest (NTC -2 % and B column, pull-up +1.2 %, rail
    # 3.242 V) and the ADC and buffer read 52 mV low, the pin reaches 2900 mV colder.
    # The stack is evaluated from there (cold_soak.py runs the same corner through C).
    def node_lowest(t: float) -> float:
        return node_v(t, V3V3_MIN, (1 - R25_TOL) * (1 - btol_frac(t)), 1 + R_PULLUP_TOL + R_PULLUP_TC * BOARD_DT_K)
    band_lo = solve_t(lambda t: ATTEN[-1][2] + ATTEN[-1][3] + BUF_VOS_V - node_lowest(t), lo=0.0, hi=60.0)
    soak_hs = residual(HS_FLAT_K)
    soak_pt = residual(PT_FLAT_K)
    rows = []
    for t in [band_lo] + [x for x in (30.0, 32.5, 35.0, 37.5, 40.0, 42.5, HS_MAX_C) if x > band_lo]:
        terms, rail, v, slope, a = hs_errors(t)
        inst = sum(terms.values()) - terms["ntc_self_heating"]
        pt = pt_low_stack(t)
        fl = {"heatsink_instrument_reads_high": inst + terms["ntc_self_heating"],
              "heatsink_rail_low": rail["rail_low_reads_high"],
              "pt100_reads_low": sum(pt.values()),
              "soak_heatsink_above_ambient": soak_hs, "soak_pt100_below_ambient": soak_pt,
              "standby_offset": STANDBY_OFFSET_K}
        miss = {"heatsink_instrument_reads_low": inst,
                "heatsink_rail_high": rail["rail_high_reads_low"],
                "pt100_reads_high": sum(pt.values()) - PT_SH_CORR_K,
                "pt100_off_pan_self_heating": pt_off_pan_self_heating(t),
                "soak_heatsink_below_ambient": soak_hs, "soak_pt100_above_ambient": soak_pt}
        rows.append({"T_C": round(t, 2), "node_mV": round(v * 1e3, 1), "mV_per_K": round(slope * 1e3, 2),
                     "heatsink_terms_K": {k: round(x, 3) for k, x in terms.items()},
                     "heatsink_rail_K": {k: round(x, 3) for k, x in rail.items()},
                     "pt100_terms_K": {k: round(x, 3) for k, x in pt.items()},
                     "false_latch_stack_K": {k: round(x, 3) for k, x in fl.items()},
                     "false_latch_total_K": round(sum(fl.values()), 2),
                     "miss_stack_K": {k: round(x, 3) for k, x in miss.items()},
                     "miss_total_K": round(sum(miss.values()), 2),
                     "miss_total_rail_corrected_K": round(sum(miss.values()) - miss["heatsink_rail_high"], 2),
                     "false_latch_total_rail_corrected_K": round(sum(fl.values()) - fl["heatsink_rail_low"], 2)})
    thr = max(r["false_latch_total_K"] for r in rows)
    thr_c = max(r["false_latch_total_rail_corrected_K"] for r in rows)
    return {"saturation_C_by_v3v3": t_sat, "band_C": [round(band_lo, 2), HS_MAX_C],
            "band_note": "band_C[0]: the coldest heatsink temperature the channel can read VALID (every "
                         "tolerance lowering the node, ADC and buffer 52 mV low); at nominal parts the channel "
                         "is VALID only above saturation_C_by_v3v3", "rows": rows,
            "threshold_K": round(math.ceil(thr * 10) / 10, 1),
            "threshold_rail_corrected_K": round(math.ceil(thr_c * 10) / 10, 1),
            "soak_residual_K": {"heatsink": round(soak_hs, 3), "pt100": round(soak_pt, 3)}}


def soak_argument():
    cook_gap = COOK_SINK_C - min(AMBIENTS)
    return {
        "tau_estimates_s": TAU_EST_S, "tau_max_s": TAU_MAX_S,
        "N_s": SOAK_N_S, "W_s": WINDOW_S, "hs_flat_K": HS_FLAT_K, "pt_flat_K": PT_FLAT_K,
        "N_over_largest_estimate": round(SOAK_N_S / max(TAU_EST_S.values()), 2),
        "heatsink_after_N_from_88.6C_at_5C_ambient_K": {
            f"tau {int(t)} s": round(cook_gap * math.exp(-SOAK_N_S / t), 2) for t in (450.0, 900.0, TAU_MAX_S)},
        "residual_bound_K": {"heatsink": round(residual(HS_FLAT_K), 3), "pt100": round(residual(PT_FLAT_K), 3),
                             "heatsink_at_tau_900s": round(residual(HS_FLAT_K, 900.0), 3)},
        "note": "The flatness tests carry the bound: a single exponential that moved at most flat_k over the "
                "last W lies within flat_k/(exp(W/tau)-1) of its final value for any tau <= tau_max. N keeps "
                "the check out of the first two estimated time constants after a cook, where the flatness "
                "windows would see the fast components; it is not itself the bound.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-pdf", type=Path)
    ap.add_argument("--verify-lug-pdf", type=Path)
    ap.add_argument("--verify-esp-pdf", type=Path)
    ap.add_argument("--out", type=Path, default=HERE / "hs-ntc.json")
    args = ap.parse_args()
    checks = {}

    beta = math.log(VISHAY_104_KOHM[25] / VISHAY_104_KOHM[85]) / (1 / 298.15 - 1 / 358.15)
    checks["B25_85_from_table_matches_4190K"] = abs(beta - B25_85_K) < 1.0
    poly = {t: mat_d_t(r_table(t)) - t for t in VISHAY_104_KOHM}
    worst_poly = max(abs(e) for e in poly.values())
    # 4 significant digits in the table: 0.05 % of R is ~0.012 K at 25 C, ~0.02 K at 150 C
    checks["table_matches_material_D_polynomial_0p03K"] = worst_poly < 0.03
    for name, fn, path in (("datasheet_pdf_column_matches", verify_pdf, args.verify_pdf),
                           ("lug_pdf_ordering_line_matches", verify_lug_pdf, args.verify_lug_pdf),
                           ("esp_pdf_table_5_6_matches", verify_esp_pdf, args.verify_esp_pdf)):
        if path is not None:
            bad = fn(path)
            checks[name] = not bad
            for b in bad:
                print("PDF MISMATCH", b)

    # leave-one-out over 10 K (the table step is 5 K: about a quarter of this)
    ks = sorted(VISHAY_104_KOHM)
    loo = []
    for t in ks[1:-1]:
        sub = {k: v for k, v in VISHAY_104_KOHM.items() if k != t}
        loo.append({"T_C": t, "err_K": round(t_of_r(r_table(t), sub) - t, 4)})
    worst_loo = max(abs(x["err_K"]) for x in loo)
    checks["interpolation_loo_10K_le_0p05K"] = worst_loo <= 0.05

    # channel rows and the whole-mV chain (rail nominal)
    rows = []
    for t in (5, 15, 25, 32, 35, 40, 45) + TRIP_POINTS_C + (145.0,):
        t = float(t)
        v = node_v(t)
        a, fs, err = atten_for(v)
        sat = v >= ATTEN[-1][2]
        slope = (node_v(t - 0.05) - node_v(t + 0.05)) / 0.1
        chain = t_from_node(round(v * 1e3) / 1e3) - t
        terms, rail, *_ = hs_errors(t)
        rows.append({"T_C": t, "R_ohm": round(r_of_t(t), 1), "node_mV": round(v * 1e3, 1), "saturated": sat,
                     "atten": None if sat else a, "mV_per_K": round(slope * 1e3, 2),
                     "adc_error_K": None if sat else round(err / slope, 3),
                     "whole_mV_chain_err_K": None if sat else round(chain, 4),
                     "tolerance_K": round(terms["ntc_R25_2pct"] + terms["ntc_B_1p5pct"], 3),
                     "rail_K": {k: round(x, 3) for k, x in rail.items()}})
    trips = {r["T_C"]: r for r in rows if r["T_C"] in TRIP_POINTS_C}
    checks["trip_points_in_calibrated_range"] = all(not r["saturated"] for r in trips.values())
    short = {f"{vdd:.3f}": round(t_of_r(R_PULLUP * (SHORT_BELOW_V / vdd) / (1 - SHORT_BELOW_V / vdd)), 2)
             if not math.isnan(t_of_r(R_PULLUP * (SHORT_BELOW_V / vdd) / (1 - SHORT_BELOW_V / vdd))) else "beyond table"
             for vdd in (V3V3_MIN, V3V3_NOM, V3V3_MAX)}
    open_ref_t = {f"{vdd:.3f}": round(solve_t(lambda t: OPEN_REF_FRAC * vdd - node_v(t, vdd)), 1)
                  for vdd in (V3V3_MIN, V3V3_NOM, V3V3_MAX)}

    b = budget()
    checks["threshold_in_pan_cold_soak_h"] = abs(header_define("PCS_THRESHOLD_K") - b["threshold_K"]) < 1e-6
    checks["soak_constants_in_pan_cold_soak_h"] = (
        header_define("PCS_SOAK_N_S") == SOAK_N_S and header_define("PCS_WINDOW_S") == WINDOW_S
        and header_define("PCS_HS_FLAT_K") == HS_FLAT_K and header_define("PCS_PT_FLAT_K") == PT_FLAT_K
        and header_define("PCS_HS_MAX_C") == HS_MAX_C)
    # documents the ATTEN3 limit: exact-ADC saturation >= 28.6 degC, VALID at any corner >= ~23 degC
    checks["saturation_above_28C_valid_band_above_20C"] = (min(b["saturation_C_by_v3v3"].values()) > 28.0
                                                            and b["band_C"][0] > 20.0)
    write_header()

    out = {
        "sources": SOURCES,
        "table_kohm": {str(k): v for k, v in VISHAY_104_KOHM.items()},
        "B25_85_from_table_K": round(beta, 1),
        "material_D_polynomial_worst_K": round(worst_poly, 4),
        "interpolation_leave_one_out_10K": {"worst_K": worst_loo, "rows": loo},
        "channel": {"rows": rows, "saturation_C_by_v3v3": b["saturation_C_by_v3v3"],
                    "short_0p25V_C_by_v3v3": short, "hw_open_comparator_C_by_v3v3": open_ref_t,
                    "note": "ATTEN3's calibrated range ends at 2900 mV (ESP32-S3 Table 5-6). The 10 k pull-up "
                            "serves the 85-101 degC hardware trip (thermal_block / C32), so the node is above "
                            "2900 mV below 28.6-35.7 degC (v3v3 3.242-3.367 V; VALID from ~23.9 degC at the low corner): the channel reads SATURATED "
                            "(colder than the bound) at most room temperatures. An open sensor also reads "
                            "SATURATED; the board's HS_OPEN comparator latches it in hardware (C13)."},
        "cold_soak_budget": b,
        "soak_timing": soak_argument(),
        "checks": checks, "all_pass": all(checks.values()),
    }
    args.out.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(f"saturation {b['saturation_C_by_v3v3']}; band {b['band_C']}; threshold {b['threshold_K']} K "
          f"(rail-corrected {b['threshold_rail_corrected_K']} K); polynomial worst {worst_poly:.4f} K; "
          f"LOO worst {worst_loo:.4f} K")
    for r in b["rows"]:
        print(f"  T {r['T_C']:6.2f}: false-latch {r['false_latch_total_K']:5.2f} K, miss {r['miss_total_K']:5.2f} K")
    print("ALL HS NTC CHECKS PASS" if out["all_pass"] else "HS NTC CHECK FAILURE")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
