<!-- provenance: commits 631414c35, b24ce8de3, 270f7780b on branch spike/pyany-removal
     base=origin/main d8062c6e6f60b693aa42f615e4042826de417d63
     date=2026-08-12
     method=pyo3-registration scan (scripts/check_unwired_kernels.py), AST import
       gate over packages/temper-placer/src + tests, cargo check/test for the
       changed crates, python-feature rebuild via make extensions, differential
       + PBT suites for the changed surface -->

# Rust PyAny-removal spike — what was removable on 2026-08-12

**Scope.** The brief asked for a removal audit of the Rust side of the now-
complete Python→Rust migration: (a) `Py<PyAny>` / `Option<Py<PyAny>>` struct
fields that can be tightened to concrete types, and (b) pyo3
`#[pyfunction]`/`#[pyclass]` wrappers that are unwired (the
`.unwired-kernel-inventory` ledger). Deliverable: a removal plan with
evidence plus the executed safe removals.

**Result: 4 unwired kernels deleted and 4 `Py<PyAny>` fields tightened; 3
commits pushed (`631414c35`, `b24ce8de3`, `270f7780b`); ~283 LOC removed
net. Nothing touched the wave-4 differential-oracle-pinned kernels.**

---

## Part A — PyAny field inventory + classification

Full inventory of every struct field carrying `Py<PyAny>` /
`Option<Py<PyAny>>` across `packages/*/src`, with the classification for
each. The key finding: the phased `BoardState` (R-A debt) is NOT tightenable
today — the D-batch stage-migration PRs (D1–D7) left every field as
`Option<Py<PyAny>>` and the stages read them via `py.getattr`, which is
exactly the "marshalling tax inside the Rust stage body" that R-A warned
against. The Python values are Python dataclasses (`Board`, `Netlist`,
`LoopCollection`, `ClearanceGrid`, `DRCOracle`, `DesignRules`, frozensets,
dicts) with **no concrete Rust pyclass at the FFI boundary** — the shims
construct the Python objects and hand them across. The Phase A marshalling
types that would enable tightening (`DrcBoardSnapshot`, `TypedConstraintSet`,
… exist, but none corresponds to a `BoardState` field *value*). Tightening
here is a real migration (marshallers + stage rewrites), not a safe removal.

### TIGHTENED (executed, Python API byte-identical)

| Field | From → To | Evidence |
|---|---|---|
| `PipelineState.config` (pipeline_state.rs) | `Py<PyAny>` → `Py<PipelineConfig>` | Dataclass declares `config: PipelineConfig` (oracle `_pipeline_state_py_oracle.py:102`); every exercised caller passes the pyclass; typed extraction is a lossless downcast. |
| `PipelineState.current_phase` | `Py<PyAny>` → `Py<PipelinePhase>` | Declared `PipelinePhase` (oracle:105); `None` ctor sentinel → `PipelinePhase.INPUT` default preserved. |
| `PipelineState.failed_phase` | `Py<PyAny>` → `Option<Py<PipelinePhase>>` | Declared `PipelinePhase \| None` (oracle:111); `None` stored as `None`, repr/eq render identically (`opt_py_eq_phase` compares via the pyclass `__eq__`, never `Py` pointer identity). |
| `ConvergenceState._best_routed_nets` (convergence.rs) | `Option<Py<PyAny>>` → `Option<Py<PyFrozenSet>>` | Oracle pins a `frozenset[str]` (`_convergence_py_oracle.py:349`); only `None`/frozenset ever lands here; kernel already writes `PyFrozenSet`. The tightened setter keeps the Python-visible frozenset type exactly. |

Verified: `test_pipeline_state_rust_differential.py` (18), full
`tests/pipeline/` (626), `test_convergence_{rust_differential,pbt}` +
`test_pipeline_feasibility_rust_differential` (111), `tests/pcl/` (1405)
green; `cargo test --lib` on temper-orchestration 1057/1057 (with
`PYO3_PYTHON` pointed at the venv; the pre-existing default-feature binary
loads a stale libpython3.9 and cannot link — environment issue, not the
change).

### TIGHTEN-pending (concrete Rust type does not exist at the FFI boundary)

- **`BoardState`, all 23 `Option<Py<PyAny>>` fields** (board_state.rs):
  `board`, `netlist`, `loops`, `grid`, `drc_oracle`, `drc_violations`,
  `design_rules`, `connectivity_violations`, `placement_violations`,
  `placements`, `used_slots`, `config`, `component_domain_map`,
  `routing_corridors`, `domain_regions`, `routes`, `vias`, `violations`,
  `zones`, `component_zone_map`, `zone_slots`, `layer_assignments`,
  `reclaim_by_pin_pair`. The Python values are `Board` / `Netlist` /
  `LoopCollection` / `ClearanceGrid` / `DRCOracle` / `DesignRules` / frozensets
  / config dicts — no Phase A marshalling pyclass exists for any of them.
  The R-A mitigation ("tighten in the same PR as the migrating stage") was
  NOT applied by the D1–D7 PRs (see `docs/evidence/2026-08-11-rust-driver-endgame-assessment.md`,
  which documents the same finding). The wasm test registry documents the
  consequence: 51 orchestration tests build fake Python objects to drive
  `BoardState` through its GIL-shaped API.
- **Stage-struct fields**: `ClearanceGridStage.pad_sizes / net_class_clearances
  / net_classes / hv_exclusion_zones` (Python dicts/lists passed by the
  `_grid_stage.py` shim), `ComponentAssignmentStage.fixed_placements`,
  `DrcOracleSetupStage.design_rules / parsed_pads`,
  `NetClassSetupStage.net_classes` — all Python objects the shims construct.

### KEEP-as-any (genuinely duck-typed / plan-settled)

- **`PipelineConfig` path fields** (`input_pcb`, `constraints_yaml`,
  `loops_yaml`, `output_pcb`, `output_report`, `output_trace`): the
  differential **randomizes `input_pcb` as both `Path` and `str`**
  (`test_pipeline_state_rust_differential.py:217-219`) — tightening to
  `PathBuf` would break a pinned input.
- **`PipelineState` container/`Any` fields** (`phase_timings` —
  `dict[PipelinePhase | str, float]` — and `board`/`netlist`/`loops`/
  `constraints`/`deterministic_result`/`placement_state`/`routing_result`/
  `physics_report`/`preflight_report`/`decision_trace`/`_best_routed_nets`):
  the dataclass types them `Any`; the differential feeds arbitrary values
  (`"board-obj"`, `42`, dicts, lists).
- **`PyRect` coords** (io-types, mirrors `core.board.Rect`): int-or-float
  duck-typing (repr `5` vs `5.0` must survive). `PyPlacementViolation`
  item refs, `PyReferenceAliasManifest` alias maps: opaque Python values.
- **`pcl_contracts` pyclasses**: fully-opaque `Py<PyAny>` storage is the
  wave-4 core-contracts plan's **settled D1 decision**
  (`docs/plans/2026-08-08-001-feat-wavec-core-contracts-migration-plan.md`).

`d1_bridge.rs` and `feasibility.rs` contain no struct fields (only
`Py<PyAny>` function parameters/returns, which are the FFI seam itself).

---

## Part B — unwired-kernel classification (37 ORPHANED-DELETE entries)

The 2026-08-11 triage marked 37 ledger entries ORPHANED-DELETE. Re-classified
each against the constraint *"do not touch kernels the wave4-differential
oracles pin"* — every one of the 37 except the four below is referenced by a
differential or PBT suite (`test_congestion_rust_differential.py`,
`test_dfm_rust_differential.py`, `test_geometry_types_rust_differential.py`,
`test_pin_geometry_rust_differential.py`, `test_quality_metrics_rust_differential.py`,
`test_fixed_copper_rust_differential.py`, `test_core_graph_cluster_pbt.py`,
`test_sequential_routing_dataclasses_*`, …), so deleting any of them would
break a pinned suite — that is the U4/U5 "delete alongside its
oracle+differential" retirement bar, out of spike scope.

### DELETED (4 — the only entries with ZERO Python references, prod or test)

| Symbol | Crate / location | Evidence |
|---|---|---|
| `PyCompiler` | temper-constraint-compiler `lib.rs:58-193` | Zero Python refs (ledger + AST gate). Superseded by the stateless `compile_pcl_constraints` pyfunction that `router_v6/_pipeline_route.py` wires (74,129). Its internal helpers remain used by that function; only `diagnostic_to_py_dict` becomes dead and is `pub` (no warning). |
| `build_adjacency_flat` | temper-io-types `placer_core/pybridge.rs` | Zero refs. Superseded by design-bundle `netlist_contracts.build_adjacency_matrix` (wired at `core/netlist.py:59`); the io-types `adjacency::build_adjacency_matrix` stays (used by `property_campaigns.rs` + 8 unit tests). |
| `normalized_bundle_json` | temper-design-bundle `lib.rs` | Zero refs. One-shot convenience export; production reaches the bundle via `preflight_identity` (`io/design_bundle_preflight.py:66`) and `parse_engine`. |
| `points_centroid_winding` | temper-geometry `bridge.rs` + `polygon.rs` | Zero refs. Passthrough alias of `polygon_centroid` (same shoelace); the wired `polygon_centroid`/`polygon_area` exports stay. Removed the bridge export, the polygon.rs alias, and its (vacuously equal) test; wasm registry regenerated (8272 tests). |

Each deletion = `#[pyfunction]`/`#[pyclass]` + registration + the Rust fn
(bridge/polygon case) + ledger entry removed. `.unwired-kernel-inventory`
regenerated via `check_unwired_kernels.py --write-inventory` (107 → 103
entries; the TRIAGE doc block restored by hand because the regenerator drops
non-generated comment lines). Note the regenerator drops hand-written header
comments — the `--write-inventory` round-trip is not comment-preserving.

### KEPT (33 — differential/PBT-pinned)

`DiffPairConfig` (design-bundle), `apply_damped_position_py`,
`apply_suggestions_damped_py`, `apply_total_movement_py`,
`apply_update_positions_py`, `build_adjacency_flat`'s neighbours are
exceptions — kept set: the 4 `congestion_heatmap_*`, 5 `dfm_*`, 5
`fixed_copper_*` scalar wrappers, `normalize_rotation_index_py`, `pad_radius_py`,
`pin_world_position_at_py` (production comment reference in
`core/pin_geometry.py` — actually the ledger records it as distinct from the
wired `pin_world_position_kernel_py`; the grep hit is a docstring), the 3
`placement_*` suggestion kernels, `point_distance_py`, `slop_*` (5),
`track_midpoint_py`, `version_py` (2 smoke tests call it:
`test_rust_constraints.py:45`, `test_quality_oracle.py:34`). Every one is
pinned by a wave-4 differential/PBT or a smoke test — deleting requires the
oracle+differential retirement bar.

---

## Gates

- `cargo check` clean on all 5 changed crates (constraint-compiler,
  io-types, design-bundle, geometry, orchestration); no new warnings.
- `cargo test`: geometry 8340, io-types 6730, design-bundle 33,
  constraint-compiler 1909+, orchestration 1057 (python feature, with
  `PYO3_PYTHON` set) — all green.
- Python: `tests/pipeline/` 626, `tests/core/` 2674 (2 failures are
  **pre-existing on origin/main** — the `#1042` gnd fix drifted the
  `_design_rules_py_oracle.py` pin; reproduced on a pristine worktree at
  `d8062c6e6`, untouched by this spike), `tests/pcl/` 1405, convergence 111.
- `scripts/import_linter_gate.py`: PASSED (0 violations).
- `scripts/check_unwired_kernels.py`: OK (103 ledgered).
- `make regen-check`: wasm registries + hash-order + wire-format OK; the 2
  failures (drifted `_measure_closure_py_oracle.py` pin from #1037, missing
  `generate_power_islands.py` manifest entry from #1047) are pre-existing on
  origin/main.
- `make extensions-check`: 10/10 fresh.

## Handoff notes

- The R-A mitigation was not followed in D1–D7; the `BoardState` PyAny debt
  is the intended Phase-A-marshalling work, not a quick removal.
- `check_unwired_kernels.py --write-inventory` is not comment-preserving;
  the ledger's TRIAGE block was restored manually.
- The shared `.venv` was found being churned by concurrent sessions (branch
  switched under the worktree mid-session; AGENTS.md edited externally) —
  commit-per-milestone + immediate push proved necessary, as the brief said.
