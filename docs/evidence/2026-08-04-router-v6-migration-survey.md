# `router_v6` migration scope survey — what should actually be ported

<!-- provenance: commit=db89355a60076e1e28012d6d22410b862445d3dc dirty=false -->

**Date:** 2026-08-04
**Surface:** `packages/temper-placer/src/temper_placer/router_v6/` — 108 modules,
11,716 `ast.stmt` nodes, 29,847 LOC; 8 modules already delegate to a Rust crate.
**Scope of this document:** a classification verdict per module and a slicing
recommendation. **No production code was changed and no Rust was written.**

Every number below is reproduced by the scripts in
`tools/measurements/router_v6_survey/` (see [Reproducing](#reproducing)).

---

## 0. Headline

> **REVISED 2026-08-04 (v2).** Nine follow-up agents measured this document's
> claims. **Every one of them corrected it.** The verdicts below are the
> corrected set; §2.8 lists every change with the PR that measured it, and
> states the methodological failure that produced them. Do not cite v1.

**Of the 8,794 executable statements across the 100 non-delegating modules,
3,932 (45%) are genuinely PORT.** The other 55% is orchestration, contracts
belonging to Phase 2, harness, dead code, or work blocked behind GEOS.

v1 said 3,483 (40%) and put 1,520 behind third-party numeric libraries. Both
were wrong in the same direction: **scipy, kiutils and networkx all dissolved
under measurement, and BLOCKED fell to 535.** What survives is a single
systemic blocker — GEOS polygon algebra, plus identifiers built from unrounded
float `repr` — not eleven module-level ones.

And a second finding that changes what "PORT" is *for*: on the production board,
**the router's dominant cost is already Rust**. The repo's own profile
(`docs/evidence/2026-07-27-first-route-and-profile.md`) measures Stage 3 at
**95.5% of full-board wall time**, of which **96.5% is a single opaque
`temper_rust_router.solve_topology_rust` (CaDiCaL) call**. The Python model
construction that feeds it costs **~2.5s of 103.6s**. Stage 4 (all of A\*) is
**3.4%**; Stage 2 is **1.07%**.

So the remaining `router_v6` Python is, with the measurements available today,
**almost entirely off the hot path**. A migration here has to be justified as a
*correctness/typing* investment, not a speed one — and the R1 gate set is what
that investment costs, not what it buys. This survey is therefore written to
minimise the number of statements that ever enter that gate set.

---

## 1. Measurement method and the reconciliation with the brief

The brief cites "8,661 statements across 100 non-delegating files (8 of 108
delegate)". The file counts reproduce exactly. The statement counts depend on
the metric, so both are reported:

| Metric | Definition | All 108 | 8 delegating | 100 non-delegating |
|---|---|---:|---:|---:|
| `stmts` | raw `ast.stmt` nodes | 11,716 | 1,407 | **10,309** |
| `exec` | `stmts` − docstrings − imports | 10,006 | 1,212 | **8,794** |
| LOC | physical lines | 29,847 | 4,068 | 25,779 |

`exec` reconciles with the brief's 8,661 to within **1.5%**, so that is the
denominator this document uses for percentages. Per-file `stmts` differ from
the brief's top-14 list in places (e.g. `_astar_reconstruct` measures 195, not
284) — the brief said "verify it yourself", and these are the verified numbers.

**Delegation** is detected structurally: a module delegates iff it imports a
non-`temper_placer` `temper_*` crate. That yields exactly the brief's 8:
`_pipeline_route`, `astar_core_rust`, `bottleneck_geometry`, `channel_widths`,
`clearance_check`, `congestion_tensor`, `corridor`, `creepage_check`.

**Compute density** = `(BinOp + AugAssign + For + While + comprehension) /
executable statements`. It is used as a *signal*, never as the sole reason. Its
calibration is reassuring: the module PR #732 actually chose to port
(`constraints_geometry`) sits at **0.86**, third-highest in the package, while
the re-export shims and Stage wrappers sit at 0.00–0.12.

---

## 2. The bucket table

```
bucket      files   stmts    exec     loc  %stmts
PORT           37    4536    3932   11053   44.0%
GLUE           34    2535    2087    7233   24.6%
ELSEWHERE      12    1022     832    2488    9.9%
BLOCKED         4     602     535    1343    5.8%
HARNESS         6     589     515    1275    5.7%
SPLIT           3     375     315     952    3.6%
UNKNOWN         1     255     238     422    2.5%
DEAD            2     198     166     539    1.9%
RETIRE          1     197     174     474    1.9%
TOTAL         100   10309    8794   25779
```

Two buckets are new since v1. **SPLIT** holds three modules that measurement
showed are two or three things at once and cannot carry a single verdict
(`constraints_design_rules`, `topology_solver`, `topology_extraction`) — their
per-fragment dispositions are in `classification.csv`. **RETIRE** holds
`quality/corridor`, which #750 measured as computing nothing at all.

**DEAD is a sixth bucket the brief did not ask for.** It is used deliberately
rather than forcing three provably-bypassed modules into HARNESS or GLUE: their
correct disposition is deletion, not migration, and that is a different
recommendation with a different reviewer. Called out explicitly here so nobody
has to guess whether it was a slip.

The per-module verdict with its evidence is
`tools/measurements/router_v6_survey/classification.csv` — 100 rows, one reason
each. The rest of this section explains the bucket boundaries.

### 2.1 PORT — 34 modules, 4,014 stmts / 3,483 exec (40%)

Modules with a named kernel that (a) runs on a live path, (b) has no hard
third-party blocker, and (c) is not a contract carrier. The largest:
`constraints_drc_oracle` (322), `occupancy_grid` (264), `connectivity` (218),
`_astar_theta_star` (214), `quality/corridor` (197), `resource_bound` (180),
`metrics/slop_linter` (166), `astar_grid` (162), `thermal_relief` (160),
`congestion` (160), `constraints_geometry` (157, in flight as #732).

Two carry caveats that a slicing plan must respect:

- **`_astar_theta_star` (214) is not on the production entry point.**
  `_adapter_convert.route_pcb` — the entry point named as production by
  `docs/evidence/2026-07-27-first-route-and-profile.md` — passes
  `enable_theta_star=False, enable_lazy_theta_star=False`
  (`_adapter_convert.py:289-290`), as does `_adapter_core.py:197-198` and
  `deterministic/state.py:123-124`. Only `RouterV6Pipeline`'s own default
  (`_pipeline_core.py:52-53`) and `adapters/router_v6_stage_adapter.py:92` turn
  it on. It is live code with tests, but porting it moves nothing on the board
  path.
- **`occupancy_grid` (264) has the package's highest compute density (0.94)**
  and its `OccupancyGrid` class is 186 statements of pure-numpy grid marking —
  but see §3.3: its measured Stage-2 cost is inside `shapely`, not inside
  Python.

### 2.2 GLUE — 32 modules, 2,409 stmts / 1,982 exec (23%)

Orchestration and marshalling. The boundary rule: density below ~0.25 **and** no
arithmetic loop whose trip count scales with the board. Examples with the
evidence a reviewer can check in one grep:

| Module | stmts | Why GLUE |
|---|---:|---|
| `_adapter_convert` | 312 | `route_pcb` config plumbing, netclass dict conversion, `.kicad_pcb` text writing; the "arithmetic" is string formatting |
| `_astar_reconstruct` | 195 | `run_astar_pathfinding` is a 175-stmt driver — per-net loop, retry/ripup policy, report assembly; the search it drives is Rust |
| `_astar_search` | 190 | a dispatch/fallback ladder; its only arithmetic is coordinate marshalling for the pyo3 call |
| `_pipeline_core` | 172 | `RouterV6Pipeline.__init__` + stage sequencing, density 0.12 |
| `layer_assignment` | 154 | enum/pattern lookup, density 0.12 (one 31-stmt kernel is separable — §5) |
| `net_classification` | 67 | keyword/prefix net-name matching, **0 BinOp**, density 0.02 |
| `astar_pathfinding` / `adapter` / `pipeline` | 12 / 6 / 4 | pure re-export shims |
| 8 Stage wrappers | 372 | `grid_prep_stage`, `net_prep_stage`, `route_stage`, `result_aggregate_stage`, `stage2_orchestrator`, `stage4_orchestrator`, `stage_validators`, `stage_ledger` — 0–6 BinOp each |

`net_classification` is worth naming specifically because it has the closest
in-repo precedent: `core/priority.py`'s `classify_net_priority` is the *same*
keyword-matching shape, and its own Phase-2 migration **deliberately kept it in
Python** (plan `2026-08-01-001`, line 131). The same reasoning applies here.

The brief's FFI arithmetic applies to this whole bucket: at a ~268 ns pyo3
boundary floor against a ~7.7 ns frozen-attribute read, and #732's own sibling
measurement of `deg_to_rad` at **0.64×** and attribute access at **0.56×**,
moving a dispatch table across the boundary is a measured regression, not a win.

### 2.3 BLOCKED — 12 modules, 1,753 stmts / 1,520 exec (17%)

Gated on a third-party primitive with no bit-exact Rust drop-in. The blockers,
with call sites:

| Blocker | Modules | Evidence |
|---|---|---|
| `scipy.ndimage.distance_transform_edt` | `_astar_heuristics` (84), `routability_check` (207) | **Recorded KTD8 keep** — the `edt` crate measured max diff 2.0–2.236 (`docs/evidence/2026-07-31-edt-crate-ktd8-spike-rejected.md`). The verdict line in `docs/wave4-discipline-contract.md:120` names `_astar_heuristics.py:101` verbatim |
| `shapely.ops.voronoi_diagram` (GEOS) | `channel_skeleton` (214) | **Recorded spike-gate**, `docs/wave4-verdicts.yaml:111`. Confirmed at `channel_skeleton.py:14,279`, plus `shapely.prepared.prep` at `:306` |
| `scipy.spatial.cKDTree` | `constraints_spatial_index` (226), `_zone_pour_stitch` (162) | `constraints_spatial_index`'s docstring line 4 states cKDTree *is* the module's purpose. kNN tie-break order is implementation-defined; **no measured parity exists** — this is a new blocker, not a recorded one |
| `scipy.cluster.hierarchy` linkage/fcluster | `zone_emission` (97) | `zone_emission.py:91-92`; merge-order semantics have no Rust drop-in |
| `scipy.ndimage.label` | `routability_check` | `routability_check.py:341` |
| `networkx` graph algorithms | `channel_mapping` (203), `topology_extraction` (56) | `nx.shortest_path` at `channel_mapping.py:339,343`. Same class as the already-recorded `nx.minimum_cut` partition-order keep in `temper-geometry/VERIFICATION.md` |
| GEOS boolean algebra | `obstacle_map` (108), `routing_space` (99), `placement_audit` (47) | `unary_union` ×2 + `buffer` ×4 in `obstacle_map`; `.difference`/`.area` in `routing_space`; `MultiPoint.convex_hull` + `.buffer` + `.intersection`/`.centroid` at `placement_audit.py:66-94`. **`RoutingSpace.available_area` is typed `MultiPolygon` (`routing_space.py:29`)** — the GEOS object is the cross-module type, not an internal detail |
| kiutils | `constraints_design_rules` (250) | Recorded: "kiutils leaves the boundary at this phase" (`docs/wave4-verdicts.yaml:55`) |

The GEOS entry deserves emphasis because it is systemic rather than per-module.
Bit-exactness class **B6** in the discipline contract already records that GEOS
point distance is `sqrt(dx·dx + dy·dy)`, not `hypot`, and that replicating it
with `hypot` fails on ~12% of random pairs; `temper-geometry/VERIFICATION.md`
records a second GEOS divergence for `shapely.affinity.rotate`. Those were
single *predicates*. Stage 2 passes GEOS *polygons* across module boundaries, so
porting it means replicating GEOS boolean ops bit-for-bit, which nothing in this
repo has attempted.

**Three new blockers this survey adds to the ledger** (recommendations, not
edits — see §7): `scipy.spatial.cKDTree`, `scipy.cluster.hierarchy`, and GEOS
polygon boolean algebra as a *type-level* boundary.

### 2.4 ELSEWHERE — 12 modules, 1,022 stmts / 832 exec (10%)

`constraint_model` (298) and `routing_results` (81) are the two the ledger
already records as Phase 2 contracts (`docs/wave4-verdicts.yaml:110`). The other
ten are the same *shape* and should be recorded with them:

| Module | stmts | class-level `AnnAssign` | BinOp | Note |
|---|---:|---:|---:|---|
| `diagnostics` | 114 | 42 | 16 | 2 enums + 4 frozen dataclasses; only compute is two 7–8 stmt scorers |
| `stage0_data` | 94 | 41 | 7 | the package's central contract carrier — **22 router_v6 + 10 placer consumers** |
| `_routing_reports` | 85 | 21 | 20 | |
| `_pipeline_types` | 76 | 28 | 15 | 0 loops |
| `_adapter_types` | 59 | 40 | 5 | 0 loops; 2 Protocols + 4 dataclasses |
| `terminal_tree_execution` | 77 | 4 | 4 | execution seam over the contract types, density 0.14 |
| `tree_route_geometry` | 30 | 4 | 1 | |
| `_check_report_base` | 13 | 2 | 3 | shared DFM report base |
| `kicad_connectivity` | 65 | 0 | 1 | parses emitted `.kicad_pcb` text — **Phase 3 formats/IO** |
| `_strip_copper` | 30 | 0 | 5 | paren-balanced s-expression removal — **Phase 3 formats/IO** |

`stage0_data` is the load-bearing one: nothing in `router_v6` can be typed
across the pyo3 boundary until `ParsedPCB`/`DesignRules`/`NetClassRules` are
pyclasses. It is the unlock for everything else (§6).

### 2.5 HARNESS — 6 modules, 589 stmts / 515 exec (6%)

**`benchmark.py` (255) — the brief's prime suspect — is CONFIRMED.** Its only
non-test consumer anywhere in `src/` is
`profiling/pipeline_metrics.py:203`, and `profiling/**` carries a recorded
`JUSTIFIED-KEEP` verdict as "development instrumentation, not product surface"
(`docs/wave4-verdicts.yaml:182`). It is also not import-reachable from any
production entry point.

The other five: `test_boards` (59, fixture catalog whose sole `src/` consumer is
`benchmark.py`), `astar_monitor` (99, a CI invariant monitor that calls
`pytest.fail` at `:209-211` and is documented as "zero overhead when the context
manager is not active"), `all_pad_evidence` (85) and `audit_provenance` (52)
(fail-closed validators for committed JSON evidence records, 0 `src/` consumers
each), and `audit_tree_geometry` (39, 0 `src/` consumers).

### 2.6 DEAD — 3 modules, 267 stmts / 224 exec (3%)

Provably bypassed by the production path:

- **`sat_model` (130)** — `_pipeline_route.py:281` sets `sat_model = None`
  unconditionally, right after printing "3.7: Building SAT model…". Nothing in
  `src/` constructs a `SATModel`; the type survives only as
  `Stage3Output.sat_model: SATModel | None` (`_pipeline_types.py:64`).
- **`topology_solver` (69)** — the Python `solve_topology` has **zero non-test
  call sites**; production Stage 3 calls `temper_rust_router.solve_topology_rust`
  (`_pipeline_route.py:290,311`). Its own docstring's example is the only usage
  pattern that exists.
- **`metrics/octilinear` (68)** — **not imported anywhere in `src/`**. The only
  mention is a prose comment at `astar_core.py:26`.

Partial: `topology_extraction.extract_topology_solution` (~36 of that module's
56 stmts) also has no non-test caller — `_pipeline_route.py:368,377` constructs
`TopologyGraph`/`NetTopology` directly.

**199 statements of Python SAT solver exist behind a production path that
solves in Rust.** Recommendation: retire, not migrate.

### 2.7 UNKNOWN — 1 module, 255 stmts

**`bundle_analyzer` (255).** Its kernel — partitioning nets into bundle
equivalence classes — is stdlib set/dict work at density 0.28 and looks portable.
But its type signature is built with GEOS `convex_hull` ×2 and `.union()` ×2 over
`MultiPoint`. Whether that seam can be isolated from the partitioning (making the
rest PORT) or whether the hull *is* the equivalence relation was not determined
in this survey. Do not plan it into a slice until someone reads
`BundleAnalyzer.analyze` end to end.

---

## 2.8 Corrections (v2) — and why v1 was wrong in one direction

### The method failure

v1 classified modules from **symbol-level imports and docstrings**. It never
checked reachability. Four channels it could not see, each of which produced a
wrong verdict:

1. **Package re-exports.** `metrics/__init__.py` re-exports `octilinear`, so the
   module *was* loaded at runtime even though no symbol had a caller. v1's
   "imported nowhere in `src/`" was true of symbols and misleading about modules.
2. **Text-reading consumers.** `scripts/bmc_adoption_gate.py` consumed
   `sat_model.py` by reading it as *text*. No import graph can see that.
3. **Dominating guards.** `channel_mapping`'s networkx calls and
   `_zone_pour_stitch`'s kNN query are both unreachable behind a guard several
   statements earlier. v1 blocked 365 statements on primitives that never run.
4. **Docstrings describing intent, not behaviour.** `constraints_spatial_index`
   says cKDTree is its purpose; it issues no kNN query at all.

A fifth error was simpler: v1 justified blocking `constraints_design_rules` by
citing a ledger verdict **whose path pattern is `io/**` and does not match
`router_v6/`**. That is a citation error, not an inference error.

The bias is one-directional — every correction moved statements *toward*
migration or *toward* deletion, never away. Treat any remaining v2 verdict that
rests on an import rather than a traced call site as provisional.

### Verdict changes, each traced to its measurement

| Module | v1 | v2 | Measured by |
|---|---|---|---|
| `constraints_spatial_index` (226) | BLOCKED | **PORT** | #743 — no kNN; `return_sorted=True` is a precondition |
| `_zone_pour_stitch` (162) | BLOCKED | **PORT** | #743 — k=1 unreachable (`cluster=False`); dormant hazard recorded |
| `channel_mapping` (203) | BLOCKED | **PORT** | #744 — nx branch unreachable; **delete, don't port** |
| `routing_space` (99) | BLOCKED | **PORT** | #747 — mask narrowing, 598,400/598,400 cells |
| `obstacle_map` (108) | BLOCKED | **PORT** | #747 — 2 kept lines |
| `placement_audit` (47) | BLOCKED | **GLUE** | #747 — advisory only, reaches a `verbose` print |
| `via_placement` (79) | PORT | **GLUE** | #749 — two `abs()` subtractions |
| `quality/corridor` (197) | PORT | **RETIRE** | #750 — two coordinate frames; 739 channels, 0 tracks |
| `constraints_design_rules` (250) | BLOCKED | **SPLIT** | #748 — v1 cited a non-matching ledger pattern |
| `topology_solver` (69) | DEAD | **SPLIT** | #745 — 24 stmts are live contracts |
| `topology_extraction` (56) | BLOCKED | **SPLIT** | #745 — 36 dead, 20 live contracts |
| `channel_skeleton` (214) | BLOCKED | BLOCKED | #746 — **right bucket, wrong reason** (see below) |
| `zone_emission` (97) | BLOCKED | BLOCKED | #748 — **right bucket, wrong reason**: scipy dissolved, GEOS found |

### The gate that was never run

`channel_skeleton`'s shapely-Voronoi spike gate, which v1 cited as recorded
evidence, **had never been executed** (#746 — `git log --all --diff-filter=A`
over `docs/evidence/` returns empty). Worse, plan `2026-08-01-001:158` describes
the module as *"pre-spiked."* **An unrun gate acquired the language of a
discharged one purely by being restated**, and v1 propagated it. Other ledger
entries plausibly share this condition; a ledger entry is not evidence.

GEOS Voronoi turned out to be deterministic. The real blocker is `edge_id` built
from **unrounded float `repr`** at `constraint_model.py:325-337` — geometry
agrees to 1.05e-15 while identifiers agree 0/12.

### Defects found while pinning oracles — reported, not fixed

Fixing any would break a verbatim pin. Each is pinned by a test that fails if
someone repairs it without re-pinning.

| # | Defect | PR |
|---|---|---|
| 1 | `analyze_congestion(positions=...)` silently ignored — byte-identical output with every component moved 999 mm. The placement feedback loop is blind to the positions it evaluates | #751 |
| 2 | `analyze_congestion(layer_assignments=...)` always raises `ModuleNotFoundError` (`temper_placer.routing` does not exist) — the multi-layer branch is unreachable | #751 |
| 3 | An off-board net writes demand to a 7×7 block at the board **origin** via a negative-index slice | #751 |
| 4 | Every escape via is labelled `F.Cu` — `getattr(component, "side", 0)` reads a field named `initial_side` | #751 |
| 5 | `poly.buffer(0)` on a bow-tie returns one lobe — a self-intersecting zone can lose half its area from the obstacle map | #747 |
| 6 | `thermal_relief._add_smd_thermal_reliefs` iterates a `frozenset` — 8 distinct output orders over 8 interpreters | #749 |
| 7 | `acid_trap_detection`'s `not isfinite(t) and t < 0` is unreachable for finite negatives; `-5.0` silently yields an empty report | #749 |
| 8 | `_classify_vias`'s `signal` accumulator is dead — overwritten two lines later | #750 |
| 9 | `simplify_tolerance` is dead on the Voronoi path (494/494 two-point LineStrings), yet is **credited for skeleton density** in `2026-07-27-stage3-model-and-rewrite.md:211` | #746 |

**Defects 4, 6 and the two in `channel_mapping` (#744) are all
`PYTHONHASHSEED`/iteration-order class**, joining PR #730. Four instances is a
class and warrants a standing check, not four separate fixes.

---

## 3. What the profile says about whether any of this pays

This section exists because a scope survey that only counts statements will
recommend porting things that cost nothing to leave alone.

### 3.1 Stage 3 is 95.5% of wall time and is already Rust

From `docs/evidence/2026-07-27-first-route-and-profile.md` (108-net production
board, `pcb/temper.kicad_pcb`):

| Stage | Wall time | Share |
|---|---:|---:|
| Stage 2 (channel analysis) | 17.6s | 1.07% |
| **Stage 3 (SAT topology)** | **1,573.8s** | **95.5%** |
| Stage 4 (A\* + post-processing) | 55.9s | 3.4% |

cProfile on the bounded 15-net run attributes **100.0 of the 103.6s inside
`_run_stage3` (96.5%) to one call**: `temper_rust_router.solve_topology_rust`
(CaDiCaL). The Python that remains in that stage — `constraint_model.py`'s
`_create_per_net_channel_vars`, `_create_capacity_constraints`, `add_variable` —
totals **~2.5s**, i.e. ~2.4% of Stage 3 and ~2.3% of the run.

Consequence: **`constraint_model` (298 stmts, already ELSEWHERE) is worth at
most ~2.3% of wall time**, and no other Stage-3 Python is worth more. The
profile's own top recommendation for this stage is a CaDiCaL conflict/time limit
— a ~5-line Rust change — not a migration.

### 3.2 Stage 4 is 3.4%, and its kernel is already Rust

`_dispatch_search` (`_astar_search.py:89-111`) routes plain 2D A\* to
`astar_core_rust._astar_search_rust`, which calls
`temper_rust_router.astar_kernel_3d_py`; line-of-sight goes to
`line_of_sight_py`. What is left in Python is:

- `astar_core._astar_search` — taken **only** when `net_id >= 0`
  (`_astar_search.py:95`), i.e. the all-pad tree-edge path, because the Rust
  kernel's binary validity tensor cannot express same-net copper;
- `astar_core._astar_search_3d` / `_route_segment_3d` — a **third-tier**
  multilayer fallback (`_astar_search.py:508,526`), measured at 2.0s tottime
  across 4 calls at subset scale — expensive per call, negligible in aggregate;
- `_astar_theta_star` — off on the production entry point (§2.1).

The brief proposes `_astar_*` (≈904 stmts) as the flagship cluster. It is a
coherent cluster, but **the hot kernel already left**, and the ~3.4% ceiling
bounds what the remainder can return.

### 3.3 Stage 2's hotspot is inside shapely, not inside Python

80% of Stage 2 (14.1 of 17.6s) is `shapely.predicates.contains` called **31,688
times**. `build_occupancy_grid` today issues a *single* batched
`contains(check_area, batch_points)` (`occupancy_grid.py:481`), so the per-call
loop is elsewhere — the prepared-geometry filters in `channel_widths.py`
(already delegating) and `channel_skeleton.py` (BLOCKED) are the candidates.
**UNVERIFIED**: the profile predates several changes to these files and the
attribution was not re-measured here.

Either way the fix is a batched/STRtree shapely call, not a Rust port — and
`occupancy_grid`, this survey's highest-density PORT module, is *not* where that
time is going.

---

## 4. Clusters

The PORT set is **not** tightly coupled by imports —
`tools/measurements/router_v6_survey/clusters.py` shows most PORT modules with
zero PORT neighbours. Clusters therefore have to be drawn by **shared kernel and
shared oracle**, which is what actually determines whether one pinned Python
oracle module and one differential harness can serve several files.

| # | Cluster | Modules | stmts | What one oracle can cover |
|---|---|---|---:|---|
| A | **DRC distance geometry** | `constraints_geometry` (157, #732), `constraints_drc_oracle` (322), `connectivity` (218), `terminal_extraction` (33), `terminal_tree` (36) | **766** | All five consume `Point`/`LineSegment`/`RotatedRect` from `constraints_geometry` and do point/segment/rect distance + touch predicates. #732's oracle module already covers the primitives; the other four add *call sites*, not new primitives |
| B | **Occupancy grid & coordinates** | `occupancy_grid` (264), `resource_bound` (180), `capacity_check` (95), `layer_capacity` (64), `neighbor_validity` (35), `path_simplify` (33), `grid_converter` (32) | **703** | One shared grid fixture (cell size, origin, `int8` state array). `neighbor_validity`'s output is already the Rust A\* kernel's input (`astar_core_rust.py:113`), so the FFI shape exists |
| C | **A\* search family** | `astar_core` (253), `_astar_theta_star` (214), `astar_grid` (162), `_astar_ordering` (76) | **705** | Shared `RoutePath`/`RouteNode3D` types + the same grid. **Discounted heavily** — kernel already Rust, ≤3.4% ceiling, theta\* off on the board path |
| D | **Post-route DFM checks** | `thermal_relief` (160), `acid_trap_detection` (119), `power_plane` (110), `copper_balance` (95), `via_placement` (79), `annular_ring_check` (78), `teardrop_generation` (78) | **719** | One routed-board fixture + one segment/via iteration harness. Two siblings (`clearance_check`, `creepage_check`) **already delegate to `temper-drc-rs`**, and `annular_ring_check` already shares `BaseCheckReport` with them — this cluster extends an existing crate rather than founding one |
| E | **Congestion & placement feedback** | `congestion` (160), `congestion_analysis` (79), `routing_demand` (73), `placement_suggestions` (58), `congestion_heatmap` (51), `apply_suggestions` (48) | **469** | One congestion-grid fixture serves all six; `congestion_tensor` already delegates |
| F | **Quality metrics / gates** | `quality/corridor` (197), `metrics/slop_linter` (166), `quality/via_count` (117) | **480** | All three define a **duplicated 3-line `_parse_pcb`** over the same `temper_placer.io.kicad_parser.parse_kicad_pcb` (`corridor.py`, `via_count.py:116`, `slop_linter.py:222`). One parsed-board fixture, one oracle, three modules |
| G | **Net ordering / escape** | `net_ordering` (105), `escape_via_generator` (67) | **172** | Weak cluster; arithmetic over nets with no shared type. Do not force it |

Total = 4,014 = the PORT bucket exactly.

### What is one-time vs per-file inside a cluster

**One-time per cluster:**

- the pinned Python oracle module (`_<cluster>_py_oracle.py`) — a **verbatim
  `git show` copy** of the pre-migration sources, so authorship cost ≈ 0;
- the input-corpus module (`_<cluster>_cases.py`) — shared by the differential
  *and* the `benchmarks/perf_ab.py` arms, which #732 made structural after
  PR #714 passed a differential at iterations `[0,1,2,8,17,100]` and then failed
  CI on a benchmark that ran 120;
- the `VERIFICATION.md` induction section (G6);
- the ≥5 PBT properties + their mutation tests (G4) and ≥3 metamorphic relations
  (G5) — the contract says **"per module"**, so the cluster's definition of
  "module" is exactly the lever;
- the crate wiring (`bridge.rs`, `lib.rs`).

**Per-file, unavoidable:**

- the Rust implementation (#732: 725 lines for 32 functions ≈ **6.6 lines per
  ported statement**);
- the differential tests (#732: 661 lines for 33 tests);
- the delegation shim in the Python module;
- new corpus rows for that file's own edge cases.

---

## 5. What amortizes — the honest arithmetic

PR #732: **+3,412 / −231** to port 109 statements ⇒ **~31 lines per statement**.
Per-file breakdown (measured from `gh pr diff 732`):

| Lines | File | Repeats per slice? |
|---:|---|---|
| 725 | `temper-geometry/src/drc_constraints_geometry.rs` (32 fns) | yes, proportional |
| 661 | `test_constraints_geometry_rust_differential.py` (33 tests) | yes, proportional |
| 551 | `test_constraints_geometry_rust_pbt.py` (21 tests) | yes, **fixed per module** |
| 370 | `_constraints_geometry_py_oracle.py` | yes, but it is a verbatim copy — ~0 authorship |
| 288 | `temper-geometry/VERIFICATION.md` | yes, **fixed per module** |
| 266 | `_constraints_geometry_cases.py` | yes, proportional |
| 154 | `benchmarks/perf_ab.py` | yes, **fixed per module** |
| 107 | `test_signature_self_test.py` | **no — one-time, package-wide** |
| 94 | `tests/router_v6/_signature.py` | **no — one-time, package-wide** |
| 72+9 | `pad_geometry.rs`, `creepage_check.rs` (dlsym libm, `py_hypot`) | **no — shared helpers, already paid** |
| 37 | `bridge.rs` + `lib.rs` | yes, but trivial |
| 78 | the delegation shim | yes, proportional |

**Slice #2 in the same shape costs ~3,130 lines instead of ~3,412 — a 8.3%
saving.** `_signature.py` and its self-test are genuinely generic (they carry
type names and `float.hex()`, nothing module-specific) and never need writing
again; so are the `dlsym` libm and `py_hypot` helpers. That is the entire
package-wide amortization, and it is small.

The real structure of the cost is:

- **fixed per module: ~1,030 lines** (VERIFICATION 288 + PBT 551 + perf_ab 154 +
  wiring 37);
- **proportional: ~19.3 lines per ported statement** (`(3,412 − 1,030 − 282) /
  109`).

So a slice covering **one** cluster of N statements costs roughly
`1,030 + 19.3·N` lines:

| Slice shape | statements | ≈ lines | lines/stmt |
|---|---:|---:|---:|
| #732 as landed | 109 | 3,412 | 31.3 |
| a 250-stmt cluster slice | 250 | 5,855 | 23.4 |
| a 500-stmt cluster slice | 500 | 10,680 | 21.4 |

**Clustering buys ~30%, not an order of magnitude, because the dominant cost is
proportional.** 19.3 lines of evidence per statement is intrinsic to the R1 gate
set — a differential test per function, a corpus row per case, 6.6 lines of Rust
per statement. Nothing in this survey makes that number smaller.

**Therefore the lever is the numerator, and this survey is the lever.**

### v2: the model above was too pessimistic — measured

Three Phase A slices have now been built (#749, #750, #751). Phase A is the
oracle + corpus + differential + PBT half; gate G1 mandates it precede the Rust,
and **none of it needs a compiler**, so it parallelizes freely.

| Slice | stmts | Phase A lines | lines/stmt |
|---|---:|---:|---:|
| #732 (single module, Phase A portion) | 109 | 1,848 | **17.0** |
| #749 cluster D (7 modules, 1 slice) | 719 | 4,350 | **6.0** |
| #750 cluster F (3 modules, 1 slice) | 480 | 4,729 | **9.9** |
| #751 cluster E + 2 (9 modules, 3 slices) | 641 | 8,950 | **14.0** |

Clustering buys **2.8×** on the Phase A half, not the ~30% projected — and the
ordering confirms the fixed-cost model: one slice of 719 statements beats three
slices totalling 641.

**The G4 caveat.** #749 gave 7 modules 13 properties, reading "≥5 properties per
module" (G4) as per *migrated unit*. That reading is **novel**: all 90 existing
`*_pbt.py` files in this repo are named per source module, and the canonical
precedent gives 11 properties to one module. If a reviewer rejects it, cluster
D's PBT (986 lines, 23% of its Phase A) becomes seven suites at #732's ~550
each — 7,214 lines for 719 statements, **10.0 lines/stmt**. So the amortization
**survives the strict reading at 1.7×**; the oracle and corpus, which are
unambiguously per-cluster, are where the win actually lives.

### The resulting slice count

Against **3,932 PORT statements** in cluster-shaped slices at ~6–10 lines/stmt
for Phase A plus a comparable Phase B, the program needs roughly **12–16
slices**, against the ~75 implied by #732's rate over the full surface. The
reduction still comes mostly from *not porting 55% of the surface* — but
clustering now contributes materially rather than marginally.

---

## 6. Recommended slicing plan

Ordered. Each line: slice, statements, rationale, and what it unlocks.

| # | Slice | stmts | Rationale |
|---:|---|---:|---|
| 0 | **Retire the dead** — DONE, PR #745 | −279 | Deletion, not migration. Landed as 50 insertions / 2,432 deletions. v1 projected −303; the true figure is 279 because `topology_solver` is not wholly dead (§2.8). Add `quality/corridor` (197) and `channel_mapping`'s unreachable nx branch as follow-on retirements |
| 1 | **`stage0_data` as pyclasses (Phase 2)** | 94 | **Unlocks everything.** `ParsedPCB`/`DesignRules`/`NetClassRules` are the package's contract carrier — 22 router_v6 + 10 placer consumers. No `router_v6` kernel can take typed input across the pyo3 boundary until these are pyclasses. Ride PR #724's pattern |
| 2 | **Cluster A — DRC distance geometry** | 766 | #732 already built the oracle and half the Rust. `constraints_drc_oracle` (322) is the single densest live kernel in the package (0.48, 115 BinOp). Land #732 first, then extend its oracle module rather than starting a new one — this is the one place where the scaffolding genuinely amortizes |
| 3 | **Cluster D — post-route DFM checks** | 719 | Extends `temper-drc-rs`, where two siblings already live and `BaseCheckReport` is already shared. One routed-board fixture serves all seven. Correctness-motivated (the DFM stage defaults **off** because it did not scale, `_adapter_convert.py:~310`), which is the honest justification for this whole surface |
| 4 | **Cluster F — quality metrics** | 480 | Three modules, one duplicated `_parse_pcb`, one fixture. Feeds `placer/cp_sat/gates.py` and the human-reference baselines, so parity is directly checkable against existing recorded numbers |
| 5 | **Cluster B — occupancy grid & coordinates** | 703 | Highest compute density in the package. **Requires slice 1** (the grid is built from `ParsedPCB`). Note §3.3: justify on typing/correctness, not speed |
| 6 | **Cluster E — congestion & feedback** | 469 | `congestion_tensor` already delegates; one congestion-grid fixture |
| 7 | **Cluster G — net ordering / escape vias** | 172 | Small, independent, no dependencies. A good first slice for a new contributor |
| 8 | **Cluster C — A\* remainder** | 705 | **Deliberately last.** Kernel already Rust, ≤3.4% ceiling, and `_astar_theta_star` (214 of the 705) is off on the production entry. Reconsider only if the board path turns theta\* on |

Slices 2–8 are mutually independent once slice 1 lands. Slices 3, 4 and 7 do
not even need slice 1 (they take routed-board or net-list inputs, not
`ParsedPCB`).

**Spikes — all five now run (v2).** Every one is recorded; BLOCKED fell from
1,753 statements to 602.

| Spike | Result | PR |
|---|---|---|
| S1 — GEOS polygon algebra | Narrowing found and measured; `placement_audit` was never a GEOS blocker | #747 |
| S2 — `scipy.spatial.cKDTree` | **Dissolved** — no kNN query exists in one module, unreachable in the other | #743 |
| S3 — `networkx.shortest_path` | **Dissolved** — the calls are unreachable; delete rather than port | #744 |
| S4 — shapely Voronoi | Gate had never been run; GEOS is deterministic; blocker is `edge_id` | #746 |
| S5 — scipy clustering + kiutils | **Both dissolved**; a GEOS boundary found in `zone_emission` that v1 missed | #748 |

**What remains is one systemic problem, not eleven module ones:** GEOS polygon
algebra (catalog class **B6**, raised by #747 from a scalar divergence to a
vertex-level one — 88.4% disagreement at up to 701 ulps) and identifiers derived
from unrounded float `repr`. The single highest-value follow-up is therefore not
another spike but a **canonicalisation change**: 1 nm coordinate quantisation
plus canonical edge ordering, which #746 measured as flipping `channel_skeleton`
parity from 0/12 to 12/12. It is behaviour-changing (every SAT variable name
moves) and needs its own A/B before anything downstream depends on it.

---

## 7. Recommended ledger changes (recommendations only — nothing was edited)

`docs/wave4-verdicts.yaml` was **not** modified, per the brief. The survey
implies these entries:

1. Extend the Phase-2-contract note beyond `constraint_model`/`routing_results`
   to `stage0_data`, `diagnostics`, `_pipeline_types`, `_adapter_types`,
   `_routing_reports`, `_check_report_base`, `tree_route_geometry`,
   `terminal_tree_execution` (§2.4).
2. Record `router_v6/benchmark.py`, `test_boards.py`, `astar_monitor.py`,
   `all_pad_evidence.py`, `audit_provenance.py`, `audit_tree_geometry.py` as
   **JUSTIFIED-KEEP — harness**, matching the existing `profiling/**` and
   `testing/**` entries.
3. Record `sat_model.py`, `topology_solver.py`, `metrics/octilinear.py` as
   **RETIRE**, with the bypass line numbers from §2.6 as the retire rationale.
4. Add three blockers to the ledger: `scipy.spatial.cKDTree`,
   `scipy.cluster.hierarchy`, and GEOS polygon boolean algebra (§2.3).
5. Move `kicad_connectivity.py` and `_strip_copper.py` from the router_v6
   Phase-5 pattern to **Phase 3 (formats/IO)**.

---

## 8. Could not classify / could not verify

Stated explicitly rather than guessed:

- **`bundle_analyzer` (255) — UNKNOWN.** §2.7. Whether the GEOS hull is
  separable from the partitioning kernel was not determined.
- **Which entry point is "the" production path.** `route_pcb` is named as
  production by the 2026-07-27 profile and by
  `test_production_board_routing_drc_regression`, but
  `adapters/router_v6_stage_adapter.py` and the `deterministic/` Stage wrappers
  are a second live path with **different flags** (theta\* on vs off). Every
  "on the production path" claim here means `route_pcb`.
- **The Stage-2 `shapely.contains` attribution.** §3.3 — 31,688 calls are
  measured, but the profile predates changes to `occupancy_grid` and
  `channel_widths`, and the attribution was not re-measured. Re-profiling Stage
  2 at current HEAD is cheap and would settle it.
- **The Stage-3 build/solve split at current HEAD.** The ~2.5s Python figure
  comes from a 15-net subset at commit `99caa33e…`; `bundle_analyzer` was not
  broken out. This is the **single highest-value measurement** anyone could take
  before planning further work on Stage 3.
- **No timings were taken in this survey.** Disk and CI were constrained and the
  brief said not to build. Every performance claim is a citation of an existing
  recorded measurement, never a new assertion.
- **`clearance_engine`, `diff_pair_inference`, `dense_package_detection`,
  `trace_width_assignment`, `bottleneck_analysis`** sit at density 0.15–0.23,
  just under the GLUE boundary. They are classified GLUE; each contains a
  10–30-statement kernel that a reviewer could reasonably argue into PORT. The
  total at stake is ~370 statements (~4%), which does not change any conclusion.
- **`layer_assignment`'s `_get_net_dominant_direction` (31 stmts)** is real
  geometry inside a GLUE module. Called out as a split candidate rather than
  reclassifying the whole 154-statement file.

---

## Reproducing

```bash
D=tools/measurements/router_v6_survey
R=packages/temper-placer/src/temper_placer/router_v6
python3 $D/measure.py   $R .  > /tmp/rows.json   # per-file numbers
python3 $D/summarize.py /tmp/rows.json           # the bucket table (§2)
python3 $D/graph.py     .     > /tmp/graph.json  # consumer census
python3 $D/reach.py     .                        # production-path reachability
python3 $D/clusters.py  .                        # PORT-set coupling (§4)
python3 $D/synopsis.py  $R                       # per-module synopsis
```

`summarize.py` fails loudly if `classification.csv` and the measured file set
disagree, so the verdicts cannot silently drift from the surface.

## Sources

- `docs/evidence/2026-07-27-first-route-and-profile.md` — the wall-time and
  cProfile measurements in §3
- `docs/evidence/2026-07-31-edt-crate-ktd8-spike-rejected.md` — KTD8
- `docs/wave4-discipline-contract.md` — the R1 gate set (G1–G8) and the
  bit-exactness catalog (B1–B12)
- `docs/wave4-verdicts.yaml` — the recorded verdicts cited by line number
- PR #732 — the per-file line counts in §5 (`gh pr diff 732`)
