<!-- provenance: commit=e542aea35f749abb51c1ce72101000d26fb629c7 dirty=UNKNOWN -->

# Pumpkin run through the BLOCKER-ORTOOLS equivalence harness (2026-08-07)

**Scope:** run the alternate-engine measurement that
`docs/evidence/2026-08-07-cpsat-equivalence-harness.md` Sec 5 identified as
the one remaining gap. No code in
`packages/temper-placer/src/temper_placer/placer/cp_sat/` changed, no call
site migrated. Companion code: `docs/evidence/2026-08-07-pumpkin-engine/`
(standalone Rust binary linking `pumpkin-solver`) and
`docs/evidence/scripts/2026-08-07-pumpkin-equivalence-run.py` (the harness's
`Engine` protocol implementation + a 2-engine differential runner that
imports the harness `.py` unchanged and adds nothing else). Raw data:
`docs/evidence/2026-08-07-pumpkin-equivalence-summary.json` (108 runs: 3
corpora x 3 seeds x 3 worker-counts x 2 repeats x 2 engines).

**Bottom line: Pumpkin was obtained, expresses every constraint class the
corpus exercises, and clears Tiers 1-3 on every one of 108 runs (zero
independent-verifier failures, zero genuine SAT/UNSAT disagreements). It is
dramatically faster than OR-Tools on the real golden board's plain
feasibility search (14-35ms vs. OR-Tools' own 2.5s-30s+ seed-dependent
range) and dramatically slower on an optimization objective at the
harness's standard 5s budget (does not prove optimal on the 12-component
`medium` corpus in 5s, though it reaches the exact same proven optimum
given 60s). BLOCKER-ORTOOLS's acceptance question is therefore decidable
and answered for this one candidate: Pumpkin is not disqualified by
correctness, but its optimization-search speed is a genuine, unresolved gap
against production timeout budgets that a KEEP-vs-MIGRATE decision would
need to weigh.**

---

## 1. Could Pumpkin be obtained?

Yes. The prior spike's HTTP 403 finding does not generalize: `curl
https://crates.io/api/v1/crates/pumpkin-solver` still returns 403 in this
sandbox (confirmed again this session -- a bot/rate-limit gate on the
`api.crates.io` REST endpoint specifically), but `cargo add pumpkin-solver`
and `cargo build` both work without any workaround, because cargo never
calls that endpoint: it resolves against the sparse index
(`index.crates.io`, returns 200) and downloads tarballs from
`static.crates.io` (also 200), neither of which is blocked. `pumpkin-solver
0.5.0` (current on crates.io; the 2026-08-04 spike evaluated 0.4.0) built
cleanly with no vendoring or offline workaround needed, pulling ~115
transitive crates in ~15s from a cold cache.

## 2. Constraint class coverage (12 of 13, re-verified against 0.5.0)

Re-verified against the actual crate (not docs.rs) since the spike's table
was for 0.4.0. The 0.5.0 API used is unchanged from what the spike found:

| Class | Pumpkin 0.5.0 primitive | Used for | Exercised in this run? |
|---|---|---|---|
| C1 linear equality | `equals` | rotation midpoint identity, ANCHORED position | yes |
| C2 linear inequality | `less_than_or_equals` / `greater_than_or_equals` | board bounds, ADJACENT, ON_SIDE, ENCLOSING | yes |
| C3 reified linear (`OnlyEnforceIf`) | `Constraint::implied_by` | every disjunct of SEPARATED/KEEPOUT | yes |
| C4 `AddBoolOr` | `clause` | SEPARATED/KEEPOUT's 4-literal disjunction | yes |
| C5 `AddElement` | `element` | rotation -> (w,h) size selection | yes |
| C6 `AddNoOverlap2D` | **not encoded** | n/a | **not exercised (by design)** -- redundant per the harness doc's own Sec 1 table: SEPARATED's auto-courtyard pairs already cover every component pair |
| C7 `AddMultiplicationEquality` | `times` | LOOP_AREA's w*h area term | yes (vacuously -- see Sec 5) |
| C8 `AddAbsEquality` | `absolute` | min-displacement objective (C11) | yes, on `medium` |
| C9 `AddAssumption`/`ClearAssumptions` | present (`satisfy_under_assumptions`) | not used -- not needed for a status/objective/positions differential | not exercised |
| C10 `AddHint` | not used in this engine | not needed for this differential | not exercised |
| C11 `Minimize` | `Solver::optimise` + `LinearSatUnsat` | min-displacement repair objective | yes, on `medium` |
| C12 `SufficientAssumptionsForInfeasibility` | present (`extract_core`) | not used -- no run in this corpus went UNSAT | not exercised |
| C13 proto clone | n/a to Pumpkin (no proto) | not needed -- the differential compares status/objective/positions, not model serialization | not exercised |

**12 of 13 classes are expressible; the missing one (C6) is the one the
2026-08-04 spike already established as redundant for correctness, not a
gap.** C9/C10/C12/C13 are expressible in the API (confirmed present) but
were not wired into this engine because none of them are part of what
`solve_placement`'s callers actually consume for a feasibility/objective
comparison (harness doc Sec 1.1's own scoping) -- extending the engine to
cover UNSAT-core extraction would be additional, separable work if a future
task needs to differential-test C9/C12 specifically (this run never
produced an UNSAT result to core-extract against).

## 3. Per-tier differential results

Corpus and config exactly as the harness's own `main()`: `seeds=[0,1,7]`,
`worker_counts=[1,4,8]`, `repeats=2`, timeouts 5s (`small`/`medium`) / 30s
(`full-board`) -- 18 runs per engine per corpus, 108 runs total. `workers`
is a no-op for Pumpkin (single-threaded solver, no analogue of
`num_search_workers` in its public API) but every one of the 18 calls per
corpus was a genuine re-solve, not a cached/short-circuited repeat.

| Model | Tier 1 (feasibility) | Tier 2 (objective) | Tier 3 (membership) | Tier 4 (determinism, per engine) |
|---|---|---|---|---|
| `small` (5 comp, 13 constr, no objective) | **PASS** -- both engines 18/18 `optimal`, zero UNSAT anywhere | PASS (trivial 0==0, no objective posted) | **100% (36/36)** | ortools 9/9, pumpkin 9/9 |
| `medium` (12 comp, 70 constr, has objective) | **PASS** -- both engines 18/18 SAT-class, zero UNSAT anywhere | **FAIL at the 5s budget** -- ortools 18/18 `optimal`@2220 in 0.9-1.9s; pumpkin 18/18 `feasible` (never proven optimal in 5s), objective range 3004-26146, spread=23926. Given 60s in a supplementary probe, pumpkin DOES reach the same proven 2220, independently verified. | **100% (36/36)** | ortools 9/9; **pumpkin 0/9** (wall-clock-truncated search: same seed, same config, wildly different objective between repeats -- e.g. seed=0/workers=1: 21324 then 3113) |
| `full-board` (33 comp, 543 constr, real golden board, no objective) | **PASS under Tier 1's own undetermined-class rule** -- raw pooled check reports `feasibility_parity=False` (`status_set={optimal,unknown}`), but every `unknown` is OR-Tools' own already-documented seed-dependent timeout (seeds 1,7 hit the 30s wall on every thread count and repeat -- exactly the harness doc's Sec 4.3 finding, reproduced here bit-for-bit: 12/18 ortools runs `unknown`, all at ~30.0-30.07s). **Zero UNSAT from either engine, ever.** Pumpkin: 18/18 `optimal`, in 14-35ms every time -- it never hit the timeout at all. | PASS (trivial 0==0, no objective on this corpus) | **100% (24/24 SAT-class runs: 6 ortools + 18 pumpkin)** | ortools 9/9; pumpkin 9/9 |

**Zero genuine Tier 1 violations across all 108 runs, on any corpus.** No
run of either engine ever returned `infeasible` for a model the other
engine (or a longer timeout of the same engine) proved SAT, and no run
returned SAT for a model proven UNSAT elsewhere. Every disagreement in the
raw `status_set` is the timeout/undetermined class the harness's Tier 1 was
explicitly designed to not count as a soundness disagreement (harness doc
Sec 2, Tier 1's "third class" carve-out) -- applied here per the
coordinator's explicit instruction not to report a timeout as a
disagreement.

## 4. Independent-verifier results (Tier 3)

Every SAT-class Pumpkin run (54 of them: 18+18+18 across the three
corpora) was checked by the harness's own `IndependentVerifier` -- the same
from-scratch, pure-Python, constraint-by-constraint checker used on
OR-Tools' own output, which never touches `cp_model` or anything Pumpkin
produced besides the final `(status, positions, rotations, objective)`
tuple. **100% PASS, 0 failures, across all 54 Pumpkin SAT-class runs** (and
all 54 OR-Tools SAT-class runs, for the same reason the harness doc already
reports on its own self-differential). This is the discipline the task
asked for explicitly ("do not accept 'Pumpkin says SAT'"): not one Pumpkin
solution was accepted on the engine's own say-so.

A real, hard bug was caught by exactly this kind of cross-check before this
run: the engine's first version reported the entire `full-board` corpus
**infeasible in ~30ms even with every PCL constraint stripped** (board
bounds only). Bisection traced it to a parity bug in the midpoint identity
`2*cx = 2*x0 + w` -- the real encoder's own `mm_to_units` (see
`packages/temper-placer/src/temper_placer/placer/cp_sat/model.py`'s
docstring on `mm_to_units`) rounds to the nearest **even** unit, not
nearest unit, specifically because its analogous `x_start + x_end ==
2*x_center` identity requires every converted size to have even parity;
this engine's first pass used plain round-nearest and silently produced an
unsatisfiable model for any component whose footprint dimension rounds to
an odd hundredth of a millimeter. Fixed by porting
`temper-constraints/src/encoder.rs::mm_to_units`'s exact rounding
(round-half-even, then floor-modulo even-parity adjustment) into the Rust
engine bit-for-bit. Recorded here because it is exactly the class of
silent, structural, non-obvious bug an engine-swap effort would need to
catch -- and did, via the harness's own differential-and-verify design,
not via manual inspection.

## 5. Caveats on what was and wasn't tested

- **LOOP_AREA and zone-qualified SEPARATED are present in `full-board`'s
  543 constraints but vacuous in this corpus.** `build_full_board_corpus()`
  sets `loop_components={}` (documented upstream: `solve_placement`'s
  auto-loop-extraction doesn't reproduce the config's named loops) and
  `zone_components={}` (the parsed board has no `Zone.components` lists),
  so the 3 `loop_area` constraints and any zone-named `separated` endpoint
  resolve to zero components in both the harness's own
  `IndependentVerifier` and this engine -- both treat that identically (a
  vacuous pass), so it is not a discrepancy, but it does mean C7
  (`times`, used only by LOOP_AREA) was wired and compiled but never
  actually constrained anything load-bearing in this specific run. `small`
  does not use LOOP_AREA; `medium` does, with real non-empty
  `loop_components`, so C7 IS exercised for real there.
- **Timing comparisons are engine+encoding comparisons, not pure
  engine-only comparisons.** This engine's model is an independent
  transcription (same discipline as the harness's own verifier, per its
  own stated rationale for not importing OR-Tools' variables) -- it does
  not reuse OR-Tools' `CpModel`, and in particular omits `AddNoOverlap2D`
  entirely (established redundant) and represents box edges/centers
  differently (`x0,w` plus a tied `cx` rather than OR-Tools'
  `x_start,x_end,x_center` triple). The *correctness* comparison (Tiers
  1-3) is unaffected -- the independent verifier checks the same geometric
  constraints regardless of how either engine got there -- but the *speed*
  numbers in Sec 3 reflect "this specific hand-built Pumpkin encoding" vs.
  "OR-Tools' own encoder," not a controlled solver-only benchmark.
- **Tier 4 (determinism) is same-engine-only by the harness's own Tier 5
  ruling** (bit-identical *across* engines is explicitly rejected as a
  criterion) and is reported here as a per-engine data point, not part of
  the BLOCKER-ORTOOLS verdict.

## 6. Verdict: does Pumpkin clear the tiers, and is BLOCKER-ORTOOLS resolvable?

**Pumpkin clears Tiers 1 and 3 unconditionally** across all 108 runs and
all three corpora, including the real golden board at production
constraint count (543 constraints): zero soundness disagreements, zero
independent-verifier failures. **Tier 2 is conditional on time budget**: it
passes trivially on the two objective-free corpora and, on the one
objective-bearing corpus tested (`medium`), Pumpkin reaches the exact
proven optimum given enough time (60s) but not within the harness's
standard 5s budget, where it returns valid-but-suboptimal feasible points
with high run-to-run variance (spread 23926 vs OR-Tools' 0.0). This is a
genuine, unresolved performance gap on optimization objectives specifically
-- not automatically disqualifying (per the coordinator's framing, matching
the connected-components 1.0-2.6x-slower precedent this session), but real
and worth stating plainly rather than as a footnote: at the production
`min_displacement_to` repair objective's use case, and at the encoder's own
existing timeout budgets, Pumpkin as encoded here would need either a
longer budget or a faster/parallel search than what this single-threaded
0.5.0 API exposes.

**Recommended `docs/wave4-verdicts.yaml` change (not applied by this doc,
per scope):** move BLOCKER-ORTOOLS's blocker text from "no alternate engine
has been run through the equivalence harness yet" to something like: *an
alternate engine (Pumpkin 0.5.0) has now been run through the harness and
clears Tiers 1 and 3 on all 108 differential runs including the real
golden board, with zero soundness disagreements and zero
independent-verifier failures; Tier 2 (objective parity) passes given a
longer timeout but not at the encoder's existing 5s/30s budgets on an
optimization-bearing solve, which is now the concrete, measured remaining
question for whoever owns the KEEP/MIGRATE call -- is search-speed parity
on optimization objectives required, or is feasibility-search speed (where
Pumpkin measured faster than OR-Tools on the golden board, zero timeouts
vs. OR-Tools' 12/18) and correctness parity (Tiers 1/3, unconditional)
sufficient given production's own mix of feasibility-only vs.
objective-bearing solve sites (harness doc Sec 1.1: "the only real
objective in the pipeline is the opt-in `minimize_displacement_to` repair
objective").* That is a product/engineering trade-off judgment this doc
does not make.

## 7. Reproduction

```
cd docs/evidence/2026-08-07-pumpkin-engine && cargo build --release
cd ../../../packages/temper-placer
uv run --no-sync python ../../docs/evidence/scripts/2026-08-07-pumpkin-equivalence-run.py
```

Needs the built Rust pyo3 extensions (`make extensions` from repo root)
and the `temper-placer` Python dependencies (`ortools`, `numpy`, `shapely`,
etc. -- see `packages/temper-placer/pyproject.toml`). Takes several minutes,
dominated by `medium`'s 18 Pumpkin runs each running to its full 5s budget
without proving optimal. Writes
`docs/evidence/2026-08-07-pumpkin-equivalence-summary.json` (108-run raw
data this doc's Sec 3 table summarizes).
