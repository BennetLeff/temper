<!-- provenance: commit=5b2a03cfe3855c78d9f575759aba06ce7c2fbcd7 dirty=false -->

# `native_only` is an upper bound, not a coverage-gap list — the real per-crate uncovered set

**Date:** 2026-08-11
**Snapshot commit (this document, worktree HEAD):** `5b2a03cfe3855c78d9f575759aba06ce7c2fbcd7`
**Corrects a misreading of:** `docs/evidence/2026-08-11-u6-orchestration-sustained-agreement.md`,
`docs/evidence/2026-08-11-u6-sustained-agreement-batch-1.md`,
`docs/evidence/2026-08-11-u6-sustained-agreement-batch-2.md` (the U6 sustained-agreement campaign,
R24) — those documents' own `native_only` counts are correct measurements; this document corrects
a wrong *reading* of what that number means, made after reading them.
**Corroborates and extends:** `docs/evidence/2026-08-11-native-only-classification-all-crates.md`
(D14/R27 mechanism classification, nine crates, one snapshot earlier).

## The correction, stated plainly

Reading the three U6 documents' `native_only` figures as "the tests that cannot leave GitHub
Actions" is **wrong**. `tools/wasm/r19_compare.py` computes `native_only` by joining native
`cargo test` output against the wasm32 registry's results **on exact test name**
(`run_comparison`, `tools/wasm/r19_compare.py:104-137`: two `dict[str, str]`/`dict[str, dict]`
maps built purely from the string `name`, no other key). A `proptest!`-generated test can never
appear in that join, for a structural reason with nothing to do with whether its *property* is
covered elsewhere: `proptest` is a `[dev-dependencies]` entry, absent by construction from the
`--no-default-features` / `wasm-registry`-feature build the registry compiles into
(`scripts/gen_wasm_test_registry.py`'s `PROPTEST_USE` exclusion). So:

- A proptest property that has been **faithfully mirrored** onto the tier — as a deterministic,
  seeded (`SplitMix64`) corpus registered under a *different* name — still counts as
  `native_only`, **permanently**. The join can never see it, because the mirror and the original
  proptest are, by name, two different tests, and only the mirror is reachable from the registry.
- This is not hypothetical. **Verified twice, live, in this worktree**, in both directions:
  - `temper-orchestration` mirrored all 45 of its `proptest-dev-dependency` tests in commit
    `7201c4205` (PR #997, already merged into this worktree's HEAD, 8 commits before this
    document's snapshot). `native_only` for `temper-orchestration` was 46 before that commit and
    is **still 46 today** — same 45 proptest names plus the one permanently-native dlsym test —
    confirmed by re-running `python3 scripts/gen_wasm_test_registry.py --crate
    temper-orchestration --census` at this snapshot: the same 8 modules, same 45 tests, still
    reported `[proptest-dev-dependency]` (detail below, §4).
  - `temper-drc-rs` mirrored all 31 of its proptests (`pymath` 15, `ipc` 9, `validation_kernels`
    7) long ago, in `packages/temper-drc-rs/src/rules/drc/property_campaigns.rs`. It reports
    exactly those 31 as native-only today, unchanged in name and count across a registered-corpus
    growth from 1,719 to 3,281 tests in the same measurement window
    (`docs/evidence/2026-08-11-u6-sustained-agreement-batch-2.md` §2) — the mirror added ~4,650
    new wasm-executed tests and moved `native_only` by exactly zero.

So `native_only` is an **upper bound** on the genuinely-uncovered set, and for a well-mirrored
crate it is a very loose one. The number that matters — "how much of this crate's *property*
space has no execution anywhere on the tier" — requires walking each crate's native-only set by
hand against its `property_campaigns*.rs` file(s) and classifying it. That is what this document
does, for all twelve registered crates.

## 1. What `native_only` does and does not measure

`native_only` is everything present in the native `cargo test` name set and absent from the
wasm32 registry's executed name set (`tools/wasm/r19_compare.py:127-137`). A name lands there for
exactly one of four structural reasons:

1. **`proptest` is a dev-dependency.** The module (or, for a correctly-gated nested submodule,
   just that submodule) `use`s `proptest::prelude::*` or invokes the `proptest!` macro, which does
   not exist in the non-`dev` build the registry compiles into. This is the largest class on this
   tier by a wide margin.
2. **The test lives under `packages/<crate>/tests/`**, a separate compilation unit
   (`scripts/gen_wasm_test_registry.py`'s registry mechanism is a `pub const` emitted inside a
   private `#[cfg(test)] mod` under `src/`, and cannot reach a sibling crate). Some of these are
   themselves proptest-based; some are plain `#[test]` fns that happen to live in `tests/` for
   organizational reasons (e.g. they need pyo3 or a fixture file). **A further wrinkle**:
   `temper-orchestration`'s `native_test_args` in `tools/wasm/wasm_tier_topology.json:423` carries
   a fourth element, `--lib`, that no other crate's entry has (verified: every other crate's
   `native_test_args` in that file omits it, `tools/wasm/wasm_tier_topology.json:309-447`).
   `--lib` excludes `tests/*.rs` from the native run entirely — cargo refuses to build any
   requested target (including the lib) once another requested target fails to compile, and all
   11 of `temper-orchestration`'s `tests/*.rs` files import `pyo3`, which does not build under
   `--no-default-features`
   (`docs/evidence/2026-08-11-u6-orchestration-sustained-agreement.md`, "Protocol"). The
   consequence: those 51 tests (confirmed still 11 files / 51 `#[test]` fns at this snapshot) are
   **not counted in `native_only` at all** — they never appear in the native output either, so
   the join never sees them as absent. They are invisible to the comparison, not present in the
   385-test tally this document works from. Every other crate runs plain `cargo test
   --no-default-features` with no `--lib`, so their `tests/*.rs` content **does** appear as
   `native_only` under class 2.
3. **The test carries its own `#[cfg(not(target_arch = "wasm32"))]`**, almost always a
   `host_libm_symbols_actually_resolve`-shaped assertion that `dlsym` resolves a host libm symbol
   — definitionally false on `wasm32-unknown-unknown` (no dynamic loader). Registered *with the
   cfg repeated on the registry entry*, present in source, absent from the compiled array.
4. **The test is a `cargo test` doctest** — its own per-example compilation unit, structurally
   outside the registry mechanism the same way a `tests/` integration binary is.

None of these four reasons says anything about whether the *property* under test has a
substantively-equivalent check running on the tier under a different name. Class 1 in particular
is where the correction matters: a crate can have mirrored 100% of its proptests and its
`native_only` count for that class will not move, because the join is name-keyed and the mirror
and the original are, correctly, two different names — the original proptest keeps running
natively (randomized, unseeded, exploring fresh input each CI run) and the mirror runs on the
tier (deterministic, fixed corpus) as a separate, additional test.

## 2. R27 and the self-selection claim — what it does and does not cover

R27 (`docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md:115`): *"A test whose tier
verdict never agrees with its GitHub Actions verdict stays on GitHub Actions — the R19 comparison
self-selects the wasm-incompatible subset (host-libm-sensitive assertions) without upfront
classification."* D14 is the design decision this requirement rests on: *"a test whose tier
verdict never agrees with its GitHub Actions verdict never leaves, so the mechanism separates the
wasm-incompatible subset without classification machinery."*

Both are claims about **disagreement** — a test that is *compared* and *diverges*. A native-only
test is never compared at all; it cannot disagree, and R27's self-selection mechanism is silent
about it by construction, not by having evaluated and cleared it. This was already the finding of
`docs/evidence/2026-08-11-native-only-classification-all-crates.md` (§0, "D14's self-selection
claim ... fails ... about tests the tier never sees") and of the Phase 1 plan itself
(`docs/plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md:588-589`: *"native-only / wasm32-only:
Does not count in the agreement rate ... Flagged for investigation, not treated as a
disagreement"*). This document is not introducing that distinction; it is applying it exhaustively
across all twelve crates and asking, for each native-only test, whether *some other mechanism* —
not R27's — has since closed the gap.

**Mirroring is that other mechanism, and it is not the same guarantee R27 describes.** R19
agreement over an in-both test means "this exact assertion executed identically on both
platforms, this run." A mirror's agreement means "a fixed, seeded corpus of N cases exercising the
same property executed identically on both platforms" — narrower on the input side (a proptest
explores its strategy's space stochastically, generating different cases run over run, shrinking
on failure; a mirror runs the *same* N cases every time) even when it is exactly as strict
per-case. **A deterministic mirror is substantively equivalent to the proptest it mirrors, not the
same guarantee.** A mirror can be green forever while missing an input region a proptest would
eventually sample into. This is not a hypothetical caveat — §7 below documents two cases in this
exact codebase where a mirror's *first* sampling strategy had precisely this failure, caught by
mutation testing before being fixed.

## 3. Method

For each of the twelve crates `scripts/gen_wasm_test_registry.py`'s `CRATES` dict registers
(confirmed exhaustive against `tools/wasm/wasm_tier_topology.json`'s twelve `tiers` entries,
`tools/wasm/wasm_tier_topology.json:303-447`), this document:

1. Took the native-only enumeration from the most recent measurement available — the U6 campaign
   docs (orchestration, batch 1, batch 2) and, for classification detail,
   `docs/evidence/2026-08-11-native-only-classification-all-crates.md` — and **re-verified the
   registered/excluded module list live at this snapshot** via `python3
   scripts/gen_wasm_test_registry.py --crate <name> --census` for all twelve crates (as detailed in §3.1: counts
   in this repo are known to drift under concurrent agent work, so a same-day re-check is not
   optional). Every module-level `[proptest-dev-dependency]` count reproduced its cited evidence
   document exactly except `temper-orchestration`, where the mirror (PR #997) landed inside this
   measurement window — see the correction above and §4's `temper-orchestration` row.
2. For every native-only test in class 1 (proptest) or the proptest-flavored portion of class 2
   (integration), grepped every `property_campaigns*.rs` file (and, for `temper-orchestration`,
   the inline `mod tests { ... }` mirrors added by #997) for that property's name or its doc
   comment's own "Mirrors proptest property `<name>`" annotation — a convention this repo already
   uses consistently (113 occurrences across 8 files) — and, where a name match alone was
   ambiguous, read the mirror function body against the original `proptest!` block to confirm it
   exercises the same relation, not merely a same-shaped one.
3. For every class-3/4 (`cfg`-excluded, doctest) entry, confirmed the citation against
   `docs/evidence/2026-08-11-native-only-classification-all-crates.md`'s file:line detail, spot
   re-read at this snapshot where the file had moved.
4. Read every campaign file's own module-header doc comment in full — every one of them states,
   in prose, exactly which native modules/files it mirrors and, where relevant, which properties
   it deliberately does *not* mirror and why. This turned up two additional findings not in any
   prior evidence document (§6, §7).

**What this method does not do:** it does not re-run `cargo test` or the wasm32 build for any
crate (the U6 docs already did that, this same day, for all twelve); it is a read-only
classification pass over source, the same shape as
`docs/evidence/2026-08-11-native-only-classification-all-crates.md`'s own method, extended to
answer "and does a mirror exist" rather than stopping at "why is this name absent."

### 3.1 A live count discrepancy, reported rather than forced to match

The assigning task cited "405 native-only across 11 crates." Re-summing the actual per-crate
figures in the three source U6 documents (orchestration 46 + batch 1's five crates
89+48+2+32+24=195 + batch 2's six crates 3+13+41+55+0+32=144, i.e. 46+195+144) gives **385**, not
405, across the **twelve** crates those three documents jointly cover (`temper-pcl-ir`
contributing 0). This document's own live re-census at the snapshot commit reproduces 385 exactly,
test name for test name, against every source document except `temper-orchestration` (see §4's
`temper-orchestration` row —
its true current native-only composition is unchanged in count, 46, but this document's own
classification differs from that document's stated future-tense plan). Both 385 and the task's 405
are consistent with this repo's own repeated warning that these counts drift under concurrent
agent work and should be treated as "true when measured," not as a stable constant; this document
reports what it independently re-measured rather than reconciling to a number it could not
reproduce.

## 4. Per-crate partition

Four classes, applied to every native-only test:

- **MIRRORED** — a proptest with a deterministic tier equivalent, name cited. Covered in
  substance (§2, "R27 and the self-selection claim," above — not the same guarantee, but not a
  gap either).
- **UNMIRRORED PROPTEST** — a proptest with no tier equivalent found. Genuinely uncovered; this is
  the actionable output (ranked list, §5).
- **STRUCTURALLY NATIVE** — host-facility (dlsym), a doctest, or a property that would pass
  vacuously on wasm32 if mirrored (§7). Can never move to the tier as-is; not a gap.
- **INTEGRATION-TARGET** — lives in `tests/*.rs`. Structurally unreachable by the registry
  mechanism regardless of mirror status; noted separately whether a substance-equivalent mirror
  exists elsewhere. `temper-orchestration`'s 51 are flagged separately: `--lib` hides them from
  `native_only` entirely (§1, class 2) — they are
  not part of the 385 this table sums, but they are real, permanently-native, pyo3-bound tests.

| crate | native-only (live) | MIRRORED | UNMIRRORED PROPTEST | STRUCTURALLY NATIVE | INTEGRATION-TARGET | hidden by `--lib` |
|---|---:|---:|---:|---:|---:|---:|
| `temper-drc-rs` | 32 | 31 | 0 | 0 | 1 | — |
| `temper-geometry` | 89 | 0 | **55** | 3 (2 dlsym + 1 doctest) | 31 | — |
| `temper-thermal` | 48 | 46 | 0 | 2 (1 dlsym + 1 deliberately-unmirrored) | 0 | — |
| `temper-design-bundle` | 2 | 0 | 0 | 0 | 2 | — |
| `temper-rust-router-core` | 32 | 16 | **2** (in `tests/`, see below) | 0 | 9 (2 of which are the 2 unmirrored) | — |
| `temper-constraint-compiler` | 24 | 9 + 13 (integration, substance-mirrored) | 0 | 1 (dlsym) | 14 (13 substance-mirrored + 1 trivial scaffold) | — |
| `temper-quality-oracle` | 41 | 40 | 0 | 1 (dlsym) | 0 | — |
| `temper-io-types` | 55 | 48 | **7** | 0 | 0 | — |
| `temper-constraints` | 13 | 0 | **9** | 1 (dlsym) | 12 (9 of which are the 9 unmirrored; 3 plain) | — |
| `temper-rust-router` | 3 | 0 | **3** | 0 | 0 | — |
| `temper-pcl-ir` | 0 | 0 | 0 | 0 | 0 | — |
| `temper-orchestration` | 46 | 45 | 0 | 1 (dlsym) | 0 (native_only) | 51 (real, pyo3-bound, never compared) |
| **total** | **385** | **248** | **76** | **9** | (see note) | **51** |

**Correction to `temper-io-types`, found by counting mirror functions directly rather than trusting the campaign
file's own header claim.** `property_campaigns.rs`'s header states its second pass "mirrors those six files' own
`proptests` modules one-for-one," which reads as a claim of full coverage — but counting `pub(crate) fn` mirror
impls per kernel prefix against each module's native property count finds four kernels short by exactly one pair
each: `pc_*` (`placer_core::placer_compute`) has 12 impls against 14 native properties, `u_*` (`placer_core::units`)
has 15 against 17, `pf_*` (`pyfmt`) has 2 against 4, `sv_*` (`stackup_validator`) has 8 against 9 — 7 short overall
(`dsn`, `dsn_types`, and the separate `dsn_exporter.rs` campaign are each fully 1:1, confirmed the same way). Every
one of the 7 gaps is a special/boundary float value a **continuous** uniform sampler
(`SplitMix64::range(-1e6, 1e6)`, this crate's only sampling primitive) cannot land on by construction: signed zero
(`p22_py_max_signed_zero_first_wins`, `p27_py_min_signed_zero_first_wins`), an exact-zero input
(`p16_deg_to_rad_zero_is_zero`, `p17_rad_to_deg_zero_is_zero`), and float-formatting special cases
(`py_float_fmt_negative_zero`, `py_float_fmt_special_values_are_lowercase`, `py_float_str_special_values`). The
file's two genuinely `NaN`-dependent mirrors (`p20`/`p21`) already work around exactly this limitation by injecting
`f64::NAN` as a hardcoded literal rather than sampling for it — proving the author knew the sampler couldn't reach
special values, and applied the fix inconsistently rather than not at all. This is the same failure class as §7's
overlap-area/keepout findings, in continuous rather than discrete form, and is added to the ranked list below as
its own entry.

Note on the INTEGRATION-TARGET column: it is not summed because several of its entries are also
counted in UNMIRRORED PROPTEST (`temper-rust-router-core`'s 2, `temper-constraints`'s 9) — a
`tests/`-resident proptest with no mirror is both structurally unreachable *and* a genuine gap;
double-counting it in a grand total would overstate the tier's total test count while
under-communicating that a subset of INTEGRATION-TARGET is not just relocatable, it is missing.

MIRRORED + UNMIRRORED PROPTEST + STRUCTURALLY NATIVE + (INTEGRATION-TARGET not already counted as
UNMIRRORED) reconciles to 385 per crate; spot-checked for every row above.

## 5. The ranked list of genuinely-uncovered properties (actionable output)

This is what the next piece of work should be driven from — every property below has **no
execution anywhere on the wasm32 tier**, under any name, deterministic or randomized. Ranked by
count, descending:

### 1. `temper-geometry` — 55 properties, six modules, zero mirrors. By far the largest gap.

None of this crate's three campaign files (`property_campaigns.rs`: `kicad_transform`,
`convex_hull`, `connected_components`; `property_campaigns_2.rs`: `sdf`, `polygon.rs` top-level
fns, `overlap`, `projections`; `property_campaigns_3.rs`: `edt`, `pad_geometry`, `copper_reach`,
`obstacle_map_kernels`) mirrors any of the six modules below. Confirmed by grepping every
module's characteristic function name against all three campaign files: zero hits, with one
partial exception noted under `polygon::proptests`.

| module | count | native kernel | mirror status |
|---|---:|---|---|
| `smooth::proptests` | 15 | `smooth.rs` (smooth-max/min/abs/step, HPWL) | none |
| `units::proptests` | 7 | `units.rs` (mil/mm/inch conversions) | none |
| `creepage_check::properties` | 8 | `creepage_check.rs` | none |
| `grid_raster::proptests` | 8 | `grid_raster.rs` (cell merge, closest-component) | none |
| `via_clearance::properties` | 8 | `via_clearance.rs` | none |
| `polygon::proptests` | 9 | `polygon.rs` (area/perimeter/bbox, p1–p9) | none *by name*, but see note below |

**Note on `polygon::proptests`:** `property_campaigns_2.rs`'s Kernel 2 exercises the *same*
underlying functions (`polygon_area`, `triangle_area`, `polygon_perimeter`) with properties in a
similar spirit (translation/rotation invariance, sign-flip on reversal, fan-triangulation
additivity) — but its own doc comment (`property_campaigns_2.rs:24-42`) frames that coverage as
targeting `tests/proptest_equivalence.rs` (a different, integration-level proptest suite over the
same kernel), not this module's `p1`–`p9`. No 1:1 correspondence between campaign_2's `poly_*`
properties and `p1`–`p9` was verified; treating `polygon::proptests` as unmirrored is the
conservative, defensible reading, but a maintainer picking this up should check whether campaign_2
already incidentally covers enough of the same ground that only the gap between the two needs
closing, not all nine from scratch.

**`tests/proptest_equivalence.rs`'s 31 tests** are separately INTEGRATION-TARGET (unreachable by
the registry mechanism regardless of mirror status) — `property_campaigns_2.rs` mirrors *some* of
them explicitly (its own doc comment names five: `box_box_distance_symmetric`,
`polygon_area_translation_invariant`, an SDF union/intersection identity, and two more) but
states plainly it does not mirror all 31 ("several others ... are not in that file at all" — in
the other direction, some of campaign_2's properties are net-new, not ports). Not counted in the
55 above (those are the six *in-module* proptest modules only); flagged here because it is the
same crate and the same shape of gap.

### 2. `temper-constraints` — 9 properties, one file, zero mirrors

`packages/temper-placer/temper-constraints/tests/shared_ir_adapter_pbt.rs`: 9 `proptest!`-based
integration tests (`adjacent_preserves_every_field`, `aligned_preserves_every_field`,
`anchored_preserves_region_and_position`, `enclosing_preserves_every_field`,
`invalid_enum_strings_err_not_panic`, `keepout_always_errs_explicitly`,
`loop_area_preserves_every_field`, `onside_some_distance_is_preserved_none_becomes_infinity`,
`separated_preserves_every_field`). No `property_campaigns.rs` or any `SplitMix64` file exists
anywhere in this crate — there is no mirroring infrastructure here at all, unlike every other
crate in this list.

### 3. `temper-io-types` — 7 properties, four modules, an otherwise near-complete mirror

`placer_core::placer_compute::proptests::{p22_py_max_signed_zero_first_wins,
p27_py_min_signed_zero_first_wins}`, `placer_core::units::proptests::{p16_deg_to_rad_zero_is_zero,
p17_rad_to_deg_zero_is_zero}`, `pyfmt::proptests::{py_float_fmt_negative_zero,
py_float_fmt_special_values_are_lowercase}`, `stackup_validator::proptests::py_float_str_special_values`.
Every one of these is a special/boundary float value (signed zero, an exact-zero input, `±inf`/`NaN`
formatting) that `property_campaigns.rs`'s only sampling primitive — a continuous uniform
`SplitMix64::range` draw — cannot land on by construction (see §4's `temper-io-types` correction for
the count-by-count derivation). Unlike the other three crates in this list, this one **has** mirroring
infrastructure and used it for 48 of 55 properties; the 7 gaps are narrow and mechanically fixable
(hardcode the special value the same way the file's own `p20`/`p21` `NaN` mirrors already do), not a
missing campaign.

### 4. `temper-rust-router` — 3 properties, one module, zero mirrors

`proptests::{p1_f32s_round_trip, p2_output_length_input_div_4, p3_zero_bytes_decode_to_zero}`
(`lib.rs:56-102`, `f32`-array encode/decode round-trip properties). Same situation as
`temper-constraints`: no campaign file, no `SplitMix64`, exists anywhere in this crate.

### 5. `temper-rust-router-core` — 2 properties, one integration file, unmirrored (the crate's only gap)

`tests/test_loop_extractor.rs`'s `mod proptest_tests` (lines 11–118): 2 genuine `proptest!` tests,
`soundness_extracted_components_share_nets` and `uniqueness_same_input_same_output`. Grepped
`property_campaigns.rs` for both names and every plausible synonym (`loop_extractor::extract`,
`share_nets`) — no match. This crate otherwise has the *best* mirror coverage in the tier (§4:
16 of 18 in-module proptests mirrored, all 3 integration-target proptest files' worth of coverage
accounted for except this one) — these 2 are its only real gap, and they are additionally
INTEGRATION-TARGET, so even a mirror would not make them reachable directly; the mirror would need
to land as a new in-`src/` property (the pattern this crate's own `property_campaigns.rs` already
uses for its other integration-target proptests, `encoding.rs`'s 5 and `pruning.rs`'s 10).

**Total genuinely-uncovered: 76 properties across 5 crates** (55 + 9 + 7 + 3 + 2). This is the number
that should drive the next round of mirroring work — not 385, and not any single crate's raw
`native_only` count. Ranked by risk as well as count: `temper-geometry`'s 55 include
`creepage_check::properties` and `via_clearance::properties` — HV/LV electrical-isolation clearance
math, the most safety-relevant kernel in this list — so that module pair is the highest-priority
subset of the largest gap, not just the largest gap by raw number.

## 6. A second finding: registry defects that look like proptest gaps but aren't (temper-rust-router-core)

Two more of `temper-rust-router-core`'s native-only entries are neither MIRRORED nor genuinely
UNMIRRORED PROPTEST — they are **not proptests at all**, wrongly swept into the
`proptest-dev-dependency` exclusion because they share an ungated module with a genuine proptest.
This is the identical bug shape `docs/evidence/2026-08-11-native-only-classification-all-crates.md`
§6 found and reported (unfixed at the time) in this same crate's `encoding.rs`, and which was
subsequently fixed in commit `58d869ae3` (PR #977, confirmed present at this snapshot via
`--check`: `wasm test registry up to date`). **Two more instances of the same mechanism remain,
unfixed, today:**

- `loop_extractor::classify_py::tests` (7 native-only): `classify_py.rs:260` opens `mod tests`
  with 6 plain, deterministic `#[test]` fns (`classify_corpus_matches_cpython`,
  `classify_is_case_folding_invariant_in_category_and_confidence`,
  `classify_malformed_capacitance_raises`, `parse_capacitance_corpus_matches_cpython`,
  `parse_capacitance_overflow_saturates_to_inf_like_cpython_float`,
  `parse_capacitance_raises_like_cpython_on_malformed`) plus one genuine `proptest::proptest! {
  ... }` block at line 379 (`parse_applies_unit_multiplier`) — all seven in the same, ungated
  `mod tests`. `discover_eligible()`'s dependency scan attributes the whole module's exclusion to
  the one proptest use; the 6 portable tests are collateral damage, exactly as `encoding.rs`'s
  `mod proptests` (unfixed) poisoned its parent before #977. The genuine proptest,
  `parse_applies_unit_multiplier`, **is** mirrored (`cls_unit_multiplier_impl`,
  `property_campaigns.rs:1211`, 150 seeds) — that part of the module is correctly covered in
  substance; the other 6 are not covered by anything and don't need to be, they need to be
  *reachable*.
- `pruning::property_tests` (11 native-only): `pruning.rs:437` opens `mod property_tests` with 10
  `proptest!` blocks (all 10 mirrored, `pr_*_impl` in `property_campaigns.rs`, verified name for
  name) plus one plain `#[test] fn tight_margin_excludes_detour_edge` at line 742, in the same
  ungated module. The 10 proptests are correctly excluded and correctly mirrored; the 1 plain test
  is collateral damage of the same shape.

**This is not a coverage gap** (no property goes unchecked — `tight_margin_excludes_detour_edge`
runs natively, and the six `classify_py` tests run natively) — it is a **registry defect**: 7
tests that could register cleanly and run on the tier today, at zero mirroring cost, if the
proptest blocks sharing their module were moved into their own `#[cfg(test)] mod proptests` (the
one-line fix `58d869ae3` already demonstrated for `encoding.rs` in this same crate). Reported here,
not fixed, per this task's documentation-only scope; the fix is mechanical and the precedent for it
already exists in this crate's own history.

## 7. Uniform-sampling blind spot: checked, found twice, both already fixed with proof

The task asked whether any mirror exercises only a trivial branch — a mirror that always passes is
worse than no mirror, because it reports green forever while proving nothing. This repo has two
documented, in-source instances of exactly this trap, both already caught (by mutation testing,
not by inspection) and fixed. Both are cited with file:line, not summarized from memory:

**`temper-geometry`'s keepout property**
(`property_campaigns_2.rs:924`, `pj_keepout_feasible_and_idempotent_impl`, mirroring
`projections::project_outside_keepout` — net-new coverage, not one of the 55 gap properties
above). The property generator's own comment (`property_campaigns_2.rs:934-942`) states the trap
directly: drawing the query point from an *independent* full-board range "would put the query
point inside the (typically much smaller) expanded keepout only rarely, so almost every generated
case would take the early 'already outside' return and never exercise the actual candidate-edge
projection logic this property exists to check." The fix: center the sampling window on the
keepout rectangle itself, "sized to extend a bit past the half-size-expanded rectangle on every
side," guaranteeing "a healthy mix of already-outside, boundary-straddling, and strictly-inside
cases." This reads as reasoned-through-in-advance, not caught-after-the-fact by a failing mutation
test — no mutation-testing citation accompanies this one specifically.

**`temper-thermal`'s overlap-area property**
(`property_campaigns.rs:981-991`, `gm_overlap_area_non_negative_impl`, mirroring the *already
covered* `prop_overlap_area_non_negative`, one of the crate's 46 MIRRORED properties). Here the
comment states the trap was caught **empirically, by mutation testing, not by inspection**: "the
board-scale original proptest strategy (`pos_f32() = 0..1000`) relies on running hundreds of
proptest cases per CI invocation to hit the overlapping branch often enough; this campaign runs a
fixed, much smaller seed set, so the overlap property specifically needs a generator biased toward
the branch it is checking — confirmed empirically: **with the wide range, 24 seeds produced zero
overlapping pairs and a deliberately broken `overlap_area_mm2 -= ox * oy` mutation went undetected
by this property**." The fix: narrow the position domain to `[0, 80)` against footprint
half-widths up to 25mm, so a meaningful fraction of drawn pairs actually overlap.

**A related, more subtle case, found in the same sweep: a deliberate non-mirror to avoid a
vacuous pass.** `temper-thermal`'s `uniqueness_distance_uses_pow_not_sqrt_proptest`
(`thermal_potential.rs:2539`) is the one property in an otherwise-fully-mirrored module
deliberately left unmirrored. `property_campaigns.rs:1548-1552` states why: the property exists
"to detect whether `pow(x, 0.5)` discriminates from `sqrt(x)` on the host libm, and on wasm32 that
fold is exact (measured, `docs/evidence/2026-08-06-wasm32-float-divergence.md`) so the property
would pass vacuously there — it is *about* the host, not a property of the kernel." This is the
same failure mode in a different guise (a mirror that always passes because the platform it runs
on cannot exhibit the divergence being tested) — correctly identified and correctly left
unmirrored rather than mirrored-and-vacuous. This is exactly the class of judgment R27's own
carve-out language ("host-libm-sensitive assertions") anticipates, applied here to a mirror rather
than to the original proptest.

**What this does not establish:** this is not an exhaustive audit of every one of the 248 MIRRORED
properties' sampling domains for the same trap — it is a report of what turned up while reading
each campaign file's own doc comments for mirror claims (§3, Method, above), plus one direct
count-by-count check (`temper-io-types`, §4's correction) that found a third instance of the same
underlying failure by counting rather than by doc-comment reading alone — a hint that a mirror's own
header claiming "one-for-one" coverage is not sufficient evidence that it is. Three instances found,
two already fixed (by mutation testing) and one found here (by counting, not yet fixed), is evidence
the pattern is *recognized but not systematically checked for* in this codebase (the two fixes read
as informed by the same lesson, and the crate authors' own commit messages for `temper-orchestration`
explicitly invoke it: "Deliberately avoided the uniform-sampling trap that has bitten this tier
before," commit `7201c4205` — yet `temper-io-types`'s gap sat undetected through a header comment
claiming full coverage). It is not evidence that no fourth, undetected instance exists among
the other 241 properties this document did not independently re-derive sampling-domain reasoning
for. **Flagged as an open risk**, not resolved: the cheap, general check available to close it
is not source reading (this document's method) but running each campaign against a deliberately
broken kernel and confirming red — the same mutation-testing standard the `overlap_area` fix's own
citation used, not yet applied tier-wide.

## 8. What this does and does not license

**Does:** establish that `native_only` (385, live at this snapshot, twelve crates) overstates the
tier's genuine coverage gap by roughly 5x. The real gap, MIRRORED-excluded and
registry-defect-excluded, is **76 properties across 5 crates** (§5), plus a separate, small,
mechanical registry-fix opportunity (7 tests, §6) that costs no new mirroring work.

**Does not:** license removing any crate's native `cargo test` step from GitHub Actions. R24's
gate is unaffected by this document — a MIRRORED proptest's *original*, randomized, unseeded form
still needs to run somewhere, because (§2, "R27 and the self-selection claim") a mirror is
substantively equivalent, not the same guarantee, and per
`docs/evidence/2026-08-11-u6-sustained-agreement-batch-1.md` §4 / batch-2 §4, most of these twelve
crates have no PR-gating native step to remove today regardless.

**Does not:** claim the 76-property ranked list or the 248-property MIRRORED list is exhaustive of
every possible registry-generator defect in this tier — `discover_eligible()`'s module-granularity
exclusion has now produced three confirmed instances of the same "plain test poisoned by an
ungated proptest sibling" bug in one crate alone (`encoding.rs`, fixed; `classify_py.rs` and
`pruning.rs`, found here, unfixed); a targeted sweep for this specific mechanism across the other
eleven crates was not performed and would be cheap, mechanical follow-up work. Nor is the
248-property MIRRORED count itself guaranteed complete — it was derived by reading each campaign
file's own claims plus, for `temper-io-types` only, an independent function-count check that found
that file's own claim wrong; the other eleven crates' MIRRORED counts were not re-verified by the
same count-by-count method, only by name/doc-comment matching.

**Does not:** resolve the uniform-sampling open risk (§7) beyond reporting what was found by
reading doc comments and one count-by-count check. A mutation-testing sweep of all 248 MIRRORED
properties' sampling domains is not performed here.

**Does not:** touch `.github/workflows/*`, `tools/wasm/wasm_tier_topology.json`, or
`packages/temper-orchestration/**` — documentation and read-only classification only, per this
task's scope boundary. No production code, workflow, or topology file was modified.

## 9. Reproduction

```bash
# Live census, any crate (module-level registered/excluded, no build required):
/usr/bin/python3 scripts/gen_wasm_test_registry.py --crate <name> --census

# Registry drift check (confirms #977's encoding.rs fix is still present):
/usr/bin/python3 scripts/gen_wasm_test_registry.py --crate temper-rust-router-core --check

# native_test_args per crate, including the --lib outlier:
grep -n '"crate"\|native_test_args' tools/wasm/wasm_tier_topology.json

# Confirm a specific mirror exists and what it says about its own sampling domain:
grep -n "Mirrors proptest property" packages/<crate>/src/property_campaigns*.rs

# The two uniform-sampling fixes, in place:
sed -n '924,960p' packages/temper-geometry/src/property_campaigns_2.rs
sed -n '955,1015p' packages/temper-thermal/src/property_campaigns.rs

# The orchestration mirror commit, full rationale:
git log -1 --format=%B 7201c4205d9b7ddb6b5cbc42eda1f43c9e0f43fc

# The router-core fix precedent for the classify_py.rs / pruning.rs finding (§6):
git log -1 --format=%B 58d869ae3
```

## 10. Related

- `tools/wasm/r19_compare.py` — the exact-name join (`run_comparison`, lines 88-137) this
  document's central correction is about; read, not modified.
- `scripts/gen_wasm_test_registry.py` — `discover_eligible()`, `--census`, `--check`; read as a
  library and via CLI, not modified.
- `tools/wasm/wasm_tier_topology.json` — `native_test_args` per crate, source of the `--lib`
  finding; read, not modified.
- `docs/evidence/2026-08-11-native-only-classification-all-crates.md` — the nine-crate mechanism
  classification (why a name is absent) this document extends (does a mirror exist) to all twelve
  crates and re-verifies live.
- `docs/evidence/2026-08-11-u6-orchestration-sustained-agreement.md`,
  `docs/evidence/2026-08-11-u6-sustained-agreement-batch-1.md`,
  `docs/evidence/2026-08-11-u6-sustained-agreement-batch-2.md` — the three source documents whose
  `native_only` figures this document corrects the reading of; their own numbers are not disputed.
- `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` — R24, R27, D12-D14.
- `docs/plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md` §U6 — the R19 sustained-agreement bar
  and its own explicit native-only/wasm32-only carve-out from the agreement rate.
- `docs/evidence/2026-08-06-wasm32-float-divergence.md` — the measured pow/sqrt fold-equality on
  wasm32 that `temper-thermal`'s deliberate non-mirror (§7) cites as its own justification.
- Commit `7201c4205` (PR #997) — `temper-orchestration`'s 45-proptest mirror, this document's
  first live-verified example that mirroring does not move `native_only`.
- Commit `58d869ae3` (PR #977) — `temper-rust-router-core`'s `encoding.rs` fix, the precedent this
  document's §6 finding (unfixed in `classify_py.rs` and `pruning.rs`) would follow.
