<!-- provenance: commit=04d3d2751188859fd274117f4b9b4b8bad32b2d0 dirty=false -->

# Unconditional host-facility acquisition — a deliberate sweep of every Rust crate

**Date:** 2026-08-11
**Commit:** `04d3d2751188859fd274117f4b9b4b8bad32b2d0` (`origin/main`,
`feat(wasm-tier): serve temper-thermal from a deployed Worker (#943)`)
**Tree:** clean at measurement time (`git status --porcelain` empty)
**Scope:** all 17 `Cargo.toml`s under `packages/` and `crates/`
**Method:** static sweep, then `cargo check --target wasm32-unknown-unknown
--no-default-features` on every manifest, then the existing wasm32 runner
(`make wasm-*-test`, Node v24.19.0) on all six registered tiers.

## Why this document exists

Two production bugs of one shape have been found so far, both by accident:

1. `packages/temper-geometry/src/bottleneck_geometry.rs:222` (pre-fix line;
   the lazy binding now sits at `:230-239`) — `Instant::now()` read before
   checking whether `deadline_remaining_s` was `Some`. 7 tests trapped. Fixed
   by PR #941 (`72545d4b`), which bound the `Instant` into the `Option`;
   reconciled by #942 (`cbdf8201`).
2. `packages/temper-rust-router-core/src/combinator/rewrite.rs:70-76` —
   `RewriteTrace::new()` sets `enabled` from `TEMPER_REWRITE_TRACE` **and**
   `start: Instant::now()` in the same struct literal. 23 tests trap. Open as
   issue #946.

Both surfaced only because somebody registered a crate onto the wasm32 tier and
watched tests trap. That mechanism finds bugs one crate at a time, after the
fact, and only in crates someone chose to register. This document replaces it
with a search that does not depend on registration.

**Snapshot warning.** This is one commit. `temper-io-types`,
`temper-quality-oracle`, `temper-rust-router-core` and `temper-geometry` were
under active edit by other agents while this sweep ran; every file:line below
is as of `04d3d275` and may have moved.

## Bottom line

The class is **bounded, and smaller than the discovery mechanism suggested**.

- **14 DEFECT sites** repo-wide, in **3 crates**.
- **12 of the 14 are live today** — every one of them is issue #946's
  `combinator/rewrite.rs`, already known, already ticketed, already
  demonstrated. The sweep found **no new live DEFECT anywhere**.
- **2 DEFECT sites are in crates nobody has registered** — and both are
  *latent*, not live: their crates cannot be built for `wasm32-unknown-unknown`
  at all today, because `pyo3` is a non-optional dependency. They will trap the
  day either crate is de-pyo3'd, and nothing in the repo would catch that.
- Every one of the repo's **12 `dlsym` sites but one** already carries
  `#[cfg(not(target_arch = "wasm32"))]`. The exception is the one latent DEFECT
  in `temper-placer/temper-constraints`.

That negative result is the finding. It is worth more than a list of new bugs
would have been, because it converts "we keep tripping over these" into "there
is exactly one open one, and here is the boundary of the class."

## Per-crate table

Counted by **acquisition site** (one source line that acquires a host
facility). `builds` is `cargo check --target wasm32-unknown-unknown
--no-default-features` on that crate's own manifest.

| crate | registered | builds wasm32 | DEFECT | INHERENT | ALREADY-GATED | UNREACHABLE |
|---|---|---|---:|---:|---:|---:|
| `temper-drc-rs` | yes | ✅ | 0 | 0 | 2 | 15 |
| `temper-geometry` | yes | ✅ | 0 | 1 | 5 | 1 |
| `temper-thermal` | yes | ✅ | 0 | 0 | 2 | 0 |
| `temper-design-bundle` | yes | ✅ | 0 | 0 | 1 | 0 |
| `temper-constraint-compiler` | yes | ✅ | 0 | 0 | 1 | 0 |
| `temper-rust-router-core` | yes | ✅ | **12** | 0 | 0 | 3 |
| `temper-io-types` | no | ❌ | 0 | 0 | 4 | 0 |
| `temper-quality-oracle` | no | ❌ | 0 | 0 | 2 | 0 |
| `temper-orchestration` | no | ❌ | 0 | 10 | 1 | 0 |
| `temper-rust-router` | no | ❌ | **1** | 0 | 0 | 0 |
| `temper-placer/temper-constraints` | no | ❌ | **1** | 0 | 0 | 0 |
| `temper-pcl-ir` | no | ✅ | 0 | 0 | 0 | 0 |
| `temper-wasm-test-runner` | n/a | ✅ | 0 | 0 | 0 | 0 |
| `temper-py-bridge` | no | ❌ | 0 | 0 | 0 | 0 |
| `temper-py-bridge-derive` | no | n/a (proc-macro) | 0 | 0 | 0 | 0 |
| `crates/temper-cli` | no | ✅ | 0 | 2 | 0 | 0 |
| `crates/temper-cpsat` | no | ❌ | 0 | 0 | 0 | 3 |
| **total** | | | **14** | **13** | **18** | **22** |

`UNREACHABLE` for `temper-drc-rs` is 15 `examples/*.rs` sites (argv, `fs`,
`process::exit`, `Instant`); examples are not compiled into the tier's module.
For `temper-rust-router-core` it is `solver.rs:63`, `solver.rs:109` and
`watchdog.rs:97`, all behind `#[cfg(feature = "sat")]`, which
`--no-default-features` turns off because `rustsat-cadical` is a C++ solver with
no wasm32 build. For `temper-cpsat` it is `build.rs`, which is host-side by
definition.

## The DEFECTs, itemised

### D1–D12 — `temper-rust-router-core/src/combinator/rewrite.rs` (LIVE, issue #946)

`rewrite()` is the SAT pipeline's RW1–RW7 simplifier. It takes twelve clock
readings. All twelve are acquired before anything establishes the trace is on.

| # | site | what the value feeds | when the gate arrives |
|---|---|---|---|
| D1 | `rewrite.rs:74` | `RewriteTrace.start`, read by `log()` | `log()` checks `self.enabled` at `:79` — *after* the struct literal at `:72-75` has already evaluated `Instant::now()` |
| D2 | `rewrite.rs:126` | `clone_start.elapsed()` at `:130` | never — `:128`'s `trace.log(&format!(…))` is unguarded, and `format!` evaluates its arguments eagerly |
| D3 | `rewrite.rs:140` | `iter_start.elapsed()` at `:205` | never — `:199`'s `trace.log(&format!(…))` is unguarded |
| D4–D9 | `rewrite.rs:146,155,164,173,182,191` | six per-rule `t.elapsed()` at `:149,158,167,176,185,194`, all assigned to locals unconditionally, consumed by the same unguarded `format!` at `:199` | never |
| D10 | `rewrite.rs:502` | `fn_start.elapsed()` at `:571` and `:717` | `if trace.enabled` at `:560` and `:712` — the *consumers* are guarded; the acquisition is not |
| D11 | `rewrite.rs:583` | `loop_start.elapsed()` at `:597` and `:647` | `if trace.enabled && …` at `:596`, `if trace.enabled` at `:644` — same shape |
| D12 | `rewrite.rs:665` | `rebuild_start.elapsed()` at `:716` | `if trace.enabled` at `:712` — same shape |

**Why the gate comes too late (D1).** Rust evaluates struct-literal fields in
source order, so `std::env::var("TEMPER_REWRITE_TRACE")` at `:73` runs, and then
`Instant::now()` at `:74` runs, unconditionally. The env read is harmless —
observed below, `std::env::var` on `wasm32-unknown-unknown` returns
`Err(NotPresent)` rather than trapping. The clock read is the trap. Nothing
downstream can rescue it: by the time `log()` consults `enabled`, the process is
already gone.

**Tests it blocks.** All 23 entries in
`tools/wasm/wasm_expected_failures_router_core.json`, every one classed
`no-clock`: 4 `combinator::integration::tests::*` and 19
`combinator::rewrite::tests::*`. Observed at this commit, not inherited from the
manifest:

```
$ make wasm-router-core-test
  registered      111
  passed           88
  failed            0
  expected-fail    23  (native-only properties; see manifest)
  unexpected-pass   0
  other             0

  [EXPECTED-FAIL] #39 combinator::rewrite::tests::ts1_no_overlap_rewrite_noop
      class: no-clock
      panicked at library/std/src/sys/time/unsupported.rs:13:9:
      time not implemented on this platform
```

`ts1_no_overlap_rewrite_noop` is the one to read: it is the *no-op* path, where
no rewrite rule fires and no timing is ever printed. It still traps.

**Fix size.** Larger than #941's one binding, and unevenly so:

- **D10–D12 are free.** Their consumers already sit inside `if trace.enabled`.
  Moving the three `Instant::now()` calls inside those same blocks — or binding
  them as `trace.enabled.then(Instant::now)` — changes no behaviour on any
  target and cannot alter a printed number.
- **D1 is one binding**, exactly #941's shape: `start: Option<Instant>`, set
  from the same `enabled` bool.
- **D2–D9 are the real work.** Their `.elapsed()` calls are arguments to
  *unguarded* `trace.log(&format!(…))` at `:128` and `:199`. Wrapping those two
  call sites in `if trace.enabled { … }` makes the eight acquisitions gateable
  and is the same edit that removes the crate's standing cost of formatting a
  trace string nobody reads.

Estimate: ~12 acquisition sites plus 2 `format!` call sites, one file, no API
change, no change to any value the trace prints when it is on. It is a bigger
diff than #941 but not a harder one; the manifest's own note calls for "its own
PR with its own A/B", which remains right — the A/B is `rewrite()` wall time on
a full board with tracing off, which this change should improve, not regress.

### D13 — `temper-rust-router/src/lib.rs:56` (LATENT, unregistered crate)

```rust
let phase_trace = std::env::var("TEMPER_REWRITE_TRACE").is_ok();   // :55
let t_start = std::time::Instant::now();                            // :56
```

The gate is computed on the line immediately above and first consulted at `:65`
(`if phase_trace { eprintln!(… t_start.elapsed() …) }`), and at `:81`, `:90`,
`:101`. This is #946's shape without the struct literal hiding it — the same
env var, the same trace, the same unconditional clock.

**Not live.** `temper-rust-router` declares `pyo3` with `extension-module` as a
non-optional dependency, so `cargo check --target wasm32-unknown-unknown
--no-default-features` on it exits 101 before reaching this line. It is a defect
in waiting: the crate is the pyo3 shell around `temper-rust-router-core`, and
the migration direction of travel is to thin such shells.

**Tests it would block:** none today — the crate registers no wasm32 tests. On
the day it is de-pyo3'd and registered, every test touching
`solve_topology_rust` (its single public entry point).

**Fix size:** one binding. `let t_start = phase_trace.then(std::time::Instant::now);`
plus `if let Some(t) = t_start` at the four print sites — or simply move it
after the first `if phase_trace`. Smaller than #941.

### D14 — `temper-placer/temper-constraints/src/ipc.rs:46-49` (LATENT, unregistered crate)

```rust
fn dlsym_pow() -> Option<MathFn> {
    use std::ffi::c_char;
    unsafe extern "C" {
        fn dlsym(handle: *const c_char, symbol: *const c_char) -> *mut c_char;
    }
```

This is **the only `dlsym` declaration in the repository without
`#[cfg(not(target_arch = "wasm32"))]`.** Its eleven siblings all carry it:
`temper-thermal/src/hostmath.rs:39`, `temper-thermal/src/device_power.rs:92`,
`temper-geometry/src/host_math.rs:58`, `…/pad_geometry.rs:68`,
`…/bundle_analyzer.rs:110`, `temper-drc-rs/src/pymath.rs:70` (with an explicit
always-miss wasm32 stub at `:100`), `temper-design-bundle/src/host_math.rs:30`,
`temper-orchestration/src/host_math.rs:73`,
`temper-quality-oracle/src/placement_metrics.rs:90`, `…/aesthetic.rs:73`,
`temper-constraint-compiler/src/constraints/mod.rs:172`.

**Why the gate matters more here than a `cfg` tidiness point.** The failure mode
is not a runtime trap. `temper-drc-rs/src/pymath.rs:85-86` states it and the
tier's own output confirms it: *"Declaring `dlsym` on `wasm32` emits an
`env.dlsym` **import** into the module, and a module with a non-empty import
object is not instantiable in a bare isolate."* The `temper-drc-rs` module built
at this commit reports `imports NONE (deployable to a bare isolate)`. An ungated
`dlsym` turns that into `imports env.dlsym` and the Worker stops loading —
a whole-module failure, not a per-test one, and one no expected-failure manifest
can absorb.

**Not live.** `temper-constraints` also declares `pyo3` with `extension-module`
non-optionally.

**Tests it would block:** all of them, by making the module non-instantiable.

**Fix size:** one `#[cfg(not(target_arch = "wasm32"))]` attribute plus the
wasm32 arm the siblings already model (`pymath.rs:99-101` is the copyable one).
Two lines.

## Classifications that are not defects, and why

**INHERENT — 13 sites.**

- `temper-geometry/src/transform.rs:301`, `rand::random::<f64>()` inside
  `gumbel_softmax`. Gumbel-softmax *is* the addition of sampled noise; there is
  no non-entropy path to gate against. Observed trapping on wasm32, correctly:
  ```
  [EXPECTED-FAIL] #681 transform::tests::test_gumbel_softmax_low_temp_argmax
      class: no-entropy-source
      panicked at rand-0.8.7/src/rngs/thread.rs:72:17:
      could not initialize thread_rng: getrandom: this target is not supported
  ```
  `src/wasm_entropy.rs` is the deliberate counterpart: it registers a custom
  `getrandom` source that returns `UNSUPPORTED`, so the crate *links* on wasm32
  and fails loudly at the one call that needs entropy instead of silently
  returning plausible non-random bytes.
- `temper-orchestration`: 6 sites in `preflight_stage.rs` (`:69,109,140,212,259,330`),
  2 in `pipeline.rs` (`:103,120`), 1 in `grid_stage.rs:564`, 1 in
  `convergence.rs:54`. In each, the elapsed value is consumed on every return
  path — it is the `duration_ms` / `elapsed_ms` / `total_elapsed_ms` the caller
  is handed. `convergence.rs`'s `now_secs()` exists to return a timestamp. Need
  is established at acquisition, so none is a DEFECT under this document's
  definition. Two notes for honesty: this telemetry is *incidental* rather than
  essential — it could be made optional and then it would be gateable — and
  `grid_stage.rs:564`'s `t0` is not consumed on the `FenceViolation` early-return
  at `:571`, which is the DEFECT shape in miniature. Neither is actionable while
  the crate is 2,283 compile errors away from a wasm32 build.
- `crates/temper-cli/src/main.rs:24,58`: `ExitCode` and
  `fs::read_to_string`. The command is *"read this `.kicad_pcb` and list its
  footprints"*. A native binary; it is not and will not be on the tier.

**ALREADY GATED — 18 sites.** All eleven guarded `dlsym` declarations above,
plus: `temper-io-types/src/footprint.rs:134` (`#[cfg(not(target_arch =
"wasm32"))]`), `footprint.rs:222` (inside `#[cfg(feature = "python")] mod
py_fs`), `zone_filler.rs:65,82` (whole module `#[cfg(feature = "python")]`),
`temper-drc-rs/src/dfm_py.rs:80` and `temper-geometry/src/py_errors.rs:36`
(`strerror` externs, both in `#[cfg(feature = "python")]` modules), and
`temper-geometry/src/bottleneck_geometry.rs:239` — the #941 fix, now the
canonical example of the correct shape:

```rust
let deadline: Option<(std::time::Instant, f64)> =
    deadline_remaining_s.map(|remaining| (std::time::Instant::now(), remaining));
```

**UNREACHABLE-ON-WASM32 — 22 sites.** `temper-rust-router-core`'s `solver.rs`
and `watchdog.rs` (3, behind `#[cfg(feature = "sat")]`);
`temper-drc-rs/examples/*` (15); `temper-cpsat/build.rs` (3);
`temper-geometry/examples/r2_cost_model.rs:34` (1).

## Empirical results, all at `04d3d275`

`cargo check --target wasm32-unknown-unknown --no-default-features`, per
manifest:

| crate | exit | note |
|---|---:|---|
| `temper-drc-rs` | 0 | |
| `temper-geometry` | 0 | |
| `temper-thermal` | 0 | |
| `temper-design-bundle` | 0 | |
| `temper-rust-router-core` | 0 | |
| `temper-constraint-compiler` | 0 | |
| `temper-pcl-ir` | 0 | |
| `temper-wasm-test-runner` | 0 | |
| `crates/temper-cli` | 0 | binary; compiles, never deployed |
| `temper-io-types` | 101 | 6 modules use `pyo3` with no `python` gate |
| `temper-quality-oracle` | 101 | 130 errors, all `src/lib.rs` ungated `pyo3` |
| `temper-orchestration` | 101 | 2,283 errors |
| `temper-rust-router` | 101 | `pyo3` non-optional |
| `temper-py-bridge` | 101 | `pyo3` non-optional |
| `crates/temper-cpsat` | 101 | OR-Tools C++ |

The two crates named as "being unblocked right now" are **not unblocked at this
commit**, and their blocker is a different defect class from this document's:

- `temper-io-types` — `src/explain.rs`, `src/footprint_library.rs`,
  `src/footprint_spec.rs`, `src/kicad_write_geometry.rs`,
  `src/reference_aliases.rs`, `src/report.rs` are declared in `lib.rs` without
  `#[cfg(feature = "python")]` and `use pyo3::…`. Its `std::fs` and subprocess
  sites are all correctly gated; **`temper-io-types` has zero DEFECTs of this
  class.**
- `temper-quality-oracle` — 130 errors, all ungated `pyo3` in `src/lib.rs`. Its
  two `dlsym` sites are correctly gated; **zero DEFECTs of this class.**

Registered-tier runs (`make wasm-*-test`, Node v24.19.0):

| tier | registered | passed | expected-fail | classes present |
|---|---:|---:|---:|---|
| `temper-drc-rs` | 1719 | 1715 | 4 | 3 `b7-pow-divergence-absent`, 1 `no-dynamic-loader` |
| `temper-geometry` | 722 | 714 | 8 | 4 `should-panic-traps`, 2 `no-entropy-source`, 1 `deadline-needs-a-clock`, 1 `powi-overflow-divergence-absent` |
| `temper-thermal` | 143 | 139 | 4 | 4 `b7-pow-divergence-absent` |
| `temper-rust-router-core` | 111 | 88 | **23** | **23 `no-clock`** |
| `temper-design-bundle` | 24 | 24 | 0 | — |
| `temper-constraint-compiler` | 69 | 69 | 0 | — |

`unexpected-pass` and `other` were 0 on every tier, so no exclusion is stale and
no trap is unaccounted for. `temper-drc-rs`'s module reports `imports NONE
(deployable to a bare isolate)`.

**`no-clock` is now a single-crate class.** It appears on exactly one of six
registered tiers, and every entry in it is D1–D12. `temper-geometry`'s last
clock entry was reclassified `deadline-needs-a-clock` by #942 precisely because
it is a property of the *test* (it passes `Some(-1.0)` to force the abort), not
a defect in the code under test.

Two facilities were confirmed *not* to be traps, by observation rather than by
reading std's source: `std::env::var` on `wasm32-unknown-unknown` returns
`Err(NotPresent)` — `rewrite.rs:73` executes it immediately before `:74`, and
every one of the 23 panics names `sys/time/unsupported.rs`, never an env path.
`println!`/`eprintln!` likewise did not trap on any of the 2,788 tests executed.

## How many DEFECTs are in crates nobody has registered

**Two** — D13 (`temper-rust-router/src/lib.rs:56`) and D14
(`temper-placer/temper-constraints/src/ipc.rs:48`), in two crates.

Both are **latent, not live**: neither crate builds for
`wasm32-unknown-unknown` at all today, because both declare `pyo3` with
`extension-module` as a hard dependency. Nothing in the repo would have found
either — not the tier (they are not registered and cannot be), not CI (no
wasm32 build is attempted for them), not review (both are single lines that read
as ordinary). They surface only when someone does to those crates what was done
to `temper-geometry` and `temper-rust-router-core`, and D14 in particular would
surface as *"the Worker will not instantiate"* rather than as a test failure,
which is a considerably worse first symptom.

The honest reading of "two" is not "we got lucky." It is that the defect class
is almost entirely a **clock** class, that clocks appear almost exclusively in
tracing and telemetry code, and that tracing and telemetry code lives in the
pyo3 shells and the orchestration layer — the parts of the repo furthest from
wasm32. The `dlsym` class was already solved by convention (11 of 12 sites
guarded); the entropy class was already solved by design
(`geometry/src/wasm_entropy.rs`); the filesystem and process class was already
solved by `cfg` (`io-types`). What is left is clocks, and there is one open
instance of it.

## What this does and does not license

**Does:** replace "register a crate and see what traps" as the discovery
mechanism for this class. Every acquisition site in every crate under
`packages/` and `crates/` is enumerated above and classified, and the
classification is checkable — the file:line, the gate, and the reason are each
stated, and the six registered tiers' behaviour was observed rather than
inferred.

**Does:** bound the remediation. Closing #946 (D1–D12) leaves zero live DEFECTs
of this class in the repository. That is a claim about `04d3d275` that the next
sweep can falsify.

**Does not:** make any of this a *standing* control. This sweep is a document,
not a gate — it has the same defect the U4 closure had before the freshness
checker existed: it was produced by hand, and nothing re-runs it. A new
`Instant::now()` landing tomorrow in an unregistered crate would be as invisible
as D13 and D14 are. The cheap version of the missing control is a lint or a
`grep`-shaped CI check for `Instant::now()` / `SystemTime::now()` / an ungated
`extern "C" { fn dlsym }` outside a `cfg`-guarded or `Option`-bound position;
that is unbuilt, and until it exists this document starts going stale the
moment it merges.

**Does not:** certify the crates it could not build. `temper-io-types`,
`temper-quality-oracle`, `temper-orchestration`, `temper-rust-router`,
`temper-py-bridge` and `temper-constraints` were classified by inspection plus a
failed `cargo check`, not by execution. Their DEFECT counts are lower bounds
against the compiler's own reachability, not against a running module. The day
any of them compiles for wasm32, its sites need re-reading — a site classified
INHERENT here because its crate is a pyo3 shell may become a live DEFECT when
the shell is removed.

**Does not:** say anything about correctness on native targets. Every site in
this document is correct on `x86_64-unknown-linux-gnu`. `temper-rust-router-core`
passes 154/155 (1 ignored) natively, all 23 wasm32-trapping tests included. This
is a portability sweep, not a bug hunt.

**Does not:** grant merge authority or change any tier verdict. Under D10 every
tier verdict stays advisory.

## Reproduction

```
# per-crate wasm32 buildability
for c in packages/*/Cargo.toml crates/*/Cargo.toml packages/temper-placer/*/Cargo.toml; do
  echo "=== $c"; cargo check --target wasm32-unknown-unknown \
    --no-default-features --manifest-path "$c"; done

# the six registered tiers (Node >= 20)
make wasm-router-core-test          # 111 registered, 88 pass, 23 no-clock
make wasm-geometry-test             # 722 registered, 714 pass, 8 expected-fail
make wasm-thermal-test              # 143 registered, 139 pass, 4 expected-fail
make wasm-design-bundle-test        # 24 / 24
make wasm-constraint-compiler-test  # 69 / 69
cargo build --release --target wasm32-unknown-unknown --no-default-features \
  --features wasm-test-registry --manifest-path packages/temper-wasm-test-runner/Cargo.toml
node tools/wasm/run_wasm_tests.mjs \
  target-shared/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm \
  --expected-failures tools/wasm/wasm_expected_failures.json   # 1719 / 1715

# the static sweep
rg -n -g '*.rs' 'Instant::now|SystemTime::now|UNIX_EPOCH|env::var|env::args|rand::random|thread_rng|getrandom::|OsRng|std::fs::|std::process::|std::net::|Command::new|libloading|fn dlsym|read_dir' packages/ crates/
```

## Related

- PR #941 (`72545d4b`) — the `temper-geometry` fix; the shape D1 and D13 should
  be fixed into.
- PR #942 (`cbdf8201`) — the manifest reconciliation, and the reclassification
  of `deadline-needs-a-clock` away from `no-clock`.
- PR #944 (`54881571`) — registered `temper-design-bundle`,
  `temper-rust-router-core` and `temper-constraint-compiler`; the PR whose
  registration made #946 visible, and the reason this sweep is possible.
- Issue #946 — D1–D12.
- `tools/wasm/wasm_expected_failures_router_core.json` — the 23 `no-clock`
  entries, and the manifest note that first sized the fix at "~10 `Instant::now()`
  sites plus eager `format!` args". Measured here as 12 sites plus 2 unguarded
  `format!` call sites.
- `packages/temper-drc-rs/src/pymath.rs:85-101` — why an ungated `dlsym` is a
  module-level failure (`env.dlsym` import), and the wasm32 stub D14 should copy.
- `docs/evidence/2026-08-10-wasm-tier-u4-closure-deployed-full-corpus.md` — the
  tier this sweep measures against, and the precedent for "a control that is not
  re-run is not a control."
