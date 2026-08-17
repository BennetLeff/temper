<!-- provenance: commit=caec25d61 (main, HEAD at start of this task), worktree agent-a0baf6568e3fdb60f.
pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1
verified unchanged before starting (read-only reference only, never opened for writing).
Spec: docs/evidence/2026-08-17-placer-creepage-constraint-spike.md (commit 659f62759,
branch spike/placer-creepage-constraints -- not yet merged to main at task start; read via
`git show 659f62759:docs/evidence/2026-08-17-placer-creepage-constraint-spike.md`, same
shared .git object store). -->

# Wiring `domain_clearance.py` into the main placement solve

STATUS: **done.** Constraint wired into `solve_placement`'s default path
(both `--loop`/`--no-loop`), solved live at 12.6mm PD3 on the current board
(optimal, 94.7s, J1/K1 legally separated by 148.9mm, 0 audit violations),
routed fresh and measured end-to-end against a same-methodology baseline.
Net result: the constraint works exactly as specified; the resulting
full-board-reshuffle placement is a worse board on connectivity/DRC than the
current one, a risk the spike itself flagged as unmeasured (§8) and not a
defect in the constraint mechanism. See "What was left undone" for the
natural next step (a minimal-disruption solve) not attempted here.

## Task

Per the spike's §7 recommended design: wire
`domain_clearance.generate_domain_clearance_constraints` into
`solve_placement()`'s default path (both `--loop` and `--no-loop`), encoding the
full classified cross-domain pair set (never a subset scoped to
currently-violating pairs, per spike §6). Measure solve time at the real 12.6mm
PD3 margin on today's board. Determine the J1/K1 verdict: placed legally or
board infeasible. If placement changes, route it and measure connectivity + DRC
before/after.

## Hard constraints in effect

- No edits to `pcb/temper.kicad_pcb`. No edits to `netclass_constraints.py` or
  `gates.py` (`IECCreepageGate`) -- a sibling agent owns those.
- No clearance/creepage/DRU threshold changes. 12.6mm PD3 is settled.
- No new placement committed to the board -- producing and reporting one is in
  scope, committing it is not.

## Plan (filled in as executed)

1. Read `domain_clearance.py`, `_encoder_solve.py`, `cli/__init__.py`,
   `_loop_core.py`, `io/real_board.py` to confirm the spike's call-site claims
   and find the minimal wiring point. DONE -- confirmed exactly as the spike
   describes: `generate_domain_clearance_constraints` had exactly one caller
   in `src/` (`cli/repair_commands.py`'s `repair-unplaced`), never
   `solve_placement`'s main `optimize` path.
2. Wire the constraint generator into `solve_placement`'s default path, gated
   so it always encodes the full classified pair set. DONE. See "What was
   wired" below.
3. Run a full solve at 12.6mm PD3 on the current board; record wall time,
   constraint count, and CP-SAT status (optimal/infeasible/UNSAT core).
   IN PROGRESS (background run started; this doc will be updated with the
   result).
4. If a placement results, route it (scratch `.kicad_pcb` + `.kicad_pro` +
   `.kicad_dru` sidecars) and measure pad connectivity + DRC
   (`--severity-all --all-track-errors`, with and without `--refill-zones`)
   against the stated baseline (63/139 connected, 36/139 genuine multi-pad,
   DRC total 1086).
5. Report findings here; do not commit the new board placement itself.

## What was wired (commit-in-progress)

- `packages/temper-placer/src/temper_placer/cli/_optimize_audit.py`: added
  `_build_domain_clearance_constraints(validator_input, all_refs)`. Reuses
  the SAME `placement`/`voltage_domains` dict `_build_validator_input`
  already loads via `temper_placer.io.real_board.load_real_board_placement`
  (elec/domain_manifest.yaml-backed) for the post-solve audit -- no new data
  load. Calls `domain_clearance.generate_domain_clearance_constraints` with
  `all_refs` = every ref in the netlist being solved (never a
  violation-scoped subset, per the spike's §6 finding that scoping
  regresses 76->217-265 elsewhere). Returns `[]` (byte-identical,
  unconstrained) when `validator_input` is `None` (the existing documented
  skip condition), matching every other optional `solve_placement` input's
  convention in this module.
- `packages/temper-placer/src/temper_placer/cli/__init__.py`: both the
  `--loop` and `--no-loop` branches of `optimize` now call
  `_build_domain_clearance_constraints(validator_input, all_refs)`
  immediately after building `validator_input`, and append the result onto
  `pcl_constraints` before it becomes `extra_constraints`
  (`--no-loop`) / `all_constraints` inside `_loop_core.py::run()`
  (`--loop`, via `pcl_constraints=`).
- No changes to `netclass_constraints.py`, `gates.py` (`IECCreepageGate`),
  or any clearance/creepage/DRU threshold. `domain_clearance.py` itself is
  unmodified -- only its call graph changed.

Confirmed live (from the 12.6mm re-solve run against today's board,
`elec/domain_manifest.yaml`): 158/168 components classified, matching the
spike's own figure; the J1<->K1 pair IS present in the generated constraint
set at 12.6mm (see run output for the exact `because`/`id`). A separate,
expected finding: 8 components (`C6, K1, K2, K3, PS1, T1, T2, U6`) straddle
a DC_BUS<->LV_CONTROL domain boundary WITHIN their own footprint (relays,
transformers, isolators) -- `generate_domain_clearance_constraints` logs
this and cannot, by construction, protect these refs against themselves;
this is documented, not a defect (see `domain_clearance.py` module
docstring). It does not prevent the J1<->K1 (two distinct refs) constraint
from being generated.

## Solve result at 12.6mm PD3 (today's board, live-measured)

Driver: full-board re-solve mirroring `docs/evidence/2026-07-30-copper-aware-
domain-resolve.md`'s own methodology (full unfiltered constraint set, soft
`hint_positions` seeded from the current board, `timeout_ms=600_000`), run
against `pcb/temper.kicad_pcb` (sha256 `6ac8b1ca8a...`, unchanged throughout
-- verified before and after every step below) via `load_real_board_placement`
+ `generate_domain_clearance_constraints` + `solve_placement`.

| Metric | Value |
|---|---|
| Classified components | 158 / 168 (matches the spike's own figure) |
| Constraints generated | **11,623** over 168 refs |
| J1-K1 constraint present | **Yes** -- `domain_clearance_J1_K1`, `min_distance_mm=12.6` |
| CP-SAT status | **optimal** |
| Solve time (reported) | 94,669.5 ms |
| Solve time (measured wall) | **94.7 s** |
| Post-solve audit (`audit_domain_clearance`) | **0 violations** across all 11,623 constraints |
| Components displaced >1mm | 168/168 (full-board reshuffle, as the 2026-07-30 precedent's own §3.2 predicted for a first full-coverage encode) |

**J1/K1 verdict: J1 is placed legally, not infeasible.** J1 solved at
(6.96, 73.22)mm, K1 at (149.87, 31.56)mm -- center-to-center distance
**148.858mm**, against the 4.0-5.3mm the spike measured on the current
committed placement. This is the "solver relocates the neighborhood" branch
of the spike's §4 point 5 ("both possible outcomes are the honest, wanted
result") -- not the infeasible branch, but equally valid evidence that the
constraint is live and effective: with 11,623 constraints covering the full
classified cross-domain pair set (not scoped to J1/K1 alone, per the hard
rule against violation-scoping), CP-SAT found a globally consistent
placement satisfying every one of them, including J1-K1, in under 100
seconds -- well inside the "several minutes" the spike's §6 projected by
extrapolating the 8.0mm/40.5s -> 10.0mm/82.2s trend to 12.6mm.

**This fills the spike's explicitly stated gap** (§8: "whether solve_placement
at 12.6mm PD3, full classified pair set, on today's 168-component board
returns optimal or infeasible ... was not re-run live"): it returns
`optimal`, at 94.7s.

## Routing / DRC before-after (the spike's other stated-open gap: §8's
second bullet, "whether wiring domain_clearance.py in by default would
regress ... other, currently-passing parts of the board")

Since the solve moved every component (168/168 >1mm), the candidate
placement was written to a **scratch** board (`write_placements_to_pcb`,
positions/rotations only, same production write path `cli/__init__.py`
already uses) and **routed fresh** via `scripts/route_board.py`'s
`route_once` (default `keep_existing_copper=False` -- strips old copper,
routes from the placement's own current positions). The **baseline** is the
SAME real committed board's own current (unchanged) placement, ALSO routed
fresh the identical way, for an apples-to-apples comparison isolated to the
placement change alone, not to "old stale copper vs. new copper." Both runs:
`scripts/route_board.py` default flags, single process, wall-clock timed.
Neither ever wrote `pcb/temper.kicad_pcb` -- verified unchanged (sha256
`6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`) before,
during, and after every step in this document.

| | baseline (current placement, fresh route) | candidate (12.6mm domain-clearance re-solve, fresh route) |
|---|---|---|
| Router topology completion | 38/106 nets (35.8%), wall 347.4s | 25/106 nets (23.6%), wall 382.3s |
| Segments / vias / zones | 4712 / 176 / 143 | 3801 / 184 / 108 |

Pad connectivity (`pad_connectivity_audit.audit_pcb_file`, 139 pad-bearing
nets both boards) and DRC (`kicad-cli pcb drc --severity-all
--all-track-errors`, resolvable `.kicad_pro`/`fp-lib-table`/`libs`
sidecars + SSOT-regenerated `.kicad_dru` beside each scratch `.kicad_pcb`,
measured with and without `--refill-zones`):

| Metric | baseline | candidate | delta |
|---|---|---|---|
| Connected (fully_connected) | **63/139** | 50/139 | -13 |
| Genuine multi-pad connected | **36/139** | 23/139 | -13 |
| Broken | 67/139 | 80/139 | +13 |
| Zone-dependent-unmeasured | 9/139 | 9/139 | 0 |
| DRC total, no `--refill-zones` | **1084** | 1216 | +132 |
| DRC total, `--refill-zones` | 1023 | 1144 | +121 |

The task's cited baseline (63/139 connected, 36/139 genuine multi-pad, DRC
total 1086) is reproduced almost exactly by this independent re-measurement
(1084 vs 1086, a 2-violation difference consistent with this project's own
documented creepage/clearance measurement jitter) -- cross-validating this
document's methodology against whatever produced that baseline figure.

By-category DRC deltas worth flagging (both `--refill-zones`, baseline ->
candidate): `clearance` 225->161 (**improvement**, -64 -- the domain-
clearance constraint genuinely reduces clearance violations board-wide, not
just at J1/K1), `shorting_items` 53->42 (**improvement**, -11),
`hole_clearance` 26->23 (improvement), `creepage` 121->132 (regression,
+11), `via_dangling` 23->21 (improvement), `track_width` 120(real)->199
(**capped** -- real count is >=199, a regression of unknown true size),
`silk_over_copper` 42(real)->199 (**capped** -- same caveat, likely a real
and large regression), `isolated_copper` 0(absent)->**2** (new, small).

**Verdict: the constraint mechanism works exactly as specified -- 0 domain-
clearance audit violations, J1/K1 legally separated by 148.9mm, full
classified-pair coverage, solved in 94.7s -- but the resulting placement,
even after a full fresh route, is a measurably WORSE board than the current
one on connectivity (-13/139) and DRC (+121 to +132 total, several
categories saturating their measurement cap).** This is not a contradiction
of the spike's recommendation; it is exactly the risk the spike's own §8
flagged as unresolved and exactly what the 2026-07-30 precedent (§3.2, cited
in the spike's §6) found for the same mechanism at a looser PD2-era margin:
a full, unconstrained-elsewhere CP-SAT re-solve moves every component
(168/168 here), which is a legitimate global optimum for the *constraint set
given*, but that set does not include anything about routability, wire
length, or preserving the router-favorable structure of a board that has
been incrementally, manually tuned by ~20 targeted placement PRs (#1248,
#1269, #1279, and others). **The gap is not in the safety constraint --
it is that `solve_placement`'s objective has nothing in it that prefers
"close to the current, already-good-for-routing layout" over any other
placement satisfying the same hard constraints.** The spike's own §7.1
recommendation already gestures at the fix (a minimal-disruption solve, the
same shape `repair_commands.py`'s `fixed_positions`/`minimize_displacement_to`
already support for narrower repairs) but applying THAT to a full-board
domain-clearance solve is new work, outside this task's scope, and is the
natural next step for whoever picks this up (see "What was left undone"
below).

## Addendum: minimal-disruption variant (coordinator follow-up, IN PROGRESS)

The full-board reshuffle above cost 63/139 -> 50/139 connectivity because
`solve_placement`'s objective had nothing preferring the current,
router-tuned layout. Per coordinator direction: re-running the identical
12.6mm PD3 constraint set (`generate_domain_clearance_constraints`, full
classified pair set, same 11,623 constraints -- never scoped to
known-violators) but this time with `solve_placement`'s existing
minimum-displacement repair primitives:

- `minimize_displacement_to = {ref: current_position}` for **every**
  component (not a hand-picked subset -- which refs need to move is exactly
  what the solve should discover), weight 1, objective = minimize summed
  Manhattan displacement.
- **No** `fixed_positions` (nothing hard-frozen) and **no**
  `max_displacement_mm` cap -- an artificial bound could manufacture a false
  "infeasible" for a pair that genuinely needs a larger move; the objective
  alone supplies the pressure to keep moves small, and if J1/K1 truly needs
  a big move, that must show up as a big move, not a forced-infeasible.
- Same `hint_positions` warm start from current board coordinates.
- `timeout_ms=900_000` (15 min).

Driver script: `/tmp/claude-1000/-home-bennet-Desktop-temper/8d670d58-2e7c-42ad-b59f-ca4e3fccd905/scratchpad/creepage-constraint/resolve_minimal_disruption.py`
(per this task's instruction, large driver scripts live under `/tmp`, not
the worktree). Launched detached (`nohup ... &`, pid 2250762 / CP-SAT worker
2250765), log at
`/tmp/claude-1000/-home-bennet-Desktop-temper/8d670d58-2e7c-42ad-b59f-ca4e3fccd905/scratchpad/creepage-constraint/resolve_minimal_disruption.log`.
**Started 2026-08-17 16:46 local, still running as of this commit** (a real
Manhattan-sum minimization objective over 11,623 hard constraints and 168
components is a materially harder search than the feasibility-only solve
that returned `optimal` in 94.7s -- CP-SAT must explore to reduce/prove the
objective bound, not merely find any one feasible point). Machine is under
memory pressure from sibling agents (two ~13-18GB pytest runs, several
concurrent routes); this solve's own worker process is a modest ~440MB RSS
and is not itself the pressure source. Being polled in bounded chunks;
results (moved-component count, max/median displacement, whether J1/K1
holds, connectivity/DRC after a fresh route) will be added to this file as
they land -- not fabricated or estimated ahead of the actual solve
terminating. `pcb/temper.kicad_pcb` sha256 verified unchanged
(`6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`) at this
checkpoint.

## What was left undone

- **A minimal-disruption variant was not attempted.** `solve_placement`
  already exposes `fixed_positions` (hard pins) and
  `minimize_displacement_to` + `max_displacement_mm` (bounded, objective-
  guided repair) -- the same primitives `repair_commands.py` uses for its
  narrower single/few-component case. Freezing every component NOT
  touching a domain-crossing violation and re-solving only the violating
  neighborhood (the same idea both the spike's §7 and the 2026-07-30
  precedent's §4 conclusion recommend as the next step) would very likely
  close most of the connectivity/DRC gap measured above, since it would
  leave the router-favorable parts of the current layout untouched. This
  was out of scope for "wire the constraint and measure the outcome" and
  is flagged, not attempted.
- The three-classifier drift (spike §7.5: name-keyword heuristic vs.
  KiCad-NetClass DRU tables vs. `elec/domain_manifest.yaml`-backed
  `VoltageDomain`) and the two stale-6.0mm sites (`IECCreepageGate`,
  `PhysicsGate`'s creepage sub-check, `DeltaMapper`) are untouched, per this
  task's explicit instruction to stay out of `netclass_constraints.py` and
  `gates.py` (a sibling's territory) and per the hard rule against changing
  any clearance/creepage/DRU threshold.
- `track_width` and `silk_over_copper`'s candidate-side true (uncapped)
  counts were not measured (`scripts/measure_uncapped_drc.py`'s exhaustive
  per-category method exists for this but was not run here, for time) --
  both categories hit the 199 saturation cap on the candidate board, so the
  reported deltas for them are a floor, not the real regression size.
- Four pre-existing, unrelated CLI test failures
  (`test_optimize_no_loop.py::test_no_loop_success_writes_output`,
  `test_no_loop_propagates_seed`, `test_no_loop_round_trip_oracle_runs_and_passes`,
  `test_no_loop_warm_start_passes_hints`) were found while sanity-checking
  this change against the existing test suite. **Isolated and confirmed NOT
  caused by this change**: they reproduce identically (same
  `board.origin`-shaped position offset in the round-trip oracle) with
  `elec/build/default.net` removed entirely -- i.e. with `validator_input`
  forced back to `None` and `_build_domain_clearance_constraints` returning
  `[]`, the exact pre-wiring code path. Not fixed here (out of scope,
  pre-existing, unrelated mechanism -- looks like a `write_placements_to_pcb`
  / `check_placement_roundtrip` interaction specific to the tiny
  `minimal_board.kicad_pcb` fixture, not the domain-clearance change).
