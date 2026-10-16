"""DECISIONS.md D-RAIL (open item 11): the v3v3 rail reading, MCP3202 CH1 against the LM4040A25.

The board (zapote/controller controller.ato at controller-c1-crs 467917c38):
  U15 MCP3202-CI/SN, VDD = VREF = v3v3 (the converter has no separate reference
  pin), CH1 = ref2v5, the LM4040A25IDBZR shunt fed from v3v3 through 1.00 k 1 %
  (r_ref) and loaded by the D-11 bias divider 90.9 k + 10 k (24.8 uA).
  Firmware (components/sensors/rail_adc.c): v3v3 = 2500 mV x 4096 / (code + 0.5),
  code the mean of 8 conversions, one reading per 100 ms.

Sources (numbers transcribed below; `--verify-mcp-pdf` / `--verify-lm-pdf` re-extract
the lines with pdftotext and fail on a mismatch):
  MCP3202: Microchip DS21034F, https://ww1.microchip.com/downloads/en/DeviceDoc/21034F.pdf,
    retrieved 2026-10-16, sha256 f06725fac4793db344845d0db9a9f7e1d3dedd3b879fc1c570b01824c41e6559.
    Electrical Characteristics ("all parameters apply at VDD = 5.5V ... TA = -40 to +85"):
    INL +/-2 LSB (MCP3202-C), offset +/-3 LSB, gain +/-5 LSB, DNL +/-1 LSB; fCLK 1.8 MHz at
    VDD 5 V, 0.9 MHz at 2.7 V; SPI modes 0,0 and 1,1 (section 6.1).
    Assumption (bench item): the LSB-denominated limits hold at VDD = 3.3 V. The data sheet
    specifies them at 5.5 V and shows offset and gain against VDD only as typical curves
    (Figures 2-15, 2-18); the budget reports the threshold with the MCP3202 terms doubled
    (`mcp3202_x2`) beside the one it uses.
  LM4040A25I: TI SLOS456Q (January 2005, revised April 2026),
    https://www.ti.com/lit/ds/symlink/lm4040.pdf, retrieved 2026-10-16,
    sha256 f43b6b6d3ecd51c8c90b70a7c4630c7e3140822b0073953ed2459df81b251c1c.
    Section 6.8: reverse breakdown voltage tolerance at IZ = 100 uA +/-2.5 mV at 25 degC,
    +/-19 mV over -40..85 degC (note 2: +/-0.1 % +/-100 ppm/degC x 65 degC); temperature
    coefficient +/-100 ppm/degC full range; change with cathode current
    IZ,min < IZ < 1 mA: 1 mV full range; IZ,min 80 uA full range; long-term stability
    120 ppm (typical, 1000 h); thermal hysteresis 0.08 % (typical, -40..125 degC).

The error of the reading, as a fraction of v3v3, at board temperature T (all terms at
their limits, the same sign):
  ref_initial        2.5 mV / 2500                     (25 degC tolerance)
  ref_tempco         100 ppm/K x |T - 25|, the sum with ref_initial capped at the
                     full-range 19 mV
  ref_current        1 mV / 2500: the data sheet's tolerance is at 100 uA; the board runs
                     the shunt at (v3v3 - 2.5 V) / 1 k (1 %) - 24.8 uA = 0.71-0.85 mA,
                     inside IZ,min < IZ < 1 mA over the v3v3 contract
  ref_long_term      120 ppm, ref_hysteresis 0.08 % (typical values; carried as
                     allowances, not limits)
  adc_offset/gain/inl  3 + 5 x code / 4096 + 2 LSB at the CH1 code (about 3103), over the
                     code
  adc_quantisation   0.5 LSB (the decode's + 0.5 centres the code)
  rail_ripple        5 mV / 3300: the MCP3202's reference is v3v3 itself, so ripple during a
                     conversion is error the eight-sample mean does not remove; 10 mV p-p for
                     the forced-CCM TPS62933 is an assumption (bench item)
Not carried: the sample capacitor's kick (20 pF, 1 k RSS) on the shunt's 0.3-0.8 ohm
dynamic impedance settles within the 1.5-clock sample time by orders of magnitude; the
v3v3 drop between U15 and the NTC dividers (microamps of divider current).

What this writes (rail-adc.json) and gates:
  1. the error rows over -40..85 degC; the soak-band figure the cold-soak budget uses
     (board 5..50 degC: the heatsink band 5..45 degC plus 5 K of board self-heating at
     idle, an assumption) and the full-range one (rim, D-RIM);
  2. RAIL_ADC_V3V3_MIN_MV / _MAX_MV (rail_adc.h): the contract 3.242-3.367 V widened by the
     full-range error, rounded outward to 5 mV, so a healthy board never reads "rail
     unknown"; a broken reference (open: code 4095 -> 2500 mV; shorted: code 0) or an
     absent converter falls outside;
  3. the firmware's SPI clock and mode against the data sheet (clock <= 0.9 MHz, mode 0 or
     3; the sample read within 1.2 ms, section 6.2);
  4. the decode against the firmware: the C formula and its inverse at the contract ends.
Exits 1 if a check fails.

Run: python3 rail_adc.py [--verify-mcp-pdf 21034F.pdf] [--verify-lm-pdf lm4040.pdf]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RAIL_H = REPO / "firmware" / "components" / "sensors" / "include" / "rail_adc.h"

VREF_MV = 2500.0
FULL_SCALE = 4096
V3V3_NOM, V3V3_MIN, V3V3_MAX = 3300.0, 3242.0, 3367.0   # TPS62933 contract (pcb/checks.py SRC v3v3)
# LM4040A25I (SLOS456Q section 6.8)
REF_TOL_25_MV = 2.5
REF_TOL_FULL_MV = 19.0
REF_TC_PPM = 100.0
REF_IZ_MV = 1.0
REF_LONG_TERM_PPM = 120.0     # typical
REF_HYST_FRAC = 0.0008        # typical
IZ_MIN_A = 80e-6
R_REF, R_REF_TOL = 1000.0, 0.01
I_DIV_A = 2500.0e-3 / (90.9e3 + 10e3)   # D-11 bias divider on ref2v5
# MCP3202-C (DS21034F Electrical Characteristics)
ADC_OFFSET_LSB = 3.0
ADC_GAIN_LSB = 5.0
ADC_INL_LSB = 2.0
ADC_QUANT_LSB = 0.5
FCLK_MAX_HZ_2V7 = 0.9e6
SAMPLE_WINDOW_S = 1.2e-3       # section 6.2: >= 10 kHz effective
RIPPLE_MV = 5.0                # half of an assumed 10 mV p-p (bench item)
BOARD_SELF_HEAT_K = 5.0        # board over the heatsink at idle (assumption)
SOAK_BOARD_C = (5.0, 45.0 + BOARD_SELF_HEAT_K)
FULL_C = (-40.0, 85.0)
ROW_T = (-40.0, -20.0, 0.0, 5.0, 10.0, 25.0, 40.0, 50.0, 55.0, 70.0, 85.0)

MCP_PDF_LINES = (r"±1\s+±2\s+LSB\s+MCP3202-C",
                 r"Offset Error\s+.*±3\s+LSB", r"Gain Error\s+.*±5\s+LSB",
                 r"all parameters apply at VDD = 5\.5V",
                 r"0\.9\s+MHz\s+VDD = 2\.7V")
LM_PDF_LINES = (r"LM4040A25I, LM4040B25I Electrical Characteristics",
                r"tolerance\s+Full range\s+–19\s+19",
                r"A-grade: ±0\.75% = ±0\.1% ±100ppm/°C × 65°C",
                r"IZ,min < IZ < 1mA")


def code_of(v3v3_mv: float) -> float:
    return FULL_SCALE * VREF_MV / v3v3_mv


def v3v3_of_code(code: float) -> float:
    """The firmware's decode (rail_adc_code_to_v3v3_mv)."""
    return VREF_MV * FULL_SCALE / (code + 0.5)


def iz_range_a() -> tuple[float, float]:
    lo = (V3V3_MIN - VREF_MV - REF_TOL_FULL_MV) * 1e-3 / (R_REF * (1 + R_REF_TOL)) - I_DIV_A
    hi = (V3V3_MAX - VREF_MV + REF_TOL_FULL_MV) * 1e-3 / (R_REF * (1 - R_REF_TOL)) - I_DIV_A
    return lo, hi


def terms(t_board: float, v3v3_mv: float, mcp_scale: float = 1.0) -> dict:
    """Error terms of the reading at board temperature t_board, fraction of v3v3."""
    code = code_of(v3v3_mv)
    ref_t = min(REF_TOL_25_MV + REF_TC_PPM * 1e-6 * abs(t_board - 25.0) * VREF_MV, REF_TOL_FULL_MV)
    lsb = 1.0 / code
    return {
        "ref_initial_and_tempco": ref_t / VREF_MV,
        "ref_current": REF_IZ_MV / VREF_MV,
        "ref_long_term_typ": REF_LONG_TERM_PPM * 1e-6,
        "ref_hysteresis_typ": REF_HYST_FRAC,
        "adc_offset": mcp_scale * ADC_OFFSET_LSB * lsb,
        "adc_gain": mcp_scale * ADC_GAIN_LSB * (code / FULL_SCALE) * lsb,
        "adc_inl": mcp_scale * ADC_INL_LSB * lsb,
        "adc_quantisation": ADC_QUANT_LSB * lsb,
        "rail_ripple": RIPPLE_MV / v3v3_mv,
    }


def tol(t_board: float, mcp_scale: float = 1.0) -> float:
    """Worst fractional error over the v3v3 contract at board temperature t_board."""
    return max(sum(terms(t_board, v, mcp_scale).values()) for v in (V3V3_MIN, V3V3_NOM, V3V3_MAX))


def tol_over(band: tuple[float, float], mcp_scale: float = 1.0) -> float:
    lo, hi = band
    pts = [lo, hi] + ([25.0] if lo < 25.0 < hi else [])
    return max(tol(t, mcp_scale) for t in pts)


SOAK_TOL = tol_over(SOAK_BOARD_C)
FULL_TOL = tol_over(FULL_C)
SOAK_TOL_MCP_X2 = tol_over(SOAK_BOARD_C, 2.0)


def window_mv() -> tuple[float, float]:
    lo = math.floor(V3V3_MIN * (1.0 - FULL_TOL) / 5.0) * 5.0
    hi = math.ceil(V3V3_MAX * (1.0 + FULL_TOL) / 5.0) * 5.0
    return lo, hi


def header_define(name: str, path: Path = RAIL_H) -> float:
    m = re.search(rf"#define {name}\s+([0-9.]+)[uf]?", path.read_text(encoding="utf-8"))
    return float(m.group(1)) if m else math.nan


def verify(pdf: Path, patterns) -> list[str]:
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True, capture_output=True,
                         text=True).stdout
    return [p for p in patterns if not re.search(p, txt)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=HERE / "rail-adc.json")
    ap.add_argument("--verify-mcp-pdf", type=Path)
    ap.add_argument("--verify-lm-pdf", type=Path)
    args = ap.parse_args()
    checks = {}
    for flag, pats, name in ((args.verify_mcp_pdf, MCP_PDF_LINES, "mcp3202"), (args.verify_lm_pdf, LM_PDF_LINES,
                                                                               "lm4040")):
        if flag is not None:
            bad = verify(flag, pats)
            checks[f"{name}_pdf_lines_found"] = not bad
            for b in bad:
                print(f"PDF MISMATCH {name}: {b}")

    iz_lo, iz_hi = iz_range_a()
    checks["lm4040_current_in_iz_min_to_1mA"] = IZ_MIN_A < iz_lo and iz_hi < 1e-3
    rows = []
    for t in ROW_T:
        tt = terms(t, V3V3_MIN)
        rows.append({"board_C": t, "terms_pct_at_3242mV": {k: round(x * 100, 4) for k, x in tt.items()},
                     "total_pct": round(tol(t) * 100, 3),
                     "total_mV_at_3300": round(tol(t) * V3V3_NOM, 1)})
    lo, hi = window_mv()
    fw_lo, fw_hi = header_define("RAIL_ADC_V3V3_MIN_MV"), header_define("RAIL_ADC_V3V3_MAX_MV")
    checks["window_min_in_rail_adc_h"] = abs(fw_lo - lo) < 1e-6
    checks["window_max_in_rail_adc_h"] = abs(fw_hi - hi) < 1e-6
    checks["healthy_reads_inside_window"] = (V3V3_MIN * (1 - FULL_TOL) >= lo and V3V3_MAX * (1 + FULL_TOL) <= hi)
    # broken measurements fall outside: reference open (CH1 at v3v3: code 4095), shorted (code 0),
    # converter absent (rejected by the null bit before the decode)
    open_ref = v3v3_of_code(4095)
    checks["open_reference_outside_window"] = not (lo <= open_ref <= hi)
    checks["shorted_reference_outside_window"] = not (lo <= v3v3_of_code(0) <= hi)
    clk = header_define("RAIL_ADC_SPI_CLOCK_HZ")
    mode = header_define("RAIL_ADC_SPI_MODE")
    n = header_define("RAIL_ADC_SAMPLES")
    checks["spi_clock_le_0p9MHz_at_2V7"] = clk <= FCLK_MAX_HZ_2V7
    checks["spi_mode_0_or_3"] = mode in (0.0, 3.0)
    # the sample-and-hold: one 24-clock transfer must finish well inside 1.2 ms
    checks["transfer_within_sample_window"] = 24.0 / clk < SAMPLE_WINDOW_S
    checks["ref_mv_matches"] = abs(header_define("RAIL_ADC_REF_MV") - VREF_MV) < 1e-6
    # decode round trip at the contract ends (the C formula)
    rt = {v: v3v3_of_code(math.floor(code_of(v))) for v in (V3V3_MIN, V3V3_NOM, V3V3_MAX)}
    checks["decode_round_trip_within_half_lsb"] = all(abs(rt[v] - v) / v <= 0.5 / code_of(v) + 1e-9 for v in rt)

    out = {
        "scope": __doc__.strip(),
        "lm4040_cathode_current_mA": [round(iz_lo * 1e3, 3), round(iz_hi * 1e3, 3)],
        "ch1_code": {f"{v:.0f}": round(code_of(v), 1) for v in (V3V3_MIN, V3V3_NOM, V3V3_MAX)},
        "rows": rows,
        "soak_band_board_C": list(SOAK_BOARD_C),
        "soak_band_tol_pct": round(SOAK_TOL * 100, 4),
        "soak_band_tol_mcp3202_x2_pct": round(SOAK_TOL_MCP_X2 * 100, 4),
        "full_range_tol_pct": round(FULL_TOL * 100, 4),
        "window_mV": [lo, hi], "firmware_window_mV": [fw_lo, fw_hi],
        "open_reference_reads_mV": round(open_ref, 1),
        "spi": {"clock_hz": clk, "mode": mode, "samples": n,
                "bus_time_per_reading_us": round(n * 24.0 / clk * 1e6, 1)},
        "checks": checks, "all_pass": all(checks.values()),
    }
    args.out.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for r in rows:
        print(f"board {r['board_C']:6.1f} C: {r['total_pct']:.3f} % ({r['total_mV_at_3300']} mV)")
    print(f"soak band {SOAK_BOARD_C} C: {SOAK_TOL * 100:.3f} % (MCP3202 x2: {SOAK_TOL_MCP_X2 * 100:.3f} %); "
          f"full range {FULL_TOL * 100:.3f} %; window {lo:.0f}-{hi:.0f} mV; IZ {iz_lo * 1e3:.3f}-{iz_hi * 1e3:.3f} mA")
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print("ALL RAIL ADC CHECKS PASS" if out["all_pass"] else "RAIL ADC CHECK FAILURE")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
