# D-17: protection timing on the FEM matrix — fault current at gate-off and device survival (task 02)

**Read [README.md](README.md) first (ground rules, board facts).**
Power-stage task 02 follow-up; indexed here with the other delegated work.

## Why it matters

Task 02 round 3 (`validation-results/02-protection-timing/round3/`) left:

- **BLOCKED** (`round3/b2-gate-off/`): the fault current at the moment the
  MOSFETs are actually off (F2) and the dynamic F3 case, because there was no
  board inductance and no assembled gate-off chain;
- a **FAIL** of the 44 A minimum shunt-OCP criterion at +85 °C corners
  (shunt OCP 38.44–85.55 A with assumed R5 self-heating; CT 50.56–60.01 A;
  OVP 272.09–288.02 V);
- the owner's round-3 decision **B (shunt as backup, resistor-only R34/R35
  retune): Hold** "until fault-current, device-energy and actual gate-off
  timing are proven" (`round3-coordination/decision-review/README.md`).

Task 01 now supplies the board loop inductances
(`round17/d2/legA-h0-best.matrix.txt`) and a validated switching deck
(`round17/d2/leg_matrix.cir`, `run_d2.py`). The dead time is 443 ns nominal
for native-18 (`DECISIONS.md` 2026-10-03), which does not change the fault
chain.

## Task

1. **Gate-off chain:** assemble the full delay from threshold crossing to
   gates off for the CT path and the shunt-OCP path, using the round-3
   results for the detector front end (A3/A5: comparator, filters,
   20 mV + 55 ns estimates and their conditions) and the frozen netlist for
   the rest: U8 NAND → U9 ISO7710 → J4.10 `BUS_FAULT` → interlock (if its
   timing is not specified, bound it from `zapote/interlock/` or mark it
   as an owner input) → `PERMIT` → Q1/Q4 → UCC21550 DIS → driver output →
   gate discharge through the driver pull-down and R10/R12 into the D2
   deck's gate loop with the FEM matrix. Cite every datasheet delay
   (min/max, temperature).
2. **Fault scenarios:** follow the task-02 plan
   (`validation-plan/02-protection-timing.md`) scenario definitions. At
   minimum: tank overcurrent ramp reaching the CT trip and the shunt trip at
   their worst-case thresholds (both corners from round 3), and a hard
   shoot-through or shorted-load event at 170 / 198 / 280 V. For each, run the
   D2 deck (with a fault-current source/ramp and the gate-off delay applied
   to the gate commands) on the best matrix, ESL 1.06 and 10 nH.
3. **Survival:** for each scenario report the current at actual gate-off,
   peak die VDS at the fault turn-off (vs 650 V; the 520 V screen from
   task 01), the device energy (D-6's overlap-proxy definition and an
   avalanche check if VDS reaches breakdown), T1's current vs its 88 A
   rating, and returned energy to the bus. State plainly any fault this
   hardware cannot stop in time.
4. **Decision B input:** with the above, say what R34/R35 retune (if any)
   moves the shunt-OCP band above 44 A at the hot corner while keeping the
   fault current at gate-off within device ratings; or show it cannot.
   Proposal only.

## Deliverable

`round17/delegation/out-D17/README.md`: one-line answer (are faults stopped
within ratings, with what margin; recommendation on decision B), the delay
budget table, the scenario/survival table, runner and raw outputs (no vendor
library). Proposals only: do not edit the board, netlist, `elec/`, `pcb/` or
firmware.

## Acceptance

Every delay traces to a cited datasheet page or a committed simulation;
the switching baseline reproduces `d2/results/grid-best/` for a matching
non-fault case; aborts are indeterminate, never passes (D-14's
`.options itl4=100000` may be used and must be stated); bounds are stated
as bounds only when they stack worst cases.
