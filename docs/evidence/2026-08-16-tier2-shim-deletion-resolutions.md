---
module: temper-placer / temper-drc-rs / temper-io-types / temper-geometry
tags: [migration, shim-deletion, oracle, tier2, rust-first]
problem_type: architecture-pattern
---

# 2026-08-16 — Tier-2 blocked shim deletions resolved

## Summary

Four Python modules were classified by the Tier-2 census as pure-delegation
shims eligible for deletion, each blocked by a specific dependency. All four
resolutions are recorded here (three executed, one kept with justification),
with the re-pin discipline from PR #1198: fix behavior first, prove every
divergence conservative, re-pin each oracle hash in a separate deliberate
commit.

| File | LOC (at census) | Resolution | Oracle re-pinned |
|---|---|---|---|
| `core/ipc2221.py` | 32 | **deleted** (defaults moved into Rust pyo3 signatures) | `_config_loader_py_oracle.py` |
| `physics/thermal.py` | 57 (actual 134) | **kept** — SSOT data module, NOT a deletion candidate | none |
| `router_v6/_strip_copper.py` | 83 | **deleted** (callers import `temper_io_types` directly) | `_adapter_convert_py_oracle.py` |
| `router_v6/grid_converter.py` | 116 | **split** — `GridCell` → `grid_types.py`; 4 delegation fns deleted | `_path_simplify_py_oracle.py` |

Total Python LOC deleted: 32 + 83 + 116 = **231** (plus the dead
`TRACE_CURRENT_TABLE_1OZ` table in ipc2221.py). Net after the split's new
`grid_types.py` (14 LOC): **217**.

## Block 1 — `core/ipc2221.py` (deleted)

**Contents:** `estimate_trace_current(width_mm, thickness_oz=1.0,
temp_rise_c=10.0, internal_layer=False)` and `estimate_current_from_net_class
(trace_width_mm, thickness_oz=1.0, temp_rise_c=10.0)`, both pure delegation
to `temper_drc_rs`; plus `TRACE_CURRENT_TABLE_1OZ` — a lookup table with no
production caller (safety-constant census 2026-08-15: prod-dead, UNCITED).

**Blocker:** the hash-pinned `_config_loader_py_oracle.py` oracle called
`estimate_current_from_net_class(net_class.trace_width_mm)` with one arg,
relying on the shim's defaults; the Rust pyo3 binding required all three
args. Additionally `config_loader.rs::validate_current_capacity` called back
into Python by module name (`py_callable("temper_placer.core.ipc2221", ...)`),
and `tools/wasm/r2_serialize_board.py` lazily imported the shim.

**Resolution (Option B — Rust owns the defaults):** added
`#[pyo3(signature = ...)]` defaults to `estimate_trace_current` (1.0 oz,
10 °C, external) and `estimate_current_from_net_class` (1.0 oz, 10 °C),
matching the shim's defaults **exactly**. Deliberately NOT
`ipc::TRACE_TEMP_RISE_C` (20.0): the oracle pins pre-migration behavior at
10 °C and the kernel's own doc comment says "Conservative current estimate
(internal layer, 1oz, 10°C rise)". Repointed `config_loader.rs`'s
`py_callable` at `temper_drc_rs` directly, the oracle's import line, and
`r2_serialize_board.py`'s lazy import; `core/__init__.py` re-export now
sources from `temper_drc_rs`.

**Parity evidence:** single-arg default calls byte-identical to the shim's
explicit (1.0, 10.0) calls across an 11-point width sweep (0 divergences);
test_ipc2221 (6), config-loader differential (21), config validation + pbt
(16), r2_serialize_board (27) all pass. The `estimate_trace_current` kernel
is now unwired (its only production caller was the shim) and ledgered
`[ORPHANED-DELETE]` — differential-only.

## Block 2 — `physics/thermal.py` (KEPT)

**The census was wrong about this file.** It is not a pure delegation shim:
it is the SSOT data module for the datasheet-recovered thermal constants —
`DEFAULT_AMBIENT_C` (60 °C, ENVIRONMENTAL_SPEC derating zero-power point),
`FIRMWARE_TRIP_TS_C` (80 °C), `T_J_DESIGN_MAX_C` (125 °C), `T_J_ABS_MAX_C`
(175 °C), `THERMAL_RESISTANCE_BY_REF` (per-refdes IKW40N120H3 values with
explicit placeholder warnings), `PLACEHOLDER_RJC_RCH_RHA`, and
`thermal_resistance_for()`. Only `estimate_junction_temp()` delegates (to
`temper_thermal.estimate_junction_temp_py`, pinned bit-for-bit by
`test_thermal_rust_differential.py`).

**Data check:** the Rust `temper-thermal` crate has **no** copies of these
constants (verified: no `pub const` for Rjc/Rch/Rha/ambient/trip anywhere in
`packages/temper-thermal/src/`; the values appear only in comments and test
arrays in `thermal_edges.rs`). The registered `_physics_py_oracle.py` oracle
imports `thermal_resistance_for` from this module. Importers are
`metrics/physics.py` (production) and `physics/thermal_potential.py`
(production).

**Resolution:** KEEP as the SSOT data module — marked **NOT a deletion
candidate**. Moving datasheet-recovered constants to Rust is a real data
migration with divergence risk (one-fact-many-homes is the project's #1
failure mechanism), not a shim deletion; it belongs to a deliberate thermal-
constants migration with its own oracle re-pin, not to this task.

## Block 3 — `router_v6/_strip_copper.py` (deleted)

**Contents:** `strip_existing_copper` / `strip_existing_zones`, pure
delegation to `temper_io_types` (the pre-migration body is pinned verbatim
inside `test_strip_copper_rust_differential.py` as the `_oracle_*` block).

**Blocker:** `_adapter_convert_py_oracle.py:48` imported `strip_existing_zones`
at module top level.

**Resolution:** repointed the oracle import to `temper_io_types` directly
(function bodies untouched — `_BODY_DIGESTS` pins remain valid), and all
production callers: `_adapter_convert.py`, `scripts/route_board.py`,
`test_topology_copper_audit.py`, `test_geometry_constraints_pbt.py`,
`test_golden_board_pumpkin_real_board.py`, `test_strip_copper.py`.
`test_shim_delegates_to_rust` removed (its subject — the shim — no longer
exists; the oracle-vs-Rust parity suites are the retained evidence).
`strip_existing_copper`/`strip_existing_zones` stay wired (production
callers now import `temper_io_types` directly) — no ledger change.

**Parity:** Rust-vs-oracle parity suites pass (70 tests in the touched
suites; 86 adapter/pipeline differential tests). The 2 remaining failures
in touched suites are pre-existing on origin/main and unrelated (board-file
segment-count pin 2290 vs 2149, handoff §4; documented power/ground policy
mismatch).

## Block 4 — `router_v6/grid_converter.py` (split)

**Contents:** `GridCell` dataclass (x, y, layer) + `grid_to_world`,
`extract_vias`, `compute_path_length`, `count_vias_in_path` — four pure
delegations to `temper_geometry` (via_clearance.rs).

**Blocker:** `_path_simplify_py_oracle.py:30` imports `GridCell` at module
level. `GridCell` is a Python type with no Rust equivalent — but it is
**production-required** (`path_simplify.py` constructs it from the Rust
`simplify_path_py` wire tuples; `io/kicad_exporter.py` consumes it).

**Resolution (option c):** `GridCell` moved to the new shared
`router_v6/grid_types.py` (plain data holder, no compute — mirrors the
`_constraint_types` JUSTIFIED-KEEP pattern). The four delegation functions
deleted; callers repointed to `temper_geometry` scalar signatures:
`kicad_exporter.py` (`grid_to_world_py(c.x, c.y, ...)` at both call sites),
`path_simplify.py` (GridCell import → grid_types), oracle
`_path_simplify_py_oracle.py` (import → grid_types), and the differential /
PBT / coverage-paydown tests.

**Ledger:** `extract_vias_py`, `compute_path_length_py`,
`count_vias_in_path_py` lost their only production caller (the shim) —
ledgered `[ORPHANED-DELETE]`, differential-only. `grid_to_world_py` stays
wired via `kicad_exporter.py`.

## Oracle re-pins (3 total — each a separate deliberate commit)

1. `_config_loader_py_oracle.py` — import line → `temper_drc_rs`
2. `_adapter_convert_py_oracle.py` — import line → `temper_io_types`
3. `_path_simplify_py_oracle.py` — import line → `grid_types`

Each re-pin commit touched exactly one `scripts/oracle_hashes.json` entry;
the gate passes 167/167. No `_BODY_DIGESTS` changed (function bodies
untouched in every case).

## Verification

- `check_oracle_hashes.py`: 167/167 OK
- `import_linter_gate.py`: PASSED (0 new violations)
- `check_verdict_coverage.py`: PASSED (R7 axis fully covered)
- 537 passed / 3 skipped across all touched suites; 1 pre-existing
  board-drift failure (documented above)
- `extensions-check`: 10/10 fresh (venv-isolated worktree; shared .venv
  untouched)
- Unwired-kernel gate: 4 ledger additions (estimate_trace_current,
  extract_vias_py, compute_path_length_py, count_vias_in_path_py); the
  remaining 4 NEW_UNWIRED (layer_identity.rs from #1210) are pre-existing
  on origin/main
- `regen-check` items: all pre-existing on origin/main (manifest-less
  scripts, layer_identity kernels, hash-order NEW_SITE in untouched files)
