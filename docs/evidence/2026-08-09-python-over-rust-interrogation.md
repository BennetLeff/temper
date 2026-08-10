# Python-over-Rust Interrogation — the 69,343-LOC with-Rust-ref surface

**Branch**: `research/python-over-rust` (worktree `/tmp/opencode/wt-pyoverrust`, off `origin/main` @ `75b8203a`)
**Date**: 2026-08-09 · **Author**: subagent research session · **Scope**: read-only; no source files touched.
**Report location**: this file.

---

## 0. What "the 69,343 LOC" actually is

Reproduced the task's baseline exactly: every `*.py` under
`packages/temper-placer/src/temper_placer/` containing a **direct import** of one of
the 12 Rust extension modules (`temper_drc_rs`, `temper_dsn`,
`temper_constraint_compiler`, `temper_design_bundle_python`, `temper_ipc`,
`temper_orchestration`, `temper_io_types`, `temper_geometry`,
`temper_quality_oracle`, `temper_placement_topology`, `temper_thermal`,
`temper_rust_router`) → **240 files, 69,343 LOC** (matches; +115 LOC of
`temper_workflow/routing/` if that tree is included).

The 12-module list is the *same blind spot* documented in
`docs/evidence/2026-08-06-never-port-triage.md` §5.1: the 13th extension
`temper_constraints` (nested under `packages/temper-placer/temper-constraints/`) is
excluded by the single-level glob. Its four extra with-ref files are
`placer/cp_sat/_encoder_solve.py` (717), `placer/cp_sat/model.py` (518),
`placer/cp_sat/handlers/keepout.py` (76), `pcl/rust_bridge.py` (245) — all
REQUIRED-PYTHON or shim, so the class totals below are unaffected in substance.

**The core finding up front**: the 69,343 is NOT 69,343 LOC of delegation shims.
Only **9.2%** is shim/reexport. The dominant class — **68.5%** — is *real Python
orchestration* (stage sequencing, batching, gate logic, model building) that calls
Rust kernels for the hot loops and keeps the control flow in Python. The migration
program's "compute in Rust, Python keeps its public API as a delegation shim"
end-state has been achieved **per-kernel**, not **per-module**: a module that once
contained 5 kernels now has 5 `return _tg.foo_py(...)` lines **and still has the
200 lines of Python orchestration that used to call them**. That orchestration is
the migration-able surface this report sizes.

---

## 1. Quantified breakdown into the four classes

Classification was done by **reading function bodies** (all 240 files surveyed;
the largest ~40 read in full, the remainder read at def-list + body-scan +
third-party-import granularity; the two prior verdict docs used as cross-checks,
re-verified against today's tree). Classes:

| Class | LOC | % of 69,343 | Files |
|---|---:|---:|---:|
| **1. PURE-DELEGATION SHIM** | **6,397** | **9.2%** | 57 |
| **2. ORCHESTRATION GLUE** | **47,515** | **68.5%** | 129 |
| **3. MARSHALLING BOUNDARY** | **4,212** | **6.1%** | 18 |
| **4. REQUIRED-PYTHON** | **11,219** | **16.2%** | 36 |
| **Total** | **69,343** | 100% | 240 |

Full per-file classification: `/tmp/opencode/classify_placer.py` (script) —
regenerable, every file in the 69,343 accounted for (0 unclassified).

### 1.1 PURE-DELEGATION SHIM — 6,397 LOC (9.2%)

Module body is almost entirely one-line `return _tg.foo(...)` delegations and/or
`X = _rust.module.X` re-exports, with no meaningful control flow.

- **Representative**: `geometry/{primitives,polygon,sdf,smooth,overlap,transform,projections}.py`
  (1,801 LOC — every public function is a verbatim `return _tg.<kernel>(...)`),
  `geometry/__init__.py` (202, ~110 re-export assigns), `core/netlist.py` (183),
  `core/design_rules.py` (392), `core/net_types.py` (78), `core/net_graph.py` (18),
  `core/differential_pair.py` (15), `validation/drc_types.py` (185),
  `io/kicad_parser.py` (132), `io/dsn.py` (86), `router_v6/astar_core_rust.py` (242,
  backend-dispatch shim with pure-Python fallback), `requirements/validators/_geometry.py`
  (119), `pcl/_parse_utils.py` (96), `physics/{emi,thermal,safety,inductance}.py`.

**Load-bearing vs pure glue**: the re-export hubs are *load-bearing API* —
`io/kicad_parser.parse_kicad_pcb_v6` has 8+ production callers and the differential
tests import the Python names; deleting them breaks the public package contract.
The one-line function shims are *pure glue* — each carries an FFI crossing that
exists only because the Python name is the API. The batch kernels
(`cell_capacity_batch_py`, `hypergraph_coo_matvec_py`, etc.) already exist precisely
because the per-call shim path is the tax.

### 1.2 ORCHESTRATION GLUE — 47,515 LOC (68.5%) — THE MIGRATION SURFACE

Real control flow (loops, conditionals, stage sequencing, batching, deadline
handling, error handling, model building) that calls Rust kernels for the compute.
**This is the class the task asks about**: it is Python's load-bearing product
logic sitting in front of Rust compute.

- **Representative**:
  - `placer/cp_sat/fixed_copper.py` (1,246) — builds the fixed-copper obstacle list
    (traces/vias/zones/pads → 18 delegated geometry kernels), *no ortools import*;
    the ortools calls live downstream in `_encoder_solve.py`. Pure Rust-kernel
    orchestration today.
  - `router_v6/constraint_model.py` (1,150) — SAT constraint model builder
    (`ModelBuilder.build()`: channel vars, capacity constraints, ESL predicates,
    geographic pruning) over 5 delegated kernels; the CNF encode+solve is already
    Rust (`solve_topology_rust`).
  - `router_v6/net_batching.py` (1,103) — net-batching orchestration: hub-block
    ordering, batch splitting, multiprocessing subprocess launch with RSS watching,
    Rust solve dispatch, result unmarshalling.
  - `router_v6/bottleneck_geometry.py` (1,229) — s-t min-cut analysis: Rust kernels
    emit `(nodes, edges)`, Python replays them into a `networkx.DiGraph`, runs
    `nx.minimum_cut`, builds the `BottleneckGeometry` payload.
  - `router_v6/clearance_check.py` (833), `channel_widths.py` (694), `channel_mapping.py`
    (639), `deterministic/stages/{_grid_core,_phase_zones,zone_aware_slot_generation,...}.py`,
    `heuristics/{organizational,structural,style}.py` (2,180), `physics/operating_point.py`
    (887, numeric core in Rust, gate/SPICE orchestration in Python), `io/kicad_exporter.py`
    (733), `io/real_board.py` (724).

### 1.3 MARSHALLING BOUNDARY — 4,212 LOC (6.1%)

Substance is converting Python objects (dataclasses, pydantic `BaseModel`s,
`PlacementState`/`Netlist`/`Board`) into the flat/typed wire shapes the Rust kernels
accept, and back. This is the Py<PyAny>/shim tax.

- **Representative**: `validation/drc_oracle.py` (716, `_placement_to_board_dict` /
  `_constraints_to_dict` builders + recursive `_constraint_value_to_plain`
  pydantic→plain), `validation/drc_runner.py` (476, same marshalers + CheckRunner),
  `validation/human_reference_extractor.py` (610, `_netlist_to_oracle_dict` /
  `_placement_to_oracle_dict`), `router_v6/terminal_extraction.py` (97, `_pin_wire` /
  `_component_wire` / `_stackup_layer_wire` wire-format marshalling into
  `extract_net_terminals_py`), `core/hypergraph.py` (148, container whose one kernel
  marshals COO triplets + numpy arrays to lists), `explainability/{decision,trace,serialization,markdown_report}.py`
  (886), `core/units.py` (191), `core/loop_extractor_rs.py` (178),
  `deterministic/feedback/{violation_mapper,drc_parser}.py`.

### 1.4 REQUIRED-PYTHON — 11,219 LOC (16.2%)

Genuinely needs Python semantics or is a recorded JUSTIFIED-KEEP.

- **Representative**: `placer/cp_sat/gates.py` (1,169 — gate orchestration over
  `kicad-cli` subprocess + pyclass re-exports; the ortools-loop boundary),
  `regression/{drc_ratchet,closure_test,physics_oracle,fingerprint,measure_closure,...}.py`
  (2,689 — recorded JUSTIFIED-KEEP harnesses, D6), `validation/spice.py` (905,
  ngspice subprocess + template strings), `cli/{timing,trace_commands}.py` (963,
  click+rich), `validation/drc_result.py` (780 — 17 ABC `Check` protocol classes),
  `validation/{drc,preflight,mfem_compare,dead_parameter_probe}.py`, `validation/prereg/schema.py`
  (pydantic), `physics/thermal_fdm.py` (523 — scipy SuperLU solve), `geometry/drc_inflate.py`
  (329 — GEOS/shapely inflate, recorded keep), `core/board.py` (314 — LayerIndex enum
  + pyclass compat), `pipeline/dag_expr.py` (201 — DAG predicate parser),
  `manufacturing/stackup_validator.py`.

---

## 2. The migration-able surface

**Migration-able LOC = ORCHESTRATION (47,515) + MARSHALLING (4,212) = 51,727 LOC (74.6%).**
The shims (6,397) are API, not compute; the required-Python (11,219) stays.

Within the 47,515 LOC of orchestration, the split by load-bearing Python-only
library (measured per file via import scan):

| Orchestration subset | LOC | Readiness |
|---|---:|---|
| **numpy-only orchestration** (no shapely/networkx/scipy/ortools/kiutils — Rust kernels + numpy arrays only) | **32,520** | **Migratable now** — the control flow is pure Rust (loops/conditionals/sequencing); numpy arrays are already the FFI wire type |
| networkx-bound orchestration (`bottleneck_geometry`, `net_batching`, `_pipeline_route`, `channel_mapping`, `topological/graph`, `loop_area`) | 4,859 | Migratable with a petgraph parity pass — `bottleneck_geometry` already shows the pattern (Rust emits the graph; `nx.minimum_cut` → petgraph) |
| kiutils-bound orchestration (`kicad_exporter`, `_write_board`, `_write_tracks`, `_write_modules`, `_write_zones`, `real_board`, `placement_roundtrip`, `_parse_board`, `_parse_nets`) | 4,665 | Migratable by replacing the kiutils s-expr writer with the Rust emitter (temper-io-types already has `kicad_write_geometry`; the DSN emitter is already Rust) |
| shapely-bound orchestration (`channel_widths`, `thermal_relief`, `bundle_analyzer`, `occupancy_grid`, `_phase_zones`, `pad_geometry`, `connectivity`, `obstacle_map`, `zone_emission`, `kicad_metadata`, ...) | 6,027 | Partially migratable — point-in-polygon/buffer/intersect already have `temper_geometry` twins; recorded keeps are only GEOS convex-hull / scipy EDT (KTD8/KTD9) |
| scipy-bound (`thermal_scorer`, `channel_skeleton`) | 1,361 | Blocked at recorded EDT/SuperLU keeps |
| multiprocessing (`net_batching`) | (in nx row) | Migratable (rayon/tokio), but the subprocess-RSS-watching design is deliberate |

(rows overlap on `channel_skeleton` and `constraints_design_rules`; the disjoint
"blocked" total is 14,995 LOC.)

### Where the migrated code would live

| Migration-able surface | Host crate | Shape of the migration |
|---|---|---|
| Stage/pipeline orchestration (deterministic `stages/*`, `router_v6/*_check.py`, `_pipeline_route.py`) | **temper-orchestration** (grows a real `Pipeline`/`Stage` engine) | Rust `Stage::run(&mut State) -> Vec<Issue>`; a thin Python `run()` keeps the public `Pipeline` API as one FFI call, not per-stage |
| Constraint-model building (`router_v6/constraint_model.py`, `placer/cp_sat/fixed_copper.py`) | **temper-design-bundle** (already holds `constraint_model` kernels) or **temper-constraint-compiler** | Rust `ModelBuilder::build()` emitting typed var/constraint structs; ortools stays only in the final encode step |
| Net batching + multiprocessing dispatch (`net_batching.py`) | **temper-rust-router** (owns `solve_topology_rust`) | Rust-side batch loop over the already-Rust solver; drop the multiprocessing entirely once single-process Rust is fast enough |
| Graph construction + min-cut (`bottleneck_geometry.py`) | **temper-geometry** (owns `build_capacitated_graph_py`) | Extend the kernel to also return the cut (petgraph), deleting the `networkx.DiGraph` replay |
| The marshalers (`validation/{drc_oracle,drc_runner,human_reference_extractor}`, `terminal_extraction`) | **temper-drc-rs** / **temper-design-bundle** / **temper-io-types** | Replace `_X_to_board_dict` with Rust-side structs / pyclasses (the `netlist`→pyclass migration is the proven precedent); the dict-wire-formats disappear |
| KiCad write path (`io/_write_*`, `kicad_exporter.py`) | **temper-io-types** (owns `kicad_write_geometry`) | Rust s-expr emitter completes; the exporter orchestration moves with it |
| Shims (`geometry/*`, `core/netlist.py`, `io/kicad_parser.py`, `validation/drc_types.py`) | — | **Collapse to `.pyi` stubs or become `X = _rust.X` one-liners** once the public API is frozen; importers repointed at the Rust module. **Do not delete** — they are the load-bearing public API + the extension-absent fallback |

---

## 3. The value argument — does the Python earn its keep?

| Class | LOC | Verdict (one line) |
|---|---:|---|
| **PURE-DELEGATION SHIM** | 6,397 | **Earns its keep ONLY as API surface + extension-absent fallback**; not compute overhead (the kernel is already Rust), but it is 6,397 LOC of FFI-tax that should be `.pyi`/one-liner, not prose bodies |
| **ORCHESTRATION GLUE** | 47,515 | **Earns its keep as testable, differential-pinnable control flow — but that is exactly the Python we are paying a per-stage FFI tax to keep**; the value is "the algorithm stays readable and pytest-drivable", the cost is 47k LOC of orchestration Rust would express in ~5–8k, and no whole-pipeline Rust fusion |
| **MARSHALLING BOUNDARY** | 4,212 | **Pure overhead — no value beyond bridge compat.** Each marshaler exists because the Rust side consumes flat dicts/lists instead of typed structs. This is the class where a Rust migration is all upside |
| **REQUIRED-PYTHON** | 11,219 | **Earns its keep — genuinely non-migratable today**: ortools, pydantic, click/rich, ngspice/kicad-cli subprocess, duck-typed `Check`/`Stage` protocols, recorded keep harnesses |

---

## 4. What genuinely must stay Python (with LOC)

1. **The ortools CP-SAT boundary** — `placer/cp_sat/gates.py` (1,169), plus the four
   `temper_constraints`-only files just outside the 12-module baseline
   (`_encoder_solve.py` 717, `model.py` 518, `handlers/keepout.py` 76). Recorded
   whole-subtree `JUSTIFIED-KEEP` (ledger, 2026-08-04) with the documented
   re-decide trigger (corpus benchmark + acceptance gate). `fixed_copper.py` is
   *not* ortools-bound (verified — no ortools import; the geometry/item building is
   Rust-kernel orchestration) and is migratable separately.
2. **pydantic validation** — `_constraint_types/**` (not in the 69,343 baseline),
   `validation/prereg/schema.py` (223), `io/config_loader.py` (113), `validation/drc_oracle.py`'s
   pydantic→plain conversion (its marshalling half, ~200 LOC).
3. **click/rich CLI** — `cli/timing.py` (827), `cli/trace_commands.py` (136), the
   CLI dispatchers in `cli/__init__.py`.
4. **External-tool subprocess wrappers** — `validation/spice.py` (905, ngspice),
   `validation/drc.py` (586, kicad-cli), `validation/preflight.py` (502),
   `placer/cp_sat/gates.py`'s kicad-cli path.
5. **Recorded JUSTIFIED-KEEP harnesses** — `regression/**` (2,689), `validation/{dead_parameter_probe,mfem_compare}.py` (681).
6. **Duck-typed protocol layers** — `validation/drc_result.py` (780, 17 ABC `Check`s), `core/board.py` (314, enum + pyclass dataclass compat).
7. **Recorded geometry boundaries** — `geometry/drc_inflate.py` (329, GEOS),
   `physics/thermal_fdm.py` (523, scipy SuperLU), the scipy-EDT carve-outs in
   `router_v6/channel_widths.py` / `_astar_heuristics.py` / `routability_check.py`.

**Total REQUIRED-PYTHON in the with-ref baseline: 11,219 LOC.** (Plus the
ortools-only files outside it: ~1,311.)

---

## 5. Prioritized migration order (most LOC reduction, least risk)

Ranked by (LOC removed × risk-to-parity):

1. **The marshalling boundary → Rust-side structs (4,212 LOC)** — *lowest risk, pure
   tax*. Replace the `_X_to_board_dict` marshalers with pyclass/typed-struct
   conversions in the crates that consume them (`temper-drc-rs`, `temper-design-bundle`).
   The netlist/board → pyclass migration is the proven precedent
   (`_contract_dataclass_compat.py` exists because of it). No orchestration moves, no
   differential surface shrinks — the differentials just stop marshalling through flat
   dicts. **This is the highest-value/lowest-risk LOC removal in the whole 69k.**

2. **Collapse the shims to `.pyi`/one-liners (6,397 LOC)** — freeze the public names
   (most already `__all__`-pinned and differential-tested), turn the 22-line
   `return _tg.foo(...)` bodies into `.pyi` stubs or `foo = _rust.foo` assigns, repoint
   internal importers at the Rust module. Zero logic changes; the extension-absent
   fallback of the few shims that carry one must be preserved.

3. **numpy-only orchestration → temper-orchestration pipeline (32,520 LOC)** — the
   biggest win. Migrate the deterministic `stages/*` and the geometry-heavy
   `router_v6` checks whose compute is already all-Rust-kernel (`clearance_check`,
   `clearance_engine`, `creepage_check`, `fixed_copper`, `domain_clearance`,
   `isolation_barrier`, `constraint_model`) as a Rust `Stage` engine, one stage per PR
   with the existing differentials as the parity gate. The Python `run()` becomes a
   single FFI call per stage (or one per pipeline). Start with the stages that have
   **no** python-only library and **already** call only Rust kernels — that is the
   lowest-risk subset (~30% of the 32.5k).

4. **networkx orchestration (4,859 LOC)** — after a petgraph min-cut parity test,
   extend `build_capacitated_graph_py` to return the cut (deleting the nx replay in
   `bottleneck_geometry.py`), then absorb `net_batching`'s batch loop into
   `temper-rust-router`.

5. **kiutils write path (4,665 LOC)** — complete the Rust s-expr emitter in
   `temper-io-types` (already owns `kicad_write_geometry`) and move the exporter
   orchestration with it. This is the quiet second-biggest hidden boundary.

6. **shapely carve-outs** — migrate point-in-polygon/buffer where a `temper_geometry`
   twin already exists; keep the recorded GEOS/Qhull/EDT carve-outs in Python.

**Never migrate**: the 11,219 LOC of REQUIRED-PYTHON in §4. The ortools boundary is
the capstone — everything upstream of it (`constraint_model`, `fixed_copper`) can
migrate *before* the CP-SAT decision, because they build typed geometry/model
structs, not ortools calls.

---

## 6. Bottom line

- **69,343 LOC** of Python imports a Rust extension, but only **9.2%** is delegation
  shim. The honest answer to "is the Python layer adding value" is: **most of it is
  real orchestration that the kernel-by-kernel migration program deliberately left
  in Python**, because the program's stated end-state ("compute in Rust, Python
  keeps its public API") was defined per-kernel, not per-pipeline.
- **51,727 LOC (74.6%) is migration-able** (orchestration + marshalling), and at
  least **32,520 LOC of that** is ready *now* (numpy-only, all compute already Rust).
- The **marshalling boundary is pure tax** (4,212) — no value beyond bridge compat.
- The **shims are load-bearing API, not overhead** (6,397) — collapse, don't delete.
- **11,219 LOC genuinely must stay Python** (16.2%): ortools, pydantic, CLI, viz,
  subprocess tool wrappers, protocol layers, recorded keeps.
- A Rust migration does not delete the Python API — it shrinks what sits *behind*
  it from 47k LOC of orchestration to a thin `run()` that crosses FFI once per
  stage, which is exactly the migration program's own end-state, one level deeper.
