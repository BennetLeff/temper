# `Py<PyAny>` Surface Audit + Removal Plan (post-wave-1)

provenance: commit=db89355a60076e1e28012d6d22410b862445d3dc dirty=false

Measured against `origin/main` @ `db89355a6` in an isolated worktree
(`docs/pyany-surface-audit`), 2026-08-05. The guide baseline is
`docs/MIGRATION_PHASE_GUIDE.md` § Phase 5 (authored 2026-08-04, commit
`8a869e9fb` on `docs/migration-phase-guide`).

All counts are grep-verified (`grep -rn "Py<Py…" packages/*/src --include='*.rs'`),
then classified by a scope-aware parser that only counts fields inside `struct { }`
blocks (function parameters and locals are excluded from the stored count).

---

## 1. Re-measured totals vs the guide's 58-field baseline

### 1.1 The guide's "58" was a raw-occurrence count, not a stored-field count

The guide says: *"58 `Py<PyAny>` fields — 28 in `temper-design-bundle`, 11 in
`temper-constraint-compiler`, 10 in `temper-rust-router` — are the deepest form
of not-really-migrated."*

Reconstructing the guide's measurement at its own tree (`8a869e9fb`, which is
`e47dd0a99` + the guide doc, i.e. the pre-wave-1 state):

| Crate | Guide's number | Raw `Py<PyAny>` occurrences at guide tree | Stored struct fields at guide tree |
|---|---|---|---:|
| temper-design-bundle | 28 | 28 | 13 (+ 5 `Py<PyDict>` + 2 `Py<PyList>`) |
| temper-constraint-compiler | 11 | 11 | 0 |
| temper-rust-router | 10 | 10 | 0 |
| temper-drc-rs | (unnamed) | 2 | 0 |
| temper-io-types | (unnamed) | 3 | 0 |
| temper-quality-oracle | (unnamed) | 4 | 0 |
| **Total** | **58** | **58** | **20** |

Two findings that matter:

1. **The guide's 28+11+10 = 49, not 58.** The "58" is the *all-crates* raw
   `Py<PyAny>` occurrence count (49 in the three named crates + 9 in
   drc-rs/io-types/quality-oracle). The guide's breakdown names only the top
   three crates.
2. **Only 20 of the 58 were actually stored fields** — and all 20 were in
   `temper-design-bundle` (the pre-existing contract pyclasses from the Phase-2
   pivot). The 11 in `temper-constraint-compiler` and the 10 in
   `temper-rust-router` were **never stored fields**: every one is a return
   position, function parameter, or local in the pyo3 bridge. The guide's
   "deepest form of not-really-migrated" label therefore overstated the surface
   by ~2.9× on the stored-field measure.

### 1.2 Current totals (post-wave-1)

| Crate | Raw `Py<PyAny>` | Stored fields (all `Py<Py…>`) | Transient occurrences | Comments |
|---|---:|---:|---:|---:|
| temper-design-bundle | 290 | **153** (146 `PyAny` + 5 `PyDict` + 2 `PyList`) | 147 | 10 |
| temper-io-types | 21 | **8** (8 `PyAny`) | 12 | 2 |
| temper-constraint-compiler | 20 | **0** | 18 | 2 |
| temper-rust-router | 10 | **0** | 10 | 0 |
| temper-drc-rs | 14 | **0** | 18 | 0 |
| temper-quality-oracle | 4 | **0** | 4 | 0 |
| **Total** | **359** | **161** | **209** | 14 |

Stored-field baseline → current: **20 → 161** (+141).
Raw-occurrence baseline → current: **58 → 359** (+301).

### 1.3 The delta, attributed per merged PR

The wave-1 migrations **grew** the stored opaque-handle surface rather than
shrinking it. This is the program's own documented technique, not drift: the
Phase-2/3 contract migrations store every field as the caller's exact Python
object *by design*, so `Component("R1", "fp", (1, 2)).width` stays `int 1` —
"widening becomes unrepresentable, not merely untested"
(MIGRATION_PHASE_GUIDE.md § Phase 2; `netlist_contracts.rs` header lines 11–28).

| Merged PR | What it added/removed | Stored-field delta |
|---|---|---:|
| #701 contracts (board/netlist) | `board_contracts.rs` (62) + `netlist_contracts.rs` (36) opaque fields — the int-1/type-preservation pattern | +98 |
| #723 parse engine | `parse_engine.rs` (33) — token int-vs-float preservation | +33 |
| #716 config loaders | `temper-io-types` `PyFootprintSpec` (5), `PyReferenceAliasManifest` (2), `PyFootprintLibrary` (1) — type-preservation (FootprintSpec) + yaml-backed dicts | +8 |
| #712 loaders | `NetClassRulesDict` (2) in design-bundle | +2 |
| #715 constraints | `temper-constraint-compiler` — **removed nothing stored** (its 11 "fields" were transient; the migration converted the transient marshalling to the "data moves into Rust" form, see `constraints/slot.rs:7`, `constraints/py.rs:14`; transient count grew 11 → 18 as the new pyo3 bridges) | 0 (stored), −0 |
| #717 DRC | `temper-drc-rs` — stored 0 before and after; transient 2 → 18 (the kicad-cli JSON marshalling bridge) | 0 |
| #718 write engine | `temper-io-types/kicad_write.rs` — text-out, no handles | 0 |
| #720 physics | `temper-thermal` — no stored handles; KTD9 scipy keep documented | 0 |
| **Net** | | **+141** (20 → 161) |

The three crates the guide named as the deepest offenders: `temper-constraint-compiler`
and `temper-rust-router` have **zero** stored `Py<Py…>` fields on current main
(the guide's 11 and 10 were transient marshalling, and stay transient);
`temper-design-bundle` carries all 153, of which 141 were added by wave-1
contracts/parse migrations using the sanctioned opaque-storage technique.

---

## 2. Per-handle classification

Classes, per the audit brief:

- **REMOVABLE** — the underlying data now has a Rust-typed home (contract
  pyclass / parse type / config type) *and* the handle exists only because the
  data was Python. Replacement is a typed `Py<ConcretePyClass>` handle that
  preserves identity; the differential pins stay green.
- **INTENTIONAL** — the opaque-storage pattern is a deliberate design decision
  (type preservation int-vs-float, identity, no-coercion dataclass semantics,
  dynamic attributes, KTD9-kept Python computations).
- **STILL-NEEDED** — the data genuinely lives in Python and has no Rust home
  yet (router_v6/pipeline/heuristics/orchestration, ortools, cp_sat gates,
  pydantic `NetClassRules`, unmigrated constraint types, yaml-loaded dicts).

### 2.1 temper-design-bundle — 153 stored fields

| Struct | # | Field(s) | Line(s) | Classification |
|---|---:|---|---|---|
| `MountingHole` | 3 | `position`, `diameter`, `keepout_radius` | board_contracts.rs:165–169 | INTENTIONAL — type preservation |
| `Pad` | 6 | `position`, `size`, `shape`, `layer`, `number`, `net_name` | :240–250 | INTENTIONAL |
| `Component` (board) | 9 | `ref_`, `position`, `rotation`, `width`, `height`, `footprint`, `pads`, `layer`, `fixed` | :333–349 | INTENTIONAL |
| `Trace` | 5 | `start`, `end`, `width`, `layer`, `net` | :438–446 | INTENTIONAL |
| `Via` | 6 | `position`, `drill`, `width`, `layers`, `net`, `is_diff_pair` | :525–535 | INTENTIONAL |
| `Layer` | 4 | `name`, `layer_type`, `copper_weight`, `is_routable` | :631–637 | INTENTIONAL |
| `LayerStackup` | 2 | `layers`, `thickness` | :711–713 | INTENTIONAL |
| `Rect` | 4 | `x_min`, `y_min`, `x_max`, `y_max` | :942–948 | INTENTIONAL |
| `Zone` | 10 | `name`, `bounds`, `net_classes`, `components`, `weight`, `polygon`, `layers`, `max_size`, `can_expand`, `zone_type` | :1147–1169 | INTENTIONAL |
| `GroundDomain` | 3 | `name`, `bounds`, `star_point` | :1335–1339 | INTENTIONAL |
| `Board` | 10 | `width`, `height`, `origin`, `zones`, `mounting_holes`, `keepouts`, `ground_domains`, `layer_stackup`, `outline_polygon`, `zone_map` | :1430–1451 | INTENTIONAL |
| `Pin` | 11 | `name`, `number`, `position`, `net`, `width`, `height`, `shape`, `layer`, `drill`, `is_pth`, `roundrect_ratio`, `pad_rotation_deg` | netlist_contracts.rs:251–273 | INTENTIONAL |
| `Component` (netlist) | 13 | `ref_`, `footprint`, `bounds`, `pins`, `net_class`, `zone`, `fixed`, `initial_position`, `initial_rotation`, `initial_side`, `attributes`, `tags`, `sheetpath` | :422–446 | INTENTIONAL |
| `Net` | 6 | `name`, `pins`, `net_class`, `weight`, `max_current`, `voltage_class` | :625–635 | INTENTIONAL |
| `Netlist` | 5 | `components`, `nets`, `component_index`, `net_index`, `component_nets` | :747–755 | INTENTIONAL — mutable containers (in-place `append`, `#[pyclass(dict)]` dynamic attrs) |
| `TraceData` | 5 | `start`, `end`, `width`, `layer`, `net` | parse_engine.rs:2152–2160 | INTENTIONAL — token int-vs-float (header lines 30–50) |
| `PadData` | 9 | `position`, `size`, `shape`, `drill`, `rotation`, `layer`, `number`, `net`, `component_ref` | :2229–2245 | INTENTIONAL |
| `ViaData` | 5 | `position`, `diameter`, `drill`, `net`, `layers` | :2346–2354 | INTENTIONAL |
| `DrillDefinition` | 4 | `oval`, `diameter`, `width`, `offset` | :2429–2435 | INTENTIONAL (kiutils raw-list quirk reproduced, header lines 41–43) |
| `Position` | 4 | `x`, `y`, `angle`, `unlocked` | :2512–2518 | INTENTIONAL |
| `ParseResult.netlist` | 1 | `netlist` | :2592 | **REMOVABLE** → `Py<Netlist>` |
| `ParseResult.board` | 1 | `board` | :2594 | **REMOVABLE** → `Py<Board>` |
| `ParseResult` | 4 | `warnings`, `traces`, `vias`, `pads` | :2596–2602 | STILL-NEEDED — Python list containers; identity-mutable, no-coercion |
| `Violation` | 3 | `type`, `components`, `nets` | gates.rs:324–330 | `type` INTENTIONAL (enum member held for identity, no-validation dataclass semantics); `components`/`nets` STILL-NEEDED (tuples assembled by cp_sat Python gates) |
| `GateResult` | 2 | `status`, `violations` | :474–477 | `status` INTENTIONAL (same identity rationale); `violations` STILL-NEEDED (tuple built by cp_sat Python gates) |
| `BoardState` | 6 | `placement`, `routing`, `netlist`, `board`, `design_rules`, `routed_pcb_path` | :569–579 | `netlist`/`board`/`design_rules` **REMOVABLE** → `Py<Netlist>`/`Py<Board>`/`Py<DesignRules>`; `placement`/`routing`/`routed_pcb_path` STILL-NEEDED (router_v6 results / pipeline path, Phase 5) |
| `DesignRules` | 8 | `net_classes`, `net_overrides`, `net_class_assignments`, `differential_pairs`, `bus_cohorts`, `net_topologies`, `via_templates` (7) + `class_pairs` (1) | design_rules.rs:345–357 | 7 STILL-NEEDED — hold unmigrated cross-module types (`NetClassRules` pydantic, `DifferentialPairConstraint`, `BusCohortConstraint`, `NetGraph`), documented at header lines 18–25 & 337–338; `class_pairs` INTENTIONAL — dynamically-attached attribute (`dr.class_pairs = {...}`), cannot be typed |
| `NetClassRulesDict` | 2 | `design_rules`, `class_pairs` | loaders.rs:204–205 | `design_rules` **REMOVABLE** → `Py<DesignRules>` (doc line 199–200: "design_rules is the `DesignRules` pyclass"); `class_pairs` STILL-NEEDED (plain Python dict of sorted-(str,str) keys, consumer-mutated) |
| `NetTypeSpec.target_layer` | 1 | `target_layer` | net_types.rs:277 | STILL-NEEDED — `str` OR `LayerIndex` IntEnum; `LayerIndex` is an R3 keep (pyo3 cannot subclass `int`), documented board_contracts.rs:31–45 |

**Subtotals (design-bundle): INTENTIONAL 128 · STILL-NEEDED 19 · REMOVABLE 6**

### 2.2 temper-io-types — 8 stored fields

| Struct | # | Field(s) | Line(s) | Classification |
|---|---:|---|---|---|
| `PyFootprintSpec` | 5 | `name`, `bounds`, `courtyard_margin`, `thermal_pad`, `pin_1_offset` | footprint_spec.rs:66–74 | INTENTIONAL — type-preservation-by-construction, documented lines 57–62 (`FootprintSpec("0805", (2, 1))` stores `int` bounds) |
| `PyReferenceAliasManifest` | 2 | `component_aliases`, `loop_aliases` | reference_aliases.rs:39–41 | STILL-NEEDED — validated alias maps backed by `yaml.safe_load` (deliberate YAML-1.1 keep, documented lines 11–15) |
| `PyFootprintLibrary` | 1 | `footprints` | footprint_library.rs:55 | STILL-NEEDED — dict registry of `FootprintSpec`, yaml-loaded |

**Subtotals (io-types): INTENTIONAL 5 · STILL-NEEDED 3 · REMOVABLE 0**

### 2.3 Crates with zero stored handles

`temper-constraint-compiler` (20), `temper-rust-router` (10), `temper-drc-rs`
(18), `temper-quality-oracle` (4) — all occurrences are transient return
positions / parameters / locals at the pyo3 boundary. Per the guide's own
reviewer ruling these are acceptable transient boundaries and are **not**
classified as removable. `temper-constraint-compiler`'s 20 include the
`yaml_value_to_py` / `builder_to_yaml_data` / `check_result_to_dict` /
`diagnostic_to_py_dict` bridges (py.rs:538–615, pyo3_bridge.rs:364) that build
Python dicts for the *Python* side to serialize (`json.dumps`, `yaml.dump` on
the shim) — the "data moves into Rust" form.

---

## 3. Summary and the guide-delta story

| Measure | Guide baseline | Current | Delta |
|---|---:|---:|---:|
| Raw `Py<PyAny>` occurrences (the guide's "58") | 58 | 359 | +301 |
| Stored `Py<Py…>` struct fields (the real "deep" measure) | 20 | 161 | +141 |
| — INTENTIONAL (type-preservation / identity / dynamic-attrs) | — | 133 | — |
| — STILL-NEEDED (data lives in Python; unmigrated surface) | — | 22 | — |
| — **REMOVABLE** (data has a Rust home; tighten the handle) | — | **6** | — |
| Transient marshalling (acceptable boundaries) | 38 | 209 | +171 |

The headline: **the eight wave-1 migrations did not remove a single stored
`Py<PyAny>` handle — they added 141** (all but 8 of them the sanctioned
type-preservation pattern). The guide's Phase-5 framing ("data lives in Python
and Rust carries a handle") needs updating: for the 133 INTENTIONAL fields the
data now lives in the Rust pyclass storage; the handles carry *typed* contract
objects, and the opacity is the deliberate bit-exactness technique, not
residual unmigrated state.

---

## 4. Removal wave plan

### Wave 1 — dispatch NOW (all dependencies migrated; pure handle tightening)

These six replacements change no reachable behavior — the values are always the
named Rust pyclass (same crate), identity is preserved by the typed handle, and
the differential pins assert the field surface and object identity, both
unchanged:

1. **`ParseResult.netlist: Py<PyAny>` → `Py<Netlist>`** (parse_engine.rs:2592).
   `build_netlist` always constructs a `netlist_contracts::Netlist`. Python
   side: `io/_kicad_types.py` is a pure-delegation re-export (verified).
   Pins: `tests/io/test_parse_engine_rust_differential.py` — the
   `ParseResult: ("netlist", "board", "warnings", …)` field-list (line 114)
   and `.netlist.components` consumers stay green.
2. **`ParseResult.board: Py<PyAny>` → `Py<Board>`** (parse_engine.rs:2594).
   `build_board` always constructs a `board_contracts::Board`. Same pins.
3. **`NetClassRulesDict.design_rules: Py<PyAny>` → `Py<DesignRules>`**
   (loaders.rs:204). Doc states the value is the `DesignRules` pyclass.
   Python side: `io/netclass_loader.py` is a pure-delegation re-export
   (verified). Pins: `test_loaders_rust_differential.py` — `copied.design_rules
   is rust.design_rules` (line 358) and `rust.design_rules.class_pairs is
   rust.class_pairs` (line 316) are identity assertions, preserved.
4. **`BoardState.netlist: Py<PyAny>` → `Py<Netlist>`** (gates.rs:573).
5. **`BoardState.board: Py<PyAny>` → `Py<Board>`** (gates.rs:575).
6. **`BoardState.design_rules: Py<PyAny>` → `Py<DesignRules>`** (gates.rs:577).

   Verified call sites pass the contract pyclasses: `router_v6/benchmark.py:82`
   (`BoardState(board=result.board, netlist=filtered_netlist)`),
   `cli/__init__.py:633`, `profiling/timing_gate.py:242`, `gates.py` re-exports
   `BoardState` from `_tdb`. Constructor takes `Option<&Bound<PyAny>>` with
   `None` default → becomes `Option<Py<Netlist>>` etc. Pins:
   `tests/placer/cp_sat/test_gate_contract.py::TestBoardState` — no test
   asserts a non-contract payload flows through (they construct `BoardState()`
   empty and with `board=`/`netlist=` kwargs).

### Wave 2 — wait on the router_v6 / pipeline / heuristics session (Phase 5)

- `BoardState.placement` / `routing` / `routed_pcb_path` — the payloads are
  router_v6 results and a pipeline path. Tighten alongside the Phase-5
  orchestration migration (they become internal Rust calls once the pipeline
  migrates, per the guide's "strangler wrapper" collapse).
- `Violation.components` / `nets` and `GateResult.violations` — assembled by
  cp_sat Python gates, which are **JUSTIFIED-KEEP** (ortools boundary). These
  handles are permanent unless the keep is re-decided; at most tighten
  `Py<PyAny>` → `Py<PyTuple>` for clarity, keeping the tuples Python-built.
- `DesignRules`' seven containers — hold pydantic `NetClassRules` +
  `DifferentialPairConstraint` / `BusCohortConstraint` / `NetGraph`. Removable
  only when those cross-module types migrate (Phase 2/4 residuals) or when a
  typed-container redesign is decided. The `net_graph` types are Phase-2
  MIGRATE-pending; `differential_pair`/`_constraint_types` are Phase-2
  MIGRATE-pending.

### Wave 3 — wait on #721/#724 (pcl/placer, in flight elsewhere)

- `config_loader.rs:1679` calls `temper_placer.pcl.constraints`
  (`KeepoutConstraint`, `ConstraintTier`) — pure Python today. **When #721
  lands, this becomes a circular call-back (Rust → Python shim → same Rust
  crate); re-flag and retarget the call.**
- `config_loader.rs:1894` calls `temper_placer._constraint_types` — pure
  Python dataclasses (Phase-2 MIGRATE-pending). Same watch.
- `config_loader.rs:1173/1207` calls `temper_placer.core.net_graph`
  (`NetGraph`/`SubNetEdge`) — pure Python dataclasses (Phase-2 MIGRATE-pending).
  Same watch.

### Never (INTENTIONAL — do not dispatch)

- All 62 board_contracts + 36 netlist_contracts + 27 parse data-type fields +
  5 io-types `PyFootprintSpec` fields. Removing them requires either accepting
  int→float widening (rejected by the documented design decision) or inventing
  a typed `Int|Float` union storage — a new design decision with its own
  differential, not a cleanup.
- `Violation.type` / `GateResult.status` — identity-held enum members;
  `DesignRules.class_pairs` — dynamic attribute. Typing any of these changes
  no-coercion dataclass semantics.

---

## 5. Circular call-backs (Rust → Python → same crate)

Flagged specifically per the audit brief. A call-back into a module that is a
delegation shim over the *same* crate is indirection, and where the target
object is itself a Rust pyclass it is removable:

1. **`loaders.rs:316–317`** — `py.import("temper_placer.core.design_rules")`
   then `DesignRules()`: the shim re-exports this crate's `DesignRules`
   pyclass. **CIRCULAR** — replace with `py.get_type::<DesignRules>()` directly.
   The `NetClassRules` (pydantic) and `TEMPER_NET_ASSIGNMENTS` (Python
   constant) lookups in the same function are genuinely Python and stay.
2. **`config_loader.rs:1954–1956`** (`constraints_to_design_rules`) — same
   `temper_placer.core.design_rules` shim for `DesignRules()`/`NetClassRules`.
   **CIRCULAR for the `DesignRules` half**; `NetClassRules` and
   `DifferentialPairConstraint` (`core/differential_pair.py`, pure Python) stay.
3. **`config_loader.rs:1838`** — `temper_placer.io.config_loader` shim to reach
   `ConfigValidationError`. The *module* is a shim of this crate, but the
   target (a Python exception class) genuinely lives in Python — exceptions
   have no pyclass mapping. **PARTIALLY circular**; keep, but note the code
   already carries a defensive fallback for the import-cycle fragility
   (lines 1845–1849).
4. **Watch-list (become circular when their surfaces migrate):**
   `config_loader.rs:1173/1207` (net_graph, Phase-2 MIGRATE-pending),
   `config_loader.rs:1679` (pcl, #721 in flight), `config_loader.rs:1894`
   (`_constraint_types`, Phase-2 MIGRATE-pending).

No call-back targets a *migrated* module and should be removed today other than
the three `DesignRules`-via-shim cases above (items 1–2), which are the only
true Rust→Python→Rust circles on main.

---

## 6. Deliberate boundary keeps (call-backs) — inventory

These are the R1a/R3-argued keeps. Listed per crate with the in-source argument
location; none are removable while their documented boundary holds.

**temper-design-bundle**
- `yaml.safe_load` — loaders.rs:293, config_loader.rs:1869 — PyYAML is YAML 1.1,
  `serde_yaml` 1.2 disagrees (documented loaders.rs:21–23).
- pydantic `model_validate` — config_loader.rs:1879 — never reimplemented
  (documented `io/config_loader.py` shim header).
- numpy array materialization — board_contracts.rs:65, netlist_contracts.rs:195 —
  dtype/bit-parity by delegation (netlist_contracts.rs:41–49).
- `dataclasses.FrozenInstanceError` — board_contracts.rs:115 — exact frozen-error
  type/message (board_contracts.rs:14–22).
- `sys`/`warnings` — board_contracts.rs:797–798 — warning parity.
- `builtins.min`/`max` — board_contracts.rs:1612 — bounds parity.
- `re` + `hashlib` — netlist_contracts.rs:952–953 — `find_isomorphic_groups`
  label prefix + hash parity.
- `builtins.round`/`builtins.sorted` — reference_loader.rs:40–46 — the
  candidate-6 determinism pins (half-to-even round; sort-key semantics).
- `logging` — config_loader.rs:1735/1762, loaders.rs:380 (`getLogger`) —
  logger/warning parity.
- `str.strip` — config_loader.rs:508 — Unicode-whitespace semantics.
- Cross-module Python constructors: `core.net_graph`, `pcl.constraints`,
  `_constraint_types`, `core.differential_pair` (see §5 watch-list).

**temper-io-types**
- `yaml.safe_load` — footprint_library.rs:44, reference_aliases.rs:151;
  `pathlib.Path` — footprint_library.rs:252, reference_aliases.rs:106;
  `str.strip` — reference_aliases.rs:180–183. All documented in the module
  headers (YAML 1.1 authority; Unicode strip).

**temper-drc-rs**
- `builtins.float`/`str` — validation.rs:506/597 — kicad-cli JSON number/string
  semantics; GEOS / `scipy.spatial.ConvexHull` / `kicad-cli` stay Python
  (validation.rs:21–23).

**temper-thermal**
- scipy `spsolve` (SuperLU) — KTD9 keep, thermal_scorer.rs:7, lib.rs:28,
  fdm.rs:338; `tj_cross_check` stays Python (tj_cross_check.rs:12).

**temper-constraint-compiler / temper-rust-router** — no Python call-backs
(they produce Python objects for the shim / marshal Python objects into Rust
types, respectively).

---

## 7. Verified spot-checks (REMOVABLE claims vs the Python side)

1. `ParseResult.netlist` → `io/_kicad_types.py` is a **pure-delegation
   re-export** of `temper_design_bundle_python.parse_engine`; the value is a
   `netlist_contracts::Netlist` pyclass built by `build_netlist`
   (parse_engine.rs:2840). Source of truth is Rust. ✓
2. `NetClassRulesDict.design_rules` → `io/netclass_loader.py` is a
   **pure-delegation re-export**; the field doc (loaders.rs:199–200) names the
   `DesignRules` pyclass. Source of truth is Rust. ✓
3. `BoardState.netlist/board` → `placer/cp_sat/gates.py` re-exports `BoardState`
   from `_tdb` (lines 72–77); call sites pass `Board`/`Netlist` pyclass
   instances (`router_v6/benchmark.py:82`, `cli/__init__.py:633`). Source of
   truth for the *payload objects* is Rust. ✓
4. (Negative control) `Component.width` int-1 preservation — verified
   INTENTIONAL per the audit brief: `netlist_contracts.rs:11–28` documents the
   no-coercion dataclass semantics and the type-preservation-by-construction
   choice. Not removable.

---

## 8. Recommended follow-ups

1. Update `docs/MIGRATION_PHASE_GUIDE.md` § Phase 5's boundary figure: the "58
   `Py<PyAny>` fields / 28–11–10" paragraph should be re-worded to the stored
   vs transient distinction (20 → 161 stored; 0 in cc/rr) so future
   measurements compare like for like.
2. Dispatch Wave 1 (six typed-handle tightenings) as a single small PR; it
   removes the only currently-removable handles and the three `DesignRules`
   circular indirections in one pass.
3. Re-run this audit when #721/#724 land and when any Phase-2 core/ surface
   (`net_graph`, `differential_pair`, `_constraint_types`) migrates — each
   turns a watch-list call-back circular and/or makes a STILL-NEEDED field
   REMOVABLE.
