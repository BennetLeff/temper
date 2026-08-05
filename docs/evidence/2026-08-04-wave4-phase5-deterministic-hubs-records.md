<!-- provenance: base=origin/main@15110fecc (dispatch base; all measurements above taken against it) branch=feat/wave4-phase5-deterministic-hubs-rust dirty=false -->
# Wave 4 Phase 5 — deterministic hubs slice: per-module verdicts and R3-style orchestration records

Slice owner: this branch (`feat/wave4-phase5-deterministic-hubs-rust`), working
against `origin/main` @ `15110fecc`. Scope: the deterministic **hubs** — the
leaf stages' orchestrators (`state.py`, `stages/base.py`, `stages/setup.py`,
`feedback/*`) plus the hub-adjacent sidecar/scoring surfaces
(`channels.py`, `bottleneck_map.py`, `seed_filter.py`, `instrumentation.py`,
`flags.py`, `geometry/courtyard.py`, `geometry/guard_strip.py`).

The R1 gate evidence (differentials, anti-vacuity, structural proof, deviations)
lives in `packages/temper-design-bundle/VERIFICATION.md` ("Wave 4 Phase 5 —
deterministic hubs" section); this doc records the per-module verdicts, the
R3-style orchestration records, and the gate status table. The pyo3 surface is
mirrored in `packages/temper-placer/stubs/temper_design_bundle_python/
deterministic_hubs.pyi` (the shims type-check against it via `mypy_path`).

Program rule applied per module: **migrate the compute, keep the orchestration.**
A module becomes a delegation shim where real compute exists and can cross the
pyo3 boundary with native types; a module whose substance is orchestration glue
over surfaces that are themselves mid-migration gets an **R3-style record**
naming a concrete blocker (per `docs/plans/2026-08-01-001` R3: a JUSTIFIED-KEEP
requires a named blocker; "consolidation" alone is never sufficient). Nothing in
this slice changes the `docs/wave4-verdicts.yaml` verdict for
`deterministic/**` (MIGRATE phase 5) — these records are the phase-5 per-module
decisions *inside* that verdict, the same granularity the phase guide's
"survey before migrating" note calls for.

The leaf-stages slice (grid_utils/via_placement/slot_generation/zone_geometry/
zone_assignment) is owned by the parallel branch
`feat/wave4-phase5-deterministic-stages-rust`; **none of the files below are
owned by that branch**, and this slice adds no code to any stage module the
leaves own. `geometry/guard_strip.py` and `geometry/courtyard.py` were checked
against that branch — the leaves did not migrate them.

## Home-crate decision

All migrated compute in this slice lands in **`temper-design-bundle`** (the
`temper_design_bundle_python` extension). Rationale:

- The program plan names "deterministic state" as a Phase-2 contracts-as-pyclasses
  candidate and the reference Phase-2 migration (`core/priority.py` → `priority.rs`)
  established that crate as the home for deterministic-placer contracts + small
  kernels.
- `temper-design-bundle` already carries `regex` and the `py_float_str`/`py_str_repr`
  CPython-repr replicas; the crate's `VERIFICATION.md` is the mandated proof
  location.
- The `temper-geometry` crate (where the leaves put grid kernels) is geometry-only;
  the sidecar/scoring/feedback kernels here are not geometry. `temper-drc-rs`
  hosts the *engine's own* types, not KiCad report-parsing contracts, and the
  guide names it the boundary-dense target shape — we do not add boundary
  density to it.

## Modules migrated (delegation shims + full R1 gates)

| Module | Kernel(s) in `temper_design_bundle_python` | What crosses the boundary |
|---|---|---|
| `deterministic/channels.py` | `build_channel_index`, `ChannelIndex.penalty` | the worst-severity bottleneck index build (native grid + per-cell index) and the `routability_penalty` hot path (floor-to-cell, occupancy clamp, severity-weight math) |
| `deterministic/bottleneck_map.py` | `bottleneck_score_at`, `bottleneck_coerce_score` | `score_at`'s floor-to-cell O(1) lookup and the `_coerce_score` clamp |
| `deterministic/seed_filter.py` | `filter_seed_kernel` | the per-ref threshold accept/reject loop (insertion-order iteration) |
| `deterministic/feedback/violation_mapper.py` | `map_violation_kernel` | component-ref regex extraction, via/PTH detection, zone containment, description clearance extraction, sorted component set |
| `deterministic/feedback/zone_adjuster.py` | `zone_adjustments_kernel` | per-zone violation counting, threshold/excess arithmetic, max-size-clamped expansion, direction gating |
| `deterministic/feedback/drc_parser.py` | `process_drc_violation` | KiCad JSON dict traversal → `DRCViolation` fields, clearance regex extraction |

Data containers (`Bottleneck`, `ChannelMap`, `BottleneckMap`, `DRCViolation`,
`MappedViolation`, `ZoneAdjustment`, `AdjustmentResult`) **stay Python
dataclasses**. This is deliberate, not an omission:

1. `dataclasses.replace(state/m/…)` is load-bearing across ~20 stage modules
   (including the leaves' files and router_v6); Python 3.12's `dataclasses.replace`
   does not dispatch to a pyclass `__replace__` (that is 3.13+), so a pyclass
   would break `replace()` at every call site.
2. `test_bottleneck_map.py` pins `dataclasses.FrozenInstanceError` on attribute
   write; a pyclass would need to fake that exception class.
3. The containers hold Python-side objects (router_v6 types, `Any` config); a
   pyclass port would be the 58-`Py<PyAny>`-handle anti-pattern the guide flags.
   The compute — not the containers — is what this slice migrates, and the
   differential pins the compute bit-exactly.

## R3-style orchestration records (recorded, not migrated)

Each names the concrete blocker. These are re-decidable when the blocker falls
(per R3).

### `deterministic/state.py` — `BoardState` — R3-style record

**Blocker: the `dataclasses.replace(state, …)` call contract plus Python-object
field types.** `BoardState` is the immutable state bag threaded between stages.
Twenty stage modules across three sessions' files (the leaves' `zone_geometry.py`,
`zone_assignment.py`, `slot_generation.py` included) build successor states with
`replace(state, field=new)`; converting the dataclass to a pyclass makes
`replace()` raise `TypeError` at every one of those sites. Its ~60 fields are
Python-side objects (`Board`, `Netlist`, `DRCOracle`, router_v6 types) and
`Any` fields (`config`, `thermal_field`). The "compute" the module contains —
frozenset union + `replace`, and the `__post_init__` layer-count validation —
is glue; the validation reads Python `Board.layer_stackup` objects. The module
is the hub the dispatch names, and its consumer pins (2,410 router_v6 +
deterministic tests) are preserved unchanged. Re-decidable when the stage
protocol is unified (the plan's `unified-stage-protocol` follow-up) and the
contained Python objects migrate.

### `deterministic/stages/base.py` — `Stage` ABC — R3-style record

**Blocker: Python ABC subclass contract.** `Stage` is an `abc.ABC` with
`abstractmethod`s; ~30 concrete stage classes (leaves-owned and router_v6)
subclass it. pyo3 pyclasses cannot be abstract base classes and cannot be
subclassed with Python `abstractmethod` semantics; a Rust port would break
every stage class's inheritance. The defaults (`invariants=()`,
`declared_reads=()`, …) are registry glue read by the fence runner. Recorded.

### `deterministic/stages/setup.py` — setup stages — R3-style record

**Blocker: constructs router_v6 constraint objects (mid-migration surface).**
`DRCOracleSetupStage.run` builds `ClearanceMatrix`, `DRCOracle`, `Point`, `Pad`
from `router_v6.constraints_*` — modules owned by the router_v6 workstream,
still Python. The stage is orchestration wiring into those objects; the two
pure helpers it contains (`_rotate_point`, layer-name→index mapping) are
single-use glue around already-delegating or external geometry. Recorded;
re-decidable when `router_v6/constraints_*` land.

### `deterministic/feedback/orchestrator.py` — `AutomatedZeroDRC` — R3-style record

**Blocker: live-Python-object orchestration.** The feedback loop mutates
`self.config` — either a raw dict or a `PlacementConstraints` object with
attribute access — calls `pipeline.run` (Python stages, mid-migration),
`drc_runner()` (Python callback), and re-assigns `mapper.zone_config` /
`adjuster.zone_config` on live objects. The loop is the definition of
orchestration; its sub-computations (`_get_zone_config`, `_update_config`,
`_inject_zone_config`) are dict/attribute mutation over Python objects with
zero native-type compute. The mapper/adjuster kernels it calls are migrated
(above). Recorded.

### `deterministic/feedback/drc_runner.py` — `KiCadDRCRunner` — R3-style record

**Blocker: subprocess/kicad-cli boundary.** The module shells out to
`kicad-cli pcb drc` and manages `tempfile`/`Path` output dirs; error strings
come from the subprocess. Per the guide's library-boundary rule (PyYAML,
GEOS, solver precedents), a subprocess boundary is kept Python-side; a Rust
port would re-invoke the same subprocess with no compute gain. Recorded.

### `deterministic/instrumentation.py` — R3-style record

**Blocker: Python-callback wrapper; instrumentation, not product surface.**
`InstrumentedStage` wraps an arbitrary Python stage and calls
`inner_stage.run(state, *args, **kwargs)`; `_count_routes` does
`getattr(route, "net_name")` over heterogeneous Python route objects; the
pipeline wrappers rebuild pipelines via `type(pipeline)()`. The verdict
program already keeps `profiling/` and `testing/` JUSTIFIED-KEEP for
instrumentation-and-test-helper reasons; this module is the same class of
surface inside the deterministic tree. The route-counting fold carries zero
native-type compute. Recorded.

### `deterministic/flags.py` — R3-style record

**Blocker: `os.environ` read-at-call-time boundary.** `is_drc_fence_fail_enabled`
and `is_feedback_enabled` read an env var on every call (so tests can flip the
flag mid-process) and classify the raw string against a four-element set. The
compute is a string-set membership; migrating it would add a pyo3 boundary
crossing per invariant-check call for zero measured value. The module-level
snapshot constant `DRC_FENCE_FAIL_ENABLED` is read at import time — a Rust
replacement could not replicate import-order semantics without a Python shim
anyway. Recorded.

### `deterministic/geometry/courtyard.py` — already-delegating (no record needed)

One-line re-export of `temper_placer.core.courtyard` (a Phase-2/3 contract
surface owned by the contracts workstream). Already a shim; unchanged.

### `deterministic/geometry/guard_strip.py` — R3-style record (JUSTIFIED-KEEP class)

**Blocker: the shapely/GEOS boundary.** `compute_guard_strip` is `Polygon.buffer`
+ `difference`. Per the guide's measured precedent, GEOS `buffer(r).bounds` is
NOT `bounds ± r` (169/169 mismatches, worst 2.4e-3 mm) — buffer/difference
semantics (arc tolerance, self-intersection handling) are not bit-reproducible
by any Rust geometry port, and the module is not physics-gated. Kept Python
with the blocker named; re-decidable if a bit-exact GEOS-equivalent boundary
ever exists.

## Leaf-coordination note (call-backs resolve on merge)

The hubs call into stage modules that the leaf-stages branch is migrating in
parallel. **No stage module is touched here.** All call-backs from this slice's
shims into stage-owned surfaces stay Python-side: `AutomatedZeroDRC.pipeline.run`
(calls Python stage `.run`), `create_drc_aware_pipeline`'s stage construction
(in `deterministic/__init__.py`, untouched), and `routability_penalty`'s
consumers in `_phase_zones.py` (leaves-owned) call the shim's module-level
function. When the leaf PR merges, its stage shims expose the same
Python-callable API (stage classes stay Python per the base.py record above),
so every hub call-back resolves without a code change here.

## R1h note (physics-gated)

None of the migrated kernels are physics-gated under the R24 discipline: no
kernel gates on a physics quantity (thermal/creepage/solve margin). `channels.py`
carries the PHYSICS-KW marker in its docstring — evaluated and recorded: the
module consumes router-V6 congestion output for **placement-time routability
scoring**, a heuristic cost term in `score_slot`, not a physics invariant; the
penalty is bounded in `[0,1]` and does not feed any R24-gated constraint. The
R24 gates (soundness proof, BMC, post-solve audit) therefore do not apply; the
R1 gates apply in full.

## R1 gate status

| Gate | Status | Evidence |
|---|---|---|
| R1a bit-identical vs verbatim oracles | **PASS** | 6 differential files, 100+ tests, `float.hex()` + type-carrying `canon`; oracles are the pinned verbatim modules (header-only diff) |
| R1b no-regression arm | **PASS (measured, registration deferred)** | local shim-vs-oracle A/B: ratio 0.909, parity sanity inside the bench; NOT registered in `_BENCHMARKS` — named blocker: an unbaselined key reddens every open PR (happened twice; #757) and darwin rows are invalid per the platform-bias rule. Re-decidable when the main capture path rows the key |
| R1c >= 5 non-vacuous properties | **PASS** | 5 hypothesis properties per module (30 total), each with the boundary probes that caught real PBT bugs during shake-out |
| R1d >= 3 MRs | **PASS** | 3 metamorphic relations per module (18 total) |
| R1e VERIFICATION.md | **PASS** | "Wave 4 Phase 5 — deterministic hubs" section in `packages/temper-design-bundle/VERIFICATION.md`: structural soundness proof (induction non-applicable — bounded straight-line kernels), documented deviations, mutation table |
| R1f TDD (differential first, RED) | **PASS** | differentials pinned the `deterministic_hubs` symbols before the Rust existed; RED = collection failure |
| R1g borrow-over-clone, no unwrap, catch_unwind | **PASS** | `catch_panic` at every pyfunction boundary (pyo3's automatic guard on the pure-f64 pyclass methods); `clippy::unwrap_used` denied crate-wide; clippy `-D warnings` clean |
| R1h physics-gated | **N/A — recorded** | see above; PHYSICS-KW marker on channels.py evaluated, not a physics invariant |

## Anti-vacuity mutation campaign

`scripts/phase5_hubs_mutations.py` — 11 mutations, each applied to the Rust,
rebuilt, suites run expecting failure, reverted. **10 caught, 1 provable
equivalent.** Full per-mutant table with the discriminating tests: the
VERIFICATION.md section (Anti-vacuity). The three survivors-adjacent PBT
defects (P4/P5 edge rounding, MR2 key collision) were real flaky-test bugs
found by the campaign's repeated suite runs and fixed in this slice
(2026-08-05); the final campaign run is a clean 10/11 with the tree verified
green after every revert.

- M1–M2: CPython float floor-division transcription (fmod subtraction, snap)
  — caught by the `8.2 // 0.1 == 81.0` discriminating probes added to
  `test_bottleneck_map_rust_differential.py` (distinct per-column scores so
  col 80 vs 81 is observable).
- M3–M4, M10: channels penalty (severity weight, off-by-one bound, non-finite
  guard) — caught by the new severity-weight pins / boundary probes /
  non-finite error-parity pins.
- M5: `score_at` non-finite guard — caught by `test_score_at_nonfinite_error_parity`.
- M6: seed_filter equality-reject — caught by the pinned score==threshold case.
- M7: zone_adjuster excess off-by-one — caught by the threshold arithmetic pins.
- M8: mapper component sort — caught after the test stopped normalising the
  kernel's order away.
- M9: drc_parser pattern order — caught by the added both-patterns-with-
  conflicting-values case.
- **M11: provable equivalent (recorded).** The index-build tie-break
  (`score >` vs `score >=` on equal weights) changes only the kept *score*;
  equal weight ⟺ equal severity, and `penalty` reads only the kept severity.
  No exported surface reads the kept score (the dataclass's own copies live
  Python-side). Recorded per the phase guide's survivor precedent rather than
  fabricating a synthetic surface to observe it.

## Documented edge divergences (recorded, not replicated)

- `ZoneAdjustment.delta_width/height` are f64 in the shim where the oracle
  yields int for int-typed configs (values bit-identical; type recorded in
  VERIFICATION.md).
- Malformed zone-config `bounds`/`max_size`/`can_expand: None` raise in the
  oracle (unpack/TypeError) but are skipped by the kernel — only reachable
  with hand-mutated configs the orchestrator cannot produce.
- `drc_parser`: a non-str item `description` (e.g. `null`) becomes `""` in
  the kernel where the oracle appends it verbatim; KiCad always emits strings.
- `penalty`/`score_at` non-finite inputs: the kernel raises the oracle's
  exact ValueError/OverflowError (a fidelity FIX, not a divergence — the
  prior silent `as i64` saturation is gone, pinned by new differential cases).
- `violation_mapper` shim: `pos=()` (empty tuple) would raise IndexError in
  the shim's unpack where the oracle's truthiness check skips it; `pos` is
  `tuple[float,float] | None` by contract.

