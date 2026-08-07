# Phase 1 — family-coverage gap closure (emc, erc, placement)

**Date:** 2026-08-07
**Branch:** `wasm/p1-family-tests`
**Base commit:** `00ec5f94a535ff86b4042748f7b036c139b3cac2` (`origin/main`)

## Summary

Closed the family-coverage gap for `emc`, `erc`, and `placement` in the
wasm32 test registry by adding 35 new unit tests across 8 rule modules and
registering them via `gen_wasm_test_registry.py`. No rule behavior was
changed; the existing checks were already wasm-portable.

## Per-Family Before/After

| Family | Before (registry) | After (registry) | Delta |
|--------|--------------------|-------------------|-------|
| emc    | 0                  | 14                | +14   |
| erc    | 0                  | 9                 | +9    |
| placement | 0               | 12                | +12   |
| drc    | 1                  | 1                 | —     |
| routing | 2                 | 2                 | —     |
| **Total** | **112**          | **147**           | **+35** |

## New Tests

### emc (14 tests)

**`rules::emc::ground_plane`** (5 tests):
- `ground_plane_empty_board_no_violations` — empty board → 0 violations
- `ground_plane_noisy_in_ground_zone_no_violation` — noisy component with matching ground zone → 0 violations
- `ground_plane_noisy_not_in_ground_zone_violation` — noisy component without matching ground zone → 1 violation (EMC_GND_001)
- `ground_plane_non_noisy_no_violation` — non-noisy ("Signal") component → 0 violations
- `ground_plane_multiple_zones_noisy_in_one` — noisy in one of two zones → 0 violations

**`rules::emc::loop_area`** (4 tests):
- `loop_area_empty_board_no_violations` — empty board, no nets → 0 violations
- `loop_area_under_threshold_no_violations` — loop area 50 mm² < 200 mm² max → 0 violations
- `loop_area_over_threshold_violation` — loop area 500 mm² > 200 mm² max → 1 violation (EMC_LPA_001)
- `loop_area_no_max_no_violations` — max_area_mm2 = None → 0 violations regardless of area

**`rules::emc::noise_coupling`** (5 tests):
- `noise_coupling_empty_board_no_violations` — empty board → 0 violations
- `noise_coupling_far_apart_no_violation` — noisy+sensitive 50 mm apart, clearance 5 mm → 0 violations
- `noise_coupling_close_pair_violation` — noisy+sensitive 2 mm apart → 1 violation (EMC_NSE_001)
- `noise_coupling_non_noisy_sensitive_no_violation` — both components "Signal" → 0 violations
- `noise_coupling_at_threshold_exact_violation` — touching components → violation

### erc (9 tests)

**`rules::erc::floating_pins`** (5 tests):
- `floating_pins_empty_board_no_violations` — empty board → 0 violations
- `floating_pins_connected_component_no_violation` — component in a net → 0 violations
- `floating_pins_unconnected_component_violation` — component with no net → 1 violation (ERC_FLT_001)
- `floating_pins_all_components_connected_no_violations` — 3 components all in nets → 0 violations
- `floating_pins_mixed_connected_and_floating` — 1 connected + 2 floating → 2 violations

**`rules::erc::net_connectivity`** (2 tests, placeholder):
- `net_connectivity_empty_board_no_violations` — exercises placeholder check (always returns empty)
- `net_connectivity_placeholder_compiles_and_runs` — verifies DrcRule trait contract (name, category, returns empty)

**`rules::erc::power_domain`** (2 tests, placeholder):
- `power_domain_empty_board_no_violations` — exercises placeholder check (always returns empty)
- `power_domain_placeholder_compiles_and_runs` — verifies DrcRule trait contract (name, category, description)

### placement (12 tests)

**`rules::placement::thermal_via_count`** (5 tests):
- `thermal_via_count_empty_vias_no_violations` — no vias → early-return 0 violations
- `thermal_via_count_no_power_component_no_violation` — power_dissipation_w = None → skipped
- `thermal_via_count_insufficient_vias_violation` — 10 W needs 7 vias, has 1 → 1 violation (DRC_THV_001)
- `thermal_via_count_sufficient_vias_no_violation` — 1 W needs 1 via, has 1 → 0 violations
- `thermal_via_count_via_outside_footprint_not_counted` — via outside bbox → not counted → violation

**`rules::placement::wave_solder_keepout`** (7 tests):
- `wave_solder_empty_board_no_violations` — empty board → 0 violations
- `wave_solder_no_bottom_smd_no_violations` — top-side SMD + THT → 0 violations
- `wave_solder_bottom_smd_too_close_to_tht_violation` — bottom SMD 2 mm from THT < 5 mm → 1 violation (DFM_WSK_001)
- `wave_solder_bottom_smd_far_enough_no_violation` — bottom SMD 20 mm from THT > 5 mm → 0 violations
- `rect_edge_distance_overlapping_zero` — overlapping rects → distance 0
- `rect_edge_distance_separated` — rects 5 mm apart → distance 5 mm
- `expand_rect_adds_margin` — rect expanded by 2 mm → correct bounds

## Module Visibility Changes

The generator widened `mod` to `pub(crate) mod` in:
- `rules/emc/mod.rs` — `ground_plane`, `loop_area`, `noise_coupling`
- `rules/erc/mod.rs` — `floating_pins`, `net_connectivity`, `power_domain`
- `placement/mod.rs` — already `pub mod`

The `wave_solder_keepout::rect_edge_distance` helper was also widened from
`fn` to `pub(crate) fn` so the test module can call it directly.

## Wasm Portability

All 35 new tests compile and pass under `wasm32-unknown-unknown`. No pyo3
types, no Python objects, no `std::fs`, no threads. The `NetConnectivityCheck`
and `PowerDomainCheck` are placeholders (always return empty) but their tests
still count as wasm-tier coverage — they verify the DrcRule trait contract
compiles and links.

## Family Map

`tools/wasm/gen_family_map.py` needed no changes. The existing
`FAMILY_FROM_PATH` dict already maps `emc` → emc, `erc` → erc,
`placement` → placement, and the new tests live under `rules::{family}::`
paths that match.

## Registry Growth

| Metric | Before | After |
|--------|--------|-------|
| Total registered tests | 112 | 147 |
| Modules with tests | 17 | 25 |
| Rule families covered | 2 (drc, routing) | 5 (+emc, erc, placement) |

## Verification Transcript

```
# Base assertion
$ scripts/assert-base.sh origin/main
ASSERT-BASE OK: HEAD == origin/main (00ec5f94a)

# Native tests (--no-default-features)
$ cargo test --no-default-features --manifest-path packages/temper-drc-rs/Cargo.toml
test result: ok. 147 passed; 0 failed; 0 ignored

# Native check (default features = python)
$ cargo check --release --manifest-path packages/temper-drc-rs/Cargo.toml
Finished `release` profile [optimized] target(s) in 9.27s

# Clippy (--no-default-features, lib only)
$ cargo clippy --no-default-features --manifest-path packages/temper-drc-rs/Cargo.toml --lib -- -D warnings
Finished (0 warnings)

# Clippy (default features, lib only)
$ cargo clippy --manifest-path packages/temper-drc-rs/Cargo.toml --lib -- -D warnings
Finished (0 warnings)

# Wasm32 build
$ cargo build --release --target wasm32-unknown-unknown --no-default-features \
    --manifest-path packages/temper-wasm-test-runner/Cargo.toml
Finished `release` profile [optimized] target(s) in 7.20s

# Wasm32 test run
$ node tools/wasm/run_wasm_tests.mjs \
    target-shared/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm \
    --json /tmp/wasm_after.json
  passed            143
  failed            0
  expected-fail     4  (native-only properties; see manifest)
  unexpected-pass   0

# Family map
$ python3 tools/wasm/gen_family_map.py /tmp/wasm_after.json --out /tmp/fam_after.json
Families: {drc: 1, emc: 14, erc: 9, placement: 12, routing: 2}

# Registry consistency check
$ python3 scripts/gen_wasm_test_registry.py --check
wasm test registry up to date: 147 tests across 25 modules
```
