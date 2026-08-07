# Phase 1 U4 — Coverage + non-vacuity (R7/R8), measured

**Date:** 2026-08-07
**Commit:** `14979d633` (origin/main at measurement time)
**Map:** `tools/wasm/gen_family_map.py` →
`docs/evidence/data/family_map_14979d63.json`
**Runner results:** `tools/wasm/run_wasm_tests.mjs <runner.wasm> --json`

## Per-family coverage (R7), from the registered suite

| Rule family | Tests in registry | Direct tests |
|---|---|---|
| `drc` | `rules::drc::clearance::clearance_at_exact_threshold_flagged` | 1 |
| `routing` | `rules::routing::power_pad_teardrop::test_distance_to_rect_edge_{inside,outside}` | 2 |
| `emc` | — | **0** |
| `erc` | — | **0** |
| `safety` | — | **0** |
| `placement` | — | **0** |
| rules-integration | `empty_board_zero_violations`, `incremental_check_equals_full_check_for_same_region` | 2 |
| infra (board/dfm/pymath/pyfmt/types) | 8 + 38 + 7 + 1 + 36 | 90 |

Total: 95 registered, 3 direct family tests, 2 integration, 90 infra.

## The finding this surfaces

**The tier's first payload (D9 — the existing portable suite) exercises
the six R5 families thinly.** Only 3 registered tests are direct family
rules; four families (`emc`, `erc`, `safety`, `placement`) have **zero**
registered tests. The Phase-0 R1 six-family exact-match was demonstrated
with *representative* invocations of the registry (notably
`empty_board_zero_violations`), which are integration tests, not per-family
rules.

This is exactly the gap U2's portable-surface census predicted:
`validation.rs`'s kernels (tht_hole_collisions, trace_length,
min_hv_lv_trace_clearance, geometric_validate, ...) are `#[cfg(feature =
"python")]`-gated out of the portable build, and no `emc`/`erc`/`safety`/
`placement` rule has been migrated into a non-python-gated module. R7
coverage as reported here is therefore **not a coverage claim** — it is the
baseline the tier starts from, and it says the family surface is unbuilt.

## Non-vacuity (R8) — what is demonstrated today

The tier CAN fail loudly. Demonstrated failing cases (trap on wasm32, caught
by the manifest):

| Test | Class | What it proves |
|---|---|---|
| `pymath::host_libm_symbols_actually_resolve` | `no-dynamic-loader` | dlsym absence traps as expected |
| `pymath::pow_is_not_a_multiply_or_a_sqrt` | `b7-pow-divergence-absent` | wasm32 libm diverges and the pin catches it |
| `dfm::thermal_via_side_round_absorbs_the_pow_vs_sqrt_divergence` | `b7-pow-divergence-absent` | ULP divergence is caught, not absorbed |
| `dfm::via_annular_area_uses_r_times_r_not_pow` | `b7-pow-divergence-absent` | same class |

All four fail on wasm32 and are correctly pre-classified in
`tools/wasm/wasm_expected_failures.json`; U1's baseline records zero
unexpected-passes (the manifest is not stale) and zero disagreements.
91,000 invocations at `--repeat 1000` produced zero unexpected failures.

## The R8 gap

The plan's R8 extends the canary contract to the tier: a coverage claim
carries a demonstrated failing case **per family**. For `drc` and `routing`
the in-suite tests + the pow-divergence class demonstrate failure
capability, but **`emc`, `erc`, `safety`, `placement` have no tests to
fail**, so a per-family canary cannot be demonstrated today. Closing this is
the un-gating work from U2's known-excluded list (split
`validation.rs`-class modules into pure kernel + `#[cfg]` bridge) — a Phase
1 scope item, recorded here so a "coverage per family" claim is never made
against an empty family.

## Verdict

R7/R8 reporting is now in place (family map + failing-case demonstration) and
the honest answer is: the tier's failure capability is proven, its
family-level coverage is thin, and the next increment of value is un-gating
the gated-out kernels rather than writing new tests.
