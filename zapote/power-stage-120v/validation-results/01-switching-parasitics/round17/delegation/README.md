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
