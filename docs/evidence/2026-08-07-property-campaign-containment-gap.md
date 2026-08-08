# R7 property-based volume campaign: board-equivalents/second, and a real containment gap

**Date:** 2026-08-07
**Scope:** `packages/temper-drc-rs/src/rules/drc/property_campaigns.rs` (new),
`examples/property_containment_sweep.rs` (new),
`tests/property_containment_gap.rs` (new), `tools/wasm/gen_property_campaign.py`
(new), plus mechanical registration in `scripts/gen_wasm_test_registry.py`,
`packages/temper-drc-rs/src/rules/drc/mod.rs`, and the generated
`wasm_test_registry.rs`. `pcb/temper.kicad_pcb`, `power_pcb_dataset/drc_ceiling.json`,
and `elec/` were not touched (read-only extraction from the board, see §3).
No Worker was deployed and `wrangler` was not run.

## tl;dr

- **The gap named in this session's brief is closed for one kernel family.**
  `Component::edge_distance_to` (board.rs) — the pure geometry kernel behind
  the `drc_clearance` rule — now has a property-based campaign: 5 metamorphic
  relations x 300 seeds = **1,500 distinct-input wasm-registered tests**,
  seeded from 127 real courtyard shapes extracted from
  `pcb/temper.kicad_pcb`, perturbed into far/near/touching/overlapping/nested
  configurations. All 1,500 pass, natively and on `wasm32-unknown-unknown`,
  at every seed.
- **A property that can fail, did.** A 6th relation (monotonicity of
  `edge_distance_to` under translation along the true separating direction —
  a provable fact for disjoint convex sets) fails on ~18% of real-geometry
  cases. Root cause, confirmed independently two ways: `edge_distance_to`
  measures *boundary-to-boundary* distance, which stays a small positive
  number when one footprint is **fully nested** inside another, even though
  the shapes collide. `Component::overlaps` correctly flags these cases, so
  the real DRC registry (`ComponentOverlapCheck` + `CourtyardCheck` run
  alongside `ClearanceCheck`) is not blind to nesting — but a caller relying
  on `edge_distance_to` alone as a clearance proxy would be. Reproducer:
  seed `0`, pinned as a permanent green regression test
  (`tests/property_containment_gap.rs`), not silently patched into the
  volume registry.
- **Board-equivalents/second, measured, for the first time.** Defined as
  `C(169, 2) = 14,196` pairwise clearance checks per board (169 = every
  component on the real board). Local wasm-tier throughput for the
  clearance-kernel family alone: **92,269 invocations/s -> ~6.50
  board-equivalents/s**, single Node process, no parallelism. The reference
  oracle (full multi-rule DRC pass, single-process) sustains **0.86–0.96
  board-equivalents/s**. This is a real ~7x measured speedup **for one
  kernel family** — explicitly not a full-registry comparison; see §5 for
  why and what full-registry coverage would require.
- **Local volume, this session:** 3,010,000 property-campaign invocations
  (drc family, K=2000 local repeats), 0 unexpected verdicts; 1,651,000
  invocations across the whole tier (all 8 families, K=1000), 0 unexpected.
  Combined with the prior session's 190,000, this repo's wasm tier has now
  run **>4.8M invocations locally** without an unexplained failure.

---

## 1. What was built, and why

The prior session (`docs/evidence/2026-08-07-wasm-tier-phase1-verdict.md`)
established that the tier sustains ~3,379 fixed-suite invocations/s locally,
but running 147 fixed tests at volume explores nothing new after the first
pass. R7 (`docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`,
D6) requires coverage reported "in units of cases evaluated against the
space they sample" — a fixed suite has a coverage denominator of 1.

`Component::edge_distance_to` and `Component::overlaps`
(`packages/temper-drc-rs/src/board.rs:315-358`) are the right target: pure
functions over two polygons, already compiled into the `wasm32` build
(`board.rs` is in the `wasm-registry-infra`/family-agnostic set and is a
dependency of the `drc` family's `ClearanceCheck`/`ComponentOverlapCheck`),
with no host imports. `temper-geometry`'s equivalent kernels (`creepage_check.rs`,
`clearance_geometry.rs`, `edt.rs`, `overlap.rs`) were considered but are
**not** currently part of the wasm tier: `temper-drc-rs`'s `Cargo.toml`
deliberately keeps `temper-geometry` behind the `python` feature (comment at
line 17-24: "the `--no-default-features` wasm32 build ... does not need
temper-geometry at all"), so wiring those in would mean adding a second
crate to the wasm dependency graph — out of scope for a session whose brief
also says "run locally at volume first." `board.rs`'s own clearance kernel
was the highest-value target reachable without touching that boundary.

## 2. The five properties in the committed volume registry

All in `packages/temper-drc-rs/src/rules/drc/property_campaigns.rs`,
registered via `scripts/gen_wasm_test_registry.py` under the existing `drc`
family (which had exactly **1** registered test before this session — the
gap Phase 1's U4 named explicitly: "`drc` has 1 registered test ... of 95
total"). Each seed produces a distinct `(a, b)` component pair via
`gen_case(seed)` (§3); each property is a metamorphic relation, not an
example assertion.

| Property | Seeds | Bug it would catch |
|---|---|---|
| **Symmetry** — `d(a,b) == d(b,a)` | 300 | An asymmetric edge-pair iteration (e.g. iterating `a`'s edges against `b`'s vertices only) would make a clearance check pass in one component order and fail in the other — and `ClearanceCheck::check`'s unordered-pair loop makes "which order" an accident of vector layout. |
| **Translation invariance** | 300 | An absolute-coordinate-dependent bug (spatial-hash bucket boundary, fixed-epsilon comparison that only misfires far from the origin, catastrophic cancellation) — exercised at the board's real 20–250mm coordinate range, not just near zero. |
| **Rotation invariance** | 300 | The exact bug class this repo has already hit once in creepage/isolation code (`docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md`): a distance computation that implicitly assumes axis alignment. |
| **Scale invariance** (`d(k*a, k*b) == k*d(a,b)`) | 300 | Any absolute-epsilon threshold baked into the distance path breaking linearity at small/large `k` — this is the "monotonicity under scaling" relation the task brief names explicitly. |
| **Naive-reference agreement** | 300 | An independently-implemented, from-scratch segment/segment distance function (no `geo` crate calls at all) cross-checks `edge_distance_to`'s `geo::Line::euclidean_distance`-based fold — would catch a `geo` version upgrade silently changing semantics, or an off-by-one skipping an edge pair. |

**Result: 1,500/1,500 pass, on `wasm32-unknown-unknown` and natively.**
`cargo test --no-default-features` and
`node tools/wasm/run_wasm_tests.mjs <module> --repeat 2000` both report zero
failures across all seeds (see §5 for the volume run).

A 6th property — monotonicity under translation along the *true separating
direction* — was designed, implemented
(`edge_distance_monotonic_under_separation_impl`), and deliberately **kept
out** of the registered/generated wrapper set. It is not weakened; it is
mathematically correct for disjoint convex sets, and it genuinely fails on
real geometry. See §4.

## 3. Seeding from real geometry

`REAL_FOOTPRINTS` (127 entries, `property_campaigns.rs:106-234`) is a
read-only extraction from `pcb/temper.kicad_pcb`: every footprint carrying an
`F.CrtYd`/`B.CrtYd` courtyard rectangle or polygon, as
`(x_mm, y_mm, rotation_deg, courtyard_w_mm, courtyard_h_mm)`. Extraction
method: the board file is s-expression text; footprint blocks were located
by paren-depth tracking (no KiCad/Python parser needed), and courtyard
geometry was read directly from each footprint's `fp_rect`/`fp_poly` on the
courtyard layer. Sizes span a real 0603 SMD capacitor (2.96 x 1.46mm) to a
TO-247-class device (51.0 x 28.0mm); positions span the board's real
21–171mm x 21–252mm extent. `pcb/temper.kicad_pcb` was read, never written
(`git status` on it is clean throughout this session).

`gen_case(seed)` (not uniform-random polygons — see the module's own
rationale in its doc comment) draws two corpus entries by index, places `a`
at (a ±1mm jitter of) its real board position and rotation, and places `b`
at a random angle from `a` with a radius biased toward small separations
(`r = u^3 * max_r`, cubic bias) — so the generated corpus spans far-apart,
near-miss, touching, overlapping, **and fully-nested** regimes, which a
fixed unit-test fixture never reaches by construction and which is exactly
where a real clearance kernel's bugs live.

## 4. The finding: `edge_distance_to` does not detect containment

`examples/property_containment_sweep.rs` runs `gen_case` at volume (native,
release build) and checks two things per seed, independent of the wasm
registry:

1. `overlaps(a,b) == true` implies `edge_distance_to(a,b)` is near zero.
2. Monotonicity under true separating-direction translation (reusing
   `edge_distance_monotonic_under_separation_impl` via `catch_unwind`).

**Measured at N=50,000** (native, `cargo run --release`):

```
cases with overlaps()==true          : 22,900
overlap-distance violations          : 8,931   (39.00% of overlapping pairs)
monotonicity violations              : 9,072 / 50,000  (18.14%)
bbox-fully-nested cases              : 11,371 / 50,000 (22.74%)
throughput                           : ~273,000 cases/s (native, not wasm-tier)
```

Same result shape at N=20,000 (run first, then reproduced at N=50,000
above): both violation rates track the bbox-nested rate closely, confirming
the mechanism. **Reproducer, seed 0:** a small (2.26 x 4.56mm) real
courtyard at real position (167.8, 171.6mm) ends up fully nested inside a
larger (5.5 x 16.4mm) real courtyard `gen_case` places around it.
`a.overlaps(&b)` correctly returns `true`. `a.edge_distance_to(&b)` returns
**0.2190mm** — small, but 219x this campaign's 1e-6mm tolerance, because it
measures the gap between `a`'s boundary and the nearest edge of `b`'s
boundary, which is nonzero even though `a` is entirely inside `b`.

**This is not a total DRC miss.** `packages/temper-drc-rs/src/rules/drc/component_overlap.rs`
(`ComponentOverlapCheck`, calling `.overlaps()`) and `courtyard.rs`
(`CourtyardCheck`) are both registered by default alongside `ClearanceCheck`
(`rules/mod.rs:232-234`), so a fully-nested pair is still caught by the real
rule registry — defense in depth. What the finding shows is narrower and
still real: **`edge_distance_to` alone is not a sound clearance/overlap
proxy**, and any future code (a new rule, a refactor that consolidates
checks, a caller outside this crate) that uses it as one would silently miss
nested footprints. That coupling — soundness depends on two independently
maintained rules always running together — was not previously documented
anywhere in the codebase found by this session.

**Disposition, following the brief's "do not weaken a property to make it
pass":**

- The property's mathematical claim is unchanged and correct (for disjoint
  convex sets; see the derivation in the function's doc comment — a
  from-scratch proof, not asserted).
- It is **not** wired into the committed, CI-gating wasm registry (would
  make ~18% of that registry permanently red).
- It **is** preserved as working code, reused directly (not
  reimplemented) by the standalone sweep, and pinned as a permanent
  green regression test (`tests/property_containment_gap.rs`) that
  documents the exact behavior with a fixed reproducer — not a red test
  quietly hidden via `wasm_expected_failures.json` (that manifest's stated
  purpose is native/wasm32 platform divergence, a different mechanism; using
  it here would misrepresent a real defect as an expected, benign one).

## 5. Board-equivalents/second

**Definition.** `ClearanceCheck::check` (`rules/drc/clearance.rs`) iterates
every unordered pair of the board's components. The real board
(`pcb/temper.kicad_pcb`) has **169** components (all `(footprint ...)`
blocks; verified by direct extraction, §3's method, distinct from the 127
that carry courtyard geometry). One **board-equivalent** = the unpruned
pairwise sweep a from-scratch clearance check over the whole board would
require:

```
C(169, 2) = 169 * 168 / 2 = 14,196 pairwise edge-distance checks
```

This is deliberately conservative (a lower bound on throughput, not an
upper one): the real `ClearanceCheck` bbox-prefilters pairs and skips the
expensive polygon sweep for most of them, so production code does *less*
work per board than this unit assumes. board-equivalents/second is
`(invocations/second) / 14,196`.

**Measured, local, this session** (`node tools/wasm/run_wasm_tests.mjs
<module> --repeat K`, wasm32, one fresh isolate-equivalent module
instantiation per repetition — same protocol as Phase 1's U5):

| Build | Registered tests | K | Total invocations | Wall time | Invocations/s | Board-equivalents/s |
|---|---|---|---|---|---|---|
| `drc` family only (this campaign + the 1 pre-existing clearance test) | 1,505 | 2,000 | 3,010,000 | 32.622s | **92,269** | **6.50** |
| Full registry (all 8 families, incl. this campaign) | 1,651 | 1,000 | 1,651,000 | 56.545s | 29,198 | 2.06 |

Both runs: **0 failed, 0 unexpected, 0 non-deterministic verdicts** across
all repetitions (drc-family run: 3,010,000/3,010,000 pass; full-registry
run: 1,647,000 pass + 4,000 expected-fail, matching the pre-existing native/
wasm32 divergence manifest exactly, no new entries). Module: 250,359 bytes
(drc-only shard) / 1,342,328 bytes (full registry), **zero imports** in
both (deployable to a bare isolate), peak linear memory 1.25 / 1.88 MiB.

**Comparison to the reference oracle, explicitly scoped.** This session's
own measurement established the oracle (the real, full multi-rule DRC pass,
via `examples/r2_full_board_pass.rs` against `pcb/temper.kicad_pcb`)
sustains **0.86–0.96 board-equivalents/s single-process, 5.6/s at 8-way**.
The drc-family shard's **6.50 board-equivalents/s** is real and measured —
but it covers **one** rule family (clearance geometry) against the oracle's
**full rule registry** (clearance + creepage + isolation + connectivity +
EMC + courtyard + ...). Naive comparison would repeat exactly the error
this session's brief warns against ("naive division flatters the tier
~3,900x"). The honest statement is narrower: *for the one kernel family this
session built a property campaign against*, the tier's local single-process
throughput is already in the same order of magnitude as — and numerically
above — the oracle's full-registry single-process throughput, and roughly
comparable to its 8-way-parallel throughput, without any parallelism on the
tier side. What that implies about a full multi-family board-equivalent
(all rule kernels covered) is **not measured** and would very plausibly be
lower — see §6.

## 6. Local volume, this session, and what remains for Workers

- **This session's local invocation count:** 3,010,000 (drc-family, K=2000)
  + 1,651,000 (full registry, K=1000) + 50,000 native (containment sweep,
  N=50,000, not wasm) = **4,711,000** invocations, zero unexpected verdicts
  across all of them.
- Combined with Phase 1's own prior local-first precedent (190,000
  invocations before any Worker existed,
  `docs/evidence/2026-08-07-phase1-u5-volume.md`), this repo's wasm tier has
  now run **>4.9M invocations locally**, still without a Worker deploy for
  this campaign.
- **What remains for the deployed Workers** (per this session's rules: no
  credentials, `wrangler` not run, no deploy attempted):
  1. Deploy this campaign's `drc`-family shard (or a dedicated shard) to one
     of the 8 already-deployed Workers
     (`docs/evidence/2026-08-07-phase1-u8-multi-worker.md`) and re-run the
     ≥10^4-invocation volume run **against the real Worker**, not just
     locally — Phase 1's own U8 never did this even for the original
     147-test suite (147-request sweep only). This campaign's 1,500-test
     drc shard is a natural first target: same ABI, same module, already
     wasm-registered.
  2. Measure the Worker-vs-local platform overhead factor for this
     specific payload (pure geometry, no host imports) — Phase 1 flagged
     this as unmeasured at volume for the fixed suite; it is equally
     unmeasured here.
  3. Extend the property campaign to the other rule families
     (`erc` currently has 0 registered wasm tests — the other gap Phase 1's
     U4 named) so a true full-registry board-equivalent figure becomes
     measurable, rather than the clearance-kernel-only figure in §5.
  4. Wire `temper-geometry`'s kernels (EDT, connected components,
     courtyard/corridor geometry named in this session's brief) into the
     wasm tier — currently structurally excluded from `temper-drc-rs`'s
     wasm32 build (§1) — which would need its own crate/registry wiring,
     out of scope here.

## 7. Reproducing

```bash
# Native, all 1,504 tests in this file (1,500 seeded + 4 sanity):
cd packages/temper-drc-rs
cargo test --no-default-features rules::drc::property_campaigns::

# The pinned containment-gap regression test:
cargo test --no-default-features --test property_containment_gap

# The containment sweep (native, prints reproducers):
cargo run --release --no-default-features --example property_containment_sweep -- 50000

# wasm32, drc family, single pass + volume:
cd ../temper-wasm-test-runner
cargo build --release --target wasm32-unknown-unknown --no-default-features \
  --features wasm-registry-drc
node ../../tools/wasm/run_wasm_tests.mjs \
  ../../target-shared/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm \
  --repeat 2000

# Replay any specific failing seed found by the sweep:
#   temper_drc_rs::rules::drc::property_campaigns::gen_case(<seed>)
# reconstructs the exact (a, b) pair deterministically.

# Regenerate the seeded wrapper block after editing PROPERTIES or bumping
# the seed count in tools/wasm/gen_property_campaign.py:
python3 tools/wasm/gen_property_campaign.py --seeds 300
python3 scripts/gen_wasm_test_registry.py   # fold new names into the registry
```
