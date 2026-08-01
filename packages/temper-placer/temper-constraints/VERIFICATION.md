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
