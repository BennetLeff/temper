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

---

# RTD Safety Model — Verification by Induction

Wave 2 slice of the Python→Rust migration roadmap
(docs/plans/2026-07-23-003): the deterministic PT100/MAX31865
safety-threshold model from `temper_placer/validation/rtd_safety.py`
(the THM-adjacent thermal protection chain), ported to
`temper_thermal.rtd`.

## Base Case

`resistance_to_code(0.0, rref)` returns 0 and
`resistance_to_code(R, rref)` for R small is
`floor(32768·R/rref)` — the Rust core and the pinned Python oracle
agree bit-for-bit. For a zero-width valid window the derivation
reports an overlap (status 1 or 2) exactly as the reference raises.

## Inductive Step

All ported functions are scalar evaluations: each output is a pure
function of its inputs with the exact f64 operation order of the
reference (e.g. `max31865_rtd_voltage_v = r * (vbias / (rref + r))` —
two operations, not `(r·vbias)/(rref+r)`; the derivation's
`(nom_min + nom_max) / 2.0` midpoint). The floor/ceil integer
conversions and the clamped 15-bit code mirror Python's `min`,
`floor`, and `ceil` semantics exactly. The overlap status codes
(0=ok, 1=low overlap, 2=high overlap) let the Python wrapper raise the
reference ValueError messages verbatim.

## Empirical Verification

The differential suite
(`packages/temper-placer/tests/validation/test_rtd_safety_rust_differential.py`)
pins all nine ported functions bit-exactly against the pre-migration
implementations (1000 resistance-code samples, 500 threshold-code
samples, 500 voltage/divider/SPI samples, and 300 random corner
derivations per window type with overlap agreement). The pre-existing
property suites (`test_rtd_safety_pbt.py`, `test_rtd_window_comparator_pbt.py`,
`test_rtd_fault_latch_pbt.py`, 28 tests) now exercise the Rust core
through the wrappers.

**Kept in Python deliberately:** the corner dataclasses, the
ValueError validation guards (interface contract), and the digital
state machines (`SimulatedDigitalRtdService`, `VirtualRtdBoard`,
latch settling) — protocol logic, not math; migrating them would
churn the consumer surface without a compute or safety win.

---

# Independent Thermal Scorer (U7) — Verification by Induction

Wave 3 candidate #6 (`docs/plans/2026-07-31-001-feat-wave3-rust-migration-roadmap-plan.md`):
the pure compute of `temper_placer/validation/thermal_scorer.py` — the
second, INDEPENDENT convective-boundary (Robin BC) FDM T_j scorer whose
repeated sparse assembly sits inside battery experiments — ported to
`temper_thermal.thermal_scorer`. The sparse SOLVE stays in scipy
(SuperLU) per the KTD9 verdict (two direct factorizations agree to
~5e-13 K; scipy stays for the solve). The falsifiability assertion's
1.0 deg-C threshold against the U5 field solver is a separate, PRESERVED
Python-side contract and is untouched.

## Base Case: 1×1 Grid

For a 1×1 grid the convective assembly produces a 1×1 system: the
single cell sits on EVERY edge, so for any declared heatsink edge it is
a heatsink-edge cell — exactly one Dirichlet face (`2·k_c/dx²` on the
diagonal, `2·k_c/dx²·T_amb` on the RHS) and NO convective term
(`is_convective_edge_cell` excludes heatsink cells). The Rust kernel and
the pinned Python reference agree bit-for-bit (asserted in both the
Rust unit test and the Python differential suite).

## Induction Step

The assembly is the union of per-cell stencil contributions; each cell's
five coefficients (east/west/north/south/diagonal) are pure functions of
the cell's own `k_c`, its neighbour's `k`, the boundary conditions, and
the optional sink — no cross-cell accumulation beyond the five-point
stencil. If the system is correct for an h×w grid it is correct for
(h+1)×w and h×(w+1): the new row/column evaluates the same formula on
new cells, and existing entries are untouched (row-major index
`row·w + col` preserves them). The exact f64 operation order (harmonic
mean `2/(1/k_a + 1/k_b)`, direction accumulation order
east→west→north→south→convective→sink→Q on both the diagonal and the
RHS, convective coefficient `h_conv·t_mm/cs·1e-6` left-to-right) is
what makes the assembled matrix and RHS bit-identical to the reference
rather than merely close.

The heat-source field follows the same per-device independence
argument: each device's footprint bounds (`floor`/`ceil` of
`(pos ∓ half_f − origin)/cs`), cell count `n_cells = max(1, ...)`, and
density `power/(n_cells·cs²)` are pure functions of that device alone;
devices accumulate in dict insertion order and never perturb earlier
entries except by the reference's exact `+=` additions. The
conductivity field is elementwise (`k_fr4_eff + (k_cu_eff − k_fr4_eff)·
clip(frac, 0, 1)`), trivially per-cell.

## Empirical Verification

The differential suite
(`packages/temper-placer/tests/validation/test_thermal_scorer_rust_differential.py`)
pins:

- `_build_conductivity_field_gs` bit-exact against the pre-migration
  vectorized-numpy reference (60 random fields + clipping/NaN/zero-
  thickness/empty-grid corners, `assert_array_equal`).
- `_build_heat_source_field_gs` bit-exact against the pre-migration
  device loop (120 random device sets + zero/negative-power, off-grid,
  overlapping, single-cell, and negative-slice-wrap corners). The
  off-grid-low negative-slice wrap is a latent reference quirk
  (identical in U5's `thermal_fdm.py`) and is replicated bit-for-bit
  rather than silently "fixed".
- `_assemble_convective_system` bit-exact against the pre-migration
  `lil_matrix` reference across all four heatsink edges, 160 random
  (k, Q, h_field, h_conv, ambient, thickness) cases, plus invalid-edge
  ("NORTH"), 1×1, h_conv=0, and all-ambient corners.
- `solve_independent` end-to-end: Rust assembly vs reference assembly
  (monkeypatched) produce bit-identical T_grids (same matrix + same
  SuperLU solve → same result).
- PBT: five non-vacuous properties — finite/non-negative T_grid;
  monotone in power (M-matrix: A⁻¹ ≥ 0); monotone in conductance on the
  PEAK (pointwise k-monotonicity provably fails near mixed boundaries);
  boundary-respecting (no sources → ambient exactly; interior point
  source → heatsink-edge max strictly below the interior peak, by the
  discrete maximum principle); energy balance (|A·T − b| scaled to
  power within 5%).
- Metamorphic relations: doubling all powers doubles the rise (linear
  regime, rtol 1e-9); integer-cell translation is exactly covariant for
  the Q-field compute and bounded (<1% of peak rise) for the field on
  the deep interior (2D boundary corrections decay only logarithmically);
  a symmetric (copper, Q_field, edge) board yields a symmetric field.

The pre-existing scorer surface (`test_thermal_scorer.py`,
`test_thermal_scorer_independence.py`, `test_thermal_battery_run.py`,
43 tests) now exercises the Rust compute through the unchanged public
API.

**Kept in Python deliberately:** `ThermalScorer`/`ThermalScorerConfig`/
`ThermalScoreResult`, `solve_independent`/`score` orchestration, the
`spsolve` call (KTD9), the four boundary-predicate helpers (mirroring
U5's retained helpers), and `falsifiability_assertion` with its 1.0 deg-C
threshold (the preserved THM-adjacent cross-check contract).
