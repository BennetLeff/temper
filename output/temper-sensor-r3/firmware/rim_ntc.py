"""sensor-r3 rim NTC (Semitec 104GT-2 on J12, GPIO9 / ADC1_CH8): the firmware's
R-T table and the numbers behind the rim driver (firmware/components/sensors/rim_ntc.c).

What it does
1. Holds the 104GT-2 column of the Semitec GT-2 datasheet R-T table, -50..300 C
   in 10 K steps (plus 25 and 85 C), transcribed below (SOURCE).
   - `--verify-pdf <GT-2 pdf>` re-extracts that column with pdftotext and
     fails if any value differs from the transcription.
   - Always checks that every point the PCB agent used (pcb/checks.py GT2_104)
     agrees with the transcription.
2. Writes firmware/components/sensors/rim_ntc_table.h (the C table the driver
   interpolates; deterministic, so a rerun leaves git clean).
3. Writes rim-ntc.json:
   - interpolation error of the driver's piecewise-beta rule (1/T linear in
     ln R between table points) against the table, leave-one-out: every interior
     point is dropped and predicted from its neighbours 20 K apart. Error scales
     with the step squared, so the 10 K table interpolates about 4x better than
     this figure (reported as an estimate, not a bound);
   - per temperature: node voltage, the CR-7 attenuation, K per mV (the
     ESP32-S3 calibration returns integer mV) and the still-air self-heating
     (datasheet 0.6 mW/K) that the driver does NOT subtract (DECISIONS D-RIM);
   - the cold saturation temperature (ATTEN3 calibrated range 2900 mV) and the
     short threshold (0.25 V) as temperatures, over the v3v3 contract range.
   Exits 1 if a check fails.

Run: python3 rim_ntc.py [--verify-pdf GT-2.pdf]
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidence_compare as EC  # noqa: E402  (reference_platform on the evidence written)
import rail_adc  # noqa: E402
HEADER = REPO / "firmware" / "components" / "sensors" / "rim_ntc_table.h"
PCB_CHECKS = HERE.parent / "pcb" / "checks.py"

SOURCE = ("Semitec GT-2 series datasheet (Japanese, 'GT-2シリーズ.pdf', page 18 '抵抗−温度特性' table, "
          "column 104GT-2, unit kOhm), https://www.semitec.co.jp/uploads/GT-2シリーズ.pdf, retrieved "
          "2026-10-15, sha256 c0a2841d9db01c672a840100baab1d034fb01295bcdb54b012cb8a52ac2d07b0. "
          "104GT-2: R25 100 k +/-3 %, B25/85 4267 K +/-2 %, -50..+300 C, dissipation ~0.6 mW/C and "
          "time constant ~7 s in still air, 3.0 mW rated. The same table (a subset) is in "
          "pcb/checks.py GT2_104 and zapote/controller/tools/controller_calcs.py.")

# 104GT-2 zero-load resistance, kOhm (datasheet column, transcribed).
GT2_104_KOHM = {
    -50: 8743.0, -40: 4218.0, -30: 2132.0, -20: 1127.0, -10: 620.1, 0: 353.7, 10: 208.6, 20: 126.8,
    25: 100.0, 30: 79.36, 40: 50.96, 50: 33.49, 60: 22.51, 70: 15.44, 80: 10.80, 85: 9.089, 90: 7.686,
    100: 5.556, 110: 4.082, 120: 3.043, 130: 2.298, 140: 1.758, 150: 1.360, 160: 1.064, 170: 0.8414,
    180: 0.6714, 190: 0.5408, 200: 0.4393, 210: 0.3597, 220: 0.2969, 230: 0.2468, 240: 0.2065,
    250: 0.1740, 260: 0.1475, 270: 0.1258, 280: 0.1079, 290: 0.09305, 300: 0.08065,
}
B25_85_K = 4267.0

# Board (zapote/controller, sensor-r3 CR-4..CR-7, pcb/REQUIREMENTS.md section 4)
R_PULLUP = 1000.0                      # 1.00 k 0.1 % to v3v3
V3V3_NOM, V3V3_MIN, V3V3_MAX = 3.300, 3.242, 3.367  # TPS62933 contract (pcb SRC v3v3)
ATTEN = ((0, 0.800, 0.850), (2, 1.550, 1.600), (3, None, 2.900))  # (atten, use below V, calibrated FS V)
SHORT_BELOW_V = 0.25
DISSIPATION_W_PER_K = 0.6e-3           # still air (datasheet); on the glass it is higher
CHECK_T = (25.0, 100.0, 150.0, 200.0, 250.0)


def r_table(t: float) -> float:
    return GT2_104_KOHM[int(t)] * 1e3


def piecewise_beta_t(r: float, pts: dict[int, float], extrapolate: bool = False) -> float:
    """The driver's rule: 1/T(K) linear in ln R between neighbouring table points.
    extrapolate: beyond the table, continue the end segment (reporting only; the
    driver flags those readings instead)."""
    ks = sorted(pts)
    segs = list(zip(ks, ks[1:]))
    for i, (a, b) in enumerate(segs):
        ra, rb = pts[a] * 1e3, pts[b] * 1e3
        if (ra >= r >= rb) or (extrapolate and ((i == 0 and r > ra) or (i == len(segs) - 1 and r < rb))):
            ia, ib = 1.0 / (a + 273.15), 1.0 / (b + 273.15)
            inv = ia + (math.log(r) - math.log(ra)) * (ib - ia) / (math.log(rb) - math.log(ra))
            return 1.0 / inv - 273.15
    raise ValueError(r)


def loglinear_t(r: float, pts: dict[int, float]) -> float:
    """pcb/checks.py's rule (ln R linear in T), for comparison."""
    ks = sorted(pts)
    for a, b in zip(ks, ks[1:]):
        ra, rb = pts[a] * 1e3, pts[b] * 1e3
        if ra >= r >= rb:
            return a + (math.log(r) - math.log(ra)) * (b - a) / (math.log(rb) - math.log(ra))
    raise ValueError(r)


def interp_r(t: float) -> float:
    """R(T) with the driver's rule (exact at table points), for node voltages between points."""
    ks = sorted(GT2_104_KOHM)
    for a, b in zip(ks, ks[1:]):
        if a <= t <= b:
            ia, ib, it = 1 / (a + 273.15), 1 / (b + 273.15), 1 / (t + 273.15)
            la, lb = math.log(r_table(a)), math.log(r_table(b))
            return math.exp(la + (lb - la) * (it - ia) / (ib - ia))
    raise ValueError(t)


def node_v(t: float, vdd: float = V3V3_NOM) -> float:
    r = interp_r(t)
    return vdd * r / (r + R_PULLUP)


def atten_for(v: float) -> tuple[int, float]:
    for a, below, fs in ATTEN:
        if below is None or v < below:
            return a, fs
    raise AssertionError


def t_of_ratio(x: float) -> float:
    return piecewise_beta_t(R_PULLUP * x / (1 - x), GT2_104_KOHM, extrapolate=True)


def verify_pdf(pdf: Path) -> list[str]:
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True, capture_output=True,
                         text=True).stdout
    got = {}
    for line in txt.splitlines():
        m = re.match(r"^\s*([−-]?\d+)\s+([\d.\s]+)$", line)
        if not m:
            continue
        t = int(m.group(1).replace("−", "-"))
        if t not in GT2_104_KOHM or t in got:
            continue
        v = [float(x) for x in m.group(2).split()]
        # 11 standard columns (102, 202, 502, 103, 203, 503, 104, 104A, 204, 504, 105GT-2),
        # then 3 application columns that every row has. Hot rows (>= 210 C) lack the
        # leading columns, so 104GT-2 is the 5th standard value from the right; cold rows
        # lack trailing ones, so it is the 7th from the left, except at -50 C where
        # 102GT-2 is also missing (6th).
        std = v[:-3]
        got[t] = std[-5] if t >= 210 else (std[5] if t == -50 else std[6])
    bad = [f"{t}: datasheet {got.get(t)} vs transcribed {r}" for t, r in GT2_104_KOHM.items()
           if got.get(t) is None or abs(got[t] - r) > 1e-9 * max(1.0, r)]
    return bad


def pcb_table() -> dict[int, float]:
    tree = ast.parse(PCB_CHECKS.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "GT2_104" for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError("GT2_104 not found in pcb/checks.py")


def c_float(x: float) -> str:
    t = f"{x:.6g}"
    return (t if ("." in t or "e" in t) else t + ".0") + "f"


def write_header() -> None:
    ks = sorted(GT2_104_KOHM)
    lines = [
        "/* Generated by output/temper-sensor-r3/firmware/rim_ntc.py - do not edit. */",
        "/*",
        " * Semitec 104GT-2 zero-load resistance (ohm) against temperature (degC).",
        " * Source: Semitec GT-2 series datasheet, R-T table, column 104GT-2",
        " * (https://www.semitec.co.jp/uploads/GT-2シリーズ.pdf, retrieved 2026-10-15,",
        " * sha256 c0a2841d9db01c672a840100baab1d034fb01295bcdb54b012cb8a52ac2d07b0).",
        " * R25 100 k +/-3 %, B25/85 4267 K +/-2 %, rated -50..+300 degC.",
        " * Interpolation: 1/T linear in ln R between points (rim_ntc.c).",
        " */",
        "#ifndef RIM_NTC_TABLE_H",
        "#define RIM_NTC_TABLE_H",
        "",
        f"#define RIM_NTC_TABLE_N {len(ks)}u",
        "",
        "static const float k_rim_ntc_table_c[RIM_NTC_TABLE_N] = {",
    ]
    for i in range(0, len(ks), 8):
        lines.append("    " + " ".join(f"{float(t):.1f}f," for t in ks[i:i + 8]))
    lines += ["};", "", "static const float k_rim_ntc_table_ohm[RIM_NTC_TABLE_N] = {"]
    for i in range(0, len(ks), 6):
        lines.append("    " + " ".join(f"{c_float(GT2_104_KOHM[t] * 1e3)}," for t in ks[i:i + 6]))
    lines += ["};", "", "#endif /* RIM_NTC_TABLE_H */", ""]
    HEADER.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-pdf", type=Path)
    ap.add_argument("--out", type=Path, default=HERE / "rim-ntc.json")
    args = ap.parse_args()
    checks = {}

    beta = math.log(GT2_104_KOHM[25] / GT2_104_KOHM[85]) / (1 / 298.15 - 1 / 358.15)
    checks["B25_85_from_table_matches_4267K"] = abs(beta - B25_85_K) < 1.0
    pcb = pcb_table()
    mism = {t: (r, GT2_104_KOHM.get(t)) for t, r in pcb.items() if GT2_104_KOHM.get(t) != r}
    checks["pcb_checks_GT2_104_agrees"] = not mism
    if args.verify_pdf is not None:
        bad = verify_pdf(args.verify_pdf)
        checks["datasheet_pdf_column_matches"] = not bad
        for b in bad:
            print("PDF MISMATCH", b)

    # Leave-one-out interpolation error, 100..280 C (the channel's useful span).
    loo = []
    ks = sorted(GT2_104_KOHM)
    for t in ks:
        if not 100 <= t <= 280 or t in (85,):
            continue
        sub = {k: v for k, v in GT2_104_KOHM.items() if k != t and k != 85}
        r = r_table(t)
        loo.append({"T_C": t, "piecewise_beta_err_K": round(piecewise_beta_t(r, sub) - t, 4),
                    "loglinear_err_K": round(loglinear_t(r, sub) - t, 4)})
    worst_pb = max(abs(x["piecewise_beta_err_K"]) for x in loo)
    worst_ll = max(abs(x["loglinear_err_K"]) for x in loo)
    checks["piecewise_beta_beats_loglinear"] = worst_pb < worst_ll

    rows = []
    for t in CHECK_T:
        v = node_v(t)
        a, fs = atten_for(v)
        sat = v >= ATTEN[-1][2]
        dv = node_v(t) - node_v(t + 0.5) + node_v(t - 0.5) - node_v(t)  # V per K, central
        r = interp_r(t)
        i = V3V3_NOM / (r + R_PULLUP)
        sh = i * i * r / DISSIPATION_W_PER_K
        rows.append({"T_C": t, "R_ohm": round(r, 3), "node_mV": round(v * 1e3, 2), "atten": None if sat else a,
                     "saturated": sat, "mV_per_K": round(dv * 1e3, 3),
                     "K_per_mV": None if sat else round(1e-3 / dv, 4),
                     "self_heating_still_air_K": round(sh, 2)})
    span = [r for r in rows if 100 <= r["T_C"] <= 250]
    worst_k_per_mv = max(r["K_per_mV"] for r in span)
    checks["resolution_1mV_le_0p3K_100_250C"] = worst_k_per_mv <= 0.3
    checks["25C_is_saturated"] = rows[0]["saturated"]
    sh_curve = []
    for t in range(100, 251, 5):
        r = interp_r(float(t))
        i = V3V3_NOM / (r + R_PULLUP)
        sh_curve.append(i * i * r / DISSIPATION_W_PER_K)
    sat = {f"{vdd:.3f}": round(t_of_ratio(ATTEN[-1][2] / vdd), 2) for vdd in (V3V3_MIN, V3V3_NOM, V3V3_MAX)}
    short = {f"{vdd:.3f}": round(t_of_ratio(SHORT_BELOW_V / vdd), 2) for vdd in (V3V3_MIN, V3V3_NOM, V3V3_MAX)}
    checks["short_threshold_above_290C"] = min(short.values()) > 290.0
    checks["saturation_below_150C_open_rule"] = max(sat.values()) < 150.0
    # Rail error without the MCP3202 reading (nominal 3.300 V assumed, true at the contract limits)
    rail = []
    for t in (100.0, 150.0, 200.0, 250.0):
        for vdd in (V3V3_MIN, V3V3_MAX):
            rail.append(abs(t_of_ratio(node_v(t, vdd) / V3V3_NOM) - t))
    # ... and with it (D-RAIL): the reading off by rail_adc.py's full-range error (-40..85 degC
    # board, the rim runs while cooking), either way, at every contract voltage
    rail_m = []
    for t in (100.0, 150.0, 200.0, 250.0):
        for vdd in (V3V3_MIN, V3V3_NOM, V3V3_MAX):
            for sgn in (-1.0, 1.0):
                rail_m.append(abs(t_of_ratio(node_v(t, vdd) / (vdd * (1.0 + sgn * rail_adc.FULL_TOL))) - t))
    checks["measured_rail_error_below_fallback"] = max(rail_m) < max(rail)
    write_header()

    out = {
        "source": SOURCE,
        "table_kohm": {str(k): v for k, v in GT2_104_KOHM.items()},
        "B25_85_from_table_K": round(beta, 1),
        "pcb_checks_mismatches": {str(k): v for k, v in mism.items()},
        "interpolation_leave_one_out_20K_step": {
            "rows": loo, "worst_piecewise_beta_K": worst_pb, "worst_loglinear_K": worst_ll,
            "note": "each interior point predicted from neighbours 20 K apart; the driver interpolates over "
                    "10 K, where the error is about a quarter of this (scales with step^2): an estimate"},
        "channel": {"rows": rows, "worst_K_per_mV_100_250C": worst_k_per_mv,
                    "saturation_C_by_v3v3": sat, "short_0p25V_C_by_v3v3": short,
                    "self_heating_still_air_max_K_100_250C": round(max(sh_curve), 2),
                    "self_heating_note": "not subtracted by the driver: on the glass the dissipation is higher "
                                         "than the still-air 0.6 mW/K, so the true offset is smaller; the rim "
                                         "therefore reads high by at most this (DECISIONS D-RIM)",
                    "rail_error_without_MCP3202_worst_K": round(max(rail), 2),
                    "rail_error_with_MCP3202_worst_K": round(max(rail_m), 2),
                    "rail_with_MCP3202_tol_pct": round(rail_adc.FULL_TOL * 100, 3)},
        "checks": checks, "all_pass": all(checks.values()),
    }
    args.out.write_text(json.dumps(EC.stamp(out), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(f"leave-one-out worst: piecewise-beta {worst_pb:.4f} K, log-linear {worst_ll:.4f} K")
    print(f"worst K/mV 100-250 C: {worst_k_per_mv:.4f}; saturation {sat}; short {short}")
    print(f"rail error 100-250 C: {max(rail):.2f} K assumed 3.300 V, {max(rail_m):.2f} K measured "
          f"({rail_adc.FULL_TOL * 100:.3f} %)")
    print("ALL RIM NTC CHECKS PASS" if out["all_pass"] else "RIM NTC CHECK FAILURE")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
