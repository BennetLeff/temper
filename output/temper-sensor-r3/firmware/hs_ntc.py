"""sensor-r3 heatsink NTC (Vishay NTCALUG01A104GA on the zapote/controller thermal-sense
block, HS_SENSE -> HS_ADC, GPIO6 / ADC1_CH5): the firmware's R-T table, the channel's
numbers, and the cold-soak error budget (DECISIONS.md D-HSNTC, D-SOAK).

The board (zapote/controller, read-only), as of controller-c1-crs 467917c38 (DECISIONS
C45, the CR-8 divider; `--verify-board-ref controller-c1-crs` re-reads every part below
from the .ato sources and the PCB):
  - elec/src/thermal_block.ato ThermalSenseUnit: hs_fixed 10 k 1 % (RC0603FR-0710KL)
    from vcc to HS_SENSE, the NTC (heatsink_probe J, external NTCALUG01A104GA lug)
    from HS_SENSE to gnd, hs_filter 100 nF at the node. The TLV3201 hot comparator
    (HS_HOT) and the TLV9031 open comparator (HS_OPEN: HS_SENSE above
    OPEN_REF = vcc * 100 k / 101.21 k) OR into HS_FAULT, a hardware latch input;
  - elec/src/controller.ato: thermal.vcc ~ v3v3; r_hs_filt 10 k + c_hs_filt 100 nF
    into the TLV9062 follower U6B (DECISIONS C13, C29); then the CR-8 divider (C45):
    r_hs_adc 1.00 k 0.1 % 25 ppm/K (RT0603BRD071KL) from the follower to HS_ADC,
    r_hs_adc_bot 5.90 k 0.1 % 25 ppm/K (ERA-3AEB5901V) from HS_ADC to selv_gnd,
    c_hs_adc 100 nF at HS_ADC; mcu.IO6 ~ hs_adc, i.e. GPIO6 = ADC1_CH5. (GPIO3, which
    the legacy temper_pins.h and elec/src name ADC_CHANNEL_NTC, is the blower tach,
    mcu.IO3 ~ fan_tach, on this board.)
  - Gain 5.90 / 6.90 = 0.855072, the firmware's HS_NTC_ADC_GAIN (hs_ntc.h, gated
    here); band 0.854824-0.855320 from the 0.1 % tolerances, 0.854421-0.855722 with
    25 ppm/K over the board's -40..85 degC, which this budget uses.
Before C45 (the "pre-C45" rows): 100 R / 100 nF and no divider (gain 1), so the node
was above ATTEN3's 2900 mV below 28.6-35.7 degC; superseded, kept as a reported row.

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
   - the channel: node and pin voltage, attenuation, mV/K, the error terms per
     temperature (accuracy table), the VALID range (from -40 degC at every corner),
     the short threshold, the over-temperature trip points, and the pre-C45 rows;
   - the ESP32-S3 SAR sampling against the divider's source (Thevenin 855 R, 100 nF):
     the driver's 8 one-shot samples per 100 ms period, with an assumed 20 pF sample
     capacitor (Espressif does not publish it; C45 assumes the same);
   - the divider's single faults: the bottom-open detection (HS_NTC_DIVIDER_FAULT_MV
     against the intact maximum) and the top-open reading;
   - the cold-soak error budget: the false-latch stack (heatsink reads high, Pt100 reads
     low, soak residual, standby offset) and the miss stack (the other way) over the
     band where the check runs (heatsink 5..45 degC: rooms down to 5 degC, 5 K under the
     rated 10 degC of docs/ENVIRONMENTAL_SPEC.md). The heatsink side is evaluated as a
     corner: every error at its limit applied to the circuit at once and read back
     through the driver's arithmetic (the per-term K figures are reported beside it;
     their linear sum overstates the cold end, where the node's slope is small), and
     the thresholds the firmware uses (gated against pan_cold_soak.h): PCS_THRESHOLD_K
     with the rail unknown (the driver assumes 3.300 V; true v3v3 anywhere in the
     3.242-3.367 V contract) and PCS_THRESHOLD_MEASURED_K with a measured rail (the
     MCP3202 CH1 reading, its error rail_adc.py's soak-band figure, D-RAIL); the
     firmware picks the second only when the rail was measured through the window;
   - the soak timing argument (N, W, flatness, residual bound).
   Exits 1 if a check fails.

Run: python3 hs_ntc.py [--verify-pdf ntcle100.pdf] [--verify-lug-pdf ntcalug01a.pdf]
                       [--verify-esp-pdf esp32-s3_datasheet_en.pdf]
                       [--verify-board-ref controller-c1-crs]
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
sys.path.insert(0, str(HERE))
import rail_adc  # noqa: E402
REPO = HERE.parents[2]
HEADER = REPO / "firmware" / "components" / "sensors" / "hs_ntc_table.h"
SOAK_H = REPO / "firmware" / "components" / "control" / "pan_cold_soak.h"
DRIVER_H = REPO / "firmware" / "components" / "sensors" / "include" / "hs_ntc.h"

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
    "board": "zapote/controller (read-only) at controller-c1-crs 467917c381578023137f8b4619b8fc076fe903f5 "
             "(DECISIONS C45): thermal_block.ato hs_fixed 10 k 1 % RC0603FR-0710KL vcc->HS_SENSE, NTC "
             "HS_SENSE->gnd, hs_filter 100 nF; controller.ato r_hs_filt 10 k / c_hs_filt 100 nF -> TLV9062 "
             "U6B follower -> r_hs_adc 1.00 k 0.1 % RT0603BRD071KL -> HS_ADC, r_hs_adc_bot 5.90 k 0.1 % "
             "ERA-3AEB5901V HS_ADC->selv_gnd, c_hs_adc 100 nF at HS_ADC, mcu.IO6 ~ hs_adc (GPIO6 = "
             "ADC1_CH5), thermal.vcc ~ v3v3 (TPS62933 3.242-3.367 V, pcb/checks.py SRC v3v3); "
             "pcb/controller.kicad_pcb R89 / R90 / C67 on hs_buf_out / HS_ADC / selv_gnd, U4 pad 6 on HS_ADC. "
             "Gain band and the 2.877 V maximum: tools/controller_calcs.py hs_adc_divider().",
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

# Board (zapote/controller at BOARD_COMMIT, DECISIONS C45)
BOARD_REF = "controller-c1-crs"
BOARD_COMMIT = "467917c381578023137f8b4619b8fc076fe903f5"
R_PULLUP = 10000.0      # hs_fixed 10 k 1 %
R_PULLUP_TOL = 0.01
R_PULLUP_TC = 100e-6    # RC0603FR (Yageo RC series) +/-100 ppm/K
BOARD_DT_K = 20.0       # board within 25 +/- 20 degC at soak (assumption)
# CR-8 divider after the follower (C45): r_hs_adc top, r_hs_adc_bot bottom, c_hs_adc at HS_ADC
R_ADC_TOP = 1000.0      # RT0603BRD071KL 1.00 k 0.1 % 25 ppm/K
R_ADC_BOT = 5900.0      # ERA-3AEB5901V 5.90 k 0.1 % 25 ppm/K
R_ADC_TOL = 0.001
R_ADC_TC = 25e-6
BOARD_RANGE_DT_K = 65.0  # board -40..85 degC: largest excursion from 25 degC (C45)
C_ADC = 100e-9
ADC_GAIN = R_ADC_BOT / (R_ADC_BOT + R_ADC_TOP)
C45_GAIN = {"nominal": 0.855072, "tolerance": (0.854824, 0.855320), "band": (0.854421, 0.855722),
            "adc_max_V": 2.877}      # zapote DECISIONS C45, as printed


def gain_band(dt_k: float = BOARD_RANGE_DT_K):
    """(low, high) divider gain: 0.1 % and 25 ppm/K over dt_k, top and bottom opposite."""
    d = R_ADC_TOL + R_ADC_TC * dt_k
    return (R_ADC_BOT * (1 - d) / (R_ADC_BOT * (1 - d) + R_ADC_TOP * (1 + d)),
            R_ADC_BOT * (1 + d) / (R_ADC_BOT * (1 + d) + R_ADC_TOP * (1 - d)))


GAIN_LO, GAIN_HI = gain_band()
# ESP32-S3 SAR against the divider's source. Espressif does not publish the sample
# capacitor: 20 pF is assumed, as C45 does, with a worst-case 2.9 V swing from whatever the
# capacitor held before (another channel, or the DAC's last state).
SAR_CS_F = 20e-12
SAR_SWING_V = 2.900
OVERSAMPLE = 8           # hs_ntc_default_params: one-shot samples per 100 ms period
DT_S = 0.1
ADC1_PATTERN_SPS = 80e3 / 9   # C45: continuous ADC1 pattern, HS once every 9 slots at 80 ksps
FILTER_TAU_S = 1.0
ADC_NOISE_MV = 3.0       # one-shot noise, rms (assumption, as cold_soak.py; bench item 5)
# MCP3202 CH1 against the LM4040A25 (rail_adc.c, D-RAIL): the reading's worst error over a
# 5..50 degC board, the band where the cold-soak check runs (rail_adc.py, rail-adc.json).
RAIL_READ_TOL = rail_adc.SOAK_TOL
# Driver constants (hs_ntc.h), gated below
DIVIDER_FAULT_MV = 2950.0
SAT_MARGIN_MV = 55.0
V3V3_NOM, V3V3_MIN, V3V3_MAX = 3.300, 3.242, 3.367
ATTEN = ((0, 0.800, 0.850, 0.005), (2, 1.550, 1.600, 0.010), (3, None, 2.900, 0.050))  # CR-7 rule, FS, error
SHORT_BELOW_V = 0.25
BUF_VOS_V = 0.002       # TLV9062 follower offset allowance (SBOS839 +/-1.6 mV max over temperature; C45 uses 1.6)
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
HS_BAND_LO_C = 5.0      # the coldest room the check is budgeted for: 5 K under the rated 10 degC
                        # (docs/ENVIRONMENTAL_SPEC.md 1, operating ambient 10..40 degC)
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


def sar_sampling() -> dict:
    """The SAR's sample capacitor against the divider's source (Thevenin of r_hs_adc ||
    r_hs_adc_bot with c_hs_adc as the reservoir). Each sample shares charge with the
    capacitor: a kick of SAR_SWING_V * Cs / (C + Cs) at most. The driver takes OVERSAMPLE
    one-shot samples back to back each 100 ms period; with no recovery assumed between
    them (a bound whatever the one-shot interval, which Espressif does not specify),
    sample k is off by at most (k + 1) kicks, and any 6 of the 8 (the trimmed mean keeps
    6) average at most the 6 largest bounds, (3 + ... + 8) / 6 = 5.5 kicks, whatever the
    signs. The reservoir recovers between periods (100 ms = DT_S / tau)."""
    r_th = R_ADC_TOP * R_ADC_BOT / (R_ADC_TOP + R_ADC_BOT)
    tau = r_th * C_ADC
    kick = SAR_SWING_V * SAR_CS_F / (C_ADC + SAR_CS_F)
    bounds = sorted(k + 1 for k in range(OVERSAMPLE))[-(OVERSAMPLE - 2):]
    trimmed = sum(bounds) / len(bounds) * kick
    f = ADC1_PATTERN_SPS
    return {"thevenin_ohm": r_th, "tau_us": tau * 1e6, "sample_cap_pF_assumed": SAR_CS_F * 1e12,
            "swing_V": SAR_SWING_V, "kick_mV": kick * 1e3,
            "driver_burst_trimmed_mean_bound_mV": trimmed * 1e3,
            "driver_burst_kicks": sum(bounds) / len(bounds),
            "recovery_between_periods_tau": DT_S / tau,
            "residual_at_next_period_mV": trimmed * math.exp(-DT_S / tau) * 1e3,
            "c45_continuous_pattern": {"rate_sps": f, "dc_mV": SAR_CS_F * SAR_SWING_V * f * r_th * 1e3,
                                       "residual_mV": kick * math.exp(-1.0 / f / tau) * 1e3}}


SAR_BOUND_V = sar_sampling()["driver_burst_trimmed_mean_bound_mV"] * 1e-3
# ADC noise after the driver: the trimmed mean of 8 (6 kept) and the 1 s filter at 100 ms;
# 3 sigma of the filtered reading (random, so it only enters the corner as an allowance).
_ALPHA = DT_S / (FILTER_TAU_S + DT_S)
NOISE_3SIGMA_V = 3.0 * ADC_NOISE_MV * 1e-3 / math.sqrt(OVERSAMPLE - 2) * math.sqrt(_ALPHA / (2.0 - _ALPHA))


def driver_t(pin_v: float, rail_read_v: float | None = None, gain: float = ADC_GAIN) -> float:
    """What hs_ntc.c computes from a pin voltage: node = pin / adc_gain, x = node / v3v3
    (3.300 V without a rail reading), R = R_pu x / (1 - x), T from the table; nan when the
    driver would not report a VALID temperature."""
    if pin_v >= ATTEN[-1][2]:
        return math.nan
    return t_from_node(pin_v / gain, rail_read_v or V3V3_NOM)


def corner(s: int, rail_measured: bool = False, gain_nominal: float = ADC_GAIN) -> dict:
    """Every heatsink-side error at its limit in one direction: s = -1 reads hot (the
    cold soak's false-latch side), +1 reads cold (its miss side), 0 nominal."""
    rail_true = {-1: V3V3_MIN, 0: V3V3_NOM, 1: V3V3_MAX}[s]
    if gain_nominal == 1.0:
        g = 1.0
    else:
        g = {-1: GAIN_LO, 0: ADC_GAIN, 1: GAIN_HI}[s]
    return {"s": s, "rail_true": rail_true,
            "rail_read": rail_true * (1.0 - s * RAIL_READ_TOL) if rail_measured else None,
            "gain": g, "gain_nominal": gain_nominal,
            "r25": 1.0 + s * R25_TOL, "rpu": 1.0 - s * (R_PULLUP_TOL + R_PULLUP_TC * BOARD_DT_K),
            "vos": s * BUF_VOS_V, "self_heating": s < 0}


def pin_at(t: float, c: dict) -> float:
    """Pin voltage at true heatsink temperature t for corner c (no ADC error)."""
    r0 = r_of_t(t) * c["r25"] * (1.0 + c["s"] * btol_frac(t))
    rp = R_PULLUP * c["rpu"]
    tb = t
    if c["self_heating"]:   # the bead above the lug: reads high
        tb = t + (c["rail_true"] / (r0 + rp)) ** 2 * r0 / NTC_DISSIPATION_W_PER_K
    r = r_of_t(tb) * c["r25"] * (1.0 + c["s"] * btol_frac(t))
    return (c["rail_true"] * r / (r + rp) + c["vos"]) * c["gain"]


def corner_reading(t: float, c: dict) -> float:
    """The driver's reading at true t for corner c: the pin plus the ADC's Table 5-6 error
    at the attenuation it picks, the SAR sampling bound and 3 sigma of noise, all in the
    corner's direction (s = -1: the pin reads low, i.e. hot)."""
    pin = pin_at(t, c)
    a, fs, err = atten_for(pin)
    extra = (err + SAR_BOUND_V + NOISE_3SIGMA_V) if c["gain_nominal"] != 1.0 else err + 0.0
    return driver_t(pin + c["s"] * extra, c["rail_read"], c["gain_nominal"])


def hs_errors(t: float):
    """Heatsink channel error terms at true temperature t (K, magnitude; each can go
    either way), first order. Rail is reported per direction."""
    v = node_v(t)
    pin = v * ADC_GAIN
    ta, tb = max(t - 0.05, -40.0), min(t + 0.05, 150.0)
    slope = (node_v(ta) - node_v(tb)) / (tb - ta)    # V/K at the node (falls with T)
    a, fs, err = atten_for(pin)
    tcr = abs(r_of_t(ta) - r_of_t(tb)) / (tb - ta) / r_of_t(t)   # 1/K
    gdev = max(ADC_GAIN - GAIN_LO, GAIN_HI - ADC_GAIN) / ADC_GAIN
    terms = {
        "ntc_R25_2pct": R25_TOL / tcr,
        "ntc_B_1p5pct": btol_frac(t) / tcr,
        "pullup_1pct_100ppm": (R_PULLUP_TOL + R_PULLUP_TC * BOARD_DT_K) / tcr,
        "adc_total_error": err / ADC_GAIN / slope,
        "divider_gain_band": gdev * v / slope,
        "sar_sampling": SAR_BOUND_V / ADC_GAIN / slope,
        "adc_noise_3sigma": NOISE_3SIGMA_V / ADC_GAIN / slope,
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


def header_define(name: str, path: Path = SOAK_H) -> float:
    if not path.exists():
        return math.nan
    m = re.search(rf"#define {name}\s+([0-9.]+)f?", path.read_text(encoding="utf-8"))
    return float(m.group(1)) if m else math.nan


def budget(rail_measured: bool = False, band_lo: float = HS_BAND_LO_C):
    """The cold-soak stacks over the band where the check runs (heatsink band_lo..HS_MAX_C).
    The heatsink side is the corner (every error at its limit at once, read back through
    the driver's arithmetic); the first-order terms are reported beside it."""
    soak_hs = residual(HS_FLAT_K)
    soak_pt = residual(PT_FLAT_K)
    cf, cm = corner(-1, rail_measured), corner(1, rail_measured)
    rows = []
    temps = [band_lo] + [x for x in (7.5, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, HS_MAX_C) if x > band_lo]
    for t in temps:
        terms, rail, v, slope, a = hs_errors(t)
        hs_high = corner_reading(t, cf) - t
        hs_low_r = corner_reading(t, cm)
        hs_low = None if math.isnan(hs_low_r) else t - hs_low_r
        pt = pt_low_stack(t)
        fl = {"heatsink_corner_reads_high": hs_high,
              "pt100_reads_low": sum(pt.values()),
              "soak_heatsink_above_ambient": soak_hs, "soak_pt100_below_ambient": soak_pt,
              "standby_offset": STANDBY_OFFSET_K}
        rail_term = (t_from_node(node_v(t), V3V3_NOM * (1.0 + RAIL_READ_TOL)) - t) if rail_measured \
            else rail["rail_low_reads_high"]
        linear_hs = sum(terms.values()) + rail_term
        row = {"T_C": round(t, 2), "node_mV": round(v * 1e3, 1), "pin_mV": round(v * ADC_GAIN * 1e3, 1),
               "atten": a, "node_mV_per_K": round(slope * 1e3, 2),
               "heatsink_terms_K": {k: round(x, 3) for k, x in terms.items()},
               "heatsink_rail_K": {k: round(x, 3) for k, x in rail.items()},
               "heatsink_linear_sum_reads_high_K": round(linear_hs, 2),
               "pt100_terms_K": {k: round(x, 3) for k, x in pt.items()},
               "false_latch_stack_K": {k: round(x, 3) for k, x in fl.items()},
               "false_latch_total_K": round(sum(fl.values()), 2)}
        if hs_low is None:
            row["miss_total_K"] = None
            row["miss_note"] = "the miss corner reads below the table: SATURATED, the check skips"
        else:
            miss = {"heatsink_corner_reads_low": hs_low,
                    "pt100_reads_high": sum(pt.values()) - PT_SH_CORR_K,
                    "pt100_off_pan_self_heating": pt_off_pan_self_heating(t),
                    "soak_heatsink_below_ambient": soak_hs, "soak_pt100_above_ambient": soak_pt}
            row["miss_stack_K"] = {k: round(x, 3) for k, x in miss.items()}
            row["miss_total_K"] = round(sum(miss.values()), 2)
        rows.append(row)
    thr = max(r["false_latch_total_K"] for r in rows)
    return {"band_C": [band_lo, HS_MAX_C], "rail_measured": rail_measured,
            "band_note": f"heatsink {band_lo:g}..{HS_MAX_C:g} degC: rooms down to {band_lo:g} degC "
                         "(5 K under the rated 10 degC, docs/ENVIRONMENTAL_SPEC.md) up to 40 degC plus the "
                         "standby offset; the channel is VALID over all of it at the false corner",
            "rows": rows, "threshold_K": round(math.ceil(thr * 10 - 1e-9) / 10, 1),
            "worst_row_T_C": max(rows, key=lambda r: r["false_latch_total_K"])["T_C"],
            "soak_residual_K": {"heatsink": round(soak_hs, 3), "pt100": round(soak_pt, 3)}}


def valid_range() -> dict:
    """Where the channel reads VALID: the pin's highest value (the node's high corner: NTC
    +2 % and the B column, pull-up low, rail 3.367 V, +V_OS, gain high) against 2900 mV."""
    ch = corner(1)
    ch["self_heating"] = False
    pin_m40 = pin_at(-40.0, ch)
    intact_max = GAIN_HI * (V3V3_MAX + BUF_VOS_V)          # any NTC state, open included
    read_extra = ATTEN[-1][3] + SAR_BOUND_V + NOISE_3SIGMA_V
    # the coldest sink whose reading can reach 2900 mV with the ADC's +50 mV (SATURATED)
    t_sat = solve_t(lambda t: (2.900 - read_extra) - pin_at(t, ch), lo=-40.0, hi=60.0) \
        if pin_m40 + read_extra >= 2.900 else None
    return {"pin_max_at_minus40C_V": round(pin_m40, 4),
            "c45_adc_max_V": C45_GAIN["adc_max_V"],
            "valid_from_C_exact_adc": -40.0 if pin_m40 < 2.900 else None,
            "pin_max_any_ntc_state_V": round(intact_max, 4),
            "reading_max_intact_mV": round((intact_max + read_extra) * 1e3, 1),
            "reading_can_saturate_below_C": None if t_sat is None else round(t_sat, 1),
            "note": "the corner model takes the NTC's B tolerance from the data sheet's dR/R column (5.88 % "
                    "at -40 degC) and V_OS 2 mV; C45 applies beta +1.5 % and 1.6 mV and gets 2.877 V"}


def divider_faults() -> dict:
    """The CR-8 divider's single faults (C45) as the driver sees them."""
    read_extra = ATTEN[-1][3] + SAR_BOUND_V + NOISE_3SIGMA_V
    intact_read_max = (GAIN_HI * (V3V3_MAX + BUF_VOS_V) + read_extra) * 1e3
    # bottom open / top shorted: gain 1, the pin is the follower output
    node_needed_worst = DIVIDER_FAULT_MV * 1e-3 + read_extra + BUF_VOS_V
    det = {f"{v:.3f}": {"worst_adc": round(solve_t(lambda t: node_needed_worst - node_v(t, v), hi=100.0), 1),
                        "nominal_adc": round(solve_t(lambda t: DIVIDER_FAULT_MV * 1e-3 - node_v(t, v), hi=100.0), 1)}
           for v in (V3V3_MIN, V3V3_NOM, V3V3_MAX)}
    v95 = node_v(95.0)
    fw95 = driver_t(v95)
    late = solve_t(lambda t: driver_t(node_v(t)) - 95.0, lo=60.0, hi=140.0)
    return {"intact_reading_max_mV": round(intact_read_max, 1), "divider_fault_mV": DIVIDER_FAULT_MV,
            "false_flag_margin_mV": round(DIVIDER_FAULT_MV - intact_read_max, 1),
            "bottom_open": {"detected_cold_start_below_C_by_v3v3": det,
                            "firmware_reads_at_95C": round(fw95, 2),
                            "firmware_95C_trip_fires_at_true_C": round(late, 2),
                            "c45_reads_at_95C_and_trip_at_C": [86.1, 103.3],
                            "hardware_hot_comparator_C": [98.3, 104.6],
                            "note": "C45: the HS_HOT comparator sits on HS_SENSE, upstream of the follower "
                                    "and the divider, so it still trips at 98.3-104.6 degC (Tj <= 132.4 degC); "
                                    "the driver latches DIVIDER at a cold start below the temperatures above"},
            "top_open": {"pin_mV": 0.0, "node_mV": 0.0, "short_below_mV": SHORT_BELOW_V * 1e3,
                         "driver": "SHORT after 3 periods, interlock +INF: FAULT_OVER_TEMP (fail-safe)"}}


def verify_board_ref(ref: str) -> tuple[list[str], str]:
    """Re-read the circuit from the zapote/controller branch: the .ato values, MPNs and
    connections, and the PCB's footprints on HS_ADC. Returns (mismatches, commit)."""
    def show(path: str) -> str:
        return subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:zapote/controller/{path}"],
                              check=True, capture_output=True, text=True).stdout
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", ref], check=True, capture_output=True,
                            text=True).stdout.strip()
    bad = []
    ctl = show("elec/src/controller.ato")
    want = [r"r_hs_adc\.value = 1kohm \+/- 0\.1%", r'r_hs_adc\.mpn = "RT0603BRD071KL"',
            r"r_hs_adc\.p1 ~ hs_buf_out", r"r_hs_adc\.p2 ~ hs_adc",
            r"r_hs_adc_bot\.value = 5\.9kohm \+/- 0\.1%", r'r_hs_adc_bot\.mpn = "ERA-3AEB5901V"',
            r"r_hs_adc_bot\.p1 ~ hs_adc", r"r_hs_adc_bot\.p2 ~ selv_gnd",
            r"c_hs_adc\.value = 100nF", r"c_hs_adc\.p1 ~ hs_adc", r"c_hs_adc\.p2 ~ selv_gnd",
            r"u_buf1\.OUTB ~ hs_buf_out", r"u_buf1\.INB_N ~ hs_buf_out", r"mcu\.IO6 ~ hs_adc"]
    bad += [f"controller.ato: no '{w}'" for w in want if not re.search(w, ctl)]
    th = show("elec/src/thermal_block.ato")
    bad += [f"thermal_block.ato: no '{w}'" for w in (r"hs_fixed\.value = 10kohm \+/- 1%", r"hs_fixed\.p1 ~ vcc",
                                                      r"hs_fixed\.p2 ~ hs_sense") if not re.search(w, th)]
    pcb = show("pcb/controller.kicad_pcb")
    on_net, parts = set(), {}
    for fp in pcb.split("\n\t(footprint ")[1:]:
        si = re.search(r'\(property "SourceInstance" "([^"]+)"', fp)
        mpn = re.search(r'\(property "MPN" "([^"]*)"', fp)
        pads = re.findall(r'\(pad "([^"]+)".*?\(net (?:\d+ )?"([^"]*)"\)', fp, re.S)
        name = si.group(1) if si else "?"
        if name in ("r_hs_adc", "r_hs_adc_bot", "c_hs_adc"):
            parts[name] = (mpn.group(1) if mpn else None, sorted(pads))
        on_net |= {(name, pad) for pad, net in pads if net == "HS_ADC"}
    want_parts = {"r_hs_adc": ("RT0603BRD071KL", [("1", "hs_buf_out"), ("2", "HS_ADC")]),
                  "r_hs_adc_bot": ("ERA-3AEB5901V", [("1", "HS_ADC"), ("2", "selv_gnd")]),
                  "c_hs_adc": ("CC0603KRX7R9BB104", [("1", "HS_ADC"), ("2", "selv_gnd")])}
    for k, w in want_parts.items():
        if parts.get(k) != w:
            bad.append(f"controller.kicad_pcb {k}: {parts.get(k)} != {w}")
    want_net = {("r_hs_adc", "2"), ("r_hs_adc_bot", "1"), ("c_hs_adc", "1"), ("mcu", "6")}
    if on_net != want_net:
        bad.append(f"controller.kicad_pcb HS_ADC pads {sorted(on_net)} != {sorted(want_net)}")
    dec = show("DECISIONS.md")
    if "## C45. Heatsink ADC divider" not in dec or "**0.854421–0.855722**" not in dec:
        bad.append("DECISIONS.md: C45 gain band not found")
    return bad, commit


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
    ap.add_argument("--verify-board-ref", help="git ref of the zapote/controller board (e.g. controller-c1-crs)")
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
    board_read = None
    if args.verify_board_ref:
        bad, commit = verify_board_ref(args.verify_board_ref)
        checks["board_ref_matches_circuit"] = not bad
        board_read = {"ref": args.verify_board_ref, "commit": commit, "mismatches": bad}
        for b in bad:
            print("BOARD MISMATCH", b)
        print(f"board {args.verify_board_ref} = {commit}: {'matches' if not bad else 'MISMATCH'}")

    # leave-one-out over 10 K (the table step is 5 K: about a quarter of this)
    ks = sorted(VISHAY_104_KOHM)
    loo = []
    for t in ks[1:-1]:
        sub = {k: v for k, v in VISHAY_104_KOHM.items() if k != t}
        loo.append({"T_C": t, "err_K": round(t_of_r(r_table(t), sub) - t, 4)})
    worst_loo = max(abs(x["err_K"]) for x in loo)
    checks["interpolation_loo_10K_le_0p05K"] = worst_loo <= 0.05

    # divider gain: the formula against C45's printed numbers, and the firmware constant
    g_tol = gain_band(0.0)
    checks["gain_matches_c45"] = (abs(ADC_GAIN - C45_GAIN["nominal"]) < 1e-6
                                  and all(abs(a - b) < 1e-6 for a, b in zip(g_tol, C45_GAIN["tolerance"]))
                                  and all(abs(a - b) < 1e-6 for a, b in zip((GAIN_LO, GAIN_HI), C45_GAIN["band"])))
    checks["adc_gain_in_hs_ntc_h"] = abs(header_define("HS_NTC_ADC_GAIN", DRIVER_H) - round(ADC_GAIN, 6)) < 1e-9
    sat_need = (ATTEN[-1][3] + max(ADC_GAIN - GAIN_LO, GAIN_HI - ADC_GAIN) / ADC_GAIN * 2.900
                + BUF_VOS_V * GAIN_HI) * 1e3
    checks["sat_margin_in_hs_ntc_h_covers_adc_gain_vos"] = (
        header_define("HS_NTC_SAT_MARGIN_MV", DRIVER_H) == SAT_MARGIN_MV and SAT_MARGIN_MV >= sat_need)

    # channel rows: the accuracy table (rail nominal, firmware's 3.300 V)
    cf, cm = corner(-1), corner(1)
    rows = []
    for t in (-40, -20, 0, 5, 15, 25, 35, 45) + TRIP_POINTS_C + (145.0,):
        t = float(t)
        v = node_v(t)
        pin = v * ADC_GAIN
        a, fs, err = atten_for(pin)
        terms, rail, *_ = hs_errors(t)
        chain = t_from_node(round(pin * 1e3) / 1e3 / ADC_GAIN) - t
        hi_r, lo_r = corner_reading(t, cf), corner_reading(t, cm)
        rows.append({"T_C": t, "R_ohm": round(r_of_t(t), 1), "node_mV": round(v * 1e3, 1),
                     "pin_mV": round(pin * 1e3, 1), "atten": a,
                     "pin_mV_per_K": round(ADC_GAIN * hs_errors(t)[3] * 1e3, 2),
                     "adc_error_K": round(terms["adc_total_error"], 3),
                     "tolerance_K": round(terms["ntc_R25_2pct"] + terms["ntc_B_1p5pct"], 3),
                     "pullup_K": round(terms["pullup_1pct_100ppm"], 3),
                     "divider_gain_K": round(terms["divider_gain_band"], 3),
                     "sar_sampling_K": round(terms["sar_sampling"], 3),
                     "whole_mV_chain_err_K": round(chain, 4),
                     "rail_K": {k: round(x, 3) for k, x in rail.items()},
                     "corner_reads_high_K": None if math.isnan(hi_r) else round(hi_r - t, 2),
                     "corner_reads_low_K": None if math.isnan(lo_r) else round(t - lo_r, 2)})
    trips = {r["T_C"]: r for r in rows if r["T_C"] in TRIP_POINTS_C}
    checks["trip_points_in_calibrated_range"] = all(r["pin_mV"] < 2900.0 for r in trips.values())
    # whole-mV rounding is half a millivolt at the pin, plus the table's interpolation (LOO)
    checks["whole_mV_chain_within_half_mV_plus_interpolation"] = all(
        abs(r["whole_mV_chain_err_K"]) <= 0.5 / r["pin_mV_per_K"] + 0.03 for r in rows)
    short = {f"{vdd:.3f}": round(t_of_r(R_PULLUP * (SHORT_BELOW_V / vdd) / (1 - SHORT_BELOW_V / vdd)), 2)
             if not math.isnan(t_of_r(R_PULLUP * (SHORT_BELOW_V / vdd) / (1 - SHORT_BELOW_V / vdd))) else "beyond table"
             for vdd in (V3V3_MIN, V3V3_NOM, V3V3_MAX)}
    open_ref_t = {f"{vdd:.3f}": round(solve_t(lambda t: OPEN_REF_FRAC * vdd - node_v(t, vdd)), 1)
                  for vdd in (V3V3_MIN, V3V3_NOM, V3V3_MAX)}

    vr = valid_range()
    checks["valid_from_minus40C_at_every_corner"] = vr["valid_from_C_exact_adc"] == -40.0
    checks["pin_max_within_5mV_of_c45"] = abs(vr["pin_max_at_minus40C_V"] - C45_GAIN["adc_max_V"]) <= 0.005
    sar = sar_sampling()
    _, _, _, slope95, _ = hs_errors(95.0)
    sar_95 = SAR_BOUND_V / ADC_GAIN / slope95
    checks["sar_sampling_le_0p2K_at_95C"] = sar_95 <= 0.2
    df = divider_faults()
    checks["divider_fault_level_above_intact_reading"] = (
        header_define("HS_NTC_DIVIDER_FAULT_MV", DRIVER_H) == DIVIDER_FAULT_MV and df["false_flag_margin_mV"] > 0.0)
    # C45 (its own NTC model) gives 86.1 / 103.3 degC; this is the firmware's table arithmetic
    checks["divider_bottom_open_agrees_with_c45_0p5K"] = (
        abs(df["bottom_open"]["firmware_reads_at_95C"] - 86.1) < 0.5
        and abs(df["bottom_open"]["firmware_95C_trip_fires_at_true_C"] - 103.3) < 0.5)

    b = budget()
    b_rail = budget(rail_measured=True)
    b["threshold_rail_corrected_K"] = b_rail["threshold_K"]   # leak_alternatives.py reads it
    b_rail["rail_read_tol_pct"] = round(RAIL_READ_TOL * 100, 4)
    checks["threshold_in_pan_cold_soak_h"] = abs(header_define("PCS_THRESHOLD_K") - b["threshold_K"]) < 1e-6
    checks["threshold_measured_in_pan_cold_soak_h"] = abs(
        header_define("PCS_THRESHOLD_MEASURED_K") - b_rail["threshold_K"]) < 1e-6
    checks["measured_threshold_below_fallback"] = b_rail["threshold_K"] < b["threshold_K"]
    checks["soak_constants_in_pan_cold_soak_h"] = (
        header_define("PCS_SOAK_N_S") == SOAK_N_S and header_define("PCS_WINDOW_S") == WINDOW_S
        and header_define("PCS_HS_FLAT_K") == HS_FLAT_K and header_define("PCS_PT_FLAT_K") == PT_FLAT_K
        and header_define("PCS_HS_MAX_C") == HS_MAX_C)
    checks["heatsink_valid_over_the_band_at_the_false_corner"] = all(
        not math.isnan(corner_reading(t, cf)) for t in (HS_BAND_LO_C, HS_MAX_C))
    pre = {"gain": 1.0, "network": "100 R / 100 nF, no divider (before C45)",
           "saturation_C_by_v3v3": {f"{v:.3f}": round(solve_t(lambda t: 2.900 - node_v(t, v)), 2)
                                    for v in (V3V3_MIN, V3V3_NOM, V3V3_MAX)},
           "cold_soak_threshold_K_then": 12.9,
           "note": "superseded by C45; reported only. Its cold-soak results are cold-soak.json at 75e512eab "
                   "(variant as_built)."}
    write_header()

    out = {
        "sources": SOURCES,
        "board": {"ref": BOARD_REF, "commit": BOARD_COMMIT, "read_this_run": board_read,
                  "divider": {"r_top_ohm": R_ADC_TOP, "r_bot_ohm": R_ADC_BOT, "tol": R_ADC_TOL,
                              "tcr_per_K": R_ADC_TC, "c_F": C_ADC},
                  "gain_nominal": round(ADC_GAIN, 6), "gain_band_tolerance_only": [round(x, 6) for x in g_tol],
                  "gain_band_minus40_85C": [round(GAIN_LO, 6), round(GAIN_HI, 6)]},
        "table_kohm": {str(k): v for k, v in VISHAY_104_KOHM.items()},
        "B25_85_from_table_K": round(beta, 1),
        "material_D_polynomial_worst_K": round(worst_poly, 4),
        "interpolation_leave_one_out_10K": {"worst_K": worst_loo, "rows": loo},
        "channel": {"rows": rows, "valid_range": vr,
                    "short_0p25V_C_by_v3v3": short, "hw_open_comparator_C_by_v3v3": open_ref_t,
                    "note": "pin = node x 0.855072 (CR-8, C45): inside ATTEN3's calibrated 2900 mV (ESP32-S3 Table "
                            "5-6) from -40 degC up at every corner, so the channel reads room temperature. The "
                            "cold end is VALID but coarse: the 10 k pull-up serves the 85-101 degC hardware trip, "
                            "and below ~15 degC the node is within 10 % of the rail (pin 5-6 mV/K), so +/-50 mV of "
                            "ADC error and an unmeasured rail are many kelvin (corner columns). An open sensor reads "
                            "SATURATED (colder than the table); HS_OPEN latches it in hardware (C13)."},
        "sar_sampling": {**sar, "error_at_95C_K": round(sar_95, 3),
                         "noise_3sigma_after_filter_mV": round(NOISE_3SIGMA_V * 1e3, 3)},
        "divider_faults": df,
        "pre_c45": pre,
        "cold_soak_budget": b,
        "cold_soak_budget_rail_measured": b_rail,
        "soak_timing": soak_argument(),
        "checks": checks, "all_pass": all(checks.values()),
    }
    args.out.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(f"gain {ADC_GAIN:.6f} band {GAIN_LO:.6f}-{GAIN_HI:.6f}; pin max {vr['pin_max_at_minus40C_V']} V at -40 C; "
          f"SAR {sar['driver_burst_trimmed_mean_bound_mV']:.2f} mV ({sar_95:.3f} K at 95 C); "
          f"divider-fault margin {df['false_flag_margin_mV']} mV")
    print(f"band {b['band_C']}; threshold {b['threshold_K']} K (worst at {b['worst_row_T_C']} C; rail measured "
          f"{b_rail['threshold_K']} K); polynomial worst {worst_poly:.4f} K; LOO worst {worst_loo:.4f} K")
    for r in b["rows"]:
        print(f"  T {r['T_C']:6.2f}: false-latch {r['false_latch_total_K']:5.2f} K (heatsink corner "
              f"{r['false_latch_stack_K']['heatsink_corner_reads_high']:5.2f}, linear {r['heatsink_linear_sum_reads_high_K']:5.2f}), "
              f"miss {r['miss_total_K']}")
    print("ALL HS NTC CHECKS PASS" if out["all_pass"] else "HS NTC CHECK FAILURE")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
