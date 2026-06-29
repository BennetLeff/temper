---
date: 2026-06-28
topic: unsat-provenance-tension-detection
---

# UNSAT Provenance + Pre-Solve Constraint Tension Detection

## Summary

Instrument every SAT clause with provenance metadata tracing back to the semantic `InternalConstraint` that generated it. Build reverse-mapping from UNSAT core clause indices to designer-level constraint names and their rationales, plus a pre-solve analytical pass that detects pairwise-incompatible constraints (e.g. capacity overflow on the same channel, diff-pair vs. layer-restriction) before invoking the solver.

---

## Problem Frame

When `splr` returns `Certificate::UNSAT` (a unit variant — no core data, no clause list), the result is an opaque failure. The pipeline at `pipeline.py:632-633` maps it to `SolverStatus.UNSATISFIABLE`, the `TopologyResult.unsat_core` field (`types.rs:353`) stays empty, and the only diagnostic is `AuditViolation::UnexplainedUnsat` (`audit.rs:34`). The designer sees "No solution found (UNSAT)" with no indication of WHICH constraints conflict or WHY.

The unsound AtMostK fix (documented in `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md`) demonstrated that the only safeguard against silent constraint violations is the post-solve constraint audit (`audit.rs` + `pipeline.py:664-677`). But that audit only fires on SAT results — it returns `UnexplainedUnsat` immediately for UNSAT results and moves on. The designer has zero visibility into the conflict space.

The constraint model in `types.rs` defines 3 `InternalConstraint` variants (Capacity, DiffPair, LayerRestriction), but the CNF encoder in `encoding.rs` emits clauses with no tracking of which constraint a given clause originated from. Auxiliary variables from the Sinz-2005 sequential counter (`encode_at_most_k`) are anonymous — they belong to no constraint at all. When the solver proves UNSAT, the only available information is "the CNF formula is unsatisfiable," which maps to thousands of clauses across 3-10 constraints.

Furthermore, some conflicts are analytically detectable without invoking the SAT solver at all. If capacity constraint C1 on channel CH1 says "max 2 nets" and C2 also on CH1 says "max 1 net," these are not contradictory — C2 subsumes C1. But if a layer restriction bans all but one channel from a net and a capacity constraint on that channel is already at its bound, the conflict is structural, not algorithmic — the SAT solver always returns UNSAT for such a model, and detecting it analytically costs microseconds instead of hundreds of milliseconds of CDCL search.

---

## Actors

- A1. **PCB Designer**: Defines constraints (indirectly via PCL, directly via the pipeline) and receives conflict reports. Needs to understand WHY routing is impossible without reading CNF clause dumps.
- A2. **SAT Solver (splr 0.13)**: Produces `Certificate::UNSAT` with no core data. The solver is treated as a black box — this feature does NOT modify splr's source.
- A3. **ModelBuilder (`encoding.rs`)**: Creates CNF clauses with provenance metadata attached to every clause, recording which `InternalConstraint` (or auxiliary set) produced it.
- A4. **Tension Detector (new)**: Pre-solve analytical checker that examines constraint pairs for structural incompatibility without invoking the solver.
- A5. **Provenance Reverse-Mapper (new)**: Post-UNSAT component that maps conflicting clause indices back through provenance records to designer-level constraint names and conflict descriptions.

---

## Key Flows

### F1. Pre-solve tension detection
- **Trigger**: After the constraint model is built (`InternalConstraintModel` populated) but before `encode_to_cnf` is called
- **Actors**: A4 (Tension Detector)
- **Steps**:
   1. For each channel, if the sum of minimum net widths for nets that MUST use this channel (all others banned by layer restrictions) exceeds capacity * slack_factor, flag as HardConflict.
  2. Pair each DiffPair constraint with each Capacity constraint on the same channel: if the diff pair's channel has capacity < 2, flag — diff pair requires both p and n nets on the same channel, which is impossible at capacity 0 or 1 after accounting for other nets
   3. For each net N, if N has exactly one allowed channel CH (all other channels banned by LayerRestrictions), and the sum of must-use nets on CH (including N) exceeds CH's capacity * slack_factor, flag as HardConflict.
  4. For each channel, compute the "must-use" net count: nets that have exactly one channel available (all others banned by layer restrictions). If must-use count > channel capacity, flag as a hard structural conflict
- **Outcome**: A list of `TensionViolation` structs (conflicting constraint pair, channel ID, explanation string) returned BEFORE the solver runs. Warnings can surface to the designer without paying the solver cost
- **Covered by**: R4, R5, R6, R7

### F2. Clause-level provenance instrumentation
- **Trigger**: During `encode_to_cnf` (`encoding.rs:78-163`), as each clause is generated
- **Actors**: A3 (ModelBuilder)
- **Steps**:
  1. Extend `CnfFormula` (or add a parallel `ClauseProvenance` structure) to carry a `provenance: Vec<ClauseOrigin>` per-clause, where `ClauseOrigin` records: (a) the `InternalConstraint` index in the model that sourced this clause, (b) a `ClauseRole` enum (`ConstraintLiteral` for clauses from DiffPair/LayerRestriction, `CardinalityCounter` for clauses from the sequential-counter encoding, `CardinalityExclusion` for the exclusion clauses, `Unit` for unit clauses)
  2. When `encode_at_most_k` generates auxiliary variables and clauses, record which Capacity constraint (by index) triggered the cardinality encoding and which role each clause plays
  3. Auxiliary variables get a `SatVariable.description` field populated with their provenance (e.g. "seq-counter for Capacity[3] r2.1")
  4. Expose provenance through a new `CnfFormula.provenance` field (or companion vector), serialized alongside the DIMACS CNF or passed directly to the reverse-mapper
- **Outcome**: Every clause in the CNF can be traced to either a specific `InternalConstraint` or a named auxiliary encoding block
- **Covered by**: R1, R2, R3

### F3. UNSAT core → designer-level conflict explanation
- **Trigger**: `solve_with_splr` returns `SolverStatus::Unsatisfiable`
- **Actors**: A5 (Provenance Reverse-Mapper), A1 (consumes report)
- **Steps**:
   1. splr does not expose an in-memory UNSAT core. Strategy: enable splr's `save_certification()` (DRAT proof output), post-process the DRAT proof with `drat-trim` to extract the final conflicting clause set (the "core" is the set of original clauses that the DRAT proof resolves to empty). The selector-literal method (add one selector variable per original clause, unit-assume them all) is rejected because `Certificate::UNSAT` is a unit variant — `unsat_core` at `solver.rs:67-69` is always empty.
   2. (Primary approach: DRAT proof post-processing. Enable splr's `save_certification()` to write the proof, then post-process with `drat-trim` to extract the final conflicting clause set. The selector-literal method, which would add one selector variable per original clause and unit-assume them all, is noted as a possible future optimization if splr gains assumption-based UNSAT core support — but currently `Certificate::UNSAT` returns no data (`unsat_core` at `solver.rs:67-69` is always empty).)
  3. Map the core clause indices back through the provenance table to produce a `ConflictReport` containing: (a) list of conflicting `InternalConstraint` names/types, (b) the channel(s) involved, (c) a human-readable explanation (e.g. "Capacity constraint 'cap_CH1' limits CH1 to 2 nets, but nets N0, N1, N3 must all use CH1 (layer restrictions ban alternatives) — capacity exceeded by 1")
  4. Surface the `ConflictReport` via `TopologyResult` (extend the `unsat_core` field from `Vec<usize>` to contain structured conflict data) and expose to Python through the existing `solve_topology_rust` return dict under a new `"conflicts"` key
- **Outcome**: Designer sees a structured conflict explanation that names specific constraints and channels, not raw clause indices
- **Covered by**: R8, R9, R10, R11

### F4. Pipeline integration
- **Trigger**: `pipeline.py:622` — `rust_result = solve_topology_rust(...)`
- **Actors**: Pipeline orchestrator
- **Steps**:
  1. Call tension detection BEFORE the solve (new pipeline step, or integrated into `solve_topology_rust`). If tensions are found, emit warnings to the log immediately
  2. When `rust_result["status"] == "unsat"`, read `rust_result.get("conflicts", [])` and print structured diagnostics
  3. Keep the existing `audit_result` call for SAT results unchanged (it already works)
  4. Store conflict/tension data in the returned solution object for downstream consumers (DRC pass, debugging tools)
- **Outcome**: No regressions. UNSAT is no longer a black box — the pipeline surfaces actionable diagnostics
- **Covered by**: R12, R13, R14, R15, R16

---

## Requirements

### R-IDs: Provenance Metadata

- **R1.** The `CnfFormula` struct SHALL carry per-clause provenance metadata: a `Vec<ClauseOrigin>` where each `ClauseOrigin` contains `constraint_idx: usize` (index into `InternalConstraintModel.constraints`), `role: ClauseRole` (enum: `ConstraintLiteral`, `CardinalityCounter`, `CardinalityExclusion`, `Unit`), and `aux_block_id: Option<usize>` (identifying which sequential-counter block, if any).

- **R2.** The `SatVariable.description` field SHALL be populated for auxiliary variables with a string identifying the originating constraint and role (e.g. `"seq-counter for Capacity[2] CH1 r0.0"`).

- **R2.1.** The `encode_at_most_k` function in `encoding.rs` SHALL accept a `constraint_label: &str` parameter used to populate auxiliary variable descriptions (e.g., `"seq-counter for Capacity[2] CH1 r0.0"`).

- **R3.** The provenance metadata SHALL add less than 100% memory overhead compared to the current encoding. A denser packed representation (`u16 constraint_idx, u8 role, u16 aux_block_id` with sentinel for `None` = 5 bytes) can achieve ~40% overhead for 3-literal clauses.

### R-IDs: Pre-Solve Tension Detection

- **R4.** A `detect_tensions(model: &InternalConstraintModel) -> Vec<TensionViolation>` function SHALL check for analytically-incompatible constraint pairs. A `TensionViolation` contains `constraint_pair: (usize, usize)` (indices into model.constraints), `channel_id: String`, `explanation: String`, and `severity: TensionSeverity` (enum: `HardConflict` for provable UNSAT, `CapacityWarning` for near-boundary situations).

- **R5.** Tension detection SHALL detect at minimum:
  - **Capacity oversubscription**: For each channel, if the sum of minimum net widths for nets that MUST use this channel (all others banned by layer restrictions) exceeds `capacity * slack_factor`, flag as `HardConflict`
  - **Diff-pair vs. capacity**: If a DiffPair constraint targets a channel with capacity < 2 after accounting for must-use nets from other constraints, flag as `HardConflict`
  - **Layer-restriction starvation**: If a net has exactly one allowed channel (all others banned) and that channel's capacity is exhausted by must-use nets, flag as `HardConflict`
  - **Mutually-exclusive assignment**: If layer restrictions on two nets in a diff pair ban ALL shared channels, flag as `HardConflict`

- **R6.** Tension detection SHALL run in O(c²) time where c is the number of constraints. For c < 50 (typical for a 30-net routing problem with 2-3 channels), wall time SHALL be < 1 second.

- **R7.** Tension detection SHALL NOT modify the constraint model or the CNF — it is a read-only analytical pass.

### R-IDs: UNSAT Core Reverse-Mapping

- **R8.** A `find_unsat_core(cnf: &CnfFormula, model: &InternalConstraintModel) -> ConflictReport` function SHALL produce structured conflict diagnostics when the solver returns UNSAT. The function SHALL use the DRAT proof post-processing method: enable splr's `save_certification()`, run the solver, post-process the DRAT proof with `drat-trim` to extract the core clauses, then map core clause indices to provenance records.

- **R9.** The `ConflictReport` SHALL contain: `conflicting_constraints: Vec<(usize, String)>` (constraint index + description), `channels_involved: Vec<String>`, `explanation: String` (human-readable), and `core_clause_count: usize`.

- **R10.** The reverse-mapping SHALL handle auxiliary clauses from the sequential-counter encoding gracefully: if a cardinality counter clause appears in the core, the report maps it to the originating Capacity constraint (not to "anonymous auxiliary clause"), using the provenance metadata from R1.

- **R11.** Core extraction SHALL NOT require modifying splr's source code. It uses splr's existing `save_certification()` API plus `drat-trim` for proof post-processing.

### R-IDs: Integration

- **R12.** The `solve_with_splr` function SHALL run tension detection before the SAT solve and return tension results in `TopologyResult` even when the result is SAT (tensions are warnings, not errors).

- **R13.** When `solve_with_splr` returns `Unsatisfiable`, the `TopologyResult.unsat_core` field SHALL be populated with structured `ConflictReport` data (replacing the current empty `Vec::new()`).

- **R14.** The Python-facing `solve_topology_rust` return dict SHALL include a `"tensions"` key (list of tension dicts) and a `"conflicts"` key (conflict report dict, present only on UNSAT).

- **R15.** The pipeline at `pipeline.py:632-633` SHALL log `HardConflict` tensions and UNSAT conflicts at `INFO` level (always visible). `CapacityWarning` tensions SHALL be logged at `DEBUG` level or gated by a `verbose` flag. The pipeline SHALL raise no exception on UNSAT. The pipeline SHALL skip the constraint audit (`audit_result` in `pipeline.py:664`) when `status == 'unsat'`, because the new `conflicts` field replaces the `UnexplainedUnsat` diagnostic. The pipeline's existing `audit_result` call SHALL continue to fire on SAT results unchanged.

- **R16.** The SAT case (solver returns SAT) SHALL experience zero performance regression: tension detection runs once per model (not per solve attempt), and the additional `.description` strings on auxiliary `SatVariable`s do not affect the solver's hot path.

- **R17.** When solver status is `Unknown` (panic/timeout), tension detection results SHALL still be reported (computed pre-solve). The `conflicts` field SHALL be absent. The pipeline SHALL treat `Unknown` as indeterminate — neither SAT nor UNSAT — and surface a warning.

- **R18.** If UNSAT core extraction fails (timeout, OOM, DRAT post-processing error), the pipeline SHALL surface the pre-solve tension detection results as the primary diagnostic and emit an `UnexplainedUnsat` audit violation as a fallback marker.

---

## Acceptance Examples

### AE1: Capacity oversubscription with layer restriction

**Setup**: 3 nets (N0, N1, N2) on channel CH1. Capacity constraint limits CH1 to 2 nets. Layer restriction bans N0 from all other channels (CH1 is the only allowed channel for N0).
```
Input:
  Capacity(channel_id="CH1", capacity=2.0, slack=1.0, terms=[("N0",1), ("N1",1), ("N2",1)])
  LayerRestriction(var_name="N0_CH1", allowed=true)  # implied: N0 banned from CH2, CH3, ...
  LayerRestriction(var_name="N0_CH2", allowed=false)
  LayerRestriction(var_name="N0_CH3", allowed=false)
  # No restrictions on N1, N2 — they can go anywhere
```
**Expected tension**: None (hard). N0 must use CH1, but N1 and N2 can go elsewhere — capacity is not forced oversubscribed.

**Same setup, add**: Layer restrictions also force N1 and N2 to CH1.
```
Additional:
  LayerRestriction(var_name="N1_CH2", allowed=false)  # N1 only CH1
  LayerRestriction(var_name="N2_CH2", allowed=false)  # N2 only CH1
```
**Expected pre-solve tension**: `HardConflict` on CH1 — 3 must-use nets, capacity 2. Explanation: "Channel CH1 capacity (2 nets) cannot accommodate 3 nets that have no other allowed channels: N0, N1, N2."

**Expected solver behavior**: UNSAT (provably).

### AE2: Diff-pair incompatibility with single-channel capacity

**Setup**: DiffPair requires p_N0 and n_N0 on the same channel. Capacity on CH1 is 1. CH1 is the only channel available to both.
```
Input:
  DiffPair(channel_id="CH1", p_var_name="p_N0_CH1", n_var_name="n_N0_CH1")
  Capacity(channel_id="CH1", capacity=1.0, slack=1.0, terms=[("p_N0_CH1",1), ("n_N0_CH1",1)])
  # No other channels exist
```
**Expected pre-solve tension**: `HardConflict` on CH1. Explanation: "Diff pair requires both p_N0 and n_N0 on channel CH1, but CH1 capacity is 1 (only 1 net allowed)."

**Expected UNSAT core**: The 4 clauses from the DiffPair encoding (2 × equivalence clauses) + 2 capacity clauses (the CNF encoding of AtMostK with k=0 for surplus = AtMostK(2, 1)) form the core. Reverse-mapped to: "DiffPair 'diff_N0_CH1' conflicts with Capacity 'cap_CH1'."

**Expected output**:
```json
{
  "status": "unsat",
  "conflicts": {
    "explanation": "Diff pair 'diff_N0_CH1' requires both p_N0 and n_N0 on CH1, but capacity 'cap_CH1' limits CH1 to 1 net",
    "constraints": ["DiffPair:p_N0,n_N0@CH1", "Capacity:CH1≤1"],
    "channels": ["CH1"],
    "core_clause_count": 6
  },
  "tensions": [
    {
      "severity": "hard_conflict",
      "channel_id": "CH1",
      "explanation": "Diff pair requires both p_N0 and n_N0 on channel CH1, but CH1 capacity is 1 (only 1 net allowed)",
      "constraint_pair": [0, 1]
    }
  ]
}
```

---

## Success Criteria

- SC1. A designer can understand WHY the solver failed without reading CNF clause dumps. The `conflicts.explanation` field names specific constraints, channels, and nets in a single sentence.
- SC2. Tension detection catches analytically-conflicting constraint pairs in O(c²) time where c is the constraint count, completing in < 1 second for c < 50 (the typical range for Temper's 10-100 net routing problems).
- SC3. Provenance metadata adds < 100% memory overhead per clause (measured on the 228K-variable worst-case model, comparing peak RSS of the current encoder vs. provenance-instrumented encoder). A denser packed representation can achieve ~40% overhead.
- SC4. SAT-case performance is unchanged: tension detection runs once before the solve (not in the solver's hot loop), and auxiliary variable `.description` strings do not affect solver execution.
- SC5. No false-positive `HardConflict` tensions (every `HardConflict` flagged by tension detection must be provably UNSAT). False negatives (UNSAT cases not caught by pre-solve) are acceptable — the SAT solver catches the remaining UNSAT cases. The pre-solve check is a fast-path filter, not a replacement for the solver. `CapacityWarning` tensions may be false positives (near-boundary heuristics).

---

## Scope Boundaries

- **Does NOT modify splr source code**. splr is consumed as a Cargo dependency at version 0.13. The DRAT proof post-processing method for core extraction uses splr's existing `save_certification()` API only.
- **Does NOT suggest fixes for conflicts**. The feature explains WHAT is wrong, not how to fix it. Suggesting design changes (e.g. "increase channel capacity" or "add a new routing layer") is out of scope.
- **Does NOT change the existing constraint types**. `InternalConstraint` remains unchanged — Capacity, DiffPair, LayerRestriction. The 3-variant constraint ISA is the ground truth.
- **Does NOT add incremental solving or timeout-based partial solutions**. The scope is diagnostics, not solver heuristics.
- **Does NOT integrate with PCL or the constraint-lowering compiler** (that feature is covered by `docs/brainstorms/2026-06-28-constraint-lowering-compiler-requirements.md` R9). This feature operates at the `InternalConstraint` level only. The provenance chain stops at `InternalConstraint` names — mapping further back to PCL constraint IDs is deferred to the compiler.

---

## Key Decisions

- **KD1. Core extraction method: DRAT proof post-processing**. splr's `Certificate::UNSAT` is a unit variant with no core data. The selector-literal method cannot work because `Certificate::UNSAT` returns no core — `unsat_core` at `solver.rs:67-69` is always empty. Core extraction SHALL use the DRAT proof output method (`save_certification()` → `drat-trim` post-processing) as the primary approach. This does not require modifying splr's source code (uses the existing `save_certification()` API). The selector-literal method is noted as a possible future optimization if splr gains assumption-based UNSAT core support.

- **KD2. Tension detection runs BEFORE the solve, not after**. The constraint model is deterministic given the same input — tension results are invariant across solver runs. Running before the solve means the designer sees warnings even when the solver eventually finds SAT (near-boundary capacity situations). Running after would hide tensions on SAT models, which are the most actionable warnings.

- **KD3. `CapacityWarning` tier for near-boundary tensions**. Not all tension hits are `HardConflict`. A channel at 90% capacity is not provably UNSAT — the solver might still find an assignment. `CapacityWarning` is a heuristic tier that surfaces near-boundary situations without claiming provable unsat. This prevents the "cried wolf" problem where false-hard-conflicts erode designer trust.

- **KD4. Provenance is per-clause, not per-variable**. Variables can appear in clauses from multiple constraints (especially when a net participates in both a Capacity and a DiffPair constraint). Tracking provenance per-variable would require conflict-resolution logic. Tracking per-clause is unambiguous: each clause has exactly one origin.

---

## Dependencies / Assumptions

- **DA1. `splr::Config.use_certification` is required**. The DRAT proof post-processing method requires splr's `save_certification()` API (enabled via `splr::Config::default().use_certification(true)`).

- **DA2. Clause identity is stable across the encoding pipeline**. The order of clauses in `CnfFormula.clauses` is deterministic given the same `InternalConstraintModel` input. The DRAT proof post-processing method requires clause IDs in the DRAT proof to match the provenance table indices.

- **DA3. splr does not panic on models with selector variables**. The existing `catch_unwind` wrapper in `solver.rs:51` handles panics. But selector-literal models are larger — we assume splr can handle the variable/clause counts without hitting internal limits.

- **DA4. The `InternalConstraintModel` passed to tension detection is the same model passed to `encode_to_cnf`**. They are built from the same Python input data in the same pipeline step (`pipeline.py:610-622`). No desynchronization possible.

---

## Outstanding Questions

### Resolve Before Planning

- **OQ1.** DRAT proof post-processing: what is the runtime overhead of `drat-trim` on a typical 30-net routing model's UNSAT proof? The DRAT approach requires running an external proof checker after the solve. Does `drat-trim` complete within the existing timeout budget (5s)?

- **OQ2.** Is there a splr feature flag or API we've missed that provides in-memory core access? The splr source (`solver/mod.rs:29-34`) shows `Certificate::UNSAT` as a unit variant with no data. But splr has a `conflict.rs` module with `analyze_final` — does that function have side-channel access to the conflicting clause set?

- **OQ3.** For the pre-solve tension pass: what is the actual constraint count c for the largest routing problem Temper encounters (worst-case: all nets on a dense board, 100+ nets)? The O(c²) budget is stated for c < 50. If c routinely exceeds 100, the analysis may need pruning.

### Deferred to Planning

- **DQ1.** Tension detection SHALL be a new module `tension.rs` in `temper-rust-router` (same crate as `solver.rs`). Rationale: it shares the `InternalConstraintModel` type and has no external dependencies.
- **DQ2.** Should `ConflictReport` be a new type in `types.rs` or a re-extension of the existing `unsat_core` field?
- **DQ3.** What is the Python-side data model for tension/conflict objects — dicts with string keys (like the existing bridge) or proper `@dataclass`es?
- **DQ4.** Should tension detection run unconditionally or be gated by a `TEMPER_SAT_DIAGNOSTICS` environment variable?
