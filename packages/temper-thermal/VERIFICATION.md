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
