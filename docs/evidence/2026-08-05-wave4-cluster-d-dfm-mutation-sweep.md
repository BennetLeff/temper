# Wave 4 cluster D — router_v6 post-route DFM slice: anti-vacuity mutation sweep — 2026-08-05

<!-- provenance: commit=1e71b613cd110849e3861f2a7d754671c66b15a3 dirty=true -->

**Base commit:** `1e71b613c` (the Phase A TDD-RED commit: pinned oracle,
shared corpus, RED differential, PBT) plus the working-tree Phase B change
(the `temper_drc_rs` DFM kernels). `dirty=true` because this document lands
in the same commit as the migration it verifies.

## Why this sweep exists

The R1 gate set requires anti-vacuity evidence for every migration: mutate
the Rust, confirm the gate **fails**, revert, and record every mutation and
what caught it. A differential never shown to fail is not evidence — the
failure mode this exists to catch is the Phase A suite on this program that
passed 53/53 on its first run while 0 of 600 generated boards reached the
code its properties described.

Phase A's own `test_pN_fails_for_*` tests already prove each *property* is
non-vacuous against a degenerate Python kernel. This sweep is the other
half: it mutates the **compiled Rust** and confirms the gates go red.

## Method

For each mutant: apply a single behaviour-changing edit to
`packages/temper-drc-rs/src/dfm.rs` or `src/pymath.rs`, rebuild the
extension (`maturin develop --release`), run

* the Python gates — `test_dfm_rust_differential.py` + `test_dfm_pbt.py`
  (531 tests), and
* the in-crate kernel tests — `cargo test --no-default-features` (101
  tests; `--no-default-features` because the crate's `cdylib` +
  `extension-module` build cannot link a test binary),

record the result, restore the file, and rebuild. The differential compares
by type-carrying signature (`float.hex()` per float, concrete type name per
non-float leaf) with **no tolerance**, and captures raised exceptions as
values so error type *and* message are part of the comparison.

## Results — 32 mutants: 29 killed, 3 equivalent

`KILLED-differential` = the Python differential/PBT went red.
`KILLED-cargo` = the differential stayed green and an in-crate kernel test
caught it (these are the behaviours the pinned corpus does not reach).

| # | module | mutation | caught by |
|---|---|---|---|
| M01 | thermal_relief | `is_power_net`: drop the `[A-Z]*GND` alternative | differential (2) |
| M02 | thermal_relief | `connects_to_power_plane`: layer test `\|\|` → `&&` | differential (4) |
| M03 | thermal_relief | `generate_spoke_segments`: spoke length `max` → `min` | differential (4) |
| M04 | thermal_relief | `generate_spoke_segments`: move the divide first (B7) | differential (2) |
| M05 | thermal_relief | `generate_spoke_segments`: `py_hypot` → `f64::hypot` (B4) | differential (1) |
| M06 | thermal_relief | `pymath::cos/sin` → `f64::cos/sin` (B1) | **equivalent — see below** |
| M07 | thermal_relief | `clamp_to_rect_outline`: swap the min/max nesting (B5) | differential (6) |
| M08 | thermal_relief | `clamp_to_rect_outline`: drop the non-finite-dim guard | cargo (new test) |
| M09 | acid_trap_detection | `calculate_angle`: `x ** 2` → `x * x` (B7) | differential (3) |
| M10 | acid_trap_detection | `calculate_angle`: sqrt-of-pow → `py_hypot` (B4/B6) | differential (5) |
| M11 | acid_trap_detection | `calculate_angle`: drop `round(deg, 9)` (B3) | differential (10) |
| M12 | acid_trap_detection | `calculate_angle`: min-then-max → max-then-min (B5) | differential (9) |
| M13 | acid_trap_detection | `degrees`: `x * k` → `(x * 180) / pi` (B1/B7) | cargo |
| M14 | acid_trap_detection | `classify_severity`: `< 45` → `<= 45` | differential (1) |
| M15 | acid_trap_detection | `classify_severity`: `< 0.2` → `<= 0.2` | differential (7) |
| M16 | power_plane | `power_pour_bounds`: distribute the multiply (B7) | differential (2) |
| M17 | power_plane | `thermal_via_positions`: `c ** 0.5` → `sqrt(c)` (B7) | **equivalent — see below** |
| M18 | power_plane | `py_round_to_int`: half-even → half-away (B3) | cargo |
| M19 | power_plane | `board_bounds`: widen `int` results to `f64` | differential (1) |
| M20 | power_plane | `power_pour_bounds`: gap check before the empty-domain return | cargo |
| M21 | copper_balance | `via_annular_area`: `r * r` → `r ** 2` | differential (1) |
| M22 | copper_balance | `segment_run_copper_area`: sum then multiply once (B7) | differential (4) |
| M23 | copper_balance | `layer_is_between`: strict → inclusive | differential (3) |
| M24 | via_placement | `via_segment_index`: first-match → last-match | differential (2) |
| M25 | via_placement | `adjacent_layer`: `B.Cu → In1.Cu` | differential (1) |
| M26 | annular_ring_check | `check_annular_ring`: `<=` → `<` | cargo (new test) |
| M27 | annular_ring_check | internal layers no longer halve the threshold | differential (5) |
| M28 | annular_ring_check | microvia override becomes a `min`, not a replacement | cargo (new test) |
| M29 | teardrop_generation | argmin keeps the LAST minimum on a tie | differential (1) |
| M30 | teardrop_generation | `py_min` → `f64::min` for the width (B5) | **equivalent — see below** |
| M31 | teardrop_generation | direction epsilon `1e-9` → `1e-12` | differential (1) |
| M32 | teardrop_generation | size gate `>=` → `>` | differential (1) |

Every one of the seven modules is represented, and every divergence class
the oracle header names (B1, B3, B4, B5, B6, B7) has at least one mutant.

### Six survivors closed by new discriminating tests

The first pass left **nine** survivors. Six were genuine gaps in the
corpus, closed by adding a discriminating in-crate test — never by
weakening a claim. Each is a behaviour the pinned corpus cannot reach:

* **M08** — every non-finite-dimension row in `RECT_CLAMPS` uses a point
  *inside* the board, for which deleting the guard is a no-op (a NaN
  `x_max` makes `min(x, NaN)` return `x`, and `max(x_min, x)` returns `x`
  again). The guard only becomes observable for a point *outside* the
  origin. → `clamp_to_rect_outline_nonfinite_guard_is_load_bearing`.
* **M13** — `round(deg, 9)` absorbs the reassociation for every input the
  corpus reaches; the PR body's own M2 complement measured the same effect
  (a 1.1x scale perturbs the unrounded value for >50% of triples and
  `round` absorbs 5000/5000). The existing pymath test asserts the
  association directly, so it kills the mutant in `cargo test`.
* **M18** — killed by the existing `round(2.5) == 2` pin in
  `round_is_decimal_not_scaled`.
* **M20** — `POUR_CASES` has no `n == 0` row, so the ordering of the
  empty-domain return against the gap check is unreachable from the
  corpus. Killed by the existing `power_pour_bounds_partitions_and_raises`.
* **M26** — `<=` vs `<` is observable only when the ring lands *exactly*
  on `threshold + 1e-12`. Constructed: `min_ring = 0.0`, `drill = 2e-12`,
  `diameter = 4e-12`, so `(4e-12 - 2e-12) / 2` is exactly `1e-12` (the
  operands share an exponent, so the subtraction is exact).
* **M28** — every microvia row in the corpus has
  `microvia_ring <= the layer threshold`, where "replace" and "take the
  smaller" agree. Separated with `min_ring = 0.01` against
  `microvia_ring = 0.025`, where the microvia threshold is the *looser* of
  the pair.

### Three equivalent mutants, with the evidence

Each carries a test that **fails if the equivalence ever stops holding**,
so the disposition is checked rather than asserted.

* **M06 — `pymath::cos/sin` → `f64::cos/sin`.** Equivalent on this host:
  after the `RTLD_DEFAULT` fix (below), `dlsym` resolves to the same
  libSystem the extension statically references, so the two spellings are
  the same function *here*. It says nothing about CI, whose
  `uv`-standalone interpreter ships its own libm — the divergence
  `temper-geometry` measured and the reason the indirection exists. What
  is falsifiable, and now asserted, is that the indirection is actually
  wired: `pymath::tests::host_libm_symbols_actually_resolve`.
* **M17 — `c ** 0.5` → `sqrt(c)`.** Equivalent at this call site, measured
  over `c` in `[0, 2_000_000]` in CPython and `[0, 300_000]` in-crate:
  the two disagree for 2550 integers, `round()` of the two agree for
  **all** of them, and the perfect-square verdict never differs. `pow` is
  kept because it is what the reference evaluates. Pinned by
  `thermal_via_side_round_absorbs_the_pow_vs_sqrt_divergence`, which fails
  if the absorption stops.
* **M30 — `py_min` → `f64::min` for the teardrop width.** Provably
  equivalent: the two differ only on NaN and on a signed-zero tie, and the
  kernel's guard chain makes both unreachable — a NaN/`+inf` trace width
  returns `None` before the min, the diameter is guarded finite and `> 0`,
  and a signed-zero tie needs both operands zero, which needs
  `diameter == 0`. Pinned by `via_teardrop_width_min_can_never_see_a_nan`.

## Finding: `RTLD_DEFAULT` is not `NULL` on Darwin

Found while closing M06, and it is **not** confined to this slice.

Three crates resolve the host interpreter's libm through
`dlsym(RTLD_DEFAULT, ...)` so their bit-exactness does not depend on which
libm the extension happens to statically link:

* `packages/temper-geometry/src/pad_geometry.rs` (`cos`, `sin`)
* `packages/temper-thermal/src/hostmath.rs` (`exp`, `log`, `log10`, `cos`,
  `sin`, `pow`)
* `packages/temper-drc-rs/src/validation.rs` (`pow`) — now
  `src/pymath.rs`

All three spell the handle `const RTLD_DEFAULT: *const u8 = core::ptr::null();`.
That is glibc's value. Darwin's `dlfcn.h` defines
`#define RTLD_DEFAULT ((void *) -2)`, and a null handle simply misses.
Measured on this host (`darwin/arm64`, a standalone probe):

```
"cos"    null-handle -> None   (-2)-handle -> Some(0x19677dad4)
"sin"    null-handle -> None   (-2)-handle -> Some(0x19677d968)
"acos"   null-handle -> None   (-2)-handle -> Some(0x196783e18)
"pow"    null-handle -> None   (-2)-handle -> Some(0x196782000)
"printf" null-handle -> None   (-2)-handle -> Some(0x18689097c)
```

So on macOS every one of those lookups has been returning `None` and
falling through to the statically-bound `f64::*` fallback — silently, and
with no test able to notice, because the fallback is a *plausible* answer
and merely not the host interpreter's. It works on Linux, which is why CI
never surfaced it.

`src/pymath.rs` now selects the handle per platform and
`host_libm_symbols_actually_resolve` asserts the resolution succeeds.
**`temper-geometry` and `temper-thermal` are left untouched** — they carry
their own differentials and belong to other slices — but they have the
same latent condition and should be fixed in their own PRs. Note the fix is
expected to be behaviour-preserving on macOS (`fallback_pow` calls
`f64::powf` with a runtime exponent, which lowers to the same libSystem
`pow`); the value of fixing it is that the *uv-standalone* case the
indirection was written for actually works.

## Reproduction

The sweep harness is not committed: it is a throwaway that rewrites crate
sources in place, and a committed copy would be a footgun. Each mutation
is a single exact string replacement, listed in the table above; applying
one, running `maturin develop --release` and then the two suites
reproduces the row.
