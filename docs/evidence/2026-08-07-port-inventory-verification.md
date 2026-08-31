<!-- provenance: commit=dc9c5a86c1ffde1e200a0b9be4a2ca28a8e30ea8 dirty=UNKNOWN -->
# PORT inventory verification (removal_surfaces axis)

**Date:** 2026-08-07
**Scope:** `docs/wave4-verdicts.yaml`'s `removal_surfaces:` list, `verdict: PORT` entries only.
**Method:** code-verified survey — every entry checked against actual source at `main`
(commit `b31fe017`, via a detached `git worktree add --detach main` scratch checkout, not
the shared working tree), not against the ledger's own notes. No ledger edits, no
migrations performed. `scripts/check_verdict_coverage.py --report` run against that
snapshot as the authoritative cross-check for every LOC figure below.

## 0. Housekeeping note: this worktree was stale

This agent's assigned worktree (`worktree-agent-adda70bb608e9ddfd`) was pinned at commit
`7e1194b7`, which diverges from `main` (`b31fe017`) — 33 commits behind, 1 ahead. The
divergent commit predates the entire `removal_surfaces:` axis (`git show
7e1194b7:docs/wave4-verdicts.yaml` is 756 lines with no `removal_surfaces:` key at all).
`git rebase main` was blocked by the auto-mode permission classifier, so verification was
done by adding a **detached, read-only scratch worktree** at `main`
(`git worktree add <scratch-path> --detach main`) rather than by mutating this worktree's
branch or touching the shared checkout at `/home/bennet/Desktop/temper`. All LOC figures
below are against that `main` snapshot. This report itself is committed to this worktree's
own branch, as instructed.

## 1. Headline number: does not match 23,684

Running the ledger's own gate script against current `main`:

```
python3 scripts/check_verdict_coverage.py --report
...
Python removal coverage (R1 -- 'what has to happen before the interpreter can go away?')
  verdict           files       LOC    share
  BLOCKER-ORTOOLS      16      3597    4.9%
  BLOCKER-SCIPY         0         0    0.0%
  PORT                235     51161   69.8%
  REPLACE              31      9743   13.3%
  DELETE               16      1099    1.5%
  OUT-OF-RUNTIME       22      5520    7.5%
  UNDECIDED            13      2159    2.9%
```

**PORT is 235 files / 51,161 LOC, not 23,684.** This isn't a rounding gap — it's more than
double. I checked whether 23,684 matches an earlier commit of the ledger: `git diff
3c13e125 main -- docs/wave4-verdicts.yaml` (the commit that first introduced the
`removal_surfaces:` axis) is **empty** — the file has not changed since the axis was
introduced. There is no commit of this file, at any point in its history, that I can find
matching 23,684. I cannot reconcile where that figure came from; it should not be used for
planning. My own file-by-file glob/path expansion of the ledger's 36 PORT entries, done
independently before I found the gate script, reproduced the same 235 files / 51,161 LOC
exactly — this is not a script bug, it's the ledger's actual current content.

One plausible (unconfirmed) partial explanation: of the 36 PORT clusters, 12 already have
at least one file that imports a compiled Rust crate (real delegation landed since the
cluster was scored), totaling 25,030 LOC; the 24 clusters with **zero** detected Rust
delegation total **26,131 LOC** — within 10% of 23,684. If 23,684 was meant to approximate
"PORT clusters with no delegation started yet," it underestimates because per-cluster
delegation is often partial (one file of nine), not all-or-nothing, so this reconciliation
is a guess, not a finding I'd stake a plan on.

### 1.1 RESOLVED: 23,684 is `retriage_python_removal.py`'s ROWS table, not the ledger

The reconciliation above can be retired — the figure is now sourced exactly. **23,684 is
the sum of the 20 `PORT` rows in `tools/measurements/retriage_python_removal.py`'s
hard-coded `ROWS` table**, reproduced to the digit:

```
$ python3 -c "…sum the 20 PORT rows of ROWS…"
23684 20
```

This is not a corrupt or unreachable number, and it is not a stale copy of the ledger. It
is a **different artifact measuring a different scope**, and the ledger's own header cites
it by name ("the re-triage that answers R1 … and
`tools/measurements/retriage_python_removal.py`'s ROWS table"). That header is precisely
where the confusion enters: it presents the ROWS table as the source the `removal_surfaces:`
axis was transcribed from, which invites the reader to assume the two agree. They do not,
and the gap is structural rather than drift:

- `ROWS` is a **hand-maintained list of 43 cluster-level rows** with LOC baked in as
  integer literals. It is a frozen snapshot; nothing recomputes it against the tree.
- `removal_surfaces:` is a **file-level** axis whose LOC is computed live by
  `check_verdict_coverage.py` against whatever the tree currently contains.
- `ROWS`'s PORT rows **never scored the router_v6 compute clusters at all** — there is no
  row in that table for the spatial-DRC cluster (7,813), the A* kernel (2,433), post-route
  DFM (1,566), congestion (1,289), `core/` graph/geometry (2,349), `heuristics/` (4,346),
  `io/` write/export (3,513), or `pcl/` constraint-object compute (2,069). Those were
  already-PORT in the *original* triage, and the re-triage explicitly scoped itself to
  re-scoring the old NEVER-PORT rows ("not re-scored… the goal change does not affect
  them"). The ledger, correctly, transcribed both sets. The ROWS table only ever held one.

Those eight omitted clusters alone total **25,378 LOC**, which is essentially the entire
gap between the two numbers (51,161 − 23,684 = 27,477).

**Consequence for planning, and it cuts the opposite way from the brief's premise.** The
task that commissioned this survey described 23,684 as "demonstrably inflated." Against the
clusters it actually names, that is true — this report finds ~9,552 LOC of PORT-labelled
code already delegating. But 23,684 is not an inflated measure of the ledger's PORT axis; it
is an **undercount of it by more than half**, because it was never measuring that axis. Both
statements hold simultaneously and neither cancels the other: the *named clusters* contain
less outstanding work than believed, and the *program as a whole* contains far more. A plan
built on 23,684 under-scopes the remaining work by ~27,000 LOC.

**Recommendation:** either delete the `ROWS` table's frozen LOC integers in favour of a call
into `check_verdict_coverage.py`, or annotate the table in-source and in the ledger header
as a historical snapshot of a narrower scope that must not be read as the PORT total. As
written, two documents in this repo answer "how big is PORT?" with numbers differing by
2.2×, and the header wires them together as if they agreed.

## 2. Per-entry classification

All 36 `removal_surfaces` PORT entries, actual LOC at `main`, and delegation status (grep
for `import`/`from` of a compiled crate: `temper_rust_router`, `temper_geometry`,
`temper_io_types`, `temper_drc_rs`, `temper_thermal`, etc., confirmed by reading each hit,
not just counting imports).

| # | Cluster | Files | Ledger LOC | Actual LOC | Status |
|---|---|--:|--:|--:|---|
| 0 | routability_check.py (scipy EDT) | 1 | 477 | 511 | **Partially migrated.** EDT call delegates to `temper_geometry.exact_edt_transform` (merged, commit `1efa1cb3`). `ndimage.label` (connected-components) still scipy — migration exists on **unmerged** commit `bacba3a4`. |
| 1 | _astar_heuristics.py (scipy EDT) | 1 | 196 | 224 | **Migrated.** EDT delegates to `temper_geometry`; no scipy import remains. Merged (`1efa1cb3`/`3ca9ea3b`). |
| 2 | pipeline/*.py (excl. topological.py) | 18 | ~3,582 (ambiguous wording) | 3,439 | **Mostly outstanding.** Only `dag_expr.py`'s predicate parser delegates (`temper_io_types.parse_skip_expr_rs`). `convergence.py`/`derivation.py`/`preflight.py`, cited as "1,396 LOC already-PORT compute," actually sum to 795 LOC — a 601 LOC / 43% gap, largest single-note discrepancy found. |
| 3 | pipeline/stages/** | 8 | 705 | 705 | **Outstanding**, exact match. Thin `Stage.__call__` wrappers, verified. |
| 4 | router_v6 pipeline/stage orchestration | 16 | 2,624 | 2,613 | **Outstanding**, close match. No delegation detected. `_pipeline_core.py` (473) and `_pipeline_verify.py` (431) are large enough to warrant a closer read before trusting "thin wiring" at face value — not independently verified beyond import scan. |
| 5 | validation/ type/registry/gate glue | 8 | 2,564 (ledger's own correction: 2,007) | 2,008 | **Outstanding.** Ledger already self-corrected this drift; confirmed. |
| 6 | placer/cp_sat/ loop controller | 9 | 2,238 | 2,097 | **Outstanding.** No ortools import in any of the 9 files (confirms the R1/BLOCKER-ORTOOLS split is real, not smuggled). `_loop_core.py` alone is 937 LOC (45% of cluster) — large enough to warrant a closer read before ranking as pure glue. |
| 7 | pcl/ parser/compiler/glue | 9 | 1,962 | 1,962 | **Outstanding**, exact match. `sat_bridge.py` does not import ortools directly (confirms "objects migrate, ortools calls stay Python" framing holds at this file). |
| 8 | router_v6 adapter I/O | 4 | 1,484 | 1,510 | **Outstanding**, close match. `_adapter_convert.py` (1,021 LOC, 68% of cluster) is large; not independently verified beyond "I/O and orchestration" framing. |
| 9 | deterministic/stages wiring | 10 | 1,424 | 970 | **Outstanding**, but a real 454 LOC / 32% gap from stated. `drc_validation.py` already delegates to `temper_drc_rs`. Nine of ten files are 33–72 LOC (genuinely thin); `_phase_core.py` (326) and `setup.py` (250) are the bulk. |
| 10 | core/ type/registry/constant/spec glue | 11 | 1,228 | 1,228 | **Outstanding**, exact match. |
| 11 | validation/ external-tool subprocess | 5 | 1,076 | 1,076 | **Outstanding**, exact match. |
| 12 | _constraint_types/** | 9 | 1,033 | 1,033 | **Outstanding**, exact match. Carries an **unresolved R7 axis conflict** (measured-keep #719 vs. always-migrate product-authority stance) — not ready for a wave regardless of its R1 label until that's decided. |
| 13 | deterministic/ pipeline factory/wiring | 9 | 926 | 1,382 | **Outstanding**, but grew 456 LOC / 49% from stated (opposite direction of most drift here). `geometry/courtyard.py` is now a 1-line re-export shim (not the "kicad-cli wrapper" the note implies — that's `feedback/drc_runner.py`, verified). `deterministic/__init__.py` alone is 589 LOC. |
| 14 | io/ glue | 5 | 641 | 641 | **Outstanding**, exact match. |
| 15 | package root | 6 | 521 | 521 | **Outstanding**, exact match. |
| 16 | cp_sat/validator_audit.py | 1 | 509 | 509 | **Outstanding**, exact match. |
| 17 | cp_sat/feedback.py | 1 | 477 | 477 | **Outstanding**, exact match. |
| 18 | adapters/ (excl. placement_adapter.py) | 4 | not stated | 361 | **Outstanding.** |
| 19 | fields/** | 4 | 279 | 279 | **Outstanding**, exact match. `field.py`'s numpy grid ops are real compute the ledger itself flags as "arguably PORT-able," folded in here anyway. |
| 20 | cp_sat/_loop_stability.py | 1 | 168 | 168 | **Outstanding**, exact match. |
| 21 | router_v6/net_classification.py | 1 | 157 | 157 (on `main`) | **Migrated on an unmerged branch.** Commit `59ea60bc` delegates to `temper_io_types`; not in `main`. See §3. |
| 22 | router_v6 A* pathfinding kernel | 5 | 2,433 | 2,433 | **Outstanding**, exact match. `astar_core.py`'s 3D fallback tier confirmed still live (called from `_astar_search.py`, not dead code). No independent scipy use beyond the already-handled EDT call in the sibling file. |
| 23 | router_v6/_zone_pour_stitch.py | 1 | not stated (row shared w/ UNDECIDED zone_emission.py) | 298 | **Partially migrated.** Imports `temper_geometry`. The ledger's characterization ("convex hull, clustering, chamfered pour-shaping" as if fully outstanding) is stale for this file. |
| 24 | terminal-tree + path geometry | 4 | 390 | 403 | **3 of 4 already migrated** (`terminal_extraction.py`, `terminal_tree.py`, `path_simplify.py` all delegate to `temper_rust_router`). Only `grid_converter.py` (122 LOC, no Rust import) is genuinely outstanding. |
| 25 | router_v6 spatial DRC/connectivity/capacity | 23 | 7,808 | 7,813 | **Partially migrated** (5 of 23 files delegate: `channel_skeleton.py`→`temper_geometry` [medial-axis merged; island-bridging radius-pairs unmerged, see §3], `occupancy_grid.py`→`temper_geometry`, `layer_assignment.py`→`temper_rust_router`, `escape_via_generator.py`→`temper_geometry`, `net_ordering.py`→`temper_rust_router`). `constraints_spatial_index.py` still imports scipy directly on `main` (persistent-index migration is unmerged, see §3). The other 18 files show zero delegation. |
| 26 | router_v6 congestion & placement-feedback | 6 | 1,336 | 1,289 | **Substantially migrated, deliberately partial.** All 6 files import `temper_geometry`. `congestion.py`'s own module docstring names exactly 3 undelegated entry points with production-call-site-verified reasons (quoted in full in §4). Confirms the task brief's claim precisely. |
| 27 | router_v6 post-route DFM | 5 | 1,551 | 1,566 | **Substantially migrated.** All 5 files (`thermal_relief.py`, `acid_trap_detection.py`, `copper_balance.py`, `annular_ring_check.py`, `teardrop_generation.py`) delegate to `temper_drc_rs` via PR #749. `thermal_relief.py`'s docstring documents a partial/GEOS carve-out (polygonal board-outline clamp, out of Rust scope per a differential test named in-source). This is the largest mischaracterization found: the ledger lists this cluster as if fully outstanding real geometry, but it is mostly done. |
| 28 | router_v6 misc small geometry | 2 | 128 | 128 | **Outstanding**, exact match. |
| 29 | core/ graph/geometry algorithms | 12 | 2,349 | 2,349 | **Outstanding**, exact match. Real networkx/scipy algorithmic content (`hypergraph.py` imports scipy), correctly characterized — no delegation, no mischaracterization. |
| 30 | heuristics/** | 12 | ~4,378 (3,486+892) | 4,346 | **Partially migrated**, undercounted by the ledger's own note. 3 of 12 files (`organizational.py`, `structural.py`, `style.py`) delegate to `temper_geometry` via merged commits (#862, #895, #820) — the note's "sibling agent is porting this area now, still Python as of this transcription" is **stale**; that work landed. `power_stage.py`, `spectral.py`, `conflict.py`, `mcu_subsystem.py`, `graph_utils.py`, `topological_init.py` (~1,274 LOC of real heuristic algorithms) remain untouched. |
| 31 | metrics/ (aesthetic/physics/init/oracle) | 4 | not cleanly stated | 658 | **Partially migrated.** `physics.py` (328 LOC) delegates to `temper_thermal`. `aesthetic.py` (93) is outstanding real numpy compute. |
| 32 | requirements/ (init/validators geometry) | 3 | 185 | 185 | **Outstanding**, exact match. |
| 33 | physics/loop_area.py | 1 | 240 | 240 | **Outstanding**, exact match. Contains a `scipy.spatial.ConvexHull` fallback path the ledger itself flags as "would, on a finer read, be its own BLOCKER-SCIPY-shaped entry" — confirmed present; not split out. |
| 34 | io/ write/export + real_board | 9 | 3,531 | 3,513 | **Partially migrated.** `real_board.py` (724 LOC) delegates to `temper_geometry` for shoelace-area/outline-classification kernels — confirmed by reading function bodies, not the "production loader" docstring, matching the ledger's own caveat. The other 8 files (2,789 LOC: `kicad_exporter.py`, `_write_board.py`, `_write_tracks.py`, `zone_manager.py`, `placement_exporter.py`, `_write_modules.py`, `_write_zones.py`, `via_dedup.py`) show zero delegation. |
| 35 | pcl/ constraint-object compute | 6 | 2,069 | 2,069 | **Outstanding**, exact match. Has a named Rust seed (`temper-pcl-ir`) but zero delegation landed. |

## 3. Today's landings — all real, all unmerged

The task brief named four items. All four check out as genuine, correctly-scoped Rust
migrations, and all four are **absent from `main`** — they exist only on isolated agent
worktree branches (this repo runs 60+ concurrent worktrees sharing one `.git`; see
`AGENTS.md`'s git-stash-guard section for why that's normal here, not a red flag).

| Item | Commit | Ancestor of `main`? | What it does |
|---|---|---|---|
| `net_classification.py` PORT→done | `59ea60bc` | No | Delegates `is_ground_net`/`is_hv_net`/pin-pattern checks to `temper_io_types` (reusing `core/net_classification.py`'s existing bindings); adds new `*_v6` Rust surface for this file's 4 extra power-net patterns + prefix heuristic. R19 pins the old implementation as the differential oracle. |
| `routability_check.py` EDT | `1efa1cb3`/`3ca9ea3b` | **Yes** (`1efa1cb3` is on `main`) | Already landed — not a "today" item once verified against `main` rather than this worktree's stale HEAD. |
| `routability_check.py` `ndimage.label` | `bacba3a4` | No | Exact 8-connected connected-component labeling in Rust (`temper-geometry/src/connected_components.rs`, two-pass union-find). Measured 0 partition mismatches across ~8.9M cells (33 curated + 300 random trials). This was the file's last scipy binding. |
| `channel_skeleton.py` `radius_pairs` | `d2123fbd` | No | Replaces `scipy.spatial.cKDTree.query_pairs` in island-bridging MST with an `rstar` R*-tree bulk-load (`temper-geometry/src/radius_pairs.rs`). The medial-axis part of this file (a separate, earlier migration) **is** already on `main`. |
| `constraints_spatial_index.py` persistent index | `59436c05` | No | Replaces `scipy.spatial.cKDTree` with a persistent `temper_geometry.RadiusIndex` (rstar) built once per geometry kind in `rebuild_index()`. |

Net effect once these four land: entry 0 goes fully migrated (label was its last scipy
use), entry 21 goes fully migrated, and entry 25's already-partial cluster gains two more
delegated files (`channel_skeleton.py` fully so, `constraints_spatial_index.py` newly so) —
roughly 1,046 LOC (157 + 403 LOC of the 477 already-EDT-migrated routability_check.py, plus
channel_skeleton's remaining share) move from "outstanding" to "delegated" the moment these
four branches merge. This is free — no new engineering, just integration.

## 4. The congestion cluster's three deliberate keeps (verbatim)

Confirms the task brief's claim exactly. From `router_v6/congestion.py`'s module
docstring, each tied to a real production call site, not just the differential's blind spot:

- **`estimate_net_demand`** — the Rust kernel always builds a fresh zero-initialized grid;
  it has no parameter for an already-populated `grid.demand`. The only production caller
  accumulates onto the same grid across many nets, so delegating would silently drop every
  net's demand but the first.
- **`CongestionResult.get_top_bottlenecks`** — the Rust kernel takes only a list of
  `overflow` floats and reconstructs synthetic `Bottleneck` rows to match the differential's
  fixture; it cannot sort real `Bottleneck` objects without discarding their true fields.
- **`analyze_congestion`** — the Rust kernel's own pin-position resolution omits the
  bottom-side mirror (`if side == 1: px = -px`) that `core.pin_geometry.pin_world_position_at`
  applies, because its own corpus never sets `Component.initial_side`. Every real caller
  (`metrics/physics.py`, `pipeline/stages/routing_stage.py`, `router_v6/verifier.py`)
  analyzes netlists that legitimately place components on the bottom side — wiring this
  kernel would silently mis-place demand for any board using one, invisible to the
  differential.

This is the single clearest example in the ledger of a documented correctness blocker, not
a laziness shortcut, and it should be the template for how the remaining ~24 outstanding
clusters get evaluated before anyone ports them mechanically.

## 5. The R19 measurement trap, quantified

`net_classification.py`: 157 LOC pre-migration. On the unmerged migration commit
(`59ea60bc`), it becomes a delegation shim over `temper_io_types` — **and grows to 188
LOC**, because R19 requires the pre-migration constants and `_matches_any` to be retained,
unchanged and unused in production, as the pinned oracle for
`test_net_classification_rust_differential.py`. Source LOC went **up** 20% for a file that
just had all of its production logic moved to Rust.

This generalizes: every migrated file in this ledger keeps its own pre-migration body as a
frozen oracle. A raw-LOC progress metric can never show shrinkage from a Wave 4 migration —
at best it's flat, more often (wrapper + oracle > original body) it goes backwards while
real progress is being made. Cluster 27 (post-route DFM) is the sharpest illustration: it's
substantially done (5/5 files delegate to `temper_drc_rs` via PR #749) and yet its LOC
(1,566) is *larger* than the ledger's own stated pre-migration figure (1,551).

**Recommended metric instead of source LOC:** count delegated call sites / production
functions that route through a Rust kernel on the executed path, not file or module LOC.
Concretely: `(functions or call sites with >=1 `temper_*` Rust delegation) / (total
production functions in the surface)`, computed per cluster, with the pinned R19 oracle
functions explicitly excluded from the denominator (they are dead code by design, not
outstanding work). This repo already has the raw material for this — every migrated module
carries an R1a/R1b differential and performance test that names exactly which functions
delegate — a script that walks those test files and cross-references call sites would give
a real, monotonically-improving completion percentage instead of a LOC figure that can
regress under successful migrations.

## 6. Ranked next-wave list

Ranked by (LOC moved off the executed Python path) × (call-site stability) ÷ (risk),
using the verification above, not the ledger's raw LOC.

1. **Merge the four unmerged branches (§3).** Zero engineering cost, ~1,000+ LOC of
   already-measured, already-tested Rust delegation sitting idle. Do this before anything
   else — it's not a "next wave," it's an integration backlog.
2. **`grid_converter.py`** (122 LOC, entry 24). Last file in an otherwise-migrated 4-file
   cluster, proven `temper_rust_router` pattern already used by its three siblings. Lowest
   risk in the entire inventory.
3. **`constraints_spatial_index.py`'s companion `constraints_drc_oracle.py`** and the
   remaining 16 zero-delegation files in entry 25 (spatial DRC cluster). This is the
   largest surface (7,813 LOC) with an established, already-proven delegation pattern in
   the same directory (`temper_geometry`/`temper_rust_router` via 5 sibling files). Stable
   call sites (production router, not experimental). Highest LOC-value-per-risk in the
   inventory once the low-hanging fruit above is picked.
4. **Congestion cluster's 3 documented gaps** (§4, ~600-700 LOC across `estimate_net_demand`,
   `get_top_bottlenecks`, `analyze_congestion`). Well-scoped, but needs Rust kernel API
   changes (accumulator param, real `Bottleneck` fields, side-aware pin position), not a
   simple shim — medium effort, but the blockers are precisely named, which de-risks the
   estimate itself.
5. **`io/` write/export cluster's 8 undelegated files** (2,789 LOC: `kicad_exporter.py`,
   `_write_board.py`, `_write_tracks.py`, `zone_manager.py`, `placement_exporter.py`,
   `_write_modules.py`, `_write_zones.py`, `via_dedup.py`). Mechanical s-expression
   construction, stable KiCad file-format call sites, low correctness risk. Good volume,
   lower urgency than #3 since it's not on router hot paths.
6. **`deterministic/stages` wiring + `deterministic/` pipeline factory** (970 + 1,382 = 2,352
   LOC combined, entries 9 and 13). Small individual files, low risk, but check
   `_phase_core.py` (326) and `deterministic/__init__.py` (589) aren't hiding real logic
   before treating this as pure wiring.
7. **Remaining `heuristics/` algorithms** (~1,274 LOC: `power_stage.py`, `spectral.py`,
   `conflict.py`, `mcu_subsystem.py`, `graph_utils.py`, `topological_init.py`). Proven
   pattern exists in the same directory (3 siblings already delegate via merged PRs #820,
   #862, #895) — reuse that pattern rather than re-deriving it. Medium risk: real placement
   algorithms, needs a differential like the siblings got.
8. **cp_sat/ loop cluster + validator_audit.py + feedback.py + _loop_stability.py**
   (2,097 + 509 + 477 + 168 = 3,251 LOC). No ortools import, confirmed independently
   portable — but tightly coupled to the actively-evolving BLOCKER-ORTOOLS boundary next
   door, so call-site stability is the weakest in this list. `_loop_core.py` (937 LOC)
   needs a closer read before committing effort here.
9. **pcl/ clusters** (entries 7 + 35, 1,962 + 2,069 = 4,031 LOC). Named Rust seed
   (`temper-pcl-ir`) exists but is unwired. Blocked on the unresolved R7 product-authority
   question about `pcl/constraints.py`'s ortools entanglement (§2, entry 12's twin issue) —
   don't start until that's decided, or the compiler/constraint split will need to be redone.
10. **`_constraint_types/**`** (1,033 LOC, entry 12). Do not schedule until the open R7
    conflict (measured-keep #719 vs. always-migrate) is resolved by the product authority —
    otherwise this is wasted work regardless of its R1 PORT label.
11. **`pipeline/*.py` UI/dashboard glue** (`andon_observer.py` HTTP+SSE, `terminal_dashboard.py`
    rich TUI, `visualization.py`). Lowest priority: this is presentation code, not compute.
    Recommend re-triaging these specific files to REPLACE (same shape as the ledger's
    existing `cli/`/`visualization/` REPLACE entries) rather than scheduling a mechanical
    PORT — a translated rich-TUI/SSE-dashboard in Rust is not obviously the right target
    shape, and no gate in this repo can score whether a port preserved behavior.

## 6b. Adjacent finding: the BLOCKER-ORTOOLS handler justification is factually wrong

Out of scope for a PORT survey, but found while confirming entry 6's "no ortools import"
claim and material enough to record, because it concerns the one category the ledger calls
"the sole remaining genuine R1 blocker."

The ledger justifies BLOCKER-ORTOOLS for the eight `handlers/encode_*.py` files with:

> Each `encode_X` handler builds `ortools.CpModel` `AddConstraint`/`NewIntervalVar` calls
> from geometric parameters — thin wrappers over the ortools API

Measured against `main`, **none of the eight contains an ortools import or an ortools API
call**:

```
$ grep -cE '\b(ortools|cp_model|CpSolver)\b' adjacent.py aligned.py anchored.py \
      enclosing.py keepout.py loop_area.py onside.py separated.py
adjacent.py:0   aligned.py:0   anchored.py:0   enclosing.py:0
keepout.py:0    onside.py:0    separated.py:0  loop_area.py:1
```

`loop_area.py`'s single hit is line 28 — a **docstring sentence** ("Uses
`cp_model.AddMultiplicationEquality` for width*height <= max_area"), not a call. Its actual
code goes through `model.new_int_var(...)` / `model.add(...)` like every sibling. Reading
`adjacent.py`'s body confirms the shape: it calls `model.mm_to_units()`,
`model.new_assumption()` and `model.add_constraint_enforced()` — all methods of the
project's own `CpSatModel` wrapper. `AddConstraint` and `NewIntervalVar` do not appear in
any handler.

**The dependency is real but structural, not API-level.** Expressions like
`va.x_center - vb.x_center <= max_d` build ortools expression objects through operator
overloading on `IntVar`, so the handlers do depend on ortools' expression algebra. That is a
genuine coupling — but it is a materially different porting story from "thin wrappers over
the ortools API." The ortools API surface is confined to `model.py`, `_encoder_solve.py`,
`unsat.py`, and `__init__.py`. Abstract `CpSatModel`'s expression type and the 588 LOC of
handlers port mechanically; they do not require the solver-replacement decision that the
BLOCKER-ORTOOLS verdict exists to defer.

Two of the four `handlers/` infrastructure files the ledger leaves **UNDECIDED**
(`_protocol.py`, `_registry.py`) *do* import ortools — but only for type aliases
(`AssumptionLiteral = cp_model.IntVar`; the registry's `Callable[..., list[cp_model.IntVar]]`
signature). That is a typing dependency erasable at runtime, not a solve-path one.

**Recommendation (not applied — this file's verdicts are not mine to change):** correct the
BLOCKER-ORTOOLS blocker text for `handlers/*.py` to say the handlers depend on ortools
*expression objects via the `CpSatModel` wrapper*, and consider re-scoping those 588 LOC to
PORT-behind-an-abstraction. The blocker text as written would lead a reader to skip 588 LOC
of mechanically-portable code on the belief that it calls a solver API it never touches.
This does not disturb the `_encoder_solve.py` / `model.py` / `unsat.py` core of the verdict,
which is accurate and where the real blocker lives.

## 7. What I did not verify

Given the scope (36 clusters, 235 files), I confirmed delegation status for every file via
import-grep, spot-read the largest/highest-risk files in each cluster, and fully read the
four clusters called out in the task brief plus the congestion cluster's documented
blockers. I did **not** deep-read every file in entries 4, 6, 8, 9, 13, 25's 18
zero-delegation files, or 29 — flagged above wherever a file's size (>300 LOC) made "thin
wiring" or "glue" a claim worth a second look before fully trusting it for wave planning.

## 8. Addendum (independent pass): 23,684's exact source, found

A second pass over this same task (against this worktree's original stale base,
`7e1194b7`, cross-checked afterward against `main` `b31fe017` -- see below) reproduces
this document's headline number almost exactly: an independent manual glob/grep survey
of all 36 `removal_surfaces` PORT entries came to **50,874 LOC** against `7e1194b7`,
287 LOC (0.6%) off this document's 51,161 against the 33-commits-newer `main` -- close
enough to be the same finding from two independent methods (this document's
`check_verdict_coverage.py --report`, and a manual per-cluster `wc -l` + import grep),
not a coincidence.

That agreement is what makes the gap worth resolving precisely rather than leaving as
"within 10%, a guess" (§1's closing line). It resolves exactly:

```
$ python3 tools/measurements/retriage_python_removal.py
  category               LOC      %
  BLOCKER-ortools       3599   8.0%
  BLOCKER-scipy          673   1.5%
  PORT                 23684  52.8%
  ...
```

**This script is the exact, sole source of 23,684** -- confirmed unchanged on `main`
(`git show main:tools/measurements/retriage_python_removal.py`, same 20-row `PORT`
total). It is not derived from `docs/wave4-verdicts.yaml` at all: it sums a hand-written
`ROWS` constant -- 20 `(loc, "PORT", name)` tuples frozen from the *original* re-triage
pass (`docs/evidence/2026-08-06-never-port-triage.md`), predating the ledger's later
`removal_surfaces` expansion from ~20 clusters to 36. Summing exactly those 20
ROWS-table PORT entries gives 3582+2624+2564+2238+1962+1484+1424+1228+1076+1033+926+
641+521+509+477+398+393+279+168+157 = **23,684** to the digit -- not an approximation of
"clusters with zero delegation" (§1's guess), but the literal, unmaintained provenance of
the cited figure.

Concretely, the 15 clusters this document's §2 numbers 22, 25 (7,808/7,813 LOC!), 26, 27,
29, 30, and the `metrics/`, `requirements/`, `physics/loop_area.py`, `pcl/` constraint-object
(entry 35), and `io/` write/export clusters have **no row in `ROWS` at all** -- the script
was simply never updated when the ledger's `removal_surfaces` section grew to cover them.
The two largest omissions alone (entry 25's spatial-DRC cluster, 7,813 LOC, and entry 30's
`heuristics/`, 4,346 LOC) account for most of the ~27,500 LOC gap between 23,684 and the
`check_verdict_coverage.py`-confirmed 51,161. `tools/measurements/retriage_python_removal.py`
should either be deleted (superseded by `check_verdict_coverage.py --report`, which reads
the ledger live) or regenerated from it -- keeping both around, silently disagreeing by
more than 2x, is exactly the kind of decorative-number risk R7's own header comment warns
against for the *other* axis.
