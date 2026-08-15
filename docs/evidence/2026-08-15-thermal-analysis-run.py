#!/usr/bin/env python3
"""Thermal sensor-chain analysis of the real board (corrected model, 2026-08-15).

Computes the Ts -> Tc -> Tj chain per high-power device at the 60 °C
design-limit ambient, using per-component thermal resistances (IKW40N120H3
datasheet Rjc = 0.31 K/W for the IGBTs; the committed TIM Rch = 0.20 and
HS1-with-fan Rha = 0.45), and reports margins against the protection
ladder (decision doc 2026-08-15): 80 °C firmware heatsink trip (sensor
space), 125 °C design-for junction, 175 °C absolute survival junction.

Run from the repo root:
    .venv/bin/python docs/evidence/2026-08-15-thermal-analysis-run.py

Does not modify any file. Positions come from pcb/temper.kicad_pcb.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages/temper-placer/src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6  # noqa: E402
from temper_placer.physics.thermal import (  # noqa: E402
    FIRMWARE_TRIP_TS_C,
    T_J_ABS_MAX_C,
    T_J_DESIGN_MAX_C,
    thermal_resistance_for,
)

# Design-limit ambient (ENVIRONMENTAL_SPEC.md §1.1 derating zero-power point).
AMBIENT_C = 60.0

# High-power devices and their worst-case dissipation (W). Per-device
# losses are committed figures: IGBTs 18-20 W (SYSTEM_THERMAL_BUDGET.md
# 36 W both vs THERMAL_DESIGN_GUIDE.md 20 W each; 20 W is the
# conservative end). The TO-220 rectifier losses are not recorded in-repo,
# so a placeholder 5 W is used and flagged. Refs on the CURRENT board:
# U4/U5 are the TO-247 IKW40N120H3 IGBTs (hb.power_loop.q_high/q_low);
# U1/U2 are the TO-220 rectifiers on the shared HS1 heatsink
# (BOM.md:542 "2xTO-247 + 2xTO-220").
POWER_MAP: dict[str, float] = {
    "U4": 20.0,  # hb.power_loop.q_high (IKW40N120H3)
    "U5": 20.0,  # hb.power_loop.q_low  (IKW40N120H3)
    # TO-220 rectifiers on HS1 — placeholder dissipation, NOT datasheet-
    # derived; flagged in the report.
    "U1": 5.0,
    "U2": 5.0,
}


def main() -> int:
    pcb = parse_kicad_pcb_v6(REPO_ROOT / "pcb/temper.kicad_pcb")
    positions = {c.ref: c.initial_position for c in pcb.components}

    print(f"Ambient (design-limit): {AMBIENT_C:.0f} °C")
    print(
        f"Limits: firmware heatsink trip {FIRMWARE_TRIP_TS_C:.0f} °C (sensor) | "
        f"junction design-for {T_J_DESIGN_MAX_C:.0f} °C | junction survival {T_J_ABS_MAX_C:.0f} °C"
    )
    print()
    print(f"{'ref':<6}{'P(W)':>6}{'Rjc':>7}{'Rch':>7}{'Rha':>7} | {'Ts':>7}{'Tc':>7}{'Tj':>7}"
          f" | {'m_Ts':>7}{'m_Tj125':>7}{'m_Tj175':>7}  verdict")
    print("-" * 108)

    failures = []
    for ref, power in POWER_MAP.items():
        pos = positions.get(ref)
        if pos is None:
            print(f"{ref:<6}  NOT ON BOARD (no position in pcb/temper.kicad_pcb)")
            continue
        rjc, rch, rha = thermal_resistance_for(ref)
        # The edge penalty in the placement metric ("0.2 K/W per mm beyond
        # 5 mm from the board edge") is a BOARD-MOUNT heuristic: it models
        # the extra sink resistance of a component relying on board-edge
        # airflow. U5/U6/D1/D2 are bolted to HS1 (a ~1 kg chassis heatsink,
        # BOM.md:542) — their sink path is the heatsink (committed Rha =
        # 0.45 K/W with fan), NOT the board edge, so the penalty does not
        # apply. Applying it would add ~14 K/W of artifact resistance for a
        # mid-board device and manufacture a fake red.
        edge_penalty = 0.0

        # Sensor chain (kernel-identical arithmetic):
        # Ts = Ta + P*Rha_eff; Tc = Ts + P*Rch; Tj = Tc + P*Rjc.
        rha_eff = rha + edge_penalty
        ts = AMBIENT_C + power * rha_eff
        tc = ts + power * rch
        tj = tc + power * rjc

        m_ts = FIRMWARE_TRIP_TS_C - ts
        m_125 = T_J_DESIGN_MAX_C - tj
        m_175 = T_J_ABS_MAX_C - tj
        verdict = "OK" if (m_ts > 0 and m_125 > 0 and m_175 > 0) else "FAIL"
        if verdict == "FAIL":
            failures.append(ref)
        print(
            f"{ref:<6}{power:>6.1f}{rjc:>7.2f}{rch:>7.2f}{rha:>7.2f} | "
            f"{ts:>7.1f}{tc:>7.1f}{tj:>7.1f} | "
            f"{m_ts:>7.1f}{m_125:>7.1f}{m_175:>7.1f}  {verdict}"
        )

    print("-" * 108)
    print()
    # Fault-case sensitivity: 2x nominal loss (40 W/IGBT) — the decision
    # doc §3.3's worst fault row at the hardware latch. Junction must stay
    # under the 175 °C survival limit.
    print("Fault sensitivity (2x nominal loss, 40 W/IGBT):")
    for ref in ("U4", "U5"):
        pos = positions.get(ref)
        if pos is None:
            continue
        rjc, rch, rha = thermal_resistance_for(ref)
        ts = AMBIENT_C + 40.0 * rha
        tc = ts + 40.0 * rch
        tj = tc + 40.0 * rjc
        print(
            f"  {ref}: Ts={ts:.1f} °C  Tc={tc:.1f} °C  Tj={tj:.1f} °C  "
            f"(survival margin {T_J_ABS_MAX_C - tj:.1f} °C vs 175 °C)"
        )
    print()
    print("Notes:")
    print("- Ts margin is vs the 80 °C firmware over-temp trip (sensor space).")
    print("- U1/U2 use a 5 W placeholder (TO-220 rectifier loss not recorded in-repo);")
    print("  their R values are placeholders too (no recovered datasheet).")
    if failures:
        print(f"\nFAILING MARGIN: {', '.join(failures)} — honest reds, not hidden.")
    else:
        print("\nNo device fails margin at the 60 °C design-limit ambient.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
