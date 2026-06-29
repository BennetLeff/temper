---
title: "feat: UNSAT provenance + pre-solve tension detection"
type: feat
status: planned
date: 2026-06-28
origin: docs/brainstorms/2026-06-28-unsat-provenance-tension-detection-requirements.md
---

# UNSAT Provenance + Pre-Solve Tension Detection

## Summary

Attach provenance metadata (`ClauseOrigin`) to every CNF clause emitted by
`encoding.rs`, traceable to the originating `InternalConstraint`. Wire the
existing `solve_with_cadical_cores()` (selector-literal extraction) as the
primary solver so the `unsat_core: Vec<usize>` is always populated on UNSAT.
Reverse-map core clause indices through provenance to produce structured
`ConflictReport`s naming specific constraints and channels. Add a pre-solve
`tension.rs` module that detects analytically-incompatible constraint pairs
before the SAT solver runs, returning `HardConflict` / `CapacityWarning`
results without paying CDCL cost.

---

## Problem Frame

The solver returns `SolverStatus::Unsatisfiable` but `TopologyResult.unsat_core`
is always empty because `solve_topology_rust` calls `solve_with_cadical()` (no
core extraction). The existing `solve_with_cadical_cores()` already implements
selector-literal UNSAT core extraction and populates `unsat_core: Vec<usize>`
with clause indices — but those raw indices are meaningless to the designer.
The constraint audit (`audit.rs`) returns only `UnexplainedUnsat` for UNSAT
results, leaving zero diagnostic signal.

The encode path (`encoding.rs:78-163`) maps each `InternalConstraint` to CNF
clauses with no tracking of provenance. Auxiliary variables from
`encode_at_most_k` are anonymous. When the solver proves UNSAT, the only data
is "the CNF formula is unsatisfiable" with thousands of clauses across 3-10
constraints.

Some conflicts are structurally provable without invoking the SAT solver
at all (e.g., 3 nets forced to CH1 with capacity 2). Detecting these
analytically costs microseconds vs. hundreds of milliseconds of CDCL search.

---

## Key Technical Decisions

### KD1. Use existing selector-literal CaCaLi core extraction (not DRAT)

The codebase already migrated from splr to CaCaLi. `solver.rs` contains a
complete, working `solve_with_cadical_cores()` that extracts UNSAT cores via
selector-literal assumptions (`core()` returns failed-assumption clause
indices). The DRAT proof post-processing approach described in the requirements
brainstorm is unnecessary — `solve_with_cadical_cores()` already works and is
simpler. Switch `solve_topology_rust` to call `solve_with_cadical_cores()`.

**Risk**: Selector vars increase clause count by 1 literal per clause and
add `num_clauses` new variables. For the worst-case 228K-variable model, this
is ~50K extra vars — well within CaCaLi's limits. The existing `freeze_var`
prevents CaCaLi from eliminating selectors during preprocessing.

### KD2. Tension detection runs before the solve, unconditionally

Tension results are deterministic given the constraint model — identical on
every run regardless of solver outcome. Running before the solve means the
designer sees warnings even on SAT models (near-boundary capacity situations,
the most actionable diagnostics). O(c²) where c < 50 means < 1ms wall time.

### KD3. Provenance is per-clause (packed u32), not per-variable

A `ClauseOrigin` (packed into a `u32`: 16 bits constraint_idx, 8 bits role,
8 bits aux_block_id with 0xFF sentinel) accompanies each clause through the
pipeline. Origin tracking per-variable is ambiguous when a variable participates
in clauses from multiple constraints. Per-clause is unambiguous.

### KD4. ConflictReport replaces raw Vec<usize> in unsat_core

The current `TopologyResult.unsat_core: Vec<usize>` field holds raw clause
indices. Replace with structured `ConflictReport` data (or extend
`TopologyResult` with a new `conflict: Option<ConflictReport>` field while
keeping `unsat_core` populated for backward compatibility). The Python bridge
serializes both the raw indices and the structured report.

---

## Scope Boundaries

- Does NOT modify CaCaLi or rustsat source code. `solve_with_cadical_cores()`
  uses existing rustsat trait APIs (`freeze_var`, `solve_assumps`, `core`).
- Does NOT suggest fixes for conflicts. The feature explains WHAT conflicts,
  not HOW to resolve.
- Does NOT change existing constraint types. `InternalConstraint` stays
  Capacity / DiffPair / LayerRestriction.
- Does NOT integrate with PCL. Provenance stops at `InternalConstraint` names.
- Tension detection is read-only on `InternalConstraintModel` — no mutation of
  constraints, variables, or CNF.

---

## Requirements

(Cross-referenced from the origin requirements document.)

### Provenance Metadata

- **R1.** `CnfFormula` carries per-clause provenance: `Vec<ClauseOrigin>` where
  `ClauseOrigin` is a packed `u32` with `constraint_idx: u16`, `role: ClauseRole` (u8),
  `aux_block_id: u8` (0xFF = none).
- **R2.** `SatVariable.description` is populated for auxiliary variables with
  constraint provenance strings.
- **R2.1.** `encode_at_most_k` accepts a `constraint_label: &str` parameter
  for auxiliary variable descriptions.
- **R3.** Provenance metadata adds <100% memory overhead (~40% for packed u32).

### Pre-Solve Tension Detection

- **R4.** `detect_tensions(model: &InternalConstraintModel) -> Vec<TensionViolation>`
  with `constraint_pair`, `channel_id`, `explanation`, `severity`.
- **R5.** Detects: (a) capacity oversubscription, (b) diff-pair vs. capacity,
  (c) layer-restriction starvation, (d) mutually-exclusive assignment.
- **R6.** O(c²) time, <1s wall time for typical c<50.
- **R7.** Read-only — no mutation of model or CNF.

### UNSAT Core Reverse-Mapping

- **R8.** `build_conflict_report(core_indices, provenance, model) -> ConflictReport`.
  Uses existing selector-literal core from `solve_with_cadical_cores()`.
- **R9.** `ConflictReport` contains: `conflicting_constraints: Vec<(usize, String)>`,
  `channels_involved: Vec<String>`, `explanation: String`, `core_clause_count: usize`.
- **R10.** Auxiliary clauses from sequential-counter map to originating Capacity
  constraint (not "anonymous").
- **R11.** No modification of CaCaLi/rustsat source. Uses existing
  `solve_with_cadical_cores()` APIs.

### Integration

- **R12.** Tension detection runs before the SAT solve; results in
  `TopologyResult` even on SAT.
- **R13.** On UNSAT, `TopologyResult` carries structured conflict data.
- **R14.** Python return dict includes `"tensions"` and `"conflicts"` keys.
- **R15.** Pipeline logs `HardConflict` at INFO, `CapacityWarning` at DEBUG;
  no exception on UNSAT; skips audit on UNSAT (replaced by conflict report).
- **R16.** SAT case has zero performance regression.
- **R17.** On `Unknown` status, tension results still reported; conflicts absent.
- **R18.** If core extraction fails, fall back to pre-solve tension results
  as primary diagnostic + `UnexplainedUnsat` audit marker.

---

## Implementation Units

### U1. Provenance types and packed origin representation

**Goal:** Define `ClauseRole`, `ClauseOrigin` (packed u32), and extend
`CnfFormula` with `provenance: Vec<ClauseOrigin>` per-clause. Define the
data structures that U2-U4 depend on.

**Requirements:** R1, R3

**Dependencies:** None (pure type additions)

**Files:**
- Modify: `packages/temper-rust-router/src/types.rs`
  * Add `ClauseRole` enum: `ConstraintLiteral`, `CardinalityCounter`,
    `CardinalityExclusion`, `Unit`
  * Add `ClauseOrigin` with `To/From<u32>` for packed representation:
    `constraint_idx: u16`, `role: ClauseRole` (u8), `aux_block_id: u8`
    (0xFF sentinel = None)
  * Add `TensionSeverity` enum: `HardConflict`, `CapacityWarning`
  * Add `TensionViolation` struct: `constraint_pair: (usize, usize)`,
    `channel_id: String`, `explanation: String`, `severity: TensionSeverity`
  * Add `ConflictReport` struct: `conflicting_constraints: Vec<(usize, String)>`,
    `channels_involved: Vec<String>`, `explanation: String`,
    `core_clause_count: usize`
- Modify: `packages/temper-rust-router/src/encoding.rs`
  * Add `provenance: Vec<ClauseOrigin>` field to `CnfFormula`
  * Initialize as `Vec::new()` in `encode_to_cnf()` return

**Approach:**
- `ClauseOrigin` packs into a single `u32` for dense storage:
  `constraint_idx` in bits 0-15 (max 65535 constraints),
  `role` in bits 16-23,
  `aux_block_id` in bits 24-31.
  Implements `From<ClauseOrigin> for u32` and `From<u32> for ClauseOrigin`.
- `CnfFormula.provenance` is a parallel vector to `CnfFormula.clauses` —
  same length, same indexing, deterministic order. When `encode_to_cnf()`
  pushes a clause, it simultaneously pushes the corresponding origin.
- `aux_block_id: u8` identifies the sequential-counter block within a
  Capacity constraint. 0xFF (255) means "not an auxiliary block" (used
  for `ConstraintLiteral` and `Unit` roles).

**Patterns to follow:**
- `types.rs:340-355` — existing enum/struct conventions in this crate
- `encoding.rs:9-14` — existing `CnfFormula` struct, extend in-place

**Test scenarios:**
- Happy path: Pack and unpack `ClauseOrigin` round-trip for all role variants
  and edge aux_block_id values (0, 1, 254, 255 = sentinel).
- Happy path: `CnfFormula.provenance` has same length as `clauses` after
  `encode_to_cnf()` on a constraint model with Capacity + DiffPair + Layer.
- Edge case: `constraint_idx=65535` (max u16) packed/unpacked without loss.
- Edge case: All aux_block_id values 0..=255 handled correctly; 255 maps to
  `None` on unpack.

**Verification:**
- `cargo test -p temper-rust-router test_clause_origin_pack_unpack` — passes
- `cargo test -p temper-rust-router test_cnf_provenance_length` — passes

---

### U2. Provenance instrumentation in encode_to_cnf

**Goal:** Populate `CnfFormula.provenance` in `encode_to_cnf()` and
`encode_at_most_k()`, assigning a `ClauseOrigin` to every clause. Populate
auxiliary variable `.description` fields with constraint labels.

**Requirements:** R1, R2, R2.1, R3

**Dependencies:** U1 (ClauseOrigin type exists)

**Files:**
- Modify: `packages/temper-rust-router/src/encoding.rs`
  * `encode_at_most_k()`: add `constraint_idx: usize` and
    `constraint_label: &str` parameters; push `ClauseOrigin` for every
    clause generated; populate aux var descriptions
  * `encode_to_cnf()`: compute `constraint_idx` from loop position; pass
    to `encode_at_most_k()`; push `ClauseOrigin` for
    DiffPair/LayerRestriction unit/binary clauses
  * Track aux block ID counter: increment per `encode_at_most_k()` call
    within a single Capacity constraint (there is exactly 1 AtMostK per
    Capacity constraint, so aux_block_id = 0 always)

**Approach:**
- Modify `encode_at_most_k` signature:
  ```rust
  fn encode_at_most_k(
      clauses: &mut Vec<Vec<i32>>,
      var_map: &mut Vec<SatVariable>,
      vars: &[usize],
      k: usize,
      constraint_idx: usize,
      constraint_label: &str,
      provenance: &mut Vec<ClauseOrigin>,
      aux_block_id: u8,
  )
  ```
- Inside `encode_at_most_k`: for each clause pushed, push a matching
  `ClauseOrigin::new(constraint_idx, CardinalityCounter, aux_block_id)`
  for register-tracking clauses, `CardinalityExclusion` for exclusion clauses.
  For k=0 case: unit clauses get `CardinalityCounter` role.
- Auxiliary variable descriptions: change
  `format!("seq-counter r{i}.{j}")` to
  `format!("seq-counter for {constraint_label} r{i}.{j}")`.
- In `encode_to_cnf()`: track constraint loop index `ci`. For each
  `DiffPair`: push `ConstraintLiteral` for both implication clauses.
  `LayerRestriction`: push `Unit` for the unit clause. `Capacity`: pass
  `ci`, label string, and `aux_block_id=0` to `encode_at_most_k`.

**Patterns to follow:**
- `encoding.rs:111-135` — existing constraint loop, add provenance pushes
- `encoding.rs:40-50` — existing aux var descriptions, expand with label

**Test scenarios:**
- Happy path: Capacity constraint with 4 vars, k=2 — each generated clause
  has provenance pointing to the correct constraint_idx, role, and
  aux_block_id.
- Happy path: DiffPair generates 2 clauses, both with `ConstraintLiteral` role
  and matching constraint_idx.
- Happy path: LayerRestriction generates 1 clause with `Unit` role.
- Happy path: Auxiliary variable descriptions contain constraint label
  (e.g., `"seq-counter for Capacity[3] CH1 r0.0"`).
- Edge case: Capacity with k >= n (no cardinality encoding) — no clauses,
  no provenance entries.
- Edge case: k=0 capacity — unit clauses with `CardinalityCounter` role.
- Regression: `exhaustive_at_most_k_n1_to_n8` test still passes (var names
  changed but encoding logic unchanged).

**Verification:**
- `cargo test -p temper-rust-router test_encoding` — all tests pass
- Manual: `encode_to_cnf()` on a small model; assert `provenance.len() ==
  clauses.len()` and each origin unpacks to valid constraint_idx

---

### U3. Tension detection module (tension.rs)

**Goal:** Implement `detect_tensions(model: &InternalConstraintModel) ->
Vec<TensionViolation>` in a new `tension.rs` module. Register it in
`lib.rs`.

**Requirements:** R4, R5, R6, R7

**Dependencies:** U1 (TensionViolation, TensionSeverity types exist)

**Files:**
- Create: `packages/temper-rust-router/src/tension.rs`
  * Function: `detect_tensions(model: &InternalConstraintModel) -> Vec<TensionViolation>`
  * Internal helpers for each check:
    - `check_capacity_oversubscription`
    - `check_diffpair_vs_capacity`
    - `check_layer_restriction_starvation`
    - `check_mutually_exclusive_diffpair`
- Modify: `packages/temper-rust-router/src/lib.rs`
  * Add `pub mod tension;`

**Approach:**

**Pre-pass: Build index maps.** Walk `model.constraints` once, building:
- `capacity_by_channel: HashMap<String, (constraint_idx, max_nets, term_vars: HashSet<String>)>`
  (max_nets computed as `floor(capacity * slack / min_width)`)
- `layer_bans: HashMap<String, HashSet<String>>` (net → set of banned channels)
- `layer_allows: HashMap<String, HashSet<String>>` (net → set of allowed channels)
- `diffpairs: Vec<(constraint_idx, channel_id, p_var, n_var)>`

**Check 1: Capacity oversubscription (R5 bullet 1).**
For each channel with a Capacity constraint:
  - Identify "must-use" nets: nets where `allowed_channels == {this_channel}`
    (the net is banned from all other channels by LayerRestrictions).
  - If `must_use_count > max_nets`: emit `HardConflict`.
  - Explanation template: `"Channel {ch} capacity ({max_nets} nets) cannot
    accommodate {count} nets that have no other allowed channels: {net_list}"`

**Check 2: Diff-pair vs. capacity (R5 bullet 2).**
For each DiffPair constraint on channel CH:
  - Look up CH's Capacity constraint (if any).
  - Count must-use nets on CH (from Check 1 logic) plus count the diff-pair
    as requiring 2 nets on CH.
  - If `must_use_count + 2 > max_nets + slack`: emit `HardConflict`.
    Specifically: the diff pair needs capacity ≥ 2. If max_nets < 2 after
    accounting for must-use nets, it's impossible.
  - Explanation template: `"Diff pair requires both {p} and {n} on channel
    {ch}, but {ch} capacity is {max_nets} (only {max_nets} net allowed)"`

**Check 3: Layer-restriction starvation (R5 bullet 3).**
For each net N with exactly one allowed channel CH:
  - Look up CH's Capacity constraint.
  - Sum must-use nets on CH (including N).
  - If `must_use_count > max_nets`: emit `HardConflict`.
  - Explanation template: `"Net {N} is restricted to channel {CH} (all other
    channels banned), but {CH} capacity ({max_nets}) is exhausted by
    {count} must-use nets"`

Note: Check 3 is a refinement of Check 1 — it attributes the conflict to a
specific net rather than just flagging the channel.

**Check 4: Mutually-exclusive DiffPair assignment (R5 bullet 4).**
For each DiffPair constraint:
  - Compute the intersection of allowed channels for p_net and n_net
    (from layer_bans).
  - A channel is "allowed for a net" if it is NOT in the net's ban set
    (or no LayerRestrictions exist for the net → any channel allowed).
  - If the intersection set of allowed channels is empty: emit `HardConflict`.
  - Explanation template: `"Diff pair {p}/{n} has no shared channel — layer
    restrictions on {p} ban all channels that {n} can use, and vice versa"`

**CapacityWarning tier:**
After HardConflict checks, for each channel where `must_use_count >= max_nets
* 0.9 && must_use_count <= max_nets`, emit `CapacityWarning`.
Explanation template: `"Channel {ch} is at {pct}% capacity ({count}/{max_nets}
must-use nets) — the solver may fail to find an assignment"`

**Performance:**
- Build phase: O(c) to walk constraints once.
- Check 1: O(c * v) where v = nets per channel (bounded by total nets < 100).
- Check 2-4: O(c) each.
- Wall time < 1ms for c < 50, v < 100. Well within R6 budget.

**Patterns to follow:**
- `audit.rs:39-72` — model iteration pattern, `HashMap<&str, usize>` lookups
- `types.rs:288-306` — `InternalConstraint` pattern matching in loops

**Test scenarios:**
- Happy path (no tensions): 4 nets, CH1 capacity 4, no layer restrictions —
  returns `Vec::new()`.
- HardConflict oversubscription: 3 nets all forced to CH1 (all other channels
  banned), CH1 capacity 2 — returns `HardConflict`.
- HardConflict diffpair: DiffPair on CH1, CH1 capacity 1 — returns
  `HardConflict`.
- HardConflict starvation: Net N0 only allowed on CH1, CH1 capacity 2,
  but 3 nets total must use CH1 — returns `HardConflict`.
- HardConflict mutually-exclusive: DiffPair p_N0/n_N0; N0 banned from all
  channels N1 can use — returns `HardConflict`.
- CapacityWarning: CH1 at 90% must-use (9 out of 10 capacity) — returns
  `CapacityWarning`.
- Edge case: No Capacity constraint on a channel referenced by a DiffPair
  or LayerRestriction — skip gracefully (no tension).
- Edge case: No DiffPairs or LayerRestrictions, only Capacity constraints —
  no tension.
- Regression: Tension detection on the existing audit test model (4 nets,
  capacity 2, diffpair, layer restriction) — no false-positive
  `HardConflict`.
- AE1 from requirements: 3 nets N0/N1/N2, CH1 capacity 2, only N0
  restricted to CH1 — no tension (N1/N2 can go elsewhere).
- AE1 extended: All 3 nets restricted to CH1 — `HardConflict`.
- AE2 from requirements: DiffPair on CH1, CH1 capacity 1 — `HardConflict`.

**Verification:**
- `cargo test -p temper-rust-router tension` — all tests pass
- `cargo test -p temper-rust-router test_encoding` — no regression
- Manual: `detect_tensions()` on AE1/AE2 models matches expected output

---

### U4. Conflict report builder

**Goal:** Implement `build_conflict_report(core_indices: &[usize],
provenance: &[ClauseOrigin], model: &InternalConstraintModel,
var_map: &[SatVariable]) -> ConflictReport` that reverse-maps UNSAT core
clause indices to semantic constraint names and produces a human-readable
explanation.

**Requirements:** R8, R9, R10, R11

**Dependencies:** U1 (ConflictReport type), U2 (provenance populated),
U3 (not strictly required but conflicts + tensions are surfaced together)

**Files:**
- Create: `packages/temper-rust-router/src/provenance.rs`
  * Function: `build_conflict_report(...) -> ConflictReport`
  * Helper: `explain_core(unique_constraints, model) -> String`
- Modify: `packages/temper-rust-router/src/lib.rs` — add `pub mod provenance;`

**Approach:**

1. **Map core indices to unique constraints.** Walk `core_indices` and for
   each index, look up `provenance[i]` (same length as clauses vector).
   Unpack the `ClauseOrigin` to get `(constraint_idx, role)`.
   Collect into a `BTreeSet<(usize, ClauseRole)>` to deduplicate.
   `aux_block_id` is informational — it doesn't affect the constraint mapping.

2. **Identify channels involved.** For each unique constraint_idx:
   - Look up `model.constraints[constraint_idx]`.
   - Extract channel_id: Capacity → `channel_id`, DiffPair → `channel_id`,
     LayerRestriction → parse channel from `var_name` (names are
     `uses_N{net_idx}_{channel_id}` → extract `{channel_id}`).
   - Collect into `channels_involved: Vec<String>` (deduplicated).
   - Build `conflicting_constraints: Vec<(usize, String)>` with
     `(idx, description)` where description is a constraint-type-specific
     label (e.g., `"Capacity:CH1≤2"`, `"DiffPair:p_N0,n_N0@CH1"`,
     `"LayerRestriction:N0:CH1=false"`).

3. **Generate human-readable explanation.** Build a sentence from the
   conflicting constraints. Template depends on which constraint types
   are involved:
   - *Capacity only*: `"Channel {ch} capacity ({max}) exceeded — core contains
     {n} clauses"`
   - *Capacity + LayerRestriction*: `"Capacity constraint '{cap_label}'
     limits {ch} to {max} nets, but layer restrictions force {must_use} nets
     to use {ch} — capacity exceeded"`
   - *DiffPair + Capacity*: `"Diff pair '{dp_label}' requires both {p} and
     {n} on {ch}, but capacity '{cap_label}' limits {ch} to {max} nets"`
   - *Multiple/diverse*: `"UNSAT core involves {n} constraints across
     {m} channels: {constraint_list}"`

4. **Handle auxiliary clauses (R10).** When a core clause has role
   `CardinalityCounter` or `CardinalityExclusion`, the `constraint_idx`
   field already maps to the originating Capacity constraint (set by U2).
   The report attributes it to that Capacity constraint, not to
   "anonymous auxiliary clause." The `role` field is used only for
   informational logging (e.g., `"core includes {n} cardinality counter
   clauses from constraint {idx}"`).

5. **Edge: empty core.** If `core_indices` is empty (solver returned UNSAT
   but core extraction failed), return a `ConflictReport` with
   `explanation: "UNSAT core extraction failed — no clause-level
    diagnostics available"` and 0 `core_clause_count`.
   The caller (pipeline) falls back to tension detection results (R18).

**Patterns to follow:**
- `audit.rs:72-98` — constraint pattern matching and explanation building
- `encoding.rs:98-108` — variable name → index mapping

**Test scenarios:**
- Happy path: 3-clause UNSAT core from a Capacity constraint (all
  cardinality counter clauses) → report attributes to the single Capacity
  constraint, explanation mentions channel and capacity limit.
- Happy path: Core spanning Capacity + DiffPair → report lists both
  constraints, explanation names both.
- Happy path: Core includes `ConstraintLiteral` (from DiffPair) and
  `CardinalityExclusion` (from Capacity) → both mapped to correct constraints.
- Edge case: Empty core_indices → ConflictReport with "extraction failed"
  explanation.
- Edge case: A core clause index >= provenance.len() (solver eliminates a
  clause during preprocessing and core references an internal clause?) →
  skip gracefully, log warning, still produce report from remaining mappings.
- Edge case: Single LayerRestriction in core → report identifies the net and
  channel from the `var_name` string parsing.
- Implementation: AE2 model builds expected ConflictReport — `conflicting_
  constraints: ["DiffPair:p_N0,n_N0@CH1", "Capacity:CH1≤1"]`,
  `channels_involved: ["CH1"]`, `core_clause_count: 6`.

**Verification:**
- `cargo test -p temper-rust-router provenance` — all tests pass
- Manual integration: construct AE2 model, run solve → UNSAT with core →
  `build_conflict_report()` produces `DiffPair:p_N0,n_N0@CH1 + Capacity:CH1≤1`

---

### U5. Wire solve_with_cadical_cores into solve_topology_rust

**Goal:** Switch `solve_topology_rust` from calling `solve_with_cadical()`
(no core extraction) to `solve_with_cadical_cores()` (selector-literal
core extraction). Pass provenance data through. Call tension detection
before the solve. Build and serialize `ConflictReport` into the Python
return dict.

**Requirements:** R12, R13, R14, R17, R18

**Dependencies:** U1 (types), U2 (provenance in CnfFormula), U3 (tension),
U4 (conflict report builder)

**Files:**
- Modify: `packages/temper-rust-router/src/lib.rs`
  * Import `tension::detect_tensions` and `provenance::build_conflict_report`
  * Call `detect_tensions(&model)` before encoding/solving
  * Call `solver::solve_with_cadical_cores(&cnf, &var_names)` instead of
    `solver::solve_with_cadical(...)`
  * On UNSAT: call `build_conflict_report(&result.unsat_core, &cnf.provenance, &model, &var_map)` → store in result
  * Serialize tensions and conflict report to Python dict
- Modify: `packages/temper-rust-router/src/types.rs`
  * Add `tensions: Vec<TensionViolation>` and `conflict: Option<ConflictReport>`
    to `TopologyResult`
- Modify: `packages/temper-rust-router/src/solver.rs`
  * Ensure `solve_with_cadical_cores` is `pub` (already is) — verify it's
    imported correctly in lib.rs

**Approach:**

In `solve_topology_rust`:
```
1. Build model from Python (existing)
2. Call detect_tensions(&model) → tensions
3. Encode to CNF (existing, now with provenance from U2)
4. Call solver::solve_with_cadical_cores(&cnf, &var_names) → result
5. result.tensions = tensions
6. On UNSAT:
   a. If !result.unsat_core.is_empty():
      result.conflict = Some(build_conflict_report(...))
   b. Else: result.conflict = None (fallback: tensions are primary diag)
7. Serialize to Python dict:
   - "tensions": list of {severity, channel_id, explanation,
     constraint_pair} dicts
   - "conflicts": None | {conflicting_constraints, channels_involved,
     explanation, core_clause_count} dict (only on UNSAT with successful
     core extraction)
   - Keep existing "unsat_core" key with raw Vec<usize> (backward compat)
```

**Performance note (R16):** Tension detection runs once per model before
the solve — not in the solver's hot loop. Auxiliary variable `.description`
strings are strings created during encoding, not accessed during CDCL.
The selector-literal instrumentation in `solve_with_cadical_cores` adds
1 literal per clause — this is existing code, not new overhead. SAT-case
solve time is unchanged.

**Patterns to follow:**
- `lib.rs:39-102` — existing `solve_topology_rust` flow, extend in-place
- `lib.rs:59-99` — existing `d.set_item` pattern for serialization

**Test scenarios:**
- Happy path SAT: model with tensions (CapacityWarning) + SAT result →
  tensions present in Python dict, conflicts=None, status="sat".
- Happy path UNSAT: AE2 model (DiffPair+Capacity conflict) → status="unsat",
  conflicts populated with constraint names, tensions populated with
  HardConflict.
- Happy path UNSAT core failure: model returns UNSAT but core is empty →
  status="unsat", conflicts=None, tensions populated as fallback (R18).
- Happy path Unknown: solver times out → status="unknown", tensions present,
  conflicts absent (R17).
- Backward compat: existing `"unsat_core"` key still in Python dict with
  raw Vec<usize>.
- Zero missing keys: Python code accessing `result.get("tensions", [])` and
  `result.get("conflicts")` never raises KeyError.

**Verification:**
- `cargo test -p temper-rust-router` — all unit tests pass
- Python: `from temper_rust_router import solve_topology_rust` → call on a
  small model → inspect return dict for "tensions", "conflicts", "unsat_core"
- Python: test that SAT result has tensions but no conflicts
- Python: test that UNSAT result has BOTH tensions and conflicts (if core
  extraction succeeds)

---

### U6. Pipeline integration

**Goal:** Update `pipeline.py:_run_stage3()` to surface tension/conflict
diagnostics. Log HardConflict tensions at INFO, CapacityWarning at DEBUG.
Skip constraint audit on UNSAT (replaced by conflict report). Do not raise
RuntimeError on UNSAT.

**Requirements:** R15, R16, R17, R18

**Dependencies:** U5 (Rust bridge returns tensions + conflicts in dict)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`
  * Lines 632-633: after `rust_result = solve_topology_rust(...)`, read
    `tensions` and `conflicts` keys
  * Lines 640-645: update status mapping (unchanged)
  * Lines 674-687: update audit block — skip audit when `status == 'unsat'`,
    surface conflict report instead
  * Additional: log tensions at appropriate levels

**Approach:**

After `rust_result = solve_topology_rust(...)` (line 633):

```python
# Surface pre-solve tension diagnostics
tensions = rust_result.get("tensions", [])
for t in tensions:
    sev = t.get("severity", "unknown")
    expl = t.get("explanation", "")
    ch = t.get("channel_id", "")
    if sev == "hard_conflict":
        logger.info(f"  PRE-SOLVE WARNING: Hard conflict on channel {ch}: {expl}")
    elif sev == "capacity_warning":
        if self.verbose:
            logger.debug(f"  PRE-SOLVE INFO: Capacity warning on channel {ch}: {expl}")

# Surface UNSAT conflict diagnostics
if rust_result["status"] == "unsat":
    conflict = rust_result.get("conflicts")
    if conflict:
        logger.info(f"  UNSAT CONFLICT: {conflict.get('explanation', '')}")
        logger.info(f"    Constraints: {conflict.get('conflicting_constraints', [])}")
        logger.info(f"    Channels: {conflict.get('channels_involved', [])}")
        logger.info(f"    Core clauses: {conflict.get('core_clause_count', 0)}")
    else:
        logger.info(f"  UNSAT: No conflict report available (core extraction failed)")
```

Modify the audit block (lines 674-687):
```python
# Skip audit for UNSAT: conflict report replaces UnexplainedUnsat.
# Audit still fires for SAT results (unchanged behavior).
if rust_result["status"] == "sat":
    from temper_rust_router import audit_result
    audit_violations = list(audit_result(
        py_vars, py_cons,
        dict(rust_result.get("assignments", {})),
        net_names,
    ))
    if audit_violations:
        msg = f"Rust solver produced {len(audit_violations)} constraint violation(s): {audit_violations}"
        if self.verbose:
            print(f"    WARNING: {msg}")
        raise RuntimeError(msg)
    elif self.verbose:
        print(f"    Constraint audit: clean (0 violations)")
elif rust_result["status"] == "unknown":
    # Unknown status: tension results may be available (R17), no conflict report
    if self.verbose:
        print(f"    Solver status: UNKNOWN (timeout/internal error)")
elif self.verbose:
    print(f"    No solution found (UNSAT) — see conflict report above")
```

The `HardConflict` tension logging uses `logging.info` → always visible
(not gated by `self.verbose`). `CapacityWarning` uses `logging.debug`
or is gated by `self.verbose` (R15: DEBUG level or verbose flag).

**Patterns to follow:**
- `pipeline.py:635-693` — existing verbose-print pattern in `_run_stage3()`

**Test scenarios:**
- Happy path SAT with tension: model produces CapacityWarning → printed at
  DEBUG/verbose level only, no INFO noise.
- Happy path UNSAT with conflict: model produces UNSAT + core → INFO logs
  show conflict explanation, no RuntimeError raised.
- Happy path UNSAT without conflict: core extraction failed → INFO logs show
  "No conflict report available", audit skipped, no RuntimeError.
- Backward compat: SAT path still runs audit at line 674-687, still raises
  RuntimeError on violations (unchanged).
- Unknown: tension results logged (if present), no conflict report, audit
  skipped.
- Verbose off: HardConflict tensions still visible at INFO; CapacityWarning
  tensions not printed.
- Verbose on: all tensions printed; SAT audit clean message printed.

**Verification:**
- Run full closure test: no RuntimeError on UNSAT boards
- Run closure test on a board known to produce SAT: audit fires, no regression
- Run with `verbose=True`: all tension messages visible in output
- Run with `verbose=False`: only HardConflict messages visible

---

### U7. End-to-end integration tests

**Goal:** Create a Python-side test that exercises the full tension →
conflict pipeline on hand-crafted constraint models. Covers the acceptance
examples from the requirements.

**Requirements:** R5 (acceptance examples), SC1 (designer-readable explanations)

**Dependencies:** U6 (pipeline integration complete)

**Files:**
- Create: `packages/temper-placer/tests/router_v6/test_tension_detection.py`
- Modify: `packages/temper-placer/tests/router_v6/test_stage3_constraint_audit.py`
  (add UNSAT conflict report assertions)

**Approach:**
- Build `InternalConstraintModel` objects directly in test (or call
  `solve_topology_rust` with hand-crafted variable/constraint lists).
- Test AE1 (capacity oversubscription with layer restriction):
  3 nets N0/N1/N2, CH1 capacity 2. N0 restricted to CH1 only. Expect:
  - tensions: empty (no HardConflict — N1/N2 can go elsewhere)
  - status: "sat"
  - Then add: N1/N2 also restricted to CH1 → tensions: `HardConflict`,
    status: "unsat", conflicts: populated with Capacity constraint reference.
- Test AE2 (diff-pair vs. capacity):
  DiffPair on CH1, CH1 capacity 1. Expect: tensions: `HardConflict`,
  status: "unsat", conflicts: `DiffPair + Capacity:CH1≤1`.
- Test CapacityWarning: CH1 capacity 10, 9 must-use nets — tensions:
  `CapacityWarning`, status: "sat" (solver can still succeed).
- Test no false-positive: model with DiffPair but capacity 2 — expected SAT,
  no HardConflict tension.
- Test mutually-exclusive diffpair: two diff-pair nets with disjoint allowed
  channel sets.
- Verify the `conflicts.explanation` field contains human-readable text
  naming specific constraints and channels (SC1).

**Patterns to follow:**
- `packages/temper-placer/tests/router_v6/test_stage3_constraint_audit.py` —
  existing Rust solver test shape

**Verification:**
- `python -m pytest packages/temper-placer/tests/router_v6/test_tension_detection.py -v`
  — all tests pass
- Each test case includes assertion on `conflicts.explanation` field format

---

## Output Structure

```
packages/temper-rust-router/
├── src/
│   ├── lib.rs                 # +pub mod tension; +pub mod provenance
│   │                          #  Wire cores solver + tensions + conflict report
│   ├── types.rs               # +ClauseOrigin, +ClauseRole, +TensionSeverity,
│   │                          #  +TensionViolation, +ConflictReport types
│   ├── encoding.rs            # +provenance field on CnfFormula
│   │                          #  +encode_at_most_k provenance instrumentation
│   │                          #  +aux var descriptions with constraint labels
│   ├── solver.rs              # (unchanged — solve_with_cadical_cores already exists)
│   ├── tension.rs             # NEW: detect_tensions() + 4 checks
│   ├── provenance.rs          # NEW: build_conflict_report()
│   ├── audit.rs               # (unchanged)
│   ├── extraction.rs          # (unchanged)
│   └── types_py_bridge.rs     # (unchanged)
└── tests/                     # (existing Rust test structure)
    └── ...                    # coverage in module-level #[cfg(test)]

packages/temper-placer/
├── src/temper_placer/router_v6/
│   └── pipeline.py            # tension/conflict logging, skip audit on UNSAT
└── tests/router_v6/
    ├── test_tension_detection.py       # NEW: acceptance example tests
    └── test_stage3_constraint_audit.py # extend: UNSAT conflict report assertions
```

---

## System-Wide Impact

- **Interaction graph:** Single integration point — `solve_topology_rust` in
  `lib.rs`. Python receives extended return dict. `pipeline.py` reads new
  keys. No other module touched.
- **Error propagation:** `detect_tensions()` is infallible (read-only analysis
  on valid model). `build_conflict_report()` handles empty core gracefully,
  never panics. Selector-literal solver already catches panics via
  `catch_unwind`.
- **State lifecycle risks:** None. Tension detection is read-only.
  Provenance is populated during encoding and read during core reverse-mapping
  (both within a single `solve_topology_rust` call).
- **API surface:** Python return dict gains `"tensions"` and `"conflicts"`
  keys. Existing `"unsat_core"` key remains (backward compat). All existing
  keys unchanged.
- **Unchanged invariants:** SAT audit (`audit_result` on `"sat"` status) fires
  unchanged. `skip_stage3=True` bypasses the entire flow unchanged.
  `TopologyGraph` format unchanged. `SolverStatus` enum unchanged.

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Selector vars cause CaCaLi performance degradation on large models | Low | Medium | `solve_with_cadical_cores` is already implemented and tested. Selector literals are frozen via `freeze_var` to prevent elimination. Runtime overhead <5% on SAT models per prior CDCL literature. |
| Tension detection produces false-positive HardConflict | Low | High | Every HardConflict rule is provably UNSAT by construction (must-use nets > max capacity → 0 feasible assignments). All 4 checks are mathematically sound. The CapacityWarning tier is explicitly heuristic. |
| Core extraction fails (CaCaLi internal error in core()) | Low | Medium | R18: fall back to tension detection results as primary diagnostic. `UnexplainedUnsat` audit violation as secondary marker. No crash. |
| ConflictReport explanation text is confusing | Medium | Low | Templates are short single-sentence forms. Acceptance examples (AE1, AE2) define the expected text format. Tests assert exact explanation string for known scenarios. |

---

## Success Criteria

- **SC1.** A designer can understand WHY the solver failed without reading CNF
  clause dumps. The `conflicts.explanation` field names specific constraints,
  channels, and nets in a single sentence.
- **SC2.** Tension detection catches analytically-conflicting constraint pairs
  in <1ms wall time for typical models (c<50, v<100).
- **SC3.** Provenance metadata adds ~40% memory overhead per clause (packed u32
  vs. Vec<i32> of 3-4 elements).
- **SC4.** SAT-case performance is unchanged: tension detection runs once
  before the solve, selector-literal overhead is already in the existing
  `solve_with_cadical_cores()` path.
- **SC5.** No false-positive `HardConflict` tensions. Every `HardConflict`
  flagged by tension detection is provably UNSAT.

---

## Sources & References

- **Origin document:** `docs/brainstorms/2026-06-28-unsat-provenance-tension-detection-requirements.md`
- **Related code:**
  - `packages/temper-rust-router/src/solver.rs` — `solve_with_cadical_cores()`
  - `packages/temper-rust-router/src/encoding.rs` — `encode_to_cnf()`,
    `encode_at_most_k()`
  - `packages/temper-rust-router/src/types.rs` — `TopologyResult`,
    `CnfFormula`, `InternalConstraintModel`
  - `packages/temper-rust-router/src/audit.rs` — constraint audit pattern
  - `packages/temper-rust-router/src/lib.rs` — Python bridge,
    `solve_topology_rust`
  - `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` —
    `_run_stage3()` integration point
- **Prior art:**
  - `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` —
    documented AtMostK bug
  - `docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md` —
    solver architecture (plan and post-implementation amendments)
- **External:** CaCaLi (rustsat-cadical 0.7.5), rustsat 0.7.5, PyO3 0.23
