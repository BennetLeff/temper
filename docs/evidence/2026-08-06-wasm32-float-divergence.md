<!-- provenance: commit=d5f4593142da87c75f9b21734e0e65d0e991f16d dirty=UNKNOWN -->

# wasm32 `pow` divergence: measured, and whether it can flip a DRC verdict

**Date:** 2026-08-06
**Base:** `origin/main` @ `d5f4593142da87c75f9b21734e0e65d0e991f16d`
**Scope:** `packages/temper-drc-rs` (the only crate with a wasm32 test harness)
**Environment:** darwin/arm64 (macOS 26.5.1, Darwin 25.5.0), `rustc 1.92.0`,
`wasm32-unknown-unknown`, executed under Node v26.4.0's built-in
`WebAssembly` (V8 — the engine `workerd` embeds; neither `wrangler` nor
`workerd` is installed in this environment, and this substitution is the one
the task explicitly sanctions). **The Linux CI container was not reached.**
Docker's CLI is present but its daemon is not running, and starting it
was judged out of scope for a disk-constrained, multi-agent shared machine —
this is stated rather than estimated, per the task's rules.

## tl;dr

- PR #800's claim re-measured and **confirmed, but exponent-specific, not
  general**: on the real wasm32 build, `pow(x, 2.0) == x*x` and
  `pow(c, 0.5) == sqrt(c)` for every sample tested (zero divergence over
  ~300k combined samples). `pow(x, 3.0)` is **not** folded — wasm32's
  `powf(x, 3.0)` disagrees with `x*x*x` about as often as native's real
  libm `pow(x, 3.0)` does, which means the mechanism that makes exponent
  2.0/0.5 "safe" (constant folding to a deterministic, IEEE-exact op)
  does not generalize to other exponents.
- **No DRC verdict flip found.** A 20,000-sample boundary-hugging search
  against the one pow-consuming, wasm-eligible decision surface
  (`dfm.rs`'s acid-trap severity classifier, whose 45°/60° bands are
  explicitly documented as pow/round-sensitive) found zero native-vs-wasm32
  disagreements, down to 1e-12° offsets from the boundary.
- **Overflow parity holds at the tested magnitude and across the real
  boundary**, for exponent 2.0: native raises `OverflowError` at `1e200`,
  and so does the real wasm32 build. Swept 1,000,000 ULPs around the actual
  overflow threshold (`sqrt(f64::MAX)`) natively and found zero
  disagreements between "real pow overflows" and "`x*x` overflows" — the
  two computations happen to cross into `inf` at the same threshold.
- **The real pass/fail DRC checks that use `pow` (`validation.rs`'s
  `tht_hole_collisions`, `trace_length`) are not compiled into the wasm32
  build at all** — they are `#[cfg(feature = "python")]`-gated, and the
  wasm-test-runner builds with that feature off. So the highest-value B7
  call sites are currently *absent* from the wasm tier, not verified safe.
- **The wasm tier does not currently build on `origin/main`.** A commit
  titled "DO NOT MERGE" landed anyway and reintroduced a feature-gating bug
  that makes `wasm_test_registry` unreachable under the documented build
  command. Found and worked around locally (not committed) to get real
  numbers; see [Finding: the tier is currently broken](#finding-the-wasm-tier-does-not-currently-build).

**Recommendation: safe only for a named subset — advisory-only for
everything else.** See [Recommendation](#recommendation).

---

## 1. The mechanism, read from source

`packages/temper-drc-rs/src/pymath.rs` resolves `cos`/`sin`/`acos`/`pow`
via `dlsym(RTLD_DEFAULT, ...)` on native targets, to track *the host
CPython interpreter's* libm bit-for-bit (`pymath::pow`, lines 155–169).
`wasm32-unknown-unknown` has no dynamic loader — declaring `dlsym` there
would emit an `env.dlsym` import, which makes the module unable to
instantiate in a bare isolate — so `dlsym_ptr` is `cfg`'d to always return
`None` on wasm32 (lines 99–102), and every call falls through to the
statically-bound fallback: `f64::powf`, `f64::cos`, `f64::sin`, `f64::acos`.

For a **constant** exponent, LLVM's `SimplifyLibCalls` rewrites
`llvm.pow.f64(x, 2.0)` to `x*x` and `llvm.pow.f64(x, 0.5)` to `sqrt(x)`,
on any target, including native — which is exactly *why* the dlsym
indirection exists at all (`f64::powf` is not an acceptable proxy on
either platform for those two exponents). On native, the dlsym path avoids
the fold by never calling `f64::powf` with a literal exponent. On wasm32,
there is no dlsym path, so the fallback *is* `f64::powf(x, 2.0)`, and the
fold applies. That is the entire mechanism behind PR #800's claim — read
from source before any measurement.

## 2. Native distributions (re-measured, not assumed)

All corpora below are freshly generated (fixed-seed xorshift64, same
formula as `pymath.rs`'s own pinned test, so this is a direct
re-measurement of the number already in the crate's docstrings — plus the
ULP data those docstrings don't carry). Command:
`cargo run --release --no-default-features --example pow_census_native`
(scratch file, not committed — see [Reproducing](#reproducing-these-numbers)).

| Comparison | Corpus | n | differ | rate | ULP (all differing cases) |
|---|---|---|---|---|---|
| `pow(x,2.0)` vs `x*x` | x ∈ [-100,100) uniform | 200,000 | 247 | 0.1235% | exactly 1 |
| `pow(x,3.0)` vs `x*x*x` | x ∈ [-100,100) uniform | 200,000 | 52,679 | 26.34% | exactly 1 |
| `pow(c,0.5)` vs `sqrt(c)` | c = 1..100,000 (int) | 99,999 | 137 | 0.137% | exactly 1 |
| `pow(x,0.5)` vs `sqrt(x)` | x ∈ [0,100000) uniform | 200,000 | 254 | 0.127% | exactly 1 |
| `cos`: dlsym-libm vs `f64::cos` | x ∈ [-π,π) uniform | 200,000 | 0 | 0% | n/a |
| `sin`: dlsym-libm vs `f64::sin` | x ∈ [-π,π) uniform | 200,000 | 0 | 0% | n/a |

Every disagreement measured is exactly 1 ULP — this platform's system
libm and the constant-folded op never disagree by more than the last bit.
`cos`/`sin` show **zero** divergence natively because `dlsym` resolves to
the same libm `f64::cos`/`f64::sin` already call on this host (confirmed
directly, not inferred — matches the crate's own note that mutant M06,
`pymath::cos/sin → f64::cos/sin`, is equivalent on this host). This says
nothing about CI's `uv`-standalone interpreter, which the crate's own
comments say ships its own libm; that comparison needs the Linux
container, which was not reachable here (see header).

Overflow, native:

```
py_pow(1e200, 2.0)  = Err(PowOverflow)   -- raises, matches CPython
1e200 * 1e200       = inf                -- plain multiply saturates silently
```

Overflow boundary sweep (native, 1,000,000 ULPs stepped directly around
`sqrt(f64::MAX) ≈ 1.3407807929942596e154`, comparing "does real `pow(x,2.0)`
overflow" against "does `x*x` overflow" — which is what wasm32 actually
computes, since §3 shows the wasm32 fold is exact):

```
swept 1,000,000 ULPs, disagreements = 0
```

Also checked the two near-miss cases the crate's own docstring calls out:
`py_pow(1e-160, 2.0) = Ok(1e-320)` (subnormal, no raise) and
`py_pow(1e-200, 2.0) = Ok(0.0)` (underflow, no raise) — both match
`1e-160*1e-160` / `1e-200*1e-200` exactly, so the underflow side of the
`ERANGE` logic is not a live divergence at exponent 2.0 either.

## 3. wasm32 distributions — from an actual wasm32 build, run under Node/V8

Not simulated: `packages/temper-wasm-test-runner` built for
`wasm32-unknown-unknown` and executed via `tools/wasm/run_wasm_tests.mjs`,
the repo's own Node-built-ins host driver (V8, same engine as `workerd`).

The crate's own pinned test `pymath::tests::pow_is_not_a_multiply_or_a_sqrt`
asserts `pow(x,2.0)` and `pow(c,0.5)` differ from `x*x`/`sqrt(c)` at least
once across 200,000 + 99,999 samples. On the real wasm32 build **this
assertion fails**, and it is listed as an *expected* failure
(`tools/wasm/wasm_expected_failures.json`, class `b7-pow-divergence-absent`)
precisely because the failure means the divergence count was **exactly
zero** — i.e. `pow(x,2.0) == x*x` and `pow(c,0.5) == sqrt(c)` for literally
every one of those ~300k samples, on the real build. That is a direct,
executed re-measurement of PR #800's headline claim, not a repetition of it.

**Exponent 3.0 does not fold.** No existing test covered it, so a scratch
probe (`scratch_pow3_overflow_probe`, same seed/formula as the native
corpus above) was added temporarily and run on the real wasm32 build:

```
POW3_DIFFERS: 55500/200000  (27.75%)
```

Compare to native's 52,679/200,000 (26.34%) for the identical `x` values
computed with the *native* real `pow(x,3.0)`. These are two different
numbers from two different mechanisms computing the same nominal
operation — not the "exactly 0" signature exponent 2.0 and 0.5 show. **wasm32's
`pow(x, 3.0)` is not constant-folded to `x*x*x`**; it runs Rust's own
(non-system) `powf` implementation for `wasm32-unknown-unknown`, which is
a *third*, independently-diverging algorithm, not a repeated multiply.
**PR #800's claim does not generalize past the two exponents LLVM actually
folds (2.0, 0.5).** Any future `pow(x, 3.0)`-or-other-exponent call site
would need its own measurement — the "inert on wasm" property is a
property of the fold, not of `pow` in general.

Overflow, same scratch probe, real wasm32 build:

```
OVERFLOW_1E200_2: Err(PowOverflow)   -- SAME as native
MUL_1E200:        inf
```

wasm32's `py_pow(1e200, 2.0)` raises, exactly like native. This is not
because wasm32's pow algorithm matches CPython's at this magnitude — it is
because `py_pow`'s overflow check (`x.is_finite() && y.is_finite() &&
r.is_infinite()`) fires whenever the *result* saturates to `inf`,
regardless of which algorithm produced it, and §2's 1,000,000-ULP sweep
already shows `x*x` (= wasm32's exact computation, per the fold) crosses
into `inf` at the same threshold as real `pow`. The overflow-raising
*behavior* survives the B7 divergence at exponent 2.0 as a structural
consequence of the fold, not a coincidence limited to `1e200` specifically.

## 4. Does it flip a verdict? — the decisive question

**Search target:** `packages/temper-drc-rs/src/dfm.rs`'s
`calculate_angle` → `classify_severity` (acid-trap detection). This is the
only `pow`-consuming decision in the wasm-eligible registry that compares
a computed value against a fixed threshold (45.0°, 60.0°) rather than just
pinning a raw numeric value — i.e. the only place a 1-ULP-scale B7
divergence could plausibly flip a categorical output. The module's own
docstring already documents the load-bearing case: "the exact 60-degree
vertex is `59.99999999999999` before the round and `60.0` after, which
flips the severity band" (dfm.rs:58-60), and a pinned test
(`calculate_angle_pins_the_60_degree_boundary`, dfm/tests.rs:189-200)
encodes that exact case.

**Method.** 20,000 deterministic triangles (fixed-seed xorshift64,
identical generator duplicated verbatim on both sides so both walk the
same sequence), split evenly between the 45.0° and 60.0° boundaries, at
five offset scales (±1e-1, 1e-3, 1e-6, 1e-9, 1e-12 degrees from the exact
boundary), each with a randomized overall rotation and randomized arm
lengths (0.01mm–1000mm, to vary magnitude/rounding behavior). Trace width
held at 1.0mm to isolate the angle-boundary path from the separate
0.2mm width-demotion branch. Computed `calculate_angle` +
`classify_severity` for the whole corpus:

- **Natively** (real dlsym `pow`/`acos`): `cargo run --release
  --no-default-features --example verdict_flip_search`, one severity
  letter (`H`/`M`/`L`) per row.
- **On the real wasm32 build** (fallback `pow`/`acos`, i.e. exactly the
  code path a Worker would run): a temporary test
  (`scratch_verdict_flip_probe`) computing the identical corpus and
  reporting all 20,000 severities via its panic message.

**Result:**

```
native len: 20000  wasm len: 20000
num diffs: 0
```

**Zero mismatches**, including at the 1e-12° offset scale — well inside
the region where the B7 1-ULP noise from `pow(v,2.0)` inside
`mag1`/`mag2` could plausibly matter, and where the wasm32 `acos` fallback
(a different libm implementation than native's dlsym'd one — a *separate*,
B1-class divergence that compounds with B7 in this exact function) is also
live. The crate's own pinned 60°-boundary test additionally passed
unmodified on the real wasm32 build (confirmed in the full registry run,
§5). `round(.., 9)` quantizes to ~1e-9 degrees, several orders of
magnitude coarser than the ~1e-15-relative noise `pow`/`acos` divergence
introduces, which is the likely reason no flip surfaces even under
deliberate boundary pressure — but this is an empirical result from a
finite corpus, not a proof that no input flips it. See
[Recommendation](#recommendation) for what would close that gap.

**What was *not* searched:** the real pass/fail DRC checks
(`tht_hole_collisions`, `trace_length` in `validation.rs`) compare a raw
`pow`-derived distance directly against a threshold with **no** rounding
or banding step in between (`if dist < required`) — structurally a much
easier case to flip than `calculate_angle`'s round-then-classify pipeline.
They could not be searched because they are not compiled into the wasm32
build at all (§6). This is the single biggest gap in this investigation
and the reason the recommendation below is a *subset*, not a blanket
clearance.

## 5. Structural census — which decisions even touch `pow`

Grepped every DRC-rule and DFM source file for `pow(`/`py_pow`/`.sqrt(`/
`hypot`, then checked each site's role:

| File | Site | Uses `pymath::pow`? | Feeds a threshold decision? | wasm-eligible? |
|---|---|---|---|---|
| `rules/drc/via_spacing.rs` | `dx*dx+dy*dy >= t*t` | No — plain multiply by construction, decision comment explains the identity avoids sqrt entirely | Yes (`DRC_VIA_001`) | Yes |
| `rules/drc/clearance.rs` | `dx.hypot(dy)` (bbox prefilter), `a.edge_distance_to(b)` (`geo` crate polygon distance) | No — `f64::hypot` / `geo`'s own sqrt-of-squares, not routed through `pymath` at all | Yes (`DRC_CLR_001`) | Yes |
| `validation.rs` | `(host_math::pow(dx,2.0)+host_math::pow(dy,2.0)).sqrt()` | **Yes** | **Yes** — `tht_hole_collisions`, `trace_length` | **No — `#[cfg(feature = "python")]`, not compiled for wasm32** |
| `dfm.rs::calculate_angle` | `pymath::py_pow(v, 2.0)` inside `sq()` | **Yes** | Yes, via `classify_severity`'s 45°/60° bands | Yes |
| `dfm.rs::thermal_via_positions` | `pymath::pow(count, 0.5)` for perfect-square side | **Yes** | Yes — `NotAPerfectSquare` classification | Yes |
| `dfm.rs::via_annular_area` | `r * r` | No — explicitly avoids `pow` (own pinned test: `via_annular_area_uses_r_times_r_not_pow`) | Yes | Yes |
| `packages/temper-geometry/src/escape_via.rs` | `pow_operator` → `host_math::pow(dx,2.0)+...).sqrt()` | Yes (same pattern) | Yes | **No wasm harness exists for `temper-geometry` at all** — no `wasm_test_registry.rs`, no `WASM_TESTS`, nothing. Out of scope of "the wasm tier" as it exists today. |

**`via_spacing.rs` is immune by construction**, on any platform: its
decision never calls `pow` or `sqrt` — the squared-space comparison
`dx*dx+dy*dy >= t*t` is algebraically equivalent to the sqrt-based test
and sidesteps the whole divergence class. This is not a wasm-specific
property; it would hold even against a hostile libm.

**`clearance.rs`'s real decision (`edge_distance_to`) never goes through
`pymath::pow` either** — it's the third-party `geo` crate's own distance
implementation. `sqrt` itself is IEEE-754 correctly-rounded on essentially
every real target including wasm32's `f64.sqrt` instruction, so it should
not diverge cross-platform the way `pow` does; `hypot` is not
correctly-rounded and could, but that is a `geo`-crate/std-library
question, not the B7 class this investigation was scoped to, and it was
not measured here.

**The real DRC pass/fail checks that use `pymath::pow` directly
(`tht_hole_collisions`, `trace_length`) are entirely absent from the
wasm32 build.** `packages/temper-wasm-test-runner/Cargo.toml` depends on
`temper-drc-rs` with `default-features = false, features =
["wasm-test-registry"]` — `python` is off, and `validation.rs` is
`#[cfg(feature = "python")]`. Confirmed by attempting the reverse
(`--features python,wasm-test-registry --target wasm32-unknown-unknown`):
it fails outright, because `pyo3`'s `extension-module` feature cannot
cross-compile to wasm32 (`PYO3_CROSS_PYTHON_VERSION or ... must be
specified when cross-compiling`). There is no configuration that puts
`validation.rs` in a wasm32 build today. This means the B7 divergence in
the crate's actual raw-comparison pass/fail checks was **not measurable**
in this investigation — not because it's safe, but because the code isn't
there to test.

## 6. Test census — of 94 wasm-eligible tests, how many touch `pow`/`sqrt`

The real wasm32 build registers and runs 94 tests today (measured:
`registered: 94, executed: 94` from the actual run). Parsed every test
body (and, transitively, every production function it calls) for
`pow`/`py_pow`/`.sqrt(`/`hypot`:

| Category | Count | Tests |
|---|---|---|
| **Directly assert something about the pow/sqrt/hypot divergence itself** | 5 | `pymath::tests::pow_is_not_a_multiply_or_a_sqrt`, `pymath::tests::hypot_pinned_values`, `dfm::tests::via_annular_area_uses_r_times_r_not_pow`, `dfm::tests::thermal_via_side_round_absorbs_the_pow_vs_sqrt_divergence`, `dfm::tests::calculate_angle_magnitude_is_sqrt_of_pow_not_hypot` |
| **Transitively exercise a `pow`-touching function, without asserting on the divergence** | 4 | `dfm::tests::calculate_angle_pins_the_60_degree_boundary`, `dfm::tests::calculate_angle_cardinal_values`, `dfm::tests::calculate_angle_degenerate_and_nan_arms`, `dfm::tests::thermal_via_positions_perfect_square_and_complex_arms` |
| **Tests the dlsym resolution mechanism itself (`pow`/`cos`/`sin`/`acos` symbols)** | 1 | `pymath::tests::host_libm_symbols_actually_resolve` |
| Touch neither | 84 | — |

**11/94 (11.7%)** of the wasm-eligible corpus touches a `pow`/`sqrt`/
`hypot` code path in some way. Of those:

- **3** are correctly marked expected-to-fail on wasm32 today
  (`pow_is_not_a_multiply_or_a_sqrt`, `via_annular_area_uses_r_times_r_not_pow`,
  `thermal_via_side_round_absorbs_the_pow_vs_sqrt_divergence`) — their
  failure *is* the intended signal (the divergence they assert exists is
  provably absent on wasm32), so a green run of them would be the actual
  bug, not the red.
- **1** (`host_libm_symbols_actually_resolve`) is also expected-to-fail,
  for the adjacent "no dynamic loader" reason.
- The remaining **7** currently pass on wasm32 and would still catch a
  gross regression (wrong sign, wrong branch, NaN where a number is
  expected) — but per §4, they can no longer discriminate the specific
  1-ULP B7 divergence, because that divergence does not flip their pinned
  outputs on this platform.
- **`hypot_pinned_values` is not a pow test at all** (B4 class — CPython's
  `math.hypot` vs `f64::hypot`); it was swept into the census because it
  shares the "floating-point-identity" family, not because it's B7.

**Zero of the crate's real pass/fail DRC checks (`DRC_VIA_001`,
`DRC_CLR_001`, and — per §5 — `tht_hole_collisions`/`trace_length`'s
would-be `DRC` equivalents) are wasm-eligible pow-consumers**, because
`via_spacing`/`clearance` structurally avoid `pow`, and
`validation.rs`'s pow-based checks aren't compiled for wasm32 at all.
The wasm tier's *only* pow-consuming, board-level decision is the DFM
severity classifier tested in §4.

## 7. Finding: the wasm tier does not currently build

`packages/temper-drc-rs/src/lib.rs` (current, lines 41-43):

```rust
#[cfg(feature = "python")]
#[cfg(feature = "wasm-test-registry")]
pub mod wasm_test_registry;
```

Both `cfg`s must be true simultaneously for the module (and therefore the
whole test registry it exposes) to exist. `packages/temper-wasm-test-runner
/Cargo.toml` depends on `temper-drc-rs` with `default-features = false,
features = ["wasm-test-registry"]` — `python` is never on. There is no way
to satisfy both: enabling `python` for a `wasm32-unknown-unknown` cross
build fails outright (`pyo3-ffi`'s build script: "PYO3_CROSS_PYTHON_VERSION
or ... must be specified when cross-compiling", verified directly).

`git blame` traces the erroneous `#[cfg(feature = "python")]` line to
commit `13aee32b7` — **"test(wave4): Phase A for cluster E + net_ordering +
escape_via — pinned oracles, RED differentials, PBTs (DO NOT MERGE) (#751)"**
— which landed on `origin/main` despite its own title. PR #800's own commits
(`2259f8598`, `97dd0fc13`) had the gate correct
(`#[cfg(feature = "wasm-test-registry")]` alone); `13aee32b7` reintroduced
the stray `python` gate on top, breaking the documented build command
(`docs/plans/2026-08-05-001-feat-wasm-tier-phase0-plan.md` lines 255, 567)
for every commit since.

**Practical effect on this investigation:** none of PR #800's "headline
numbers" it never got to report, and nothing in
`tools/wasm/wasm_expected_failures.json`, could have been produced by
actually running the documented build command against current `main` —
that command does not compile. All real-wasm32 numbers in this document
were produced after locally removing the stray `#[cfg(feature = "python")]`
line (uncommitted — this is a docs-only investigation branch, not the
place to land a production fix). **Anyone re-running this investigation
from a fresh checkout of `main` needs to apply that same one-line revert
first**, or the build fails before any measurement is possible.

## Recommendation

**Safe only for a named subset.**

- **Safe today:** `dfm.rs`'s `calculate_angle`/`classify_severity` (the
  acid-trap DFM severity classifier) and `thermal_via_positions`'s
  perfect-square check — the only wasm-eligible, `pow`-consuming decision
  surfaces, and the only ones this investigation could actually search.
  20,000 boundary-focused samples down to 1e-12° from the documented
  load-bearing threshold produced zero native-vs-wasm32 disagreements, and
  the crate's own pinned regression case for this exact boundary passes
  unmodified on the real wasm32 build.
- **Structurally safe on any platform, not just wasm32:**
  `via_spacing.rs`'s `DRC_VIA_001` check — it never calls `pow` or `sqrt`
  in its decision path by construction.
- **Not yet assessed — excluded, not cleared:** `validation.rs`'s
  `tht_hole_collisions` and `trace_length`, and by extension anything
  behind `#[cfg(feature = "python")]`, and all of `temper-geometry`
  (`escape_via.rs`'s `pow_operator` and friends). These are the call sites
  where a 1-ULP `pow` divergence is most dangerous — a raw `dist <
  required` comparison with no rounding/classification buffer in
  between — and they are precisely the ones with **no wasm32 build path
  today**, so they could not be searched. Do not infer safety for them
  from §4's result; the risk profile is structurally different (no
  quantization step to absorb 1-ULP noise).
- **Exponent-specific, not general:** the "wasm `pow` == multiply"
  property that makes exponent 2.0/0.5 tractable is an LLVM constant-fold
  artifact. Exponent 3.0 does not fold and was measured to diverge from
  `x*x*x` at a similar but not identical rate to native (§3) — any future
  `pow` call site at an exponent other than 2.0/0.5 needs its own
  measurement before being trusted on wasm32; nothing here generalizes
  to it.

**Cost to make the tier trustworthy if the excluded subset ever needs to
move onto it:**

1. **Prerequisite, independent of the pow question:** fix the one-line
   `#[cfg(feature = "python")]` regression (§7) — the tier does not build
   on `main` today, so none of this is currently reachable by CI at all,
   regardless of what this document concludes.
2. **To extend coverage to `validation.rs`'s real pass/fail checks:** they
   would need the same restructuring `dfm.rs` already has — pure,
   feature-independent compute kernels reachable without `pyo3` — before
   they could even be *registered* for wasm32, let alone measured. That is
   real migration work, out of scope here.
3. **To close the "empirical, not proven" gap for the surfaces already
   measured safe:** either (a) keep the wasm arm strictly advisory
   (non-blocking on CI/merge) until a formal error-bound analysis replaces
   the corpus search with a proof, for every `pow`/`sqrt` call site that
   feeds a *raw* (non-rounded, non-classified) threshold comparison — the
   ones this investigation could not even reach — or (b) pin a
   deterministic/softfloat `pow`/`powf` implementation shared bit-for-bit
   by both the native and wasm32 builds, so the B7 class is eliminated by
   construction instead of merely "not yet observed to matter" in 20,000
   samples. (b) is the only option that turns "no flip found" into "cannot
   flip."

## Reproducing these numbers

All measurement code was scratch (`packages/temper-drc-rs/examples/
pow_census_native.rs`, `verdict_flip_search.rs`, `overflow_boundary.rs`,
and two temporary `#[cfg_attr(test, test)]` probes added to `dfm/tests.rs`
and registered in its `WASM_TESTS` array) — written, run, and reverted
(`git checkout --`) in the course of this investigation, not committed, per
the task's "investigation, not migration" scope. To reproduce:

1. `git checkout d5f4593142da87c75f9b21734e0e65d0e991f16d` (or any commit
   with `13aee32b7` in its history).
2. Apply the one-line fix from §7 to `packages/temper-drc-rs/src/lib.rs`
   (remove the stray `#[cfg(feature = "python")]` above `pub mod
   wasm_test_registry;`) — uncommitted, local only.
3. `source scripts/cargo_shared_env.sh`
4. Native: `cargo run --release --no-default-features --example <name>`
   from `packages/temper-drc-rs` (re-add the scratch example files — their
   content is inlined in this document's §2/§4/§3 methodology).
5. wasm32: from `packages/temper-wasm-test-runner`, `cargo build --release
   --target wasm32-unknown-unknown`, then `node tools/wasm/run_wasm_tests.mjs
   <target-dir>/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm`.
