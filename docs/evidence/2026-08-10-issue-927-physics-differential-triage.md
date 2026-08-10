# Issue #927 triage — 4 Rust-vs-oracle differential failures in `tests/physics/` (2026-08-10)

<!-- provenance: commit=da07f2c226cebacd1b00493269dc9510f5c92fc2 dirty=false (triage recorded at this commit; re-measured after a clean release rebuild) -->
<!-- provenance: worktree=<wt-927>, branch=fix/physics-differential-927 -->

**What this is.** The triage record for the four pre-existing failures
reported in issue #927 (all reproduced on a clean release rebuild of
`main` at 86e81396).  Per-failure verdict: which side diverged from the
pinned contract — the KERNEL or the TEST — and the exact root cause.
Three were TEST-design artifacts (libm-dependent discriminator
constants) and one was a KERNEL-vs-oracle divergence (compiler
reassociation of a unary minus that changes the NaN payload sign for
invalid inputs).

## Failure-by-failure verdict

| # | Test | Verdict | Root cause |
|---|---|---|---|
| 1 | `test_safety_rust_differential.py::test_direct_nan_inf_semantics` | **KERNEL fix** (`safety.rs`) | LLVM sinks `-tau * log(...)` into `r * (-c) * log(...)`, changing the NaN payload SIGN for `(nan, 1e-6, 0.632)` vs the oracle's `(-tau) * log(...)` |
| 2 | `test_copper_coverage_phase4_rust_differential.py::test_masks_hole_radius_pow_vs_mul_discriminator` | **TEST fix** (re-pin, search-based) | The hardcoded `kr = 2.882033520478047` does not discriminate `pow(kr, 2.0)` from `kr*kr` on the current host libm; kernel already matches the oracle |
| 3 | `test_device_power_rust_differential.py::test_direct_mosfet_pow2_semantics` | **TEST fix** (re-pin, search-based) | The hardcoded `x = 974.5535622665931` does not discriminate `pow(x, 2.0)` from `x*x` on the current host libm; kernel already matches the oracle |
| 4 | `test_heat_removal_rust_differential.py::test_direct_background_pow_vs_mul_discriminator` | **TEST fix** (re-pin, search-based) | The hardcoded `cs = 66.24771326355554` does not discriminate on the current host libm; kernel already matches the oracle |

## Root cause 1 — the NaN payload sign (KERNEL divergence)

The oracle computes `(-tau) * math.log(1.0 - threshold)` — a standalone
IEEE sign-flip of `tau`, THEN a multiply.  The kernel's source is
identical (`-tau * hostmath::log(...)`), but LLVM's DAGCombine sinks the
`fneg` into the innermost multiply, emitting `(r * (-c)) * log(...)`.
For FINITE inputs the two are bit-identical (a sign flip commutes with a
multiply), which is why the whole B7 operation-order discipline passed
for years.  For a NaN `tau` the compiled sign differs: this x86-64
hardware propagates the NaN operand's OWN sign (not the IEEE XOR of the
two signs — verified empirically, CPython `-0.001 * nan` yields a
POSITIVE NaN), so

- CPython `(-tau) * log(...)`  → NaN operand `fff8000000000000` → NEGATIVE NaN
- compiled `(r * (-c)) * log(...)` → NaN rides on `r` (sign never flipped) → POSITIVE NaN `7ff8000000000000`

(Observed: only the `(nan, r_ohms, ...)` position diverged; the `(..., c_farads, nan)`
case passed because there the negation lands on the non-NaN operand either way.)

**Fix.** `safety.rs` now negates through an `#[inline(never)]` helper
(`negate(x) -> -x`), forcing the `fneg` to remain its own instruction
(x86: `xorpd` sign-mask) before the multiply — exactly CPython's operand
structure.  `#[inline(never)]` is required: an inline `-x` is
re-folded by the same DAGCombine and the divergence returns (verified in
isolation).  This keeps `test_direct_nan_inf_semantics` bit-exact for
all four non-finite argument positions.  The NaN payload sign is
implementation-defined noise (no physical meaning), but the contract is
bit-exact parity with the pinned oracle, and reproducing the oracle's
operand structure reproduces its bits on any deterministic hardware.

**Robustness caveat.** The sign match depends on (a) the compiler keeping
the `negate` call un-inlined and (b) the hardware's NaN sign
propagation matching CPython's.  Both hold on this toolchain/machine;
if a future compiler re-inlines `negate` the differential test fails
loudly (it is designed to) and the fix is re-verified, not silent.

## Root cause 2 — libm-dependent discriminator constants (TEST divergence)

Three discriminator pins hardcoded a scalar found by search on the
2026-08-04 migration runtime.  Whether `pow(x, 2.0) != x * x` holds for a
given `x` is a property of the HOST LIBNM's `pow` implementation: a
correctly-rounded `pow(x, 2.0)` is bit-identical to `x * x`, so on libms
with an exact `pow` the two agree everywhere and on log/exp-based `pow`
they differ in the last ulp for ~0.08 % of floats.  The pinned constants
(`974.5535622665931`, `66.24771326355554`, `2.882033520478047`) do NOT
discriminate on the current libm — the assertions failed, while the
kernel (which resolves the SAME host libm via `dlsym`) still matches the
oracle.  Confirmed: the current libm CAN discriminate (~0.08 % rate),
so the pins were not vacuous-by-construction, just stale.

**Fix.** Each of the three tests now SEARCHES for a discriminating input
on the loaded libm at runtime (deterministic LCG seed, bounded
iterations, `assert found` fails loudly if the libm cannot discriminate
at all), then verifies the kernel matches the oracle on the found input
bit-exactly.  This is strictly more robust than the hardcoded constants:
the search adapts to whatever libm is loaded.  The copper-coverage test
was also made orientation-independent (`oracle_bit == (d2 < p)` and
`oracle_bit != (d2 < m)` rather than a pinned inside/outside direction).

**Same root cause in the crate's own unit tests.** `cargo test -p
temper-thermal` surfaced THREE more pre-existing failures of the identical
class — `hostmath::pow_is_not_multiplication`,
`geometric_metrics::pow_used_not_multiplication_in_hypot`, and
`thermal_potential::separation_test_uses_pow_not_multiplication` — each
hardcoding the same libm-specific discriminators (the `974.5535622665931`
value recurs in hostmath).  Fixed the same way (runtime search over the
crate's own `hostmath::pow` dlsym route).  Note these unit tests cannot
use `f64::powf` for the search: LLVM folds a direct `pow(x, 2.0)` libcall
to `x * x` in optimized code (probe-verified), which is exactly why
`hostmath` exists and why the search must go through the dlsym indirection.

## Verify (on a clean release rebuild)

- `cargo test -p temper-thermal` — 188 passed; clippy clean.
- `tests/physics/` — 1028 passed in the post-fix full run.
- `tests/validation/test_thermal_scorer*.py` — 47 passed.
- `import_linter_gate.py` and `make regen-check` — green.

## Discovered, pre-existing, OUT of scope: flaky `test_p6_anchors_are_unique`

While re-running the full `tests/physics/` dir, hypothesis falsified
`test_thermal_potential_rust_pbt.py::test_p6_anchors_are_unique`:
`board=(0, 0, 40, 21)`, `devices=[('Q0',0.0),('Q1',0.0),('Q2',1.0),
('Q3',0.0),('Q4',1.0)]` puts Q0 and Q3 BOTH at `(40.0, 21.0)` — the
top-right corner.  `assign_thermal_anchors` nudges colliding devices by
`offset_mm` toward `+x` and clamps at `x_max`; when two devices are both
pushed into the same corner the clamp makes them coincide, violating R13
("no two anchors within 0.1 mm").  Verified **not** introduced by this
change: calling `assign_thermal_anchors` with the identical input on a
pristine `main` build (325e4458, no #927 changes) returns the byte-identical
coincident anchors.  The PBT is flaky run-to-run (hypothesis randomness:
the first post-fix full run passed it, the second found the counterexample,
which the per-worktree `.hypothesis` DB then replays deterministically).
Left as a separate follow-up — it is a real pre-existing R13 violation in
`thermal_potential`, unrelated to the #927 pow/NaN differentials.
