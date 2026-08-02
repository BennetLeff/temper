# Wave-4 Phase 1 spike: ortools CP-SAT boundary — feature enumeration, Rust-candidate survey, verdict (2026-08-01)

<!-- provenance: commit=37a4251e03f3b483ea6345d19a8f7ba5e8bf0c4c dirty=false (base=origin/main 37a4251e03f3b483ea6345d19a8f7ba5e8bf0c4c; worktree ../w4-spike, branch w4/ortools-spike; asserted with scripts/assert-base.sh) -->

**Date:** 2026-08-01
**Scope:** read-only analysis of
`packages/temper-placer/src/temper_placer/placer/cp_sat/` (all of it) plus
the ortools call sites in `_encoder_solve.py`, `unsat.py`, `cli/__init__.py`,
and the `placer/` orchestration that consumes `solve_placement`. No code was
changed; this is a decision-gate spike (Wave-4 plan R4/R6, Phase 1).

**Verdict: KEEP the ortools CP-SAT engine and the Python solve boundary,
with a version-locked solve contract, a KTD9-style measured parity
contract, and the R24 post-solve audit enforced across the boundary.**
The plan's "no mature Rust drop-in" claim is **verified** for a
pure-Rust engine, with one important refinement: two Rust *FFI bindings to
the same ortools engine* exist (`cp_sat` 0.4.1, `cpsat-rs` 0.1.2) and are
the only path that could ever satisfy the repo's R1a bit-identical bar —
but both are too immature to pin as the production boundary today. WRAP
(Rust boundary, ortools engine via FFI) is recorded as the named
re-decidable path with concrete triggers. REPLACE (different solver
engine) is rejected: bit-identical parity across solver engines cannot
be guaranteed or asserted as a gate (R1a's bit-exact bar is only
assertable same-engine; a different engine's heuristic search may
coincidentally find identical output, but that is empirical, not
constructive — the honest claim is that the *gate* is unassertable
across engines, not that identical output is impossible).

---

## 1. Feature enumeration (the load-bearing artifact)

The complete CP-SAT API surface used by the placer, code-grounded. Two
files own the model construction (`model.py` = primitive layer,
`handlers/` = PCL-constraint encoders); `_encoder_solve.py` owns the solve
call; `unsat.py` owns assumption-based core extraction; `audit.py` owns the
R24 post-solve audit (geometry only, already Rust-backed via temper-geometry).

### 1.1 Model types / variables

| # | Type | Domain / form | Where | Encodes | Load |
|---|---|---|---|---|---|
| M1 | `BoolVar` (`NewBoolVar`) | {0,1} | `model.py:382` (assumption literals), `model.py:518`; direction/axis Booleans `handlers/separated.py:95-107` | assumption literals for UNSAT-core extraction; per-pair axis-separation flags | 3 |
| M2 | `IntVar` position | [0, 1_000_000] | `model.py:147-152` (x/y_center, x/y_start, x/y_end) | component bounding-box geometry in integer grid units (units_per_mm=100) | 2 |
| M3 | `IntVar` size | [min_dim, max_dim] (both orientations) | `model.py:145-146` | footprint w/h; rotation selects active size | 2 |
| M4 | `IntVar` rotation | [0, 3] | `model.py:202` | 4-way axis-aligned rotation quadrant | 2 |
| M5 | `IntVar` diff helper | [-max_diff, max_diff] | `model.py:419` | |a-b| helper for abs-diff bound | 1 |
| M6 | `IntVar` displacement | [0, 1_000_000] | `model.py:333-335` | per-axis |x-target| for min-displacement objective | 1 |
| M7 | `IntVar` loop AABB | [0, max_dim] / [0, max_dim²] | `handlers/loop_area.py:47-50, 59-68` | loop bounding box + area (product) | 2 |
| M8 | `NewConstant` | constants | `model.py:195` (polarized rot=0), `model.py:257-264` (keepout rect) | pinned rotation, fixed keepout geometry | 1 |
| M9 | `IntervalVar` (`NewIntervalVar`) | start/size/end triples | `model.py:229-230` (per component), `model.py:260-265` (keepout), `handlers/keepout.py:62-72` | component / keepout rectangles feeding NoOverlap2D | 2 |
| M10 | Forced literals (`OnlyEnforceIf`) | BoolVar guard | `model.py:398` (helper), used by every handler, `model.py:504-507` (set_bounds), `isolation_barrier.py:564,574,624-625` | assumption-guarded constraints — the core soft/fail-closed mechanism | 3 |

### 1.2 Constraint classes

| # | Constraint | Where | Encodes | Load |
|---|---|---|---|---|
| C1 | Linear equality `Add(a + b == c)` | `model.py:155-156` (midpoint `x_start+x_end == 2*x_center`), `model.py:159-160` (interval consistency `start+size == end`), `model.py:369` (rotation pin), `_encoder_solve.py:315-318` (fixed position pins), `isolation_barrier.py:597` (isolator rot pin), `handlers/loop_area.py:61-62` (loop w/h) | geometry invariants, hard pins | 2 |
| C2 | Linear inequality `Add(expr <= c)` | `model.py:342` (displacement bound), `model.py:416-417` (abs-diff), `handlers/loop_area.py:54-57` (AABB bounds) | bounds | 1 |
| C3 | Reified linear (`OnlyEnforceIf`) | every handler: `separated.py:100-103`, `adjacent.py:54-62`, `aligned.py:46-47`, `anchored.py:39-50`, `enclosing.py:48-63`, `onside.py:40-46`, `loop_area.py:71`, `model.py:504-507`, `isolation_barrier.py:564,574,624-625` | assumption-guarded Chebyshev clearance, alignment, anchoring, zones, edges, isolation barrier | 3 |
| C4 | `AddBoolOr` (clauses, with `.Not()`) | `handlers/separated.py:109-113` | Chebyshev separation disjunction (x_ok ∨ y_ok); axis Booleans | 1 |
| C5 | `AddElement` (table) | `model.py:205-206` | rotation → size selection ([w0,h0,w0,h0] tables) | 2 |
| C6 | `AddNoOverlap2D` (interval disjunctive scheduling) | `model.py:237` (global, all comps + keepouts), `handlers/keepout.py:59-74` (keepout vs all comps) | rectangle non-overlap; keepout exclusion | 2 |
| C7 | `AddMultiplicationEquality(target, [a,b])` | `model.py:406` (helper), `handlers/loop_area.py:69` | loop AABB area (width × height) — the only nonlinear product | 2 |
| C8 | `AddAbsEquality` | `model.py:336` | per-axis displacement distance for the min-displacement objective | 1 |
| C9 | `AddAssumption` / `AddAssumptions` / `ClearAssumptions` | `model.py:383`, `unsat.py:297-300` | assumption literals for core extraction; MUS refinement re-solves | 3 |
| C10 | `AddHint` | `_encoder_solve.py:267-270` | warm-start search from deterministic-pipeline / current-board positions | 3 |
| C11 | `Minimize(Σ var·weight)` (linear objective) | `model.py:288-291`, terms at `model.py:275-277`, displacement terms `model.py:337` | min-Manhattan-displacement repair objective (issue #504); no wirelength objective is actually encoded — `_loop_core.py:884-913` "Phase 2 polish" is a longer-timeout (5s) re-solve with no objective | 2 |
| C12 | `SufficientAssumptionsForInfeasibility` | `model.py:458`, `_encoder_solve.py:431`, `unsat.py:133` | solver-native sufficient unsat core — NOT reproducible by a different engine without reimplementing the search | 3 |
| C13 | Proto serialize/clone (`model.Proto()`, `copy_from`) | `unsat.py:264-268` | model cloning for MUS refinement re-solves | 1 |

### 1.3 Solver parameters / result accessors

| Param | Value(s) | Where |
|---|---|---|
| `max_time_in_seconds` | 10.0 (`model.py:435`), timeout_ms/1000 (`_encoder_solve.py:391`), 5.0/60.0 (unsat re-solves, `unsat.py:277`) | both solve paths |
| `num_search_workers` | 8 (`model.py:436`), 4 (`_encoder_solve.py:393`) | determinism-relevant |
| `random_seed` | 0 (default; `_encoder_solve.py:392`) | determinism-relevant |
| `log_search_progress` | False (`_encoder_solve.py:394`, `unsat.py:276`) | |
| accessors | `Value`, `ObjectiveValue`, `WallTime` (`model.py:444-467`, `_encoder_solve.py:418-426`) | result extraction |

### 1.4 PCL constraint types → handlers (8/8 covered)

ADJACENT (`adjacent.py:20`), SEPARATED (`separated.py:20`), ENCLOSING
(`enclosing.py:20`), KEEPOUT (`keepout.py:20`), ALIGNED (`aligned.py:20`),
ON_SIDE (`onside.py:20`), ANCHORED (`anchored.py:20`), LOOP_AREA
(`loop_area.py:20`). Dispatch via `HANDLER_REGISTRY`
(`handlers/_registry.py:11`), constraint generation upstream in
`netclass_constraints.py` (cross-class SEPARATED auto-gen) and
`_encoder_core.py:165-209` (courtyard-τ SEPARATED auto-gen, all pairs).
`domain_clearance.py` and `isolation_barrier.py` generate their own
constraints (isolation barrier encodes directly, `isolation_barrier.py:557-625`).

**Not used** (relevant to candidate coverage): `AddAllDifferent`,
`AddExactlyOne`, `AddCircuit`, `AddCumulative`, `AddAllowedAssignments`,
`AddAutomaton`, `AddInverse`, `AddMin/MaxEquality`, `AddModulo`,
`AddDivision`, optional intervals, `DecisionStrategy` search hints,
`Maximize`.

**Enumeration tally: 13 constraint classes (C1-C13), 10 model-type rows
(M1-M10), 4 solver parameters, 8 PCL handler types.** This is the surface
Phase B contracts must refine.

### 1.5 Honest uncertainty

- The `AddNoOverlap2D` global (`C6`) is *redundant* for correctness — the
  per-pair SEPARATED Chebyshev disjunction (`C3+C4`) already enforces
  pairwise clearance — but it is kept as a strong propagator
  (`_encoder_solve.py:236-238` comment: "redundant global for
  propagation"). Removing it is a solve-quality change, not a semantics
  change.
- The unsat-core surface splits into a **portable** half (MUS refinement
  via repeated assumption re-solves, `unsat.py:160-288`) and a
  **solver-native** half (`SufficientAssumptionsForInfeasibility`, C12).
  Any replacement engine with assumption support can host the MUS half;
  the sufficient-core half must be reimplemented.

---

## 2. Candidate evaluation (current as of 2026-08-01)

Researched via crates.io/GitHub/docs.rs, current through July 2026.
Maturity claims cite the newest release observed; anything not documented
in the crate's own surface is marked **needs-verification** rather than
asserted.

| Candidate | Maturity (2025-26) | Native constraint support (of C1-C13) | Re-encoding needed | Posture | Effort to bit-identical parity (R1a) |
|---|---|---|---|---|---|
| **rustsat** 0.8.0 (2025-10-18) / 0.7.5 (2026-01-30) — version anomaly noted (0.8.0 predates 0.7.5's date; possibly a backported patch release, unverified) | Active, 158 releases, MIT, MSRV 1.76+ | C1/C2 linear (as PB), C3 reified (implications), C4 clauses, C9 assumptions (SAT-native), C11 objective (MaxSAT). NOT native: C5 element, C6 no-overlap-2D, C7 product | Everything to CNF: element → table encoding, no-overlap-2D → pairwise disjunctions, product → sequential encoding (expensive) | natively compiled SAT; CNF blowup risk on C7 | **Unreachable** — different solver, different search; parity must be redefined (see §4) |
| **Pumpkin** (pure Rust, ConSol-Lab TU Delft) | Active; CP'24 paper; DRCP unsat-certificate proof logging | C1/C2 linear, C3 (reification not documented — **needs-verification**), C5 element ✓, C7 multiplication ✓ (integer_multiplication), C8 abs ✓, C4 clausal ✓, disjunctive ✓, cumulative ✓. No no_overlap_2d propagator | no-overlap-2D → disjunctive encoding | pure Rust LCG; proof certificates are a genuine soundness asset | **Unreachable** |
| **aries-solver** 0.6.0 | Small community; ECAI'23 paper; scheduling-focused | linear, max, no-overlap (1D), difference-logic; element/product/2D-not documented — **needs-verification** | most of C5-C7 | pure Rust | **Unreachable** |
| **huub** v100.1.0 (2026-06-01) | New (odd versioning; 2023-2026); MiniZinc/flatzinc support | CP+SAT framework, extensible propagators; exact global-constraint coverage **needs-verification** | likely most of C5-C7 | pure Rust | **Unreachable** |
| **good_lp 1.15.2 (2026-05-31) + HiGHS 2.0 / CBC** | Mature, 3.7M downloads | C1/C2 linear ✓, C11 objective ✓, C4 as Σ≥1 ✓. NOT native: C3 reification (big-M), C5 element (big-M), C6 no-overlap-2D (disjunctive big-M), C7 product (linearization), C8 abs (aux vars), C9/C12 assumptions & cores (**absent — core extraction must be dropped**) | full model-class change MIP | C++ engines via FFI (HiGHS, CBC) | **Unreachable** + unsat-core feature loss |
| **cp_sat crate** (KardinalAI) 0.4.1 (2026-07-08) | Revived 2026 after 2021; **0 dependents**; needs system or-tools + C++ + protobuf | C1-C13 **by construction** — it is Rust bindings to the same ortools engine (prost proto + FFI); exposes validate_cp_model, solution_is_feasible | none (same engine) | FFI to ortools | **Achievable in principle** — same engine ⇒ same deterministic output for pinned version + seed |
| **cpsat-rs** (moorbrook) 0.1.2 (2026-04-03) | **0.1.x, 198 downloads, 0 dependents**; proto vendored from ortools **9.15** (matches repo pin) | C1-C13 by construction: linear, all_different, no_overlap(_2d), cumulative, circuit, table, automaton, element, boolean, hints, params | none (same engine) | FFI to ortools C API (`SolveCpModelWithParameters`) | **Achievable in principle** (same reasoning) |

**Headline facts.** (1) No pure-Rust engine covers C5-C7 (element, 2D
no-overlap, product) with competitive propagators — the plan's "no mature
Rust drop-in" claim **holds for pure-Rust engines**. (2) The only Rust
paths that can meet R1a's bit-identical bar are FFI bindings to the same
ortools engine (`cp_sat`, `cpsat-rs`); both are far below the repo's
production bar (0 dependents, 0.1.x, external system-library requirements
— the same class of dependency risk that rejected the `edt` crate in
KTD8). (3) Any different engine (rustsat/Pumpkin/aries/huub/HiGHS)
changes the search, so bit-identical outputs are unreachable regardless of
implementation quality.

---

## 3. Verdict + acceptance criteria (R4 gate)

### Verdict: **KEEP** (with justification)

**Named blocker (R3/R4):** no mature pure-Rust CP-SAT engine implements
the required propagator surface (C5 element, C6 2D no-overlap, C7
product, C12 assumption cores) at competitive search quality; the two Rust
FFI bindings to the same engine are too immature to pin as the production
boundary today (`cp_sat` 0.4.1: 0 dependents, revived after a 4-year gap,
requires system or-tools/libprotobuf; `cpsat-rs` 0.1.2: 198 downloads,
0.1.x). REPLACE across a different engine additionally fails R1a:
bit-identical outputs on identical inputs are unreachable across solver
engines by construction (heuristic search), so REPLACE would require
amending R1a to semantic parity — an R4/R1 contract change that needs
product authority, not a spike.

**KEEP acceptance criteria (what "done" means for this verdict):**
1. A **version-locked solve contract**: `ortools==9.15.6755` (already
   pinned in `uv.lock`; `pyproject.toml:28` requires >=9.12 — tighten to
   `==9.15.6755` or a `~=` floor that cannot float past the measured
   version), with solver parameters frozen: `max_time_in_seconds`
   (10.0 / caller timeout), `num_search_workers` (8 in `model.py`, 4 in
   `_encoder_solve.py` — freeze both call sites), `random_seed` (0),
   `log_search_progress=False`.
2. A **KTD9-style measured parity contract**: before any future solver
   change (version bump, param change, WRAP), record the corpus solve
   output (positions/rotations/status/objective for the canonical board
   corpus at the frozen params) and assert bit-identical re-solve — the
   same pattern as the KTD9 `~5e-13` recorded tolerance. Tolerance is
   **exactly 0 only for deterministic-completed solves** (status
   `OPTIMAL`/`INFEASIBLE`/`FEASIBLE` with deterministic termination);
   solves that hit the wall-clock `max_time_in_seconds` cutoffs
   (`model.py:435`, `_encoder_solve.py:391`, `unsat.py:277`) terminate
   non-deterministically across machines/load, so timeout-terminated
   corpus solves are recorded with a measured baseline (KTD9-style) and
   asserted to it — never to an unconditional bit-identical claim.
3. The **R24 post-solve audit holds across the boundary**: `audit.py`
   (already Rust-backed via temper-geometry) remains wired after every
   solve (`placer/cp_sat/audit.py`), enforcing the Chebyshev soundness
   checks independently of the solver's own feasibility claim.
4. The blocker is recorded under R3 in the plan (this doc + Phase-1
   amendment carry it).

**WRAP (re-decidable path, recorded trigger):** if `cpsat-rs` reaches 1.x
with broad adoption, or Phase 4 pulls the solve-boundary migration, the
WRAP shape is: Rust model builder → `CpModelProto` (prost) → ortools C
API (`SolveCpModelWithParameters`) — the pattern `cpsat-rs` proves,
vendored to the pinned 9.15 proto. WRAP acceptance: a working Rust solver
boundary passing the R1 gate set on a representative board corpus with
bit-identical parity vs the Python path on identical inputs (same engine ⇒
achievable), `validate_cp_model`/`solution_is_feasible` asserted at the
boundary, R24 audit enforced at the boundary. WRAP keeps the engine —
it is a boundary migration, not a solver replacement, so it does not
require redefining R1a.

**REPLACE (rejected, with the condition that would reopen it):** a
pure-Rust engine could only be adopted if (a) one of rustsat/Pumpkin/
huub/aries gains the full C5-C7+C12 surface with competitive
performance, AND (b) R1a is amended to semantic parity (feasibility +
objective equivalence + R24 audit across the corpus) by product authority.
Neither holds today; (b) is explicitly out of this spike's scope.

**Honest uncertainty:** adoption counts for Pumpkin/huub/aries were not
fully enumerated; their *feature* coverage is documented above but their
search-quality equivalence to ortools on this board class is unmeasured —
any future REPLACE attempt must start with a corpus benchmark, per KTD8's
precedent (third-party geometry library diverging from the reference).

---

## 4. KEEP contract (what is concretely pinned)

- **Engine**: ortools CP-SAT, version `==9.15.6755` (uv.lock today;
  pyproject floor tightened).
- **Params**: the four frozen values in §3.1, at both call sites
  (`model.py:434-436`, `_encoder_solve.py:390-394`), plus
  `unsat.py` re-solve timeouts (5s → 60s doubling).
- **Parity**: KTD9-style measurement, tolerance 0 (bit-identical
  re-solve on the board corpus at frozen params), re-run on any solver
  change.
- **Soundness**: R24 post-solve audit (`audit.py`, Rust-backed) enforced
  after every solve; the Chebyshev SEPARATED encoding's soundness proof is
  recorded in `handlers/separated.py:50-53` and the Rust
  `temper-constraints` encoder arithmetic is pinned by
  `test_encoder_rust_differential.py`.
- **Unsat cores**: `unsat.py` stays the owner; the MUS half is portable,
  the sufficient-core half is engine-native (documented in §1.5).

## 5. Test state

No harness was built for this spike (decision-gate only — the pattern
matching KTD8/KTD9, whose harnesses were removed with the crates). The
existing suite pins the boundary behavior: `test_encoder_rust_differential.py`,
`test_audit_rust_differential.py`, `test_audit_pbt.py`, and the
`tests/placer/cp_sat/` suite (30+ files) are the corpus for the KEEP
parity contract. The verdict is recorded here and in the Wave-4 plan's
Phase-1 section (see the plan amendment commit); Phase B contracts will
refine the §1 enumeration.
