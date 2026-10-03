# 06 — Controller interface cross-check (J4)

Part of the [master plan](00-MASTER-PLAN.md). Read the master plan's ground
rules first.

## Goal

Prove that the power board and every board it connects to agree on J4
signal by signal. Check the pin, direction, voltage level, polarity, default
state when either side is unpowered or unplugged, current, and timing. Nothing
checks across boards today. An earlier review found a fault-polarity mismatch
of exactly this kind. It's fixed, and FAULT-INTERFACE.md records the fix.

Evidence class: **exact structural** for pin and net correspondence;
**bounded calculation** for levels and currents. The physical test that
confirms it is a harness continuity test and powered interface checks at
bring-up.

## J4 on this board

J4 is a Molex Micro-Fit 3.0 43045-1612, a 2 × 8 header. The pin map below is
from `elec/src/power_stage_120v.ato`, lines ~528–545. Re-read it; don't trust
this copy.

| Pin | Net | Pin | Net |
| --- | --- | --- | --- |
| 1 | V15_SELV | 9 | PERMIT |
| 2 | SELV_GND | 10 | BUS_FAULT |
| 3 | V3V3 | 11 | VBUS_P |
| 4 | SELV_GND | 12 | VBUS_N |
| 5 | PWM_HA | 13 | CT_S1 |
| 6 | PWM_LA | 14 | CT_S2 |
| 7 | PWM_HB | 15 | SELV_GND |
| 8 | PWM_LB | 16 | SELV_GND |

POWER-SECTION.md §3 says the ESP32 controller, current-sense, thermal,
interlock and RTD boards connect through this one header.

## Counterparts to find

Use `git grep` for the net names (`BUS_FAULT`, `PERMIT`, `PWM_HA`, `CT_S1`,
`VBUS_P`, `V15_SELV`) across the repo.

| Board | Where to look |
| --- | --- |
| Interlock | `zapote/interlock/`, including `INTERFACES.md` |
| Gate-drive | `zapote/gate-drive/INTERFACES.md` |
| Current-sense | `zapote/current-sense/` |
| Controller (ESP32) | Search `zapote/` and `pcb/`, read-only. **Never edit `pcb/temper.kicad_pcb` or `elec/` at the repo root** |
| Connection manifest | `zapote/ports.toml` and `zapote/project.toml` may declare cross-board ports |

If a counterpart doesn't exist yet, say so. The interface contract then goes in
the report as a requirement for that board.

## Checks, one row per pin in the report

1. **Pin and net correspondence:**
   - Which board and pin each J4 pin mates with, through which cable
     or connector.
   - **Micro-Fit orientation:** with a straight 2 × 8 cable, does pin 1 land
     on pin 1? Check the Molex drawing for the cable assembly type and
     whether the rows mirror.
2. **Direction and supply ownership:**
   - V15_SELV: PS1 (IRM-20-15) on this board makes 15 V SELV. Who consumes it,
     and what's the total load vs the IRM-20-15 rating?
   - V3V3 comes *in* from the controller and powers the SELV sides of U1, U2,
     U4 and U9. What's the current budget, and is the controller's 3.3 V
     regulator sized for it?
3. **Logic levels:**
   - **PWM inputs:** the UCC21550 input thresholds at VCCI = 3.3 V (datasheet)
     vs the controller's output VOH/VOL.
   - **PERMIT:** its level and polarity, and what the permit FETs Q1/Q4
     (AO3400A) need at their gates.
   - **BUS_FAULT:** already documented in FAULT-INTERFACE.md. The ISO7710
     VOH ≥ VCC2 − 0.3 V gives ≥ 2.835 V; the interlock needs ≥ 2.7 V high and
     ≤ 0.3 V low. Re-verify against the current datasheets.
4. **Default states:** for each signal, what happens when:
   - (a) the controller is unpowered but the power board is live
   - (b) the cable is unplugged
   - (c) V3V3 is present but the controller is in reset

   **Every case must leave the bridge off.** Check pull-ups and pull-downs
   on both sides and the UCC21550 input defaults (datasheet).
5. **CT secondary, the priority safety check:**
   - T1's secondary goes out on CT_S1/CT_S2. **Find where the burden resistor
     is.** If it's only on the far board, then unplugging the cable while the
     tank runs open-circuits a CT carrying up to ~37 A primary. The secondary
     voltage can then rise far above SELV levels.
   - Report where the burden is. If it's off-board, report whether anything
     (a local burden or clamp on this board) limits the open-circuit voltage.
   - **An unprotected open-circuit CT on a SELV connector is a FAIL** to be
     escalated.
6. **VBUS_P/VBUS_N:** the U4 AMC1311 differential output range vs the
   controller ADC input range and common mode. The divider gain is R26–R29
   (1.88 MΩ) over R30 (15.8 kΩ). Report the ADC code at 0, 198 and 280 V.
7. **Timing:** PWM dead-time ownership. Both the controller and the UCC21550
   DT pin set dead time; which one dominates? Also the PERMIT and BUS_FAULT
   latency. Coordinate with task 02.
8. **Ground and return:** SELV_GND has 5 pins. Are they enough for the return
   current, and are the SELV grounds tied to PE only at the one functional
   bond (D5, R38)?

## Acceptance criteria

- Every one of the 16 pins has a verdict: OK, MISMATCH, or UNKNOWN (with a
  reason).
- Any MISMATCH, or any default state that could enable the bridge, is a FAIL.
- The CT open-circuit question has a definite answer.

## Deliverables

In `validation-results/06-controller-interface/`:

- `README.md`, with the 16-row pin table and the default-state table
- `scripts/interface_check.py`, which extracts both sides' pin/net maps from
  their source files and diffs them, so the check can rerun
- A recommendation for a permanent Rust cross-board rule (ports.toml-based)
  if one would have caught the mismatches. **Don't implement it here.**
