---
date: 2026-07-01
topic: profiling-guided-rust-extraction
---

# Profiling-Guided Rust Extraction — Constraint Engine First

## Summary

Profile the temper pipeline end-to-end to produce a per-stage performance heatmap. Extract the highest-impact, most self-contained compute kernels to Rust via PyO3+maturin — starting with the PCL constraint engine — using a station-by-station strategy where each extracted stage implements the same `StageHandler` interface and is swappable via the DAG manifest.

---

## Problem Frame

Router v6 is 80+ files with Numba/A*/SAT and the PCL constraint engine is correctness-critical but Python-only. There is no profiling data to guide extraction priority. A big-bang Rust rewrite of the entire pipeline would block all other work for months. Station-by-station extraction with profiling guidance solves the migration problem incrementally: each extraction is benchmarked against its Python predecessor before the next begins, and Rust migration is a background activity rather than a release-blocking rewrite.

The constraint engine (`pcl/constraints.py` + `pcl/loss_bridge.py`, ~1200 lines) is the ideal first target: it is small, self-contained, correctness-critical (keepout, decoupling, spacing), consumed by both CLI and DAG pipeline, and naturally expressed in Rust's type system — enum-based constraint types with exhaustive match eliminates the class of bug where a constraint is modeled but not applied by every consumer.

---

## Actors

- **A1. Pipeline developer**: Profiles pipeline stages, identifies hot paths, implements Rust extractions behind the `StageHandler` interface
- **A2. CI system**: Builds Rust crate, runs integration tests proving Python<->Rust wiring, benchmarks against Python baseline
- **A3. Pipeline operator**: Runs `temper optimize`, benefits from faster constraint evaluation without knowing or caring if Rust is involved

---

## Key Flows

- **F1. Profiling-guided extraction target selection**
  - **Trigger:** Pipeline developer runs `temper profile` against a benchmark board
  - **Actors:** A1
  - **Steps:** Profile produces per-stage wall-clock / memory heatmap; developer identifies the highest-impact, most self-contained stage; developer extracts that stage's compute kernel to Rust behind the same `StageHandler` interface; benchmark validates before/after performance delta
  - **Outcome:** Each extraction has a quantified performance delta
  - **Covered by:** R1, R2, R3

- **F2. CI-integrated Rust extraction pipeline**
  - **Trigger:** PR adds or modifies a Rust extraction
  - **Actors:** A2
  - **Steps:** CI builds Rust crate with maturin on macOS and Linux; runs `cargo test` for Rust unit tests; runs Python integration tests that invoke the Rust backend through PyO3; runs benchmark comparison against Python baseline; gates on performance regression
  - **Outcome:** Rust extractions are verified as wired, correct, and non-regressive
  - **Covered by:** R4, R5, R6, R7, R8, R12

---

## Requirements

### Extraction Strategy

- **R1.** The pipeline is profiled end-to-end to produce a per-stage wall-clock and memory heatmap. Profiling must complete before the second Rust extraction begins; it is not required to gate the first extraction (PCL constraint engine).
- **R2.** Extraction targets after the first (PCL constraint engine) are selected by three criteria applied in order: (1) measured compute intensity from profiling data, (2) self-contained interface surface area (minimal cross-stage coupling), (3) correctness criticality. Correctness criticality takes priority over compute intensity for kernels within 2x of the hottest kernel. The first extraction target (PCL constraint engine) is pre-selected regardless of profiling data because of its correctness-critical nature and self-contained interface.
- **R3.** Each Rust extraction implements the same `StageHandler` interface as its Python predecessor and is swappable via the DAG manifest — Python fallback is automatic when the Rust crate is not installed.

### First Extraction: PCL Constraint Engine

- **R4.** PCL constraint types (`KeepoutZone`, `SpacingRule`, `DecouplingRule`, `TagGroup`) are modeled as Rust enums with exhaustive match semantics, ensuring every constraint variant is handled by every consumer at compile time.
- **R5.** PCL loss bridge functions (`keepout_loss`, `spacing_loss`, `decoupling_loss`, `tag_expansion`) are implemented in Rust and exposed via PyO3 bindings as callable Python functions.
- **R6.** The Rust constraint engine produces loss values identical to the Python implementation on a golden corpus of 10+ board placements within floating-point tolerance (1e-6).

### CI and Verification

- **R7.** CI builds the Rust crate on macOS and Linux, runs `cargo test`, and runs Python integration tests that invoke the Rust backend through PyO3.
- **R8.** CI includes a benchmark gate: a PR that extracts a stage to Rust must include before/after wall-clock metrics on the golden corpus. CI compares the benchmark p50 of 5 runs against the registered baseline; the gate rejects the PR if the p50 regresses by more than 2 standard deviations of the baseline's own variance. The gate starts as warn-only and becomes blocking after a 2-week calibration period to establish baseline variance for each extraction target.
- **R9.** A positive integration test proves the Rust backend is wired — if PyO3 import fails or the Rust function is never called, the test fails (preventing the infrastructure-unwired failure mode where components are tested in isolation but never connected).

### Operational

- **R10.** Rust extraction is an additive, non-breaking change — Python fallback works transparently when the Rust crate is not installed, with a one-time informative log message.
- **R11.** `pyproject.toml` includes maturin build configuration for both macOS and Linux targets, making `pip install` the only step needed to enable Rust acceleration.

- **R12.** CI runs an integration test that exercises all constraint types through both the Rust and Python engines on every PR, asserting identical loss values within floating-point tolerance (1e-6). If a new constraint type is added to Python without a Rust equivalent, the test fails because the Rust engine returns a NotImplemented error for unknown constraint types.

- **R13.** The first Rust extraction (PCL constraint engine) must demonstrate >= 50% wall-clock reduction on the golden corpus of 10+ board placements (benchmark p50 of 5 runs each, Python vs. Rust).

- **R14.** The Rust constraint engine catches all errors internally and returns them as Python exceptions (never aborts the Python process). Panics are caught via `std::panic::catch_unwind` and converted to `RuntimeError`. OOM errors propagate as Python `MemoryError`. Unhandled constraint types return a `NotImplementedError` that surfaces to the caller with the constraint type name.

---

## Acceptance Examples

- **AE1.** Covers R4, R5, R6. Given a golden corpus placement with known keepout zone violations, when `temper_constraints.compute_keepout_loss(placement, constraints)` is called through PyO3, the returned loss value matches the Python `keepout_loss()` output within 1e-6.

- **AE2.** Covers R7, R9. Given a PR that adds a new constraint type `ThermalZone` to the Rust engine but forgets to expose it via PyO3 bindings, when CI runs `cargo test && pytest tests/rust_integration/`, the integration test fails with an error indicating the constraint type is not exported from Rust bindings.

- **AE3.** Covers R8. Given a PR that extracts the A* priority queue to Rust, when CI runs the benchmark gate, the output shows a measurable wall-clock reduction (e.g., `astar_priority_queue: python 450ms -> rust 120ms (73% reduction)`).

- **AE4.** Covers R10. Given a developer environment without the Rust toolchain installed, when `temper optimize` runs, it falls back to the Python constraint engine with a one-time log message: `[INFO optimizer] Rust constraint engine not available, using Python fallback`.

---

## Success Criteria

- PCL constraint evaluation time is reduced measurably (target: >50% reduction) after Rust extraction
- New constraint types added to the Rust engine cannot be silently "forgotten" by any consumer — the compiler enforces exhaustive handling
- CI detects broken PyO3 wiring within one push (infrastructure-unwired failure mode prevented)
- Python-only operation continues to work — Rust is an acceleration, not a requirement

---

## Scope Boundaries

- Not extracting the entire pipeline to Rust — only compute-hot, self-contained kernels
- Not rewriting the DAG engine or YAML manifest system in Rust — orchestration stays in Python
- Not extracting JAX optimization loops — JAX/XLA is already compiled; Rust targets non-JAX compute (constraints, routing)
- First extraction is PCL constraint engine only — SAT solver, A* router, and DRC checker are subsequent extractions defined in separate brainstorms
- After extraction, the Rust engine becomes the reference implementation for extracted constraint types. Python implementations of extracted types may be removed after a one-release deprecation period with a CI gate verifying parity between Rust and Python implementations remains intact during the deprecation window.

---

## Key Decisions

- Constraint engine is the first extraction target because it is small (~1200 lines), correctness-critical, consumed by both CLI and DAG, and naturally expressed in Rust's type system (enum + exhaustive match)
- Python fallback is mandatory — Rust is an acceleration, not a hard dependency, and the system must operate without it
- Before/after benchmarking is a CI requirement for every extraction PR — no extraction merges without quantified improvement
- Profiling data guides extraction ORDER for subsequent extractions but does not gate the first extraction decision — PCL constraint engine is the first target regardless of profiling results because of its correctness-critical nature, small size, and self-contained interface
- The R8 benchmark gate starts as warn-only and becomes blocking after a 2-week calibration period to establish reliable baseline variance for each extraction target. The gate uses benchmark p50 of 5 runs with a 2σ regression threshold.

---

## Dependencies / Assumptions

- Observability middleware (separate brainstorm) produces the profiling data that guides extraction prioritization
- PyO3+maturin toolchain works on macOS (dev) and Linux (CI) — Windows is explicitly out of scope
- Python fallback performance is acceptable for development without the Rust toolchain installed
- A golden corpus of 10+ board placements exists or will be established to serve as the correctness and performance baseline

---

## Outstanding Questions

### Resolve Before Planning

- **[Affects R1]** [User decision] Is there a canonical benchmark board + placement that serves as the profiling baseline, or does one need to be established?
- **[Affects R5]** [User decision] Should the Rust PCL engine store constraint state internally (own the constraint graph) or should Python pass constraints as function arguments on each call?

### Deferred to Planning

- **[Affects R4]** [Technical] JAX array -> Rust ndarray zero-copy sharing interface via rust-numpy or Arrow
- **[Affects R7]** [Technical] CI cross-compilation setup for Rust + maturin on macOS and Linux runners
