# Codex handoff, 2026-10-06: four tasks (D-32 … D-35)

**Read [README.md](README.md) first.** Its ground rules apply to every task:
your own worktree from `origin/codex/power-stage-120v-build`, no bare `git
stash`, vendor models fetched and never committed, no Rust workspace builds,
never touch the repository-root `pcb/temper.kicad_pcb` or root `elec/`.

Each task is independent. Use one branch and one **draft PR into
`codex/power-stage-120v-build`** per task, and title the PR with the task id.
Every numeric claim in a PR must come from a committed script or test that
reproduces it.

The decisions these tasks implement are in
[`zapote/power-stage-120v/DECISIONS.md`](../../../../DECISIONS.md),
2026-10-05 entries (low-power control, F6 adoption and its addendum,
protection closure), and the layout checklist in
[`RELAYOUT-REQUIREMENTS.md`](../../../../RELAYOUT-REQUIREMENTS.md).

---

## D-32: firmware — safe state, fixed 180°, and line-synchronous bursts (medium)

**Why.** The power stage is now approved for one operating mode only:
both legs 180° apart at 50 % duty, with power below the frequency-control floor
set by bursts of whole mains half-cycles. Phase shift is removed (FINDINGS F9
closed by decision). Two firmware drafts are open: **#1643** (D-21 dead time)
needs the failure-cleanup fix from FINDINGS F8, and **#1653** (D-29 prototype
conformance) needs finishing.

**Do.**
1. **#1643 (`codex/ps-r17-d21`).** Every cleanup and failure path must end by
   re-asserting each PWM GPIO as a push-pull output driven low (D-25's finding:
   `gpio_reset_pin()` leaves pads floating). Add a host test per failure path
   that asserts the final pad state.
2. **#1653 (`codex/ps-r17-d29-conformance`).** Bring it to the same rule and
   make 180° a hard constraint: any phase other than 180° is rejected at
   configuration time, with a test.
3. **Burst scheduler** in the product firmware (`firmware/`, HAL under
   `firmware/components/hal/`), as a new module with host tests:
   - bursts start and stop only at a **bus zero crossing**, using the bus-sense
     channel (VBUS_P/N via AMC1311, D-11) and the controller's zero-cross logic;
   - they are made of whole half-cycles (8.33 ms at 60 Hz) at 180°;
   - the burst period follows
     `T_burst ≥ max(2 s, 4.6 · d^3.2 / 0.65^3.2)`, with
     `d[%] = 100 · (P/(V·PF)) · (0.4·PF + 0.25·sin(acos PF)) / V`
     from the measured burst power, and a **20 s default**
     (`validation-results/07-conducted-emi/flicker/burst_flicker.py`;
     reuse its numbers as test vectors);
   - a build or config flag `burst_enabled` that **defaults to false**. Native-20
     runs continuous-only until bench test B2 passes
     (`validation-plan/BENCH-NATIVE20-ADDENDUM.md`).
4. Host suite: `cmake -S firmware/test -B <build>` then `ctest`. All tests pass,
   including the existing ones.

**Out of scope.** Frequency-control tuning, the PLL, temperature control, and
any hardware change.

---

## D-33: native-21 source — F6 negative bias from a SELV-fed transformer driver (large)

**Why.** F6 (−2 V off-bias with a 1 nF Cgs and a 1 Ω + PMEG6030EP discharge
branch) is adopted for the enclosure re-layout. In the model it passes all
decision cases at 27/100/150 °C on both legs, plus the S5 burst-start edge,
which fails without it (FINDINGS F2/F6/F11). The owner is doing the layout.
This task delivers the **source and netlist** the layout needs.

**Do.** In `zapote/power-stage-120v/elec/src/` (the power-stage atopile source,
**not** the repository-root `elec/`), implement F6 with a **transformer-driver
isolated bias fed from the existing SELV 15 V rail (PS1)**. This is the
2026-10-06 decision ([BOM-REVIEW-2026-10-06.md](../../../../BOM-REVIEW-2026-10-06.md)
item 1), which replaces D-12's four-RECOM-module variant:
- **one transformer driver** (TI SN6507, 36 V input, push-pull, or the
  UCC25800 class; pick one from its datasheet and justify the choice) on PS1's
  15 V, with **three reinforced-isolation transformers**: HS-A referenced to
  `sw_a`, HS-B to `sw_b`, and one low side referenced to `leg_ret`, shared by
  both low-side channels;
- per secondary: a rectifier, a regulated +15 V (LDO) and a **−2 V** rail from a
  Zener or shunt split, each backed by reservoir capacitors sized for the
  gate-charge transfer;
- per gate: 1 nF C0G Cgs and a 1 Ω + **PMEG6030EP** discharge branch (anode at
  the gate side as in the F6 deck: `Doff gd3 off`), keeping the existing 3.9 Ω Rg;
- a rail-window monitor that holds DIS active until every bias rail is in window;
- **delete PS2 and the bootstrap network** (D1/D2, C10/C11/C17/C18). V15_LS
  and HOT5 now come from the low-side secondary. HOT5 uses a **30 V-input low-Iq
  LDO (TPS709 class)** in place of the MC78L05, because its ground current is in
  the Kelvin budget.

**Sizing first** (`native-21/bias_sizing.py`, committed). Calculate the gate
power from the IPW65R018CFD7 datasheet Qg at 33–80 kHz, the transformer
driver's and transformers' datasheet efficiency, the PS1 (IRM-20-15) budget
with the D-20 controller allocation, the transformer isolation rating against
the **D5 reinforced basis** for 120 V mains (stop and report if no catalogue
transformer meets it), and the −2 V rail's source impedance and ripple at
80 kHz. **Then re-run F6** with that bias-source model in place of the ideal
−2 V source: `round17/d2/f6_legs.py --diode pmeg`, with a deck variant that
models the rail as its reservoir capacitance plus ESR and the Zener or shunt.
Run decision and startup cases on both legs at 27/100/150 °C. The adoption
holds only if they all still pass.

Keep native-20's values: R34 10.6 kΩ RT0603BRD0710K6L, R8/R16 330 Ω,
R9/R17 49.9 kΩ. Then:
- compile with atopile 0.2.69 (`uv tool run --offline --from atopile==0.2.69 ato build`
  and `tools/circuit_export.py`; see `native-19/verification/reproduction-commands.json`);
- copy the outputs to `zapote/power-stage-120v/frozen/` **and** a new
  `native-21/frozen/`, with no board file;
- extend `audit.rs` IDENTITY for every new part, and add structural tests: each
  of the four gates has the negative rail, the Cgs, and a discharge diode in the
  right orientation; the monitor output reaches DIS; each high-side bias is
  referenced to its own switch node; plus a mutation test for each;
- `rustc --edition=2021 --test zapote/power-stage-120v/audit.rs` must pass.

Also write `native-21/ECO.md`: every added or changed part and net, the
footprint for each, and placement notes. The negative-bias parts go next to
each driver, and the discharge loop is as small as the gate loop. Cross-check
it against `RELAYOUT-REQUIREMENTS.md` L1–L7.

**Do not** edit `native-20/` or any `.kicad_pcb`. **Do not** route.

---

## D-34: bench verdict tool (medium)

**Why.** The owner wants custom software to catch problems. The native-20
bench tests B0–B4 (`validation-plan/BENCH-NATIVE20-ADDENDUM.md`) each have a
numeric pass criterion. A tool that reads the raw captures and prints the
verdict removes judgment calls at the bench.

**Do.** Write `zapote/power-stage-120v/validation-plan/bench_verdict.py`:
- inputs: scope captures as CSV (time plus named channels; document the
  expected column names per test) and a small JSON describing the test (B0–B4,
  leg, bus voltage, probe deskew);
- per test, compute what the addendum criterion needs:
  - **B0**: mV offsets;
  - **B1**: PERMIT↓ → gate < 0.65 V → DIS > 2.3 V → OUT < 10 % delays;
  - **B2**: partner VGS peak in the window after the edge;
  - **B3**: D-8's quantities;
  - **B4**: trip current at BUS_FAULT, comparator-to-gate-off delay, and die
    VDS peak;
- output a verdict JSON with PASS/FAIL per criterion, the measured value, the
  limit, and its source document.
- tests: synthetic waveforms with known answers, one passing and one failing
  per criterion, plus an edge-detection test with noise and ringing.
  Generate at least one fixture from a real ngspice run of the D2 deck
  (`round17/d2/leg_matrix.cir` with `.print`/`wrdata`; vendor model fetched,
  not committed) so the tool is exercised on realistic edges.

---

## D-35: IEC 61000-4-15 flickermeter for burst mode, 120 V lamp (medium)

**Why.** The burst-period rule comes from IEC 61000-3-3's **analytical** screen,
using the 230 V reference impedance and lamp curve as a stand-in
(`validation-results/07-conducted-emi/flicker/README.md`). A digital
flickermeter with the **120 V lamp** model is the in-the-box upgrade.

**Do.** Write `zapote/power-stage-120v/validation-results/07-conducted-emi/flicker/flickermeter.py`:
- the IEC 61000-4-15 digital flickermeter (blocks 1–5): demodulation,
  weighting filters for the **120 V / 60 Hz** lamp, squaring and smoothing,
  and the statistical Pst evaluation;
- **validate** it against the standard's performance-test tables
  (rectangular and sinusoidal modulation giving Pinst = 1 / Pst = 1 for
  120 V / 60 Hz) to the standard's stated tolerance, as committed tests. If the
  table values cannot be obtained, say so and stop at a tool that is
  self-consistent but unvalidated;
- apply it to synthetic burst-mode voltage at 120 V. The current steps come
  from burst power (160/200/250/300 W, PF 0.95) through a reference impedance.
  Run both IEC's 0.4 + j0.25 Ω and a documented North American service-impedance
  case. Find the minimum burst period for Pst ≤ 1 and Plt ≤ 0.65, and compare
  with `burst_flicker.py`;
- report whether the 20 s default and the T_burst rule hold. If they don't,
  propose the corrected rule; do not change DECISIONS.md.

---

## Reporting

For each task, end the PR body with a short answer first:
- what changed;
- what was verified, with the exact commands;
- what is still open.

Do not merge your own PR.
