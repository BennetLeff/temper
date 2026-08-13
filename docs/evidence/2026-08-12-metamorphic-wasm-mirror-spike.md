# SPIKE: mirroring the Python metamorphic test relations onto the wasm tier

<!-- provenance: commit=HEAD-at-write dirty=false -->

**Date:** 2026-08-12
**Branch:** `spike/metamorphic-wasm-mirror`

## Summary

The Python-side metamorphic suites (`packages/temper-placer/tests/**/test_*_metamorphic*.py`)
are functional relations (translation invariance, permutation invariance,
monotonicity, symmetry) that are language-agnostic: each can be re-expressed
as a seeded Rust property over the crate's pure kernels and registered in
`wasm_test_registry.rs`, which runs on the Cloudflare Workers tier. This
spike surveyed all 12 metamorphic files, classified every relation as
mirror-able (pure-functional, deterministic) vs not (Python-object- or
interpreter-bound), and mirrored the clean batch: **8 new relations, 361 new
wasm-tier tests across 3 crates** (plus 2 relations found already mirrored).

## The established mirror pattern (read before mirroring)

1. A `fn <name>_impl(seed: u64)` property over the pure kernel, drawing its
   inputs from a local `SplitMix64` PRNG (no external RNG crate —
   wasm32-unknown-unknown has no entropy source; a fixed seed makes a trap
   reproducible from the failing test's name). See
   `temper-drc-rs/src/rules/drc/property_campaigns.rs`,
   `temper-io-types/src/property_campaigns.rs`,
   `temper-orchestration/src/wasm_campaign_prng.rs`.
2. `#[cfg_attr(test, test)] fn <name>_seed_XXXXXX() { <name>_impl(seed); }`
   wrappers — one per seed, in a `// --- <name>: N generated seeds ---`
   block (io-types) or a `BEGIN/END generated seeded property-mirror
   wrappers` marker block (orchestration). `gen_wasm_test_registry.py`
   folds every `#[test]`-shape function into the module's `WASM_TESTS`.
3. `python3 scripts/gen_wasm_test_registry.py --crate <crate>` regenerates
   the registry; `--check` is the CI drift gate.
   **Gotcha:** the generator resolves `REPO_ROOT` from the script's own
   path, so it always targets the *main checkout* — run a worktree-local
   copy (or point it at the worktree) or it silently validates the wrong
   tree.

## Survey — every metamorphic relation, classified

`(a)` = pure-functional, mirror-able as a seeded Rust property.
`(b)` = not mirror-able (Python-object, numpy/shapely, oracle, or
interpreter-bound kernel).

| File | Relation | Class | Why / mirror target |
|---|---|---|---|
| `test_metamorphic_oracles.py` | parse idempotency | (b) | parses the real `temper.kicad_pcb` through `parse_kicad_pcb` |
| | fixed-position bounds | (b) | board file + Python dataclasses |
| | initial non-overlap | (b) | Python objects, warn-only |
| | ref uniqueness | (b) | Python objects |
| `test_topological_metamorphic.py` | MR1 relabelling | (b) | `temper_placer.topological` is **pure Python** (`graph.py`, `propagation.py`, `force_refinement.py`); no Rust kernel to mirror onto |
| | MR2 edge-order permutation | (b) | same |
| | MR3 translation equivariance | (b) | same (tolerance-based; Python impl) |
| | MR4 x-reflection equivariance | (b) | same (bit-exact claim over Python impl) |
| | MR5 power-of-two scaling | (b) | same |
| | MR6 order-sensitivity witness | (b) | pins Python behaviour |
| `test_astar_metamorphic_pbt.py` | MR1 rotation / MR2 symmetry / MR3-4 obstacle monotonicity / MR5 weight scaling / MR6 empty-grid / MR7 translation / MR8-9 path sanity + Theta*/Lazy variants | (b) | `astar_core._astar_search` is Python over numpy `OccupancyGrid`, and most relations pair against a **Dijkstra oracle** for small grids; the Rust A* surface (`temper-rust-router`) exposes no matching search kernel with the same semantics |
| `test_tag_metamorphic_pbt.py` | tag refinement subset / expansion monotonicity / boolean identity | (b) | `temper_placer.pcl.tag_dispatch` over Python `Component`/`Netlist`; `temper-pcl-ir` has no tag-dispatch kernel |
| `test_channel_ops_rust_metamorphic.py` | MR1 expansion idempotence | (a) | `temper-geometry` `channel_mapping.rs` (`expand`-family kernels) — **not mirrored in this batch** (kernel lives Python-side in the shim; follow-up) |
| | MR2 pad-order closure | (a) | same |
| | MR3 waypoint permutation invariance | (a) | same |
| | MR4 edge-width bound | (a) | `channel_widths` kernels in `temper-geometry` |
| `test_net_batching_rust_metamorphic.py` | MR1 order permutation / MR2 chunk merge / MR3 shrink decomposition / MR4 consume decomposition | (a) | relations are pure, but the Python file is oracle-vs-shim over `Net`/`SimpleNamespace` objects; the Rust `net_batching` module exposes no wasm-eligible kernels (only a `register()` bridge) — **not mirrored** |
| `test_clearance_family_rust_metamorphic.py` | MR1 clearance symmetry | (b) | `get_clearance_impl` is `#[cfg(feature = "python")]` — calls `temper_design_bundle_python` `VoltageClass`; no wasm-compatible kernel |
| | MR2 creepage threshold superset | (b) | `run_creepage_check_impl` python-gated (temper-geometry py calls) |
| | MR3 partition ref covariance | (a) | **MIRRORED** — `classify_domain_partition_py` is pure; new P4 (20 seeds) in `temper-orchestration/src/clearance.rs` |
| | MR4 audit monotone in separation | (b) | `audit_domain_clearance` python-gated |
| | MR5 barrier rotation table | (a) | **already mirrored** — `project_onto_barrier_axis_is_the_integer_rotation_table` + P2/P3 seeded rotation properties |
| `test_pipeline_route_rust_metamorphic.py` | MR1-4 select/convert/write/grids | (b) | exercised through Python shims (`SimpleNamespace` duck-typing); the orchestration `pipeline_route.rs` kernels are marshal-level and shim-bound |
| `test_adapter_convert_marshal_metamorphic.py` | MR1-4 marshal invariance | (b) | shim functions `_write_routes_to_content`/`_build_routing_result` are Python glue over `SimpleNamespace`; no pure kernel surface |
| `test_bottleneck_geometry_metamorphic.py` | M1 translation | (a) | **MIRRORED** — `cell_capacity` + `build_capacitated_graph` + `min_cut_edmonds_karp` in `temper-geometry/src/bottleneck_geometry.rs` (10 seeds + deterministic min-cut scenario) |
| | M2 source/sink swap | (a) | **MIRRORED** (10 seeds) |
| | M3 obstacle doubling monotonicity | (a) | **MIRRORED** (10 seeds) |
| | M4 safety reclassification monotonicity | (a) | **MIRRORED** (10 seeds) |
| `test_core_contracts_metamorphic.py` | M1 adjacency pin-order invariance | (a) | **already mirrored** — `adj_pin_order_invariance_impl` (+ `adj_relabeling_invariance_impl`) in `temper-io-types/src/property_campaigns.rs` |
| | M2 classification case invariance | (a) | **already mirrored** — `nc_case_invariance_core_impl` / `_v6_impl` (same file) |
| | M3 Rect translation | (a) | not mirrored: `RectData::width` is a single subtraction — the relation is vacuous in Rust (no rounding path); low value |
| | M4 placement-DRC translation | (a) | **MIRRORED** — `pdrc_translation_invariance_impl` (100 seeds) |
| | M5 inflation additivity | (a) | **MIRRORED** — `mf_inflation_additive_impl` (100 seeds) |
| | M6 angle oddness | (a) | **MIRRORED** — `u_angle_conversion_odd_impl` (100 seeds) |
| | witnesses (round-trips, hash seed) | (b) | pin Python/`PYTHONHASHSEED`-specific behaviour |
| `test_fixed_copper_builder_metamorphic.py` | MR1 margin monotonicity / MR2 layer subset / MR3 origin translation / MR4 audit monotone | (a) | relations pure, but the `temper-design-bundle` `FixedCopperBuilder` mirrors only item-encode surfaces; **not mirrored in this batch** (follow-up candidate) |

## The mirrored batch (committed)

| Crate | Relation | Tests | Commit |
|---|---|---|---|
| temper-geometry | bottleneck M1-M4 | 41 (40 seeded + 1 deterministic) | `c1c41c9bb` |
| temper-io-types | core-contracts M4/M5/M6 | 300 (100 seeds each) | `fb9423bd7` |
| temper-orchestration | clearance-family MR3 | 20 | `7dec6c08f` |

Registry totals: temper-geometry 8280 → 8321, temper-io-types 6638 → 6938,
temper-orchestration 999 → 1019.

## Coverage gain

- **8 relations** moved from Python-CI-only coverage to the wasm tier (2
  more, M1/M2, were already mirrored — the survey re-confirmed them).
- **361 new wasm-tier tests** run on every Worker invocation with distinct
  seeded inputs (the wasm tier's volume payload — a fixed fixture explores
  the same inputs; each seed here is a distinct occupancy/netlist/angle
  scenario).
- The Python suites stay (they exercise the Python-visible shim surface and
  its oracle pairing); the offload is per-relation *coverage redundancy*,
  not test deletion. The Python-CI time that could eventually be reclaimed
  is the seeded random exploration (Hypothesis `max_examples` runs) for the
  mirrored relations — the deterministic/witness Python tests remain the
  shim-level pin. Quantifying the reclaimable seconds per suite is a
  follow-up (measure pytest wall time per mirrored test class); the spike
  deliberately did not delete or shrink any Python test.

## Verification

- `cargo test`: geometry bottleneck 63/63, io-types property_campaigns
  6789/6789, orchestration clearance 92/92 (`--no-default-features`; the
  default `python` feature links libpython3.9, which is absent on this box).
- `gen_wasm_test_registry.py --crate <crate> --check`: all three up to date
  (8321 / 6938 / 1019).
- `scripts/regen_derived.py --check` (worktree-local copy): all gates OK.
- `cargo check --no-default-features --features wasm-test-registry` per
  crate: compiles (this is the wasm32 build's feature set);
  `cargo clippy`: clean.

## Notes for follow-ups

- `temper-geometry` `channel_mapping.rs` MR1-MR3 and
  `temper-design-bundle` `FixedCopperBuilder` MR1-MR4 are the next clean
  (a)-class batch (the `channel_mapping` kernel
  `expand_channel_path_terminals` equivalent needs locating first).
- `test_topological_metamorphic.py` is (b) only because the Python module
  is pure Python — if/when the topological kernels migrate to Rust, its
  six relations become the highest-value mirror batch.
- The orchestration registry is not on `regen_derived.py`'s drift-gate
  crate list; `gen_wasm_test_registry.py --crate temper-orchestration
  --check` covers it directly.
