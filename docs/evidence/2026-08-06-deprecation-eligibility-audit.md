# Deprecation eligibility audit — what Python can be deleted NOW

<!-- provenance: commit=a365f0906 (origin/main HEAD at audit time) branch=docs/deprecation-audit
     date=2026-08-06 method=AST import-gate over src/ + tests/ + scripts/ + benchmarks/ (grep-verified),
     differential-mapped shim population, ledger + handoff cross-check, per-mutant campaign analysis -->

**Purpose.** Determine, per the goal-set deprecation criteria
(`docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md` D6 / R19–R22 and the
guide's Deprecation section), which Python under the Wave-4 migration can be
**deleted now**, with evidence. Investigation + docs only — no production code
was changed.

**Headline answer.**

| Category | Criterion | Deletable now | LOC |
|---|---|---|---|
| RETIRE-now (dead/obsolete) | RETIRE verdict not yet landed | **0 files** — every RETIRE verdict has already landed | 0 |
| R21 (shim removal) | zero importers (import gate, not search) | **3 pure-delegation shims** | **114** |
| R20 (differential removal) | PBT/MR suites catch every campaign mutant | **0 differentials** (4/4 sampled = RETAIN) | 0 |
| R22 (blockers hold) | no JUSTIFIED-KEEP blocker lifted | all verified holding | n/a |

**Total deletable NOW: 3 files / 114 LOC.** The only Python that the deprecation
rules license today is the R21 zero-importer shim set. Everything else is gated
behind R20's campaign re-run (a follow-up, not a current deletion).

---

## 0. Ledger and nomenclature

Two naming facts the audit had to reconcile:

1. **There are no `*_py.py` shim files in the repo.** The audit brief named the
   shims "the `*_py.py` files under temper_placer". The actual convention (per
   `docs/MIGRATION_PHASE_GUIDE.md` and every migration's docstring): the shim is
   the **src module that keeps the pre-migration public API and re-exports the
   Rust pyo3 classes** (e.g. `core/priority.py` re-exports
   `temper_design_bundle_python` pyclasses), and the oracle is the
   **`_*_py_oracle.py`** file retained verbatim under `tests/`. The `*_py.py`
   glob matches nothing; the shim population below is the oracle-derived set.
2. **Shims vs oracles.** The differential tests import the Rust extension and
   the **oracle directly** — not the shim. This is what makes R21 shim removal
   safe: deleting the shim leaves the oracle and the differential intact.

**Shim population.** 86 src modules are migration shims, derived by mapping each
`_*_py_oracle.py` in the test suite to its src module of the same base name
(89 oracles → 86 shims; the three extras are the `_parse_engine_py_oracle/`
package and shared `_contract_canon`/`_drc_contract_canon` helpers). The full
importer-count table for all 86 is in the appendix.

---

## 1. RETIRE-now — all RETIRE verdicts have landed (0 candidates)

Every RETIRE verdict recorded anywhere in the program resolves to a file that
**no longer exists**:

| Verdict | Source | Status |
|---|---|---|
| `core/loss_types.py` → RETIRE | program plan (Phase 2 residual), handoff #622 | **deleted** by #657 (`refactor(placer): retire core/loss_types.py, rewire its 7 consumers`, 207 LOC removed, 7 consumers rewired) |
| `scripts/internal_route.py` → RETIRE | ledger (`docs/wave4-verdicts.yaml`) | **deleted** by #708 (2026-08-04) |
| `scripts/placement_quality_report.py` → RETIRE | ledger | **deleted** by #708 (2026-08-04) |

Additional dead-code removals landed as plain `chore(router_v6/pipeline)` PRs,
not RETIRE-verdict deletions: `router_v6/sat_model.py`,
`router_v6/metrics/octilinear.py` (#745), `router_v6/quality/corridor.py` (#755),
`pipeline/topology_phase.py` (#817).

**Nothing in the RETIRE category is a deletion candidate now.** The two RETIRE
**ledger entries** at `wave4-verdicts.yaml:533` and `:545`, and the stale
`exclude:` carve-outs for the same two deleted files inside the `scripts/*.py`
pattern (lines ~452–460), still reference files that no longer exist — this is a
**ledger-hygiene** finding (the close-out audit 2026-08-06 Sec 4 already flags
it), a docs edit, not a Python deletion. The ledger's own convention
(`2026-08-04-wave4-residual-verdicts.md` Sec 9.1) is that an entry scoped to a
file that no longer exists "exempts nothing and reads as a live gap that is
already closed" — those entries should be removed in the same PR that lands any
of the deletions below.

---

## 2. R21 — zero-importer delegation shims (3 candidates, 114 LOC)

**Criterion (guide):** a shim is removed only when *no consumer imports it*,
demonstrated by the **import gate** (AST import resolution across
`src/`, `tests/`, `scripts/`, `benchmarks/`) rather than by search.

**Gate evidence (grep-verified, not `search`):** an AST pass resolved every
`import`/`from` (absolute and relative, level≥0) for all 86 shims against
`src/` + `tests/` + `scripts/` + `benchmarks/`, then each zero-count was
re-verified with a repo-wide `grep` for the module path and every exported
symbol, plus a check for CLI / `python -m` / console-script / `__init__`
re-export invocation (the guide's "import-dead is not reference-free" caution).

Three shims have **zero importers** and no alternate invocation surface:

| Shim | LOC | Re-exports (from) | Verification that still covers it |
|---|---|---|---|
| `deterministic/stages/routing_metrics.py` | 23 | `NetMetrics, RoutingMetrics, SegmentMetrics` (`temper_design_bundle_python`) | `test_routing_metrics_rust_differential.py` + `test_routing_metrics_pbt.py` — both import the extension and `_routing_metrics_py_oracle.py` **directly**, never the shim |
| `deterministic/stages/sequential_routing_dataclasses.py` | 20 | `DiffPairConfig` (`temper_design_bundle_python`) | `test_sequential_routing_dataclasses_rust_differential.py` (+ PBT) import the extension + oracle directly |
| `deterministic/geometry/via_placement.py` | 71 | `PadInfo` (kept Python dataclass) + `distance, is_via_position_valid, place_via_with_clearance` (`temper_geometry`) | `test_via_placement_rust_differential.py` + `test_via_placement_pbt.py` import `temper_geometry` + `_via_placement_py_oracle.py` directly |

**Grep evidence for each zero count** (repo-wide, excluding the shim itself,
its oracle, its differential/PBT, `__pycache__`, `.git`):

- `routing_metrics`: only matches are the local `_compute_routing_metrics`
  helper in `validation/human_reference_extractor.py` + its oracle (a different
  function), the mutation-driver script `scripts/phase5_batch2_mutations.py`
  (targets the **Rust** `src/routing_metrics.rs`), and docs/plans history.
  No `__init__.py` re-exports it (`deterministic/stages/__init__.py` has no
  `NetMetrics`/`SegmentMetrics`/`RoutingMetrics`).
- `sequential_routing_dataclasses`: only the shim's own docstring +
  `scripts/manifest.yaml` (a description string of the mutation driver) +
  `scripts/phase5_batch2_mutations.py` (Rust target). No `DiffPairConfig`
  import anywhere; `deterministic/stages/__init__.py` does not re-export it
  (the pre-migration plan that promised that re-export is superseded — the
  stage it served was itself retired).
- `via_placement`: the module `temper_placer.deterministic.geometry.via_placement`
  is imported nowhere. All `via_placement` imports in the tree target
  `temper_placer.router_v6.via_placement` (a different module, 32 importers).
  `deterministic/geometry/__init__.py` and `deterministic/__init__.py` do not
  re-export it. The only `PadInfo` hits elsewhere are unrelated local class
  definitions.

**Why the oracle and differential survive the shim deletion.** The guide's
oracle debt applies: the deletion target is the **shim alone**; the oracle
(`_*_py_oracle.py`) and the differential (`test_*_rust_differential.py`) stay
because R20's re-run evidence depends on them. Verified for all three: the
differential/PBT files contain zero imports of the shim module (they pin the
Rust extension against the pinned oracle), and `scripts/oracle_hashes.json` pins
the oracle files themselves, which are untouched.

**Near-misses that are NOT candidates** (listed so the zero-row is not
misread as exhaustive):

- `regression/measure_closure.py` (180 LOC, 0 importers) — **excluded**: it is
  invoked by the promotion gate as `python -m temper_placer.regression.measure_closure`
  (shelled out to by `tests/closure/test_router_completion.py`). Import-dead is
  not reference-free — the guide's exact caution. It is a marshalling/CLI
  module, not a pure delegation shim.
- Every other shim has ≥1 importer (see appendix). The most lightly-imported
  non-candidate shims (`core/graph` 1, `deterministic/geometry/grid_utils` 1,
  `deterministic/stages/fine_pitch_escape` 1, `heuristics/structural` 1,
  `manufacturing/monte_carlo` 1, `regression/cp_sat_comparison` 1,
  `validation/tht_check` 1) each have exactly one consumer that still uses the
  module path — R21 blocks them until that consumer is migrated or retired.

---

## 3. R20 — differential removability, sampled (4 modules, all RETAIN)

**Criterion:** a differential is removed only when the **property (PBT) and
metamorphic (MR) suites** are shown to catch every mutant the campaign caught —
i.e. re-run the campaign with the differential disabled. The full re-run is the
follow-up; this audit performs the sampling step: for each sampled module, take
the campaign's mutant list, and check whether each mutant's discriminating
assertion exists in the PBT/MR suites alone.

**Method per module:** campaign mutant list from the crate's `VERIFICATION.md`
and the mutation-sweep evidence docs → "Caught by" attribution → check whether
the discriminating assertion is (a) in a standalone `*_pbt.py` file, or (b)
inside the differential file (including `test_prop*`/`test_mr*` tests that live
inside `test_*_rust_differential.py` — those are part of the differential, not
the standalone PBT/MR suites).

### 3.1 `core/priority` (temper-design-bundle) — **RETAIN**

- Surface: 87 differential assertions (enum name/value/str/repr, value
  construction, dataclass defaults/round-trip, full `repr(...)` byte-for-byte,
  `classify_component`/`classify_net` per-branch, word-boundary regression set)
  + `test_priority_pbt.py` P1–P5 (each with a `test_pN_fails_for_<mutant>`
  vacuity mutant) + MR1–MR4.
- Discriminating assertions that exist **only** in the differential: repr
  byte-for-byte equality, dataclass default values, `repr` rendering of the
  enum members. P1–P5 pin classification outcomes and the `(name, value)`
  tables, not repr text or defaults. A mutant that changes `repr` formatting or
  a dataclass default survives P1–P5/MR1–MR4.
- **Verdict: RETAIN** — PBT/MR alone does not cover the byte-level repr/default
  surface the campaign (and the "survivors had to be closed" record in
  `2026-08-04-wave4-phase4-validation-mutation-sweep.md:52`) depends on.

### 3.2 Constraints (temper-constraint-compiler: builder/compiler/reporter) — **RETAIN**

- Campaign: 11 mutants, 10 caught, 1 provably equivalent
  (`VERIFICATION.md` §Anti-vacuity). Six survivors were closed by adding
  exact-boundary cases to the **differential** ("the random differential almost
  never lands exactly on a threshold").
- Per-mutant discriminating assertions:
  - M1/M2/M6/M11 (threshold `<`/`<=`/`>=`/`>` flips) → exact-10.0mm cases **in
    the differential**. PBT P3 (`SATISFIED iff dist >= threshold`, bit-exact)
    and MR1 (crossing a threshold flips status) exist, but MR1 crosses at
    5.0/15.0, never at equality, and P3's random corpus almost never samples
    `dist == min` exactly — the campaign record explicitly says so.
  - M4 (Neumaier → naive sum) → the crafted centroid cancellation case
    `(1e16+1-1e16)/3`, differential-only; no property forces that input.
  - M5 (message threshold `py_float_str` → `{:.1}`) → multi-decimal message pin
    (`10.25mm` vs `10.2`), differential-only.
  - M3/M7/M8/M10 → random scorer differential + rejection/empty-string cases
    (differential domain).
- **Verdict: RETAIN** — at least M1/M2/M4/M5/M6/M11 are caught only by
  differential assertions the PBT/MR suites do not contain.

### 3.3 DRC checks (temper-drc-rs: validation slice + drc_contracts + clearance validator) — **RETAIN**

- Phase-4 validation sweep (12 mutants) — the record is explicit: "**Every
  mutation was caught by at least one differential assertion**"
  (`2026-08-04-wave4-phase4-validation-mutation-sweep.md:50-52`).
- drc_contracts (11 mutants, `2026-08-06-wave4-phase2-drc-contracts-mutation-sweep.md`):
  the killing tests `test_prop1_severity_weight_table`, `test_prop2_run_result_passed_fail_closed`,
  `test_mr1_merge_is_order_preserving_concatenation`, `test_prop3/4_*` all live
  **inside** `tests/validation/test_drc_contracts_rust_differential.py`
  (verified by grep — those names resolve to the differential file only). They
  are part of the differential, not the standalone PBT suite.
- Clearance validator M9–M13 (`2026-08-05-wave4-phase5-mutation-sweep.md`):
  all caught by clearance differential pins (same-domain pairing, `measured_mm`
  bit pins, worst-first pins, verify_iec pins, WARNING-record comparison). The
  PBT pins row-count/insulation-class invariants that a halved `min_clr`
  (M12) does not disturb.
- **Verdict: RETAIN** — every sampled mutant is caught only inside the
  differential files.

### 3.4 Loaders (temper-io-types / design-bundle parse-engine: config_loader, netclass_loader, reference_aliases, footprint_library) — **RETAIN**

- Campaign: 10 parse-engine mutants (`temper-design-bundle/VERIFICATION.md` §
  Mutation campaign). Discriminating assertions:
  - M1 (bounds-check dropped) → error-parity, differential.
  - M2 (`yaml.safe_load` → `BaseLoader`) → YAML-1.1 scalar-typing parity; proves
    the PyYAML call-back is load-bearing — no PBT/MR property asserts the
    PyYAML scalar-typing behavior.
  - M4 (`str.strip` → `str::trim`) → escape-decoded-C0-control fixture,
    differential + Rust unit test; no property covers the Unicode-whitespace
    divergence.
  - M6/M10 (default flips) → production-fixture differentials (no property
    pins defaults).
  - M8 (CPython `round` → `f64::round`) → exact-tie (`0.0625`) discriminator;
    a random PBT corpus cannot be expected to land on exact ties (survived the
    first whole-number-only run).
  - M5/M7/M9 → PBT P3/P1/P5 partially (these are the three the PBT genuinely
    covers) — but that does not rescue the differential while M1/M2/M4/M6/M8/M10
    need it.
- **Verdict: RETAIN** — six of ten mutants are differential-only; the PyYAML /
  `str.strip` call-back mutants are structurally uncatchable by a property suite
  (they are parity claims against the pinned oracle's runtime behavior).

### 3.5 Sample result

| Module | Campaign mutants | Any mutant only caught by the differential? | Verdict |
|---|---|---|---|
| priority | PBT-vacuity + repr/default surface | yes (repr byte-for-byte, defaults) | **RETAIN** |
| constraints (builder/compiler/reporter) | 11 (10 caught + 1 equivalent) | yes (exact-threshold ×4, Neumaier, message fmt) | **RETAIN** |
| drc checks (validation + contracts + clearance) | 12 + 11 + 5 | yes (all — records say "differential assertion") | **RETAIN** |
| loaders (parse-engine) | 10 | yes (6 of 10, incl. call-back parity) | **RETAIN** |

**0 of 4 sampled differentials are removable now.** Supporting micro-finding on
the R21 candidates' own kernels: `routing_metrics`' PBT P2 asserts
`avg_iterations_per_segment == sum/total` (the **unrounded** ratio), so the
campaign's "avg rounding dropped" mutant (M15) would **pass** P2 and is caught
only by the differential's bit-exact `round(x, 2)` pin — a concrete example of
the differential carrying assertions no property does.

This is a sample, not the gate. The full R20 pass is the follow-up: re-execute
each campaign with the differential disabled (the drivers exist:
`scripts/phase5_batch2_mutations.py` and the sweep records) and count survivors.
Given 4/4 RETAIN on sampling, the prior is that few (likely zero) differentials
clear R20 today.

---

## 4. R22 — every JUSTIFIED-KEEP blocker still holds

The ledger's JUSTIFIED-KEEP surfaces were re-checked against their named
blockers. **No blocker has been lifted.**

| Surface | Blocker | Check (2026-08-06) |
|---|---|---|
| `placer/cp_sat/**` | ortools CP-SAT boundary (R4, Phase-1 KEEP) | holds — `model.py:14` still `from ortools.sat.python import cp_model`; no Rust drop-in |
| `io/**` kiutils boundary | parent-R4 keep | holds — `_parse_board.py:32` still `from kiutils.board import Board` |
| `router_v6/channel_skeleton.py` shapely Voronoi | spike-gated keep | holds — `channel_skeleton.py:13-14` still `shapely` `voronoi_diagram` |
| `router_v6/bottleneck_geometry.py` networkx min-cut | partition-order follow-up | holds — min-cut still networkx (kept-Python wrapper) |
| `physics/**` scipy spsolve (KTD9) | recorded solver-keep | holds — `thermal_fdm.py` still `scipy.sparse`, `loop_area.py` still `scipy.spatial` |
| `visualization/**` | Plotly acceptance unassertable; not on product path | holds — `board_renderer.py` still `plotly.graph_objects` |
| `scripts/*.py`, `scripts/_lib/**`, `scripts/tests/**` | fail-closed independence + bootstrap + measured CI cost | holds — gates still run on bare `python3`; no prebuilt gate binary shipped (the re-decision condition) |
| `benchmarks/**` | perf A/B must host the Python arm | holds — `perf_ab.py` still imports the verbatim oracle copy (imports an oracle module from an explicit path, lines 19-26/145) |
| `tests/**`, `testing/**`, `fixtures/**` | harness independence + R20 oracle duty | holds — differential oracles still present (89 oracle files), no Rust-only harness |
| regression harness (runner/reporter/corpus_runner/metrics_recorder/cli/manifest) | harness independence | holds — still imported by gate jobs + pytest |
| `fields/**` | no portable compute (numpy containers) | holds |
| `profiling/**` | dev instrumentation, zero hot-path compute | holds |
| `__init__.py`/`__main__.py`/`_version.py` | hatchling distribution root + console entry points | holds — `temper-placer/pyproject.toml` build-backend is still `hatchling.build` |
| `protocol.py` | `@runtime_checkable` structural typing, no pyclass mapping | holds |
| `strategy_registry.py` | import-time registry surface (D6) | holds — still consumed by `runner.py` and the `adapters/` modules |
| `pcl/constraints.py`, `router_v6/routing_results.py` | handoff recorded blockers, **overturned** by product authority (always-migrate), ledger says MIGRATE | ledger state is MIGRATE; no deprecation is blocked by these |

Note the two stale carve-out exclusions in the ledger (Sec 1) reference deleted
files — they are ledger hygiene, not a blocker; the scripts/ blocker itself
still holds.

---

## 5. The oracle debt (the other arm)

The ~89 oracle files (`_*_py_oracle.py` under `tests/`) + 126 differential
files are the retained R20 evidence base. The audit's standing rule, confirmed
for every finding above:

- **Deleting a shim keeps the oracle** — the differential continues to pin the
  Rust extension against the pinned verbatim oracle. Verified for all three R21
  candidates: the differential/PBT files never import the shim.
- **The deletion target is the shim + its differential together, never the
  oracle alone.** Oracle deletion happens only at state 3 (shim *and* oracle
  removed), gated by R20's campaign re-run. None of the sampled differentials
  qualifies, so **no oracle should be deleted now**.
- `scripts/oracle_hashes.json` / `scripts/check_oracle_hashes.py` pin the oracle
  files and are unaffected by shim deletion.

---

## 6. Deletable LOC totals

| Category | Files | LOC |
|---|---|---|
| RETIRE-now | 0 | 0 |
| R21 zero-importer shims | 3 | **114** (23 + 20 + 71) |
| R20 sampled candidates | 0 | 0 |
| **Total deletable now** | **3** | **114** |

For scale: the Wave-4 product surface is measured at 123,568 LOC (plan, R8
re-measure 2026-08-03); 114 LOC is ~0.09% of that — the deprecation program is
correctly pointing at the *next* unlock (R20 re-runs), not at volume today.

---

## 7. Recommended deletion sequence

**PR A — R21 shim deletion (the only code deletion licensed now):**
delete `deterministic/stages/routing_metrics.py`,
`deterministic/stages/sequential_routing_dataclasses.py`, and
`deterministic/geometry/via_placement.py` (−114 LOC). Include in the same PR:
- the ledger hygiene edit (remove the two stale `exclude:` carve-outs and the
  two stale RETIRE entries in `docs/wave4-verdicts.yaml`, on the repo's own
  Sec 9.1 precedent), and
- no changes to `deterministic/stages/__init__.py` /
  `deterministic/geometry/__init__.py` (neither re-exports the deleted names).
- CI evidence: differential + PBT + oracle-hash gates stay green (they target
  the Rust extension and oracles directly). No `@req`/TRACEABILITY sentinel
  concern: these are `deterministic/` modules (not under a TRACEABILITY sentinel
  tree) — confirm before commit if the sentinel scope has changed.

**PR B — ledger + docs follow-up (non-code):** already folded into PR A.

**PR C — R20 evidence-producing run (no deletion):** re-execute the mutation
campaigns for priority, constraints, drc checks, and loaders with the
differential disabled, to confirm the sampled RETAIN verdicts and to start the
R20 backlog. Drivers exist (`scripts/phase5_batch2_mutations.py`); the sweep
evidence docs record the exact per-mutant protocol. Nothing is deleted here.

**PR D — state-3 deletions (future, gated):** any differential that R20 clears
(unlikely per the 4/4 RETAIN sample) becomes a shim+oracle+differential removal
target, in dependency order (lowest-importer shims first — the R21 set was
already done in PR A).

**Dependency order:** A (standalone) → C (needs A's deletion only so the shims
are gone from the tree) → D (needs C). No PR depends on the RETIRE ledger cleanup
beyond being committed with A.

---

## 8. Items needing a decision

1. **The three R21 deletions themselves** — they are licensed by the import
   gate, but deleting the module paths removes the last Python surface through
   which `NetMetrics`/`SegmentMetrics`/`RoutingMetrics`/`DiffPairConfig`/
   `deterministic`-geometry via placement were constructible in-repo. Any
   out-of-repo consumer of those paths would break (the gate is repo-scoped, per
   the guide). Confirmed no in-repo consumer exists.
2. **The stale ledger carve-outs/RETIRE entries** (`wave4-verdicts.yaml:452-460`,
   `:533`, `:545`) — delete as part of PR A (recommended) or as a docs-only PR.
3. **The R20 full re-run** — schedule it (PR C) as the next deprecation step;
   the sample strongly predicts all-RETAIN, so the re-run is cheap evidence,
   not a deletion pipeline.
4. **`regression/measure_closure.py`** — zero importers but CLI-invoked; not an
   R21 candidate under the guide's own caution. If its promotion-gate consumer
   (`tests/closure/test_router_completion.py`) is ever migrated/retired, it
   becomes the next R21 candidate. Flag for Phase 6.
5. **Zero-importer non-shim modules** (sidebar, out of scope here): 32 modules
   beyond the shims have zero importers (e.g. `pipeline/dag_engine` 471 LOC,
   `io/net_class_manager` 524 LOC, `visualization/routing_health` 469 LOC,
   `core/power_topology` 248 LOC, `pipeline/andon_observer` 207 LOC). These are
   not shims, so they are not R21 candidates — they are RETIRE-justification
   candidates under R3 and need the written dead-code procedure, not this
   audit's rules. Recommend a follow-up sweep for the MIGRATE-phase surfaces
   among them.

---

## Appendix — R21 importer counts for all 86 shims (import gate)

| importers | shim (LOC) |
|---|---|
| 213 | core/netlist (183) |
| 179 | core/board (314) |
| 55 | io/config_loader (113) |
| 43 | core/design_rules (379) |
| 42 | placer/cp_sat/gates (1144) |
| 32 | router_v6/via_placement (177) |
| 27 | core/loop (72), geometry/kicad_transform (164) |
| 20 | io/netclass_loader (56) |
| 16 | router_v6/constraints_geometry (214), validation/drc_types (185) |
| 14 | regression/closure_test (478) |
| 12 | validation/prereg/schema (223) |
| 11 | topological/graph (332) |
| 10 | deterministic/bottleneck_map (193), deterministic/channels (294), validation/netlist_reconciliation (366) |
| 9 | core/net_types (78), router_v6/layer_assignment (557) |
| 8 | deterministic/feedback/violation_mapper (96), placer/cp_sat/loop (91), router_v6/congestion (524), validation/drc_fence (511) |
| 7 | io/dsn_exporter (180), metrics/quality (574), physics/operating_point (887), validation/placement_roundtrip (407) |
| 6 | constraints/compiler (241), pcl/tag_dispatch (280), regression/drc_ratchet (948), topological/zone_solver (191) |
| 5 | constraints/reporter (170), deterministic/stages/zone_geometry (105), io/dsn (86), io/loop_loader (163), io/reference_loader (315), regression/physics_oracle (496), topological/force_refinement (228), topological/initial_placement (293), validation/preflight (502) |
| 4 | constraints/builder (346), core/priority (86), deterministic/feedback/zone_adjuster (87), deterministic/stages/layer_assignment (79), deterministic/stages/slot_generation (54), geometry/drc_inflate (329), regression/reporter (152), router_v6/net_ordering (361), topological/propagation (193) |
| 3 | deterministic/feedback/drc_parser (51), deterministic/seed_filter (78), deterministic/stages/component_assignment (247), deterministic/stages/connectivity_validation (145), deterministic/stages/phased_component_assignment_validator (351), deterministic/stages/zone_assignment (54), extraction/hypergraph_factory (125), io/footprint_library (20), physics/thermal_potential (594), regression/fingerprint (134), report/formatter (50), report/summary (37), validation/drc_oracle (678), validation/geometric (583) |
| 2 | cli/timing (827), cli/trace_commands (136), deterministic/stages/net_ordering (47), deterministic/stages/power_plane (148), io/reference_aliases (13), manufacturing/stackup_validator (66), manufacturing/tolerances (49), pipeline/preflight (286), regression/schema_validator (115), report/generator (144), router_v6/power_plane (319), validation/human_reference_extractor (610) |
| 1 | core/graph (105), deterministic/geometry/grid_utils (62), deterministic/stages/fine_pitch_escape (319), heuristics/structural (808), manufacturing/monte_carlo (65), regression/cp_sat_comparison (113), validation/tht_check (69) |
| **0** | **deterministic/geometry/via_placement (71), deterministic/stages/routing_metrics (23), deterministic/stages/sequential_routing_dataclasses (20)** |

(The counts include the shim's own oracle/differential imports where the
test-side helper modules import the shim for fixtures — e.g. several oracle
fixture builders import `core/netlist` for constructor parity, inflating the
heaviest rows. The three zero rows are clean under both the AST gate and the
repo-wide grep.)
