---
title: "Pattern: Typed Rust Quality Oracle with PyO3 — Making Incorrect States Unrepresentable Across a Six-Layer PCB Placement Pipeline"
date: 2026-07-01
category: architecture-patterns
module: temper-quality-oracle
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "A multi-stage pipeline has a quality-assessment concern that crosses Python-Rust boundaries"
  - "Intermediate pipeline states carry correctness invariants that are unenforced in the existing Python type system"
  - "A greenfield Rust crate with PyO3 bindings can replace runtime checks with compile-time type proofs"
tags:
  - rust
  - pyo3
  - quality-oracle
  - pcb
  - type-safety
  - pipeline
  - invariant-chain
  - compile-time-guarantee
---

# Pattern: Typed Rust Quality Oracle with PyO3

## Context

The temper PCB project's quality evaluation pipeline was built on untyped `dict[str, Any]` — no schema enforcement, no compile-time verification, no single source of truth. Scores, classifications, constraints, and violations flowed through Python functions as opaque dictionaries. When a metric key was misspelled, a constraint was dropped, or a violation type was wrong, the pipeline silently produced incorrect pass/fail verdicts.

The gap: correctness-critical PCB safety decisions (creepage, thermal clearance, loop area) were being made by a pipeline that could not guarantee type consistency, exhaustiveness, or bounds validation.

## Guidance: Typed Quality Oracle as a Standalone PyO3 Crate

The architectural pattern replaces an untyped multi-language pipeline with a **single Rust crate** exposed to Python via PyO3. Six typed pipeline layers form a linear invariant chain.

### 1. Standalone Rust Crate with Dual Crate Types

```toml
# Cargo.toml
crate-type = ["cdylib", "rlib"]
# cdylib → Python .so; rlib → Rust unit/proptest tests
```

The crate compiles to both a native shared library (imported by Python) and a static library (imported by other Rust crates in the workspace). Tests run in both languages: Rust `#[test]` + `proptest!` for property-based testing, Python `pytest` for E2E verification through the actual PyO3 bindings.

CI integration follows the existing temper pattern: `uvx maturin develop --release` to build, import verification step, and `cargo test --lib` for Rust-native test execution.

### 2. Closed-Enum Type System as Single Source of Truth

Every pipeline concept is a Rust `enum` or `struct`, not a string literal:

- `NetClass` (7 variants) — compile-time exhaustiveness in all match arms
- `NormalizedScore` (newtype) — [0,1] bounds enforced at construction, not at use
- `QualityVerdict` (enum) — Pass/Fail carries structured payloads, not bare booleans
- `Violation` — typed violation_type, actual_value, required_value

**NormalizedScore newtype pattern** (from `src/types.rs`):

```rust
pub struct NormalizedScore(f64);

impl NormalizedScore {
    pub fn new(value: f64) -> Result<Self, ScoreError> {
        if value.is_nan() { return Err(ScoreError::NaN); }
        if value < 0.0 || value > 1.0 { return Err(ScoreError::OutOfRange { value }); }
        Ok(NormalizedScore(value))
    }
}
```

All 7 metric scores enter Rust as raw `f64` via `PrecomputedMetrics` and are validated into `NormalizedScore` at the boundary. Any out-of-range or NaN score produces an `InvalidMetric` violation instead of silently corrupting the pipeline. Missing Python metric keys default to `0.0` (conservative) — a missing metric cannot cause a false Pass.

### 3. Six-Layer Invariant-Chain Pipeline

```
classify_nets()  →  Vec<NetClassification>
       ↓
derive()         →  DerivedConstraints
       ↓
build_config()   →  QualityConfig
       ↓
QualityMetrics::from_precomputed()  →  QualityMetrics  (with validated NormalizedScores)
       ↓
evaluate()       →  Vec<Violation>
       ↓
evaluate_quality() → QualityVerdict::Pass | QualityVerdict::Fail
```

Each layer consumes the typed output of the previous layer. There is no dictionary passthrough — every struct field is statically known. The pipeline is a single pure function:

```rust
pub fn evaluate_quality(
    spec: &PcbSpecification,
    netlist: &Netlist,
    placement: &PlacementState,
    precomputed: &PrecomputedMetrics,
) -> QualityVerdict { ... }
```

### 4. Construction-Time Validation

`DerivedConstraints` has a manual `Default` impl that sets `hv_lv_isolation_mm: 6.5` — it is impossible to create a constraints object without an isolation value. `QualityMetrics::from_precomputed()` returns `Result<Self, ScoreError>`, meaning downstream code cannot accidentally use unvalidated scores. `QualityConfig::min_hv_lv_clearance_mm` is populated directly from `constraints.hv_lv_isolation_mm`, not from a string-keyed dict lookup that silently returns None.

### 5. catch_unwind at the PyO3 Boundary

All `#[pyfunction]` bodies wrap their logic in `catch_unwind`:

```rust
fn catch_unwind_pyobj(f: impl FnOnce() -> PyResult<PyObject>) -> PyResult<PyObject> {
    match panic::catch_unwind(panic::AssertUnwindSafe(f)) {
        Ok(result) => result,
        Err(panic_info) => {
            let msg = ...;
            Err(PyRuntimeError::new_err(format!("temper_quality_oracle panic: {msg}")))
        }
    }
}
```

Rust panics are caught and converted to `PyRuntimeError` instead of aborting the Python process.

### 6. Dual-Language Testing Strategy

- **Rust unit tests** in every source module — fast, no Python dependency
- **proptest** — `pbt_oracle_empty_board_always_passes`, `pbt_oracle_deterministic`, `pbt_clearance_monotonicity_adding_component`, `pbt_roundtrip_no_panic`, `pbt_normalized_score_bounds` — 7 property-based tests
- **Python E2E tests** — call `evaluate_quality_py()` with real dict inputs, verify IPC-2221 bracket parity against Python `_calculate_required_creepage()`

### 7. Static Const Table with Monotonicity Check

The IPC-2221 clearance table is a `const` array with a `verify_monotonic()` function. The invariant is checked by a unit test, preventing accidental corruption of the bracket boundaries.

## Why This Matters

- **Silent bugs become compile errors.** A misspelled metric key doesn't return `None` — it fails to compile. An unhandled `NetClass` variant in a `match` is a compiler warning.
- **Single source of truth.** Net classes, IPC-2221 brackets, constraint categories, and violation types exist in exactly one place with one authoritative definition.
- **Bounds violations are impossible downstream.** Once `NormalizedScore::new()` validates a score, every consumer receives a value guaranteed `0.0..=1.0`.
- **Determinism is testable.** Property-based tests assert that the same inputs produce the same verdict — trivial to verify because `evaluate_quality()` is a pure function.
- **The boundary is the only fallible layer.** Python dict extraction may fail with `PyValueError`, but once data enters the Rust pipeline, there are no more dict lookups — only typed struct field access.
- **Proptest caught a real bug during development.** The `pbt_oracle_empty_board_always_passes` test discovered that `evaluate_loop_areas` was unconditionally checking the loop-area score on empty configs, producing false violations. The fix — gating on `loop_components.is_empty()` — was applied before any code review.

## When to Apply

- When building a **correctness-critical pipeline** that crosses Python-Rust boundaries, especially for physical safety or regulatory compliance domains
- When the existing pipeline uses **untyped dicts as the inter-stage protocol** and you've had bugs from key typos, missing fields, or wrong types
- When you need **exhaustive coverage guarantees** across a fixed set of variants
- When both **fast Rust-native tests** (milliseconds) and **E2E integration tests** (PyO3 round-trip) are needed
- When the pipeline is **a pure function** — stateless, deterministic, consuming references and producing a verdict

## Examples

**Classification with precedence.** First-match-wins (`Ground > Power > HighVoltage > Differential > HighCurrent > GateDrive > Signal`) with compile-time exhaustiveness. Each net name is tested against 6 pattern sets; if no match, `Signal` is the explicit fallback.

**Pipeline composition.** A single 4-line call sequence — classify, derive, configure, evaluate — produces a `QualityVerdict`. Type signatures prevent accidentally passing classifications to the threshold evaluator instead of to the config builder.

**HV-LV clearance wired end-to-end.** `constraints.hv_lv_isolation_mm` (6.5mm) flows through `QualityConfig.min_hv_lv_clearance_mm` into `evaluate_clearance()` as a typed `f64`. No string-keyed dict lookup that can silently return None if renamed.

**IPC-2221 lookup with ceiling behavior.** Linear scan over a const array of 10 brackets. Above 1000V, the highest defined clearance (12.0mm) is returned. No `IndexError` from a dict, no missing keys.

## Related

- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — sibling pattern: typed Rust solver behind PyO3 for correctness-critical PCB tooling
- `docs/solutions/tooling-decisions/splr-to-rustsat-cadical-solver-migration-2026-06-29.md` — canonical "how to build a typed Rust solver behind PyO3 in temper"
- `docs/solutions/best-practices/hypothesis-invariant-test-suite-pattern-2026-06-28.md` — four-layer PBT suite structure used here
- `docs/solutions/architecture-patterns/4layer-invariant-chain-boundary-enforcement-2026-06-30.md` — invariant-chain pattern applied across the six pipeline layers
- `docs/solutions/logic-errors/clearance-false-negatives-per-net-pair-2026-06-28.md` — completeness-oracle pattern: brute-force vs. production engine verification
