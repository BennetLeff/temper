---
title: Placer Combined Objective — Wirelength/Clustering + HV/SELV Separation — Plan
type: feat
date: 2026-08-11
topic: placer-wirelength-hv-separation
artifact_contract: ce-unified-plan/v1
artifact_readiness: design-and-prototype
execution: code
product_contract_source: ce-plan
status: draft
swept: null
swept_basis: null
---

# Placer Combined Objective — Wirelength/Clustering + HV/SELV Separation — Plan

## Goal Capsule

**Objective:** Design (not implement) a combined CP-SAT placement
formulation for `pcb/temper.kicad_pcb`: a linear HPWL wirelength/clustering
objective plus a parameterised HV/SELV isolation-barrier hard constraint, in
the same solve, replacing today's feasibility-only, no-objective placer path.

**Headline finding, stated first per this task's instruction.** A
barrier-admitting placement is **feasible today at PD2/8.0mm** — not merely
theoretically, but *already true of the committed board's pad/footprint
geometry*, one component-move away, and that move (`R24`) already landed on
`main` (`docs/evidence/2026-08-04-r24-barrier-resolve.md`). What is
**not** feasible today is the *routed copper*: traces, vias and 96 zone
pours already consume 87.4% of the board and leave zero admissible HV-side
space (`docs/evidence/2026-08-04-isolation-barrier-freeform-corridor.md`).
**These are two different claims that the source evidence conflates under
one "87.4%" figure** — the placement problem is nearly solved; the routing
problem (a keepout must be reserved *before* the pour, not carved out
after) is not, and is the expensive part. At **PD3/12.6mm**, feasibility is
materially worse and not established: 196 HV↔SELV pad-pairs violate the
bar on the real placement, and while ~89% of the *inter-component* share is
plausibly recoverable by board growth no real product would use, the
*isolator* population (`C6, K1, K2, K3, T1, U3, U7`) is structurally
invariant to board size and at least one isolator (`K1`, in the CP-SAT
straight-corridor model) remains UNSAT even after part substitution
(`docs/evidence/2026-07-30-pd3-board-expansion-measurement.md`). **This
plan scopes concrete work to PD2/8.0mm and treats PD3/12.6mm as a
documented, gated contingency**, per Key Decision D3.

**Product authority:** `packages/temper-placer/src/temper_placer/placer/cp_sat/**`
maintainers.

**Open blockers:** none for the design itself. Two real prerequisites are
named, not silently assumed, in Scope Boundaries: the PD2-vs-PD3 owner
decision (`docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`, still
open) and the pour-regeneration/keepout-before-pour architecture this
plan's barrier constraint depends on to survive routing
(`docs/plans/2026-07-28-001-feat-provable-safety-place-and-route-plan.md`'s
U3, landed generally but never pointed at this specific corridor).

---

## Product Contract

### Summary

`solve_placement()` (`packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py`)
is the single live CP-SAT entry point for both `temper optimize --no-loop`
and every round of `PlaceRouteLoop` (the default, looped path CI's golden-
and production-board regression tests exercise). It runs a feasibility-only
solve with **no objective** by explicit design (`_encoder_solve.py:491-495`:
*"Phase 1 (feasibility): no objective — find any valid placement"*); the
comment's promised "Phase 2 (wirelength polish)" (`_loop_core.py:908-937`)
re-invokes the same solver with a longer timeout and **posts no new
`Minimize()` term at all** — a vestigial comment, not a mechanism. The only
CP-SAT objective that exists anywhere in this codebase is a minimum-
displacement repair term (`add_displacement_objective`, issue #504),
reachable only through the opt-in `minimize_displacement_to` kwarg, invoked
in a measured ~1% or fewer of real solves
(`docs/evidence/2026-08-07-cpsat-objective-frequency.md`). Separately, a
fully-built, unit-tested, **directional HV/SELV isolation-barrier hard
constraint** (`placer/cp_sat/isolation_barrier.py`) already exists — with
per-isolator rotation-aware pad-cluster splitting and a parameterised
`corridor_width_mm` — but is reachable only through an `isolation_barrier=`
kwarg that no automatic caller (`temper optimize`, `PlaceRouteLoop`, CI)
ever passes.

This plan is the design for turning both of those "exists but unused"
mechanisms on, together, as one opt-in placement-polish pass: a linear
HPWL wirelength objective (new, small — the objective *plumbing*
`add_objective_term`/`apply_objective` already exists and needs exactly one
more term-producer function) composed with the isolation barrier (reused
unmodified, just called), warm-started from the current board and
displacement-bounded so the pass reads as a *repair*, not a fresh re-solve.

### Problem Frame

#### §0. Verifying the synthesis this task was asked to unify

All three source claims were checked against the live code and the cited
evidence, not trusted. Two corrections matter enough to change scope; one
citation the brief seemed to doubt is in fact accurate.

1. **"Zero wirelength/clustering objective in the live solve path" — confirmed
   exactly**, and confirmed *cheap to add*, which the brief's framing does
   not distinguish. `grep -rn "Minimize\|Maximize"
   packages/temper-placer/src/temper_placer/placer/cp_sat/*.py` returns
   exactly one call site (`model.py:290`, inside `apply_objective()`), fed by
   exactly one producer (`add_displacement_objective`). But the *generic*
   objective machinery — `CpSatModel.add_objective_term()`,
   `apply_objective()`, the idempotent-Minimize contract — already exists,
   is already wired into both solve entry points
   (`_encoder_solve.py:507`, `model.py:427-432`), and already ships a
   working example of an `Add{Max,Min}Equality`-style linearisation pattern
   (`AddAbsEquality` in `add_displacement_objective`). Adding HPWL is "write
   one more term-producer function that calls existing plumbing," not
   "build objective support from scratch." This is the single most
   consequential thing this plan found, per this task's own instruction
   that finding it would be "the single most valuable thing" available —
   see §1.
2. **The "~171 residual violations, no straight barrier line, 87.4% copper
   coverage, zero admissible HV-side space" claim is accurate but
   conflates two different geometric models under one number, and the
   conflation changes the recommended scope materially.**
   - `docs/evidence/2026-08-11-creepage-gatedrivehv-false-positive.md` (this
     exists, current — cited correctly; an initial search of this doc under
     the wrong working directory during this task's own investigation
     briefly suggested otherwise, a process artifact of worktree isolation,
     not a real absence) confirms **169–171 residual DRC creepage
     violations** (ceiling 172) as of today, after the same-day
     GateDriveHV/HighVoltageIsolated false-positive fix. 75% of those
     violations involve at least one **already-routed track**, not two bare
     pads — meaning most of the residual cannot be resolved by a placement
     change alone.
   - **"87.4% copper coverage, zero admissible HV-side space" is a claim
     about the *as-routed* board** — 2,338 traces + 48 vias + 96 pours
     (`docs/evidence/2026-08-04-isolation-barrier-freeform-corridor.md`
     §4.1). It is placement-independent: no re-placement fixes it, because
     the obstruction is the copper that already exists, poured by a router
     that has never been barrier-aware.
   - **At the *placement* level — pad/footprint geometry only, assuming a
     full re-route — the same document's §4.2 finds the barrier is
     admissible at 8.0mm except for one component, `R24`** (2.27mm
     shortfall on the widest available channel). `R24` was moved on
     2026-08-04 (`docs/evidence/2026-08-04-r24-barrier-resolve.md`) and the
     necessary-condition test suite now passes both Test 1 (pairwise
     separability) and Test 2 (HV connectivity, at two independent raster
     resolutions) — **on the committed board, today.**
   - **Net effect on scope:** the "topologically non-separable" framing in
     the brief is true of the *as-routed copper*, no longer true of the
     *underlying placement*. This is good news for the objective/barrier
     design (§2) and bad news for how much this plan alone can fix (the
     routed copper needs a full re-route with a keepout reserved before the
     pour — a separate, larger, already-named piece of work; see Scope
     Boundaries).
3. **"171 residual violations exist because no straight barrier line
   separates HV from SELV pads"** is corroborated independently three
   times (an exhaustive axis-aligned-line search still misclassifying
   28–32% of pads at only 5.9mm HV/SELV centroid separation; the routed-
   copper 87.4%-coverage finding; a real-geometry `IsolationBarrierCheck`
   finding 398 crossing/near-miss violations against the routed board's 96
   zones) — see
   `docs/evidence/2026-08-08-selv-hv-pour-barrier-drc-spike.md` §1,2,4e,
   cited by the GateDriveHV doc §4. This part of the synthesis is solid.

#### §1. What the live CP-SAT placer actually does today

- **Entry point:** `solve_placement()`
  (`packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py`),
  called from `cli/__init__.py`'s `optimize --no-loop` path and from
  `PlaceRouteLoop._call_solver` (`_loop_core.py:46-88`), which every round
  of the default, looped `temper optimize` path and every CI-gating
  golden-/production-board regression test goes through.
- **Phase 1 (always-on):** feasibility only, explicitly no objective
  (`_encoder_solve.py:491-495`).
- **"Phase 2 (wirelength polish)"** (`_loop_core.py:905-937`): re-invokes
  the same solver, longer timeout (5s), **posts no objective** — confirmed
  by reading the function body, not inferred from its docstring. The name
  is a holdover from a plan that was never finished.
  `docs/evidence/2026-08-07-placement-clustering-feasibility.md` §3 reaches
  the identical conclusion independently.
- **The only real objective in the codebase**, `add_displacement_objective`
  (issue #504, minimum-displacement repair), is reachable only via
  `minimize_displacement_to`, which no automatic caller ever passes
  (`docs/evidence/2026-08-07-cpsat-objective-frequency.md` §1.1: 5 manual
  incident-script invocations against 482 commits touching this surface).
  Production's real timeout budget for this one objective-bearing path is
  180,000ms/round, up to 4 rounds — 36× the 5s figure a prior harness
  investigation used, and Pumpkin/OR-Tools both prove optimal on the
  displacement objective's own corpus in 5-50s once achievable at all
  (§3 of the same doc). This budget, not the 5s harness artifact, is the
  realistic number to design this plan's own objective against.
- **`isolation_barrier.py`** (`placer/cp_sat/isolation_barrier.py`, 672
  lines): a complete, tested, directional two-region split — HV-only
  components forced to one side of a corridor (vertical or horizontal, not
  freeform), SELV-only to the other, and the 8 isolators
  (`C6, K1, K2, K3, PS1, T1, U3, U7`) individually rotation-pinned so their
  own HV pad cluster and SELV pad cluster straddle correctly. Its only
  caller in the repository is its own test file
  (`tests/placer/cp_sat/test_isolation_barrier.py`) — `solve_placement`
  accepts an `isolation_barrier` kwarg that forwards to it
  (`_encoder_solve.py:111,297-307`), but no automatic caller ever supplies
  it.
- **`domain_clearance.py`** is a *different*, already-live mechanism: it
  generates ordinary pairwise `SeparatedConstraint` objects (one per
  HV/SELV component pair, margin = the IEC 60335-2-6 figure) and **is**
  wired into every production solve via `encode_constraints`. This is why
  the committed board's HV/SELV pairwise clearance is clean (minimum
  measured cross-domain copper separation exactly 8.0000mm, zero pairs
  below) — but pairwise clearance does not imply topological separability;
  a board can satisfy every pairwise margin and still interleave HV and
  SELV in a checkerboard, which is what the committed board does until the
  isolation barrier (a genuinely different constraint shape — connectivity,
  not pairwise distance) is also applied.
- **The `component_groups`/`loss_weights` config surface**
  (`configs/temper_constraints.yaml`) that looks like it should feed a
  clustering objective is dead: `loss_weights` is parsed nowhere in
  `packages/temper-placer/src/`, and `component_groups` feeds a
  rule-based, non-CP-SAT initial-guess heuristic
  (`heuristics/organizational.py` → `pipeline/topological.py`), not the
  live solve. `GroupClusterLoss`, the docstring's named consumer, does not
  exist anywhere in the repository.
  (`docs/evidence/2026-08-07-placement-clustering-feasibility.md` §3,
  independently re-confirmed by this task's own reading of
  `_encoder_solve.py`/`model.py`/`_loop_core.py`.)

#### §2. Feasibility: is a separable placement geometrically possible? (the headline question)

**At PD2/8.0mm: yes, and it is essentially already achieved.** The
necessary-condition test suite built for PR #690
(`docs/evidence/2026-08-04-isolation-barrier-freeform-corridor.md`) —
Test 1 (pairwise separability: no HV/SELV pad pair shares a connected
component of `board \ opening(free, 4mm)`) and Test 2 (HV connectivity: all
HV copper pads reachable in one connected region) — both **pass on the
committed board today**, at pad/footprint granularity, assuming a full
re-route. The one component that failed Test 2 (`R24`, stranded by a
2.27mm channel-width shortfall) was moved on 2026-08-04
(`docs/evidence/2026-08-04-r24-barrier-resolve.md`) with **zero** DRC
category regression, confirmed at 11 samples. Necessary conditions are not
sufficiency (§ Outstanding Questions O1), but this is a materially
different, more optimistic starting point than "topologically
non-separable" suggests. **89% of the board's 169 components (~150) carry
no hard position pin at all** (`docs/evidence/2026-08-07-placement-
clustering-feasibility.md` §2), so there is ample freedom left for both a
wirelength objective and a barrier constraint to operate inside — the
constraints that exist today mostly do not care about clustering or
barrier admissibility one way or the other.

**At PD3/12.6mm: not established, and the available evidence points to
infeasible-without-redesign.**

- **The inter-component (bystander) population is mostly, not entirely,
  recoverable by board growth — and the growth required has no relationship
  to a countertop appliance.** At 12.6mm, 157 of 196 violating pad-pairs
  are inter-component; an idealised uniform re-spread model
  (`docs/evidence/2026-07-30-pd3-inter-component-creepage-board-expansion.md`)
  clears 89% of these by 2× linear board growth (304×468mm — already the
  outer bound the sibling CP-SAT isolator experiment tested), but the
  `C17`/`C22`↔`R32`/`L2` snubber-to-logic cluster needs ~3.75× linear
  growth (~570×880mm) — not a plausible design point.
- **The isolator (intra-component) population is structurally invariant to
  board size — it cannot be helped by any amount of placement freedom or
  board growth**, because it is a fixed property of each isolator's own
  terminal geometry, not of where the isolator sits. `docs/evidence/
  2026-07-30-pd3-board-expansion-measurement.md`: the 7-of-8 isolator
  infeasible set (`C6, K1, K2, K3, T1, U3, U7`) is unchanged at every board
  size tested; even the reduced 4-set after verified part substitutions
  (`K1, T1, U3, U7`) remains **INFEASIBLE** in the CP-SAT straight-corridor
  model (UNSAT core `isolator_straddle_K1`).
- **A real, unconstrained re-solve at comparable scope is expensive, not
  a targeted fix.** `docs/evidence/2026-08-04-r24-barrier-resolve.md` §3's
  own "control" run — asked to change as little as possible under the
  *8.0mm* bar — still moved 167 of 169 refs by a cumulative 7,068.8mm and
  was judged not worth writing. Nothing in the record suggests a 12.6mm
  re-solve would be smaller; every 12.6mm-specific document describes it as
  "a full re-layout," not a nudge.
- **This plan's own isolation-barrier reuse (§ Key Decisions D2) only
  encodes a straight (vertical/horizontal) corridor.** The freeform
  (bent/non-convex) search that rescued the 8.0mm case (the straight-
  corridor NO-GO for `R24` turned out to be resolvable by a single move
  once the shape-independent Test 1/Test 2 methodology was applied) has
  **not** been run at 12.6mm. It is possible a freeform barrier recovers
  some of the isolator/inter-component infeasibility a straight one
  cannot — this is a real, cheap, unanswered question, named explicitly in
  Outstanding Questions rather than assumed either way.

**Conclusion for §2, stated as the task asked:** a separable placement is
feasible, and nearly already achieved, at the bar currently enforced
everywhere in this codebase (PD2/8.0mm). It is not established, and the
available evidence leans infeasible-without-part-substitution-and-a-
large-re-layout, at the bar the standard's own default would require
absent a sealed compartment (PD3/12.6mm). **This is the load-bearing input
to Key Decision D3: scope concrete work to 8.0mm.**

#### §3. Tractability: is the combined formulation solvable at all, in a bounded budget?

No production-scale test-solve was run against the real board (forbidden
by this task's own boundaries — a prior spike burned its whole budget on
exactly this and delivered nothing). Instead, a **synthetic** CP-SAT model
was built and solved this task, matching the real board's rough scale (150
free components, 110 nets, board 152×234mm, a directional 8.0mm barrier
splitting 45 HV/105 SELV components, net-degree distribution skewed like
the real board's `gnd`/`+3V3`/`vcc` high-fanout outliers) — no repo file
touched, script at
`/tmp/.../scratchpad/synth_wirelength_barrier_test2.py` (not committed;
reproducible from this doc). Measured, this task:

| Configuration | Build time | Solve outcome |
|---|---:|---|
| Barrier only (today's Phase-1 shape) | 0.01s | **OPTIMAL in 0.04s** — the barrier constraint alone is essentially free |
| Barrier + HPWL objective | 0.01s | First feasible solution at **t=0.94s**; objective falls from 1,597,633 to 390,573 (4.1× improvement) by t=45s; **optimality gap stuck at ~78-95%, best bound never moves off 84,833 for the whole run** |

**Reading this correctly matters for the design.** The model is cheap to
*build* (1,764 variables, 1,915 constraints for 150 components/110 nets —
HPWL is `O(nets)` extra variables, not `O(components²)`; the "the full O(n²)
objective... creates ~2100 extra variables" warning in `_encoder_solve.py`'s
own comment is about a hypothetical *pairwise* wirelength term, not HPWL,
and does not apply here). But CP-SAT's search finds steadily-improving
feasible solutions fast while making essentially no progress tightening the
proof bound — the same non-monotone, hard-to-prove-optimal shape the
existing displacement-objective investigation already found for a related
(but smaller, 12-component) corpus
(`docs/evidence/2026-08-07-cpsat-objective-frequency.md` §3). **The correct
design target is "materially improved within a fixed budget," never
"proven optimal"** — this is Key Decision D4, and it is falsified, not
assumed: this task measured it directly on a model shaped like the real
problem, not extrapolated from a smaller corpus.

### Key Decisions

- **D1. HPWL, not quadratic wirelength.** CP-SAT is an integer/boolean
  solver; a quadratic (sum-of-squared-distance) objective requires either
  `AddMultiplicationEquality` per pair (no linearisation, poor propagation,
  and — unlike HPWL — genuinely `O(nets × pins²)`) or an approximation with
  no standard CP-SAT idiom. HPWL (`Σ_nets (max_x - min_x) + (max_y - min_y)`)
  linearises exactly via `AddMaxEquality`/`AddMinEquality` over per-member
  center variables that already exist (`ComponentVars.x_center`/`y_center`),
  is the metric this codebase's own post-hoc scoring already uses
  (`validation/metrics.py::_compute_wirelength_metrics`,
  `metrics/physics.py`, `deterministic/stages/_phase_zones.py`'s
  `_compute_wirelength` HPWL kernel for the *separate*, non-CP-SAT
  deterministic pipeline) — using the same metric family for the objective
  and for scoring is a coherence win, not a new concept to justify. Chosen
  over inventing a different differentiable-style loss (the removed
  gradient-descent system's `loss_weights` surface, per §1, is exactly that
  dead end).
- **D2. Reuse `isolation_barrier.py`'s existing straight, directional
  corridor unmodified — do not build a new barrier mechanism.** It already
  does the hard part correctly (per-isolator rotation-aware pad-cluster
  splitting, parameterised `corridor_width_mm`, assumption-literal UNSAT-
  core support) and is already unit-tested. The only missing piece is a
  caller. A freeform (bent) corridor is a real, larger extension (§2, PD3
  discussion) explicitly deferred, not attempted here.
- **D3. Scope concrete implementation to PD2/8.0mm; PD3/12.6mm is a
  documented, gated contingency, not built.** §2's feasibility asymmetry is
  the reason: 8.0mm is both what every one of the 8 enforcement points in
  this codebase currently enforces
  (`docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md` §3.2, confirmed
  aligned as of today) and what is geometrically nearly-solved already.
  12.6mm requires, at minimum, isolator part substitution (following the
  K2/K3 RT314012 precedent) and a probably-large re-layout, gated on an
  organisational decision (build the sealed compartment vs. retarget to
  PD3) this plan does not make. `corridor_width_mm` is already a parameter
  on the reused function (D2), so nothing about this design *prevents*
  12.6mm later — it is a config value, not new code — but no unit below
  builds or verifies the 12.6mm path.
- **D4. The objective is time-budgeted for "materially improved," never
  "proven optimal."** §3's own measurement (78-95% optimality gap, flat
  bound) makes proving optimality an unrealistic bar at this scale. Success
  criteria (Requirements, below) are measured deltas against a baseline,
  not a proof certificate — matching how the existing displacement
  objective is already accepted (`add_displacement_objective`'s own
  docstring: "a preference, never a hard bound").
- **D5. Warm-start from the current board position, with a hard
  `max_displacement_mm` bound, reusing the existing bounded-repair
  primitives (`hint_positions`, `add_displacement_objective`'s
  `max_units`).** Chosen over an unconstrained fresh re-solve: `docs/
  evidence/2026-08-04-r24-barrier-resolve.md` §3's own "control" run shows
  an unconstrained re-solve moves 167/169 refs by 7+ meters cumulative even
  under the easier 8.0mm bar — a re-route-everything outcome this plan
  should not reproduce for a wirelength-quality improvement.
- **D6. The combined (HPWL + barrier) solve is a new, explicitly opt-in
  "placement polish" entry point — not inserted into today's always-on
  Phase 1 feasibility path, and not silently reusing the vestigial "Phase
  2" name.** Chosen because Phase 1's speed and unconditional
  objective-freedom is exactly what keeps every automatically-triggered
  path (CI regression, `PlaceRouteLoop`'s round-trip loop) fast and
  predictable (§1); this plan's objective-bearing solve belongs on the same
  footing as the existing `run_clearance_repair_solve` — a deliberate,
  budgeted, human/agent-invoked polish pass, not a default that changes
  every placement's runtime characteristics.

### Requirements

- **R1.** `CpSatModel` gains a new HPWL objective-term producer
  (`add_hpwl_objective` or equivalent), built on the existing
  `add_objective_term`/`apply_objective` plumbing — no change to that
  plumbing's contract.
- **R2.** The HPWL term operates over component *centers*
  (`ComponentVars.x_center`/`y_center`), matching this model's existing
  box-level granularity — not pad-level HPWL, which would need a
  materially larger model (per-pad position variables the CP-SAT model
  does not carry today). This is a stated approximation, not silently
  assumed precision.
- **R3.** Only router-eligible signal nets (reuse the existing
  should-route classification already used elsewhere, e.g.
  `net_classification.py`/`_net_policy.should_route`) are HPWL-weighted —
  power/ground zone-poured nets are excluded, matching how they are
  already excluded from SAT-routing everywhere else in this codebase.
- **R4.** `isolation_barrier.py` is called, unmodified, with
  `corridor_width_mm` sourced from `isolation_constants.MIN_BARRIER_WIDTH_MM`
  (today 8.0) plus its existing 0.5mm design margin — no new barrier logic.
- **R5.** The combined solve is warm-started from current board positions
  and bounded by `max_displacement_mm`, using the existing
  `hint_positions`/`minimize_displacement_to`/`max_displacement_mm`
  primitives already in `solve_placement()`'s signature.
- **R6.** The combined solve is reachable only via an explicit opt-in
  entry point (new CLI flag or `PlaceRouteLoop` opt-in stage) — it must
  not change the behaviour of `temper optimize`'s default path or any
  CI-gating regression test that does not explicitly request it.
- **R7.** Success is measured, not asserted: HPWL total (mm) on a real
  board run, via the existing `validation/metrics.py::wirelength_metrics_py`
  oracle, before/after; `isolation_barrier`'s own `IsolationBarrierReport`
  (0 infeasible isolators at the chosen bar); Stage 4 routing completion
  rate (not regressed below today's ~58% baseline;
  `docs/evidence/2026-08-11-stage4-placement-congestion-spike.md`); DRC
  ceiling categories (no un-approved rise, per `AGENTS.md`'s existing
  contract).

---

## Units

Dependency order. U1 has no dependency on U2-U4 and is where the real
engineering value concentrates; U2 is the first point real board evidence
becomes available; U3 and U4 are explicitly out-of-this-plan's-execution
bridges to other owners' work, named so they are not silently assumed done.

### U1 — HPWL objective producer

**Deliverable.** `CpSatModel.add_hpwl_objective(nets: dict[str, list[str]],
weight_fn: Callable[[str], int] | None = None)` in
`packages/temper-placer/src/temper_placer/placer/cp_sat/model.py`: for each
net's member component refs, build per-member center references (reusing
existing `x_center`/`y_center`), `AddMaxEquality`/`AddMinEquality` over
each axis, a `span_x`/`span_y` pair, and register both as weighted
objective terms via the existing `add_objective_term`. Net-class weighting
(higher weight on creepage-adjacent/`HighVoltage`-class nets, so the
objective also pulls HV components toward tighter internal clustering,
which independently helps barrier admissibility per
`docs/evidence/2026-08-07-placement-clustering-feasibility.md` §5) is a
tunable parameter, not required for a first landing.

- Reuses `AddMaxEquality`/`AddMinEquality` — both already used elsewhere in
  this codebase's Rust/Python CP-SAT surface for unrelated constraints — no
  new OR-Tools primitive is introduced.
- `solve_placement()` gains an opt-in `hpwl_objective: dict | None` kwarg,
  mirroring `minimize_displacement_to`'s existing shape and fail-closed
  validation discipline (unresolved net members raise, per this codebase's
  established "silent skip is a defect" convention).
- One-line fix bundled here at no extra risk: mark
  `configs/temper_constraints.yaml`'s `loss_weights`/`AestheticConstraints`
  fields' docstrings as explicitly dead/unconsumed (they are, per §1), so a
  future reader does not mistake them for this unit's config surface.

**Evidence of closure.** A unit test comparing `add_hpwl_objective`'s
solved-placement HPWL against `validation/metrics.py`'s own
`wirelength_metrics_py` computation on the same solved positions (the two
must agree, since both should compute the same HPWL definition) — this is
the correctness oracle, reusing an existing implementation rather than
trusting a new one on its own say-so. A synthetic scale test (this plan's
own §3 script, formalised as a repo test or benchmark) demonstrating a
bounded solve at ~150-component/~110-net scale finds a materially improved
(not necessarily proven-optimal) feasible solution within the existing
`run_clearance_repair_solve`-precedent budget (recommend starting at 30-60s,
well inside the accepted 180s/round production budget for objective-bearing
solves).

**Blocked by:** nothing. **Blocks:** U2.

### U2 — Combined polish entry point, spiked against the real board first

**Deliverable.** A new opt-in entry point (CLI flag, e.g. `temper optimize
--polish-wirelength-hv`, or a `PlaceRouteLoop` opt-in post-convergence
stage) that calls `solve_placement()` with U1's `hpwl_objective` **and**
`isolation_barrier` (D2, D4) kwargs together, warm-started
(`hint_positions` from the current board) and bounded
(`max_displacement_mm`, D5). Per this task's own boundary, **no full
place-and-route run against `pcb/temper.kicad_pcb` is executed as part of
this plan** — the first real-board run is explicitly scoped as this unit's
own follow-up spike (read-only against the committed board, reporting
results, not writing them), separate from and before any landing decision.

- The spike's own success/failure criteria are R7's four measures.
- If the spike's solve time or churn exceeds budget, the fallback (per D4)
  is a smaller/weighted objective (fewer net classes weighted, or a
  `max_displacement_mm` bound tight enough to keep the search local) —
  named here as the mitigation path, not assumed to work on the first try.

**Evidence of closure.** A spike evidence doc (this plan's own follow-up,
not written here) reporting: solve status, wall time, HPWL delta,
`IsolationBarrierReport.infeasible_isolators` (expect empty at 8.0mm per
§2), total displacement, and the four R7 metrics — against the real,
current committed board, read-only.

**Blocked by:** U1. **Blocks:** U3 (the routing bridge only matters once a
real barrier-respecting placement exists to route).

### U3 — Bridge to the pour-regeneration/keepout-before-pour architecture

**Deliverable.** *Not new router architecture.* This unit is scoped
narrowly: extend `docs/plans/2026-07-28-001-feat-provable-safety-place-
and-route-plan.md`'s **U3** (pour regeneration after routing — landed
generally, `zone_emission.py`/`_write_zones.py`) so that when a placement
carries an `IsolationBarrierReport`, the barrier's corridor geometry is
passed through as a hard keepout the regenerated zones must not enter —
closing exactly the gap `docs/evidence/2026-08-04-r24-barrier-resolve.md`
§6 names and explicitly did not attempt ("a keepout must be placed before
the pour, not carved out after. Not attempted here"). Without this unit,
U1/U2's placement-level admissibility (§2) cannot survive a real re-route:
the router would immediately re-pour into the corridor, reproducing the
87.4%-coverage obstruction.

**Why this wasn't already built:** `docs/plans/2026-07-28-001`'s own
Landing Status shows U1-U3 landed as *general* stackup/pour-derivation
machinery, but U4-U6 (prover-soundness gate, coverage ratchet, unattended
orchestration) never started, and none of U1-U3's landed work was ever
pointed at *this specific* isolation-barrier corridor, because the barrier
constraint itself has never been active on any real solve until this
plan's U2 turns it on. This is not a duplicate of that plan; it is the
specific application its own §6 gap names.

**Evidence of closure.** `scripts/check_isolation_keepout.py` (currently
red — no `MAINS_SELV_ISOLATION_BARRIER` keepout geometry exists on the
board) passes on a re-routed board produced through this bridged pipeline.

**Blocked by:** U2 (needs a real barrier-respecting placement to route
against). Owned jointly with whoever executes
`docs/plans/2026-07-28-001`'s remaining units — **this plan does not
execute U3 itself**, it specifies the bridge as a small, scoped addition to
already-landed machinery.

### U4 — PD3/12.6mm contingency (design-only; not built)

**Deliverable.** Nothing lands here in this plan's execution. Recorded for
completeness because D3 explicitly defers it: if the PD2-vs-PD3 owner
decision (`docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`) resolves
toward PD3, the concrete prerequisites, in order, are (a) the isolator part
substitutions already named for K2/K3 (RT314012-class swaps) extended to
`K1`, verified against the reduced-set UNSAT finding directly rather than
assumed fixed by analogy; (b) a **freeform** (not straight) barrier
admissibility re-test at 12.6mm, using the same shape-independent
Test 1/Test 2 methodology that rescued the 8.0mm case, before assuming
`isolation_barrier.py`'s straight-corridor mechanism (D2) is even the
right shape at this bar; (c) only then, `corridor_width_mm` retargeted to
12.6 plus the coordinated all-8-points retarget
(`docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md` §4 Option (b)) this
plan's design does not otherwise require.

**Evidence of closure.** N/A — this unit is a documented decision point,
not a deliverable, until the PD2/PD3 decision (Scope Boundaries) resolves.

**Blocked by:** the PD2/PD3 owner decision (outside this plan's authority).

### U5 — Verdict document

**Deliverable.** One document recording U1-U2's measured outcome against
R7's four criteria, following this repo's own evidence-doc convention —
supersedes this plan's synthetic §3 measurement with real numbers once U2's
spike runs.

**Blocked by:** U1, U2.

---

## Scope Boundaries

- **Not in scope: any modification to `pcb/temper.kicad_pcb`, or a full
  place-and-route run against it.** Per this task's explicit boundary — a
  prior spike burned its whole budget on exactly this and delivered
  nothing. U2's real-board spike is named as necessary *follow-up* work,
  not executed here.
- **Not in scope: building the freeform (non-straight) barrier mechanism.**
  D2 reuses the existing straight-corridor `isolation_barrier.py`
  unmodified. A freeform corridor is real, larger work, named only as a
  PD3 prerequisite (U4) this plan does not build.
- **Not in scope: the PD2-vs-PD3 owner decision itself.** This plan designs
  for a parameterised bar (§2, D3) so the formulation survives either
  outcome, but does not choose between them — that decision sits with
  whoever owns `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`'s
  open recommendation.
- **Not in scope: the router-side re-route/re-pour itself.** U3 specifies
  a narrow bridge to already-landed pour-regeneration machinery; executing
  a full re-route with the new keepout is real, large, separate work
  (confirmed by every cited document that touches it: "a keepout must be
  placed before the pour, not carved out after").
- **Not in scope: reviving `docs/plans/2026-07-28-001`'s U4-U6** (prover-
  soundness gate, coverage ratchet, unattended orchestration). U3 above
  depends only on that plan's already-landed U1-U3, not on its unstarted
  units.
- **Not in scope: `docs/plans/2026-08-07-003-feat-routing-block-
  decomposition-plan.md`'s routing-SAT decomposition.** Orthogonal problem
  (router_v6 Stage-3 topology/CDCL memory, not placement); this plan does
  not touch it, though a successful HPWL/clustering objective (U1) would,
  as a side effect, raise that plan's own edges-per-model ceiling for free
  (noted, not scoped, as a possible future synergy — see Dependencies).

## Dependencies / Assumptions

- **`isolation_barrier.py`'s straight-corridor mechanism is correct and
  unmodified-by-this-plan** (D2). Its own soundness discussion (rotation
  selection, HV=lo/SELV=hi convention) is inherited, not re-derived here.
- **The board's pad/footprint geometry admits an 8.0mm barrier today** (§2)
  is contingent on `R24`'s 2026-08-04 move remaining in place and no
  subsequent placement change re-introducing a stranded HV pad cluster —
  worth a cheap re-check (re-running
  `docs/evidence/scripts/2026-08-04-r24-barrier-admissibility.py` against current
  HEAD) before U2's spike, since this plan's own investigation did not
  re-run it against today's exact commit.
- **Production's real objective-bearing solve budget is 180,000ms/round,
  up to 4 rounds** (`docs/evidence/2026-08-07-cpsat-objective-frequency.md`
  §2) — this plan's time-budget recommendations (D4, U1's 30-60s starting
  point) are sized against that figure, not the unrelated 5s harness
  artifact that document already debunked.
- **A successful U1/U2 landing changes `docs/plans/2026-08-07-003`'s own
  "board isn't clustered" measurement** (its `tools/block_dispersion_
  measure.py` finding, radius-of-gyration 90-105% of board-wide for 8/9
  atopile blocks) **if and only if** the HPWL objective is weighted to
  favour intra-block locality specifically, which this plan's default
  (net-class weighting, not block-membership weighting) does not do by
  default — named as a possible follow-on tuning, not assumed to happen
  automatically.
- **`net_classification.py`/`_net_policy.should_route`'s existing
  should-route predicate is the correct filter for R3's "router-eligible
  signal nets"** — reused, not re-derived.

## Outstanding Questions

- **O1** (§2). Test 1/Test 2 are *necessary*, not *sufficient*, conditions
  for barrier admissibility (a min-cut probe in the freeform-corridor
  evidence found a separating curve but not one reaching exactly two
  regions). Whether a genuinely conforming, exactly-two-region barrier
  exists at 8.0mm on the current placement is unresolved — U2's spike
  should attempt to construct one explicitly, not merely re-check the two
  necessary conditions.
- **O2** (U1). Net-class weighting values (which classes get more HPWL
  weight, and by how much) are left as a tunable, not specified — an
  execution-time discovery once real board measurements (U2's spike) show
  which nets dominate the objective.
- **O3** (U3). The exact mechanism for passing barrier-corridor geometry
  into `zone_emission.py`'s pour regeneration (a new keepout-polygon
  parameter vs. a board-level config artifact) is deferred to whoever
  executes that unit — this plan specifies the requirement (R4, U3's
  Deliverable), not the API shape.
- **O4** (U4/D3). Whether a freeform barrier search recovers isolator or
  inter-component feasibility at 12.6mm that the straight-corridor model
  cannot — genuinely unknown, flagged rather than assumed either way, and
  cheap to test (the same Test 1/Test 2 methodology, re-run at 12.6mm)
  before committing to the "PD3 requires part substitution and a large
  re-layout" reading this plan otherwise adopts from the straight-corridor
  evidence alone.

## Sources / Research

- `docs/evidence/2026-08-11-stage4-placement-congestion-spike.md` — the
  routing-congestion investigation naming the missing wirelength objective
  as the root cause (§6 option 4) and its own cost/risk framing, reused
  directly.
- `docs/evidence/2026-08-07-placement-clustering-feasibility.md` — the
  primary source for §0/§1/§2's "no clustering objective exists, and it is
  not merely disabled" finding, the 89%-free-component measurement, and the
  HV/SELV safety-interaction discussion (§5) this plan's D1/U1 build on.
- `docs/evidence/2026-08-11-creepage-gatedrivehv-false-positive.md` — the
  current 169–171 residual-creepage figure, the same-side false-positive
  fix, and the explicit "systemic, board-wide placement/routing
  interleaving problem, not a handful of repeat offenders" finding this
  plan's §0/§2 rely on.
- `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md` — the open
  PD2-vs-PD3 owner decision this plan designs around (D3) but does not
  resolve; the 8-point enforcement-tree alignment table.
- `docs/evidence/2026-08-04-isolation-barrier-freeform-corridor.md`
  (PR #690) and `docs/evidence/2026-08-04-r24-barrier-resolve.md` — the
  Test 1/Test 2 methodology, the 87.4%-as-routed vs. 3.6%-as-placed
  distinction (§0's central correction), and the `R24` fix that made
  8.0mm-barrier admissibility real on the committed board.
- `docs/evidence/2026-07-30-pd3-inter-component-creepage-board-expansion.md`
  and `docs/evidence/2026-07-30-pd3-board-expansion-measurement.md` — the
  12.6mm feasibility data (196 pairs, 89% board-growth-recoverable
  inter-component share, structurally-invariant isolator population,
  reduced-set UNSAT) behind §2/D3's PD3 verdict.
- `docs/evidence/2026-08-08-selv-hv-pour-barrier-drc-spike.md` — third
  independent corroboration of "no straight line separates HV/SELV," cited
  by the GateDriveHV doc.
- `docs/evidence/2026-08-07-cpsat-objective-frequency.md` — the real
  production timeout budget (180,000ms/round) this plan's D4/U1 size
  against, and the objective-posting-frequency census informing D6.
- `docs/evidence/2026-08-07-sat-model-reduction-options.md` — background on
  the *router's* (not placer's) SAT model-size problem; cited for context
  in Scope Boundaries' orthogonality note, not otherwise load-bearing here.
- `docs/plans/2026-07-28-001-feat-provable-safety-place-and-route-plan.md`
  — read in full per this task's instruction; its U1-U3 (landed) are U3's
  dependency; its U4-U6 (unstarted) are explicitly out of this plan's
  scope. Not duplicated: it owns router refusal/pour-derivation
  architecture generally, this plan owns the placement-side objective and
  barrier constraint specifically.
- `docs/plans/2026-08-07-003-feat-routing-block-decomposition-plan.md` —
  read in full per this task's instruction; orthogonal (router Stage-3 SAT
  partitioning), corroborates the "board isn't clustered" finding via an
  independent bounding-box measurement, not duplicated here.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/model.py`,
  `_encoder_solve.py`, `_loop_core.py`, `isolation_barrier.py`,
  `domain_clearance.py` — the live code this plan's §0/§1 verify directly
  (not trusted from any prior summary).
- `packages/temper-placer/src/temper_placer/core/isolation_constants.py`
  (`MIN_BARRIER_WIDTH_MM = 8.0`) — the single source `corridor_width_mm`
  should continue to derive from (D2/D3).
- This task's own synthetic tractability measurement (§3;
  `synth_wirelength_barrier_test2.py`, not committed — reproducible from
  this document's own inline script description) — the only new empirical
  data point this plan contributes: HPWL + directional-barrier CP-SAT
  models build in ~0.01s and find a 4×-improved feasible solution within
  45s at ~150-component/~110-net scale, but do not approach a proven
  optimum in that budget (flat bound, ~78-95% gap), which is why D4 targets
  "materially improved," not "optimal."
