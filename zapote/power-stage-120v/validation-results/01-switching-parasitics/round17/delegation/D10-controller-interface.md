# D-10: finish the J4 controller-interface cross-check (all 16 pins)

**Read [README.md](README.md) first (ground rules, board facts).**
This is power-stage task 06, not a round-17 simulation; it lives here so
all delegated work has one index.

## Why it matters

The power stage connects to the controller (ESP32), current-sense, thermal,
interlock and RTD boards through one 2 × 8 header, J4. Task 06
([`validation-plan/06-controller-interface.md`](../../../../validation-plan/06-controller-interface.md))
asks for a pin-by-pin cross-check against every counterpart board. Only
check 5 (the CT secondary, J4.13/14) has been done
([`validation-results/06-controller-interface/README.md`](../../../06-controller-interface/README.md)):
it **failed** on native-09 (no burden anywhere: the current-sense unit has
no input for this CT) and was fixed on native-11 by terminating the CT on the
power board. The other 15 pins have never been checked across boards, and an
earlier review found a fault-polarity mismatch of exactly this kind
(`FAULT-INTERFACE.md`).

## Task

Do task 06 in full, on the **current board** `native-17/section.kicad_pcb`
and `frozen/default.net` (not native-09), following its "Checks" list 1–8
and its acceptance criteria and deliverables, with these specifics:

1. Re-read the J4 pin map from the source (`elec/src/power_stage_120v.ato`
   inside `zapote/power-stage-120v/`) and the frozen netlist; don't trust
   the table in the task doc.
2. For each counterpart board — `zapote/interlock/`, `zapote/gate-drive/`,
   `zapote/current-sense/`, `zapote/thermal-sense/`, `zapote/rtd/` — find
   its connector, pin and net for each J4 signal (`INTERFACES.md`,
   `interface-contract.json`, netlists). The **ESP32 controller** exists only
   inside the root full-board design `pcb/` / `elec/`: read-only, **never
   edit `pcb/temper.kicad_pcb` or `elec/` at the repo root**. Also check
   `zapote/ports.toml` / `project.toml` for declared cross-board ports.
3. Where no counterpart exists, say so and write the requirement that board
   must meet (pin, direction, level, default state, current, timing).
4. Re-check check 5 (CT) on native-17: is the native-11 termination still
   present and is J4.13/14 now a defined, bounded signal? Who consumes it?
5. Check 7 (dead-time ownership) overlaps D-5: cite D-5's result if it is
   done; otherwise record what this check finds and leave the worst-case
   arithmetic to D-5.

## Deliverable

`validation-results/06-controller-interface/README.md` extended (keep the
existing CT section as recorded), with the one-row-per-pin table task 06
asks for, a one-line verdict per pin (PASS / FAIL / NO COUNTERPART /
INDETERMINATE), a list of mismatches ranked by safety consequence, and the
requirements list for missing counterparts. Scripts that extract the pin and
net data go in `validation-results/06-controller-interface/scripts/` with
their outputs. Open the PR against `codex/power-stage-120v-build`.

## Acceptance

Every correspondence traces to a file:line or netlist entry at a cited
commit; levels and currents are bounded calculations with datasheet
citations; no design file is edited. A contradiction between boards is
reported as a finding, not fixed.
