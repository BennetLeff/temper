<!-- provenance: commit=d9f12d18e7220566de465ac303d8b30b6001bf0a dirty=false -->
<!-- worktree agent/full-replace-attempt off origin/fix/board-schematic-resync + PR #1157 (aa90a4376) + PR #1158 (01098a7c9) + PR #1144 (f28db82b4) -->

# Full re-place, attempted for the first time: measured, and it loses to repair

**Recommendation: continue repairing the current placement. Do not re-place
from scratch.**

## The three numbers that decide it

1. **A fresh full route of the best re-placed candidate reaches 50/139 nets
   fully pad-connected -- fewer than the current placement's fresh-routed
   53/139**, measured the identical way for both
   (`pad_connectivity_audit.audit_pcb_file`, `fully_connected` field, live
   re-run, not inferred). This is the exact number the task named as
   decisive, and the re-place does not beat it. Re-placing is not the
   answer, and repair wins by default on this axis alone -- everything
   below is why, and what it would cost anyway.

2. **A full re-place with the isolation barrier enforced exactly as
   specified is not slow, and not unattempted -- it is PROVEN INFEASIBLE in
   26 seconds.** CP-SAT returns a real `SufficientAssumptionsForInfeasibility`
   core (`isolator_straddle_C6`), not a timeout. Root cause: 3 of the
   board's 8 mains<->SELV isolator parts (`C6`, `K1`, `U6`) cannot
   geometrically span the 8.5mm reinforced-creepage corridor at ANY
   position or rotation -- a pre-existing, already-documented BOM/land-
   pattern defect (`docs/evidence/2026-07-28-isolator-sourcing-brief.md`),
   not a placement-search failure. This blocks repair equally, not just
   re-placement -- it is a constraint-set/BOM fact, independent of strategy.

3. **Set that pre-existing defect aside (relax only the 3 already-broken
   isolators) and the solver DOES find a full-board placement -- fast: 36s,
   `optimal`, all 168 components including T2/C37/R65.** But writing that
   placement to a board and checking it with live `kicad-cli` DRC shows
   **14 `courtyards_overlap` -- more than the current board's 8**, including
   two NEW severe electrolytic-capacitor body collisions (`C4`x`C5`, 9.35mm
   overlap; `C4`x`C3`, 9.47mm overlap) that are BOTH worse than the current
   board's worst collision (`C2`x`C3`, 7.73mm). A second independent run
   (isolation barrier dropped entirely) reproduces the same defect class at
   the same magnitude. Routing does not fix this (components do not move
   during routing) and adds more DRC damage on top: clearance saturates the
   DRC report's 499-item cap post-route, vs. the current board's true,
   uncapped 316. **The CP-SAT courtyard constraint does not reliably
   prevent true physical collisions between the board's large 35mm snap-in
   electrolytic capacitors -- the exact defect class that produced the
   CURRENT board's unassemblable state in the first place** (commit
   `de59c0458`, PR #602, one automated CP-SAT re-solve). A full re-place
   with this tool does not avoid that failure mode. It reproduces it,
   twice, at a worse magnitude than what already shipped.

## Why this document exists

The re-place vs. repair decision has been deferred twice for lack of
evidence, because nobody had ever attempted a full re-place. This document
is that attempt -- run today, in scratch, against `origin/fix/board-
schematic-resync` plus every repair PR stacked on it (#1157 clearance
remediation, #1158 collision characterization, #1144 repair-unplaced
tooling). `pcb/temper.kicad_pcb` was never written to; every candidate
lives under this document's own scratch paths, sha256-verified identical
before and after every run below.

## 1. Setup

Worktree: `agent/full-replace-attempt`, branched from
`origin/fix/board-schematic-resync` (a3fbaff37), with `origin/fix/
clearance-1085-remediation-exec` (#1157), `origin/agent/collision-
remediation-plan` (#1158), and `origin/fix/t2-repair-entrypoint` (#1144)
merged in -- clean, no conflict markers (`git grep -l "^<<<<<<< "` empty).
`make venv-isolate` + `make extensions`: 10/10 fresh AND independently
import-verified (not just the freshness gate, which the task brief warns
certifies freshness, not loadability). `make netlist` run in this worktree.

Board: `pcb/temper.kicad_pcb`, sha256
`a70e34bbefe4801212104376adccd59872c06142d8a4d0de0f04eea5a445f04f` --
identical to `power_pcb_dataset/drc_ceiling.json`'s own recorded
`provenance.inputs[].sha256`, confirming this is exactly the board the
ceiling file's own numbers (clearance=316, courtyards_overlap=8) describe.
168 components (not 169 -- re-verified live, `parse_kicad_pcb` count),
139 nets (`pad_connectivity_audit`, re-verified live: 27 fully-connected,
41 fake-completion -- 48 pre-#1157, minus the 7 nets #1157 stripped copper
from, exactly consistent).

## 2. The production `optimize --loop` path is not usable against this board at all

Tried first, as the task specifies ("repo's CP-SAT placement machinery"):

```
uv run --no-sync python -m temper_placer.cli optimize pcb/temper.kicad_pcb \
  -c packages/temper-placer/configs/constraints/temper_induction_cooker.yaml \
  -o <scratch>/full_replace_candidate.kicad_pcb --seed 0
```

Fails closed immediately:

```
Error: Place→route loop failed: Constraint(s) reference names absent from
the netlist/zones/loops -- these would silently drop (fail-closed violation):
  adj_C_BUS1_Q1: C_BUS1
  enc_HV_ZONE: C_BUS1, C_BUS2, J_AC_IN, J_COIL, U_GATE, C_BOOT
  enc_MCU_ZONE: U_MCU, MAX31865, J_DEBUG
  ... (13 constraint names total)
```

This is the exact config/board drift `docs/evidence/2026-08-11-pumpkin-
real-budget-spike.md` (main, PR #1024) already documented on 2026-08-11:
the production PCL config (`temper_induction_cooker.yaml`) still names
components absent from the real, resynced board. Unfixed since. This is
itself a finding -- "the repo's CP-SAT placement machinery," used the way
its own CLI documents, cannot run a full re-place against this board at
all, PCL config aside.

**Worked around, not fixed** (the config is a scratch concern, not the
tracked board -- and `-D warnings`-clean is not this task's job): called
`temper_placer.placer.cp_sat.encoder.solve_placement` directly -- the SAME
function `optimize --loop` and `repair-unplaced` both call underneath --
with every one of the 168 real components free (`fixed_positions={}`,
including `T2`/`C37`/`R65`, confirmed `fixed=False` on the real board,
parked off-board at y=252-280mm against the 234mm-tall outline), the full
unfiltered courtyard NoOverlap constraint (`auto_pairwise_touch_refs=None`
-- catches the 6 real body collisions AND every other pair, not just
them), the full domain-clearance + unclassified-HV-keepaway constraint
family (11,466 + 0 constraints, built from `elec/domain_manifest.yaml` +
`elec/build/default.net`, NOT the drifted PCL config), and the isolation
barrier. `fixed_copper` was omitted -- there is no committed copper for a
from-scratch placement to respect; that constraint family is about not
routing a NEW pad onto EXISTING routed copper, moot before the first
route.

## 3. Attempt 1: isolation barrier exactly as specified -- PROVEN infeasible in 26s

```
status=infeasible   solve_wall_s=26.18   (not a timeout -- TIMEOUT_MS=1,800,000)
unsat_core: [{"name": "isolator_straddle_C6", "because": "", "literal_index": 1830}]
```

Not a search failure -- CP-SAT's own `SufficientAssumptionsForInfeasibility`
proof. The isolation-barrier module (`isolation_barrier.py`) computes, per
isolator, a **position-independent** geometric fact: can this part's own
HV pad cluster and SELV pad cluster achieve an 8.5mm edge-to-edge
separation (`DEFAULT_CORRIDOR_WIDTH_MM` = SSOT reinforced-creepage figure +
0.5mm headroom) on SOME axis, at SOME rotation? For 3 of the board's 8
derived isolators (`C6`, `K1`, `K2`, `K3`, `PS1`, `T1`, `T2`, `U6`), the
answer is no, measured directly from this solve's own
`IsolationBarrierReport`:

| isolator | achievable gap (mm) | clears 8.5mm? |
|---|---:|---|
| C6 | 8.000 | **NO** |
| K1 | 8.000 | **NO** |
| U6 | 8.100 | **NO** |
| K2 | 12.760 | yes |
| K3 | 12.760 | yes |
| PS1 | 35.500 | yes |
| T1 | 9.100 | yes |
| T2 | 9.100 | yes |

`add_isolation_barrier_to_model` adds the straddle constraint for every
isolator unconditionally -- it does not check `IsolatorFeasibility.feasible`
before encoding, so any ONE of these 3 alone makes the whole barrier
constraint UNSAT; CP-SAT's minimal core just happened to name `C6`
first. This is not new: `docs/evidence/2026-07-28-isolator-sourcing-
brief.md` already investigated exactly this -- back then as `{C6, K1, U7}`
(the board's isolator set has since renumbered `U7`->`U6` under the
resync; `U7`'s recorded 8.100mm is identical to `U6`'s here) -- concluding
"3 (K1 at 8.000, U7 at 8.100, C6 at stock pad diameters) would sit under
the CP-SAT module's 8.5mm working corridor" even after every proposed
part-swap fix. **This is a BOM/sourcing defect, not a placement defect --
it blocks repair exactly as much as it blocks a re-place**, since
`repair-unplaced`'s own isolation-barrier pre-flight (frozen-board check)
independently hits the same wall (see §5).

## 4. Attempt 2 and 3: set the 3 known-broken isolators aside -- solves, fast, but is not a board

Two variants, both bypassing only the already-known-broken part of the
barrier:

- **`relaxed_barrier`**: barrier enforced for the 5 isolators that clear
  8.5mm (`K2, K3, PS1, T1, T2`); `C6`/`K1`/`U6` relaxed via `isolation_
  barrier.py`'s own `relax_isolator_straddle` param (an existing,
  documented escape hatch, not something built for this document).
- **`no_barrier`**: isolation barrier dropped entirely, as a second,
  independent data point.

```
relaxed_barrier: status=optimal   solve_wall_s=36.39   n_positions=168
no_barrier:      status=optimal   solve_wall_s=43.40   n_positions=168
```

Both genuinely solve, fast -- confirming issue #871 (router OOM) is
irrelevant here (it was never a placement blocker) and that the earlier
"production engine times out" caution (PR #1151) was correctly
reclassified as *not attempted*, not *infeasible*: attempted now, and it
is NOT infeasible once the known-broken isolator geometry is set aside.
(`objective_value=0.0` on both -- no `minimize_displacement_to` objective
was posted, consistent with `docs/evidence/2026-08-11-pumpkin-real-budget-
spike.md`'s finding that objective-posting frequency in this codebase is
0% today; "optimal" here means *feasible*, not *best*.)

**But a CP-SAT "optimal" is not a board -- measuring the written candidate
with real `kicad-cli` DRC finds it is WORSE than what is already shipped:**

| | committed board (today) | `relaxed_barrier` candidate | `no_barrier` candidate |
|---|---:|---:|---:|
| `courtyards_overlap` (kicad-cli) | 8 | **14** | **9** |
| worst real body overlap (mm) | 7.73 (`C2`x`C3`) | **9.47** (`C4`x`C3`) | **9.47** (`C4`x`C3`) |

Verified independently for both candidates (not inferred from the
courtyard count -- the committed board's own 8 tracked courtyard hits
include 2 that are courtyard-only/benign, so courtyard count alone is not
proof of body collision; re-derived true body overlap the same way
`docs/evidence/2026-08-13-courtyard-collision-characterization-and-
remediation-plan.md` did, from real footprint centers and the shared
`CP_Radial_D35.0mm_P10.00mm_SnapIn` 17.5mm body radius):

```
relaxed_barrier candidate:
  C4 (15.56, 40.46) vs C5 (33.56, 64.34): center dist 29.90mm, sum-radii 35.00mm -> overlap 5.10mm
  C4 (15.56, 40.46) vs C3 (9.94, 15.56):  center dist 25.53mm, sum-radii 35.00mm -> overlap 9.47mm

no_barrier candidate:
  C4 (63.38, 40.46) vs C5 (69.54, 65.36): center dist 25.65mm, sum-radii 35.00mm -> overlap 9.35mm
  C4 (63.38, 40.46) vs C3 (57.76, 15.56): center dist 25.53mm, sum-radii 35.00mm -> overlap 9.47mm
```

**Both independent re-place attempts create a NEW `C4`x`C3` collision at
9.47mm overlap -- worse than the current board's worst collision.** This
is not a coincidence of one bad seed: two different constraint
configurations, same defect, same magnitude on `C4`x`C3` to the
millimetre. The CP-SAT courtyard model's own internal `bounds` for this
footprint (`30.13mm x 18.875mm`, confirmed by direct inspection) is not
the true 35mm-diameter circular body -- it is a courtyard-box
approximation, and the solver satisfies ITS OWN box constraint while the
true circular bodies still interpenetrate. **This is exactly the defect
class that produced the current board's unassemblable state**: commit
`de59c0458` (PR #602) moved all 12 collision-involved components in one
automated CP-SAT re-solve and nothing caught the result being physically
impossible. Re-placing from scratch with the same tool does not avoid that
failure mode -- it reproduces it, in both variants tried, at a worse
magnitude on the same pair of parts.

## 5. `repair-unplaced` T2/C37/R65 -- re-confirmed fresh, today

```
$ temper-placer repair-unplaced pcb/temper.kicad_pcb --refs T2,C37,R65 \
    -o <scratch>/t2_repair_candidate.kicad_pcb --no-run-drc
  165 frozen ref(s) (unchanged)
  Isolation-barrier pre-flight: SKIPPED -- barrier already UNSAT against the
    CURRENT board with every component frozen (pre-existing, independent of
    T2/C37/R65)
  Phase 1: status=infeasible (8087ms)
  UNSAT core: edge_margin_T2
```

Confirms the task brief's claim live: real UNSAT, real core, board hash
unchanged (`a70e34...5f04f` before and after). Note also confirms §3's
barrier finding independently -- even with EVERY component frozen at
today's positions, the barrier pre-flight is already UNSAT (the
checkerboard-interleaving reason `isolation_barrier.py`'s own docstring
describes, layered on top of the 3-isolator geometric defect from §3).

## 6. Routing: the decisive comparison

The task named one number as decisive: does a re-placed board route better
than the current placement's fresh-routed **53/139**? Routed the
`relaxed_barrier` candidate (the more complete of the two solving variants
-- barrier enforced for 5/8 isolators, only the 3 pre-existing BOM-blocked
ones relaxed) the identical way the 53/139 baseline was produced:

```
uv run --no-sync python3 scripts/route_board.py \
  --pcb <scratch>/relaxed_barrier/full_replace_candidate.kicad_pcb \
  --output <scratch>/relaxed_barrier/routed.kicad_pcb \
  --net-batching --batch-size 10
```

```
Result: 80/106 nets (75.5%)  segments=3558 vias=40 zones=76  wall=406.2s
Result (pad connectivity, PRIMARY metric): 50/139 nets fully pad-connected
  fake-completion=56  honest-gap=33
Unrouted (26): +15V, DISCHARGE_CTRL, GATE_HS, PWM_LS, RTD_CS_N, bias, ...
```

Re-confirmed independently with the same tool the 53/139 baseline used
(`pad_connectivity_audit.audit_pcb_file`, not trusting the router's own
self-reported line):

```
total=139  fully_connected=50  fake_completion=56
```

| | current placement (fresh route, task-provided baseline) | `relaxed_barrier` re-place (fresh route, measured here) |
|---|---:|---:|
| fully pad-connected | **53/139** | **50/139** |
| wall time | 452s | 406.2s |
| peak RSS | 4.0GB | not separately captured (comparable order of magnitude; process observed climbing toward the same range before completion) |
| `courtyards_overlap` (kicad-cli, post-route) | 8 | **14** (unchanged from pre-route -- routing does not move components) |
| clearance | 316 (true, uncapped) | **>=499 (saturates the DRC report's own cap)** -- not independently uncapped-measured (the uncapped-measurement tool, `scripts/measure_uncapped_drc.py`, is hardcoded to `pcb/temper.kicad_pcb` and has no path override; adapting it was out of scope for this measurement pass). Directionally worse or equal in every observed indicator, never better. |

**The re-place does not beat 53/139. It loses on the task's own named
decisive metric**, and loses again on every DRC-adjacent number checked
alongside it. Per the task's own framing: re-placing is not the answer,
and repair wins by default.

## 7. Repair path, costed honestly

| item | status | source |
|---|---|---|
| 7 of 8 courtyard collisions | verified single/small-part-move fixes (kicad-cli confirmed, 8->1 if applied) | PR #1158, open, not merged |
| `C2`x`C3` (the 8th, worst) | needs coordinated 4-body move (`C2,C3,K3,PS1`); existence proven, not safety-verified | PR #1158 §4.4, open |
| 40/139 nets with zero legal route | unresolved; 7 of the worst confirmed genuinely congested (`no_path`, not forced) after copper strip | PR #1157, open |
| clearance 1085 -> 321 (true 316) | done | PR #1157, merged into this worktree's baseline |
| T2/C37/R65 unplaced | UNSAT, real core (`edge_margin_T2`), re-confirmed today | PR #1144, open |
| isolation barrier (3 isolators, `C6/K1/U6`) | BOM/sourcing defect, sourcing path documented for `C6`, not yet applied | `docs/evidence/2026-07-28-isolator-sourcing-brief.md` |

None of this is fixed by re-placing -- the isolation-barrier BOM defect and
T2's UNSAT are placement-independent facts (§3, §5), and §4 shows a fresh
re-place does not even improve the courtyard-collision picture, let alone
the routing one.

## 8. What a re-place would invalidate, for the record

Every position-pinned measurement on the current board (clearance ratchet,
courtyard ceiling, the 12 PR #1158 verified nudge coordinates, the T2 UNSAT
core, the ~15 PRs stacked on the current geometry) would need re-deriving
from a new board hash. Given §4's result, that cost would buy a board that
is currently MORE collision-prone than what it replaced, not less.

## 9. Recommendation

**Continue repairing. Do not re-place from scratch.** This is not a
default-by-lack-of-evidence call, the way it was the last two times this
decision was deferred -- it is the first time a full re-place has actually
been attempted, and it lost on every axis measured:

- **Decisive metric (task's own framing): 50/139 vs. 53/139 pad-connected,
  fresh-routed, measured the same way for both.** Re-place is worse.
- **Physical assemblability: 14 vs. 8 `courtyards_overlap`, and a new worst
  single collision (9.47mm) exceeding the current board's worst (7.73mm),
  reproduced independently across two different constraint
  configurations.** Re-place is worse, and reproduces the exact failure
  mode (an automated CP-SAT re-solve producing physically-impossible
  output, unchecked) that created the current board's collision problem in
  the first place.
- **Clearance: current board's true count is 316; the re-placed,
  fresh-routed candidate saturates the DRC report's 499-item cap.**
  Re-place is worse or equal, never better, on every DRC-adjacent count
  checked.
- **The isolation-barrier BOM defect (`C6`/`K1`/`U6`, §3) and T2's UNSAT
  (§5) are placement-independent facts.** They block a from-scratch
  re-place exactly as much as they block repair -- neither path avoids
  them, and re-placing does not turn out to be the tool that resolves them.

The repair path, by contrast, has 7 of 8 courtyard collisions with
verified, kicad-cli-confirmed small-move fixes already characterized (PR
#1158, not yet landed), a scoped and already-understood remaining problem
(`C2`x`C3`'s 4-body coordinated move, 40 currently-unroutable nets, 7 of
which are confirmed genuinely congested rather than tooling-blocked, T2/
C37/R65 still unplaced, and the 3-isolator BOM/sourcing defect with a
documented path forward for at least `C6`) -- a known, bounded, already-
partially-solved problem, not an unknown one. Re-placing would forfeit
every position-pinned measurement on the current board (the clearance
ratchet, the courtyard ceiling, PR #1158's 7 verified nudge coordinates,
the T2 UNSAT core, and the ~15 PRs stacked on the current geometry) in
exchange for a board that this document measured to be worse on every
axis checked. There is no version of this trade that pays for itself.

## 10. New defects surfaced (not fixed here -- out of this task's scope)

Listed for whoever picks up the repair path next, per instruction not to
chase fixes in this pass:

- The production `optimize --loop` CLI path cannot run against the real
  board at all (PCL config/board name drift, `temper_induction_cooker.yaml`
  vs. the resynced board -- §2). Pre-existing since 2026-08-11
  (`docs/evidence/2026-08-11-pumpkin-real-budget-spike.md`), still true
  today.
- `add_isolation_barrier_to_model` encodes every isolator's straddle
  constraint unconditionally, without checking its own computed
  `IsolatorFeasibility.feasible` first (§3) -- a solve against the full,
  unfiltered isolator set fails closed on the first geometrically-broken
  part found, with no way to distinguish "genuinely UNSAT" from "one known
  BOM defect papering over an otherwise-solvable model" without manually
  relaxing candidates one at a time, the way this document had to.
- The CP-SAT courtyard NoOverlap constraint's internal geometry
  (`Component.bounds`, e.g. `30.13mm x 18.875mm` for a `CP_Radial_D35.0mm`
  35mm-diameter snap-in electrolytic) does not match the part's true
  circular body -- confirmed to allow real, severe (>9mm) body
  interpenetration between big electrolytics that the solver's own hard
  constraint was supposed to prevent (§4). This is the same defect class
  already implicated in the current board's `C2`x`C3`/`C5`x`C7` collisions
  (PR #602); it was not fixed by, and is not specific to, this document's
  re-place attempt -- it lives in the shared encoder and will affect any
  future placement solve, repair or re-place, that includes these parts.

## 11. Final verification

```
$ sha256sum pcb/temper.kicad_pcb
a70e34bbefe4801212104376adccd59872c06142d8a4d0de0f04eea5a445f04f
```

Identical to this document's own §1 value and to
`power_pcb_dataset/drc_ceiling.json`'s recorded `provenance.inputs[].sha256`
-- `pcb/temper.kicad_pcb` was not modified by any measurement in this
document. Every candidate board (`full_replace_candidate.kicad_pcb` x3,
`routed.kicad_pcb`) lives under this document's own scratch paths, never
under `pcb/`.

```
$ git status --porcelain
(clean)
$ git grep -l "^<<<<<<< "
(empty)
$ uv run --no-sync python scripts/check_stale_extensions.py
PASSED -- 10/10 extension module(s) fresh.
```

10/10 extensions were also independently import-verified (not just the
freshness gate, which certifies freshness but not loadability per the
task brief's own warning) before any measurement in this document was
taken.
