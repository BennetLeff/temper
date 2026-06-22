---
title: "Cython Twin Re-Introduction Threshold"
type: spec
status: active
date: 2026-06-22
---

# Cython Twin Re-Introduction Threshold

This document records the pre-agreed threshold for any future re-introduction of a Cython A* twin alongside `router_v6/astar_pathfinding.py`. The threshold is the gate referenced by the historical-removal notes in `docs/reports/PERFORMANCE_OPTIMIZATION_SESSION.md` and `router-experiments/reports/exp_24_piantor_2026-01-10.md`.

## Threshold

A Cython twin shall be re-introduced **only if** either of the following conditions is met on the four-board corpus:

1. **Per-path p95 A* latency is >= 5x the hypothetical Cython target** (i.e., the measured pure-Python p95 from `tests/router_v6/benchmarks/baseline.json` is >= 5x what a Cython twin would deliver).
2. **End-to-end routing-stage wall time is >= 2x what a Cython twin would deliver** (i.e., the measured `runtime_seconds` from the R3 benchmark is >= 2x the expected Cython wall time).

These are **OR** conditions: either alone justifies re-introduction. The two-number form prevents the case where per-path speedup is large but the routing stage is not the wall-time bottleneck.

## Rationale

- The historical 40x per-path figure (`PERFORMANCE_OPTIMIZATION_SESSION.md` line 39, 0.086ms vs 3.5ms) was measured against the **deleted** `astar_core.pyx` (707 lines) driving the **legacy** `deterministic/stages/multilayer_astar.py`. It is **not evidence** about the current `router_v6/astar_pathfinding.py` (2289 lines, pure Python).
- A 2x single-number threshold under-weights the build-complexity cost and ignores the historical reality that the per-path delta was 40x, not 2x.
- A build step that delivers <5x per-path speedup does not justify the ongoing drift risk and build complexity (Cython dependency, `.pyx` maintenance, parity-test overhead).

## Corpus

The four external boards defined in `packages/temper-placer/temper_placer/router_v6/test_boards.py`:

| Board | Domain | Layers | ~Net Count |
|-------|--------|--------|------------|
| Piantor_Right | digital | 2 | 33 |
| LibreSolar_BMS | power | 4 | 200 |
| RP2040_DesignGuide | mixed | 4 | 120 |
| BitAxe_Ultra | mixed | 2 | 80 |

The Temper board (`TEMPER_PATH`, `test_boards.py:54`) is excluded because its path was hardcoded to a user-local absolute path and the file is not under version control. The four external boards span a representative range of complexity (consumer keyboard, BMS, MCU design guide, mining board).

## Measurement Protocol

1. Run the R3 benchmark: `python -m temper_placer.router_v6.benchmark --router v6 --output baseline.json`
2. Compare `per_path_latency_ms.p95` and `runtime_seconds` against the committed baseline in `tests/router_v6/benchmarks/baseline.json`.
3. The baseline is committed once per machine-class; the 15% regression gate (R5) absorbs cross-machine variance.

## Re-Introduction Path

If the threshold is met in a future measurement initiative, the default implementation approach is:

- **Approach B (codegen from type-annotated `.py`)** — Cython type annotations (`cython.int`, `cython.double`, typed memoryviews) are added to `astar_pathfinding.py` guarded by `if cython.compiled`, so the file remains importable as pure Python.
- **Approach C (hand-maintained `.pyx`)** is escalation-only. Hand-maintained `.pyx` reintroduces the exact drift risk this threshold exists to eliminate.

In either case, the **parity test (R6)** is implemented alongside the re-introduction, asserting byte-identical path output between pure-Python and Cython implementations against golden routing fixtures drawn from the corpus.

## References

- Origin requirements: `docs/brainstorms/2026-06-21-cython-twin-measure-requirements.md`
- Implementation plan: `docs/plans/2026-06-22-007-fix-cython-twin-cleanup-plan.md`
- Deletion commit: `3314d94a` (Jan 17 2026)
- R3 benchmark: `packages/temper-placer/temper_placer/router_v6/benchmark.py`
- R5 regression gate: `packages/temper-placer/tests/router_v6/test_astar_perf_regression.py`
