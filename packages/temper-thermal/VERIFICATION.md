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
and `inductance::estimate_gate_inductance` added (Wave 4 Phase A #4 —
migration of `temper_placer/physics/inductance.py` to Rust; the Python
module keeps its public API and delegates to
`temper_thermal.estimate_loop_inductance_py` /
`temper_thermal.estimate_gate_inductance_py`).  See the
"Parasitic-loop-inductance kernels — induction non-applicability note"
section below.

U6 of the Python→Rust migration roadmap (docs/plans/2026-07-23-003),
porting the assembly hot loops of
`temper_placer/physics/thermal_fdm.py` (`_assemble_system`,
`_trace_to_cell_coverage`, `_point_to_segment_distance`) to the
`temper-thermal` crate. The sparse SOLVE stays in scipy (SuperLU) —
a Rust solver is gated on the KTD9 parity spike (still outstanding;
see the roadmap).

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

## Parasitic-loop-inductance kernels — induction non-applicability note

`inductance::estimate_loop_inductance(loop_area_mm2, perimeter_mm,
layer_separation_mm, routing_factor) -> f64` and
`inductance::estimate_gate_inductance(source_to_gate_dist_mm,
return_dist_mm) -> f64` (Wave 4 Phase A #4 — migration of
`temper_placer/physics/inductance.py`) are **closed-form, loop-free and
recursion-free functions of their scalar inputs**.  The loop estimator
has exactly one branch (the `h_m > 0` conditional area term); the gate
estimator has none:

```text
loop:  MU_0       = 4 * math.pi * 1e-7                      (three-op chain)
       area_m2    = loop_area_mm2 * 1e-6
       h_m        = layer_separation_mm * 1e-3
       L_area_H   = (MU_0 * area_m2 / h_m) if h_m > 0 else 0
       L_area_nH  = L_area_H * 1e9
       L_self_nH  = perimeter_mm * 0.2
       L_total    = (L_area_nH * 0.5 + L_self_nH) * routing_factor
gate:  L          = (source_to_gate_dist_mm + return_dist_mm + 5.0) * 0.8
```

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
     multiply by `routing_factor`; the gate estimator is the
     left-to-right `(a + b) + 5.0` add chain then `* 0.8`.  No
     reassociation, no fusing (**B7**).
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
   surface.** These kernels are analysis estimators consumed by the
   EMI measurement path (`metrics/physics.py::measure_emi`), not
   CP-SAT constraints that gate on a physics quantity; the R24 gates
   (Chebyshev soundness proof, BMC-exhaustive validation on small N,
   post-solve audit recompute) do not apply.  The bit-exactness pins
   above are the applicable correctness contract.

### Empirical verification

- **Differential (G2):** `test_inductance_rust_differential.py` — 40
  randomized-seed direct kernel pins across 25+15 seeds (loop + gate,
  with the h <= 0 degenerate arm), hand-computed known values, the
  `mu_0` named-constant chain pin, the denormal band, NaN/inf parity,
  the zero-height branch flip, and module-level delegation pins with
  defaults — all `==` bit-exact.
- **PBT (G4):** `test_inductance_rust_pbt.py` — 6 non-vacuous
  properties (P1 non-negativity/richness, P2 loop closed form, P3 gate
  closed form, P4 zero-height degeneracy, P5/P6 monotonicity in area
  and perimeter) each vacuity-guarded by a `test_pN_fails_for_<mutant>`
  mutation test (constant kernel, missing 0.5 factor, missing +5.0
  coupling term, unconditional area term, decreasing-in-area and
  decreasing-in-perimeter kernels), plus 5 metamorphic relations (M1/M3
  bit-exact power-of-two scales, M2 zero-routing-factor degeneracy,
  M4/M5 exact monotone comparisons) and a determinism/richness smoke
  test.
- **Rust unit tests:** `inductance.rs` `#[cfg(test)]` — known values,
  zero-height/NaN-h arm selection, zero-routing-factor degeneracy, gate
  op-order pin, and the `mu_0` named-constant chain pin.

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
`updated` flag can only shorten it. The final clamp and
`enforce_unique_positions_with` are single passes over the ordered result,
the latter mutating in place so later pairs observe earlier offsets —
reproduced exactly.

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
* the **uniqueness nudge** (`_enforce_unique_positions`, +0.5 mm in x)
  deliberately leaves the grid to break an exact tie; `AuditFinding::
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

## Empirical Verification

* `packages/temper-placer/tests/physics/test_thermal_potential_rust_differential.py`
  — 109 tests: direct-kernel and module-level pins against the verbatim
  oracle in `tests/physics/_thermal_potential_py_oracle.py`, compared
  through type-carrying `float.hex()` signatures
  (`tests/physics/_leafcmp.py`), plus the two BMC-exhaustive sweeps.
* `packages/temper-placer/tests/physics/test_thermal_potential_rust_pbt.py`
  — 30 tests: properties P1–P7, one vacuity guard per property (nine
  mutants covering sign flip, constant field, dropped term, double
  count, off-by-one, BC swap and off-grid), and metamorphic relations
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
