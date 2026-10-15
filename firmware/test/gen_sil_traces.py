#!/usr/bin/env python3
"""
Generate the SIL fault-injection traces added for the C1 pan-sensor loop
(output/temper-sensor-r3/firmware/DECISIONS.md D-SIL).

The original traces in firmware/test/traces/ were written by hand for the
legacy loop and are left untouched. This script writes only the traces it
owns (TRACES below) and is deterministic: rerunning it reproduces the
committed files byte for byte.

    python3 firmware/test/gen_sil_traces.py           # (re)write the traces
    python3 firmware/test/gen_sil_traces.py --check   # exit 1 on any drift

Trace format (firmware/test/test_sil_fault_injection.c, load_csv): one row per
100 ms, columns

    tick, hs_temp, pan_temp, dc_current, rtd_resistance, pan_impedance,
    fan_running, rtd_drdy

`rtd_drdy` (1 = the MAX31865 keeps delivering conversions) is read only by the
C1 SIL target, which models the converter at the register level; the legacy
target ignores it. The style follows the hand-written traces:

  * the pan reading carries +0.1 K on every 5th row, so a healthy trace never
    repeats one value for more than 4 rows (20 C1 conversions, against the
    250-conversion frozen-code limit and the legacy 49-read stuck check);
  * dc_current 5.0 A and rtd_resistance 100.0 ohm are the traces' nominal
    placeholders. A value that differs from row 0 is an injected fault. The
    C1 target replaces the placeholders with the physically consistent value
    (current from the commanded power, resistance from the pan temperature),
    because C1 cross-checks both (DECISIONS D-SIL).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TRACE_DIR = Path(__file__).resolve().parent / "traces"
HEADER = "tick,hs_temp,pan_temp,dc_current,rtd_resistance,pan_impedance,fan_running,rtd_drdy"

HS_C = 35.0
I_NOMINAL_A = 5.0
R_NOMINAL_OHM = 100.0
Z_PAN = 5.0

# A power stage stuck on at full output: 1.8 kW at 120 V.
I_STUCK_ON_A = 15.0
# The ramp a stuck-on stage gives a pan (K per 100 ms row): 1.5 K/s.
STUCK_RAMP_K_PER_ROW = 0.15
# A sensor-path rise faster than R1's 15 K/s limit: 20 K/s.
SENSOR_RAMP_K_PER_ROW = 2.0


def noise(row: int) -> float:
    """The hand-written traces' live-sensor pattern: +0.1 K every 5th row."""
    return 0.1 if row % 5 == 0 else 0.0


def row(t, pan, cur=I_NOMINAL_A, rtd=R_NOMINAL_OHM, fan=1, drdy=1, hs=HS_C, z=Z_PAN):
    return f"{t},{hs:.1f},{pan:.2f},{cur:.1f},{rtd:.1f},{z:.1f},{fan},{drdy}"


def ramp(n_rows, start_c, at, k_per_row, cur_after=I_NOMINAL_A):
    out = []
    for t in range(n_rows):
        if t < at:
            out.append(row(t, start_c + noise(t)))
        else:
            out.append(row(t, start_c + k_per_row * (t - at) + noise(t), cur=cur_after))
    return out


def step_hold(n_rows, start_c, at, hold_c):
    return [row(t, (start_c if t < at else hold_c) + noise(t)) for t in range(n_rows)]


def rtd_fault(n_rows, start_c, at, r_ohm):
    return [row(t, start_c + noise(t), rtd=(R_NOMINAL_OHM if t < at else r_ohm))
            for t in range(n_rows)]


def no_drdy(n_rows, start_c, at):
    return [row(t, start_c + noise(t), drdy=(1 if t < at else 0)) for t in range(n_rows)]


def frozen(n_rows, start_c, at):
    """Live pattern until `at`, then one value held (the last distinct row is
    the last noise row before `at`)."""
    return [row(t, start_c + (noise(t) if t < at else 0.0)) for t in range(n_rows)]


# Pan removed at row 40 (impedance below the 3.0 presence threshold): HEATING
# -> NO_PAN after the debounce, -> COOLDOWN after NO_PAN_TIMEOUT_MS. The
# heatsink sits at 55 degC (above SAFE_IDLE_TEMP 50, below OVER_TEMP 80), so
# COOLDOWN does not end on its first update at either cadence: the legacy SIL
# steps 100 ms per update and reaches COOLDOWN at row 81, the firmware's
# 10 ms cadence (C1 target) at row 71. Both are in COOLDOWN at row 90.
HS_HOT_C = 55.0
PAN_REMOVED_AT = 40
Z_REMOVED = 2.0


def cooldown(n_rows, at, hs_of_t):
    return [row(t, 92.0 + noise(t), hs=(HS_HOT_C if t < at else hs_of_t(t)),
                z=(Z_PAN if t < PAN_REMOVED_AT else Z_REMOVED))
            for t in range(n_rows)]


# name -> rows. Perturbation ticks and expectations live in manifest.json.
TRACES = {
    # Power stage stuck on (current sense working): legacy latches target +
    # 10 K, C1 latches supervisor stage 2a.
    "trace_stage_stuck_on_heating.csv": lambda: ramp(400, 92.0, 85, STUCK_RAMP_K_PER_ROW, I_STUCK_ON_A),
    "trace_stage_stuck_on_preheat.csv": lambda: ramp(400, 80.0, 85, STUCK_RAMP_K_PER_ROW, I_STUCK_ON_A),
    # Double fault: stuck-on stage and a bus-current sense reading 0. Legacy
    # latches target + 10 K, C1 latches stage 2b.
    "trace_stage_stuck_on_current_sense_lost_heating.csv":
        lambda: ramp(500, 92.0, 85, STUCK_RAMP_K_PER_ROW, 0.0),
    # Sensor-path rise at 20 K/s: legacy 15 K/s per-read check, C1 R1.
    "trace_sustained_rise_heating.csv": lambda: ramp(200, 92.0, 85, SENSOR_RAMP_K_PER_ROW),
    "trace_sustained_rise_preheat.csv": lambda: ramp(200, 80.0, 85, SENSOR_RAMP_K_PER_ROW),
    # Reading target + 15 K for 31 s with an obeying stage (h_c drop, hot
    # pan): C1 holds the power at 0 and must not latch (stage 1 only).
    "trace_c1_over_target_obeying_stage_heating.csv": lambda: step_hold(400, 92.0, 85, 115.0),
    # C1 MAX31865 paths from IDLE (the converter is serviced in every state).
    "trace_c1_probe_open_idle.csv": lambda: rtd_fault(120, 25.0, 20, 15000.0),
    "trace_c1_probe_short_idle.csv": lambda: rtd_fault(120, 25.0, 20, 5.0),
    "trace_c1_frozen_idle.csv": lambda: frozen(120, 25.0, 20),
    "trace_c1_no_drdy_idle.csv": lambda: no_drdy(120, 25.0, 20),
    "trace_c1_no_drdy_heating.csv": lambda: no_drdy(151, 92.0, 85),
    # COOLDOWN-origin faults at either cadence (the hand-written
    # trace_fault_cooldown_overheat.csv / trace_fault_relay_welded.csv reach
    # COOLDOWN one 100 ms update before the heatsink step, with the heatsink
    # at 35 degC; at 10 ms the machine has already gone COOLDOWN -> IDLE).
    "trace_cooldown_overheat_hot_heatsink.csv": lambda: cooldown(160, 90, lambda t: 65.0),
    "trace_relay_welded_hot_heatsink.csv":
        lambda: cooldown(160, 90, lambda t: min(75.0, HS_HOT_C + 2.0 * (t - 89))),
    # PAN_DET with the fan off and no pan for 1 s, then pan placed and fan on:
    # the PAN_DET dwell (power_set_level(5)) outlasts one 100 ms row at either
    # cadence. The hand-written trace_gap_pan_det_fan_failure.csv dwells 3
    # legacy updates (300 ms); at 10 ms that is 30 ms and the fan is still off
    # when PREHEAT starts.
    "trace_gap_pan_det_fan_failure_dwell.csv": lambda: [
        row(t, 25.0 + noise(t), fan=(0 if t < 10 else 1), z=(Z_REMOVED if t < 10 else Z_PAN))
        for t in range(40)],
    # 80 ohm: inside the legacy 10..300 ohm window, below the C1 84.27 ohm
    # short threshold. Exercises the C1 window end to end, reset included.
    "trace_c1_rtd_low_80ohm_heating.csv": lambda: rtd_fault(151, 92.0, 85, 80.0),
}


def render(rows):
    return HEADER + "\n" + "\n".join(rows) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if a committed trace differs")
    args = ap.parse_args()
    drift = []
    for name, make in TRACES.items():
        text = render(make())
        path = TRACE_DIR / name
        if args.check:
            if not path.exists() or path.read_text() != text:
                drift.append(name)
        else:
            path.write_text(text)
    if args.check:
        if drift:
            print("SIL trace drift (rerun gen_sil_traces.py): " + ", ".join(drift), file=sys.stderr)
            return 1
        print(f"SIL traces up to date ({len(TRACES)} generated traces)")
    else:
        print(f"wrote {len(TRACES)} traces to {TRACE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
