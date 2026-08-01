# IPC-2152 Ampacity Model — Verification by Induction

Wave 2 slice of the Python→Rust migration roadmap
(docs/plans/2026-07-23-003): the physics model behind the
CURRENT_DENSITY gate (`_ipc2152_forward`, `_min_width_ipc2152` in
`temper_placer/placer/cp_sat/gates.py`), ported to
`temper_constraints.ipc`.

## Base Case

For `current_a <= 0.0`, the minimum width is `0.0` (no current, no
width requirement). For a 1×1 search interval, the bisection midpoint
is `(lo + hi) / 2` and the forward map is evaluated at that single
point — the Rust core and the pinned Python oracle agree bit-for-bit.

## Inductive Step

The bisection is 60 iterations of the same scalar contraction:
`mid = (lo + hi) / 2`, `cap = forward(mid)`, shrink one bound. Each
iteration is a pure function of the previous interval, so if the
k-th iteration matches the reference, the (k+1)-th does too — the
arithmetic order (`k_ext * pow(rise, 0.44) * pow(area, 0.725)`,
internal-layer derate `* 0.65`) is preserved exactly, and the final
`round(x, 3)` replicates Python's banker's rounding (round-half-even)
via `round_ties_even`, not `f64::round` (half away from zero).

`pow` is resolved through dlsym so the crate matches the host Python
runtime's own libm (the uv standalone build's libm can differ from
the crate's statically-bound `f64::powf` in the last ulp — the same
class of divergence as the sin/cos fix in temper-geometry's
pad_geometry).

## Empirical Verification

The differential suite
(`packages/temper-placer/tests/placer/cp_sat/test_ipc2152_rust_differential.py`)
pins both functions bit-exactly against the pre-migration
implementations (1000 random forward cases, 500 random inversion
cases across oz/rise/internal combinations, zero/negative current,
and the known 1 mm / 1 oz / 10 °C operating point: 3.225 A forward,
2 A threshold inverting to 0.517 mm). The pre-existing
`test_stackup_gate.py` (16 tests) now exercises the Rust model
through the gate. PBT properties
(`tests/placer/cp_sat/test_ipc2152_pbt.py`): forward monotonic in
width and rise; internal never exceeds external (exact 0.65 derate);
minimum width monotonic in current; roundtrip within a rounding step
with the pinned-bound behavior asserted when the root lies above the
50 mm search range (the reference's documented out-of-range pinning,
which correctly flags an unroutable-width violation).

# CP-SAT Encoder Pure Compute — Verification by Induction (Wave 3 #4)

The CP-SAT constraint encoder's pure numeric surface
(`temper_constraints.encoder`): the unit conversion and margin
parameters the encoders compute from board geometry before/around the
ortools calls.  The ortools orchestration (CpModel/IntVar construction,
handler dispatch, solver calls) stays Python; these five functions are
the entire numeric core, pinned bit-exactly by
`packages/temper-placer/tests/placer/cp_sat/test_encoder_rust_differential.py`
and `test_encoder_rust_pbt.py`.

Migrated functions (Python reference in parentheses):

- `mm_to_units(mm, units_per_mm)` — `CpSatModel.mm_to_units`:
  `int(round(mm * units_per_mm))` (Python round-half-even on the float)
  then forced even parity.  This is the spine of the encoder: every
  handler's margin math (separated/enclosing/onside/adjacent/aligned
  margins, the keepout rect, the board-edge margin) funnels through it.
- `units_to_mm(units, units_per_mm)` — `CpSatModel.units_to_mm`:
  `units / units_per_mm`.
- `courtyard_clearance_mm(default, expansion)` — `_encoder_solve.py`
  C1: `default + 2 * expansion` (strict `+`, not `max()`).
- `required_margin_mm(clearance, creepage)` — `domain_clearance.py`:
  Python-builtin-`max` semantics (`max(NaN, x) == NaN` but
  `max(x, NaN) == x`, unlike `f64::max`).
- `keepout_rect_units(zx_min, zy_min, zx_max, zy_max, margin, units_per_mm)`
  — `handlers/keepout.py`: the margin-expanded keepout bbox in model
  units (start = converted corner − converted margin; size = converted
  *span* + 2 × converted margin).

## Base Case

For the smallest meaningful inputs — `mm_to_units(0.0, u) == 0` (zero
mm converts to zero units, even parity trivially holds), and the exact
binary tie `mm = m/8` at u = 100 (`mm·u` is exactly `k + 0.5`, e.g.
`0.125 → 12`, `0.375 → 38`, `0.625 → 62` under round-half-even) — the
Rust core and the pinned Python oracle agree bit-for-bit.  The known
operating points are pinned in the differential suite and in the Rust
unit tests: `mm_to_units(10.0, 100) == 1000`, `units_to_mm(1000, 100)
== 10.0`, `courtyard_clearance_mm(0.2, 0.1) == 0.4`,
`required_margin_mm(6.0, 8.0) == 8.0`,
`keepout_rect_units(10, 10, 20, 20, 0.5, 100) == (950, 950, 1100, 1100)`.

## Induction Step

Every migrated function is a pure function of scalar arithmetic with no
cross-input state, so correctness lifts from any input to the next by
operation-order preservation:

1. **mm_to_units is a pointwise map.**  The output for a single mm is a
   pure function of the scaled float: `round_ties_even` (the exact
   replica of CPython's `round(x)` for the ndigits=0 path — both give
   round-half-even for ties, and `int(round(±inf))`/`int(round(nan))`
   raise OverflowError/ValueError, replicated) followed by a per-value
   parity clamp.  Since the conversion of each component depends only on
   that component's own scaled value, a component list of any size
   converts correctly by induction on the list length — the model's
   midpoint invariant `x_start + x_end == 2 * x_center` requires exactly
   this per-component evenness.
2. **The parity clamp is order-exact.**  `raw - (raw % 2)` uses Python's
   *floor* modulo: a negative odd raw decrements by one (-15 → -16).
   Rust's truncating `%` would give -14, so the port uses
   `rem_euclid(2)` — the differential suite pins the negative-odd case
   explicitly (`mm_to_units(-0.155, 100) == -16`).
3. **keepout_rect_units composes mm_to_units with preserved order.**
   Each output is a sum/difference of exactly two conversions whose
   operands are fixed by the reference: `mm_to_units(zx_min) − margin_u`
   and `mm_to_units(zx_max − zx_min) + 2·margin_u`.  The *span* is
   converted first (f64 subtraction of the corner floats, then the
   conversion) — never a difference of conversions, which can disagree
   at rounding boundaries (the differential suite pins a measured pair
   where the two orders give -90 vs -88).  Margins and corners convert
   identically by point (1), so a rect for any zone is correct.
4. **The margin parameters are one-op pure functions.**
   `courtyard_clearance_mm` preserves the reference's `2 * expansion`
   first, then the addition; `required_margin_mm` replicates the
   builtin `max` decision (`b > a ? b : a`), so both are correct for
   every input by definitional equality with the pinned oracle.

Extending to the whole encoder surface: every handler's margin is
`mm_to_units(margin_mm)` (a pointwise conversion), and the courtyard/
keepout/enclosing/onside handlers feed the solver one independent
margin-derived term per component/pair — appending a component adds
independent terms, so the encoder's numeric layer is correct for any
board by induction on the component count.

## Empirical Verification

The differential suite pins all five functions bit-exactly against the
pre-migration implementations: 400+500 randomized mm/unit conversions
across grids {1, 10, 50, 100, 101, 1000} (negative values included),
300 units_to_mm, 300 τ samples, 300 required-margin samples, 400
randomized keepout rects, plus the edge cases: exact binary ties,
odd-raw even-adjustment, negative floor-modulo, zero/small inputs,
non-finite errors, span-vs-difference-of-conversions disagreement, and
the NaN builtin-max semantics.  The pre-existing `test_model.py`,
`test_courtyard_edge.py`, `test_domain_clearance.py`, and the geometry
PBT suites keep exercising the Rust core through the wrappers.  PBT
(`tests/placer/cp_sat/test_encoder_rust_pbt.py`): five non-vacuous
properties per function — each fails if the function returned a
constant — plus five metamorphic relations (mm_to_units scale identity,
required-margin order permutation, τ additive decomposition, keepout
zero-margin dual-call identity, keepout margin containment).

## Known Environment Limitation

`cargo test` on this crate aborts at dyld load (`_PyBool_Type` symbol
not found in flat namespace) on macOS — a pre-existing condition that
also affects the crate's `ipc`/`loss` unit tests (verified at the base
commit); the crate's Rust unit tests are validated through the pytest
differential suite against the built wheel instead.
