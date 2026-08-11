<!-- provenance: commit=d1b330b90a149f5effd09c7e63b87deeebdb0261 dirty=false -->

# Issue #872 — pyo3 and wasm32 feature unification: re-measured against the current 9-crate tier

**Date:** 2026-08-11
**Commit:** `d1b330b90a149f5effd09c7e63b87deeebdb0261` (`origin/main` ancestor —
`origin/main` had advanced to `b0b7641872083bbdede656adf871667a177f4831` by
the time this was written; working tree clean, no uncommitted changes)
**Scope:** measurement only. No Rust, `Cargo.toml`, script, workflow or
manifest was modified. Every crate in the tier is owned by another agent.
**Environment:** `cargo 1.97.1` / `rustc 1.97.1`, `wasm32-unknown-unknown`
(rustup-installed), Node v24.19.0 (for `WebAssembly.Module.imports()` — no
`wasm-tools` binary available in this environment, see §2 for why that's
sufficient), Linux x86_64. Shared build cache
(`CARGO_TARGET_DIR=target-shared`) via `scripts/cargo_shared_env.sh`'s
resolution path.

## Verdict, plainly

**#872 is stale. Recommend closing it.**

The finding was true when filed on 2026-08-07: `cargo tree` showed
`temper-drc-rs`'s `--no-default-features` not propagating to its
`temper-geometry` edge, so `python` (and pyo3) stayed enabled for
`temper-geometry` in the documented build graph. That exact bug was fixed
the same day, in the same evidence trail the issue cites
(`docs/evidence/2026-08-05-r1-wasm-substrate-verdict.md` Part 3, "Feature-shape
change: `default = []`"). The tier has since grown from 2 crates to 9, and
the fix generalized: **every one of the 9 registered crates' wasm32 builds
excludes pyo3 from the dependency graph today, measured directly, including
the specific multi-crate-unification shape #872's mechanism describes.**
Nothing in this investigation found pyo3 in a wasm32 dependency graph, a
pyo3 symbol in a built module, or a non-empty import list, for any of the 9
crates, alone or combined.

## 1. What "the crate" means today — 9 registered, 8 deployed

`packages/temper-wasm-test-runner/Cargo.toml` registers 9 optional crate
dependencies, each pinned `default-features = false` **on the dependency
edge itself**, not relying on `--no-default-features` at the command line:

| Crate | Registry feature | Default features (own `Cargo.toml`) | pyo3 dependency declared? |
|---|---|---|---|
| `temper-drc-rs` | `wasm-test-registry` (+ 7 family shards) | `default = []` | optional, `python = ["dep:pyo3", "dep:temper-geometry", "dep:temper-py-bridge"]` |
| `temper-geometry` | `geometry-wasm-test-registry` | `default = []` | optional, `python = ["dep:pyo3", "dep:temper-py-bridge"]` |
| `temper-thermal` | `thermal-wasm-test-registry` | `default = ["python"]` | optional, `python = [..., "dep:faer"]` |
| `temper-design-bundle` | `design-bundle-wasm-test-registry` | `default = []` | optional, `python = [...]` |
| `temper-rust-router-core` | `router-core-wasm-test-registry` | `default = ["sat"]` (no `python` feature exists on this crate) | none |
| `temper-constraint-compiler` | `constraint-compiler-wasm-test-registry` | `default = ["python", "sat"]` | optional, `python = [...]` |
| `temper-quality-oracle` | `quality-oracle-wasm-test-registry` | `default = ["python"]` | optional, `python = [...]` |
| `temper-io-types` | `io-types-wasm-test-registry` | `default = ["python"]` | optional, `python = [...]` |
| `temper-pcl-ir` | `pcl-ir-wasm-test-registry` | `default = []` | none |

5 of the 9 crates default **to** `python` when built standalone — exactly
the shape that makes edge-level `default-features = false` load-bearing
rather than redundant. `tools/wasm/wasm_tier_topology.json` deploys 8 of
these 9 as Cloudflare Workers (`temper-pcl-ir` is registered in the runner's
`Cargo.toml` but not yet in the deploy topology — "registered" and
"deployed" are genuinely different counts, matching the task brief's "9
crates registered, 8 tiers deployed"). 15 `wrangler.toml` files exist under
`packages/temper-worker/families/` (drc's 7 shards + drc's full corpus + one
each for the other 7 deployed crates = 15), matching "15 Workers".

## 2. Is pyo3 in the wasm32 dependency graph? — measured per crate, and combined

`cargo tree -i pyo3` against `packages/temper-wasm-test-runner`'s actual
`--target wasm32-unknown-unknown` graph, once per registry feature exactly
as `scripts/stage_wasm_families.sh` builds it:

```
$ cargo tree --manifest-path packages/temper-wasm-test-runner/Cargo.toml \
    --target wasm32-unknown-unknown --no-default-features \
    --features <registry-feature> -i pyo3
error: package ID specification `pyo3` did not match any packages
```

That result for all 9 registry features individually
(`wasm-test-registry`, `geometry-wasm-test-registry`,
`thermal-wasm-test-registry`, `design-bundle-wasm-test-registry`,
`router-core-wasm-test-registry`, `constraint-compiler-wasm-test-registry`,
`quality-oracle-wasm-test-registry`, `io-types-wasm-test-registry`,
`pcl-ir-wasm-test-registry`) — **pyo3 is absent from the wasm32 graph in
every one of the 9 crates' registries.**

## 3. Where unification could bite — tested directly, not inferred

Task item 3 names the mechanism precisely: does a multi-crate build (several
registry features enabled in one `cargo` invocation) unify differently from
a single-crate one? Tested by enabling **all 9 registry features at once**
in one `cargo` invocation against the one crate that actually aggregates
them:

```
$ cargo build --release --target wasm32-unknown-unknown --no-default-features \
    --features wasm-test-registry,geometry-wasm-test-registry,thermal-wasm-test-registry,\
design-bundle-wasm-test-registry,router-core-wasm-test-registry,\
constraint-compiler-wasm-test-registry,quality-oracle-wasm-test-registry,\
io-types-wasm-test-registry,pcl-ir-wasm-test-registry \
    --manifest-path packages/temper-wasm-test-runner/Cargo.toml
   Finished `release` profile [optimized] target(s) in 19.29s

$ cargo tree ... (same feature set) -i pyo3
error: package ID specification `pyo3` did not match any packages
```

No unification effect: `pyo3` stays absent even when every crate's registry
is unified into a single dependency graph. The reason is structural, not
incidental — every one of the 9 dependency edges in
`temper-wasm-test-runner/Cargo.toml` is written `default-features = false`,
and **none of the 15 registry/shard features ever activates any crate's
`python` feature.** Unification only has something to unify onto when two
edges to the same crate disagree about default features; here every edge
to every optional crate agrees (off), so there is nothing for feature-union
to escalate.

**The literal mechanism #872's evidence doc described no longer has a way to
occur at all.** The original bug was two *separately selected packages* on
one command line (`cargo build --no-default-features -p temper-drc-rs -p
temper-geometry`) unifying a shared dependency edge. That requires a Cargo
workspace so `-p` can select multiple packages in one invocation. This repo
has none:

```
$ find . -maxdepth 1 -iname Cargo.toml   →  (nothing)
$ grep -l '^\[workspace\]' packages/*/Cargo.toml   →  (nothing)
$ find packages -maxdepth 2 -iname Cargo.lock | wc -l   →  14 (one lockfile per crate)
```

Every one of the 9 crates is an independent Cargo project with its own
lockfile. The only way two of them ever enter one dependency graph today is
through a path-dependency edge (as `temper-wasm-test-runner` does), and
every such edge in this tier is pinned `default-features = false`. There is
no `-p A -p B` build anywhere in `scripts/stage_wasm_families.sh`, the three
`wasm-tier-*.yml` workflows, or `tools/wasm/tier_topology.mjs` — every
build in the pipeline is a single `--manifest-path` invocation.

## 4. Does pyo3 code survive into the module? — the artifact, not the graph

Per the task's own discipline ("distinguish dependency-graph presence from
module content from instantiability"), the graph check in §2–3 is necessary
but not sufficient — a crate could be absent from the *default* graph and
still leak in via a stray unconditional `use`. So each of the 9 registries
was actually built for `wasm32-unknown-unknown` (`--release`, the same
profile the deploy script uses: `opt-level=z`, `lto=true`,
`codegen-units=1`, `strip=true`, `panic=abort`) and the resulting
`.wasm` was inspected directly. `wasm-tools` is not installed in this
environment; `WebAssembly.Module.imports()` under Node (V8 — the same
engine `workerd` embeds, and the same substitution the project's own prior
evidence docs used) reads the same import section a `wasm-tools print`
would, so it is an equivalent check for this question.

| Crate (registry) | wasm32 build | Module size | Imports | Exports |
|---|---|---:|---:|---:|
| `temper-drc-rs` (`wasm-test-registry`, full corpus) | OK | 1,471,496 B | **0** | 8 |
| `temper-geometry` (`geometry-wasm-test-registry`) | OK | 829,091 B | **0** | 9 |
| `temper-thermal` (`thermal-wasm-test-registry`) | OK | 191,495 B | **0** | 8 |
| `temper-design-bundle` (`design-bundle-wasm-test-registry`) | OK | 257,102 B | **0** | 8 |
| `temper-rust-router-core` (`router-core-wasm-test-registry`) | OK | 303,721 B | **0** | 8 |
| `temper-constraint-compiler` (`constraint-compiler-wasm-test-registry`) | OK | 161,640 B | **0** | 8 |
| `temper-quality-oracle` (`quality-oracle-wasm-test-registry`) | OK | 209,211 B | **0** | 8 |
| `temper-io-types` (`io-types-wasm-test-registry`) | OK | 1,184,221 B | **0** | 8 |
| `temper-pcl-ir` (`pcl-ir-wasm-test-registry`, registered, not yet deployed) | OK | 128,119 B | **0** | 8 |
| **all 9 combined, one module** | OK | 3,215,544 B | **0** | 9 |

**Zero imports in every case, alone or combined.** Every module instantiates
against `{}` — the "bare Cloudflare isolate, zero imports" premise holds for
all 9 registries as they exist today, not just the ones #872's evidence
covered (2 crates, pre-fix).

A coarse string-residue check (`pyo3`, `Py_Initialize`, `PyErr_`, `_Py_`,
`PyObject`, `extension-module` — literal bytes, not proof of executable
code, but a cheap corroborating signal since `strip=true` removes most debug
info) found none of those strings in any of the 9 modules. The only hits
across all 9 builds were the substring `cpython`, and every occurrence
traces to a Rust test-function *name* embedded for the wasm registry's
name-reporting (`violation_report.rs::matches_cpython_on_rounding_classes`,
`pyfmt.rs::py_float_fmt_matches_cpython`,
`dfm/tests.rs::spoke_length_is_cpython_max_not_f64_max`, …) — tests that
assert the crate's own `pymath`/`pyfmt` kernels match CPython's floating
point behavior, unrelated to whether the `pyo3` crate is linked. `grep -rn
cpython packages/temper-drc-rs/src` confirms every source occurrence is one
of these identifiers, not a pyo3 symbol.

**`temper-geometry` in particular was worth checking harder.** The
2026-08-07 evidence (`2026-08-05-r1-wasm-substrate-verdict.md` Part 3 §3)
found a *standalone* `temper_geometry.wasm` (built directly, not through the
test-runner registry) carrying 4 `__wbindgen_*` imports from
`rand::random()` inside `transform.rs::gumbel_softmax`, sourced through
`getrandom`'s `js` feature — a real, non-pyo3 import-list defect. That
defect is fixed on this commit: `packages/temper-geometry/src/wasm_entropy.rs`
registers a custom `getrandom` source
(`getrandom::register_custom_getrandom!(no_entropy)`, `Cargo.toml`:
`getrandom = { version = "0.2", features = ["custom"] }`, no `js`) that
fails loudly (`Err(getrandom::Error::UNSUPPORTED)`, which traps the two
`gumbel_softmax` tests that sample entropy — both listed as expected
failures in `tools/wasm/wasm_expected_failures_geometry.json`) rather than
linking wasm-bindgen glue. `rand`/`getrandom` *are* still in the wasm32
dependency graph for `temper-geometry` (`cargo tree -i rand`/`-i getrandom`
both resolve, unconditionally — this is a real, non-pyo3, graph-level fact)
— and still produce **zero imports** in the built module, because nothing
exported from the wasm-test registry reaches a path that needs the entropy
source at *link* time in a way that pulls in glue; the module only traps at
*run* time on the two tests that actually call it. This is the same
graph-vs-artifact distinction #872 raised for pyo3, independently confirmed
on a different dependency in the same crate — dependency-graph presence and
artifact-level consequence are reliably different questions here, not just
for pyo3.

## 5. The counterfactual: what happens if wasm32 + `python` is forced anyway

To check whether unification pulling `python` on for wasm32 would be a
*silent* cost (the thing #872 worried about) or something else, `python`
was forced on directly against the real `wasm32-unknown-unknown` target:

```
$ cargo build --release --target wasm32-unknown-unknown --features python \
    --manifest-path packages/temper-drc-rs/Cargo.toml
error: PYO3_CROSS_PYTHON_VERSION or either an abi3-py3* or abi3t-py3* feature
must be specified when cross-compiling and PYO3_CROSS_LIB_DIR is not set.
  --- pyo3-ffi build script, exit status 1
```

`pyo3-ffi`'s build script refuses to cross-compile to `wasm32-unknown-unknown`
at all unless `PYO3_CROSS_LIB_DIR`/`PYO3_CROSS_PYTHON_VERSION` or an `abi3`
feature is supplied — none of which this tier's build ever sets. This
confirms the mechanism the 2026-08-05 evidence already named (pyo3's own
cross-compile guard) still holds on current `pyo3 0.29`/`cargo 1.97`. It
matters for #872's framing specifically: even in the worst case where
unification *did* re-activate `python` for a wasm32 build, the outcome is
not a silently-bloated module — it is a **hard, loud build failure before
any pyo3 code is compiled**, in the same job that would deploy the module.
There is no path in this pipeline from "unification turns python on" to "a
Worker silently ships pyo3."

## 6. Cost, quantified

Because pyo3 is absent from every wasm32 graph measured (§2–3) and cannot
enter one without a build failure that blocks deployment (§5), **the cost
today is zero** — there is no pyo3-laden wasm32 artifact to measure. What
was measured instead, for context:

- **Build time**, shared warm cache, per single-crate registry:
  1.6–9.4s each (temper-pcl-ir 1.57s → temper-geometry 9.40s). All 9
  registries in one combined invocation: **19.29s** wall (`/usr/bin/time
  -v`), 29.5s user / 1.9s system CPU, peak host-process RSS 799,776 KB. That
  RSS is the **build-time** memory of the `cargo`/`rustc` process on this
  machine, not the runtime memory of the deployed module in a Workers
  isolate — a different question from R2's 128 MiB ceiling, which this
  investigation was not scoped to re-measure.
- **Module size**: 128 KB (`temper-pcl-ir`) to 1.47 MB
  (`temper-drc-rs` full corpus); the all-9-combined module is 3.22 MB.
  None of this size is pyo3 — §2–4 establish pyo3 is absent from all of
  them.
- **Native pyo3 presence, for contrast**: `cargo tree --manifest-path
  packages/temper-drc-rs/Cargo.toml --features python -i pyo3` (host
  target, not wasm32) resolves `pyo3 v0.29.0` normally — pyo3 is a real,
  intentional dependency of these crates' *native* Python-extension build.
  It is specifically the `wasm32-unknown-unknown` configuration, gated by
  `default-features = false` on every edge plus pyo3's own cross-compile
  guard, where it is excluded twice over.

## 7. The three-way distinction, resolved per crate

| Crate | pyo3 in wasm32 dependency graph? | pyo3 code/symbols in the built module? | Module fails to instantiate? |
|---|---|---|---|
| `temper-drc-rs` | No (§2, §3) | No — 0 imports, no pyo3 strings (§4) | No — 0 imports |
| `temper-geometry` | No (§2, §3) | No — 0 imports, no pyo3 strings (§4). `rand`/`getrandom` ARE in-graph but produce 0 imports (custom entropy source, §4) | No — 0 imports |
| `temper-thermal` | No (§2, §3) | No — 0 imports (§4) | No — 0 imports |
| `temper-design-bundle` | No (§2, §3) | No — 0 imports (§4) | No — 0 imports |
| `temper-rust-router-core` | No (§2, §3) | No — 0 imports (§4) | No — 0 imports |
| `temper-constraint-compiler` | No (§2, §3) | No — 0 imports (§4) | No — 0 imports |
| `temper-quality-oracle` | No (§2, §3) | No — 0 imports (§4) | No — 0 imports |
| `temper-io-types` | No (§2, §3) | No — 0 imports (§4) | No — 0 imports |
| `temper-pcl-ir` | No (§2, §3) | No — 0 imports (§4) | No — 0 imports |
| all 9 combined (§3) | No | No — 0 imports (§4) | No — 0 imports |

All three claims collapse to "no" for all 9 crates, individually and
combined. #872's own text already anticipated this possibility ("this may
be a non-issue in practice... this is a nuance for U1's import-list
measurement to arbitrate") — U1's rung 2/3 measurement (the 2026-08-07
evidence) arbitrated it for the 2-crate tier that existed then, and this
document re-arbitrates it for the 9-crate tier that exists now, with the
same answer.

## 8. Why this is not merely "not yet observed" — R1's own contract already covers it

`docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` R1 requires
the crates to "compile for `wasm32-unknown-unknown` with `pyo3` behind a
feature flag." That is the shape measured here: `default = []` (or a
non-`python` default) on `temper-drc-rs`, `temper-geometry`,
`temper-design-bundle`, `temper-pcl-ir`; `python` present but excluded by
the wasm-test-runner's edge-level `default-features = false` on the other
five. The plan's own Dependencies section (line 143) already names the
current shape as interim: *"R1's `pyo3` feature gate is an interim measure,
not the permanent shape. Wave 4's endgame removes the Python boundary
entirely, at which point `pyo3` has no consumer and these crates target
`wasm32` without a flag."* Nothing measured here contradicts that — pyo3
is gated, not gone, and stays gated until Wave 4 removes the Python
boundary. #872 asked whether the gate actually holds under unification; it
does, structurally (§3), for every crate registered on the tier today.

## 9. What could not be measured

- **The live deployed Workers' actual bytes**, as opposed to a local
  rebuild of the same commit's source under the same documented command.
  This investigation rebuilt from source rather than fetching the 15
  deployed `.wasm` files from Cloudflare; `tools/wasm/wasm_tier_topology.json`
  and `scripts/stage_wasm_families.sh` show the deploy pipeline uses the
  identical `cargo build --release --target wasm32-unknown-unknown
  --no-default-features --features <feature> --manifest-path
  packages/temper-wasm-test-runner/Cargo.toml` command reproduced here, so
  the local rebuild should be byte-for-byte what staging produces from the
  same commit, but the deployed artifacts themselves (which may be a few
  commits stale, per the freshness-drift mechanism `wasm-tier-pr.yml`
  documents) were not independently downloaded and diffed here.
- **Whether some future registry feature could reintroduce python.** This
  is a structural finding about the *current* 15 features and 9 edges, not
  a proof that no future feature addition could set `default-features` back
  to unspecified on some new edge. `scripts/check_vacuous_gates.py`-style
  discipline (a CI assertion re-running §2's `cargo tree -i pyo3` check per
  registry) would catch a regression; none exists today, and this
  investigation was told not to add one (read-only scope).
- **Peak wasm32 runtime memory against the 128 MiB isolate ceiling.** Out of
  scope for #872 (that is R2's question, already measured separately per
  the plan); not re-measured here.
