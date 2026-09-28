# Power-stage-120v validation master plan

Status: round-three validation executed 2026-09-27 against native-15; tasks
01–05 and 07 have model findings, partial or blocked results (see §5). This plan covers the desk
validations and simulations to run on the routed board **before** fabrication
release. Physical tests (hipot, leakage, measured EMI, measured temperature)
come later; each task lists the physical test that finally confirms it.

**Round 3: [ROUND-3.md](ROUND-3.md)** says, item by item, how to close
what rounds 1–2 left blocked, in what order, and which decisions need the
owner.

Round-three execution and reviewed handbacks are tracked in the
[execution record](../validation-results/round3-coordination/README.md).
Owner decisions on the round-3 findings (2026-09-28) and the review
dossiers are in [decision-review](../validation-results/round3-coordination/decision-review/README.md).
Raw round-3 evidence is a release asset; restore it with
[raw-evidence/restore.sh](../validation-results/round3-coordination/raw-evidence/restore.sh).

Every task has its own document. Read this master plan first, then only the
task document you're assigned. **For the simulation tasks (01, 02, 04, 05,
07), also follow [SIMULATION-RUNBOOK.md](SIMULATION-RUNBOOK.md)** and its
tested starter kit in [`sim-kit/`](sim-kit/). Run `sim-kit/smoke_test.py`
before anything else.

| # | Task | Doc | Finds | Depends on |
| --- | --- | --- | --- | --- |
| 01 | Layout parasitics and switching transient | [01-switching-parasitics.md](01-switching-parasitics.md) | Turn-off overshoot, gate ringing, false turn-on, dead-time margin | — |
| 02 | Protection timing | [02-protection-timing.md](02-protection-timing.md) | Whether OCP/OVP act before the MOSFETs are damaged; trip-threshold spread | 01 (loop inductance) |
| 03 | Loss and thermal budget | [03-loss-thermal-budget.md](03-loss-thermal-budget.md) | MOSFET/bridge/shunt losses; required heatsink and airflow (D2) | — (01 improves switching-loss inputs) |
| 04 | Board current density and temperature | [04-board-current-thermal.md](04-board-current-thermal.md) | Real current sharing and copper temperature rise, replacing the width screens | 03 (heat sources) |
| 05 | Resonant tank operating envelope | [05-resonant-tank-envelope.md](05-resonant-tank-envelope.md) | Tank current/voltage stress on C21–C23, T1, bleed resistors; soft-switching margin | — |
| 06 | Controller interface cross-check | [06-controller-interface.md](06-controller-interface.md) | J4 pinout, polarity, levels, power-loss states, CT open-circuit hazard | — |
| 07 | Conducted EMI pre-check | [07-conducted-emi.md](07-conducted-emi.md) | Whether the input filter is sized for the conducted limits | 01 (switch-node edges) |
| 08 | Manufacturing package review | [08-manufacturing-package.md](08-manufacturing-package.md) | Silkscreen fix, Gerber/drill/BOM/position files, independent review | Run after any task that changes the board |
| 09 | Mechanical fit | [09-mechanical-fit.md](09-mechanical-fit.md) | Heatsink, terminal, enclosure and wiring collisions | 03 (heatsink choice) |

**Recommended order:** start 01, 05 and 06 in parallel. Then run 02 (it needs
01's inductance), 03 and 07. After those come 04 (needs 03) and 09 (needs 03's
heatsink). Run 08 last, and again after any board change.

Run tasks **one at a time per worktree** (see the ground rules below). Parallel
tasks need separate worktrees and must not both build Rust or the native bridge.

---

## 1. What the board is

- **Unit:** `zapote/power-stage-120v` in the Temper repo. All paths in these
  docs are relative to that directory unless they start with `zapote/` or
  `docs/`.
- **Function:** a 120/127 V induction-cooktop power stage. It has the mains
  entry, EMI filter (L1, C1–C4), bridge rectifier BR1, a film DC bus with no
  PFC (C5/C6, plus local C38–C41), and a full bridge of four IPW65R018CFD7
  MOSFETs (leg A: Q2 high/Q3 low; leg B: Q5 high/Q6 low). The bridge drives a
  series-resonant tank: an external coil of about 70 µH on terminals J2/J5,
  resonant capacitors C21–C23 (0.54 µF total), and the current transformer T1.
  The board also carries two UCC21550 gate drivers (U1 leg A, U2 leg B), the
  shoot-through OCP (1 mΩ shunt R5, comparator U6), bus OVP (U7), the
  isolated bus-voltage sense (U4 AMC1311), the fault isolator (U8 NAND →
  U9 ISO7710 → J4.10) and two aux supplies (PS1 IRM-20-15 for SELV, PS2
  IRM-05-15 for the HOT side).
- **Operating envelope** (`docs/hardware/power-section-120v/POWER-SECTION.md` §2):
  1,710 W at 120 V / 15 A input; tank current ~18.7 A rms (line-average) and
  ~37 A peak; 33–39 kHz at full power, up to 60 kHz at light load; nominal
  dead time ≈ 348 ns; OCP trip ≈ 61 A; OVP ≈ 280 V; bus crest ≈ 170 V at
  120 V rms and ≈ 198 V at 140 V rms line crest.
- **Board file:** `native-15/section.kicad_pcb`. This supersedes native-09,
  which the rest of this section still describes; see
  `native-13/verification/README.md` and `native-15/verification/README.md`
  for the deltas. Native-13 adds the tank-CT detector (U10–U13) and has
  BAS116H clamps and a 100 Ω / 1 kΩ permit/DIS network. Native-15 corrects
  C1/C2 to KEMET R463N410000N1M (22.5 mm pitch); its copper is identical to
  native-13's, so copper results from native-13 still apply. It's 240 × 160 mm with 4 layers:
  - F.Cu: parts and power pours
  - In1: HV_RET return plane
  - In2: BUS_P plane
  - B.Cu: SW_B band and pours

  It's built to JLCPCB stackup JLC041622-7628 (`stackup.json`). The active native-15
  presentation revision has SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`;
  its copper is identical to the electrically verified native-15 revision
  `bec1df670d5965bff852b5c0e674dbfa2a6396767c78f213f88b58eddad9ab5f`
  (`native-15/verification/README.md`).
  **Record the SHA-256 of the board you actually analyse in every result.**
- **Source of truth for parts:** `frozen/default.csv` and
  `frozen/resolved-components.json`. Never take part identity from
  `default.net`; its part fields are aliased. See the `README.md` warning.
- **Netlist and connectivity:** `frozen/default.net`, plus the native board.
  Useful net names:
  - Power: `bus_p`, `hv_ret`, `leg_ret`, `sw_a`, `sw_b`, `res_a`, `coil_feed`
  - Gate drive: `leg_a-gate_h`, `leg_a-gate_l`, `leg_b-gate_h`, `leg_b-gate_l`
  - Protection and supplies: `ocp_kelvin_n`, `ocp_node`, `ocp_thresh`, `ref25`, `hot5`, `v15_ls`
  - SELV side: `v3v3`, `selv_gnd`, `pwm_ha/la/hb/lb`, `permit`, `bus_fault`
- **Key design documents:**
  - Power section design basis: `docs/hardware/power-section-120v/` (`POWER-SECTION.md`, `LOSS-REFACTOR.md`, `COIL-MC.md`, and the calculation programs `power_section.rs` and `coil_mc.rs`)
  - Circuit analyses in this unit: `DC-LINK-CLAMP.md`, `BUS-CAP-SCREEN.md`, `FAULT-INTERFACE.md`, `REFERENCE-BIAS.md`, `ORACLE-REVIEW.md`
  - Layout and fabrication: `ROUTING.md`, `DECISIONS.md`, `D5-BASIS.md`, `FAB-JLCPCB.md`
  - Existing lumped bus model: `tools/bus_voltage_sim.py`, which is ideal, with no stray inductance

## 2. Ground rules (mandatory)

1. **Work in your assigned git worktree only.** Never use bare `git stash`;
   other sessions share the stash stack. Use a WIP commit instead.
2. **One writer per worktree.** Don't run two tasks in the same worktree.
3. **Don't run parallel heavy builds.** Rust and native-bridge builds are
   multi-gigabyte. Use `CARGO_TARGET_DIR=/tmp/ps-native-cargo` (already built)
   and don't start several agents that each compile the workspace.
4. **Don't change copper, placement or source** (`elec/`, `frozen/`,
   `poses.json`, `routes/`, `tools/routes*.py`) as part of a validation task.
   If a result says the board must change, **stop and report**; the owner
   decides. Task 08 is the only exception, and only for its silkscreen text
   step.
5. **Every number you report must be reproducible from committed files.**
   Commit the script, its inputs (or input hashes) and its raw output next to
   the result. Say "bound" only when the calculation really bounds the
   quantity. Check parts at worst-case tolerance and temperature corners, not
   nominal only.
6. **Label every result with its evidence class** from `zapote/VALIDATION.md`:
   exact structural, bounded calculation, simulation/model-based, heuristic,
   or physical-test requirement. A passing simulation is not a measurement.
7. **Verdicts that become permanent rules go in Rust.** The zapote framework
   (`zapote/VALIDATION.md`) says Rust computes engineering verdicts and Python
   only transports data. A one-off simulation may be Python or ngspice. If you
   propose a new pass/fail rule for the permanent suite, write it up as a Rust
   port recommendation instead of adding a Python gate.
8. **Get datasheet values from the datasheet.** Download it, record the
   URL, revision and page/table for every value you use, and keep a copy or
   hash under the task's `sources/` folder. Don't use remembered values.
9. **Stop and report instead of guessing** when:
   - a required input or model is missing
   - an install fails twice
   - a result contradicts a committed document
   - a result fails an acceptance criterion

   A clear "blocked" report is a good outcome.
10. **Commits:** do not push to `main`. Commit to the working branch given to
    you. End each commit message with the co-author line the operator gives you.

## 3. Environment

| Tool | Status on the reference machine | Use |
| --- | --- | --- |
| KiCad 10.0.4 (`kicad-cli`, KiCad Python at `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`) | installed | Board queries, DRC, exports |
| ngspice (`/opt/homebrew/bin/ngspice`) | installed | Circuit transients (01, 02, 05, 07) |
| gmsh | installed | Meshing (04, optional) |
| Python with numpy/scipy/shapely (`/Users/bennet/Miniforge3/bin/python3`) | installed | Scripts, sheet solves |
| Rust toolchain; built checkers under `/tmp/ps-native-cargo/debug/` (`zapote-board`, `zapote-power-native-parity`, `zapote-power-copper-identity`) | installed | Board gates |
| FastHenry2, openEMS, Elmer FEM | **not installed** | Optional; each task gives a fallback |
| gerbv | not installed (`brew install gerbv`) | Gerber review (08) |
| FreeCAD | not checked | Mechanical (09) |

The copper census tool `tools/copper_dump.py` (run under KiCad Python) writes
every pad, track, via and filled-zone polygon with net and layer. Most tasks
start from it:

```sh
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
$KP tools/copper_dump.py native-15/section.kicad_pcb /tmp/copper.json
```

The DRC must run with the board's sibling files present (`section.kicad_dru`,
`section.kicad_pro`, `fp-lib-table`, `candidate-libs/`):

```sh
kicad-cli pcb drc --all-track-errors --schematic-parity --severity-all \
  --format json --output /tmp/drc.json native-15/section.kicad_pcb
```

Documented native-15 baseline (the same as native-13's): 0 copper findings, 28 `lib_footprint_mismatch`, 3
`silk_overlap`, and 1 unconnected item (the intended R5 Kelvin split).

## 4. Where results go

Each task writes to `validation-results/NN-<short-name>/` (create it):

```
validation-results/01-switching-parasitics/
  README.md         <- the report (template below)
  sources/          <- datasheets/models or their URLs + SHA-256
  scripts/          <- every script used, runnable as committed
  inputs/           <- extracted inputs (or hashes of large ones)
  outputs/          <- raw simulator output, CSV, plots
```

### Report template (copy into each README.md)

```markdown
# NN <task name> — result

- Board: native-15/section.kicad_pcb, SHA-256 <hash>
- Date, tool versions, operator/model
- Evidence class: <class>
- Verdict: PASS / FAIL / BLOCKED / PASS WITH CONDITIONS

## Summary (3–6 lines, numbers with units and margins)
## Method and assumptions (list every assumption; mark each estimated/datasheet/measured)
## Results (tables; each number traceable to a file in outputs/)
## Sensitivity (what changes the verdict, and by how much)
## Open items and the physical test that confirms this result
## Reproduce (exact commands)
```

## 5. Status

Update this table when a task finishes (link the result README).

| # | Status | Result | Verdict |
| --- | --- | --- | --- |
| 01 | round 3 model criteria failed; physical qualification blocked | [switching round three](../validation-results/01-switching-parasitics/round3/README.md) | A1 edge independence failed; heuristic board-inductance B1 stopped at first VDS/off-gate failure; parasitic bounds and remaining grid unresolved |
| 02 | round 3 partial; static criterion failed | [protection round three](../validation-results/02-protection-timing/round3/README.md) | All 108 ideal CT cases complete; shunt minimum 38.44 A fails 44 A criterion; ramp timing, actual gate-off and HOT5 slow-fall fail-safe guarantee unresolved |
| 03 | round 3 conditional budget complete; cooling choice blocked | [loss and thermal budget](../validation-results/03-loss-thermal-budget/round3/README.md) | Two pad options, heatsink requirement and 42-part heat map delivered; switching/auxiliary losses, installed contact and airflow remain unqualified |
| 04 | round 3 electrical and conditional thermal studies complete; operating temperature blocked | [copper](../validation-results/04-board-current-thermal/round3/a4-copper/README.md), [thermal](../validation-results/04-board-current-thermal/round3/b3-thermal/README.md) | BUS_P resistance spread 1.985%; thermal analytic checks pass but local peaks vary with mesh; actual operating heat/current covariance incomplete |
| 05 | round 3 numerical work complete; acceptance blocked | [tank round three](../validation-results/05-resonant-tank-envelope/round3/README.md) | 135 ideal grid cases, R5 RMS and finite-bus trip complete; hot capacitor ratings and validated ZVS map absent; protection limits sustained operating cases |
| 06 | partial (CT check done; fixed in native-11) | [CT burden](../validation-results/06-controller-interface/README.md) | CT: FAIL on native-09 → fixed in native-11 (source change; renewed D4 review needed) |
| 07 | round 3 model and fixtures complete; margins blocked | [EMI round three](../validation-results/07-conducted-emi/round3/README.md) | Floating-bus/PE return and opposed legs checked; component fits and assumed 35/60 kHz peak spectra saved; qualified edges, DM bus-current source and physical parasitics missing |
| 08 | partial (silkscreen step done) | [native-11 presentation](../native-11/verification/presentation/README.md) | Designators at 1.0/0.15 mm, copper unchanged; Gerber/BOM/sourcing steps not started |
| 09 | not started | — | — |

## 6. What this plan does not do

It doesn't release fabrication. DECISIONS.md still controls that: the open
items are the insulation evidence (D5), measured hardware, the finished-copper
answer from JLCPCB, and D4 conditions 2–3. It doesn't replace bring-up
measurements or certification testing. When every task passes, the result is
"the desk evidence supports building a prototype"; it is not "the board is
safe".
