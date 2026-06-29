---
date: 2026-06-28
topic: net-bundling-lazy-grounding
---

# Hierarchical Net Bundling with Type-Gated Lazy Grounding

## Summary

Pre-partition nets into bundle equivalence classes sharing the same constraint-type signature and geometric neighborhood. Encode safety constraints eagerly per bundle class, ground performance constraints lazily during CDCL search via homomorphism, and skip aesthetic constraints entirely. Reduces the routing SAT model from O(n·|E|) variables to O(b·|E| + n) where b ≪ n is the number of bundle classes.

---

## Problem Frame

The current `ModelBuilder` (`constraint_model.py:176-185`) creates one `NetChannelVar` per (net × skeleton edge) and one `ViaVar` per (net × skeleton node) for every net that passes the `target_net_names` filter. On the Temper PCB (23 nets, 2 signal layers, ~6,000 skeleton edges) this produces ~228K variables — ~138K NetChannelVars + ~85K ViaVars. Even with `max_sat_nets` gating to the 3 simplest nets, the model is 29K variables, and splr 0.13 panics at M=6+ nets (`docs/solutions/performance-issues/sat-model-too-large-for-splr-selective-construction-2026-06-28.md:34`).

The `max_sat_nets` lever solves the problem coarsely — it excludes nets from SAT entirely. Nets above the cutoff get no channel assignment from the topology stage and must rely on direct A* routing with no capacity-coordination guarantees. This is adequate for a handful of critical nets but does not scale to boards where every net benefits from SAT-coordinated channel allocation.

The root cause is that the current encoding treats every net as an independent variable-generator. However, many nets are *substitutionally equivalent* for constraint purposes — two signal nets of the same width in the same geometric region contribute identically to capacity constraints and differ only in which specific pins they connect. Encoding one capacity constraint per bundle class and instantiating per-net variables only when needed would collapse the O(n·|E|) variable space to O(b·|E|) with b bundle classes.

---

## Actors

- **A1. ModelBuilder** (`constraint_model.py:153-363`): Consumes the netlist, channel skeletons, and design rules; currently builds all SAT variables and constraints eagerly in one pass.
- **A2. SAT Solver (splr 0.13)** (`solver.rs:19-100`): Receives a CNF formula (all variables + all clauses up front), runs CDCL search, returns SAT/UNSAT with model. splr's `SatSolverIF` trait supports `add_var()` and `add_clause()` calls but only *before* `solve()` — there is no callback API exposed for adding clauses mid-search (`~/.cargo/registry/.../splr-0.13.0/src/solver/build.rs:20-96`, `src/solver/search.rs:19-27`).
- **A3. Pipeline Orchestrator** (`pipeline.py:319-382, 585-603`): Decides via `max_sat_nets` / `_select_sat_nets` which nets enter SAT routing. Currently a binary filter — nets are either fully in or fully out.
- **A4. Bundle Analyzer** (new component): Pre-solve pass that partitions nets into equivalence classes based on constraint-type signature and geometric neighborhood. Produces a mapping `bundle_class_id → [net_idx, ...]` and a per-class constraint template.
- **A5. Lazy-Clause Provider** (new component): Interface between the SAT solver and the constraint model that instantiates per-net clauses on demand when a bundle-class variable assignment makes a constraint violation concretely possible.

---

## Key Flows

### F1. Bundle Analysis Pass (Pre-Solve)

- **Trigger:** `ModelBuilder.build()` is called with nets and skeletons.
- **Actors:** A4 (Bundle Analyzer), A1 (ModelBuilder)
- **Steps:**
  1. For each net, compute a *constraint-type signature*: a tuple of (net_class, trace_width, clearance, has_diff_pair, pin_layer_set). Net class is resolved via `net_classification.py:75-87` (ground / power / hv / signal). **Mapping:** Until `safety_category` is added to `stage0_data.py`'s `NetClassRules`, the fallback mapping from the net-name-based classification to Safety/Performance/Aesthetic tiers is: `hv` → Safety, `power` → Performance, `ground` → Safety, `signal` → Performance.
  2. For each net, compute a *geometric footprint*: the convex hull of its pin positions plus a margin equal to the channel graph's median edge length.
  3. Partition nets into equivalence classes where two nets are in the same class iff they share the same type signature AND their geometric footprints overlap sufficiently (Jaccard index > 0.5 on the set of skeleton edges covered).
  4. For each class, identify which constraint types apply: Safety (HV/LV isolation, layer restrictions), Performance (diff-pair skew), Aesthetic (length-matching guidance).
  5. Produce a `BundleManifest`: `{bundle_id: {net_indices: [int, ...], type_signature: Tuple[...], geometric_footprint: Polygon, constraint_types: Set[ConstraintType]}}`
- **Outcome:** A `BundleManifest` that gates which constraints are encoded eagerly vs lazily vs never.
- **Covered by:** R1, R2

### F2. Eager Safety Constraint Encoding (Pre-Solve)

- **Trigger:** After F1, before solver invocation.
- **Actors:** A1 (ModelBuilder), A2 (SAT Solver via `add_var`/`add_clause`)
- **Steps:**
  1. For each bundle class with Safety constraint types, create one *class variable* per skeleton edge instead of one per net.
  2. Instantiate capacity constraints as AtMostK over class variables where K = floor(channel_capacity / net_width) — this is identical to the current encoding but with b class variables instead of n net variables.
  3. Encode layer restrictions as unit clauses on class variables.
  4. Add all safety clauses to the solver via `add_clause()` (as currently done at `solver.rs:42-47`).
- **Outcome:** The solver starts with a safety-grounded CNF containing b·|E| variables (class-level) instead of n·|E| variables (net-level). This is the O(b·|E|) term in the complexity bound.
- **Covered by:** R3, R4, R5

### F3. Lazy Performance Constraint Grounding via CEGAR Loop

- **Trigger:** The safety CNF returns SAT; the resulting full assignment contains a Performance constraint violation.
- **Actors:** A2 (SAT Solver), A5 (Lazy-Clause Provider)
- **Steps:**
  1. Solve the safety-grounded CNF (class variables only) via `solve()`.
  2. Inspect the full solution for Performance constraint violations (e.g., both members of a diff pair assigned to different channels, capacity overrun on a signal-only channel).
  3. If a violation is found: instantiate per-net variables for the affected nets and add the violated Performance clauses as blocking clauses via `add_var()` + `add_clause()`.
  4. Re-solve (new `solve()` invocation) with the additional clauses.
  5. Iterate until either a violation-free solution is found (SAT) or the safety CNF itself becomes UNSAT under the accumulated blocking clauses.
- **Outcome:** Performance constraints are only grounded when a concrete violation is found in a full solution — not eagerly for all nets × all channels. This is the O(n) term in the complexity bound: per-net variables are only created for nets that appear in actual violations.
- **Covered by:** R6, R7, R8, R9

**Note:** KD4: The watchdog runs between `solve()` calls, not during CDCL search. This is CEGAR (counterexample-guided abstraction refinement), not fine-grained lazy clause generation.

### F4. Aesthetic Constraints (Never Grounded)

- **Trigger:** N/A — these constraints are *not* added to the SAT solver.
- **Actors:** A1 (ModelBuilder — marks as aesthetic), A3 (Pipeline Orchestrator — provides soft guidance downstream)
- **Steps:**
  1. During F1, constraints typed as Aesthetic (length-matching preferences, color-guide hints) are recorded in the `BundleManifest` but never lowered to SAT clauses.
  2. After SAT solving, the post-processing stage (`extraction.rs`) reads the bundle manifest and applies aesthetic preferences as a refinement step on the solver's channel assignments (e.g., picking the shorter of two equidistant channels for a length-matched bus).
- **Outcome:** Aesthetic preferences never inflate the SAT variable/clause count. They are applied as a cheap post-processing refinement.
- **Covered by:** R10

---

## Requirements

### Core Bundle Partitioning

- **R1 (Bundle equivalence):** The bundle analyzer shall partition nets into equivalence classes such that two nets are in the same class iff they have identical `(net_class, trace_width, clearance, has_diff_pair, pin_layer_set)` tuples AND their geometric footprints (convex hull of pin positions expanded by median channel edge length) overlap on >50% of skeleton edges by Jaccard index.

- **R2 (Bundle manifest):** The bundle analyzer shall produce a `BundleManifest` data structure containing for each bundle class: `net_indices`, `type_signature`, `geometric_footprint`, and a `constraint_types` set enumerating which of {Safety, Performance, Aesthetic} apply.

- **R2.1 (Determinism):** Bundle partitioning shall be deterministic — given identical nets and skeletons, the same bundle classes shall be produced. Sort order shall be by bundle_id (lexicographic on first net name) to ensure reproducibility.

### Type-Gating Policy

- **R3 (Safety constraints — eager):** All constraints classified as Safety shall be fully grounded as SAT clauses before the solver begins CDCL search. Safety constraints include: HV/LV isolation (capacity constraints on channels adjacent to HV nets), layer restrictions (SMD pin layer assignment), and minimum clearance for safety-critical net pairs as identified by `safety_pair_inference.py`.

- **R4 (Performance constraints — lazy):** All constraints classified as Performance shall be grounded lazily during CDCL search, only when the partial assignment makes a violation concretely possible. Performance constraints include: differential pair skew (both members of a diff pair assigned to different channels), impedance-controlled length matching, and signal-integrity ordering.

- **R5 (Aesthetic constraints — never):** Constraints classified as Aesthetic shall never be lowered to SAT clauses. They shall be recorded in the `BundleManifest` for post-processing refinement of the solved topology.

- **R5.1 (Constraint classification resolution):** The classification of each constraint as Safety/Performance/Aesthetic shall be determined by a configurable mapping from constraint kind → gating tier, defaulting to: `CapacityConstraint` on channels touching HV nets → Safety; `CapacityConstraint` on signal-only channels → Performance; `DiffPairConstraint` → Performance; `LayerConstraint` → Safety.

### Lazy Clause Callback Interface

- **R6 (Lazy addition API):** The SAT solver interface shall support adding variables and clauses after the initial solve has begun. At minimum: `add_var_lazy(name: str) → var_idx` and `add_clause_lazy(literals: [i32]) → Result<(), Error>` callable between incremental `solve()` invocations.

- **R7 (Violation-concrete trigger):** The lazy grounding watchdog shall add Performance clauses when — and only when — a partial assignment to class-level variables, when mapped through the bundle-to-net homomorphism, makes it concretely possible that at least one Performance constraint is violated. "Concretely possible" means: the current partial assignment is compatible with a violation (i.e., the constraint's guard condition is met in the partial assignment).

- **R7.1 (Early termination guard):** The lazy grounding watchdog SHALL impose a budget limit on per-net variable instantiation per CEGAR iteration. The budget formula SHALL be M × |bundle_nets| where M is an empirically calibrated multiplier (initial value: 10, recalibrated in the first integration sprint).

- **R7.2 (Budget exhaustion degradation):** When the watchdog's instantiation budget is exhausted before all Performance constraints are grounded, nets with ungrounded Performance constraints SHALL be routed via the existing A* fallback (same degradation path as nets excluded by `max_sat_nets`).

### Homomorphism Instantiation

- **R8 (Homomorphism correctness):** For non-diff-pair bundles, the homomorphism mapping class-variable `uses[B, channel_id]` to per-net-variable `uses[net_i, channel_id]` shall preserve constraint semantics: every satisfying assignment of the per-net encoding, when projected through the homomorphism, shall satisfy the class-level encoding; and every satisfying assignment of the class-level encoding shall be extendable (by assigning per-net variables) to a satisfying assignment of the full encoding. For diff-pair bundles, the homomorphism SHALL be extended to handle paired-variable instantiation (both members of a diff pair are instantiated together). Until OQ-D3 is resolved, diff-pair nets SHALL be placed in their own dedicated 2-net bundle classes.

- **R8.1 (Inverse mapping for extraction):** After SAT solving, the topology extractor (`extraction.rs:9-94`) shall use the inverse homomorphism to map class-variable assignments back to per-net channel assignments for all nets in the bundle.

### Integration with Existing ModelBuilder

- **R9 (Backward compatibility):** The `ModelBuilder.build()` API shall be unchanged. An optional `enable_bundling: bool = False` parameter shall gate the new bundle path. When `False`, the current eager-all-variables behavior is preserved unmodified. The existing `target_net_names` parameter shall continue to work regardless of bundling mode.

- **R9.1 (Constraint audit integration):** The existing constraint audit (`audit.rs:39-129`) shall validate bundled SAT results against the expanded (fully grounded) constraint set. Audit violations shall report in terms of per-net variable names even when the solver operated on class-level variables. The audit SHALL be provided with both the original bundled model AND the fully-grounded expanded model (expansion performed by the bundle analyzer before solver invocation).

### Correctness Guarantees

- **R10 (Bundled-vs-unbundled equivalence):** For any constraint set C where all constraints are of type Safety (eagerly grounded), the bundled encoding shall produce bit-identical SAT/UNSAT results to the unbundled (current) encoding. For constraint sets containing Performance constraints, the bundled encoding shall produce results that satisfy all Safety constraints identically and all Performance constraints equivalently (modulo the variable-naming difference from homomorphism projection).

- **R10.1 (Soundness):** If the bundled encoding returns SAT, every safety constraint in the original model is satisfied by the extracted per-net assignments (post-homomorphism).

- **R10.2 (Completeness):** If a satisfying per-net assignment exists, the bundled encoding with full lazy grounding shall return SAT.

---

## Acceptance Examples

### AE1. Two Identical Signal Nets in the Same Channel

**Setup:** Two signal nets (SIG_A, SIG_B) with identical trace widths (0.2 mm), both 2-pin nets, both routed in the same 10 mm × 10 mm region. The channel CH1 has capacity 1.0 mm (i.e., room for 2 nets at 0.2 mm width + 0.2 mm clearance = 0.4 mm each).

**Bundle behavior:** SIG_A and SIG_B fall into the same bundle class B1 (identical type signature, overlapping geometric footprints). The capacity constraint for CH1 is encoded once as `uses[B1, CH1] ≤ 2` (class-level AtMostK) instead of `uses[SIG_A, CH1] + uses[SIG_B, CH1] ≤ 2`. The constraint is identical — only the variable name changes.

**Expected outcome:** The bundled encoding produces the same SAT/UNSAT result as the unbundled encoding. After extraction, both nets get channel assignments (or both do not). Variable count drops by 50% per channel (1 class var vs 2 net vars).

### AE2. Diff Pair Bundles with Lazy Skew Clause

**Setup:** A differential pair (USB_DP, USB_DN) sharing the same type signature. CH1 and CH2 are two possible routing channels. The Safety encoding (capacity for CH1, CH2) grounds eagerly with one class variable per channel. The Performance constraint (USB_DP ↔ USB_DN equivalence: both must use the same channel) is lazily grounded.

**Bundle behavior:** USB_DP and USB_DN form a single bundle class B_USB. The Safety encoding adds `uses[B_USB, CH1] ≤ K1` and `uses[B_USB, CH2] ≤ K2` eagerly. The watchdog observes the partial assignment. When the solver tentatively assigns `uses[B_USB, CH1] = true` and `uses[B_USB, CH2] = true`, the watchdog detects this enables a possible violation (the pair could be split across channels). It instantiates per-net variables `uses[USB_DP, CH1]`, `uses[USB_DP, CH2]`, `uses[USB_DN, CH1]`, `uses[USB_DN, CH2]` and adds the equivalence clause `(uses[USB_DP, CH1] ↔ uses[USB_DN, CH1]) ∧ (uses[USB_DP, CH2] ↔ uses[USB_DN, CH2])` lazily.

**Expected outcome:** The diff pair equivalence constraint is enforced without encoding it for every channel × every diff pair pair eagerly. For a 200-net board with 5 diff pairs on 20 channels, this saves 5 × 20 = 100 eager clause pairs, replacing them with at most 5 instantiations (one per diff pair that is "activated" during search).

### AE3. HV Net Safety Isolation (Eager)

**Setup:** An HV net (AC_L) and two signal nets in the same region. Channel CH1 is adjacent to an HV pad. The safety constraint: "at most 1 non-HV net may enter CH1" due to creepage requirements.

**Bundle behavior:** AC_L is in its own bundle class B_HV (unique type signature — HV). The two signal nets are in bundle class B_SIG. The safety constraint for CH1 encodes eagerly: `uses[B_HV, CH1] = 1` (HV net must use this channel for its pad) and `uses[B_SIG, CH1] ≤ 1` (at most one signal net may share this channel with HV). This is a Safety constraint → eager grounding, regardless of solver state.

**Expected outcome:** The HV isolation constraint is always enforceable. No lazy instantiation is needed. The Safety-vs-Performance gating prevents the HV constraint from being lazily deferred (which would be unsafe — the solver could commit to an assignment that violates creepage before the constraint is grounded).

---

## Success Criteria

- **SC1 (Variable count reduction):** On a 200-net board with 12 bundle classes, the bundling pass produces ≤ 10% of the eager variable count for the Safety constraints (i.e., ≥90% reduction vs unbundled encoding). Measured at the point immediately after F2 (eager safety encoding complete, before any lazy grounding).

- **SC2 (Lazy grounding correctness):** For any constraint set where all Performance constraints are lazily grounded and all Safety constraints are eagerly grounded, the solver's SAT/UNSAT result is EQUIVALENT to the result when the same constraint set is fully eagerly grounded (same sat/unsat answer, same net-to-channel assignments, disregarding variable-name differences from homomorphism projection). Verified via property-based test across random constraint sets on ≤8 nets, ≤4 channels.

- **SC3 (Safety constraint guarantee):** Safety constraints are never deferred to lazy grounding. Every Safety constraint is present as a clause in the CNF before `solve()` is called. Verified by assertion in the bundle analysis pass.

- **SC4 (Performance constraint trigger correctness):** No Performance constraint clause is added to the CNF unless the partial assignment at the time of addition makes a violation concretely possible (i.e., the constraint's guard condition evaluates to true for the current assignment). Verified by watchdog telemetry logging each lazy addition with its trigger assignment.

- **SC5 (End-to-end closure preservation):** The SM1 completion rate (≥90%) and SM2 DRC pass rate (≥96.7%) measured by the closure test (`test_router_completion.py`) do not regress when bundling is enabled vs the current unbundled path on `pcb/temper_placed.kicad_pcb`.

- **SC6 (No solver regression):** The unbundled path (`enable_bundling=False`) produces identical variable count, clause count, and SAT assignments to the pre-bundling codebase. Verified by CI diff test.

---

## Scope Boundaries

**In scope:**

- Bundle equivalence class analysis based on net type signature and geometric footprint
- Type-gating policy (Safety vs Performance vs Aesthetic) with configurable classification rules
- Eager encoding of Safety constraints at class-variable granularity
- Lazy encoding of Performance constraints triggered by partial-assignment guard conditions
- Homomorphism mapping between class variables and per-net variables
- Integration with existing `ModelBuilder`, `encoding.rs`, `solver.rs`, `extraction.rs`, and `audit.rs`
- Correctness proofs for the homomorphism (R8, R10)

**Explicitly outside scope:**

- **Operator ordering constraints** (`OrderVar`): The current `OrderVar` type (`constraint_model.py:68-78`) encodes relative ordering of nets in a channel. Bundling does not affect this — ordering is inherently per-net and cannot be class-aggregated. OrderVar creation remains per-net (O(n·|E|) worst case) and is excluded from bundling.
- **ViaVar bundling:** Via variables are currently excluded from bundling because via placement is pin-position-specific and cannot be shared across nets (each net has distinct pin locations). ViaVar count remains O(n·|V|).
- **Constraint type inference / auto-classification:** The constraint type system described in `NetClassRules` (`stage0_data.py:77-88`) does not currently expose `safety_category` as a field. Adding this field is prerequisite work but is out of scope for the bundling feature itself.
- **Solver replacement:** Research into solvers with native IPASIR incremental interfaces (CaDiCaL, MiniSat, Glucose) is out of scope. The initial implementation shall work within splr's capabilities (multiple sequential `solve()` calls) or extend splr with a patch.
- **Multi-solve iteration for Performance grounding:** The exact mechanism (restart-based incremental solves vs solver API extension) is deferred to planning.
- **Aesthetic post-processing:** The actual post-processing algorithms for length matching, color guides, etc. are deferred.

---

## Key Decisions

- **KD1:** Bundle equivalence is defined by *constraint-type signature* (net class + physical dimensions) AND *geometric overlap* (Jaccard > 0.5 on skeleton edges) — not by graph isomorphism. Reasons: (a) graph isomorphism is NP-complete and the bundling pass must run in O(n log n) time, (b) constraint-type signature captures the structural properties that matter for constraint encoding, (c) geometric overlap ensures two nets in different physical regions don't incorrectly share a class variable for a channel neither will use.

- **KD2:** Safety constraints are always eager — never lazy. Reasoning: the whole point of Safety constraints (HV/LV isolation) is that they must NEVER be violated. Deferring them to lazy grounding creates a window where the solver could commit to a partial assignment that already violates safety, and backtracking from that assignment would be more expensive than encoding the constraint up front.

- **KD3:** The homomorphism is injective from class variables to per-net variable *sets* (each class variable maps to N per-net variables where N = number of nets in the class). The reverse mapping is surjective — multiple per-net variables map to one class variable. This is the standard "lift" pattern from LCG (Ohrimenko et al. 2009).

- **KD4:** The watchdog for lazy grounding runs *between* incremental `solve()` calls, not *during* CDCL search. splr 0.13 does not expose a mid-search callback. The flow is: solve safety CNF partially → inspect assignment → add Performance clauses → resume solve. This may require splr to support `add_clause` between `solve()` calls (the current `add_assignment` API at `SatSolverIF` line 48 suggests partial-assignment injection is supported, but post-solve clause addition is untested).

- **KD5:** The bundle analyzer is a new module in `temper-placer` (`packages/temper-placer/src/temper_placer/router_v6/bundle_analyzer.py`), not in `temper-rust-router`. The Rust crate receives a pre-bundled constraint model where class variables are already resolved. This keeps the Rust→Python boundary unchanged and simplifies the Rust code. The lazy grounding watchdog is a new Rust module in `temper-rust-router` (alongside `solver.rs`). It receives the pre-bundled constraint model from Python via a new PyO3 binding and drives the incremental solve loop internally.

---

## Dependencies / Assumptions

1. **splr 0.13 supports `add_var()`/`add_clause()` between incremental `solve()` calls** (not just before the first solve). This is assumed based on `SatSolverIF` supporting `add_assignment` at line 48 of `build.rs` which can inject unit assignments — but the full incremental clause-addition workflow needs verification. If splr does not support this, either a splr patch or a solver migration is required.

2. **Dependency:** Enable splr's `incremental_solver` feature in `temper-rust-router/Cargo.toml` and verify the `add_clause` → second `solve()` workflow with property-based tests on small CNF instances (≤8 vars) before implementing lazy grounding.

3. **Net class resolution is fast and available at bundle-analysis time.** The current `net_classification.py` functions (`is_hv_net`, `is_power_net`, etc.) operate on net names and are O(1) per net. This is sufficient; no changes needed.

4. **`NetClassRules.safety_category` field exists or is added.** This is out of scope but is a prerequisite: the Safety/Performance/Aesthetic classification needs a per-rule safety category. Currently `NetClassRules` (`stage0_data.py:77-88`) has no such field. Without it, the gating policy falls back to net-name-based heuristics from `net_classification.py`.

5. **The channel skeleton graph is available at bundle-analysis time.** Confirmed: `ChannelSkeleton.graph` is a `networkx.Graph` with node positions as (x, y) tuples (`channel_skeleton.py:27-32`). The bundle analyzer can traverse it to compute geometric footprints.

6. **Constraint audit (`audit.rs`) can validate bundled results.** The audit operates on `InternalConstraintModel` variables and checks constraints directly (`audit.rs:72-126`). After bundling, the constraint model's per-net variable names differ (they carry class-variable names pre-homomorphism). The audit must be adapted to expand class variables to per-net variables before checking, or the audit must operate on the post-homomorphism model.

---

## Outstanding Questions

### Resolve Before Planning

- **OQ-R1 (splr incremental support):** Can splr 0.13's `add_clause()` be called between successive `solve()` invocations on the same `Solver` instance? The current code at `solver.rs:19-100` calls `add_var()` → `add_clause()` → `solve()` in a single pass. We need to verify: does `solve()` leave the solver in a state where more clauses can be added, and does a second `solve()` continue from the previous state? Answer needed before choosing between (a) splr incremental solves, (b) splr API extension, or (c) solver migration.

- **OQ-R2 (Constraint type field):** Does `NetClassRules` need a `safety_category: Literal["HV", "LV", "SELV", "Signal"]` field? In the current codebase, HV/LV classification is done by net-name pattern matching in `net_classification.py:28-30` and not by the `NetClassRules` data model. Should the bundling feature add this field, or should it reuse the existing pattern-matching functions? Decision affects R3-R5.

- **OQ-R3 (Geometric overlap threshold):** Is Jaccard index > 0.5 on skeleton edge sets the correct equivalence threshold? This needs empirical calibration on the Temper PCB. Too high → many singleton bundles (no compression). Too low → nets in different corners of the board share a bundle class (pessimistic AtMostK that rejects feasible assignments). Answer needed before R1 implementation.

- **OQ-R4 (Bundle class count for Temper PCB):** What is the expected number of bundle classes b for the Temper PCB (23 nets)? Running the bundle analysis on the existing data (even without full implementation) would bound the expected compression ratio and validate the O(b·|E| + n) complexity claim in the Summary.

### Deferred to Planning

- **OQ-D1 (Watchdog implementation language):** Should the lazy grounding watchdog be in Rust (closer to solver, faster) or Python (easier to prototype, access to `BundleManifest`)? If in Rust, the `BundleManifest` must cross the PyO3 boundary. If in Python, we need a mechanism to pause splr, inspect its partial assignment, and add clauses.

- **OQ-D2 (Budget for lazy instantiation):** What is the concrete budget for per-net variable instantiation (R7.1)? The current placeholder is `10 × |bundle_nets|`. This needs empirical calibration — too low may reject SAT instances that are actually solvable with full grounding.

- **OQ-D3 (Diff pair homomorphism detail):** For diff pairs, the homomorphism must handle the case where USB_DP and USB_DN are in the same bundle class. The equivalence clause `uses[USB_DP, c] == uses[USB_DN, c]` is inherently per-pair, not per-class. The homomorphism must handle paired-variable instantiation (always create both members of a diff pair together). Design TBD.

- **OQ-D4 (Test strategy for homomorphism correctness):** R8 requires that the homomorphism preserves constraint semantics. The inductive proof strategy (see the inductive proof at `encoding.rs:167-181` in the Rust source, or Sinz 2005 "Towards an Optimal CNF Encoding of Boolean Cardinality Constraints" for the full paper) should be drafted during planning. Exhaustive verification for small-n (n ≤ 6 nets, ≤4 channels) should cover the base cases.

- **OQ-D5 (Channel width awareness in bundling):** Nets with different trace widths cannot share a bundle class because the AtMostK capacity formula depends on width. The current type signature includes `(trace_width, clearance)` from `NetClassRules`. Should widths within ±10% tolerance be considered equivalent for bundling purposes? This would increase bundle class membership (more compression) at the cost of mildly pessimistic capacity estimates.
