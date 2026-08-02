<!-- provenance: commit=58b74bb0f0c1a0ed4f59ad937376bb33e4511e12 dirty=false (landed on main via 58b74bb0f, perf(placer): migrate Wave 1 hot paths to Rust) -->

# KTD9 spike: faer vs scipy sparse-solver parity (2026-07-31)

<!-- provenance: commit=58b74bb0f0c1a0ed4f59ad937376bb33e4511e12 dirty=UNKNOWN (backfilled 2026-08-02: this file landed on main via commit 58b74bb0f ("perf(placer): migrate Wave 1 hot paths to Rust"); content byte-identical to that commit. Measurement-time dirty state not recorded, hence UNKNOWN.) -->

**Verdict: faer (0.24.4) is numerically viable as a drop-in for scipy
`spsolve` on the FDM matrix, but adoption is NOT warranted.** Recorded
per the repo's measurement-provenance convention.

## Reproduction

```python
# temper_thermal built 2026-07-31 (solve_faer_py); FDM matrix via the
# Rust assembly (temper_placer.physics.thermal_fdm._assemble_system)
from scipy.sparse.linalg import spsolve
# 50x50 grid (2500 cells, the max_cells budget ceiling), random k/Q/h
# fields, heatsink TOP: spsolve(A, b) vs temper_thermal.solve_faer_py(...)
# max|T_faer - T_scipy| = 5.116e-13 K
# residuals: scipy 1.54e-15, faer 2.48e-15 (relative, ||Ax-b||/||b||)
# 25x100: 3.411e-13 K
# 20x20 vs numpy dense oracle: scipy 6.963e-13 K, faer 5.826e-13 K
```

## Interpretation

- Two direct factorizations agree to ~5e-13 K — far below the ~1e-9 K
  a-priori estimate (the FDM matrix is well-conditioned: 5-point
  stencil, M-matrix with strong diagonal).
- Both solvers agree with the independent dense solve to ~7e-13 K;
  all residuals at machine precision (~1e-15).
- No performance case: at ≤2500 cells both solvers run in ~0.00-0.01s
  (SuperLU is C-speed; the solve was never the Python hot loop).

## Consequence

The solve side of U6 stays on scipy `spsolve` (SuperLU) — the
deterministic reference is unchanged, preserving bit-identical parity
with the Python baseline. The measured contract (~5e-13 K forward
agreement) is the recorded tolerance for any future solver change
(faer included). The assembly-side port (the roadmap's "10-50x matrix
assembly" win) is delivered by temper-thermal.

## Test state

The spike is documented in `packages/temper-thermal/VERIFICATION.md`,
the KTD9 resolution in
`docs/plans/2026-07-23-003-perf-rust-migration-roadmap-plan.md`, and
the `solve_faer_py` pyfunction remains in temper-thermal for
re-measurement.
