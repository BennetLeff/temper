---
title: WASM Verification Tier - Plan
type: feat
date: 2026-08-03
topic: wasm-verification-tier
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
---

# WASM Verification Tier - Plan

## Goal Capsule

- **Objective:** Establish where verification runs *at scale* — a continuously-running tier that re-checks the board and the tooling that generates it at volumes GitHub Actions cannot reach, so the board earns fabrication confidence before it is built. The tier runs the pure-Rust rules and property kernels as WASM on Cloudflare Workers, off the GitHub Actions concurrency pool. Everyday pull-request CI throughput is not in scope; it stays with `docs/plans/2026-08-03-001-perf-drc-trio-parallelization-plan.md`.
- **Product authority:** temper-placer and firmware maintainer (single-maintainer project). This plan owns the substrate decision, the phase order, the success signal, and the `kicad-cli` retirement bar. It does not own the validation ideas themselves — those are pulled from `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — nor the disposition of findings, which belongs to `docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-plan.md`.
- **Open blockers:** Three, all resolved by Phase 0 and all capable of reopening the substrate decision. The `wasm32` build has never been attempted for `temper-drc-rs` or `temper-geometry`, and both declare `pyo3` unconditionally. Peak memory for a full-board rule pass is unmeasured against the 128 MiB Workers isolate limit. No workflow regenerates the board, so the continuous loop has no producer today.

---

## Product Contract

### Summary

Run the pure-Rust DRC/ERC rules and the property and metamorphic kernels as WASM on Cloudflare Workers, sharded by rule family and region, so correctness checks scale by orders of magnitude without consuming GitHub Actions capacity. `kicad-cli` continues as the reference oracle in GitHub Actions and is retired only when the Rust suite demonstrates interval-based equivalence with it. Findings route into the DRC burn-down.

### Problem Frame

`docs/STRATEGY.md` records that the critical path is design completion, and that the board cannot be fabricated: of seven protection gates, zero are validated on hardware, IGBT desaturation protection does not exist, and the router's output carries roughly 120 shorts and 499 clearance violations. `docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-plan.md` measures 1346 DRC errors across 13 categories. Confidence sufficient to commit to fabrication does not exist today, and the checks that would build it are rationed by CI capacity rather than by their value.

The rationing is measurable. On 2026-08-03 the account's concurrency ceiling was ~24 jobs while a single push requested ~40; individual jobs queued 8–13 minutes, and a run whose longest job took 6.9 minutes took 17 minutes wall-clock. Property-based tests are budget-shaped as a result: 129 properties run at `max_examples=100`, and some run at 1, 10 or 20. Those numbers were chosen to fit a runner's clock, not to find bugs.

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

### Requirements

**Phase 0 — substrate proof and producer**

- R1. `temper-drc-rs` and `temper-geometry` compile for `wasm32-unknown-unknown` with `pyo3` behind a feature flag, and a failure to do so reopens D3 rather than being worked around.
- R2. Per-case CPU cost and peak resident memory for a full-board rule pass are measured natively before any Worker is written, with memory reported against the 128 MiB isolate limit. Measured 2026-08-04 (`packages/temper-geometry/examples/r2_cost_model.rs`): median 4 ns per kernel case, and an occupancy grid costing 24 MB across six layers at 0.1 mm but 2,400 MB at 0.01 mm. CPU is therefore not a constraint even allowing a thousandfold margin for input generation and assertion; memory is, and grid resolution sets it.
- R3. Board regeneration is automated, so the tier has an input that changes when the harness changes.

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

### Phased Path

Phases are pulled individually. Phase 0 gates every later phase because its outcomes can invalidate D3.

- **Phase 0 — substrate proof and producer.** Covers R1, R2, R3. Establishes that the kernels compile to `wasm32`, what a case costs in CPU and memory, and how the board gets regenerated. A failure in R1 or R2 returns the substrate to an open decision.
- **Phase 1 — tooling correctness.** Property and metamorphic testing over the placer, router and geometry kernels, at volumes the current `max_examples` values cannot reach. First because the checkers must be trustworthy before their verdicts are scaled.
- **Phase 2 — manufacturing variation.** Sweeps the board across the fabrication envelope rather than nominal geometry alone. Requires a fabrication-envelope model that does not exist yet.
- **Phase 3 — fault injection and mutation.** Scales the seeded-defect work already in flight under portfolio R38 and R42, proving the gates bite at volume.
- **Phase 4 — design-space variants.** Validates placer candidates rather than only the committed one, turning DRC and ERC into a selection signal.

### Scope Boundaries

- Everyday pull-request CI throughput. It stays with `docs/plans/2026-08-03-001-perf-drc-trio-parallelization-plan.md`. Moving Rust rule work off GitHub relieves queue backpressure as a side-effect, which is welcome but is not this plan's measure of success.
- Cloudflare containers-as-runners, rejected under D3 on cost.
- Running `kicad-cli` on Workers. It is a native application and cannot execute in an isolate; R9 keeps it in GitHub Actions.
- The CP-SAT solve and the SAT-backed router core. Neither is portable to `wasm32`, and the solver boundary's fate is already an explicit spike under `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md` (R4).
- Migration of the Python test suite. That belongs to Wave 4.

### Dependencies / Assumptions

- The pure-Rust rules engine has no filesystem, process, thread or `rayon` usage, and its dependencies are pure Rust. This was verified by inspection on 2026-08-03 and is what makes R1 plausible; it is not a substitute for R1's build.
- Every module Wave 4 moves from Python to Rust becomes a candidate for this tier, so the addressable surface grows with that programme. Wave 4's discipline contract also mandates five property tests and three metamorphic relations per migrated module, which grows the property surface the tier exists to run.
- WASM and native builds use different math libraries, so results may differ in the final unit of least precision. R15 assumes this divergence is tolerable because the tier is advisory; a divergence at a rule threshold is itself a finding worth recording rather than a defect in the tier.
- The tier will eventually want finer grid resolution than production. Production uses 1.0 mm predominantly (131 call sites), 0.5 mm and 0.1 mm elsewhere, and nothing uses 0.01 mm — so at today's resolutions R2's memory figures are comfortable and the 128 MiB limit does not bind. Sweeping manufacturing variation is expected to want sub-trace-width detail, which is where it starts to.
- Cloudflare's pricing model bills CPU time and requests but not provisioned memory or disk, which is what makes the economics differ from containers by roughly two orders of magnitude. A change to that model invalidates D3's cost basis.

### Outstanding Questions

**Resolve Before Planning**

- Q1. What licenses `kicad-cli` retirement under R10 — how much agreement, over what corpus, sustained for how long. Without this the trajectory in D7 has no terminal condition.
- Q2. What automated board regeneration under R3 consists of, and whether it runs per-change or on a schedule. This may be larger than the rest of Phase 0.
- Q3. What a fabrication-envelope model contains for Phase 2, and where its values come from.

**Deferred to Planning**

- Q4. How work is sharded under R5 once R2 has measured the memory profile.
- Q5. How findings are ranked under R14.
- Q6. Which kernel Phase 1 ports first.
- Q7. Which memory strategy carries the tier past production resolution, given R2 measured 2,400 MB at 0.01 mm against a 128 MiB limit. Four candidates, cheapest first: reuse the existing `occupancy_bitmap_row` packing (1 bit per cell rather than an `i32` net id — 32x, already implemented, but discards net identity and most DRC rules need it); region sharding (bounded by construction, composes with the rest); run-length encoding per row (matches the kernels' scanline write pattern); and a hash-consed quadtree in the hashlife sense (highest compression on empty space and pours, worst case on thin diagonal traces). Only the quadtree's spatial half transfers — hashlife's memoised time evolution has no analogue here — and the obstacle is not compression but mutation: the kernels write cell-by-cell via `merge_cell`, whereas hash-consing assumes immutability, so it needs the kernels restructured from mutate-in-place to build-then-freeze. R2's finding that CPU is effectively free is what makes trading access cost for memory a good deal.

### Sources / Research

- `docs/STRATEGY.md` — the critical-path statement and the board's current defect state.
- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — the 43-requirement validation menu this tier executes against, including portfolio R11, R30, R38 and R42.
- `docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-plan.md` — the burn-down target, the ratchet, and the recorded instance of an improved instrument raising the count.
- `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md` — the migration programme that grows this tier's addressable surface, and the governance pattern R16 adopts.
- `docs/plans/2026-08-03-001-perf-drc-trio-parallelization-plan.md` — owns everyday CI throughput and its own Cloudflare evidence protocol.
- `packages/temper-placer/src/temper_placer/validation/_drc_api.py` — the recorded run-to-run ranges in `kicad-cli` DRC output that force R10's interval framing.
- `packages/temper-drc-rs/` — the rules engine, with `drc`, `emc`, `erc`, `safety`, `placement` and `routing` families already separated.
