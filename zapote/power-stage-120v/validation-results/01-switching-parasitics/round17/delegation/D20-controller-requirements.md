# D-20: controller board requirements from the power stage (J4 contract)

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

The power stage connects to a controller (ESP32) that does not yet exist as a
separate unit; it lives only inside the root full-board design (`pcb/`,
`elec/` at the repository root, read-only). Its requirements are scattered
across D-5 (dead time and firmware), D-10 (all 16 J4 pins:
`validation-results/06-controller-interface/README.md`), D-11 (bus-voltage
receiver), D-17 if done (fault-chain timing), and `DECISIONS.md` (2026-10-03:
dead time, bus-sense targets, ADC1 allocation, over-range latch). This brief
turns them into one requirements document the controller is designed
against.

## Task

Write `round17/delegation/out-D20/CONTROLLER-REQUIREMENTS.md`: one numbered,
testable requirement per line, each with its source (file:line or decision
entry) and its verification method (analysis / bench / inspection). Cover:

1. **J4 pin table:** all 16 pins, direction, level, load, default state when
   either side is unpowered/unplugged, connector and harness (from D-10).
2. **PWM:** four outputs for the full bridge (PWM_HA/LA/HB/LB), complementary
   pairs, frequency range (POWER-SECTION §2), and **dead-time ownership**:
   given the UCC21550's DT-pin dead time (native-18: ≈ 397–488 ns, D-12) and
   its combination rule with input overlap (D-1, D-5: cite TI SLUSE89C), state
   what the controller must and must not do (e.g. never overlap the inputs;
   minimum controller-inserted gap, if any); and the power-on, reset and
   brown-out states of all four outputs.
3. **Protection interface:** BUS_FAULT input (J4.10) behaviour and latency
   budget, PERMIT output (J4.9) default and timing, from D-10 and D-17.
4. **Bus sense:** the D-11 receiver, the ADC1 channel, sampling 20 ksample/s
   time-stamped, the accuracy/timing targets and the 1.210 V over-range latch
   with manual re-arm (DECISIONS.md 2026-10-03).
5. **CT signals** (J4.13/14 or their native-17 successors per D-10), supplies,
   returns and grounding ownership.
6. **Open items:** every requirement whose value is not yet fixed, named as
   an open item with its owner.

Also list contradictions between sources (stop and report them; do not
resolve them by choice).

## Deliverable

`out-D20/CONTROLLER-REQUIREMENTS.md` plus `out-D20/README.md` (one-line
summary, coverage table mapping every D-5/D-10/D-11/decision finding to a
requirement, open items). Document only: no board, netlist, `elec/`, `pcb/`
or firmware edits.

## Acceptance

Every requirement traces to a cited source and has a verification method;
no requirement is invented without a source (mark engineering targets as
such); the coverage table has no unmapped finding.
