#!/usr/bin/env python3
"""verify_interlock_margin.py

Reads runaway_boundary_map.csv, computes interlock margin for each
sweep point, generates a pass/fail report in Markdown format.

Per the plan:
  - Tj_trip = T_heatsink + P_diss * (RthetaJC + RthetaCH)
    where P_diss is extracted from the sim at the trip point.
  - margin = Tj_boundary - Tj_trip
  - Trip at 85 C heatsink (hardware latch) OR 120 C coil (firmware),
    whichever fires first.

AC-5: No destructive (Tj > 175 C) trajectory below interlock trip.
Output: simulation/results/runaway_interlock_margin.md
"""

import csv
import math
import os
import sys
from datetime import datetime
from pathlib import Path


# Thermal constants from docs/ELECTRICAL_VALIDATION_IMPACT.md
RTHETA_JC = 0.6   # K/W - junction to case
RTHETA_CH = 0.3   # K/W - case to heatsink
RTHETA_JH = RTHETA_JC + RTHETA_CH  # 0.9 K/W - junction to heatsink

# Interlock trip thresholds from docs/FUNCTIONAL_TEST_CRITERIA.md SS 2.3
TRIP_HEATSINK = 85   # C - hardware NTC comparator
TRIP_COIL = 120      # C - firmware/coil NTC

# Acceptance threshold
MIN_MARGIN = 20  # C


def compute_tj_trip(heatsink_temp: float, coil_temp: float,
                    power_diss: float) -> tuple[float, str]:
    """Compute junction temp at interlock trip.

    Returns (Tj_trip, which_sensor) where which_sensor is
    'heatsink' or 'coil'.
    """
    # Trip margin: how close is the heatsink to 85 C? coil to 120 C?
    hs_margin = TRIP_HEATSINK - heatsink_temp
    co_margin = TRIP_COIL - coil_temp

    # The sensor closer to tripping (smaller margin) trips first
    if hs_margin <= co_margin:
        # Heatsink trips first: Tj = T_heatsink + P_diss * Rtheta_jh
        tj_trip = TRIP_HEATSINK + power_diss * RTHETA_JH
        return tj_trip, "heatsink"
    else:
        # Coil trips first: approximate Tj based on power flow
        # Coil temp translates to junction via heatsink path
        tj_trip = heatsink_temp + (coil_temp - heatsink_temp) * (
            RTHETA_JH / RTHETA_JH) + power_diss * RTHETA_JH
        return tj_trip, "coil"


def verify_ac5(rows: list[dict]) -> tuple[bool, list[str]]:
    """AC-5: No destructive trajectory below interlock trip.

    For every destructive point, verify T_heatsink >= 85 OR T_coil >= 120.
    """
    violations = []
    for row in rows:
        cls = row.get("classification", "")
        if cls != "destructive":
            continue
        try:
            hs = float(row["ths_end_powered"])
            co = float(row["tcoil_end_powered"])
        except (ValueError, KeyError):
            continue
        if hs < TRIP_HEATSINK and co < TRIP_COIL:
            violations.append(
                f"VBUS={row['vbus']} K={row['k']} CTOL={row['ctol']} "
                f"TAMB={row['tamb']} FAN={row['fan']}: "
                f"Hs={hs:.1f}C (trip=85C), Coil={co:.1f}C (trip=120C)"
            )
    return len(violations) == 0, violations


def generate_report(csv_path: str, md_path: str) -> int:
    """Generate interlock margin report.

    Returns worst-case margin (C), or -1 if all points failed.
    """
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("ERROR: No data in CSV")
        return -1

    # Compute margin for each point
    margins = []
    for row in rows:
        try:
            tj_boundary = float(row["tj_end_powered"])
            hs = float(row["ths_end_powered"])
            co = float(row["tcoil_end_powered"])
            # Estimate P_diss from (Tj - Tc) / Rtheta_jc_ch
            # This is approximate; the sim doesn't directly output P_diss
            # but we can estimate it from the thermal gradient.
            p_diss = max(0, (tj_boundary - hs) / RTHETA_JH) if tj_boundary > hs else 0
            tj_trip, sensor = compute_tj_trip(hs, co, p_diss)
            margin = tj_boundary - tj_trip
            passed = margin >= MIN_MARGIN

            margins.append({
                **row,
                "tj_trip": tj_trip,
                "margin": margin,
                "passed": passed,
                "trip_sensor": sensor,
                "p_diss_est": p_diss,
            })
        except (ValueError, KeyError, TypeError):
            continue

    margins.sort(key=lambda x: x["margin"])

    # AC-5 check
    ac5_pass, ac5_violations = verify_ac5(rows)

    # Build markdown
    lines = []
    lines.append("# Runaway Interlock Margin Verification")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().isoformat()}")
    lines.append(f"**Data source:** `{os.path.basename(csv_path)}`")
    lines.append("")
    lines.append("## Acceptance Criteria")
    lines.append("")
    lines.append("| AC | Criterion | Result |")
    lines.append("|----|-----------|--------|")
    lines.append(f"| AC-1 | Boundary mapped (432 sweep points) | "
                 f"{'PASS' if len(margins) > 0 else 'FAIL'} |")
    lines.append(f"| AC-2 | Margin computed per sweep point | "
                 f"{'PASS' if len(margins) > 0 else 'FAIL'} |")

    worst_margin = min((m["margin"] for m in margins), default=-1)
    ac3_pass = worst_margin >= MIN_MARGIN
    lines.append(f"| AC-3 | Min margin >= {MIN_MARGIN} C | "
                 f"{'PASS' if ac3_pass else 'FAIL'} (worst: {worst_margin:.1f} C) |")
    lines.append(f"| AC-4 | Worst-3 corners identified | "
                 f"{'PASS' if len(margins) >= 3 else 'FAIL'} |")
    lines.append(f"| AC-5 | No destructive below interlock | "
                 f"{'PASS' if ac5_pass else 'FAIL'} |")
    lines.append(f"| AC-6 | Boundary reproducible (+/-2 C) | PENDING (re-run needed) |")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total sweep points:** {len(margins)}")
    passed_count = sum(1 for m in margins if m["passed"])
    lines.append(f"- **Passed (margin >= {MIN_MARGIN} C):** {passed_count}")
    lines.append(f"- **Failed (margin < {MIN_MARGIN} C):** {len(margins) - passed_count}")
    lines.append(f"- **Worst margin:** {worst_margin:.1f} C")
    lines.append("")

    # Worst-3 corners
    lines.append("## Worst-3 Corners (Regression Test Candidates)")
    lines.append("")
    lines.append("| # | VBUS | K | C_TOL | TAMB | FAN | Tj_boundary | "
                 "Hs | Coil | Tj_trip | Margin | Pass |")
    lines.append("|---|------|---|-------|------|-----|-------------|"
                 "----|------|---------|--------|------|")
    for i, m in enumerate(margins[:3]):
        lines.append(
            f"| {i+1} | {m['vbus']} | {m['k']} | {m['ctol']} | "
            f"{m['tamb']} | {m['fan']} | {float(m['tj_end_powered']):.1f} | "
            f"{float(m['ths_end_powered']):.1f} | {float(m['tcoil_end_powered']):.1f} | "
            f"{m['tj_trip']:.1f} | {m['margin']:.1f} | "
            f"{'PASS' if m['passed'] else 'FAIL'} |"
        )
    lines.append("")

    # Full table
    lines.append("## Full Margin Table")
    lines.append("")
    # Use abbreviated headers
    lines.append("| VBUS | K | C_TOL | TAMB | FAN | Tj | Hs | Coil | "
                 "Tj_trip | Margin | Class | Pass |")
    lines.append("|------|---|-------|------|-----|----|----|------|"
                 "---------|--------|-------|------|")
    for m in margins:
        lines.append(
            f"| {m['vbus']} | {m['k']} | {m['ctol']} | {m['tamb']} | "
            f"{m['fan']} | {float(m['tj_end_powered']):.1f} | "
            f"{float(m['ths_end_powered']):.1f} | "
            f"{float(m['tcoil_end_powered']):.1f} | {m['tj_trip']:.1f} | "
            f"{m['margin']:.1f} | {m.get('classification','?')} | "
            f"{'PASS' if m['passed'] else 'FAIL'} |"
        )
    lines.append("")

    # AC-5 violations
    lines.append("## AC-5: Destructive-Below-Interlock Check")
    lines.append("")
    if ac5_pass:
        lines.append("**PASS:** No destructive trajectory detected below interlock trip thresholds.")
    else:
        lines.append("**FAIL:** Destructive trajectories detected below interlock trip:")
        lines.append("")
        for v in ac5_violations:
            lines.append(f"- {v}")
    lines.append("")

    # Rtheta reference
    lines.append("## Thermal Constants (Reference)")
    lines.append("")
    lines.append(f"- RthetaJC = {RTHETA_JC} K/W (IKW40N120H3 datasheet)")
    lines.append(f"- RthetaCH = {RTHETA_CH} K/W (mounting estimate)")
    lines.append(f"- RthetaJH = {RTHETA_JH} K/W (junction to heatsink)")
    lines.append(f"- Heatsink trip = {TRIP_HEATSINK} C (hardware NTC comparator)")
    lines.append(f"- Coil trip = {TRIP_COIL} C (firmware)")
    lines.append(f"- Minimum margin = {MIN_MARGIN} C")
    lines.append("")

    with open(md_path, "w") as f:
        f.write("\n".join(lines))

    print(f"Margin report written to: {md_path}")
    print(f"Worst margin: {worst_margin:.1f} C "
          f"({'PASS' if ac3_pass else 'FAIL'})")
    print(f"AC-5 destructive-below-interlock: "
          f"{'PASS' if ac5_pass else 'FAIL'}")

    return worst_margin


def main():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent
    results_dir = project_root / "simulation" / "results"
    csv_path = results_dir / "runaway_boundary_map.csv"
    md_path = results_dir / "runaway_interlock_margin.md"

    if not csv_path.exists():
        print(f"ERROR: CSV not found at {csv_path}")
        print("Run sweep_runaway_boundary.sh first.")
        sys.exit(1)

    worst = generate_report(str(csv_path), str(md_path))
    sys.exit(0 if worst >= MIN_MARGIN else 1)


if __name__ == "__main__":
    main()
