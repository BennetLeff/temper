---
title: WASM Tier Phase 2 — manufacturing-variation sweep, memory-bounded (parent Q3)
type: feat
date: 2026-08-11
topic: wasm-tier-phase2
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
execution: code
product_contract_source: measurement
status: draft
swept: null
swept_basis: null
---

# WASM Tier Phase 2 — Plan

## Goal Capsule

**Objective:** Break Phase 2 of
[`2026-08-03-002-feat-wasm-verification-tier-plan.md`](./2026-08-03-002-feat-wasm-verification-tier-plan.md)
("manufacturing variation... requires a fabrication-envelope model that does
not exist yet") into implementable units, the way
[`2026-08-10-001-feat-wasm-tier-phase5-plan.md`](./2026-08-10-001-feat-wasm-tier-phase5-plan.md)
did for Phase 5. Phase 2 has been decided since 2026-08-03. It is not,
however, unit-less: `docs/plans/2026-08-07-002-feat-wasm-tier-phase2-4-plan.md`
already carries a Phase 2 section (§4, units U2.1–U2.5), merged onto `main` in
commit `04d3d275` on 2026-08-10. **This plan supersedes that section rather
than duplicating it** — see Problem Frame §0 for why, and what it left
unsettled.

**What this plan changes about Phase 2:** the 2026-08-07 status doc
(`docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md`) and the 002 plan
built on it both name the fabrication-envelope model as the open question and
stop there. Neither addresses the constraint that actually binds first — the
128 MiB isolate ceiling an envelope sweep can hit through grid resolution
alone (parent R2/Q7) — nor how a sweep becomes tier-executable work (the
`wasm32` host ABI dispatches by flat index, with no way to pass a sweep
point's values at call time), nor how a sweep's findings avoid corrupting the
one board-snapshot burn-down tracker that exists. This plan settles those
three questions and, in doing so, also finds a portable fabrication-tolerance
type (`FabPreset`, `temper-io-types`) that neither prior document located,
which changes U1's scope from "design a new type" to "site an existing one
correctly."

## Product Contract

### Summary

Phase 2 sweeps the board's fabrication-relevant geometry across a bounded set
of envelope points — etch/trace-width tolerance, layer-registration offset,
drill tolerance, copper-thickness variation, solder-mask registration — and
re-runs `temper-drc-rs`'s existing rule kernels against each perturbed
instance, using the same source-generates-registry-entries mechanism that
already scaled one property-test file to 1,500 wasm32 tests
(`property_campaigns.rs`). It does this without ever varying grid resolution,
because resolution is the axis that costs 2,400 MB at 0.01 mm against a 128
MiB isolate. Findings that would also occur on the as-fabricated board extend
the existing DRC-ceiling ratchet (`power_pcb_dataset/drc_ceiling.json`) as a
distinct, non-conflating category rather than a new tracker, per parent D8.

### Problem Frame

#### §0. What already exists, and why this plan supersedes it rather than extending it

`docs/plans/2026-08-07-002-feat-wasm-tier-phase2-4-plan.md` §4 (U2.1–U2.5) is
implementation-ready in form — it has a `FabricationEnvelope` type proposal,
a maintainer question for Q3, a sweep-kernel unit, a non-vacuity canary, and a
verdict unit. Checked against the repo at `main` `12b9e205` (2026-08-11):
**zero of its named artifacts exist.** No `FabricationEnvelope` type anywhere
in the tree (`grep -rl "FabricationEnvelope"` returns nothing), no
`docs/evidence/*phase2-envelope-shape*` or `*phase2-sweep-results*` file. It
was merged and never pulled — the same "swept but never verified" gap
`docs/plans/README.md`'s own classifier would catch on its next sweep (last
run 2026-08-07, before this file existed). Per this task's scope, that file
is not touched here; a future sweep should mark it `superseded` by this one
(flagged as Outstanding Question O5).

What it got right and this plan keeps: the axis table (etch, registration,
solder-mask — sourced from `ToleranceTable`'s defaults), the framing of Q3 as
a maintainer/procurement question rather than an engineering one, and
treating a demonstrated failing case as the non-vacuity bar (parent D6).

What it missed, verified independently for this plan:

1. **It names `manufacturing_tolerances.rs` as "not a starting point... a
   CPython-embedded pyclass data model" and stops there.** True, and still
   true today — `packages/temper-design-bundle/src/manufacturing_tolerances.rs`
   still carries unconditional `use pyo3::prelude::*` and `Py<PyAny>` fields
   (`etch_tolerance`, `registration`), and `lib.rs:144-146` gates the whole
   module `#[cfg(feature = "python")]`. This is unchanged even though
   `temper-design-bundle` itself joined the deployed tier on 2026-08-11 (24
   tests) — those 24 come from other modules; `manufacturing_tolerances` and
   `manufacturing_monte_carlo` are excluded from every wasm32 build the same
   way they were on 2026-08-07. **But it never searched for a second
   candidate**, and one exists: `packages/temper-io-types/src/placer_core/
   manufacturing.rs`'s `FabPreset` — a plain `#[derive(Clone, Debug,
   PartialEq)]` struct (no `pyo3`, no `Py<PyAny>`) carrying
   `trace_width_pct`, `min_trace_mm`, `min_clearance_mm`, `etch_undercut_mm`,
   `layer_registration_mm`, `drill_tolerance_mm`, three real presets
   (`jlcpcb_standard`, `jlcpcb_hdi`, `oshpark`), and a `WASM_TESTS` block
   already generated by `scripts/gen_wasm_test_registry.py` (4 entries). As of
   commit `d76b3974` (2026-08-10, "unblock and register temper-io-types (144
   tests, eighth crate)"), `temper-io-types` **builds clean for
   `wasm32-unknown-unknown --no-default-features` and is registered** — its
   144 tests are counted among the tier's 8 registered crates. It is not one
   of the 6 crates **deployed** to a Cloudflare Worker (absent from
   `tools/wasm/wasm_tier_topology.json`), so `FabPreset`'s tests build and
   pass locally but ship nowhere today. §Key Decisions D2 explains why this
   plan still does not depend on it directly.
2. **It never mentions the 128 MiB isolate ceiling or Q7.** U2.3's "Sizing
   the sweep" section talks about *how many* samples, never about *what a
   sample costs in memory*. An envelope sweep that perturbs geometry fed into
   an occupancy-grid rasterization at finer resolution reopens exactly the
   wall parent R2 measured: `packages/temper-geometry/examples/
   r2_cost_model.rs` computes 24 MB across six layers at 0.1 mm, 2,400 MB at
   0.01 mm (both confirmed by re-derivation from the file's own formula: 1,000²
   cells × 4 bytes (`i32`) × 6 layers = 24 MB; 10,000² cells at the same
   layer count = 2,400 MB). Q7's four candidate mitigations
   (`packages/temper-geometry/src/grid_raster.rs`'s `occupancy_bitmap_row` —
   1 bit/cell, 32× denser but discards net identity; region sharding; RLE;
   hash-consed quadtree) are unchanged since the parent plan recorded them:
   only the bitmap packing exists, and it is not a drop-in for rules that
   need net identity (most DRC rules do). §Key Decisions D3 is this plan's
   answer.
3. **Its U2.3 sweep kernel names no dispatch mechanism.** "For N sweep
   samples... perturb... re-run the rule kernels" does not say how N samples
   become N wasm32-invocable entries under a host ABI that dispatches by flat
   `(name, fn())` index with no argument-passing (confirmed directly in
   `tools/wasm/gen_property_campaign.py`'s own docstring: "there is no way to
   pass a `u64` seed argument at call time"). `property_campaigns.rs` already
   solves exactly this problem for a different sweep (geometry perturbation
   seeds, not fabrication tolerance): a Python generator
   (`tools/wasm/gen_property_campaign.py`) writes one zero-argument `#[test]`
   wrapper per seed between committed markers, and
   `scripts/gen_wasm_test_registry.py` folds each into the crate-wide
   registry — 5 properties × 300 seeds = 1,500 entries from one source file,
   verified directly at `property_campaigns.rs:756` and by the registry
   markers at lines 3759/5270. §Key Decisions D4 adopts this mechanism rather
   than inventing another.
4. **It does not address routing findings into the burn-down concretely.**
   U2.5's "blocked on Q3" branch says findings are "not to be treated as a
   burn-down input... until real values replace them," but the "established"
   branch does not say how they *do* route. The tracker `docs/plans/
   2026-07-30-001-fix-drc-burndown-to-zero-plan.md` names as owning
   disposition still does not exist on `main` (confirmed: no file at that
   path; the parent plan's own `swept_basis` already recorded this on
   2026-08-07 and it remains true). What does exist and function is
   `power_pcb_dataset/drc_ceiling.json` plus `scripts/
   check_drc_ceiling_approval.py` (the R27 monotone-contract gate: ceilings
   may only decrease; a raise needs a `Ceiling-Approval:` trailer, a `_march`
   log entry, and fresh `source=measured-live` provenance). Its
   `violations_by_type` keys are `kicad-cli`'s own DRC category vocabulary,
   scoped to one committed board (`board_id: temper`,
   `path: pcb/temper.kicad_pcb`) — not a category a hypothetical
   perturbed-geometry instance naturally maps onto. §Key Decisions D5 is this
   plan's answer.
5. **No cost measurement survives to the current corpus size.** The
   852.3 tests/s figure (`docs/evidence/2026-08-10-wasm-tier-u4-closure-
   deployed-full-corpus.md`) was measured against 1,708 tests on one tier.
   The corpus has since grown twice — `temper-thermal` (`04d3d275`),
   `temper-design-bundle`/`temper-rust-router-core`/`temper-constraint-
   compiler` (`ba4bfd73`) — to **2,788 tests across 6 deployed tiers, 13
   Worker scripts** (`tools/wasm/wasm_tier_topology.json`'s own header
   comment, and independently summed from its `tiers` array: 1,719 + 722 +
   143 + 24 + 111 + 69 = 2,788), plus `temper-quality-oracle` and
   `temper-io-types` registered-but-undeployed (bringing registered crates to
   8, per `d76b3974`/`325175df`). No throughput or per-request cost figure
   exists at this size. §Units U3 measures it before U4 sizes anything
   against it.

#### §1. The tier today (measured 2026-08-11, `origin/main` `12b9e205`)

| | value | source |
|---|---:|---|
| Registered crates (wasm32-buildable) | 8 | `temper-drc-rs`, `temper-geometry`, `temper-thermal`, `temper-design-bundle`, `temper-rust-router-core`, `temper-constraint-compiler`, `temper-quality-oracle` (`325175df`), `temper-io-types` (`d76b3974`) |
| Deployed tiers (Cloudflare Worker + nightly R19 arm) | 6 | `wasm_tier_topology.json`'s `tiers` array — `quality-oracle`/`io-types` absent |
| Worker scripts | 13 | 1 full-corpus + 7 family shards for `temper-drc-rs`, 1 each for the other 5 deployed tiers |
| Deployed wasm32 tests | 2,788 | sum above, matches `ba4bfd73`'s commit message exactly |
| `temper-drc-rs` family breakdown | drc 1,524; dfm 38; safety 38; emc 31; routing 29; placement 28; types 16; erc 12; integration 3 | `tools/wasm/test_family_map.json`, counted directly |
| R19 agreement rate | 1.0 | `docs/evidence/2026-08-10-wasm-tier-u4-closure-deployed-full-corpus.md` (at 1,708; unmeasured at 2,788) |
| Measured sweep throughput | 852.3 tests/s @ concurrency 64 | same doc, **at 1,708 tests — stale relative to today's 2,788** |
| Isolate memory ceiling | 128 MiB | parent plan D3/R2 |
| Occupancy grid cost | 24 MB @ 0.1 mm, 2,400 MB @ 0.01 mm, 6 layers, `i32`/cell | `packages/temper-geometry/examples/r2_cost_model.rs`, re-derived and confirmed |
| Cloudflare cost basis | $5.00/month flat (Workers Paid, already active) + $0.30/add'l M requests over 10M/mo + $0.02/add'l M CPU-ms over 30M/mo | `docs/evidence/2026-08-07-wasm-tier-u8-volume-measured.md` §4, from published pricing, **not billing-verified** |
| `kicad-cli` oracle throughput | ~0.86–0.96 whole-board DRC checks/s single-process; ~5.6/s @ 8 concurrent | `docs/evidence/2026-08-07-reference-oracle-throughput-baseline.md` |

### Key Decisions

- **D2.1. This plan supersedes 002's Phase 2 section (§4, U2.1–U2.5) rather
  than extending it in place.** Chosen over treating 002 as already-current
  and only patching gaps: 002's units are unexecuted (zero artifacts landed,
  §0) and were never swept for currency, and three of the five substance
  gaps §0 lists (memory ceiling, dispatch mechanism, burn-down routing) are
  not small patches — they change U2.1's crate choice, U2.3's entire
  mechanism, and U2.5's "established" branch. Editing 002's file is out of
  this plan's scope (see Scope Boundaries); it is left in place for a future
  sweep to mark `superseded` (Outstanding Question O5).
- **D2.2. The `FabricationEnvelope` type is a new, small module in
  `temper-drc-rs`, not a retrofit of `manufacturing_tolerances.rs` and not a
  dependency on `temper-io-types`'s `FabPreset`.** Chosen over reusing
  `FabPreset` directly, which was tempting given it is already portable,
  wasm32-buildable and registered (§0.1): depending on it would make Phase
  2's sweep kernel depend on a crate that is not one of the 6 **deployed**
  tiers — `temper-io-types` has no Cloudflare Worker, no topology entry, no
  nightly R19 arm (§1) — pulling that unblock into this plan's scope when it
  is really its own unit for whoever owns tier-topology expansion (see Scope
  Boundaries). `FabPreset`'s field shape and default values (`drill_tolerance_mm:
  0.05`, `layer_registration_mm: 0.1`, `etch_undercut_mm: 0.05`) are adopted
  as the reference design so the two representations do not diverge by
  accident; `ToleranceTable`'s solder-mask default (`0.075`) fills the one
  axis `FabPreset` lacks that `manufacturing_tolerances.rs` has. Neither
  source is treated as fabricator-verified (same caveat 002 raised: both are
  differential-testing artifacts, not sourced from a real capability sheet).
- **D2.3. Grid resolution is never a sweep axis; only geometry is
  perturbed.** Chosen over allowing envelope points to vary raster
  resolution, which is what would reopen the 2,400 MB wall: instead, each
  envelope point perturbs the same geometric primitives
  `property_campaigns.rs` already perturbs — trace widths, pad/hole edges,
  layer offsets — as inputs to `Component::edge_distance_to` and the other
  polygon-level clearance kernels, at whatever resolution the consuming rule
  already uses (predominantly 1.0 mm in production; Q7 records nothing below
  0.1 mm is used anywhere today). Rules whose only implementation goes
  through `OccupancyGrid`/`occupancy_bitmap_row` rasterization (routing
  corridor and pour-fill DFM checks) are **excluded from this phase's first
  sweep** rather than accepted at memory risk, because Q7's only built
  mitigation (bitmap packing) discards net identity most DRC rules need, and
  none of region sharding, RLE, or the hash-consed quadtree exist. This is a
  real scope cut, stated as one (Scope Boundaries), not hidden inside "the
  sweep."
- **D2.4. The sweep is generated as static per-(envelope-point, rule)
  wrapper functions, via the same codegen pipeline `property_campaigns.rs`
  already uses** (`tools/wasm/gen_property_campaign.py`-style generator +
  `scripts/gen_wasm_test_registry.py`'s `#[test]`-scan fold-in). Chosen over
  a runtime-parameterized single test function, which the current
  `temper_run_test(index)` host ABI cannot support (flat `(name, fn())`
  index, no argument passing — confirmed in the generator's own docstring).
  This is the same answer the task posed as a question ("is that the
  mechanism, or does Phase 2 need a different one?") — it is the same
  mechanism, because the ABI constraint that forced it for
  `property_campaigns.rs` applies identically here.
- **D2.5. A sweep result extends `drc_ceiling.json`'s schema with a new,
  explicitly distinct category rather than routing into a new tracker or
  silently merging into `violations_by_type`.** Chosen per parent D8
  ("findings route into the existing burn-down... not a new tracker") over
  both alternatives: a new tracker file duplicates the `_march`/
  `Ceiling-Approval` machinery `check_drc_ceiling_approval.py` already
  enforces; merging into `violations_by_type` un-distinguished would conflate
  a real violation on the committed, as-designed board with a hypothetical
  worst-case-tolerance instance that may never be fabricated — exactly the
  ambiguity R13 already exists to prevent for a different cause (instrument
  improvement vs. regression). An envelope-margin finding is recorded
  separately and is promoted into `violations_by_type` proper — becoming
  ratchet-governed — only once its perturbation values are confirmed against
  Q3's eventual answer, not before. The exact schema shape is deliberately
  not specified here (requirements-only; see Outstanding Question O4).
- **D2.6. Sweep size N is set from a cost ceiling measured against the
  current 2,788-test, 6-tier corpus, not extrapolated from the 852.3 tests/s
  figure measured at 1,708.** Chosen because that figure predates two corpus
  expansions (§0.5, §1) and, more fundamentally, is a wall-clock throughput
  figure under local concurrency, not a Cloudflare-billed request/CPU-ms
  figure — the two are not the same unit, the same gap 002 itself never
  closed for the oracle-throughput comparison (`docs/evidence/2026-08-07-
  reference-oracle-throughput-baseline.md`'s own "unit problem" finding).

### Requirements

- **R2.1.** A `FabricationEnvelope` (or equivalently named) type exists in a
  crate that already builds clean for `wasm32-unknown-unknown
  --no-default-features` and is already one of the 6 deployed tiers, so no
  new tier-deployment infrastructure is a precondition of this phase.
- **R2.2.** Every axis in R2.1's type states its value source explicitly —
  `FabPreset`/`ToleranceTable`-derived default, or "TBD, needs maintainer" —
  and no value is presented as fabricator-verified unless it is.
- **R2.3.** No unit in this phase varies occupancy-grid resolution as a sweep
  parameter. A sweep point perturbs geometry, not raster cell size.
- **R2.4.** The sweep's tier-executable form is generated by the same
  codegen pipeline that produced `property_campaigns.rs`'s 1,500 entries, so
  it is folded into the existing per-crate registry
  (`scripts/gen_wasm_test_registry.py`) rather than inventing a second
  registration path.
- **R2.5.** At least one sweep case is a demonstrated failing case (parent
  D6/R8 non-vacuity) — a hand-calculated worst-case-tolerance combination
  that trips a rule the nominal board passes.
- **R2.6.** A defect found under this phase is distinguishable, in whatever
  record it produces, from a violation on the committed board — per D2.5 —
  and does not silently raise `drc_ceiling.json`'s ratchet-governed ceiling.
- **R2.7.** Sweep size is justified against a measured request/CPU-ms cost
  ceiling for the current (not a stale) corpus size, per D2.6.

## Units

Dependency order. U3 (cost ceiling) has no dependency on U1/U2 and may run in
parallel with them; everything else is sequential.

### U1 — A portable `FabricationEnvelope` type, correctly sited

**Deliverable.** A plain-data type in `temper-drc-rs` (or a new module
alongside `property_campaigns.rs` if the sweep kernel's home makes that
cleaner — decided by whoever executes this unit) naming: etch/trace-width
tolerance (per copper weight), layer-registration offset (per layer type),
copper-thickness variation (not modeled anywhere today — new), drill
tolerance (per hole-diameter class), solder-mask registration (scalar).

- Field shape and non-placeholder defaults are seeded from `FabPreset`
  (`packages/temper-io-types/src/placer_core/manufacturing.rs`) for the four
  axes it already has, and from `ToleranceTable`'s solder-mask default
  (`packages/temper-design-bundle/src/manufacturing_tolerances.rs:363`,
  `0.075`) for the fifth. Copper-thickness variation has no existing source
  anywhere in the repo and is added new, explicitly marked "TBD, needs
  maintainer" per R2.2.
- Explicitly does not touch `manufacturing_tolerances.rs`'s pyo3 pyclasses or
  `temper-io-types`'s `FabPreset` — this is a new type in a different crate,
  not a retrofit (D2.2).
- Evidence doc records the source table (axis → shape → value source), same
  content 002's U2.1 proposed, at whatever path the executing session
  chooses under `docs/evidence/`.

**Evidence of closure.** The type compiles under `cargo check --target
wasm32-unknown-unknown --no-default-features` inside `temper-drc-rs`; the
evidence doc's source table has an entry for every axis, with no axis
silently omitted.

**Blocked by:** nothing technical. **Blocks:** U2, U4.

### U2 — Q3's value-sourcing question, restated

**Deliverable.** The same maintainer question 002's U2.2 already posed,
restated against U1's (possibly revised) axis list, because nothing in the
repo answers it and this plan does not manufacture an answer.

- No file in the repository names this board's actual PCB fabricator or that
  fabricator's stated process capabilities (re-confirmed, not assumed from
  002). `FabPreset`'s three presets (`jlcpcb_standard`, `jlcpcb_hdi`,
  `oshpark`) are named, real fab process classes, closer to real data than
  `ToleranceTable`'s unattributed constants — but nothing in the repo states
  which preset, if any, corresponds to the board actually being fabricated.
- The question, and the interim-default fallback (documented conservative
  placeholder, e.g. IPC-2221 generic Class 2, or `FabPreset::jlcpcb_standard`
  if that is judged closer to the real process) are recorded exactly as 002
  proposed — this unit does not re-derive a different answer, it re-poses
  the same one with better-sourced defaults available if no answer arrives.

**Evidence of closure.** Either a maintainer-provided answer recorded
verbatim, or an explicit interim-default decision with its caveat ("not
fabricator-verified — findings under this default are bounds on relevance,
not fabrication-ready, per D2.5").

**Blocked by:** U1. **Blocks:** U4 (the sweep needs real, even if
provisional, values).

### U3 — The tier's real cost ceiling, measured at current scale

**Deliverable.** A measured (not extrapolated) request-count and CPU-ms
figure for the deployed tier at its current 2,788-test, 6-tier size, checked
against Cloudflare Workers Paid's published quotas (10M requests/mo, 30M
CPU-ms/mo included; §1) rather than against the stale 852.3 tests/s figure.

- Re-run the existing sweep tooling (`tools/wasm/sweep_multi_worker.mjs`
  against the now-6 deployed tiers) and record wall-clock throughput at
  current scale, exactly as `docs/evidence/2026-08-10-wasm-tier-u4-closure-
  deployed-full-corpus.md` did at 1,708 — this closes the "unmeasured at
  2,788" gap §0.5/§1 name.
- Separately, estimate (flagged as an estimate, not a Cloudflare-billed
  figure — no billing API access, same constraint `docs/evidence/2026-08-07-
  wasm-tier-u8-volume-measured.md` §4 recorded) what fraction of the 10M/30M
  monthly quotas the current corpus consumes at whatever cadence the nightly
  runs, so a sweep's added request count has a real ceiling to size against
  rather than an invented one.
- States plainly where "stops being free" sits: the current $5.00/month
  subscription is a flat fee already being paid regardless of this phase: it
  becomes non-flat only if a sweep's added monthly request count, at nightly
  cadence, would push past the 10M included requests, or if per-request
  CPU-ms (still unmeasured — this unit's second half) is high enough to push
  past 30M included CPU-ms. Both are arithmetic once this unit's numbers
  exist; neither is computed here without them (R2.7).

**Evidence of closure.** A re-measured throughput figure at 2,788 tests,
labeled with its measurement date; a stated request-count ceiling per
sweep-run at nightly cadence before the $5/month flat fee would need to grow.

**Blocked by:** nothing (independent of U1/U2). **Blocks:** U4 (sizing).

### U4 — Envelope × rule sweep as tier dispatch, memory-bounded by construction

**Deliverable.** For N envelope points (grid or Monte Carlo draw over U1's
axes, matching `monte_carlo.py`'s existing sampling shape) × the DRC/ERC/
safety rule families the perturbation is relevant to, one generated
zero-argument wrapper function per (point, rule) pair, following D2.4's
mechanism exactly — a new generator script alongside
`tools/wasm/gen_property_campaign.py`, folded in by the existing
`scripts/gen_wasm_test_registry.py`.

- N is set from U3's measured ceiling (R2.7), not invented. `property_
  campaigns.rs`'s own precedent (300 seeds/property) is a plausible starting
  order of magnitude but is not assumed correct here without U3's numbers.
- Per D2.3, no sweep point varies grid resolution; every point perturbs
  geometry at production resolution. Rules reachable only through
  `OccupancyGrid` rasterization are excluded from this unit's first cut
  (Scope Boundaries) — a smaller, honestly-scoped sweep now, not a
  memory-unsafe complete one.
- Results are reported per rule family and per envelope-point class (which
  axis was pushed to its extreme), not only aggregate pass/fail, matching
  R7's "per kernel and per rule family" framing from the parent plan.

**Evidence of closure.** The sweep builds and runs to completion inside the
128 MiB isolate (measured peak memory, not assumed); N and its justification
against U3's ceiling are recorded; results are broken out per family.

**Blocked by:** U1, U2, U3. **Blocks:** U5.

### U5 — Demonstrated-failing-case canary, and its burn-down route

**Deliverable.** One recorded case, at the envelope's extremes (maximum
under-etch combined with maximum registration offset in the same direction,
mirroring 002's U2.4 proposal), that a hand calculation against the board's
narrowest declared clearance predicts will trip a rule the nominal board
passes — and that case's finding recorded per D2.5's schema extension to
`power_pcb_dataset/drc_ceiling.json`, proving the routing path actually
works rather than only being designed.

- The hand calculation and the sweep's result for that same case are both
  recorded, so the canary can be checked by inspection, matching parent
  D6/R8's non-vacuity bar and `scripts/check_vacuous_gates.py`'s existing
  standard.
- Confirms, as part of closing this unit, whether the schema extension
  proposed in D2.5 actually coexists with `scripts/
  check_drc_ceiling_approval.py`'s existing raise-detection logic without
  triggering a false ratchet raise — this is Outstanding Question O4,
  resolved by this unit's own evidence rather than left open past it.

**Evidence of closure.** The predicted-vs-observed case recorded in
`docs/evidence/`; a `drc_ceiling.json` diff (or a stated reason none was
needed) showing the envelope-margin finding did not raise
`violations_by_type` or trip `check_drc_ceiling_approval.py` on its own.

**Blocked by:** U4.

### U6 — Phase 2 verdict

**Deliverable.** One document, matching Phase 0/1's U9/U8 and 002's U2.5
pattern: a table of U1–U5's verdicts, followed by exactly one of "Phase 2
established" (values sourced or interim-defaulted per U2, at least one
demonstrated failing case per U5, cost bounded per U3/R2.7) or "Phase 2
blocked on Q3" (no maintainer answer arrived; findings are bounds on
relevance only, per D2.5's caveat, not burn-down input).

**Evidence of closure.** The verdict document exists and its stated
conclusion matches U1–U5's individual evidence, checked, not assumed.

**Blocked by:** U1–U5.

## Scope Boundaries

- **Not in scope: deploying `temper-io-types` (or `temper-quality-oracle`) as
  a 7th/8th tier.** Both are registered (wasm32-buildable) but undeployed
  (§1); adding a Cloudflare Worker, a topology entry, and a nightly R19 arm
  for either is its own unit for whoever owns tier-topology expansion, not
  this phase (D2.2). `FabPreset`'s presence there is a design reference, not
  a dependency this plan takes on.
- **Not in scope: any of Q7's four memory-strategy candidates** (region
  sharding, run-length encoding, hash-consed quadtree; bitmap packing exists
  but discards net identity). D2.3 works entirely within production
  resolution and excludes grid-rasterized rule families from the first
  sweep rather than building toward finer resolution.
- **Not in scope: retrofitting `manufacturing_tolerances.rs`/
  `manufacturing_monte_carlo.rs`'s pyo3 pyclasses into portable types.** That
  is a separate, larger migration (their `Py<PyAny>` fields and CPython-dict
  parity requirements are load-bearing for their actual consumers) — D2.2's
  new type in `temper-drc-rs` sidesteps it rather than attempting it.
  `packages/temper-placer/src/temper_placer/manufacturing/{tolerances,
  monte_carlo,stackup_validator}.py` remain what they are today: thin
  Python re-export shims over these Rust pyo3 pyclasses, doing statistical
  process-variation/yield modeling for a different consumer (the placer's
  Monte Carlo yield estimate) than what Phase 2 needs (a bounded, tier-
  executable sweep). They are confirmed adjacent, not the model, unchanged
  from the 2026-08-07 status doc's finding.
- **Not in scope: Phase 3 and Phase 4.** Untouched by this plan;
  characterized by `docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md`
  §2 and `docs/plans/2026-08-07-002-feat-wasm-tier-phase2-4-plan.md` §5–6,
  neither of which this plan re-verifies.
- **Not in scope: merge authority for any Phase 2 finding.** Every unit's
  output stays advisory, consistent with parent D10/R15 and Phase 5's D5.4 —
  R22/R23 durability remains deferred, and nothing here proposes a required
  PR context.
- **Not in scope: sourcing real fabricator capability data.** U2 restates
  the question; answering it is a maintainer/procurement decision, the same
  position 002 already took and this plan does not relitigate.
- **Requirements-only.** No Rust, no workflow, no crate change is made by
  this plan; every "Deliverable" above is a description of future work for
  whoever pulls this phase, not code shipped alongside this document.

## Dependencies / Assumptions

- **The 128 MiB isolate limit remains the binding constraint** (parent R2:
  median 4 ns per kernel case, so CPU is not the limit; 24 MB @ 0.1 mm vs.
  2,400 MB @ 0.01 mm for a six-layer occupancy grid). D2.3 is this plan's
  entire answer to it; any future unit that reintroduces grid-resolution
  sweeping must re-open this question, not silently bypass it.
- **The `wasm32` host ABI dispatches by flat `(name, fn())` index with no
  argument-passing**, confirmed directly in `tools/wasm/
  gen_property_campaign.py`'s docstring. D2.4 and U4 depend on this being
  unchanged; if a future ABI revision adds parameterized dispatch, U4's
  codegen mechanism becomes optional rather than required.
- **`temper-io-types` builds for `wasm32-unknown-unknown` and is registered**
  (`d76b3974`, 2026-08-10) but is **not** one of the 6 deployed tiers
  (absent from `wasm_tier_topology.json`). This plan treats that gap as
  someone else's unit (Scope Boundaries), not a precondition it waits on.
- **`power_pcb_dataset/drc_ceiling.json` and `scripts/
  check_drc_ceiling_approval.py` are the operative "existing burn-down"** for
  parent D8's purposes. `docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-
  plan.md`, which D8's prose names, still does not exist on `main` (confirmed
  absent, matching the parent plan's own `swept_basis` note from
  2026-08-03/2026-08-07). If that plan lands later with a different tracker
  shape, D2.5's schema-extension design needs re-checking against it.
- **Cloudflare Workers Paid pricing** ($5/mo flat, $0.30/M requests over
  10M, $0.02/M CPU-ms over 30M) is drawn from `docs/evidence/2026-08-07-
  wasm-tier-u8-volume-measured.md`'s published-pricing citation, **not from a
  billing statement** — that document itself flags the same gap. A change to
  Cloudflare's pricing model invalidates U3's ceiling arithmetic.
- **`FabPreset`'s three presets and `ToleranceTable`'s constants are
  differential-testing artifacts**, reproduced bit-identically from a
  pre-migration Python implementation for parity purposes — neither is
  independently confirmed against a real PCB fabricator's capability sheet.
  U1 inherits them as defaults, not as verified fabrication data; U2 exists
  because of this gap.

## Outstanding Questions

- **O1** (U1). Should `FabricationEnvelope` eventually converge with
  `temper-io-types`'s `FabPreset` once that crate is deployed as its own
  tier, rather than maintaining two representations? Left open — deferred to
  whoever executes the `temper-io-types` deployment unit (Scope Boundaries).
- **O2** (U2). Q3 itself: what a fabrication-envelope model's values should
  be, and where they come from. Inherited unresolved from the parent plan
  and from 002's U2.2; this plan does not close it, only restates it against
  a better-sourced default set.
- **O3** (U3). What the deployed tier's actual per-request CPU-ms is, as
  billed by Cloudflare rather than estimated from wall-clock concurrency
  throughput. No measurement exists at any corpus size; U3 measures
  wall-clock and states this gap explicitly rather than treating the two as
  equivalent.
- **O4** (U5). Whether extending `drc_ceiling.json`'s schema with an
  envelope-margin category coexists cleanly with `scripts/
  check_drc_ceiling_approval.py`'s existing raise-detection logic, or needs a
  change to that script. Named as an open question here; U5's own evidence
  is designed to answer it during execution rather than leaving it
  permanently open.
- **O5.** Whether `docs/plans/2026-08-07-002-feat-wasm-tier-phase2-4-plan.md`
  should be marked `superseded` now that this plan exists. Out of this
  plan's scope to change (see Scope Boundaries — no other doc is touched);
  flagged for the next `docs/plans/` sweep.

## Sources / Research

- Parent plan: `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`
  (Phase 2 paragraph, D3/R2, Q3/Q7, D6/R7-R8, D8/R12-R14).
- `docs/plans/2026-08-07-002-feat-wasm-tier-phase2-4-plan.md` §4 (U2.1–U2.5)
  — the prior, unexecuted Phase 2 unit breakdown this plan supersedes.
- `docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md` — the "Phases 2–4
  have no units" finding this plan's Goal Capsule corrects (partially — 002
  postdates it) and the manufacturing-module adjacency finding this plan
  reconfirms.
- `docs/evidence/2026-08-10-wasm-tier-u4-closure-deployed-full-corpus.md` —
  the 1,708-test/852.3 tests/s baseline this plan's U3 re-measures.
- `docs/evidence/2026-08-07-wasm-tier-u8-volume-measured.md` — the Cloudflare
  Workers Paid cost basis ($5/mo flat, per-unit overage pricing).
- `docs/evidence/2026-08-07-reference-oracle-throughput-baseline.md` — the
  `kicad-cli` throughput baseline and the invocation-unit mismatch this plan
  avoids repeating for its own sweep-size arithmetic.
- `docs/evidence/2026-08-11-host-facility-acquisition-sweep.md` — confirms
  `temper-io-types` builds clean for wasm32 as of `04d3d275` and enumerates
  which crates remain pyo3-blocked.
- `packages/temper-drc-rs/src/rules/drc/property_campaigns.rs`,
  `tools/wasm/gen_property_campaign.py`, `scripts/gen_wasm_test_registry.py`
  — the codegen dispatch mechanism D2.4/U4 reuse.
- `packages/temper-design-bundle/src/manufacturing_tolerances.rs`,
  `packages/temper-io-types/src/placer_core/manufacturing.rs` — the two
  fabrication-tolerance data models checked, and why one (`ToleranceTable`)
  is excluded and the other (`FabPreset`) is a reference design but not a
  dependency.
- `packages/temper-placer/src/temper_placer/manufacturing/{tolerances,
  monte_carlo,stackup_validator}.py` — confirmed as thin re-export shims over
  the Rust pyo3 pyclasses above, not the fabrication-envelope model.
- `packages/temper-geometry/examples/r2_cost_model.rs`,
  `packages/temper-geometry/src/grid_raster.rs` (`occupancy_bitmap_row`) —
  the memory-cost figures and the one implemented Q7 mitigation.
- `power_pcb_dataset/drc_ceiling.json`, `scripts/
  check_drc_ceiling_approval.py` — the operative burn-down tracker D2.5
  extends.
- `tools/wasm/wasm_tier_topology.json`, `tools/wasm/test_family_map.json` —
  current deployed-tier and family-count measurements (§1).
- Commits `04d3d275`, `325175df`, `d76b3974`, `ba4bfd73`, `dcb9a86b` (all
  ancestors of `main` `12b9e205`) — the 2026-08-10 corpus/registration growth
  this plan's §0/§1 measure against.
