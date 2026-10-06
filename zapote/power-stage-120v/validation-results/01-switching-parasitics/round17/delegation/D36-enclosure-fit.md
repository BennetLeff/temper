# D-36: power board + heatsink + airflow fit in the R4 enclosure (fit gate + cooling architecture)

**Read [README.md](README.md) first (ground rules).** This task builds a
**rerunnable fit gate**: custom software that catches packaging problems
before layout, in the spirit of the zapote validators. It is not a one-off
render. It is analysis and CAD only: no board, netlist, `elec/` or firmware
change.

## Why it matters

The enclosure-driven re-layout (native-21) is about to start
(`zapote/power-stage-120v/RELAYOUT-REQUIREMENTS.md`). No one has checked the
current power board, its heatsink, fans, duct or EMI filter module against the
owner's enclosure:

- **R4** (`/Users/bennet/Desktop/temper/output/temper-flush-front-r4/`; source
  and checks tracked in git under `output/temper-flush-front-r4/`, STEP exports
  local only) states in its README: "The current 240x160mm full-bridge PCB and
  its 305mm-class shared sink are different hardware; their integrated fit and
  airflow are not established by this assembly." Its `inputs/current-pcb.step`
  is a **historical** board.
- The **Oct 2 integrated study** (`/Users/bennet/Desktop/temper/output/temper-inbox-cad/`,
  local only: `integrate.py`, `findings.html`, `geometry-evidence.json`)
  established the constraints:
  - a 105 mm body;
  - **90 mm clear vertical space** between the base top and the glass underside;
  - a **forward, rotated board placement** (90°, Y 154 mm), because the
    centered placement intersects the Ø36 mm centre-sensor service corridor
    (Z −40…86); the board's rear edge is only 0.5 mm from that corridor;
  - the old BOM sink (120 × 125 × 135.8 mm) cannot fit in any orientation.

  It used an older board with two TO-247s.
- **Native-20** (current; copper identical to native-19) has **all four TO-247s
  vertical in one row along the board's y ≈ 4.2 mm edge**: Q5/Q6/Q3/Q2 at
  x = 92.55/110.55/132.55/150.55 mm, a 58 mm span. BR1 (the bridge rectifier)
  also goes on the sink.
- The **cooling allocation** (DECISIONS.md 2026-10-03, D-18 `out-D18/`) is a
  shared PE-bonded sink with RθSA ≤ 0.15 °C/W at the operating flow, ≥ 20 CFM
  through it, ≤ 1.0 °C/W per MOSFET interface, a 50 °C design inlet, and
  airflow from the coil/right end to the mains/left end. The example envelope is
  Wakefield SFA2B1L, 60 × 305 mm, 68 mm tall plus fans. **Sink load is about
  100–121 W** at the approved full-power cases (D-18 table: four FETs at
  18–25 W plus BR1 at 12–28 W).
- Also reserved: a **20 A DM + CM inlet filter module, 110 × 80 × 50 mm, 8 W**,
  out of the sink exhaust (DECISIONS.md 2026-10-05), and fans on their own
  SELV 12 V supply.

**Assume R4 is the current enclosure.** If the owner points to a newer one,
switch to it; the gate must take the enclosure as an input.

## Task

1. **Board model.** Export native-20's populated STEP with
   `kicad-cli pcb export step --subst-models --no-dnp` (see
   `native-19/verification/reproduction-commands.json`; 24 bodies are authored
   provisional envelopes, which is fine for fit). Do not commit the STEP; commit
   its SHA-256 and the command.
2. **Fit gate** (`zapote/power-stage-120v/validation-plan/enclosure-fit/fit_gate.py`,
   CadQuery 2.6.1 as R4 pins it; set up the environment from R4's
   `requirements-model.txt`). Inputs are JSON: enclosure STEP(s) and named keep-outs
   (glass, coil, sensor corridor plus a **≥ 3 mm tool margin**, base, lid), board
   STEP and pose, and envelopes for sink, fans, duct, EMI module and fan supply.
   Checks, each reported PASS/FAIL with the interference volume or minimum
   clearance:
   - every solid pair is interference-free;
   - everything sits below the 90 mm clear height;
   - the sensor service corridor is clear;
   - the TO-247 row faces the sink's mounting face (all four devices plus BR1
     can bolt to it);
   - the duct runs as one path from an inlet on the coil/right side to an exhaust
     on the mains/left side, the EMI module is not in the exhaust, and the
     controller is not downstream of the sink;
   - connector access: J1 (mains in), J4 (controller harness) and the coil
     terminals (J5/J2 area) reach the enclosure openings with a stated bend
     allowance;
   - mounting: at least four board standoffs land on structure.

   Tests: one known-good and one known-bad fixture per check.
3. **Run it** on native-20 at the forward/rotated pose with the D-18 example
   sink (SFA2B1L class) and two 60 × 60 × 25 mm fans.
4. **If the sink does not fit, close the cooling architecture with numbers.**
   For each candidate, compute RθSA at ≥ 20 CFM from vendor curves, or a
   documented fin-channel correlation, against the ≤ 0.15 °C/W requirement at
   ~121 W and a 50 °C inlet, and run the fit gate on it. Candidates:
   - (a) a lower/longer extrusion along the TO-247 row with higher flow;
   - (b) split sinks per leg;
   - (c) the TO-247 row clamped to a spreader into the base, with the base as
     part of the sink (check the D5 insulation basis);
   - (d) moving the board or rotating the row.

   Recommend one, and state the board-outline, device-row and connector
   constraints it imposes on native-21.
5. Output `out-D36/README.md`: a one-line answer first (does native-20 plus the
   D-18 cooling fit R4: yes/no and why), the gate results table, the chosen
   cooling architecture with its thermal numbers, and **a list of layout
   constraints for native-21** (outline, keep-outs, device-row position and
   orientation, connector edges, mounting holes) to append to
   `RELAYOUT-REQUIREMENTS.md`. Propose that edit in the PR; don't make it
   unilaterally.

## Deliverable

A draft PR into `codex/power-stage-120v-build` containing the gate,
tests, fixtures, JSON inputs, hashes of every STEP used, `out-D36/` and
rendered section PNGs. No large STEP/STL commits.
