#!/usr/bin/env python3
"""
Plant model for the Temper induction cooker.

First-order thermal R-C network with two nodes (heatsink, pan) plus a simple
electrical model.  Writes per-tick CSV traces used by the SIL fault-injection
harness.

Usage:
    python3 tools/sil/plant_model.py \
        --scenario heating_to_steady_state \
        --ticks 500 \
        --dt 0.1 \
        --output-dir traces/raw/
"""

import argparse
import csv
import os
import sys

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
R_HEATSINK_PAN = 0.02      # thermal resistance heatsink -> pan [K/W]
R_HEATSINK_AMBIENT = 0.08  # thermal resistance heatsink -> ambient [K/W]
R_PAN_AMBIENT = 0.10       # thermal resistance pan -> ambient [K/W]
C_HEATSINK = 300.0         # heat capacity of heatsink [J/K]
C_PAN = 150.0              # heat capacity of pan [J/K]

MAX_POWER_W = 1800.0       # max power delivery [W]
CURRENT_PER_POWER_UNIT = 0.35  # A per power-level unit (100 units = 35 A)

# RTD PT100 model: R = 100 * (1 + 0.00385 * T_celsius)
RTD_R0 = 100.0
RTD_ALPHA = 0.00385

CSV_COLUMNS = [
    "tick",
    "heatsink_temp_c",
    "pan_temp_c",
    "dc_bus_current_a",
    "rtd_resistance_ohm",
    "pan_impedance",
    "fan_running",
]


def _thermal_step(T_heatsink: float, T_pan: float, T_ambient: float,
                  power_w: float, dt: float):
    """Single Euler step of the two-node thermal RC network."""
    # Heatsink ODE
    dT_hs = (
        power_w
        + (T_pan - T_heatsink) / R_HEATSINK_PAN
        + (T_ambient - T_heatsink) / R_HEATSINK_AMBIENT
    ) / C_HEATSINK

    # Pan ODE
    dT_pan = (
        (T_heatsink - T_pan) / R_HEATSINK_PAN
        + (T_ambient - T_pan) / R_PAN_AMBIENT
    ) / C_PAN

    T_heatsink += dT_hs * dt
    T_pan += dT_pan * dt

    # Temperature floor at ambient
    if T_heatsink < T_ambient:
        T_heatsink = T_ambient
    if T_pan < T_ambient:
        T_pan = T_ambient

    return T_heatsink, T_pan


def run_scenario(scenario: str, ticks: int, dt: float, output_dir: str) -> None:
    """Run a named scenario and write the CSV trace."""

    T_heatsink: float = 25.0
    T_pan: float = 25.0
    T_ambient: float = 25.0

    power_level: float = 0.0
    pan_drop_tick: int = -1

    if scenario == "heating_to_steady_state":
        ticks = max(ticks, 500)
        power_level = 100.0

    elif scenario == "preheat_then_pan_removed":
        ticks = max(ticks, 500)
        power_level = 100.0
        pan_drop_tick = 300

    elif scenario == "standby_long_run":
        ticks = max(ticks, 500)
        power_level = 0.0

    else:
        print(f"ERROR: unknown scenario '{scenario}'", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{scenario}.csv")

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)

        pan_impedance: float = 5.0  # valid pan

        for tick in range(ticks):
            # Pan-impedance drop for pan-removed scenario
            if pan_drop_tick >= 0 and tick >= pan_drop_tick:
                pan_impedance = 1.0
                power_level = 0.0  # cut power

            power_w = power_level / 100.0 * MAX_POWER_W
            dc_bus_current = power_level * CURRENT_PER_POWER_UNIT
            rtd_resistance = RTD_R0 * (1.0 + RTD_ALPHA * T_pan)
            fan_running = 1.0 if power_level > 0 else 0.0

            writer.writerow([
                tick,
                round(T_heatsink, 3),
                round(T_pan, 3),
                round(dc_bus_current, 3),
                round(rtd_resistance, 3),
                round(pan_impedance, 3),
                int(fan_running),
            ])

            T_heatsink, T_pan = _thermal_step(
                T_heatsink, T_pan, T_ambient, power_w, dt)


def main() -> None:
    parser = argparse.ArgumentParser(description="Temper plant model simulator")
    parser.add_argument("--scenario", required=True,
                        help="Scenario name (heating_to_steady_state, "
                             "preheat_then_pan_removed, standby_long_run)")
    parser.add_argument("--ticks", type=int, default=500,
                        help="Number of simulation ticks")
    parser.add_argument("--dt", type=float, default=0.1,
                        help="Time step in seconds (default 0.1)")
    parser.add_argument("--output-dir", default="traces/raw/",
                        help="Output directory for CSV traces")
    args = parser.parse_args()
    run_scenario(args.scenario, args.ticks, args.dt, args.output_dir)


if __name__ == "__main__":
    main()
