---
date: 2026-07-01
topic: quality-oracle-typed-pipeline
---

# Typed Quality Oracle Pipeline

## Summary

A standalone Rust quality oracle crate that makes incorrect states unrepresentable across the six-layer placement-quality pipeline. Every layer handoff is typed so the pipeline cannot be wired wrong at compile time. Metric computation stays in Python/JAX but crosses a typed Rust boundary; the entire oracle is a pure function fuzzable and provable in isolation.

---

## Problem Frame

The current six-layer quality pipeline — net classification → constraint derivation → quality config → metric computation → threshold definition → pass/fail oracle — passes untyped `dict[str, Any]` dictionaries across every handoff. A misclassified net, a missing key, or a silently out-of-range score propagates undetected through the entire path. The project has dozens of hypothesis property-based tests, but no type-level enforcement linking a net's classification to its clearance requirement, a derived constraint to its spec source, or a quality score to its [0,1] contract. The pass/fail oracle is scattered across multiple files (validation_gates, quality_score, drc_types) with no single source of truth, and no systematic induction proofs to guarantee that correctness on N components implies correctness on N+1.

The cost of this is systemic low confidence: every change to the pipeline risks a silent correctness regression, and there is no automated oracle to say "this placement would pass IPC-2221." This project instruments the full pipeline as a typed, testable, provable unit.

---

## Actors

- A1. **Python optimizer**: Computes candidate placements using JAX; calls the Rust oracle to judge placement quality.
- A2. **CI pipeline**: Runs the oracle as a gate on every PR to verify quality thresholds have not regressed.
- A3. **Developer**: Writes and runs tests, debugs quality regressions, adds new constraint types.

---

## Key Flows

- F1. **Placement Quality Check**
  - **Trigger:** Optimizer produces a candidate placement.
  - **Actors:** A1
  - **Steps:** Optimizer computes physics metrics in Python/JAX → passes scores + placement state + pcb_spec + netlist to the Rust oracle → oracle classifies nets, derives constraints, populates quality config, checks all thresholds → returns typed Pass/Fail verdict with metrics and any violations.
  - **Outcome:** Verdict used to guide optimization or reject the placement.
  - **Covered by:** R1, R2, R7, R8

- F2. **CI Quality Gate**
  - **Trigger:** PR is opened or updated.
  - **Actors:** A2
  - **Steps:** CI loads reference design + spec → runs optimizer → calls oracle → compares verdict against golden baseline → fails PR if quality degraded.
  - **Outcome:** PR blocked or allowed based on oracle pass/fail.
  - **Covered by:** R1, R7, R8, R13

- F3. **Property-Based Test Run**
  - **Trigger:** `cargo test` or CI test suite.
  - **Actors:** A3
  - **Steps:** proptest generates random netlists, pcb_specs, placements → oracle runs the full six-layer roundtrip → asserts invariants hold across all generated inputs.
  - **Outcome:** Failing test if any invariant is violated.
  - **Covered by:** R10, R11, R12

---

## Requirements

**Oracle crate and interface**

- R1. The oracle is a standalone Rust crate with a single entry-point function that maps `(PcbSpec, Netlist, Placement, PrecomputedMetrics) → QualityVerdict`, exposed via PyO3.
- R2. Every internal layer handoff uses a typed struct or enum — no `dict[str, Any]` crosses any internal boundary. Construction-time invariants prevent invalid states from existing at rest.

**Type system**

- R3. `NetClass` is a closed enum (`Hv`, `Lv`, `Ac`, `GateDrive`, `Signal`) with exhaustive pattern matching. Classification is deterministic. The enum variants are the canonical source of truth; the pattern-matching rules from `router_v6/net_classification.py` and the name-string mapping from `router_v6/net_ordering.py` are both mapped to this single enum.
- R4. `NormalizedScore` is a `newtype(f64)` that enforces `0.0 <= value <= 1.0` at construction via `Result<NormalizedScore, ScoreError>`. Panic is reserved for debug/test builds only; release builds return an error so the optimizer can treat out-of-bounds scores as rejected candidates without aborting.
- R5. IPC-2221 clearance is a typed monotonic bracket list (0-15V, 16-30V, 31-50V, 51-100V, 101-150V, 151-170V, 171-250V, 251-300V, 301-600V, 601-1000V). This bracket table is the canonical source of truth; the Python `router_v6/creepage_check.py` table is derived from it. A CI test asserts equivalence between the two copies.
- R6. Derived constraints enforce non-negative distances and clearances at construction. Loop component groups enforce a minimum of 3 components (polygon constraint).

**Correctness**

- R7. The oracle must never return `Pass` for a placement that violates IPC-2221 clearance requirements (no false passes on creepage/clearance).
- R8. The oracle must never return `Pass` for a placement that exceeds pcb_spec.yaml loop-area limits or thermal limits. This guarantee is conditional on Python-computed `PrecomputedMetrics` until those metric functions are also migrated to Rust; the Python metrics are marked for eventual deprecation.
- R9. The oracle is deterministic: same inputs always produce the same verdict and identical metric values.

**Testing strategy**

- R10. Unit tests cover base cases: empty board, single component, single net — classification is trivial, all constraints are empty, verdict is always `Pass`.
- R11. Property-based tests verify clearance monotonicity: for any placement, adding a component can only add clearance violations, never remove them. Loop-area monotonicity is tested separately with scenarios that exercise loop-grouping boundary changes where re-grouping could reduce violation counts.
- R12. Property-based tests verify constructor invariants (`NormalizedScore` bounds, non-negative distances, loop polygon size >= 3, IPC-2221 bracket monotonicity).
- R13. Property-based tests verify the full pipeline roundtrip (classify → derive → configure → threshold → verdict) never panics on any valid input. Test harnesses generate synthetic `PrecomputedMetrics` to exercise the judgment stages.
- R14. E2E tests drive the full oracle through PyO3 from the Python test suite, comparing oracle verdicts against expected outcomes for known-good and known-bad reference placements.

**Rust-Python safety**

- R15. All PyO3 FFI boundaries use `catch_unwind`. A Rust panic is always converted to a Python exception — the crate never aborts the Python process.

---

## Acceptance Examples

- AE1. **Covers R7.** Given a placement where an HV net (230V) is 2mm from an LV net (signal), and IPC-2221 requires 8mm clearance for voltages 251-300V, the oracle returns `Fail` with a `CreepageInsufficient` violation citing actual=2mm and required=8mm.

- AE2. **Covers R8.** Given a placement where the `gate_drive_loop` polygon area is 120mm² and `pcb_spec.yaml` specifies `max_loop_area_mm2.gate_drive_loop: 30`, the oracle returns `Fail` with a `LoopAreaExceeded` violation.

- AE3. **Covers R4.** Constructing `NormalizedScore(1.2)` returns `Err(ScoreError)`. Constructing `NormalizedScore(-0.1)` returns `Err(ScoreError)`. `NormalizedScore(0.73)` returns `Ok(score)`. In debug/test builds, out-of-bounds construction panics.

- AE4. **Covers R15.** Calling the oracle from Python with a malformed input that triggers a Rust `unwrap()` on `None` produces a Python `RuntimeError`, not a segfault or process abort.

---

## Success Criteria

- Zero type-related bugs (wrong string key, missing dict field, `None` propagation) survive to the oracle boundary — the Rust compiler catches them.
- Proptest catches any constructor invariant violation before the PR merges.
- A developer adding a new `NetClass` variant gets a compile-time error on every `match` arm in the codebase, not a runtime surprise.
- The Rust oracle produces pass/fail verdicts that match the existing Python pipeline for all current test cases (parity gate).
- Clearance monotonicity is verified by proptest; loop-area monotonicity boundary cases are explicitly tested.

---

## Scope Boundaries

- The JAX optimizer, routing engine (`router_v6`), and existing DRC engine (`temper-drc-rs`) are unchanged — the oracle is the judgment, not the optimization or routing.
- The existing Python quality judgment code (`validation_gates`, `quality_score`, `drc_types`) is deprecated and replaced by the Rust oracle. The Python pipeline persists as the parity reference during the transition.
- No regulatory certification automation (UL, CE). This project is correctness infrastructure, not compliance tooling.
- No performance benchmarking of Rust vs Python — peak throughput is not a deliverable.
- No changes to the KiCad parser, DSN export, or board file I/O.

---

## Key Decisions

- **New crate, not modification of existing Rust crates.** The quality oracle is a separate concern from the constraint solver (`temper-constraints`) and the DRC engine (`temper-drc-rs`). It depends on their types but does not live inside them.
- **Metric computation stays in Python/JAX.** The JAX compute graph for wirelength, congestion, clustering, etc. is deeply coupled to the optimizer. Only the resulting score values cross the Rust boundary as typed `NormalizedScore` newtypes.
- **Closed `NetClass` enum, not extensible.** The fixed taxonomy (HV, LV, AC, GateDrive, Signal) covers the project's current domain. If a new class is needed later, adding it to the enum is a deliberate breaking change that triggers compile-time exhaustiveness checks.
- **Construction-time error, not panic.** A `NormalizedScore` outside [0,1] returns a `Result::Err` in release builds so the optimizer can reject invalid candidates without aborting. Panic is reserved for debug/test builds where an out-of-bounds score signals a genuine bug.
- **Python compute path is a bridge, not a permanent split.** The Python/JAX metric functions are marked for eventual deprecation. New constraints are added in Rust from the start; existing Python metrics migrate over time. This avoids the ongoing coordination cost of a permanent two-language split.

---

## Dependencies / Assumptions

- **Depends on:** `temper-constraints` Rust crate (PCL constraint types), `temper-drc-rs` crate (DRC types for clearance/zone definitions), `pyo3` for Python bindings.
- **Assumes:** The `pcb_spec.yaml` format is the stable source of truth for performance targets. The Rust bracket table for IPC-2221 is canonical; the Python `creepage_check.py` table is derived and checked by CI parity test.
- **Assumes:** The existing Python metric functions (`total_wirelength`, `thermal_score`, `zone_compliance_score`, etc.) serve as the initial compute path but are marked for eventual deprecation and migration to Rust.
- **Assumes:** `proptest` is available in the Rust ecosystem and can generate synthetic netlists and placements of sufficient complexity.

---

## Outstanding Questions

### Deferred to Planning

- [Needs research] Exact crate name and location under `packages/`.
- [Affects R13][Technical] Whether proptest strategies share code with existing Python hypothesis strategies, or are independent reimplementations.
- [Affects R1][Technical] Serialization format for passing scores + placement state across the PyO3 boundary (numpy array views vs owned `Vec<f64>` vs serialized struct).
- [Affects R5][Technical] Whether the IPC-2221 bracket table should be a `const` generic array or loaded from a YAML/toml config at crate initialization.
