# `Py<PyAny>` Surface Re-Audit + Removal Plan (post-wave-2)

provenance: commit=4da76ebb00fe7bcf0590c00de14b6d498aa6b679 dirty=false

> **Wave-3 outcome addendum (2026-08-07, commit `7dcfb2fe`):** This plan's
> Wave A and Wave B both overstate what is removable. Wave-3 landed the safe
> tightening (transient returns, extract-helper dedup onto `temper-py-bridge`)
> and verified — against the actual pinned test suite — that the remaining
> stored fields are not removable. A future audit must compare against this
> state, not against the wave-2 numbers below.

Measured against `origin/main` @ `4da76ebb0` (2026-08-06) in an isolated
worktree (`/private/tmp/wt9-pyany2`, branch `docs/pyany-audit-2`). The
wave-1 baseline is `docs/evidence/2026-08-05-pyany-surface-audit.md`
(measured at `db89355a6`, PR #740).

Methodology is unchanged from wave-1: counts are grep-verified, then
classified by a scope-aware parser that counts only `Py<Py…>` tokens inside
`struct { }` bodies (this re-audit additionally strips Rust comments and
string literals before tokenizing — wave-1 did not, which inflated
design-bundle by 2 via comment text in `parse_engine.rs`; the fix is what
makes `ParseResult` report 4 stored fields, not 6).

---

## 1. Re-measured totals vs the wave-1 161 baseline

| Crate | Wave-1 stored | **Current stored** | Transient (current) | Raw (current) | Stored delta |
|---|---:|---:|---:|---:|---:|
| temper-design-bundle | 153 | **252** (245 Any + 5 Dict + 2 List) | 279 | 531 | +99 |
| temper-drc-rs | 0 | **85** (85 Any) | 118 | 203 | +85 |
| temper-io-types | 8 | **16** (16 Any) | 41 | 57 | +8 |
| temper-constraint-compiler | 0 | **0** | 18 | 18 | 0 |
| temper-rust-router | 0 | **0** | 10 | 10 | 0 |
| temper-quality-oracle | 0 | **0** | 13 | 13 | 0 |
| temper-geometry | — | **0** | 3 | 3 | — |
| temper-orchestration | — | **0** | 2 | 2 | — |
| temper-placement-topology | — | **0** | 1 | 1 | — |
| **Total** | **161** | **353** | **485** | **838** | **+192** |

Wave-1's own arithmetic had two small errors that this re-audit corrects
before diffing (neither changes a classification):

- **`Violation.context`** (gates.rs:340) was a stored field at wave-1 and is
  still there — `gates.rs` has not changed since wave-1. The wave-1 table
  listed `Violation` as 3 fields; the real count was 4.
- **`Pin`** was listed as 11 fields with 12 names; the real count is 12
  (`netlist_contracts.rs` unchanged since wave-1).

So the wave-1 *true* baseline was 162 stored, and the honest movement is
**162 → 353 (+191): −3 tightenings, +194 newly-stored fields.**

### 1.1 The delta, attributed per merged PR

Wave-1's headline was "the migrations grew the surface rather than shrinking
it". Wave-2 repeats that pattern at a larger scale: **+194 new stored fields,
−3 removals** (the three wave-1 REMOVABLEs that landed). The growth is again
the sanctioned opaque-storage technique — every new struct stores the
caller's exact Python object so `repr`/`==`/`type` stay bit-identical to the
pre-migration dataclass (the drc_contracts.rs header lines 10–21 restate the
netlist_contracts.rs rationale).

| Merged PR | What it added | Stored-field delta |
|---|---|---:|
| #721 pcl tag_dispatch/_parse_utils | `pcl_tags.rs` (6: `TagTypes` 3 cached class handles + `TagRef`/`TagNot`/`ComponentRef`) + `pcl_parse.rs` (6: `PclTypes` cached enum handles) | +12 |
| #805/#816 deterministic leaves (+ batch 2) | `routing_metrics.rs` (45: `SegmentMetrics` 14 + `NetMetrics` 12 + `RoutingMetrics` 19) + `deterministic_leaves.rs` (9: `DiffPairConfig` 5 + `LayerAssignment` 4) | +54 |
| #766 leftovers | `manufacturing_monte_carlo.rs` (21) + `manufacturing_tolerances.rs` (5) + `hypergraph_factory.rs` (9) + `stackup_validator.rs` (2, io-types) | +37 |
| #808 drc-contracts | `drc_contracts.rs` (85: 16 result-type + 10 component/placement + 34 PCL constraint + 25 via/trace fields) | +85 |
| #724/#811 placer core + non-cp_sat | `placer_core/pybridge.rs` (6: `PyRect` 4 + `PyPlacementViolation` 2, io-types) | +6 |
| #740 wave-1 removals landing (2026-08-04) | `ParseResult.netlist/board` → `Py<Netlist>`/`Py<Board>`; `NetClassRulesDict.design_rules` → `Py<DesignRules>` | **−3** |
| **Net** | | **+191** (162 → 353) |

The three crates that were pure-transient at wave-1 (constraint-compiler,
rust-router, quality-oracle) stay stored-free; quality-oracle's 13 transient
occurrences are the cluster_f/survey-oracle infra (report/req/explain
surfaces), all at the boundary. `temper-constraint-compiler`'s 18 transient
are the yaml/pydantic marshalling bridges, unchanged in class.

---

## 2. Per-handle classification

Classes, per the wave-1 audit brief (unchanged):

- **REMOVABLE** — the handle wraps a single same-crate Rust pyclass (or
  `None`), the value is always that pyclass on every production construction
  path, and the replacement typed handle (`Py<ConcretePyClass>` /
  `Option<Py<ConcretePyClass>>`) preserves identity with no reachable
  behavior change.
- **INTENTIONAL** — opaque type-preservation (int-vs-float, no-coercion
  dataclass semantics), identity, dynamic attrs, duck-typed fallbacks.
- **STILL-NEEDED** — the data genuinely lives in Python (router_v6/pipeline/
  heuristics, ortools/cp_sat gates, pydantic `NetClassRules`, Python enum
  keeps, yaml-loaded dicts, numpy Generator) or is a Python-built
  identity-mutable container. Container fields whose elements are same-crate
  pyclasses are classified STILL-NEEDED (the wave-1 rule: containers are
  not removable) and listed in §4 as *tightenable*, not removable.

### 2.1 temper-design-bundle — 252 stored fields

**Unchanged wave-1 constituents (151 stored):**

| Struct | # | Line(s) | Classification |
|---|---|---:|---|---|
| `MountingHole` | 3 | board_contracts.rs:165–169 | INTENTIONAL — type preservation |
| `Pad` | 6 | :240–250 | INTENTIONAL |
| `Component` (board) | 9 | :333–349 | INTENTIONAL |
| `Trace` | 5 | :438–446 | INTENTIONAL |
| `Via` | 6 | :525–535 | INTENTIONAL |
| `Layer` | 4 | :631–637 | INTENTIONAL |
| `LayerStackup` | 2 | :711–713 | INTENTIONAL |
| `Rect` | 4 | :942–948 | INTENTIONAL |
| `Zone` | 10 | :1147–1169 | INTENTIONAL |
| `GroundDomain` | 3 | :1335–1339 | INTENTIONAL |
| `Board` | 10 | :1430–1451 | INTENTIONAL |
| `Pin` | 12 | netlist_contracts.rs:251–273 | INTENTIONAL |
| `Component` (netlist) | 13 | :422–446 | INTENTIONAL |
| `Net` | 6 | :625–635 | INTENTIONAL |
| `Netlist` | 5 | :747–755 | INTENTIONAL — mutable containers (in-place append, `#[pyclass(dict)]` dynamic attrs) |
| `TraceData` | 5 | parse_engine.rs:2153–2161 | INTENTIONAL |
| `PadData` | 9 | :2230–2246 | INTENTIONAL |
| `ViaData` | 5 | :2347–2355 | INTENTIONAL |
| `DrillDefinition` | 4 | :2430–2436 | INTENTIONAL |
| `Position` | 4 | :2513–2519 | INTENTIONAL |
| `ParseResult` | 4 | :2605–2611 (`warnings`/`traces`/`vias`/`pads`) | STILL-NEEDED — Python list containers, identity-mutable (`netlist`/`board` are now `Py<Netlist>`/`Py<Board>`, tightened) |
| `Violation` | 4 | gates.rs:324–340 | `type` INTENTIONAL (enum member identity, no-validation); `components`/`nets`/`context` STILL-NEEDED (tuples/dicts assembled by cp_sat Python gates) |
| `GateResult` | 2 | :474–477 | `status` INTENTIONAL; `violations` STILL-NEEDED (cp_sat-built tuple) |
| `BoardState` | 6 | :569–579 | `netlist`/`board`/`design_rules` **REMOVABLE** → `Py<Netlist>`/`Py<Board>`/`Py<DesignRules>` (wave-1 pending); `placement`/`routing`/`routed_pcb_path` STILL-NEEDED (router_v6 results / pipeline path) |
| `DesignRules` | 8 | design_rules.rs:345–357 | 5 STILL-NEEDED (pydantic `NetClassRules` + `BusCohortConstraint` cross-module objects); `differential_pairs` + `net_topologies` reclassified INTENTIONAL (Wave C — same-crate pyclasses, container identity-preserving); `class_pairs` INTENTIONAL (dynamic attr) |
| `NetClassRulesDict` | 1 | loaders.rs:210 | `class_pairs` STILL-NEEDED (consumer-mutated dict; `design_rules` was tightened to `Py<DesignRules>`) |
| `NetTypeSpec` | 1 | net_types.rs:277 | STILL-NEEDED — `str` OR `LayerIndex` IntEnum (R3 keep) |

**New since wave-1 (101 stored):**

| Struct | # | Line(s) | Classification |
|---|---|---:|---|---|
| `SegmentMetrics` | 14 | routing_metrics.rs:79–92 | INTENTIONAL — type-preserved scalars; `layers_used` container tightenable |
| `NetMetrics` | 12 | :279–290 | INTENTIONAL; `segment_details` (list of `SegmentMetrics`) tightenable |
| `RoutingMetrics` | 19 | :474–492 | INTENTIONAL; `net_metrics`/`failed_nets`/`timeout_nets` tightenable |
| `DiffPairConfig` | 5 | deterministic_leaves.rs:97–101 | INTENTIONAL — no-coercion dataclass (int stays int) |
| `LayerAssignment` | 4 | :223–226 | INTENTIONAL |
| `DistributionParams` | 5 | manufacturing_monte_carlo.rs:206–214 | INTENTIONAL |
| `ManufacturingVariables` | 6 | :299–309 | INTENTIONAL |
| `MonteCarloConfig` | 3 | :413–417 | INTENTIONAL |
| `MonteCarloResult` | 4 | :496–502 | INTENTIONAL |
| `MonteCarloSimulator` | 3 | :601–607 | `variables` **REMOVABLE** → `Py<ManufacturingVariables>`; `config` **REMOVABLE** → `Py<MonteCarloConfig>`; `rng` STILL-NEEDED (numpy Generator, KTD9 boundary) |
| `FeatureTolerance` | 2 | manufacturing_tolerances.rs:434/445 | INTENTIONAL — original-caller-object preservation (`nominal_value`, `worst_case_max`) |
| `ToleranceTable` | 2 | :329/331 | STILL-NEEDED — real Python dicts keyed by pyclass enum members (`etch_tolerance`, `registration`) |
| `ToleranceAnalyzer` | 1 | :518 | **REMOVABLE** → `Py<ToleranceTable>` (default is a `ToleranceTable` pyclass; doc: table never mutated) |
| `HypergraphBuildResult` | 8 | hypergraph_factory.rs:79–102 | STILL-NEEDED — Python-list containers, original-object passthrough; **unwired per #826** (see §5) |
| `HypergraphFactory` | 1 | :117 | **REMOVABLE** → `Py<Netlist>` (wrapper `extraction/hypergraph_factory.py:67` passes the `Netlist` pyclass) |
| `PclTypes` | 6 | pcl_parse.rs:63–68 | STILL-NEEDED — cached handles to Python `enum.Enum` classes (class-iteration keep, documented header) |
| `TagTypes` | 3 | pcl_tags.rs:181–183 | STILL-NEEDED — cached `ComponentTag` enum + `FrozenInstanceError` + `TagValidationError` |
| `TagRef` | 1 | :258 | STILL-NEEDED — `tag` may be `ComponentTag` OR a duck-typed Python value (fallback kept, doc lines 199–207) |
| `TagNot` | 1 | :412 | STILL-NEEDED — expression may be Rust pyclass or duck-typed Python |
| `ComponentRef` | 1 | :474 | STILL-NEEDED — original caller object, type-preserved |

**Subtotals (design-bundle): INTENTIONAL 202 · STILL-NEEDED 43 · REMOVABLE 7**

### 2.2 temper-drc-rs — 85 stored fields (all `drc_contracts.rs`, #808)

The wave-2 analog of the board/netlist contracts: every field stores the
caller's exact Python object (drc_contracts.rs header lines 10–31 — the
report surface renders `100` vs `100.0` differently, so `f64` fields would
be a visible widening). The four fields that wrap a *same-crate pyclass*
(not a scalar) are REMOVABLE; the 25 containers are STILL-NEEDED (Python-
built, identity-mutable); the scalars are INTENTIONAL.

| Struct | # | REMOVABLE → typed | STILL-NEEDED (containers) | INTENTIONAL |
|---|---|---:|---|---|---|
| `Location` | 3 | — | — | 3 (x/y may be None/int/float) |
| `Issue` | 9 | `severity` :507 → `Py<Severity>`; `location` :519 → `Option<Py<Location>>` | `affected_items`, `details` | 5 (code/message/category/check_name/constraint_id) |
| `CheckResult` | 5 | — | `issues`, `metrics` | 3 |
| `RunResult` | 2 | — | `check_results` | 1 |
| `ComponentPlacement` | 10 | — | — | 10 |
| `Placement` | 9 | `via_placement` :1318 → `Option<Py<ViaPlacement>>`; `trace_placement` :1320 → `Option<Py<TracePlacement>>` | `components`, `nets`, `zones`, `net_classes`, `voltage_domains` | 2 (board_width/height) |
| `ClearanceRule` | 4 | — | — | 4 |
| `ZoneDefinition` | 4 | — | `net_classes`, `components` | 2 |
| `LoopConstraint` | 5 | — | `nets` | 4 |
| `ThermalConstraint` | 5 | — | `components` | 4 |
| `GroupConstraint` | 6 | — | `components`, `proximity_rules` | 4 |
| `ConstraintSet` | 10 | — | `clearances`, `zones`, `critical_loops`, `thermal_constraints`, `component_groups`, `net_classes`, `voltage_domains` | 3 (hv_clearance_mm, board_width/height) |
| `Via` | 6 | — | — | 6 |
| `ViaPlacement` | 1 | — | `vias` | — |
| `TraceSegment` | 5 | — | — | 5 |
| `TracePlacement` | 1 | — | `segments` | — |

**Subtotals (drc-rs): INTENTIONAL 56 · STILL-NEEDED 25 · REMOVABLE 4**

Verified production construction paths for the REMOVABLEs: `drc_runner.py:239`
and `drc_oracle.py:575` always pass `_SEVERITY_MAP[...]` (the `Severity`
pyclass singletons) and `_Location(...)`/`None`; `router_v6/_pipeline_verify.py:98/124`
assigns `DRCViaPlacement(...)`/`DRCTracePlacement(...)` (the pyclasses).
Both consumers construct through the `drc_result.py`/`drc_types.py`
pure-delegation re-exports of these pyclasses (verified).

### 2.3 temper-io-types — 16 stored fields

| Struct | # | Line(s) | Classification |
|---|---|---:|---|---|
| `PyFootprintSpec` | 5 | footprint_spec.rs:66–74 | INTENTIONAL — type-preservation-by-construction (wave-1) |
| `PyReferenceAliasManifest` | 2 | reference_aliases.rs:39–41 | STILL-NEEDED — yaml-backed alias maps (wave-1) |
| `PyFootprintLibrary` | 1 | footprint_library.rs:55 | STILL-NEEDED — yaml-loaded registry (wave-1) |
| `PyRect` | 4 | placer_core/pybridge.rs:90–93 | INTENTIONAL — documented type-preservation with parallel `RectData` f64 view (rect.rs header); **not** removable: the Python-visible R1a signature must keep int-vs-float |
| `PyPlacementViolation` | 2 | :766/768 | INTENTIONAL — identity preservation with a live duck-typed fallback (pybridge.rs:871–881 re-attaches the caller's own pin object, which may be a non-`PyPinInfo` stand-in) |
| `PyStackupValidationResult` | 1 | stackup_validator.rs:268 | STILL-NEEDED — optional `details` dict passthrough |
| `PyStackupValidationReport` | 1 | :321 | STILL-NEEDED — results list container |

**Subtotals (io-types): INTENTIONAL 11 · STILL-NEEDED 5 · REMOVABLE 0**

### 2.4 Summary

| Class | Wave-1 | **Current** | Delta |
|---|---:|---:|---:|
| INTENTIONAL | 133 | **269** | +136 |
| STILL-NEEDED | 22 | **73** | +51 |
| **REMOVABLE** | 6 | **11** | **+5** |
| — of which already-landed wave-1 | — | (3 done) | — |
| Total stored | 161 | **353** | +192 |
| Transient (acceptable boundaries) | 209 | **485** | +276 |

Wave-1's "six removables" are now three: `ParseResult.netlist`/`board` and
`NetClassRulesDict.design_rules` landed on 2026-08-04 (the tightening wave
before this audit). `BoardState.netlist`/`board`/`design_rules` remain
pending. The eight new REMOVABLEs (drc-rs 4, design-bundle 4) come from the
wave-2 migrations.

---

## 3. Circular call-back re-scan (Rust → Python shim → same crate)

Wave-1 flagged three live + three watch-list items. Re-scan at current main:

| Wave-1 site | Status now |
|---|---|
| **loaders.rs:326** (`temper_placer.core.design_rules` → `DesignRules`) | **RESOLVED** — `py.get_type::<DesignRules>().call0()` replaces the shim hop (comment lines 320–323). The remaining shim import is `NetClassRules` (pydantic) — genuinely Python. |
| **config_loader.rs:1969** (`constraints_to_design_rules` → `DesignRules`) | **RESOLVED** — same `py.get_type::<DesignRules>()` replacement; only `NetClassRules` stays on the shim. |
| **config_loader.rs:1848** (`io.config_loader` → `ConfigValidationError`) | **KEPT, now documented inline** — the comment cites the wave-1 audit §5 item 3 and argues the import is from the exception's "real home" (the shim owns `ConfigValidationError`), not circular at runtime (sys.modules hit), with the defensive fallback (1845–1849) retained. |
| Watch: **config_loader.rs:1174/1208** (`core.net_graph`) | **RESOLVED (Wave C, 2026-08-08)** — `SubNetEdge`/`NetGraph` migrated to same-crate pyclasses (`net_graph_contracts.rs`). Now uses `py.get_type::<NetGraph>()` / `py.get_type::<SubNetEdge>()` (Rust→Rust, not circular). The Python shim `core/net_graph.py` is a pure-delegation re-export. |
| Watch: **config_loader.rs:1680** (`pcl.constraints`) | **NOT yet circular** — `pcl/constraints.py` still pure-Python dataclasses (`KeepoutConstraint`/`ConstraintTier`). The always-migrate verdict for pcl (2026-08-05 ledger) is recorded; the migration is not merged. |
| Watch: **config_loader.rs:1904** (`_constraint_types`) | **NOT yet circular** — `PlacementConstraints` is a pydantic model; still Python. |
| Watch: **config_loader.rs:1969** (`core.differential_pair`) | **RESOLVED (Wave C, 2026-08-08)** — `DifferentialPairConstraint` migrated to same-crate pyclass (`differential_pair_contracts.rs`). Now uses `py.get_type::<DifferentialPairConstraint>()`. |

**New shim-mediated call-backs since wave-1 (all non-removable, deliberate keeps):**

- **`golden_serializers.rs:406`** (io-types → `temper_placer.io.dsn_exporter`
  → `DSNExporterCore`, the *same* io-types crate). Structurally Rust→Python→
  Rust, but `DSNExporter` is a genuine boundary, not a pure re-export: it
  owns `np.argmax` rotation indices, `pin_world_position` (math.pi
  transcendentals) and the `compute_dsn_schema_hash` chain
  (dsn_exporter.py header lines 7–28 — the same judgement as the `yaml.safe_load`
  keep). Removing the call-back would require re-deciding those keeps.
- **`cluster_f/bindings.rs:221`** (quality-oracle → `io.kicad_parser` → Rust
  design-bundle parse engine). Cross-crate via shim, not same-crate; the call
  target `parse_kicad_pcb` is a Python orchestrator. Not circular.
- **`design_rules.rs:397/407`** → `router_v6.net_classification` and
  **`stackup_validator.rs:670`** → `router_v6.copper_balance` — router_v6 is
  the Phase-5 Python keep; not circular.
- **`net_types.rs:887`** → `core.board.LayerIndex` — the R3 keep (pyo3 cannot
  subclass `int`); only the IntEnum member is fetched, genuinely Python.
- **`pcl_parse.rs:75` / `pcl_tags.rs:190`** → the PCL `enum.Enum` + exception
  classes, deliberately Python (class-iteration keep). Not circular.

**Verdict: zero current removable circular call-backs.** Both wave-1
DesignRules circles and both Wave C watch-items (net_graph, differential_pair)
are now closed. The remaining Rust→Python→Rust paths are all either kept
boundaries (dsn_exporter, ConfigValidationError) or still-pure-Python
watch items.

---

## 4. Removal-wave plan

### Wave A — dispatch NOW (11 REMOVABLEs; dependencies fully migrated)

Pure handle tightening. Each replacement preserves identity of the wrapped
pyclass; the differential pins assert the field surface and object identity,
both unchanged. The three wave-1 pendings are in the same bucket as the eight
new ones.

**A1. `BoardState.netlist`/`board`/`design_rules` → `Py<Netlist>`/`Py<Board>`/`Py<DesignRules>`**
(gates.rs:573/575/577). Constructor `Option<&Bound<PyAny>>` → `Option<Py<…>>`
per field; `__eq__`/`__hash__`/`__repr__` are unchanged (they bind the handle
and defer to Python ops). Verified call sites all pass contract pyclasses:
`cli/__init__.py:741`, `router_v6/benchmark.py:82` (`result.board`,
`filtered_netlist`), `_pipeline_core.py:418` (path only), `feedback/orchestrator.py:228`
(state round-trip), `examples/demo_integrated_pipeline.py`, `_loop_gates.py:170`.
**Pins:** `tests/placer/cp_sat/test_gate_contract.py::TestBoardState`
(empty / `board=` / `netlist=` kwargs); no test pushes a non-contract payload.

> **Wave-3 verdict: NOT REMOVABLE — the pin claim above is false.** The
> pinned `test_gate_contract.py::TestBoardState::test_all_fields_populated`
> (line 244–258) and `test_gates_rust_differential.py::test_board_state_populated_identical`
> (line 371–395) both push bare `object()` instances into `netlist`/`board`/
> `design_rules` and assert identity (`bs.netlist is fake_netlist`). A typed
> constructor (`Option<&Bound<Netlist>>`) would raise `TypeError` on those
> payloads and break both pins. Typed storage behind a `PyAny` constructor
> was considered and rejected in wave 3: transmuting `object()` into a
> `Py<Netlist>` is a type lie (UB on any Rust-side downcast). These three
> fields are reclassified **INTENTIONAL** — arbitrary-payload identity
> preservation is the pinned contract. Documented in `gates.rs:563`.

**A2. `Issue.severity` → `Py<Severity>`** (drc_contracts.rs:507).
`#[pyclass]` `Severity` singletons are the only production values
(`drc_runner.py:239`, `drc_oracle.py:575`). Constructor param → `&Bound<Severity>`;
`__repr__`/`__eq__`/`to_dict` unchanged (bind + Python ops).
**Pins:** `tests/validation/test_drc_contracts_rust_differential.py` — every
`Issue(...)` construction passes `_SEV[...]` (the `Severity` members; verified
lines 93/637/640/960/963/1002); no type-preservation case passes a non-
`Severity` object, so the tightening is pin-clean.

**A3. `Issue.location` → `Option<Py<Location>>`** (drc_contracts.rs:519).
Production passes `_Location(...)` pyclass or `None` only. Replaces the
`opt_or_none` dance with `Option`. **Pins:** same differential; `__str__`/
`to_dict` None-guard unchanged.

**A4. `Placement.via_placement`/`trace_placement` → `Option<Py<ViaPlacement>>`/`Option<Py<TracePlacement>>`**
(drc_contracts.rs:1318/1320). Production assigns the pyclasses only
(`_pipeline_verify.py:98/124`). **Pins:** drc_types differential
construction cases with `via_placement=None` default.

**A5. `HypergraphFactory.netlist` → `Py<Netlist>`** (hypergraph_factory.rs:117).
The Python wrapper passes the `Netlist` pyclass (`extraction/hypergraph_factory.py:67`).
**Pins:** regression differential (`tests/extraction/…hypergraph…`). Caveat:
see §5 — the hypergraph kernel is unwired in practice; this tightening is
dispatch-able but low-value until the shim is wired.

**A6. `MonteCarloSimulator.variables`/`config` → `Py<ManufacturingVariables>`/`Py<MonteCarloConfig>`**
(manufacturing_monte_carlo.rs:601/603). **Pins:** `tests/manufacturing/test_monte_carlo_rust_differential.py`.
Caveat: these pyclasses are shim-wired but have no active production caller —
zero behavioral risk, and the differential is the only pin.

**A7. `ToleranceAnalyzer.table` → `Py<ToleranceTable>`**
(manufacturing_tolerances.rs:518). Default constructor builds a
`ToleranceTable` pyclass; the doc states the table is never mutated.
**Pins:** tolerances differential; same shim-wired caveat as A6.

### Wave B — wait on router_v6 / pipeline / heuristics (the other session's surfaces, Phase 5)

- `BoardState.placement`/`routing`/`routed_pcb_path` — router_v6 results and
  a pipeline path; tighten alongside the Phase-5 orchestration collapse.
- `Violation.components`/`nets`/`context` and `GateResult.violations` —
  assembled by cp_sat Python gates (JUSTIFIED-KEEP, ortools). Permanent
  unless the keep is re-decided. The suggested clarity tightening
  (`Py<PyAny>` → `Py<PyTuple>`/`Py<PyDict>`) is **NOT dispatchable**: the
  pinned `tests/placer/cp_sat/test_loop_termination_pbt.py:144` constructs
  `GateResult(..., violations=[v])` with a **list**, so a `Py<PyTuple>`
  field/constructor would break it (same pin-claim error as Wave A1).
- `PyPlacementViolation.item_a`/`item_b` — the duck-typed pin fallback
  (pybridge.rs:871–881) keeps these INTENTIONAL. Re-flag only if a sweep
  proves every production pin is a `PyPinInfo`.

### Wave C — core-contracts migration landed (2026-08-08)

**Landed** (plan `docs/plans/2026-08-08-001-feat-wavec-core-contracts-migration-plan.md`):

- `SubNetEdge` + `NetGraph` (62 LOC) → MIGRATED as `net_graph_contracts.rs`
  pyclasses + delegation shim. `core/net_graph.py` is now a pure-delegation
  re-export of `temper_design_bundle_python.net_graph_contracts`.
- `DifferentialPairConstraint` (47 LOC) → MIGRATED as `differential_pair_contracts.rs`
  pyclass + delegation shim. `core/differential_pair.py` is now a
  pure-delegation re-export.
- `DesignRules.differential_pairs` and `DesignRules.net_topologies` — container
  types unchanged (`Py<PyList>`/`Py<PyDict>`, identity-mutable) but element
  types are now same-crate pyclasses (`DifferentialPairConstraint`/`NetGraph`).
  Reclassified STILL-NEEDED → INTENTIONAL (container identity preserved;
  elements typed).
- Two §3 watch-items RESOLVED (`config_loader.rs:1174/1208`, `:1969`).
  Watch-list shortens from 4 to 2 (pcl.constraints + _constraint_types still
  pending).

**Still pending:**

- `DesignRules`' remaining containers (pydantic `NetClassRules`,
  `BusCohortConstraint`) — removable only when those types migrate.
  `_constraint_types` and `pcl.constraints` are still pure Python.
- `PclTypes`/`TagTypes` cached enum handles — bound to the class-iteration
  keep; permanent.
- `PyRect` — the parallel-`RectData` design means the opaque fields stay; a
  typed redesign would be a *new* design decision with its own differential.

### Wave D — tied to the #826 gate

- `HypergraphBuildResult` (8 fields) sits in the unwired ledger. Do **not**
  spend tightening effort on it while it is unwired; either wire the #793
  regression shim (making the PyAny surface exercised in production) or leave
  it ledgered. If the shim is wired later, `node_refs`/`hyperedge_names`/
  `edge_voltages`/`edge_currents`/`edge_widths`/`node_weights`/
  `hyperedge_weights`/`connected_indices` become `Py<PyList>` tightenings
  (elements are strings/floats/ints, no same-crate pyclass to point at).

### Never (INTENTIONAL — do not dispatch)

- All 62 board_contracts + 36 netlist_contracts + 27 parse fields + the 45
  routing_metrics + 9 deterministic-leaves + 20 manufacturing scalar fields +
  5 `PyFootprintSpec` + 4 `PyRect` — removing requires accepting int→float
  widening (rejected design decision) or inventing a typed `Int|Float` union.
- `Violation.type` / `GateResult.status` — identity-held enum members;
  `DesignRules.class_pairs` — dynamic attr.

---

## 5. #826-gate interaction (`check_unwired_kernels.py`)

State at current main: gate **passes** — 551 registered kernels, 85 unwired,
all ledgered. Verified by running the gate in the worktree.

- The gate does **not** currently flag any PyAny-heavy kernel the removal
  plan depends on. Every REMOVABLE target pyclass (`BoardState`, `Issue`,
  `Location`, `Placement`, `HypergraphFactory`, `MonteCarloSimulator`,
  `ToleranceAnalyzer`, `DesignRules`, `Netlist`, `Board`) is wired (its
  delegation shim references it, which the gate counts as wired). Wave A is
  therefore not blocked by #826.
- The one ledgered PyAny-heavy struct is **`HypergraphBuildResult`**
  ("unwired at time of recording; no reason given"). `HypergraphFactory`
  itself is wired only through `extraction/hypergraph_factory.py`'s
  constructor; the `build()` → `HypergraphBuildResult` → scipy-COO path has
  no production caller (matches the ledger). This makes Wave A5's
  `HypergraphFactory.netlist` tightening safe but low-value, and Wave D
  above the right treatment for the 8-field surface.
- `MonteCarloSimulator`/`ToleranceAnalyzer` are "shim-wired" (referenced by
  the `manufacturing/*` shims, so not ledgered) but have no active production
  caller — functionally dormant pyclasses. Their A6/A7 tightenings carry zero
  behavioral risk; they also could be candidates for the unwired-ledger
  conversation if the shims are considered inert.

---

## 6. Verified spot-checks (REMOVABLE claims vs production)

1. `Issue.severity` → `drc_runner.py:52,239` imports `Severity as _Severity`
   from the `drc_result.py` re-export and passes `_SEVERITY_MAP[...]` (the
   pyclass singletons) into `_Issue(severity=...)`; `drc_oracle.py:575` does
   the same. `drc_result.py` is a pure-delegation re-export of the
   `temper_drc_rs` pyclasses (header + import `temper_drc_rs as _tdrc`). ✓
2. `Issue.location` → both wrappers build `_Location(...)` (the pyclass) or
   pass `None`. ✓
3. `Placement.via_placement`/`trace_placement` → `_pipeline_verify.py:98/124`
   assigns `DRCViaPlacement(vias=...)`/`DRCTracePlacement(segments=...)`
   (aliases of the pyclasses). ✓
4. `BoardState` → all production constructions pass contract pyclasses or
   omit the field (call sites listed in A1). ✓
5. `HypergraphFactory.netlist` → `extraction/hypergraph_factory.py:67` passes
   `netlist` (typed `Netlist` in the wrapper signature). ✓
6. `ToleranceAnalyzer.table` → default builds a `ToleranceTable` pyclass;
   doc: "the table is never mutated". ✓
7. (Negative control) `PyPlacementViolation.item_a`/`item_b` — the Rust
   `validate_placement_drc` has a live duck-typed fallback
   (pybridge.rs:871–881), so the fields are not guaranteed `PinInfo`.
   Correctly INTENTIONAL, not REMOVABLE. ✓

## 7. Recommended follow-ups

1. ~~**Dispatch Wave A** (11 REMOVABLEs) as one small PR~~ — **DONE in wave-3**
   (commit `7dcfb2fe`): A2–A7 had already landed (PR #858); the transient
   returns and extract-helper dedup landed in wave-3; A1 is proven NOT
   removable (see §4). The remaining stored `Py<PyAny>` is all INTENTIONAL
   or STILL-NEEDED.
2. Update `docs/MIGRATION_PHASE_GUIDE.md` § Phase 5's boundary figure again:
   the "58 `Py<PyAny>` fields" paragraph should now be told as stored 20 → 161
   → 353 → (wave-3: transient tightened, stored unchanged for the non-removable
   classes) with the stored-vs-transient distinction, so the next measurement
   (wave-3) compares like for like. NOTE: `docs/MIGRATION_PHASE_GUIDE.md` no
   longer exists as of 2026-08-07 — record the wave-3 numbers wherever the
   Phase-5 boundary figure lives next.
3. Re-run this audit when the pcl/net_graph/`_constraint_types`/differential_pair
   migrations land — each converts a §3 watch-item into a circular call-back
   and can make `DesignRules`' seven containers removable.
4. Wire or retire the hypergraph kernel (Wave D) — `HypergraphBuildResult`'s
   8-field surface is inert today, and the #826 ledger is the mechanism to
   make that visible.
5. ~~**Migrate `BusCohortConstraint` to close `DesignRules.bus_cohorts`
   opacity**~~ — **PLANNED** (`docs/plans/2026-08-08-002-feat-buscohort-pyclass-migration-plan.md`).
   `bus_cohorts` (`design_rules.rs:354`) was excluded from Wave-C because its
   element type is pure Python; the plan migrates the dataclass to a pyclass
   (typed `Py<PyList>` elements, `get_bus_cohort_for_net` typed, config_loader
   resolved), dropping the stored count by 1 and reclassifying `bus_cohorts`
   INTENTIONAL.
6. **`metrics/quality.py::compute_quality_report` — test-only, unwired Rust
   replacement.** Verified 2026-08-08: the deprecated function has NO production
   caller (only its own differential pins it), and its Rust replacement
   `temper_quality_oracle.evaluate_quality_py` (`lib.rs:441`) takes a different
   contract (netlist/placement/spec/metrics as PyDicts, not PlacementState/
   Board objects) — wiring it requires a marshal layer, not a delegation. Both
   ends are dormant (test-only); the honest decision is Phase-6 test-suite
   territory (wire the marshaler + retire the Python, or keep both as migration
   validation). Not dispatched.
7. **`pcl/tiers.py` `tier_to_weight` twin wired** (2026-08-08, commit
   `4a19ade9`): `TieredConstraintManager.get_penalty_weights` now delegates to
   the built `temper_constraints` kernel via `pcl/rust_bridge.py`, keeping the
   dict as the R10 Python fallback. Values pinned by
   `test_rust_constraints.py::test_tier_weight_parity`. (The wider tier system
   — `ConstraintStatus`/`EscalationConfig`/`calculate_penalty` — still has zero
   production callers and is a product-owner RETIRE-vs-keep call.)
