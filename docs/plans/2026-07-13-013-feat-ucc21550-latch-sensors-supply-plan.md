---
title: UCC21550 latch, sensor, and supply closure
type: feat
status: stale
date: 2026-07-13
origin: docs/brainstorms/2026-07-13-real-induction-board-closure-arc-requirements.md
swept: 2026-07-25
swept_basis: "insufficient evidence - needs human triage"
---

# UCC21550 latch, sensor, and supply closure

Closed in the current slice:

- VCCI is supplied from 3.3 V; the 15 V rail is kept for gate-side power.
- DIS is active-high on the `SHUTDOWN` net.
- OCP/OVP/thermal faults are latched by a cross-coupled NAND SR latch.
- Watchdog RESET_N and firmware runaway-cut feed the fault bus.
- Reset is fault-qualified so a live fault cannot be cleared by firmware.
- DT uses a 34 kΩ resistor rather than the unsupported capacitor topology;
  this is 305.4 ns nominal, not a guaranteed 300 ns hardware minimum.
  The in-box corner model reports 270.5–343.2 ns when a 100-ppm/°C resistor,
  −40…150 °C, and the datasheet-derived ±10% device envelope are included.
  A 39 kΩ candidate clears 300 ns in that model but still requires scope
  correlation and a system-level gate-transition check.

Open evidence gates:

1. Choose 34 kΩ as a nominal-only starting point or review the 39 kΩ
   worst-corner candidate; then scope-correlate the selected resistor to the
   required 300 ns minimum across temperature and gate-drive load.
2. The specified hardware open/short/out-of-range sensor-fault front end is
   captured alongside the retained firmware path. The MAX31865 SPI fault status and the
   independent comparator cover different failure modes; either one must
   assert the same latched fault. The executable resistance model and property
   tests live in `temper_placer.validation.rtd_safety` and
   `tests/validation/test_rtd_safety_pbt.py`.
   The selected interface is a default-high `RTD_HW_FAULT`: post-ferrite
   `RTD_AVDD` powers the MAX31865/window logic, an upstream rail monitor
   rejects brownout before the window comparators become undefined, and an
   Ioff-rated open-drain NAND sinks the fault line only when both window and
   rail permissions are valid. A second aggregate OR preserves set dominance
   because the original `SN74HC4075` is fully allocated. The selected
   REF2025/TLV3201/TPS3700 resistor network has property coverage and nominal
   selected-value ngspice coverage. Independently written, scope-bounded
   portable ngspice models now preserve the TI model pin order, safety supply
   floors, and output modes in the full RTD deck; tolerance/PVT remains covered
   by property tests rather than an unreviewed PSpice conversion. Low-voltage
   bench capture remains a release gate. See
   `docs/hardware/RTD_SAFETY_DUAL_PATH.md`.
3. Verify the MCU GPIO7 watchdog-kick output, GPIO6 watchdog input, GPIO14
   reset-request input, and GPIO15 runaway-cut output against the firmware pin
   manifest before PCB release.

Firmware now routes software-detected fan, RTD, and ADC faults through the
active-high runaway-cut helper before entering `STATE_FAULT`. The full firmware
CTest suite passes; physical GPIO assertion and the sensor threshold/front-end
choice remain hardware-review evidence gates.

The firmware now uses the inclusive 10 Ω/300 Ω PT100 guard thresholds from
generated configuration for detection and reset clearance. The legacy >10 kΩ
condition remains a secondary gross-open diagnostic so the existing 15 kΩ SIL
trace continues to exercise its historical case; it does not weaken the 300 Ω
safety boundary. The captured analogue window comparator uses the MAX31865
VBIAS/RREF topology at the local `REFIN−`/`ISENSOR` node; the tolerance model
sweeps its declared voltage/RREF corners. Vendor-macro-model PVT and bench
evidence remain required before PCB release.

The prior GPIO collision was removed: runaway-cut is GPIO15, not the PWM_L pin;
the contract test asserts the complete non-overlapping safety map.

The latch contract also has Hypothesis coverage over generated fault/reset
sequences, including simultaneous fault and reset assertions.
