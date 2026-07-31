# Thermal FDM Assembly Kernels — Verification by Induction

U6 of the Python→Rust migration roadmap (docs/plans/2026-07-23-003),
porting the assembly hot loops of
`temper_placer/physics/thermal_fdm.py` (`_assemble_system`,
`_trace_to_cell_coverage`, `_point_to_segment_distance`) to the
`temper-thermal` crate. The sparse SOLVE stays in scipy (SuperLU) —
a Rust solver is gated on the KTD9 parity spike (still outstanding;
see the roadmap).

## Base Case: 1×1 Grid

For a 1×1 grid with a "TOP" heatsink edge, the assembly produces a
1×1 system: the single cell has no neighbours, the south/west/east
faces are Neumann (no term), the north face is Dirichlet
(`2·k_c/dx²` on the diagonal, `2·k_c/dx²·T_amb` on the RHS), plus the
sink and Q terms. Both the Rust kernel and the pinned Python reference
produce the identical scalar system (asserted bit-exactly).

## Induction Step

The assembly is the union of per-cell stencil contributions; each
cell's five coefficients (east/west/north/south/diagonal) are pure
functions of the cell's own `k_c`, its neighbour's `k`, the boundary
conditions, and the optional sink — no cross-cell accumulation beyond
the five-point stencil. If the system is correct for an h×w grid it
is correct for (h+1)×w and h×(w+1): the new row/column evaluates the
same formula on new cells, and existing entries are untouched
(row-major index `row·w + col` preserves them). The exact f64
operation order (harmonic mean `2/(1/k_a + 1/k_b)`, direction
accumulation order east→west→north→south→sink→Q on both the diagonal
and the RHS) is what makes the assembled matrix and RHS bit-identical
to the reference rather than merely close.

Trace rasterisation follows the same argument per cell: the 4×4
supersampling hit-count is a pure per-cell function; extending the
grid adds cells without perturbing existing coverage values.

## Empirical Verification

The differential suite
(`packages/temper-placer/tests/physics/test_thermal_fdm_rust_differential.py`)
pins:

- `_assemble_system` bit-exact against the pre-migration `lil_matrix`
  reference across all four heatsink edges, random k/Q fields, and
  optional h_field (matrix `.toarray()` and RHS compared with
  `assert_array_equal` — f64 bit equality).
- `solve_thermal_fdm` end-to-end: Rust assembly vs reference assembly
  (monkeypatched) produce bit-identical temperature grids (same
  matrix + same SuperLU solve → same result).
- `_trace_to_cell_coverage` bit-exact against the reference
  supersampling loop on 25 random traces plus degenerate (zero-length)
  and off-grid cases.

The full pre-existing thermal verification surface
(`test_thermal_fdm.py`, `test_thermal_fdm_pbt.py`,
`test_thermal_fdm_matrix_class.py`, `test_thermal_fdm_mms.py`,
`test_thermal_fdm_refinement.py`, `test_thermal_fdm_invariants_pbt.py`,
`test_copper_coverage.py`) now exercises the Rust assembly through the
public API: matrix class properties (symmetry, SPD, M-matrix sign
pattern), manufactured-solution convergence, mesh refinement, and the
five PBT invariants (energy conserving, positive temperature,
steady-state unique, boundary-respecting, mesh-convergent) all pass —
these become the property gate for the migrated assembly.

## KTD9 status

The sparse-solver parity spike was executed 2026-07-31 (faer 0.24.4 vs
scipy spsolve/SuperLU, plus an independent numpy dense-solve oracle on
a 20×20 mesh):

| Case | max|T_faer − T_scipy| | residual (scipy / faer) |
|---|---|---|
| 50×50 (2500 cells, budget ceiling) | 5.1e-13 K | 1.5e-15 / 2.5e-15 |
| 25×100 | 3.4e-13 K | 1.1e-15 / 1.8e-15 |
| 20×20 vs dense oracle | 7.0e-13 (scipy) / 5.8e-13 (faer) | 1.5e-15 / 1.2e-15 |

**Verdict: faer is numerically viable** — agreement ~5e-13 K (far below
the ~1e-9 K estimate; the FDM matrix is well-conditioned) — **but
adoption is not warranted**: no perf win at these sizes (scipy spsolve
is C-speed) and it would break bit-parity with the deterministic
reference for zero measured benefit. scipy stays; the measured contract
above is the recorded tolerance for any future solver change. The
assembly-side win (the roadmap's "10-50x matrix assembly" target) is
delivered; the solve was never the Python hot loop.
