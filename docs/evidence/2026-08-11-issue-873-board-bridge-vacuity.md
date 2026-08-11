<!-- provenance: commit=12b9e2055aa3bf44db25da64e9152f4c64a427a6 dirty=false -->

# Issue #873 — `board_py_bridge` traces/vias/zones: stale, and structurally inapplicable to the wasm-tier corpus

**Date:** 2026-08-11
**Commit:** `12b9e2055aa3bf44db25da64e9152f4c64a427a6` (`origin/main`)
**Board:** `pcb/temper.kicad_pcb` sha256 `6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64`
**Issue:** [#873](https://github.com/BennetLeff/temper/issues/873) — "wasm-tier U4: `board_py_bridge` doesn't populate traces/vias/zones — routing rules are no-ops in the measured full-board pass," filed 2026-08-07.

## Bottom line

**The issue is stale, and the mechanism it describes cannot exist in the wasm-tier's 2,788 registered tests.** Two independent facts, both verified empirically in this worktree, not read off documentation:

1. **The specific pipeline #873 named — the R2 `r2_full_board_pass` cost-model benchmark — is fixed.** `board_py_bridge.rs` fully supports `traces`/`vias`/`zones` today, and `tools/wasm/r2_serialize_board.py` (the producer #873 actually blamed, per its own since-added docstring) now populates all three from the committed board. Re-running the exact pipeline against `pcb/temper.kicad_pcb` today yields 2,290 real trace segments, 48 real vias, 94 real zones, and running the routing family against that data produces **34 real violations**, not the 0 the issue describes.
2. **The wasm-tier's 2,788 registered tests never went through this pipeline at all, and structurally cannot.** `board_py_bridge` is gated behind `#[cfg(feature = "python")]` (pyo3), and every one of the six wasm tiers in `tools/wasm/wasm_tier_topology.json` builds with `--no-default-features` on **both** arms (wasm32 build and the native `cargo test` arm it's compared against). `board_py_bridge.rs` is not present in any binary the tier ever runs or compares against. Every registered test builds its own `BoardState` fixture directly in Rust.

**Vacuous tests attributable to issue #873: 0 of 2,788.** Not "closed to zero by a fix" — the failure mode the issue describes (an external Python producer handing the rule engine an empty board) has no code path into the wasm-tier corpus to be vacuous through.

A distinct, smaller finding surfaced while enumerating rule coverage (§3): 9 of the 14 rule kernels that read `traces`/`vias`/`zones` have no rule-specific test module in the wasm tier at all — their only tier coverage is one shared non-empty fixture in a crate-wide anti-vacuity guard. That is a coverage-depth gap, not a vacuity bug, and is reported honestly below rather than folded into the headline number.

## 1. Is #873 still true? (measured, not read)

### 1a. `board_py_bridge.rs` already supports the K1 schema's routing keys

Read `packages/temper-drc-rs/src/board_py_bridge.rs` directly: `extract_trace_segment`, `extract_via`, `extract_copper_zone`, `parse_traces_from_dict`, `parse_zones_from_dict` are all present, and `build_board_state` (lines 719–733) calls them and assigns the results into `BoardState.traces`/`.vias`/`.zones` (lines 735–746). This is not new: the crate's own dedicated regression suite is `packages/temper-placer/tests/validation/test_board_py_bridge_routing_data.py`, whose module docstring states plainly: *"`build_board_state`... already had full support for the K1 schema's optional `traces`/`vias`/`zones` keys — the gap... was entirely in the Python-side producer."*

Ran it:

```
$ uv run --no-sync python3 -m pytest packages/temper-placer/tests/validation/test_board_py_bridge_routing_data.py -v
8 passed in 0.87s
```

All 8 pass, including the anti-vacuity case (`test_n_traces_yields_n_traces_in_board_state` etc. — N in, N out, not just "the field exists").

### 1b. The producer #873 actually named (`tools/wasm/r2_serialize_board.py`) populates them

`build_board_dict` (the function `r2_full_board_pass`'s input comes from) sets:

```python
"traces": _traces_from_parsed(parsed),
"vias": _vias_from_parsed(parsed),
"zones": zones,   # _zones_from_placement(...) or _zones_from_parsed(...)
```

Ran the crate's producer-level regression suite:

```
$ uv run --no-sync python3 -m pytest packages/temper-placer/tests/scripts/test_r2_serialize_board.py -v
27 passed in 1.31s
```

Including, against the real committed board (not a synthetic fixture):

```python
assert total_segments == 2290
assert len(board_dict_1["vias"]) == 48
assert len(board_dict_1["zones"]) == 96
```

### 1c. Ran the actual pipeline end-to-end today, independent of the pre-existing test suite

```
$ uv run --no-sync python3 tools/wasm/r2_serialize_board.py --output board.json
Parsing pcb/temper.kicad_pcb ...
  components: 169  nets: 110
  pads: 527
  zones (placement): 94
Wrote BoardState JSON → board.json (406,068 bytes)
Input pcb/temper.kicad_pcb sha256:  6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64
```

```
$ python3 -c "import json; d=json.load(open('board.json')); \
  print(len(d['traces']), sum(len(t['segments']) for t in d['traces']), len(d['vias']), len(d['zones']))"
54 2290 48 94
```

(94 vs. the pytest suite's 96 zones is the documented `zone_source="placement"` vs. `"committed"` difference — both non-empty, both real, not the 0 issue #873 describes.)

Then ran the actual native benchmark binary against that board:

```
$ cargo run --release --no-default-features --manifest-path packages/temper-drc-rs/Cargo.toml \
    --example r2_full_board_pass -- board.json --summary --family routing
{"family":"routing", ...,
 "rules_run":["routing_parallel_run","routing_stitching_via_density","routing_copper_pullback",
   "routing_isolation_barrier","routing_tht_thermal_relief","routing_power_pad_teardrop",
   "routing_partial_discharge","routing_pad_entry_width","routing_split_plane_crossing",
   "routing_isolation_slot"],
 "violations_error":34,"violations_warning":0,"wall_ns":166464}
```

**34 real routing-family violations against the real board.** The specific claim in #873 — "routing-family rules in the measured full-board pass execute against an empty routing surface and return empty results" — is false today, measured directly, not inferred from a docstring.

The fix landed in commit `04d3d275` (`feat(wasm-tier): serve temper-thermal from a deployed Worker...`, PR #943), which — despite its title being about a different tier addition — is the only commit in this branch's history touching `board_py_bridge.rs`, `tools/wasm/r2_serialize_board.py`, and both of the routing-data test files cited above; its own diff and docstrings self-identify as the #873 close (`"Issue #873: those two scripts... never populated the K1 schema's optional traces/vias/zones keys"`). `04d3d275` is confirmed on this branch's `git log` and is an ancestor of the current worktree HEAD.

## 2. Which rules read traces/vias/zones, and can the wasm tier even reach them?

`grep`-ing `packages/temper-drc-rs/src/rules/` for `board.traces`/`.vias`/`.zones` field reads finds **14 rule kernels**:

| Rule (`DrcRule::name()`) | File | Category |
|---|---|---|
| `drc_trace_clearance` | `rules/drc/trace_clearance.rs` | drc |
| `drc_via_spacing` | `rules/drc/via_spacing.rs` | drc |
| `drc_zone_containment` | `rules/drc/zone_containment.rs` | drc |
| `emc_ground_plane` | `rules/emc/ground_plane.rs` | emc |
| `placement_thermal_via_count` | `rules/placement/thermal_via_count.rs` | placement |
| `routing_copper_pullback` | `rules/routing/copper_pullback.rs` | drc |
| `routing_isolation_barrier` | `rules/routing/isolation_barrier.rs` | safety |
| `routing_isolation_slot` | `rules/routing/isolation_slot.rs` | safety |
| `routing_pad_entry_width` | `rules/routing/pad_entry_width.rs` | dfm |
| `routing_parallel_run` | `rules/routing/parallel_run.rs` | emc |
| `routing_partial_discharge` | `rules/routing/partial_discharge.rs` | safety |
| `routing_power_pad_teardrop` | `rules/routing/power_pad_teardrop.rs` | dfm |
| `routing_split_plane_crossing` | `rules/routing/split_plane_crossing.rs` | emc |
| `routing_stitching_via_density` | `rules/routing/stitching_via_density.rs` | emc |

(`rules/oracle/mod.rs` also reads `board.traces` — it is a proptest differential-testing oracle, not a registered rule, and out of scope here.)

**None of these 14 can be fed by `board_py_bridge` in the wasm tier, structurally:**

- `board_py_bridge` (`packages/temper-drc-rs/src/board_py_bridge.rs`) is declared `#[cfg(feature = "python")]` in `lib.rs:12`. The `python` feature pulls in `pyo3` and is **not** a default feature.
- Every tier in `tools/wasm/wasm_tier_topology.json` builds its wasm32 module and its native comparison arm (`native_test_args`) with `--no-default-features`. This is true for all six tiers (`temper-drc-rs`, `temper-geometry`, `temper-thermal`, `temper-design-bundle`, `temper-rust-router-core`, `temper-constraint-compiler`), verified by reading the topology file directly.
- `wasm_test_registry.rs`, the module that enumerates every wasm32-callable test (`WASM_TESTS` consts pulled from `crate::rules::drc::*::tests`, `crate::rules::routing::*::tests`, etc.), is gated on `#[cfg(feature = "wasm-registry")]`, never on `python`.

So `board_py_bridge.rs` is not merely "empty on this path" — **it is not compiled into any binary either arm of the R19 agreement check ever runs.** The class of bug #873 describes (a Python bridge silently handing the rule engine an empty board) has no code path into the 2,788-test corpus to occur through.

## 3. Are the wasm-tier tests for these 14 rules vacuous? (the crux — quantified)

Every wasm32-registered test constructs its own `BoardState` in Rust — confirmed by `grep`: zero references to `board_py_bridge`/`serialize_board_state` anywhere under `rules/`, and 16 rule-test files construct `traces: vec![...]` / `vias: vec![...]` / `zones: vec![...]` fixtures directly.

**Dedicated per-rule test coverage in the wasm tier**, from `tools/wasm/test_family_map.json` (1,719 tests, current and accurate — confirmed `sum(family_counts.values()) == 1719`) cross-referenced against `wasm_test_registry.rs`'s module list:

| Rule | Dedicated wasm-tier test module? | Test count |
|---|---:|---:|
| `routing_isolation_barrier` | yes (`rules::routing::isolation_barrier::tests`) | 16 |
| `drc_zone_containment` | yes (`rules::drc::zone_containment::tests`) | 5 |
| `emc_ground_plane` | yes (`rules::emc::ground_plane::tests`) | 6 |
| `placement_thermal_via_count` | yes (`rules::placement::thermal_via_count::tests`) | 5 |
| `routing_power_pad_teardrop` | partial — 2 tests, but they exercise only the private `distance_to_rect_edge` geometry helper, not `PowerPadTeardropCheck::check()` end-to-end | 2 |
| `drc_trace_clearance` | **no** | 0 |
| `drc_via_spacing` | **no** | 0 |
| `routing_copper_pullback` | **no** | 0 |
| `routing_isolation_slot` | **no** | 0 |
| `routing_pad_entry_width` | **no** | 0 |
| `routing_parallel_run` | **no** | 0 |
| `routing_partial_discharge` | **no** | 0 |
| `routing_split_plane_crossing` | **no** | 0 |
| `routing_stitching_via_density` | **no** | 0 |

(Verified by `grep -n 'cfg_attr(test\|#\[test\]\|mod tests'` against each of the 9 "no" files: zero matches in every one. `wasm_test_registry.rs` independently confirms — its module list names exactly `isolation_barrier` and `power_pad_teardrop` as the only routing-family test modules registered.)

**The 9 zero-dedicated-test rules are not vacuous, because of one crate-wide guard**, `rules::integration_tests::no_registered_rule_is_vacuous_across_varied_fixtures` (added 2026-08-08, itself a wasm-registered test, `integration` family). It builds one hand-authored, non-empty fixture per registered rule — e.g. `fixture_trace_clearance()` builds two real `TraceSegment`s 0.05mm apart on different nets, `fixture_stitching_via_density()` builds two real `Via`s inside a real `CopperZone` — runs the *entire* registry against every fixture, and asserts every currently-registered rule name appears in the violations output at least once. A rule that returns `vec![]` unconditionally (the exact `PowerDomainCheck`/`NetConnectivityCheck` defect class this guard was built to catch, per `docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md`) fails this test.

Ran it directly:

```
$ cargo test --lib rules::integration_tests
running 3 tests
test rules::integration_tests::empty_board_zero_violations ... ok
test rules::integration_tests::incremental_check_equals_full_check_for_same_region ... ok
test rules::integration_tests::no_registered_rule_is_vacuous_across_varied_fixtures ... ok
test result: ok. 3 passed; 0 failed
```

Passes today, for all 14 rules in §2 (all 14 have a `fixture_*` entry in the guard's fixture list, confirmed by reading `rules/mod.rs` lines 922–950).

**So: 0 of the 2,788 wasm-tier tests assert "no violations" against permanently-empty routing data while claiming to test a routing rule.** Every rule that reads `traces`/`vias`/`zones` is proven, by a real (if minimal) fixture, to fire at least once. What's honestly thinner is *depth*, not *vacuity*: 9 of 14 rules have exactly one shared positive case and no rule-specific edge cases (no boundary values, no true-negative "should not fire on this real-looking board" case, no multi-scenario matrix) in the wasm tier — versus `routing_isolation_barrier`'s 16 dedicated tests covering layer scoping, polyline vs. straight-line barriers, zero-clearance edge cases, and more.

## 4. Fix status

**No fix was needed for #873 as filed.** The producer-side gap it described was already closed by commit `04d3d275`, verified in §1 with fresh test runs and a fresh end-to-end pipeline execution against the real board, not by reading that commit's own claims.

**No fix was made to the coverage-depth finding in §3**, per this task's scope (prefer investigation over sweeping changes; report precisely what's needed rather than force it). What it would take, if someone chooses to close that gap: 9 small `#[cfg_attr(test, test)]` modules (one per rule in the "no" column of §3's table), each adding a handful of rule-specific cases beyond the single shared fixture — e.g. a true-negative case (compliant board, 0 violations) and a boundary case (exactly-at-threshold) per rule, mirroring the shape `routing_isolation_barrier`'s 16-test module already has. This is additive test-writing with no production-code change, independently doable per rule, and does not block anything else in the wasm tier today since no test is currently wrong or misleading.

## 5. The tier's honest coverage claim after this analysis

- **2,788 wasm-tier tests, 0 vacuous with respect to issue #873.** The bridge-vacuity failure mode has no code path into this corpus (§2), and the crate's own anti-vacuity guard independently proves every registered rule — including all 14 that read `traces`/`vias`/`zones` — fires on real, non-empty, self-constructed fixture data (§3), verified by re-running that guard today.
- **The R19 agreement rate of 1.0 over 2,788 tests continues to mean what it claims to mean** for these 14 rules specifically: wasm32 and native agree on rule behavior against real routing geometry, not against an empty board that both sides trivially agree is empty.
- **Depth caveat, stated plainly and not hidden in the headline:** for 9 of those 14 rules, "the wasm tier tests this rule" currently means "one shared, non-empty, violation-triggering fixture, run once" — not a dedicated edge-case suite. That is a legitimate place to invest test-writing effort next; it is not a defect in what's already there.
- **Issue #873 should be closed** as stale — the bridge and its producer already carry real routing geometry, verified today against the live board, and the wasm-tier corpus the issue's title invokes was never structurally able to be affected by the gap it described.
