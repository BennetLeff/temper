# Thermal FDM Assembly Kernels — Verification by Induction

Updated 2026-08-02: `device_power::single_device_power` and
`junction_temp::estimate_junction_temp` added (Wave 4 Phase A #2 and #3 —
migrations of `temper_placer/physics/device_power.py` and
`temper_placer/physics/thermal.py::estimate_junction_temp` to Rust; the
Python modules keep their public APIs and delegate the arithmetic to
`temper_thermal.single_device_power_py` /
`temper_thermal.estimate_junction_temp_py`).  See the
"Per-device power kernel — induction non-applicability note" and
"Junction-temperature kernel — induction non-applicability note"
sections below.  Also updated 2026-08-02: `inductance::estimate_loop_inductance`
added (Wave 4 Phase A #4 — migration of `temper_placer/physics/inductance.py`
to Rust; the Python module keeps its public API and delegates to
`temper_thermal.estimate_loop_inductance_py`).  See the
"Parasitic-loop-inductance kernels — induction non-applicability note"
section below. Updated 2026-08-17: the sibling `inductance::estimate_gate_inductance`
kernel (added the same day as the loop estimator) was **deleted** — it had
no production caller for its entire lifetime, and its only intended
consumer (`metrics/physics.py::measure_emi`) was itself retired as dead
code on 2026-07-10. See
`docs/evidence/2026-08-17-gate-inductance-and-unwired-kernels.md`.

U6 of the Python→Rust migration roadmap (docs/plans/2026-07-23-003),
porting the assembly hot loops of
`temper_placer/physics/thermal_fdm.py` (`_assemble_system`,
`_trace_to_cell_coverage`, `_point_to_segment_distance`) to the
`temper-thermal` crate. The sparse SOLVE was migrated to the crate too
on 2026-08-09 (`solve.rs`, faer sparse LU), closing the last scipy
imports in the product surface — see the "Sparse solve kernel (U5/U7)"
section below (KTD9 overturn, documented tolerance 1e-10 K).

## Per-device power kernel — induction non-applicability note

`device_power::single_device_power(device_type_code, v_ce_sat,
r_ds_on, e_on, e_off, v_f, e_rr, v_bus, i_load_rms, f_sw, t_rise,
t_fall) -> f64` is a **closed-form, loop-free and recursion-free
function of its scalar inputs** — a three-way branch (DIODE vs
IGBT/MOSFET, and within IGBT/MOSFET a conduction branch and a switching
branch) over fixed arithmetic chains:

```text
DIODE:        I_avg = I_load_rms * 0.5
              P_cond = I_avg * V_f
              P_sw = E_rr * f_sw
              P = P_cond + P_sw
IGBT/MOSFET:  P_cond = pow(I_load_rms, 2.0) * R_ds_on   (R_ds_on > 0)
                    else I_load_rms * V_ce_sat
              P_sw = (E_on + E_off) * f_sw              (E_on > 0 or E_off > 0)
                    else 0.5 * V_bus * I_peak * f_sw * (t_rise + t_fall)
                    with I_peak = I_load_rms * sqrt(2)
              P = P_cond + P_sw
```

There is no iteration, no induction variable, and no data structure
whose size varies with the input — the kernel does exactly the same
finite sequence of correctly-rounded f64 operations for every input.
R1e's induction requirement applies to modules with recursive or
computational structure; for this module it is **not applicable**.
In its place we record the structural correctness argument below, which
is what the R1e note requires for data-only / closed-form modules
(identical convention to `temper-quality-oracle/VERIFICATION.md`'s
routing-quality note, Wave 4 Phase A #1).

### Structural correctness argument (bit-exact parity)

1. **Pure function of twelve scalars.** Every output bit depends only on
   the scalar arguments and on correctly-rounded IEEE-754 f64
   arithmetic, which is deterministic and identical in CPython and Rust
   for the same operation sequence.  No IO, no global state, no
   nondeterminism enters the computation.

2. **Operation-order pinning.** The kernel reproduces the pre-migration
   Python's exact f64 operation order (pinned by the differential suite
   `packages/temper-placer/tests/physics/test_device_power_rust_differential.py`,
   which embeds the verbatim pre-migration implementation as an oracle
   and asserts bit-identical equality over all four device paths):
   - `I_load_rms ** 2` (CPython `float.__pow__` → host libm
     `pow(x, 2.0)`) ⇔ `math_pow(I, 2.0)` resolved via `dlsym` — **not**
     `x * x` (the two differ by 1 ulp on ~0.14% of random floats,
     measured 2026-08-02 and pinned by
     `test_direct_mosfet_pow2_semantics`).  Catalog class **B1** (libm
     via dlsym) + **B7** (operation order).
   - `math.sqrt(2)` ⇔ `math_sqrt(2.0)` via `dlsym("sqrt")` (**B1**).
   - `0.5 * V_bus * I_peak * f_sw * (t_rise + t_fall)` stays the same
     five-op left-to-right chain (**B7**), with `I_peak` computed before
     the chain.
   - `(E_on + E_off) * f_sw` keeps the parenthesized sum; `I_avg =
     I_load_rms * 0.5`; final `P_cond + P_sw` left-to-right (**B7**).
   - **B8 (denormal underflow):** default IEEE semantics (no fast-math,
     no FTZ/DAZ, no `mul_add` fusion); a denormal-band differential case
     pins `pow(1e-155, 2.0) * 1.0` in the denormal range bit-identical
     to CPython.

3. **Branch equivalence.** The `device_type == "DIODE"`, `R_ds_on > 0`,
   and `E_on > 0 or E_off > 0` branches map one-to-one to the Python
   `if/else` structure, including the NaN semantics of IEEE comparisons
   (NaN selects the else arms in both languages; pinned by
   `test_direct_nan_inf_semantics`).

### Empirical verification

- **Differential (G2):** `test_device_power_rust_differential.py` —
  42 tests: direct kernel pins (25 randomized seeds × 4 device paths,
  hand-computed values, the pow-vs-mul discrimination value, the
  denormal band, NaN/inf parity, zero-energy branch edges) plus
  module-level delegation pins (`_compute_single_device_power`,
  `derive_power_map`), all `==` bit-exact.
- **PBT (G4):** `test_device_power_rust_pbt.py` — 6 properties (P1
  positivity/richness, P2/P3/P4 bit-exact closed forms per path, P5
  monotonicity in I, P6 V_bus irrelevance) each vacuity-guarded by a
  `test_pN_fails_for_<mutant>` mutation test, plus 5 metamorphic
  relations (M1/M2/M5 power-of-two scale exactness per path, M3 waveform
  closed form, M4 f_sw=0 degeneracy).
- **Rust unit tests:** `device_power.rs` `#[cfg(test)]` — branch
  structure, pow semantics, NaN branch selection, closed-form pins.

## Junction-temperature kernel — induction non-applicability note

`junction_temp::estimate_junction_temp(power_w, edge_distance_mm,
copper_area_mm2, ambient_c, rjc, rch, rha_base) -> f64` is a **closed-form,
loop-free and recursion-free function of its scalar inputs** — the
heuristic Tj estimator from `temper_placer/physics/thermal.py`
(edge-distance penalty, copper-spreading benefit, and the
`ambient + P * R_total` model) — a fixed arithmetic chain with no
branching at all:

```text
edge_penalty   = max(0.0, edge_distance_mm - 5.0) * 0.2
copper_benefit = min(0.5, (copper_area_mm2 / 1000.0) * 0.1)
R_total        = ((Rjc + Rch) + Rha_base) + edge_penalty - copper_benefit
T_junction     = ambient_C + (power_W * R_total)
```

There is no iteration, no induction variable, no data structure whose
size varies with the input, and no branch — the kernel performs exactly
the same finite sequence of correctly-rounded f64 operations for every
input.  R1e's induction requirement applies to modules with recursive or
computational structure; for this module it is **not applicable**.  In
its place we record the structural correctness argument below (identical
convention to the routing-quality and per-device-power notes).

### Structural correctness argument (bit-exact parity)

1. **Pure function of seven scalars.** Every output bit depends only on
   the scalar arguments and on correctly-rounded IEEE-754 f64
   arithmetic, which is deterministic and identical in CPython and Rust
   for the same operation sequence.  No IO, no global state, no
   nondeterminism enters the computation.

2. **Operation-order pinning.** The kernel reproduces the pre-migration
   Python's exact f64 operation order (pinned by the differential suite
   `packages/temper-placer/tests/physics/test_thermal_rust_differential.py`,
   which embeds the verbatim pre-migration implementation as an oracle
   and asserts bit-identical equality):
   - `edge_penalty = max(0.0, edge_distance_mm - 5.0) * 0.2` — the
     `* 0.2` applies to the max RESULT, and the **constant `0.0` is the
     first `max` argument** (catalog class **B5**, Python builtin
     first-argument NaN semantics: `max(0.0, NaN) == 0.0`; Rust mirrors
     with `0.0_f64.max(d)` so the constant is the receiver).
   - `copper_benefit = min(0.5, (copper_area_mm2 / 1000.0) * 0.1)` —
     division, then `* 0.1`, then `min` with the **constant `0.5`
     first** (**B5** again: `min(0.5, NaN) == 0.5`).
   - `R_total` is the left-to-right `((Rjc + Rch) + Rha_base) +
     edge_penalty - copper_benefit` chain; the final step is
     `ambient_C + (power_W * R_total)` with the parenthesized product
     evaluated first.  No reassociation, no fusing (**B7**).
   - **B8 (denormal underflow):** default IEEE semantics (no fast-math,
     no FTZ/DAZ, no `mul_add` fusion); a denormal-band differential case
     pins `1e-310 * R_total` in the denormal range bit-identical to
     CPython, with a non-zero-resistance sanity check proving the case
     genuinely exercises the denormal product.
   - **B1/B2/B3/B4/B6 are not applicable**: the kernel calls no libm
     functions (no sqrt/pow/log — no dlsym needed), divides no
     constants, rounds nothing, and computes no distances.

### Empirical verification

- **Differential (G2):** `test_thermal_rust_differential.py` — 30 tests:
  direct kernel pins (20 randomized seeds × 50 cases, hand-computed
  values, edge-penalty and copper-benefit saturation, NaN/inf parity
  including the B5 first-argument pins, the denormal band, zero-power)
  plus module-level delegation pins (`estimate_junction_temp` with
  defaults and custom Rjc), all `==` bit-exact.
- **PBT (G4):** `test_thermal_rust_pbt.py` — 5 non-vacuous properties
  (P1 positivity/richness, P2 non-decreasing in power, P3 bit-exact
  closed form, P4 non-decreasing in edge distance, P5 non-increasing in
  copper) each vacuity-guarded by a `test_pN_fails_for_<mutant>`
  mutation test, plus 4 bit-exact metamorphic relations (M1 power-of-two
  P-scale, M2/M3 saturation sub-threshold/supra-threshold equivalence,
  M4 zero-power degeneracy) and a determinism/richness smoke test.
- **Rust unit tests:** `junction_temp.rs` `#[cfg(test)]` — closed-form
  pins, both saturation ranges, both B5 NaN pins, zero-power, and the
  B7 product-before-add op-order pin.

## Parasitic-loop-inductance kernel — induction non-applicability note

`inductance::estimate_loop_inductance(loop_area_mm2, perimeter_mm,
layer_separation_mm, routing_factor) -> f64` (Wave 4 Phase A #4 —
migration of `temper_placer/physics/inductance.py`) is a **closed-form,
loop-free and recursion-free function of its scalar inputs**, with
exactly one branch (the `h_m > 0` conditional area term):

```text
loop:  MU_0       = 4 * math.pi * 1e-7                      (three-op chain)
       area_m2    = loop_area_mm2 * 1e-6
       h_m        = layer_separation_mm * 1e-3
       L_area_H   = (MU_0 * area_m2 / h_m) if h_m > 0 else 0
       L_area_nH  = L_area_H * 1e9
       L_self_nH  = perimeter_mm * 0.2
       L_total    = (L_area_nH * 0.5 + L_self_nH) * routing_factor
```

The sibling `inductance::estimate_gate_inductance(source_to_gate_dist_mm,
return_dist_mm) -> f64` kernel that lived alongside this one was deleted
2026-08-17 (no production caller for its entire lifetime — see
`docs/evidence/2026-08-17-gate-inductance-and-unwired-kernels.md`); this
section no longer describes it.

There is no iteration, no induction variable, and no data structure
whose size varies with the input — each kernel performs exactly the
same finite sequence of correctly-rounded f64 operations for every
input.  R1e's induction requirement applies to modules with recursive
or computational structure; for these kernels it is **not applicable**.
In its place we record the structural correctness argument below
(identical convention to the routing-quality, per-device-power, and
junction-temperature notes).

### Structural correctness argument (bit-exact parity)

1. **Pure functions of scalars.** Every output bit depends only on the
   scalar arguments and on correctly-rounded IEEE-754 f64 arithmetic,
   which is deterministic and identical in CPython and Rust for the
   same operation sequence.  No IO, no global state, no nondeterminism
   enters the computation.

2. **Operation-order pinning.** The kernels reproduce the pre-migration
   Python's exact f64 operation order (pinned by the differential suite
   `packages/temper-placer/tests/physics/test_inductance_rust_differential.py`,
   which embeds the verbatim pre-migration implementation as an oracle
   and asserts bit-identical equality):
   - `MU_0 = 4 * math.pi * 1e-7` is the left-to-right three-op chain
     `(4.0 * PI) * 1e-7` — catalog class **B2 (extension)**.  The oracle
     uses the NAMED constant `math.pi` (0x400921FB54442D18), the
     correctly-rounded 53-bit double closest to pi, which is
     **bit-identical to Rust's `std::f64::consts::PI`** (verified by
     `test_direct_mu0_chain_bit_exact`).  The classic B2 pitfall —
     `PI / 2.0` vs the pre-rounded `FRAC_PI_2` — does NOT arise here
     because the oracle never divides pi.
   - `MU_0 * area_m2 / h_m` is the left-to-right `(mu_0 * area_m2) /
     h_m` chain; `L_area_H * 1e9` and `perimeter_mm * 0.2` are single
     multiplies; the final `(L_area_nH * 0.5 + L_self_nH) *
     routing_factor` keeps the parenthesized sum evaluated BEFORE the
     multiply by `routing_factor`.  No reassociation, no fusing (**B7**).
   - **B8 (denormal underflow):** default IEEE semantics (no fast-math,
     no FTZ/DAZ, no `mul_add` fusion); a denormal-band differential case
     pins `mu_0 * area_m2` for a 1e-300 mm² loop area (≈1.26e-312,
     inside the f64 denormal band) bit-identical to CPython, with a
     non-zero sanity check proving the case genuinely exercises the
     denormal product.

3. **Branch equivalence.** The `h_m > 0` conditional area term maps
   one-to-one to the Python `(MU_0 * area_m2 / h_m) if h_m > 0 else 0`
   conditional expression, including the NaN semantics of IEEE
   comparisons (0.0, negative, and NaN all select the `0` arm in both
   languages; pinned by `test_direct_zero_height_edge` and
   `test_direct_nan_inf_semantics`).  **B1/B3/B4/B5/B6 are not
   applicable**: the kernels call no libm functions (no sqrt/pow/log —
   the only constant is `math.pi`), round nothing, use no `hypot`, and
   use no Python `max`/`min`.

4. **R24 physics discipline (G8): N/A — not a CP-SAT constraint
   surface.** This kernel is an analysis estimator, not a CP-SAT
   constraint that gates on a physics quantity; the R24 gates
   (Chebyshev soundness proof, BMC-exhaustive validation on small N,
   post-solve audit recompute) do not apply.  The bit-exactness pins
   above are the applicable correctness contract.
   **Correction, 2026-08-17:** this note previously said the kernel
   (and its now-deleted `estimate_gate_inductance` sibling) was
   "consumed by the EMI measurement path (`metrics/physics.py::
   measure_emi`)". That was stale: `measure_emi`'s only caller,
   `PipelineOrchestrator`, was deleted as dead code by `1060584b7`
   (2026-07-10); `measure_emi` and this whole module have had zero
   production callers since. See
   `docs/evidence/2026-08-17-gate-inductance-and-unwired-kernels.md`.

### Empirical verification

- **Differential (G2):** `test_inductance_rust_differential.py` — 25
  randomized-seed direct kernel pins (with the h <= 0 degenerate arm),
  hand-computed known values, the `mu_0` named-constant chain pin, the
  denormal band, NaN/inf parity, the zero-height branch flip, and
  module-level delegation pins with defaults — all `==` bit-exact.
- **PBT (G4):** `test_inductance_rust_pbt.py` — 5 non-vacuous
  properties (P1 non-negativity/richness, P2 loop closed form, P4
  zero-height degeneracy, P5/P6 monotonicity in area and perimeter;
  P3/M5 were the deleted gate-estimator properties and are
  intentionally not renumbered) each vacuity-guarded by a
  `test_pN_fails_for_<mutant>` mutation test (constant kernel, missing
  0.5 factor, unconditional area term, decreasing-in-area and
  decreasing-in-perimeter kernels), plus 4 metamorphic relations (M1/M3
  bit-exact power-of-two scales, M2 zero-routing-factor degeneracy, M4
  exact monotone comparison) and a determinism/richness smoke test.
- **Rust unit tests:** `inductance.rs` `#[cfg(test)]` — known values,
  zero-height/NaN-h arm selection, zero-routing-factor degeneracy, and
  the `mu_0` named-constant chain pin.

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
  matrix + same faer solve → same result).
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

## Sparse solve kernel (U5/U7) — characterization and migration decision (2026-08-09)

The KTD9 verdict above is **OVERTURNED under the contract's re-decidable
rule** (docs/wave4-discipline-contract.md §3): the evidence changed in
two ways — the program now requires the scipy dependency to leave the
product surface (this migration drive is the change that makes the
"solver boundary" a decision), and the measured divergence is four
orders of magnitude below the tightest consumer tolerance. The verdict
was correct on the evidence it had (no perf win, bit-parity break, zero
measured benefit); the benefit is now dependency elimination. Recorded
here alongside the original, per the contract's overturn convention.

### Solve characterization

**What matrix each assembler builds.** Both `_assemble_system` (U5,
`thermal_fdm.py`) and `_assemble_convective_system` (U7,
`thermal_scorer.py`) build the same symmetric 5-point Laplacian stencil
with harmonic-mean interface conductivity `2/(1/k_a + 1/k_b)`, on grids
up to `max_cells = 2500` cells (e.g. 50×50 or 25×100). U5 puts a
Dirichlet face term (`2·k_c/dx²`, RHS `coeff·ambient`) at the heatsink
edge and adiabatic Neumann on the other three edges; U7 puts the same
Dirichlet face at the heatsink edge and a Robin convective term
`h_conv·(T − T_amb)` on the other three edges. An optional per-cell
vertical sink `h_cell` adds to the diagonal and `h_cell·ambient` to the
RHS; `Q` is added last to the RHS. The result is an M-matrix (U5 SPD,
symmetric; U7 symmetric but not necessarily SPD — the Robin faces add
negative-definite contributions), with ~5·n nonzeros and **no duplicate
COO triplets** (each ordered (row, col) is written exactly once).

**Determinism.** Both solvers are deterministic given fixed matrix +
flags: scipy `spsolve` (SuperLU, COLAMD ordering + partial pivoting)
returns bit-identical results on repeated calls, and faer's sparse LU
(partial row pivoting) is bit-identical on repeated calls (verified on
the 2500-cell U5 matrix, 2026-08-09). Neither involves RNG or an
iteration budget, so the "deterministic reference" property is preserved
by the migration — determinism, not bit-parity with scipy, is the
property the consumers rely on.

**Bit-for-bit Rust match: not achievable, and not required.**
SuperLU and faer use different pivoting and fill ordering, so factor
entries and therefore the forward solution differ in the last ulp. A
Rust solver reproducing SuperLU bit-for-bit is not a realistic target.
The consumers decide whether that matters:

**Consumer comparison mode.** No consumer of the solve output compares
it bit-exactly. Every consumer is tolerance/physics-based:
manufactured-solution convergence rates, `np.allclose(..., atol=1e-6)`,
ambient-field checks `assert_allclose(atol=1e-9)` (the **tightest**
tolerance in the suite), U5-vs-U7 relative-error thresholds (< 2%),
peak-temperature assertions (0.1 K), the A·x − b residual energy-balance
check, and the physical invariant battery (monotonicity, maximum
principle, SPD — all at 1e-9/1e-10). A solver change that stays
>10^3 below the tightest tolerance is invisible to every consumer.

### Measured divergence (2026-08-09, faer 0.24.4 / scipy 1.16.3)

Re-measured over a 144-case corpus: U5 and U7 systems, 9 grid sizes
from 1×1 to the 25×100 / 50×50 max-cells ceiling (and beyond), all four
heatsink edges, with and without the vertical-sink `h_field`, random
k/Q fields:

| Metric | Value |
|---|---|
| max\|T_faer − T_scipy\| over all 144 cases | **5.7e-12 K** (U5 25×100, LEFT edge, no sink) |
| max relative residual of the faer solve | 3.5e-15 (machine precision) |

The 5.7e-12 K divergence is ~175× below the tightest consumer tolerance
(1e-9 K) and ~6 orders below the typical one (1e-6). Both solvers agree
with an independent dense solve to ~1e-12 K (KTD9, 2026-07-31).

### Decision

**MIGRATE with a documented tolerance.** The solve call in both U5
(`thermal_fdm.py`) and U7 (`thermal_scorer.py`) delegates to
`temper_thermal.solve_sparse_lu_py` (faer sparse LU); the scipy
`coo_matrix`/`spsolve` imports leave the product surface. Per the
contract's §3 divergence-recording discipline, the differential suite
(`tests/physics/test_thermal_solve_rust_differential.py`) pins the
bound explicitly:

> **Pinned bound: for every grid in the FDM corpus (U5 + U7, any
> heatsink edge, with or without `h_field`, up to the 2500-cell
> `max_cells` ceiling), `max|T_faer − T_scipy| ≤ 1e-10 K`** — 175× above
> the observed 5.7e-12 K maximum, and still 10× below the tightest
> consumer tolerance.

### Empirical verification (solve kernel)

- **Differential (G2, documented-tolerance):**
  `tests/physics/test_thermal_solve_rust_differential.py` — the retired
  scipy `coo_matrix → spsolve` path is the verbatim oracle; the pinned
  bound `max|T_faer − T_scipy| ≤ 1e-10 K` is asserted over the full U5+U7
  corpus (8 grid sizes up to the 2500-cell ceiling × 4 heatsink edges ×
  ± h_field = 128 cases per solver kind), plus bit-identical determinism
  of both solvers and a machine-precision regression case on small grids.
- **PBT (G4):** `tests/physics/test_thermal_solve_rust_pbt.py` — 6
  properties (P1 residual smallness, P2 discrete maximum principle, P3
  no-source ambient exactness, P4 linearity in source, P5 bit-identical
  determinism, P6 finiteness) each vacuity-guarded by a
  `test_pN_fails_for_<mutant>` mutation test; every property assembles a
  real FDM system and solves it through the kernel, so generated inputs
  genuinely reach the solve (reachability is inherent).
- **Metamorphic (G5):** 3 relations in the same suite — M1 ambient-shift
  invariance (x(b + c·A·1) = x(b) + c), M2 positive-scaling invariance
  (x(2A, 2b) = x(A, b)), M3 permutation covariance (x′(π(i)) = x(i)).
- **Rust unit tests:** `solve.rs` `#[cfg(test)]` — 1×1 / 2×2 /
  tridiagonal hand-solved systems, malformed-input rejection (length
  mismatch, out-of-range triplets), singular-matrix behavior (returns
  non-finite, matching scipy's non-raising warning-and-NaN), and
  determinism.
- **End-to-end suites over the migrated solve:** the full pre-existing
  thermal verification surface (`test_thermal_fdm.py`,
  `test_thermal_fdm_rust_differential.py`, `test_thermal_fdm_mms.py`,
  `test_thermal_fdm_refinement.py`, `test_thermal_fdm_invariants_pbt.py`,
  `test_thermal_fdm_matrix_class.py`, `test_heat_removal.py`,
  `test_thermal_scorer*.py`) passes unchanged against the faer solve —
  the assembly-parity bits, the physical invariant battery, the MMS
  convergence, and the U5-vs-U7 falsifiability threshold all hold.

---

# Independent Thermal Scorer (U7) — Verification by Induction

Wave 3 candidate #6 (`docs/plans/2026-07-31-001-feat-wave3-rust-migration-roadmap-plan.md`):
the pure compute of `temper_placer/validation/thermal_scorer.py` — the
second, INDEPENDENT convective-boundary (Robin BC) FDM T_j scorer whose
repeated sparse assembly sits inside battery experiments — ported to
`temper_thermal.thermal_scorer`. The sparse SOLVE is delegated to the
`temper-thermal` crate's faer sparse LU (2026-08-09, `solve.rs` — see
the "Sparse solve kernel (U5/U7)" section; the KTD9 keep is overturned
there with the measured 5.7e-12 K tolerance). The falsifiability
assertion's 1.0 deg-C threshold against the U5 field solver is a
separate, PRESERVED Python-side contract and is untouched.

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
four boundary-predicate helpers (mirroring
U5's retained helpers), and `falsifiability_assertion` with its 1.0 deg-C
threshold (the preserved THM-adjacent cross-check contract). The
`spsolve` call (the KTD9 keep) was migrated to `solve::solve_sparse_lu_py`
on 2026-08-09.

## FFI Audit (spike C7, 2026-08-01) — tagged-type simplification

B-class parameters converted to int enums, with the public Python API
unchanged (the wrapper converts once):

| pyfunction | Old | New |
|---|---|---|
| `assemble_system_py` | `heatsink_edge: String` | `heatsink_edge: i64` code (`HEATSINK_*` in fdm.rs; 0=TOP, 1=BOTTOM, 2=LEFT, 3=RIGHT, any other = no heatsink → all-Neumann) |
| `assemble_convective_system_py` | `heatsink_edge: String` | `heatsink_edge: i64` code (same enum) |

The Python wrappers (`thermal_fdm.py::_heatsink_edge_code`,
`thermal_scorer.py`) apply the old `.upper().strip()` normalization and
map to the code; unrecognized edges map to 99, reproducing the old
all-Neumann / all-convective behavior exactly (pinned by
`test_thermal_scorer_rust_differential.py`'s "NORTH" edge case).
The `fdm.rs`/`thermal_scorer.rs` match arms are the same decisions the
old string compares made. `rtd.rs` and the byte-buffer/`PyBuffer`
surfaces were already A-class and are untouched.

---

# Thermal Potential Field & Greedy Anchoring — Verification by Induction

Wave 4 Phase 4. Home of `thermal_potential::{linspace,
build_potential_grid, phi_edge, phi_copper, phi_coupling, phi_exclusion,
phi_convection, superpose, find_min_valid, enforce_unique_positions_with,
assign_thermal_anchors, audit_anchor}`, the bit-exact port of
`temper_placer/physics/thermal_potential.py`'s compute.

This is a **physics-gated surface** — `thermal_potential` is one of the
four module names `scripts/physics_soundness_register_gate.py` scans for
(`PHYSICS_MODULE_NAMES`), and the anchors it returns become placement
coordinates. It therefore carries the full R24 discipline (soundness
proof, BMC-exhaustive validation on small N, post-solve audit) per
`AGENTS.md` R24 and `docs/physics-verification-methodology.md`, on top of
the standard Wave-4 gates.

## Base Case: a 1-cell grid

`resolution = 1` produces `linspace(a, b, 1) = [0.0 * (b - a) + a] = [a]`
— numpy assigns the endpoint only when `num > 1`, so the single sample is
the *start*, not the stop, and the mirror reproduces that. The grid is
the single cell `(x_min, y_min)` and:

* `phi_edge` is `1 - exp((-d)/lambda)` at that one point — one
  correctly-rounded `exp` and two arithmetic ops, no accumulation;
* `phi_coupling` and `phi_exclusion` start from a zero field and fold in
  zero sources, returning exactly `0.0`;
* `phi_copper` with no zones is the `(1, 1)` constant `1.0 * 0.5`, which
  broadcasts onto any grid;
* `superpose` adds only the enabled weighted components, in the fixed
  order edge → copper → coupling → exclusion → convection;
* `find_min_valid` scans one cell: it is selected iff it satisfies the
  edge strip, zone, keepout and separation predicates, and `phi < +inf`.

`assign_thermal_anchors` on one device and this grid therefore returns
either `{}` (the cell is infeasible) or that cell, clamped to the board —
which is trivially the arg-min over a one-element feasible set. Verified
bit-exactly against the pinned oracle by
`test_direct_build_grid_bit_exact` (resolution 1 is in the sampled set)
and `test_bmc_exhaustive_small_n_anchor_assignment`.

## Induction Step

Three nested inductions compose.

**(a) Over grid cells — the field kernels.** Hypothesis: for a grid of
`n` cells every kernel produces the reference's value at each cell.
Step: each kernel is an *elementwise* map — cell `n+1`'s value is a pure
function of `(x[n+1], y[n+1])` and the loop-invariant scalars (`bounds`,
`decay`, `sigma`, `radius`, `ux`/`uy`), computed with the same operation
order the reference uses. No cell reads another cell's value, so adding a
cell cannot perturb the first `n`. The only cross-cell operator is the
*per-device* fold in `phi_coupling`/`phi_exclusion`, which is handled by
(b).

**(b) Over sources — the per-device folds.** Hypothesis: after folding
`m` devices the accumulator equals the reference's after `m`. Step:
`phi_coupling` performs `field[i] += power * exp(...)` and `phi_exclusion`
performs `field[i] = np_maximum(field[i], barrier)`, both in the
reference's device order, starting from an all-zero field. Each step is a
single correctly-rounded operation applied to the hypothesis's value, so
the `m+1`-th agrees too. Order is *preserved*, never sorted: the addition
fold is order-sensitive (IEEE addition is not associative) and imposing
an order the reference did not have would be a silent behaviour change no
differential could catch. `test_mr1_coupling_superposition_is_exact`
pins the fold's additivity and
`test_mr2_exclusion_is_permutation_invariant` proves the `max` fold is
genuinely order-free by checking *every* permutation rather than sorting.

**(c) Over devices — the greedy assignment.** Hypothesis: after placing
`m` devices, `pass1` and `existing` match the reference's. Step: device
`m+1` is placed by `find_min_valid` against the *same* `phi` array and
the accumulated `existing` list; `find_min_valid` is a deterministic
row-major scan with a strict `<` update, so it returns the earliest cell
attaining the minimum. Adding a device appends to `existing` and never
rewrites an earlier anchor, so the hypothesis carries. The pass-2 loop is
bounded by `MAX_ITERATIONS = 3` and terminates unconditionally; the
`updated` flag can only shorten it. The final clamp and `enforce_unique_positions_with` are single passes over
the ordered result, the latter re-scanning to a fixpoint and mutating in
place so later pairs observe earlier offsets — reproduced exactly
(see the #928 note below for the deliberate re-pin of that behaviour).

`OrderedAnchors` reproduces CPython `dict` semantics for the induction to
be about the same object: re-assigning an existing key updates the value
and keeps the key's original position, which matters when the input
device list repeats a reference (`duplicate_reference_keeps_one_key`).

## R24 Discipline

**1. Chebyshev-style soundness proof (conservative bound).** The claim
the anchoring surface makes is:

> For each device `d`, `phi(anchor_d) <= phi(c)` for every grid cell `c`
> satisfying `d`'s edge-strip, zone, keepout and min-separation
> constraints at the time `d` was placed.

This is a *conservative* bound in the R24 sense: the returned anchor's
potential never *under*-states what is achievable, so downstream
placement can only be handed a position at least as good as reported.
Proof: `find_min_valid` enumerates the full feasible set (it visits every
cell and applies exactly the four predicates), maintains `best_val` as
the running minimum, and updates only on strict `<`. By induction over
the scan (b above) `best_val` is the minimum of the feasible potentials
visited so far; at termination it is the minimum over the whole feasible
set, and `best_xy` is the earliest cell attaining it. Two residuals are
recorded rather than hidden:

* the final **clamp** may move an anchor off the arg-min cell when a zone
  or the board bounds exclude it — the reference logs a warning above
  2 mm and `AuditFinding::OutsideZone`/`OffGrid` surface it;
* the **uniqueness nudge** (`_enforce_unique_positions`, stepping
  `±k·0.5 mm` in x within the board — see the #928 note below) deliberately
  leaves the grid to break an exact tie; `AuditFinding::
  Duplicate` and property P7 both account for it explicitly.

**2. BMC-exhaustive validation on small N.**
`test_bmc_exhaustive_small_n_anchor_assignment` enumerates the *complete*
cross product of 4 edges x 3 resolutions x 3 device counts x 2 zone
states x 2 keepout states x 2 airflow states = 288 configurations on a
20x20 mm board and compares every returned anchor with the pinned oracle
leaf-by-leaf via `float.hex()`. `test_bmc_exhaustive_small_n_field_
components` does the same for every field component on a 3x3 grid across
every edge (including an unknown one) and a lattice of powers, radii,
steepnesses, magnitudes and directions. No sampling and no tolerance is
involved in either — these are proofs for the bounded case.

**3. Post-solve audit.** `thermal_potential::audit_anchor` recomputes
`phi` from the returned coordinates alone — never from the search's
internal state — and re-derives every predicate: on-grid membership, edge
strip, zone, keepout, uniqueness, and minimality against every feasible
cell (`AuditFinding::NotMinimal`). Its fail-capability is demonstrated in
`audit_rejects_a_feasible_but_non_minimal_anchor`,
`audit_flags_an_off_grid_anchor` and
`audit_flags_a_keepout_and_a_duplicate`; the Python-side equivalent is
property P7 in `test_thermal_potential_rust_pbt.py`, guarded by two
mutants (`_off_strip_assign`, an off-grid perturbation).

## Bit-exactness notes

* **B1 (host libm).** `exp`, `cos`, `sin` and `pow` resolve through
  `hostmath`'s `dlsym` cache. Measured on this repo's runtime (CPython
  3.12.13, numpy 2.3.5, macOS/arm64): numpy's float64 `exp`/`cos`/`sin`
  ufunc loops are bit-identical to the host libm at every array length
  this module uses (1, 2, 4, 8, 16, 100, 2500 elements, and the 50x50
  2-D case), so a single resolution serves the scalar `math.*` and the
  array `np.*` call sites alike. The differential re-measures this on
  every run rather than trusting the note.
* **B2 (constant expression).** `np.radians(d)` is measured bit-identical
  to `d * (PI / 180.0)` — the *division* — over 20 000 random degrees,
  and *not* to the reassociated `(d * PI) / 180.0`, which differs on
  ~28 % of them. `test_direct_phi_convection_radians_is_the_division_form`
  pins an angle from the disagreeing set.
* **B5 (NaN comparison semantics).** Three different maxima appear in the
  reference and stay distinct here: `py_max` for CPython's builtin
  `max(power, 1e-6)` (first argument wins on NaN), `np_maximum` for
  `np.maximum(field, barrier)` (NaN propagates from either side), and
  `np_clip` for `np.clip` (NaN propagates; inverted bounds return the
  upper). `f64::max` matches none of them.
* **B7 (operation order).** `x ** 2` is libm `pow(x, 2.0)`, not `x * x`
  (measured to disagree on ~0.14 % of random f64); `(...) ** 0.5` is
  `pow(v, 0.5)`, not `sqrt` (~0.15 %). Both forms appear — the
  min-separation test and the uniqueness distance — and both go through
  `hostmath::pow`.
* **B8 (denormals).** Default IEEE semantics; no fast-math, no FTZ/DAZ,
  no `mul_add` fusion. `test_direct_phi_exclusion_denormal_barrier_is_
  not_flushed` and `test_direct_build_grid_degenerate_and_denormal` pin
  denormal-band results.

### Preserved reference quirks

Two reference behaviours are reproduced verbatim rather than "fixed",
because changing either would be a behaviour change no differential could
catch:

1. `phi_copper` hard-codes `grid_res = 50` *inside itself*, independent of
   `config.grid_resolution`. A zone-fed copper field is therefore always
   50x50 and only broadcasts against a 50x50 potential grid; any other
   resolution raises `ValueError` from numpy. The Rust path raises the
   same class (`FieldError::CopperBroadcast`), pinned by
   `test_module_assign_anchors_copper_zone_shape_mismatch_raises_alike`.
2. `phi_copper` writes `conductance[gx0:gx1, gy0:gy1]` — the first axis
   carries **x** and the second **y**, the transpose of the `meshgrid`
   convention the rest of the module uses. Preserved.

### R13 uniqueness enforcement — deliberate behavioural change (issue #928)

The uniqueness nudge is the ONE deliberate behavioural change in this
module, made 2026-08-10 because the old behaviour was a genuine R13 bug,
not a reference quirk worth preserving:

**Old behaviour (bit-pinned by the migration):** for each pair (i < j)
closer than `tolerance_mm`, move `anchors[j]` to `min(xj + offset_mm,
x_max)`.  Two failure modes, both confirmed by the flaky
`test_p6_anchors_are_unique` counterexample `board=(0,0,40,21)` putting
Q0 and Q3 BOTH at `(40.0, 21.0)`:
1. When `xj` sat at `x_max`, the clamp landed the nudged anchor back ON
   TOP of an anchor already at `x_max`, and the pair was never
   re-checked.
2. The single pair scan never revisited a pair the nudge had newly
   collided with a third anchor.

**New behaviour (both arms, bit-identical):** re-scan every pair until a
full pass makes no move.  Each move places the later anchor on the first
x-position on its row — `+offset_mm` outward, then `-offset_mm` inward,
never beyond the board — that is at least `tolerance_mm` from *every*
other anchor (`search_free_x`).  Because every move lands clear of all
anchors, a move never re-creates a violation, so termination is
guaranteed; a pair whose row is saturated (no in-bounds x-position
clears it) is left as-is rather than clamped onto an anchor.  The R24
soundness claim of §1 is unchanged in direction: the nudge still moves x
only within the board, and for a TOP/BOTTOM edge strip the strip
membership survives; the reachable set widens from `grid ± offset` to
`grid ± k·offset` for any whole `k`, which P7 and `audit_anchor`'s
callers account for.

**Why re-pinned rather than preserved:** the differential's contract is
bit-parity between the Rust kernel and the pinned pure-Python oracle.  A
bug shared bit-for-bit by both arms is still a bug; the differential
that existed to catch migration drift cannot catch a behaviour both arms
got wrong together.  The oracle in
`tests/physics/_thermal_potential_py_oracle.py` was therefore re-pinned
to the new algorithm in lock-step with the Rust kernel, and the
differential now asserts the two arms agree on the NEW behaviour (110
tests, including the two BMC-exhaustive sweeps).  The file header there
records the exception to its "verbatim" rule.

## Empirical Verification

* `packages/temper-placer/tests/physics/test_thermal_potential_rust_differential.py`
  — 110 tests: direct-kernel and module-level pins against the pinned
  oracle in `tests/physics/_thermal_potential_py_oracle.py`, compared
  through type-carrying `float.hex()` signatures
  (`tests/physics/_leafcmp.py`), plus the two BMC-exhaustive sweeps.
* `packages/temper-placer/tests/physics/test_thermal_potential_rust_pbt.py`
  — 34 tests: properties P1–P7 (P6 at 500 examples since the #928 fix),
  one vacuity guard per property (nine
  mutants covering sign flip, constant field, dropped term, double
  count, off-by-one, BC swap, off-grid and non-multiple nudge), three
  R13 regression tests (the x_max merge, the third-anchor collision, and
  the exact #928 flake input end-to-end), and metamorphic relations
  MR1–MR5 (superposition, source permutation, airflow scaling, weight
  linearity, translation) with their exactness claims stated.
* `packages/temper-placer/tests/physics/test_thermal_potential.py`
  — the pre-existing U9/U10 battery, unchanged and still green.
* `cargo test -p temper-thermal` — the crate's own unit tests for
  `linspace`'s three branches, the meshgrid orientation, the copper
  branches (including non-finite zone bounds), NaN fall-through, the
  broadcast error, determinism, uniqueness and the audit.

---

# Coupled-Load Operating Point — Verification by Induction

Wave 4 Phase 4. Home of `operating_point::{l_eff, thermal_chain,
extreme_point, interior_k_grid, interior_scan, audit_bounding}`, the
bit-exact port of the numeric core of
`temper_placer/physics/operating_point.py`.

**Why this crate.** The surface's dominant quantity is the junction
temperature chain `T_amb + P_device * (R_jc + R_cs + R_sa)`, which is the
same lumped thermal model `junction_temp.rs` already hosts; `P_device`
already delegates to `device_power.rs` in this crate (issue #140 — one
power-source formula); and the gate's ceilings are consumed alongside the
thermal battery. The electrical tail (`di/dt`, `L_loop_max`) is a dozen
scalar operations on top of that chain and does not justify a second
home. The alternatives were excluded by ownership (`temper-geometry`,
`temper-io-types`, `temper-design-bundle`, `temper-quality-oracle` are
held by concurrent work), and `Violation`/`GateResult` construction —
which lives in `temper-design-bundle` — deliberately stays in Python so
this migration touches none of it.

## Induction — applicability

`l_eff`, `thermal_chain` and `extreme_point` are **closed-form,
loop-free and recursion-free** functions of their scalar inputs, in the
same sense as this file's `device_power` and `junction_temp` notes: a
fixed sequence of correctly-rounded f64 operations with one comparison
branch (`num <= 0`) and no data structure whose size varies with the
input. R1e's induction requirement is **not applicable** to them, and the
structural argument in the "Soundness" section below stands in its place.

`interior_scan` *does* have iterative structure, and it gets a proper
induction:

**Base case.** With no interior samples the scan returns the endpoint
envelope alone: `endpoint_worst_di_dt = max(di_dt(0), di_dt(1))` and
`endpoint_worst_L_loop_max = min(L_loop_max(0), L_loop_max(1))`, both
CPython builtins (first argument wins on NaN). No sample can then
contradict it, and the reference returns no violations — matched by
`interior_scan_returns_nothing_for_a_non_positive_endpoint` and
`test_direct_interior_scan_non_positive_endpoint_is_silent`.

**Step.** Assume the first `m` samples produced the reference's verdicts.
Sample `m+1` is evaluated against the *same* loop-invariant envelope
(computed once, before the loop) and the same three predicates, in the
reference's order — `breaches_min_feasible`, then `worse_di_dt`, then
`worse_l_loop_max`. Its verdict depends on nothing accumulated from the
previous `m`, so the hypothesis carries and the emitted `Violation` list
is the concatenation the reference builds. Samples with `L_eff <= 0` are
skipped in both, contributing nothing.

## R24 Discipline

**1. Chebyshev-style soundness proof (conservative bound).** The claim:

> For every `k` in `[0, 1]`, `di/dt(k) <= max(di/dt(0), di/dt(1))` and
> `L_loop_max(k) >= min(L_loop_max(0), L_loop_max(1))`.

Proof (restated at `operating_point::l_eff` and in the Python
docstring): `L_eff(k) = L_coil*(1-k) + L_leakage*k` is affine in `k`;
`_validate_config` enforces `L_coil > 0` and `L_leakage > 0`, so `L_eff`
is strictly positive on `[0, 1]` and, being affine, is bounded by its
endpoint values there. `di/dt(k) = V_bus / L_eff(k)` is then monotone in
`k` because `1/x` is monotone on `x > 0`, and
`L_loop_max(k) = (V_BR*derate - V_bus) / (di/dt(k))` is monotone for the
same reason. `P_device` and `T_j` do not depend on `k` at all. A monotone
function on a closed interval attains its extremes at the endpoints, so
the endpoint pair is a conservative bound — the gate never reports a
`di/dt` lower, or an `L_loop_max` higher, than some interior `k`
achieves. This is what licenses the gate to check two points instead of a
continuum.

**2. BMC-exhaustive validation on small N.** Two independent sweeps:

* `operating_point::tests::bmc_interior_bounding_holds_exhaustively`
  (Rust) — 5 coil x 5 leakage x 3 bus x 3 breakdown inductance/voltage
  configurations, each crossed with an exhaustive `k` sweep at 1/1024
  resolution (>100 000 samples), asserting the envelope holds on every
  one.
* `test_bmc_exhaustive_small_n_operating_point` (Python) — the complete
  cross product of 3 buses x 3 breakdowns x 3 coil x 3 leakage x
  2 derates x 2 thermal chains = 324 configurations, every reported
  quantity compared with the oracle bit-for-bit, plus
  `test_bmc_endpoint_bounding_is_exhaustively_sound` sweeping `k` at
  1/512 across the lattice.

Both are paired with fail-capable twins
(`bmc_property_is_fail_capable`, `test_bmc_soundness_property_is_fail_
capable`) that feed a quadratic-dip coupling model — a plausible
non-monotone model, not a strawman — and require the sweep to catch it.

**3. Post-solve audit.** `operating_point::audit_bounding`, exposed as
`operating_point.audit_operating_point(cfg, k0, k1)`, recomputes `T_j`,
`di/dt` and `L_loop_max` from the raw configuration — never from the
gate's intermediate state — compares each against what the gate reported,
and re-derives the bounding claim on a dense interior sweep. Findings are
named (`JunctionTemperatureMismatch`, `SlewRateMismatch`,
`LoopInductanceCeilingMismatch`, `FeasibilityMismatch`,
`InteriorSlewRateExceedsEnvelope`, `InteriorLoopCeilingBelowEnvelope`).
Fail-capability: `audit_catches_a_tampered_report` (Rust),
`test_audit_catches_a_tampered_ceiling`,
`test_audit_catches_an_unsound_coupling_model` and property P6's
`_widened_ceiling` mutant (Python).

## Triaged finding — evaluated monotonicity floor (R22)

The *model* `L_eff(k)` is exactly monotone; its **f64 evaluation** is
monotone only to within ~1.2e-16 relative. When `L_coil` and `L_leakage`
are within a few ulp of each other, `L_coil*(1-k) + L_leakage*k` wobbles
by about one ulp as `k` sweeps, so consecutive `di/dt` samples can step
backwards by that much (found by property P2 under Hypothesis;
falsifying example `L_coil = 1.0000000000000003e-09`,
`L_leakage = 1e-09`).

This is **not a regression and not a soundness gap**: the pure-Python
oracle exhibits the identical wobble at the identical `k` values, the
Rust kernel reproduces it bit-for-bit (pinned by the differential), and
the envelope predicates the gate actually enforces carry the reference's
own `1e-12` relative guard bands — roughly 1e4 times the observed
wobble, so no violation can be triggered by it. It is recorded here as an
accuracy floor, and property P2 states the bound it actually holds to
(same-direction step, or a step no larger than 4 ulp) rather than
claiming a strict monotonicity the arithmetic does not deliver.

## Bit-exactness notes

* **B5.** `max(di_dt_k0, di_dt_k1)` and `min(l_loop_max_k0,
  l_loop_max_k1)` are CPython *builtins*: the first argument wins
  whenever the comparison is false, NaN included. `f64::max`/`f64::min`
  discard NaN and would silently narrow the envelope the gate enforces —
  pinned by
  `test_direct_interior_scan_nan_endpoint_keeps_the_first_argument`.
* **B7.** `(R_jc + R_cs) + R_sa`, `T_amb + (P * R_th)`, `V_BR * derate`,
  `v_br_derated - V_bus`, `num / di_dt` and the guard factors
  `worst * (1.0 + 1e-12)` / `* (1.0 - 1e-12)` all keep the reference's
  grouping and order.
* **B8.** A denormal `P_device` survives `T_amb + P * R_th` on both
  sides (`test_direct_extremes_denormal_power_is_not_flushed`).
* **B1–B4, B6, B9, B10** are not applicable: no libm transcendental, no
  rounding, no distance, no repr string.

## Empirical Verification

* `packages/temper-placer/tests/physics/test_operating_point_rust_differential.py`
  — 80 tests: direct-kernel and module-level pins against the verbatim
  oracle in `tests/physics/_operating_point_py_oracle.py` (including the
  assembled `Violation` payloads and the `_coupling_l_eff_fn` test
  hook), the BMC sweeps, and the audit's fail-capable cases.
* `packages/temper-placer/tests/physics/test_operating_point_rust_pbt.py`
  — 27 tests: properties P1–P6 with one vacuity guard each (dipping
  model, reversed endpoints, sign-flipped thermal chain, loosened
  feasibility, widened ceiling), and metamorphic relations MR1–MR4
  (inductance scaling, endpoint permutation, reflection, thermal-
  resistance scaling) with their exactness claims stated.
* `packages/temper-placer/tests/physics/test_operating_point.py` and
  `test_operating_point_monotonicity.py` — the pre-existing U6/U2
  batteries, unchanged and still green.

# Phase 4 continuation: emi / safety / heat_removal / copper_coverage / tj_cross_check

Added 2026-08-04 (Wave 4 Phase 4, second slice — the sibling #713 landed
`thermal_potential` + `operating_point`; this slice migrates the five
remaining physics modules' compute).  The remaining Python modules keep
their public APIs and delegate; bit-identical parity is pinned by the differential suites
listed per module below.  `hostmath` was extended with `log`/`log10` (the
emi/safety kernels need them; `sqrt` deliberately stays `f64::sqrt` per
hostmath's documented reasoning — IEEE correctly-rounded, bit-identical to
libm).

**Oracle-convention note (this slice).** The Wave-4 guide's documented
unit of work places the verbatim pre-migration implementation in a
separate `_<mod>_py_oracle.py` module (as #713 did for
`_thermal_potential_py_oracle.py` / `_operating_point_py_oracle.py`).
This slice instead EMBEDS the oracles inside each differential test file
as `_oracle_*` functions (`test_emi_rust_differential.py`,
`test_safety_rust_differential.py`,
`test_heat_removal_rust_differential.py`,
`test_copper_coverage_phase4_rust_differential.py`,
`test_tj_cross_check_rust_differential.py`).  The oracle content is
verbatim (semantically identical to the pre-migration implementation,
pinning the same bit-exact behaviour) — only the file SHAPE differs
from the documented convention, so the differential suites double as
their own oracle reference and the perf harness imports them directly
(`benchmarks/perf_ab.py`).  Verified verbatim against the pre-migration
implementations at migration time (2026-08-04).

**R1b performance A/B status — NO_BASELINE, by decision.** The six
physics benchmarks are registered in `benchmarks/perf_ab.py`, but the
committed baseline (`power_pcb_dataset/metrics/perf_ab_baseline.jsonl`)
carries NO rows for them: the 30 rows this PR originally committed were
local darwin/arm64 measurements (`git_commit` literally `"HEAD"`),
which violate the harness's documented contract — "CAPTURE IT ON CI,
NOT LOCALLY" (`benchmarks/perf_ab.py` docstring, measured -11% darwin-
vs-linux bias, provably blind in the +20..+35% band).  They were
REMOVED in review (restoring the baseline to its pre-PR state; the
pre-existing loaders/bottleneck-geometry rows are untouched).  The
physics arms are therefore honestly **NO_BASELINE** until a CI capture
lands: per the harness's per-key convention they are REPORTED in the
comparison output without failing (NEW_BENCHMARK on this PR — main does
not yet have the physics registry — then NO_BASELINE on later PRs until
a capture lands; never silent confidence), and this PR does not claim
otherwise.  Capturing
the physics rows is a NAMED FOLLOW-UP (trigger
`.github/workflows/pr-perf-check.yml` on main via workflow_dispatch,
append the published rows in a reviewed PR) — nothing writes the
baseline file automatically, by the harness's design.  The loaders
(`bottleneck-geometry`) arm keeps its existing CI-captured rows and is
still compared normally.

**darwin RTLD_DEFAULT pin — CI-blind, by decision (pass 2 P2).**  The
macOS `RTLD_DEFAULT = (void*)-2` correction in
`hostmath.rs::dlsym_ptr` is pinned by `dlsym_resolves_on_macos`, a
`#[cfg(target_os = "macos")]` unit test that NEVER executes in CI
(every workflow runs ubuntu-latest, where the NULL-handle arm is
correct for glibc).  On darwin the differentials pass under either
resolution (dlsym and the std fallback resolve the same libSystem
functions), so the pin is the ONLY thing that would catch a regression
of the handle value.  **Recorded follow-up: the pin requires a local
macOS `cargo test` (run `cargo test --all-features -p temper-thermal`
on a darwin host), or a future macOS CI runner — no macOS CI job is
added in this PR, by decision.**  The BSDs share `RTLD_DEFAULT = -2`
with macOS but are NOT covered by the `target_os = "macos"` cfg (they
fall to the NULL arm — a recorded gap; no BSD target is built or
tested in this repo's CI).

## EMI radiated-emissions kernels — induction non-applicability note

`emi::predict_radiated_emissions` and `emi::check_emi_compliance` are
**closed-form, loop-free and recursion-free functions of their scalar
inputs** — no size-parameterized invariant to induct on, so R1e is **not
applicable** in the induction form; the structural correctness argument is
recorded instead (same convention as the prior kernel notes).

### Structural correctness argument (bit-exact parity)

1. **Pure functions of scalars.** Every output bit depends only on the
   scalar arguments and on correctly-rounded IEEE-754 f64 arithmetic,
   deterministic and identical in CPython and Rust for the same operation
   sequence.
2. **Operation-order pinning** (pinned by
   `tests/physics/test_emi_rust_differential.py`, which embeds the verbatim
   pre-migration implementation as an oracle): `frequency_mhz ** 2` is
   CPython `float.__pow__` → host libm `pow(x, 2.0)` via `hostmath::pow`
   (B1) — NOT `x * x` (pinned by the pow-vs-mul discriminator);
   `(1.316e-14 * A * I * pow(f, 2.0)) / d` is the exact four-op left-to-
   right chain (B7); `e_v * 1e6`; the `e_uv_per_m <= 0` guard; `20.0 *
   log10(...)` with `hostmath::log10` (B1).  B8 denormal-band parity
   pinned.
3. **Branch equivalence.** The three `<= 0` input guards and the output
   guard are IEEE comparisons (NaN flows through, exactly like the
   reference).
4. **R24.** Analysis estimator (metrics/physics.py EMI measurement), not a
   CP-SAT constraint encoder — the constraint-form R24 gates do not apply;
   bit-exact parity (R1a) is the applicable contract.

### Empirical verification

- Differential: `test_emi_rust_differential.py` — 20 randomized-seed ×
  50-sample pins, known values, pow-vs-mul discriminator, guard arms, the
  underflow guard, denormal band, NaN/inf parity, compliance limits, and
  module-level delegation.
- PBT: `test_emi_rust_pbt.py` — 5 vacuity-guarded properties (each with a
  real mutant) + 4 metamorphic relations (honestly bounded dB scaling
  laws, compliance-limit monotonicity).
- Rust unit tests in `emi.rs`.

## Safety-interlock timing kernels — induction non-applicability note

`safety::estimate_filter_delay` / `estimate_fault_response_time` /
`is_safety_timing_valid` are closed-form scalar functions — R1e **not
applicable** in the induction form; structural argument recorded.

### Structural correctness argument (bit-exact parity)

1. **Operation-order pinning** (pinned by
   `tests/physics/test_safety_rust_differential.py`): `tau = r * c`;
   `(-tau) * log(1.0 - threshold)` with the unary minus bound BEFORE the
   multiply (B7); `(comparator_delay_ns + mcu_latency_ns) * 1e-3`
   parenthesized; `hostmath::log` (B1).
2. **The unary minus is an opaque call (`negate`), not an inline
   `-tau`.**  LLVM's DAGCombine sinks an inline `fneg` into the
   innermost multiply (`(r * (-c)) * log`); for finite inputs that is
   bit-identical, but for a NaN `tau` the compiled NaN payload SIGN
   flips vs the oracle's `(-tau) * log(...)` (the hardware propagates
   the NaN operand's own sign, and the NaN rides on `r`, whose sign was
   never flipped).  `#[inline(never)]` keeps the sign-flip its own
   instruction and reproduces the oracle's bits for all four non-finite
   argument positions (issue #927, 2026-08-10).  If a future compiler
   re-inlines `negate`, `test_direct_nan_inf_semantics` fails loudly —
   re-verify, don't silence.
3. **Domain-error parity (the reference raises).** CPython `math.log(x)`
   raises `ValueError("math domain error")` for `x <= 0.0` (incl. `-0.0`)
   but returns NaN for NaN.  The pyo3 bridge replicates this exactly in the
   reference's guard order (`r <= 0 || c <= 0` returns 0.0 first, then the
   raise).  Pinned by `test_direct_threshold_extremes`.
4. **R24.** Safety-timing estimators, not constraint encoders — parity is
   the applicable contract.

### Empirical verification

- Differential: 20 randomized-seed pins, known values (one time constant →
  exactly RC), guard arms, NaN/inf, threshold extremes with the raise arms,
  module-level delegation.
- PBT: `test_safety_rust_pbt.py` — 5 vacuity-guarded properties + 3
  metamorphic relations (M1 power-of-two scale EXACT, M2 r·c commutativity
  EXACT, M3 component commutativity EXACT — the stronger ±shift claim is
  NOT made because float addition is not associative).

## Vertical-sink field kernel — induction non-applicability note

`heat_removal::build_h_field` is the migration of
`temper_placer/physics/heat_removal.py::build_h_field` (issue #141).  The
loop over devices is **data-driven with a per-element formula independent
of the collection's size and of the iteration order** — R1e **not
applicable** in the induction form; structural argument recorded.

### Structural correctness argument (bit-exact parity)

1. **Closed-form per-cell arithmetic (B1/B7).** `h_bg = (10.0 *
   pow(cs*1e-3, 2.0)) / (cs*cs)` via `hostmath::pow`; per-device
   `g_dev = 1.0 / (r_cs + r_sa)`; bbox from `max(0, int(np.floor((x -
   2.5 - ox)/cs)))` / `min(w, int(np.ceil(...)))` (floor/ceil-then-
   truncate = `as i64`); `n_cells = max(1, raw product)` from the RAW
   post-clamp values; `h_cell = g_dev / ((n_cells * cs) * cs)`.
2. **numpy slice semantics (the trap this migration found).** When a
   footprint sits LEFT of / BELOW the grid, `min(w, int(ceil(...)))` goes
   NEGATIVE and numpy wraps the slice stop as `dim + stop` (measured:
   `a[:, 0:-3]` on width-4 covers columns [0, 1)) — while `n_cells` is
   computed from the raw pre-wrap values.  The kernel replicates both
   behaviors exactly, pinned by dedicated wrap tests.
3. **Iteration order.** Devices accumulate in the caller's dict order
   (overlapping footprints `+=` in the same order on both sides).
4. **R24.** Input FIELD builder for the FDM (not a constraint encoder);
   the field's boundedness (non-negative, ≤ background + Σ g_dev/
   (n_cells·cs²)) is asserted by PBT P4.

### Empirical verification

- Differential: `test_heat_removal_rust_differential.py` — 8 randomized
  seeds with in-grid/edge/off-grid devices, the negative-slice-wrap pins,
  denormal band, the pow-vs-mul h_bg discriminator (cs=66.24771326355554 —
  a mul-mutant initially SURVIVED the randomized differential and was
  closed with this 1-ulp pin), module-level delegation incl. the original
  ValueError arms.
- PBT: `test_heat_removal_rust_pbt.py` — 5 properties + 3 metamorphic
  relations (origin-translation covariance, area-consistency
  `peak·(n_cells·cs²) = g_dev`, R_θ commutativity).

## Copper-coverage grid kernels — induction non-applicability note

`copper_coverage::copper_masks` and `copper_coverage::copper_trace_accumulate`
are the migration of `temper_placer/physics/copper_coverage.py`'s mask and
per-trace-accumulation arithmetic (issue #137).  Per-element formulas, no
size-parameterized invariant — R1e **not applicable**; structural argument
recorded.

### Structural correctness argument (bit-exact parity)

1. **Per-element closed forms (B1/B7).** Cell centres `ox + ((col + 0.5) *
   cs)`; rect bounds IEEE `<=`; the keepout circle test and the trace cap
   keep the reference's op order.
2. **Array `** 2` vs float `** 2` (the trap this migration found).**
   Measured 2026-08-04: numpy's `** 2` on an ARRAY with an INTEGER
   exponent dispatches to the x*x multiply path (NOT libm pow), while
   `kr ** 2` on a PYTHON float IS libm pow.  The circle test uses both —
   the kernel mirrors both exactly (a pow-for-offsets kernel is bit-wrong;
   closed with a constructed adjacent-float discriminator pin).
3. **`np.minimum` NaN semantics.** `np.minimum(1.0, grid + cell_cov)`
   propagates NaN from either operand — implemented explicitly (Rust
   `f64::min` discards NaN; pinned by the NaN-propagation test).
4. **Iteration order.** The mask accumulation is a bool OR (order-
   independent — pinned by the keepout-permutation metamorphic); the trace
   path accumulates per trace in caller order.
5. **R24.** Copper fraction is an input FIELD (not a constraint encoder);
   the [0, 1] boundedness is asserted by PBT P1/P4.

### Empirical verification

- Differential: `test_copper_coverage_phase4_rust_differential.py` — 6
  randomized mask seeds, the mul-vs-pow offset discriminator, the pow-vs-
  mul radius discriminator (kr=2.882033520478047), 6 randomized trace
  seeds, NaN propagation, module-level end-to-end pins (keepouts + holes,
  traces incl. tuple form, zero-weight stackup, plausibility).  The Wave 3
  rasterise differential continues to pin the polygon boundary.
- PBT: `test_copper_coverage_phase4_rust_pbt.py` — 5 properties + 3
  metamorphic relations (keepout-order permutation bit-exact, hole mirror
  symmetry bit-exact, resolution invariance of the mean — honest approx
  bound).

## T_j cross-check kernels — induction non-applicability note

`tj_cross_check::distance_to_heatsink_edge` and `tj_cross_check::device_cross_check`
are the migration of `temper_placer/physics/tj_cross_check.py`'s scalar
cross-check arithmetic (U11).  Closed-form scalar functions — R1e **not
applicable**; structural argument recorded.

### Structural correctness argument (bit-exact parity)

1. **Closed-form chains (B7).** `H = height_cells * cell_size` (int
   widened exactly like Python int*float); `abs(oy + H - y)` etc.;
   `T_j_fdm = T_case_fdm + power * R_jc`; `R_total = R_jc + R_cs + R_sa`;
   `T_j_lumped = T_amb + (power * R_total)`; `delta = abs(...)`;
   `margin = T_j_max - conservative`; `exceeds = delta > tau`.
2. **Python max semantics.** `conservative_T_j = max(T_j_fdm, T_j_lumped)`
   is CPython's two-arg max (first argument wins unless the second is
   strictly greater — `max(nan, x) = nan`, measured 2026-08-04); the kernel
   implements the same rule explicitly, NOT `f64::max` (which discards
   NaN).  This matters for the safety gating.
3. **Kept-Python boundary (np.mean).** `_area_average_temperature`'s
   `np.mean` is deliberately NOT migrated: numpy 2.3.5's SIMD reduction is
   not bit-reproducible by any Rust summation strategy (measured 2026-08-04
   on arm64 — naive, Neumaier, pairwise-128 and sequential-block pairwise
   all disagree with np.sum/np.mean even for n=8).  This is the genuine
   measured-blocker class of keep — distinct from the scipy-spsolve keep,
   which was overturned 2026-08-09 (see the "Sparse solve kernel" section)
   because a measured parity result made the migration defensible; np.mean
   has no such parity result.  Argued in-source at the call site.
4. **R24.** Gate, not a constraint encoder: the T_j_max ceiling is gated
   on the CONSERVATIVE (higher) estimate so the optimistic model can never
   decide; corroborated-but-over-limit is still a VIOLATION.  Fail-closed
   on missing R_θ.

### Empirical verification

- Differential: `test_tj_cross_check_rust_differential.py` — 8 randomized
  distance pins (incl. unknown-edge zero), known values, 8 randomized
  device-check pins with NaN in every argument position, the
  conservative-max NaN pin, module-level delegation.
- PBT: `test_tj_parameter_bounds_rust_pbt.py` — **5 properties + 3
  metamorphic relations for
  tj_cross_check** (P1 conservative ≥ both estimates, P2 delta/exceeds
  exact with the strict-`>` boundary, P3 distance geometry, P6 margin
  definitional, P7 exceeds gated only on (delta, tau); M1 zero-power
  degeneracy, M2 conservative order-independence, M4 reciprocal
  power-of-two scaling), **each property and relation vacuity-guarded
  by a real mutant** — pass 2 added the missing P3 / M1 / M2 / M4
  guards (`test_p3_fails_for_drops_abs`,
  `test_m1_fails_for_phantom_power` (evaluated at NONZERO power — a
  phantom power-proportional term is invisible at p=0, the honest
  guard for M1's degenerate sampling),
  `test_m2_fails_for_first_arg_wins`,
  `test_m4_fails_for_forgot_halve_r`), so the header's "every property
  is guarded" claim now holds.

## Parameter-bound kernels — induction non-applicability note

`parameter_bounds::classify_parameter` and `parameter_bounds::worst_case_values`
are the migration of `temper_placer/physics/parameter_bounds.py`'s
monotonicity classification and worst-case-corner selection (L2).  No
size-parameterized invariant — R1e **not applicable**; structural argument
recorded.

### Structural correctness argument (bit-exact parity)

1. **Classification fidelity.** The keyword rules replicate the reference's
   exact branch ORDER and its BUG-FOR-BUG case sensitivity: `"P_loss" in
   param_lower` compares the capital-P literal against the LOWERCASED name,
   so it never matches (dead code); the kernel keeps the same literal.
   Found by the differential (a lowercased kernel misclassified
   `P_LOSS_W4`).  The `because` citation strings are reproduced VERBATIM
   (double spaces, interpolated original-case name).  Rust `to_lowercase`
   matches CPython `lower()` for the ASCII parameter names in the prereg
   manifests (documented divergence: non-ASCII case folding — none in the
   repo's surface).
2. **Worst-case selection.** `mono < 0 → min, else max` (0 is
   conservatively max — not a guarantee, per the module's own docs).
3. **Retired Python surface.** The former
   `build_thermal_parameter_bounds` / `compute_thermal_soundness` Python
   module had no production callers and was deleted. Its binding-only Rust
   adapters, result classes, and proof-text export were deleted with it;
   only the two pure Rust kernels above remain, together with their Rust
   unit/WASM tests.
4. **R24.** This module IS the L2 soundness-gate surface.  Its
   Chebyshev-style soundness claim: the worst-case corner bounds every
   interior configuration for provably-monotone parameters, via the
   M-matrix A⁻¹ ≥ 0 monotonicity argument; mono-0 parameters are NOT
   guaranteed and the module says so.  The corner computation IS the audit
   of that claim.

### Empirical verification

- Rust unit/WASM tests in `parameter_bounds.rs` cover the three parameter
  families, precedence, unknown parameters, citations, and element-wise
  worst-case selection. The former Python differential/PBT files were
  binding-only compatibility tests and were retired with the deleted
  PyO3 surface.

## Anti-vacuity summary (this slice's kernels)

Mutants applied to the Rust kernels and confirmed to fail the
differential/PBT, then reverted.  Each mutant is listed ONCE: a mutant
either was killed by the general differential/PBT suite, or it survived
that suite and was closed with a CONSTRUCTED discriminator pin (the
guide's "no survivor left open" pattern).  A closing pin is NOT a
separate kill — it is the evidence that the survivor is bit-wrong.

**Totals: 19 mutants applied; 16 killed by the general suite; 3
survived the general suite and were each closed with a constructed
discriminator pin (no survivor left open).**  (The survivors: one
heat_removal pow→mul in h_bg, and two copper_coverage mutants —
pow-for-offsets and kr·kr-for-radius — the two arms of the array-`** 2`-
is-mul / float-`** 2`-is-pow trap.)

| Module | Mutants | Killed by (general differential/PBT) | Survived the general suite → closed by constructed pin |
|---|---|---|---|
| emi | 3 | randomized pins, pow-vs-mul discriminator, underflow guard | — |
| safety | 2 | B7 order mutant → randomized pins + one-time-constant; domain-error raise-arm mutant → test_direct_threshold_extremes | — |
| heat_removal | 5 | R_vert-skip pin, randomized pins, slice-wrap pin, off-by-one | pow→mul in h_bg → closed by the 1-ulp discriminator pin (cs=66.24771326355554; the cs is now SEARCHED on the loaded libm, issue #927) |
| copper_coverage | 5 | rect axis, trace min-cap, NaN-discard | pow-for-offsets → closed by the mul-vs-pow offset discriminator; kr·kr-for-radius → closed by the radius pow-vs-mul discriminator (the kr is now SEARCHED on the loaded libm, issue #927) |
| tj_cross_check | 2 | NaN conservative-max pin, distance abs pin | — |

(No operating_point flag-bit-swap entry: that module landed via #713.)

Every kill was confirmed by the differential/PBT failing under the
mutated kernel, then reverting; every survivor is pinned by a
constructed discriminator that flips exactly under the mutation (see
the per-module differential sections above for the discriminator
values).
