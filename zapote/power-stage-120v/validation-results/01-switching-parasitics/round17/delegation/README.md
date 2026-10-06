# Round 17 delegation briefs (for Codex / Astra agents)

Four self-contained tasks that decide how much of round 17's D2 switching
result is real. Each brief has its own context; read this file first, then
only your brief.

| Brief | Question | Size |
| --- | --- | --- |
| [D-1 dead time](D1-dead-time.md) | What dead time does the UCC21550 really produce on this board, worst case? | small |
| [D-2 driver model](D2-driver-model.md) | Is the D2 deck's driver approximation (5 Ω pull-up, 0.55 Ω pull-down, 5 ns ramp) faithful, and what are the gate resistors' inductances? | small |
| [D-3 diode recovery](D3-diode-recovery.md) | Does the Infineon IPW65R018CFD7 L1 model's body-diode recovery match the datasheet? | medium |
| [D-4 review](D4-review.md) | Adversarial review of round 17's matrix → SPICE mapping, extrapolation and margin correction | medium |
| [D-5 gate dead time](D5-gate-dead-time.md) | Worst-case dead time at the gates: firmware MCPWM + signal path + driver DT combined | small |
| [D-6 off-gate remedies](D6-off-gate-mitigation.md) | Which gate-drive remedy (Rg_off, Cgs, negative bias, Miller clamp) fixes the off-gate failures, at what cost; is the 3.0 V criterion right | medium |
| [D-7 capacitor ESL](D7-capacitor-esl.md) | ESL of C38–C41 and bulk C5/C6 from TDK models/curves | small |
| [D-8 double-pulse plan](D8-double-pulse-plan.md) | Bench procedure to measure diode recovery (S4) and gate dead time | small |
| [D-9 review](D9-review-followups.md) | Adversarial review of the D-4 follow-up commits (f5a1c8083 onward) | medium |
| [D-10 J4 interface](D10-controller-interface.md) | Power-stage task 06 in full: all 16 J4 pins against every counterpart board (controller read-only) | medium |
| [D-11 bus-sense range](D11-bus-sense-range.md) | AMC1311B leaves its linear range at ~240 V (< 280 V OVP); divider values, receiver and overrange behaviour | small |
| [D-12 remedy proposals](D12-remedy-proposals.md) | Build-level comparison of the two hot-screen remedies: negative bias (F6) vs longer dead time (F7): circuit, parts, BOM, layout/rerun impact | medium |
| [D-13 hot switching](D13-hot-switching.md) | D2 transients at Tj 27/100/150 °C (vendor model uses TEMP), baseline and both remedies, judged against the hot threshold | medium |
| [D-14 solver robustness](D14-solver-robustness.md) | Why some D2 runs abort ("timestep too small"); a physics-neutral fix, qualified; timestep convergence | medium |
| [D-15 losses vs dead time](D15-losses-dead-time.md) | Round-4 C1/C2 (ZVS map, switching losses) rerun on the FEM matrix, 307–498 ns: the cost of F7 | medium |
| [D-16 native-18](D16-native18-dt-resistors.md) | **Design change** (owner decision 2026-10-03): R9/R17 → 49.9 kΩ ±0.1 %, value-only native-18, verified copper-identical | medium |
| [D-17 protection gate-off](D17-protection-gate-off.md) | (superseded by D-31) Task 02 on the FEM matrix: fault current at actual gate-off, device survival, input to the held R34/R35 retune (decision B) | medium |
| [D-18 loss/thermal](D18-loss-thermal-update.md) | Task 03 on round-17 results at 443 ns: loss table, heatsink Rth and airflow direction for the enclosure, R5 check | medium |
| [D-19 conducted EMI](D19-conducted-emi-edges.md) | Task 07 with the real switch-node edges: spectrum and margin, filter change or not | medium |
| [D-20 controller requirements](D20-controller-requirements.md) | One testable requirements document for the controller (J4, PWM/dead-time ownership, protection, bus sense) from D-5/D-10/D-11 and decisions | medium |
| [D-21 firmware dead time](D21-firmware-dead-time.md) | **Firmware change (draft PR):** fix MCPWM dead-time configuration, error propagation and readback found by D-5, with host tests | medium |
| [D-22 EMI filter](D22-emi-filter.md) | Converge D-19's periodic EMI source over the envelope and size an additional damped DM stage for ≥ 6 dB margin, with parts, volume and placement | medium |
| [D-23 driver vendor model](D23-driver-vendor-model.md) | TI UCC21550 model in place of the 5 Ω/0.55 Ω approximation: real gate timing, DT pin and longer-of rule, decision cases rerun | medium |
| [D-24 S4 recovery sweep](D24-s4-recovery-sweep.md) | Sweep body-diode recovery over its evidenced plausible range: does S4 need a remedy regardless of the bench? | medium |
| [D-25 firmware safe state](D25-firmware-safe-state.md) | Settle D-21's blocker from the ESP32-S3 TRM, ESP-IDF source and (if possible) QEMU: does the forced safe state drive both gates low? | small |
| [D-26 parametric driver model](D26-driver-parametric-model.md) | Datasheet-parametric UCC21550 model (min/typ/max timing, DT pin, longer-of rule): bound gate dead time and rerun decision cases on native-19 | medium |
| [D-27 prototype reconciliation](D27-prototype-reconciliation.md) | Check every prototype-closure choice against DECISIONS.md and round-17 findings (agree / contradict / one-sided / supersedes); nominal enclosure fit of the D-18 and D-22 allocations | medium |
| [D-28 phase-shift validation](D28-phase-shift-validation.md) | Validate fixed-frequency phase shift (gated low-power mode): per-leg commutation current, ZVS, off-gate, losses vs phase; CT inhibit | medium |
| [D-29 prototype firmware conformance](D29-prototype-firmware-conformance.md) | **Firmware change (draft PR):** prototype ESP32 PWM safe state on every failure path, 180° phase cap, fault-injection tests | small |
| [D-30 connector power direction](D30-connector-power-direction.md) | **Board-source fix (draft PR):** central J9 supply pins typed power_out; fix, audit the class on all nine round-5 boards, add a power-direction validator | small |
| [D-31 protection closure](D31-protection-closure.md) | **Supersedes D-17.** Gate-off chain and device survival on native-19, a source-to-gate-off/extinction timing ledger, FC1 DC clearing, precharge repeated pulses, contactor DC duty | large |

| [D-32 … D-35](CODEX-HANDOFF-2026-10-06.md) | Firmware safe state + 180° + burst scheduler; native-21 F6 bias source/netlist; bench verdict tool; 120 V flickermeter | medium |

D-1..D-27 are complete (`out-D*`; D-23 and D-26 indeterminate, D-24 answer c); D-21 is a draft PR awaiting the D-25 cleanup fix. D-5..D-10 are independent of
each other except D-8 (cite D-5/D-6 if done first) and D-10's dead-time check (cite D-5).

**Paths:** `round17/...` means
`zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/...`;
`validation-plan/...`, `native-17/...` and `frozen/...` are under
`zapote/power-stage-120v/`; `docs/...` is at the repository root.

## Ground rules (all briefs)

- **Branch:** start from `origin/codex/power-stage-120v-build` at or after
  the commit that added this file. Work in **your own git worktree**; one
  writer per worktree. Do not touch another agent's worktree.
- **Never** run bare `git stash` / `git stash pop` (the stash stack is shared
  across worktrees). Use a WIP commit instead.
- **Vendor MOSFET model** (licensed, git-ignored): fetch and hash-check it
  with `zsh zapote/power-stage-120v/validation-plan/sim-kit/models/fetch_models.sh`
  before any ngspice run (D-2, D-3), then run
  `python3 zapote/power-stage-120v/validation-plan/sim-kit/smoke_test.py`.
- **Do not build the Rust workspace or the native bridge.** None of these
  tasks needs it. Python (Miniforge 3.12) and ngspice 45.2
  (`/opt/homebrew/bin/ngspice` on the Mac) are enough.
- **Do not edit** `pcb/temper.kicad_pcb`, `elec/`, the board files under
  `zapote/power-stage-120v/native-*`, or anything under `round17/` except
  your own output folder `round17/delegation/out-<brief>/`.
- **Numeric claims need committed, rerunnable evidence**: every number in
  your report must come from a file you commit (script + its output) or a
  cited datasheet page (part number, document revision, page/figure/table).
  Say "bound" only for a real bound; mark estimates as estimates.
- **Report** in `round17/delegation/out-<brief>/README.md`: a one-line
  answer first, then method, numbers with sources, limits. Commit messages
  end with `Co-Authored-By:` for your model; push to your own branch and
  open a PR against `codex/power-stage-120v-build`.
- If you find a contradiction between the board, the netlist and a
  datasheet, **stop and report it**; do not change design files.

## Board facts you will need

- Power stage: 120 V full bridge, four Infineon **IPW65R018CFD7** (TO-247-3).
  Leg A: Q2 high side, Q3 low side, driver **U1 = TI UCC21550BDWKR**. Leg B:
  Q5/Q6, driver U2.
- Gate resistors R10 (leg A high) / R12 (leg A low) = **Yageo
  RC1206FR-073R9L**, 3.9 Ω 1206. 10 kΩ gate–source hold-off.
- Bus 170 / 198 V nominal (120 / 140 V rms crest), OVP 280 V; tank current
  37 A peak; OCP trip ≈ 61 A; nominal dead time ≈ 348 ns (from the DT pin
  resistor).
- Board: `zapote/power-stage-120v/native-17/section.kicad_pcb`; frozen BOM
  and netlist: `zapote/power-stage-120v/frozen/default.csv`,
  `frozen/default.net`.
- D2 deck and results: `round17/d2/` (`leg_matrix.cir`, `run_d2.py`,
  `grid.py`, `README.md`); board matrices `legA-h1-e0p35.matrix.txt` (1 mm
  closures), `legA-h2-e0p35.matrix.txt` (2 mm), `legA-h0-lin12.matrix.txt`
  (straight-line extrapolation to h = 0, provisional until 3 mm), and its
  SPICE form `legA-board-lin12.sp`. Vendor model library:
  `zapote/power-stage-120v/validation-plan/sim-kit/models/vendor/IFX_CFD7_650V.lib`
  (licensed; do not commit copies). Kit runner:
  `validation-plan/sim-kit/common/run_ngspice.py`.
