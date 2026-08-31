---
title: WASM Verification Tier - Plan
type: feat
date: 2026-08-03
topic: wasm-verification-tier
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
status: active
swept: 2026-08-07
swept_basis: "in flight - governs goal-set goals 2/3; Phase 0 done, Phase 1 in progress (2026-08-07-001-feat-wasm-tier-phase1-plan.md). NOTE: cites docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-plan.md and 2026-08-03-001-perf-drc-trio-parallelization-plan.md, neither of which exists on main - both live only on the unmerged branch origin/docs/phase3-formats-io-plan"
---

# WASM Verification Tier - Plan

## Goal Capsule

- **Objective:** Establish where verification runs *at scale* — a continuously-running tier that re-checks the board and the tooling that generates it at volumes GitHub Actions cannot reach, so the board earns fabrication confidence before it is built. The tier runs the pure-Rust rules and property kernels as WASM on Cloudflare Workers, off the GitHub Actions concurrency pool. It additionally relieves the PR pool: the Rust test suites leave GitHub Actions suite-by-suite as their tier verdicts sustain agreement, ending with GitHub Actions running only CPython-bound work. Everyday pull-request CI throughput for the Python-bound surface stays with `docs/plans/2026-08-03-001-perf-drc-trio-parallelization-plan.md`.
- **Product authority:** temper-placer and firmware maintainer (single-maintainer project). This plan owns the substrate decision, the phase order, the success signal, and the `kicad-cli` retirement bar. It does not own the validation ideas themselves — those are pulled from `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — nor the disposition of findings, which belongs to `docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-plan.md`.
- **Open blockers:** Three, all resolved by Phase 0 and all capable of reopening the substrate decision. The `wasm32` build has never been attempted for `temper-drc-rs` or `temper-geometry`, and both declare `pyo3` unconditionally. Peak memory for a full-board rule pass is unmeasured against the 128 MiB Workers isolate limit. No workflow regenerates the board, so the continuous loop has no producer today.

---

## Product Contract

### Summary

Run the pure-Rust DRC/ERC rules and the property and metamorphic kernels as WASM on Cloudflare Workers, sharded by rule family and region, so correctness checks scale by orders of magnitude without consuming GitHub Actions capacity. The Rust test suites join them suite-by-suite, leaving GitHub Actions as their tier verdicts sustain agreement, until GitHub Actions runs only the CPython-bound surface. `kicad-cli` continues as the reference oracle in GitHub Actions and is retired only when the Rust suite demonstrates interval-based equivalence with it. Findings route into the DRC burn-down.

### Problem Frame

`docs/STRATEGY.md` records that the critical path is design completion, and that the board cannot be fabricated: of seven protection gates, zero are validated on hardware, IGBT desaturation protection does not exist, and the router's output carries roughly 120 shorts and 499 clearance violations. `docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-plan.md` measures 1346 DRC errors across 13 categories. Confidence sufficient to commit to fabrication does not exist today, and the checks that would build it are rationed by CI capacity rather than by their value.

The rationing is measurable. On 2026-08-03 the account's concurrency ceiling was ~24 jobs while a single push requested ~40; individual jobs queued 8–13 minutes, and a run whose longest job took 6.9 minutes took 17 minutes wall-clock. Property-based tests are budget-shaped as a result: 129 properties run at `max_examples=100`, and some run at 1, 10 or 20. Those numbers were chosen to fit a runner's clock, not to find bugs.

The same rationing motivates a second role for the tier. The Rust test surface is ~84 `#[cfg(test)]` modules across the crates, run on GitHub Actions in per-crate `cargo test` steps (temper-orchestration, temper-geometry) and a backgrounded subprocess inside the shared bundle job (temper-design-bundle). The CPython-bound differential/PBT surface — ~168k LOC of Python tests, the queue's dominant consumer — cannot run in a Workers isolate and stays on GitHub Actions permanently. Moving the Rust suites off the pool frees the capacity that the Python suite competes for; the end-state is GitHub Actions running only CPython-bound work.

The board is also not static. It is regenerated whenever the placer, router or layout harness changes, so a single sweep of a single artifact answers a question that expires. What is missing is a place for correctness checks to run continuously, at volume, without competing for the capacity that merges depend on.

The project's own history sets two traps for such a tier. The burn-down plan records the DRC count *rising* when creepage emission and netclass assignment were fixed — "nothing was created, the instrument stopped under-reporting" — so a better instrument will look like a regression. And `scripts/check_vacuous_gates.py` exists because gates that do not bite recur here; a tier running 10⁸ checks that cannot fail would be the largest instance of that failure class yet.

### Key Decisions

- D1. **The tier is design-completion capability, not developer tooling** (session-settled: user-directed — chosen over framing it as CI tooling, as Wave 4 migration infrastructure, or as unjustified: `docs/STRATEGY.md` deprioritizes tooling, and a tier whose output is board defects cleared is on the critical path rather than competing with it). Governs R7, R14.
- D2. **Scope is the at-scale tier only** (session-settled: user-directed — chosen over one plan owning all verification execution: everyday pull-request throughput and the at-scale tier are separately deliverable and have different success measures). Governs R4, and see Scope Boundaries.
- D3. **Cloudflare Workers, committed up front** (session-settled: user-directed — chosen over a native-first spike that would let measured throughput pick the substrate, and over Cloudflare containers-as-runners: the board regenerates on every harness change, so checking must be continuous, and running 10⁶ checks inside a ~24-slot pool is not possible at any scheduling. Containers were rejected at ~$65–535/month against ~$5–7). Governs R4, R5, R6.
- D4. **Phase 0 proves the substrate before anything is built on it** (session-settled: user-approved — chosen over proceeding directly to Phase 1: the `wasm32` build is unattempted, peak memory is unmeasured against a hard 128 MiB isolate limit, and no producer regenerates the board. Each can invalidate D3). Governs R1, R2, R3.
- D5. **Phase order is tooling correctness, then manufacturing variation, then fault injection, then design-space variants** (session-settled: user-directed — chosen over leading with manufacturing variation: `docs/STRATEGY.md` records the router's own DRC crashing the first time it ran and a courtyard check reporting zero collisions where real DRC found 43, so scaling unvalidated checkers multiplies unreliable answers). Governs the Phased Path.
- D6. **Success is search-space coverage, and every coverage claim must carry demonstrated kill capability** (session-settled: user-directed on coverage, user-approved on the pairing — chosen over defect count, a fabrication-readiness bar, and kill-set escape rate: coverage alone is an activity metric, and the portfolio's own non-vacuity requirements are the available antidote). Governs R7, R8.
- D7. **`kicad-cli` supplements now and is superseded later** (session-settled: user-directed — chosen over treating `kicad-cli` as the permanent oracle, which is how `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` frames it: the Rust suite is expected to become comprehensive enough to retire it, and retirement is gated on measured equivalence rather than a date). Governs R9, R10, R11.
- D8. **Findings route into the existing burn-down rather than a new tracker** (session-settled: user-directed — chosen over the tier owning its own triage: the burn-down plan already owns the target, what counts as progress, the ratchet, and escalation for violations layout cannot fix). Governs R12, R13, R14.
- D9. **The existing Rust test suite is the tier's first payload** (session-settled: user-directed — chosen over leading with new property kernels: the suite already exists and proves the substrate against real code rather than kernels written for the purpose). Governs R17, R18.
- D10. **Durability machinery is gated on gating** (session-settled: user-approved — chosen over building dead-letter handling, reconciliation and replication up front: while R15 holds the tier advisory, a lost result costs a data point rather than a merge). Governs R22, R23.
- D11. **Regeneration verifies; it does not commit** (session-settled: user-directed — chosen over a scheduled job opening a PR on difference, and over on-demand only: the committed board is a reviewed artifact with curated history, and any diff-based cadence is untrustworthy while the board writer emits track and via order from a `frozenset`). Governs R3.
- D12. **The tier is also CI tooling for the Rust test suites** (session-settled: user-directed — chosen over keeping it design-completion-only as D1 framed it: the Rust suites are wasm-portable and the pool relief is the immediate efficiency win, extending D1 rather than replacing it). Governs R24–R28.
- D13. **The transition is suite-by-suite, each crate leaving GitHub Actions as its R19 agreement sustains** (session-settled: user-directed — chosen over all-at-once after a global R19 demonstration and over keeping the suites in GHA additively: incremental relief with a smaller per-step risk window). Governs R24.
- D14. **Wasm-sensitive tests self-select via the R19 comparison** (session-settled: user-directed — chosen over an upfront per-test classification pass: a test whose tier verdict never agrees with its GitHub Actions verdict never leaves, so the mechanism separates the wasm-incompatible subset without classification machinery). Governs R27.
- D15. **The end-state is GitHub Actions running only CPython-bound work** (session-settled: user-directed — chosen over relief-only and over scale-only: the freed pool capacity benefits the Python differentials that must remain). Governs R26, R28.

### Requirements

**Phase 0 — substrate proof and producer**

- R1. `temper-drc-rs` and `temper-geometry` compile for `wasm32-unknown-unknown` with `pyo3` behind a feature flag, and a failure to do so reopens D3 rather than being worked around.
- R2. Per-case CPU cost and peak resident memory for a full-board rule pass are measured natively before any Worker is written, with memory reported against the 128 MiB isolate limit. Measured 2026-08-04 (`packages/temper-geometry/examples/r2_cost_model.rs`): median 4 ns per kernel case, and an occupancy grid costing 24 MB across six layers at 0.1 mm but 2,400 MB at 0.01 mm. CPU is therefore not a constraint even allowing a thousandfold margin for input generation and assertion; memory is, and grid resolution sets it.
- R3. Board regeneration runs per harness change in CI and verifies the pipeline still produces a valid board; the regenerated artifact is discarded and the committed board stays human-reviewed.

**The tier**

- R4. Rules and property kernels execute as WASM on Cloudflare Workers and consume no GitHub Actions concurrency.
- R5. Work is sharded so that no single unit exceeds the isolate's memory or CPU limits, using the rule families the engine already exposes as the natural seam.
- R6. Board and netlist inputs are addressed by content hash, so every finding names the exact artifact it came from.

**Coverage and non-vacuity**

- R7. Coverage is reported per kernel and per rule family, in units of cases evaluated against the space they sample.
- R8. A coverage claim is reported as vacuous unless it carries a demonstrated failing case, extending the per-gate canary contract in `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` (portfolio R30, R42) to the tier.

**The `kicad-cli` trajectory**

- R9. `kicad-cli` remains the reference oracle and continues to run in GitHub Actions while the tier is being established.
- R10. Retirement of `kicad-cli` is gated on interval-based equivalence with the Rust suite, not exact match, because `kicad-cli` DRC output is range-valued — `packages/temper-placer/src/temper_placer/validation/_drc_api.py` records `clearance` at 334–343 and `shorting_items` at 148–174 across runs on a byte-identical board.
- R11. The equivalence instrument is the full-board DRC oracle differential (portfolio R11), which already compares the placer's models against real `kicad-cli` DRC violation-by-violation; this plan adds what sustained agreement licenses.

**Findings and their disposition**

- R12. Findings route into `docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-plan.md` as burn-down input.
- R13. A rise in violation counts caused by the tier observing more is recorded as an instrument-improvement rise, attributable and distinct from a regression rise, so it does not read as a ratchet breach under `scripts/check_drc_ceiling_approval.py`.
- R14. Findings are ranked for triage rather than only counted, because review bandwidth is one maintainer and unranked volume is unusable.

**Authority and governance**

- R15. Verdicts from the WASM tier are advisory; native `temper-drc-rs` and `kicad-cli` hold merge authority until R10's equivalence bar is met.
- R16. The plan is a gated roadmap pulled opportunistically, committing no engineering capacity against the board path, matching the governance pattern in `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md` (D4, R5) and the portfolio's pull-to-plan model.

**Test-suite payload**

- R17. The portable Rust test suite runs on the tier, one test function per Worker invocation.
- R18. Test dispatch is generated at build time, because `cargo test`'s harness cannot target `wasm32-unknown-unknown`.
- R19. Per-test verdicts are compared against GitHub Actions verdicts for the same commit, and sustained agreement is the bar for licensing any later gating under R15.

**Result capture and feedback**

- R20. Every test outcome is recorded durably, attributable to a commit, a crate, and a test function.
- R21. Run completion is signalled back to GitHub Actions.
- R22. Result delivery becomes loss-proof — dead-letter handling, idempotent keys, and a reconciliation pass — before the tier's verdicts gain merge authority under R15.
- R23. Results are replicated outside the primary store, on the same trigger as R22.

**Test-suite payload (extension — PR-pool relief)**

- R24. ~~Each crate's `cargo test` suite leaves GitHub Actions once its per-test verdicts agree with the tier's (R19) for that crate, sustained — the suite-by-suite transition. The agreement duration is the same question Q1 poses for `kicad-cli` retirement under R10.~~ **RETIRED 2026-08-24 as VACUOUS** (`docs/evidence/2026-08-24-wasm-tier-phase5-verdict.md` §1, §2.1). Its population is empty: the only Rust suite left on the PR path is `temper-orchestration`'s, which is structurally native-only (proptest dev-dependencies, `#[cfg(feature = "python")]` pyo3 code, and `subprocess_stage`'s 7 tests that trap on `wasm32-unknown-unknown` with `no pids on this platform`) plus a doctest loop that no tier build can carry. Removing it would delete coverage, not duplication. Its licensing condition is separately unproducible — see R28's note. **Not carried into Phase 6.**
- R25. The pool relief is measured per GitHub Actions job or step actually removed, not per crate — the design-bundle `cargo test` runs as a backgrounded subprocess inside a shared job, so the freed capacity must be counted at the job level.
- R26. The Python differential/PBT suites remain on GitHub Actions permanently — they are CPython-bound and cannot run in a Workers isolate.
- R27. A test whose tier verdict never agrees with its GitHub Actions verdict stays on GitHub Actions — the R19 comparison self-selects the wasm-incompatible subset (host-libm-sensitive assertions) without upfront classification.
- R28. The end-state is GitHub Actions running only CPython-bound work; the moved Rust suites' tier verdicts become their required PR context per the R15/R19 gating. **BLOCKED as of 2026-08-24, and RE-PULLED as Phase 6** (`docs/plans/2026-08-24-001-feat-wasm-tier-phase6-plan.md`). `.github/required-checks.json` holds zero wasm contexts. **The blocker is not what D10/D5.4 say it is:** R22/R23 durability was closed by #992 on 2026-08-11 — dead-letter handling, idempotent work keys, a `reconcile()` pass with its own `exit(2)`, replication, each fault-injection tested — one day after the documents asserting it was unbuilt were written, and re-verified at `9546f568e`. The real blocker is (a) **R19 sustained per-crate agreement**, which the native-arm rotation re-derives once every `len(tiers)` nights and records in no artifact, so D13's licensing sentence cannot be written at all; and (b) **R10/Q1** for the `temper-drc-rs` verdict specifically. Both are measurement campaigns; the engineering prerequisite is already paid for. The first half of D15 is separately **substantially true already** — but by #978's removals and by nine crates that never had a `cargo test` step, not by any transition under D13, which was never exercised.

### Phased Path

Phases are pulled individually. Phase 0 gates every later phase because its outcomes can invalidate D3.

- **Phase 0 — substrate proof and producer.** Covers R1, R2, R3. Establishes that the kernels compile to `wasm32`, what a case costs in CPU and memory, and how the board gets regenerated. A failure in R1 or R2 returns the substrate to an open decision.
- **Phase 1 — tooling correctness.** Property and metamorphic testing over the placer, router and geometry kernels, at volumes the current `max_examples` values cannot reach. First because the checkers must be trustworthy before their verdicts are scaled.
- **Phase 2 — manufacturing variation.** Sweeps the board across the fabrication envelope rather than nominal geometry alone. Requires a fabrication-envelope model that does not exist yet.
- **Phase 3 — fault injection and mutation.** Scales the seeded-defect work already in flight under portfolio R38 and R42, proving the gates bite at volume.
- **Phase 4 — design-space variants.** Validates placer candidates rather than only the committed one, turning DRC and ERC into a selection signal.
- **Phase 5 — suite-by-suite transition (extension).** Covers R24–R28. Each crate's `cargo test` suite moves to the tier as its R19 agreement sustains; the GitHub Actions job or step it occupied is removed from the PR path; the freed capacity is measured per job. Ends with GitHub Actions running only CPython-bound work. **COMPLETE BY EXHAUSTION, 2026-08-24** — verdict in `docs/evidence/2026-08-24-wasm-tier-phase5-verdict.md`. Its additive half shipped and works; R24 is retired as vacuous, R25 is satisfied with relief measured at **zero** (D12's premise, falsified), R26 satisfied, R27 partial, and R28 handed to Phase 6.
- **Phase 6 — sustained R19 agreement, then merge authority (extension).** Covers R28 alone (`docs/plans/2026-08-24-001-feat-wasm-tier-phase6-plan.md`). Builds the per-crate agreement ledger that does not exist, raises the derivation cadence for promotion candidates only so the rotation's cost argument survives, proves the streak is falsifiable, and promotes one non-DRC crate's tier verdict to a required context. Drops D12's pool-relief framing entirely.

### Scope Boundaries

- Everyday pull-request CI throughput for the Python-bound surface stays with `docs/plans/2026-08-03-001-perf-drc-trio-parallelization-plan.md`. The Rust test suites' PR execution is in scope here (R24–R28) as the pool-relief extension.
- Cloudflare containers-as-runners, rejected under D3 on cost.
- Running `kicad-cli` on Workers. It is a native application and cannot execute in an isolate; R9 keeps it in GitHub Actions.
- The CP-SAT solve and the SAT-backed router core. Neither is portable to `wasm32`, and the solver boundary's fate is already an explicit spike under `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md` (R4).
- Migration of the Python test suite. That belongs to Wave 4; the Rust suite is in scope under D9.

### Dependencies / Assumptions

- The pure-Rust rules engine has no filesystem, process, thread or `rayon` usage, and its dependencies are pure Rust. This was verified by inspection on 2026-08-03 and is what makes R1 plausible; it is not a substitute for R1's build.
- Every module Wave 4 moves from Python to Rust becomes a candidate for this tier, so the addressable surface grows with that programme. Wave 4's discipline contract also mandates five property tests and three metamorphic relations per migrated module, which grows the property surface the tier exists to run.
- WASM and native builds use different math libraries, so results may differ in the final unit of least precision. R15 assumes this divergence is tolerable because the tier is advisory; a divergence at a rule threshold is itself a finding worth recording rather than a defect in the tier.
- The tier will eventually want finer grid resolution than production. Production uses 1.0 mm predominantly (131 call sites), 0.5 mm and 0.1 mm elsewhere, and nothing uses 0.01 mm — so at today's resolutions R2's memory figures are comfortable and the 128 MiB limit does not bind. Sweeping manufacturing variation is expected to want sub-trace-width detail, which is where it starts to.
- R1's `pyo3` feature gate is an interim measure, not the permanent shape. Wave 4's endgame removes the Python boundary entirely, at which point `pyo3` has no consumer and these crates target `wasm32` without a flag.
- `packages/temper-geometry/src/pad_geometry.rs` resolves `cos`/`sin` through `dlsym`, which is a link-time dependency `cargo check` cannot observe. Any R1 evidence that stops at type-checking does not establish that a `.wasm` artifact links.
- `rustsat-cadical` transitively blocks `temper-rust-router-core`, `temper-constraint-compiler` and `temper-rust-router` from `wasm32`. This is the concrete extent of the SAT-router exclusion recorded in Scope Boundaries.
- The board writer emits track and via order from a `frozenset`, so regeneration is not byte-reproducible across processes. R3 avoids depending on it by discarding the regenerated artifact; a diff-based cadence, or a regenerated board carrying the DRC ceiling's hash provenance, would each require fixing the writer first.
- Cloudflare's pricing model bills CPU time and requests but not provisioned memory or disk, which is what makes the economics differ from containers by roughly two orders of magnitude. A change to that model invalidates D3's cost basis.

### Outstanding Questions

**Resolve Before Planning**

- Q1. What licenses `kicad-cli` retirement under R10 — how much agreement, over what corpus, sustained for how long. Without this the trajectory in D7 has no terminal condition.
- Q3. What a fabrication-envelope model contains for Phase 2, and where its values come from.

**Deferred to Planning**

- Q4. How work is sharded under R5 once R2 has measured the memory profile.
- Q5. How findings are ranked under R14.
- Q6. Which kernel Phase 1 ports first.
- Q7. Which memory strategy carries the tier past production resolution, given R2 measured 2,400 MB at 0.01 mm against a 128 MiB limit. Four candidates, cheapest first: reuse the existing `occupancy_bitmap_row` packing (1 bit per cell rather than an `i32` net id — 32x, already implemented, but discards net identity and most DRC rules need it); region sharding (bounded by construction, composes with the rest); run-length encoding per row (matches the kernels' scanline write pattern); and a hash-consed quadtree in the hashlife sense (highest compression on empty space and pours, worst case on thin diagonal traces). Only the quadtree's spatial half transfers — hashlife's memoised time evolution has no analogue here — and the obstacle is not compression but mutation: the kernels write cell-by-cell via `merge_cell`, whereas hash-consing assumes immutability, so it needs the kernels restructured from mutate-in-place to build-then-freeze. R2's finding that CPU is effectively free is what makes trading access cost for memory a good deal.
- Q8. Whether one build-time dispatch table serves the whole portable set or one per crate, per R18.
- Q9. Which GitHub Actions jobs/steps the Rust suites actually occupy, and their measured wall-clock and queue cost — the per-job relief baseline R25 requires. (Measured 2026-08-07: `cargo test` steps for temper-orchestration and temper-geometry are separate steps; the temper-design-bundle `cargo test` is a backgrounded subprocess inside the shared bundle job.)

### Sources / Research

- `docs/STRATEGY.md` — the critical-path statement and the board's current defect state.
- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — the 43-requirement validation menu this tier executes against, including portfolio R11, R30, R38 and R42.
- `docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-plan.md` — the burn-down target, the ratchet, and the recorded instance of an improved instrument raising the count.
- `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md` — the migration programme that grows this tier's addressable surface, and the governance pattern R16 adopts.
- `docs/plans/2026-08-03-001-perf-drc-trio-parallelization-plan.md` — owns everyday CI throughput and its own Cloudflare evidence protocol.
- `packages/temper-placer/src/temper_placer/validation/_drc_api.py` — the recorded run-to-run ranges in `kicad-cli` DRC output that force R10's interval framing.
- `packages/temper-drc-rs/` — the rules engine, with `drc`, `emc`, `erc`, `safety`, `placement` and `routing` families already separated.
- Surface measurement 2026-08-07: ~84 `#[cfg(test)]` modules across the Rust crates (the wasm-portable test surface); ~168k LOC of Python tests under `packages/*/tests` + `scripts/tests` (the CPython-bound differential/PBT surface); `cargo test` locations in `.github/workflows/python-tests.yml` (temper-orchestration, temper-geometry steps; temper-design-bundle subprocess).
