<!-- provenance: commit=d1640c62c751ce673ed0ea03093bfddaf1db3342 dirty=false -->

# WASM Verification Tier — Phase 0 Verdict (U9)

**Date:** 2026-08-07
**Base:** `origin/main` @ `d1640c62c751ce673ed0ea03093bfddaf1db3342`
**Branch:** `wasm/u9-phase0-verdict`
**Unit:** U9 "The Phase 0 verdict" of
`docs/plans/2026-08-05-001-feat-wasm-tier-phase0-plan.md`
**Scope:** this document only. No source, CI, baseline, or plan document was
touched; `git status` is clean apart from this file.
**Base assertion:** `scripts/assert-base.sh origin/main` exited 0 (HEAD ==
`origin/main` at dispatch).

This document consolidates the Phase 0 verdict from the evidence produced by
U1/U2 (R1), U4/U5 (R2), and U6 (R3). It does not edit the parent plan; it is
the recorded verdict that either upholds D3 (Cloudflare Workers) or reopens it.

---

## 1. The verdict table (plan §U9)

| Req | Verdict | Evidence | Consequence |
|---|---|---|---|
| R1 | PASS | U1, U2 docs | FAIL → D3 reopens |
| R2 | PASS | U4, U5 docs | FAIL → D3 reopens |
| R3 | BLOCKED-UPSTREAM | U6, U7, U8 docs | Neither reopens D3 |

R1 = **PASS** with a noted caveat class that is a Phase-1 precondition, not a
substrate failure (feature unification, issue #872; and the gated-out portable
surface of 61 tests across 23 python-gated modules). R2 = **PASS** with the
routing-data gap (issue #873) noted as Phase-1 scope. R3 = **BLOCKED-UPSTREAM**
on the `route_pcb()` OOM (issue #871); per plan §3, U7 and U8 may still be
outstanding if U6 recorded BLOCKED-UPSTREAM, and that is an acceptable Phase 0
exit.

---

## 2. The D3 sentence

> **D3 stands.** The substrate proof and cost model support Cloudflare Workers.
> Phase 1 may be pulled.

---

## 3. Stand-alone evidence (headline numbers, inline)

The referenced evidence docs merge via PRs #874/#875/#876/#879. Until they
land, this section keeps the verdict self-contained.

### R1 — substrate proof (U1 + U2)

- **Rung 2 — links.** `cargo build --release --target wasm32-unknown-unknown`
  (via the `temper-wasm-test-runner` graph) produced
  `temper_wasm_test_runner.wasm`, **1,183,886 bytes (~1.13 MiB)**, sha256
  `5173726ea34802753854603787fe58266666391621d11ea7c8d7090efba648fe`,
  rustc/cargo 1.92.0, release profile.
- **Import list — the artifact that matters: ZERO imports.** `wasm-tools print
  | grep '(import'` returns nothing. No `env.dlsym`, no `__wbindgen_*`, no
  `getrandom` glue. A module with zero non-WASI imports is deployable to a bare
  Cloudflare isolate. `pyo3`, `rand`/`getrandom`, and `wasm-bindgen` are
  excluded from the dependency graph in the wasm configuration.
- **Rung 3 — executes.** Under wasmtime 47.0.3 (aarch64-apple-darwin):
  95 registered / 95 executed, **91 pass, 4 expected-fail, 0 unexpected**;
  native `cargo test --no-default-features`: **95 pass, 0 fail**. The four
  expected-fail tests are documented (no dynamic loader; LLVM `powf` folding on
  wasm32) and none is an unexpected trap or a ULP threshold flip.
- **Six-family exact match.** One rule from each of R5's six families (`drc`,
  `emc`, `erc`, `safety`, `placement`, `routing`) ran under wasmtime and
  matched the native verdict **exactly** (zero mismatches).
- **Condition 4 — portable surface (U2).** All six families are reachable under
  `--no-default-features` (no internal `#[cfg]` gates in `rules/`, all `*Check`
  entry points registered in `create_default_registry`, and that registry
  executes: `cargo test --no-default-features` → 94 passed in temper-drc-rs).
  Portable surface is 576 of 637 tests (61 gated out: 22 in temper-drc-rs, 39 in
  temper-geometry).
- **Source changes R1 required: one, incidental.** `temper-geometry` made
  `optional` in `temper-drc-rs/Cargo.toml` and bound to the `python` feature —
  the feature-unification issue #872, a `cfg` never added, two lines, no API or
  default-features behavior change. **Plan §2: R1 = PASS requires conditions
  1–4; all four hold, so the overall R1 verdict is PASS.** The caveat class
  (feature unification #872, and the 23 python-gated modules excluded from the
  portable build) is Phase 1's un-gating precondition, not a substrate failure —
  a caveat does not reopen D3.

### R2 — full-board cost (U4 + U5)

- **Subject.** `pcb/temper.kicad_pcb` (1,032,079 bytes, sha256
  `1cce4a0872051675b0339de3378ff7ec2c16bb4b035c999dfa408dec5ecbc3f6`), one full
  pass of all 27 rules from `create_default_registry()` (169 electrical
  components, 110 nets).
- **Per-case CPU (N=32 fresh processes).** Whole-pass wall **median 1.51 ms**
  (range 1.44–5.61 ms). `drc_clearance` dominates at 1.2 ms/case (O(n²)
  all-pairs over 169 components); other families are single-digit to ~60 µs.
- **Peak RSS (N=32 fresh processes).** **Median 3,080,192 bytes (2.94 MiB) =
  2.3% of the 128 MiB Cloudflare isolate limit** (134,217,728 bytes); max
  3,129,344 bytes — **42× below the limit, 21× below the 50% warning threshold**
  (64 MiB). Comparison is exact, not tolerance-based. The 50%-of-limit FAIL
  trigger does not fire, so no in-isolate re-measurement is required.
- **Violations.** 79 errors / 38 warnings, deterministic across all 32 runs.
- **U5 (Q7).** The rules allocate **no occupancy grid at any resolution** — the
  largest structure is the 169-entry `Vec<Component>`. Even a hypothetical naive
  `[i32; N]` grid at the production 1.0 mm resolution is 0.23 MB; only the
  0.01 mm resolution (2,289 MB) exceeds 128 MiB. **Verdict: "No memory strategy
  is required for Phase 1."** Q7's four candidates stay dormant until a future
  phase introduces sub-0.05 mm grids.
- **Routed gap.** The `BoardState` produced by `board_py_bridge` contains no
  traces/vias/zones, so routing-family rules execute but return empty (their
  per-case cost is a lower bound). The board's routing data is O(1,000)
  segments, bounding the RSS impact; the gap does not change the verdict, and
  closing it (extend the bridge's `board_dict` keys and `build_board_state`) is
  **issue #873, Phase-1 scope** — recorded, not absorbed.

### R3 — router status (U6)

- **Upstream fix landed.** The `NetClassRules` `_mm`-alias fix is **on
  `origin/main` via PR #671 (commit `40024a13c`)** — not via the feature-branch
  commit `65c100c82` the prior evidence cited. `git cherry-pick 65c100c82`
  reports already applied; codegen `--check` exits 0. The
  `AttributeError: 'NetClassRules' object has no attribute 'via_diameter_mm'`
  **does not reproduce**.
- **Route stage BLOCKED-UPSTREAM.** `route_pcb()` on the production board
  allocated **>13 GB RSS at peak** and was SIGKILL'd before completing in all
  three attempts (8.8 GB/6.5 min, 13.5 GB/7 min, 13.5 GB/15 min timeout). Wall
  time (N=12) and the 5-run sha256 determinism protocol were therefore **NOT
  RUN**. The 2026-07-27 baseline (~1.7 min, ~7 GB) was not reproduced; candidates
  (contention, regression, changed board shape 2338→2290) were recorded, not
  fixed, per U6. **Issue #871 tracks the OOM.**
- **Gate un-masked and green.** `continue-on-error: true` was removed from the
  routing DRC regression step in `extended-cpsat-slow` (trunk-only); the stale
  shape guard was re-baselined **2338→2290 segments** (the #771 zero-length-track
  removal), and the gate test **PASSED in 56 s** with the Category-B DRC
  baselines (shorting ≤ 115, unconnected ≤ 405, total ≤ 1551) still holding.
  `actionlint` exit 0.
- **Phase 0 exit.** Per plan §3, U7 (nightly producer) and U8 (anti-vacuity)
  remain outstanding because U6 recorded BLOCKED-UPSTREAM — an acceptable Phase 0
  exit: R3's failure mode is "the tier has a stale input," not "the tier cannot
  exist." R3's verdict does not gate D3.

---

## 4. Evidence sources

| Row | Verdict source | Branch | Merge PR |
|---|---|---|---|
| R1, conditions 1–3 | `docs/evidence/2026-08-05-r1-wasm-substrate-verdict.md` (U1 rungs 2–3) | `wasm/u1-rung23-closing` | #874 |
| R1, condition 4 | `docs/evidence/2026-08-05-r1-wasm-substrate-verdict.md` (U2 portable-surface section) | `wasm/u2-portable-surface` | #875 |
| R2, U4 | `docs/evidence/2026-08-05-r2-full-board-cost.md` | `wasm/u4-full-board-cost` | #876 |
| R2, U5 | §4 of `docs/evidence/2026-08-05-r2-full-board-cost.md` (Q7 table) | `wasm/u4-full-board-cost` | #876 |
| R3, U6 | `docs/evidence/2026-08-05-r3-router-status.md` | `wasm/router-unmask` | #879 |

Tracked issues carried by this verdict: **#871** route OOM (R3, blocked
upstream), **#872** feature unification (R1 caveat → Phase-1 precondition),
**#873** routing-data gap in the `BoardState` bridge (R2 scope → Phase-1).

---

## 5. What could not be verified from source docs

- The exact PR-number → branch mapping for #874/#875/#876/#879 was taken from
  the dispatch briefing; the branch-to-doc mapping above was verified by reading
  each branch's evidence file.
- In-isolate (WASM) RSS and route determinism were not measurable upstream
  (U1's rung-3 host metrics and R3's OOM); both are recorded in the respective
  evidence docs as unmeasured, and neither affects these verdicts.
