---
title: router_v6 status reconciliation — what "migrated" means in this repo right now
type: evidence
date: 2026-08-06
topic: wave4-router-v6-status-reconciliation
---

<!-- provenance: commit=3524812c05e5a9a56d8624b870668d983c38cf83 dirty=UNKNOWN -->

# `router_v6/` status reconciliation

**This document reconciles, file by file, two documents that disagree by
~3,100–5,600 LOC on `router_v6/`'s migration status, and answers the
question underneath the disagreement: what does "migrated" mean in this
repo right now.** No code was migrated, no shim was rewired, and
`docs/wave4-verdicts.yaml` was not edited to produce this. Every number below
comes from a command run in this worktree against `origin/main` at commit
`3524812c0`; commands are given so the numbers reproduce.

**Bottom line up front:**

1. The two documents disagree because one of them (the triage) read
   `router_v6/` at cluster granularity and re-derived a coarse PORT/NEVER-PORT
   split, while the other (the survey) read it file by file across nine
   correction rounds. Where they disagree — 19 files, 5,601 LOC — the survey
   is right in every case I checked. This is a real disagreement, not a
   definitional one; the triage document already suspected this about itself
   and deferred to the survey, correctly.
2. **Neither document is measuring what the task's briefing found.** There is
   a fourth state, invisible to both documents' PORT/NEVER-PORT vocabulary:
   **verified Rust exists, registered, and passing its differential — called
   by nothing except the test that proves it works.** 4,096 LOC across 15
   files in `router_v6/` are in this state today. Both documents count all
   4,096 of those LOC as outstanding "PORT" debt, which is defensible under
   their own definitions but obscures that the expensive half of the work
   (write the Rust, prove it bit-identical) is already done and sitting
   unused.
3. **Shim-rewiring was never a defined phase with a gate.** The formal
   pipeline (`docs/migration-pipeline.md`, `docs/wave4-discipline-contract.md`)
   ends at "the differential is green." Making the production Python actually
   call the new Rust function is not stage 3, not a gate, not mentioned. It
   was omitted, not skipped.

---

## 0. The two source documents, and what they each measured

- `docs/evidence/2026-08-06-never-port-triage.md` ("the triage") — a
  cluster-level PORT / NEVER-PORT / ALREADY-DONE split over the repo's whole
  "Python remaining" surface (370 files / 82,310 LOC across
  `temper_placer`/`temper_workflow`), measured at commit `d5f459314`.
  `router_v6/` is one of its five largest areas, read as 15 clusters. The
  document itself flags the disagreement with the survey and defers to it as
  "more authoritative for `router_v6/` specifically" (triage §2.1).
- `docs/evidence/2026-08-04-router-v6-migration-survey.md` ("the survey") —
  a file-level classification of the 100 non-delegating `router_v6/` modules
  into PORT/GLUE/ELSEWHERE/BLOCKED/HARNESS/SPLIT/UNKNOWN/DEAD/RETIRE, "v2,"
  corrected across nine follow-up spike PRs (#743–#750) after every one of
  v1's claims was independently measured and found wrong in one direction —
  toward under-migrating. The per-file verdict lives in
  `tools/measurements/router_v6_survey/classification.csv`.

Both documents' own baselines were reproduced exactly for this document:

```
$ grep -h module-name packages/*/pyproject.toml | wc -l     # single-level glob
12
$ find packages -name pyproject.toml | xargs grep -l module-name | wc -l   # recursive
13   # + packages/temper-placer/temper-constraints/pyproject.toml (temper_constraints)
```

Using the correct, recursive 13-module list (this document's baseline
throughout):

```
temper_drc_rs, temper_dsn, temper_constraint_compiler,
temper_design_bundle_python, temper_ipc, temper_orchestration,
temper_io_types, temper_geometry, temper_quality_oracle,
temper_placement_topology, temper_thermal, temper_rust_router,
temper_constraints
```

---

## 1. What "migrated" means — the four states

The task's premise, verified in §2: "no direct Rust import" is used by both
source documents as a proxy for "not migrated," and it is wrong in **both**
directions:

- **Trap 1 (false negative on delegation):** a file can indirectly delegate
  through a sibling module that imports Rust, or (documented, not re-verified
  here) through a whole package like `topological/` that delegates via
  `temper_placement_topology` with zero direct imports.
- **Trap 2 (false positive on "still Python"):** a file can have a
  fully-verified Rust twin — registered pyfunctions, a 100%-symbol-complete
  differential, mutation-tested — while its own body is byte-for-byte
  unchanged and still executes in production. "No Rust import" here means
  "not wired," not "not built."

Four states, checked in this order:

| State | Definition | How verified here |
|---|---|---|
| **DELEGATING** | The file itself directly imports one of the 13 Rust modules, and production code reaches it. | `import`/`from` grep against the 13-module list. |
| **RUST-EXISTS-UNWIRED** | The file does **not** import Rust, but a `*_rust_differential.py` suite exists whose every `REQUIRED_RUST_SYMBOLS` entry is registered (`wrap_pyfunction!`) in the named crate, **and** grepping `packages/temper-placer/src/` for those symbol names outside the file itself returns nothing. | Symbol-by-symbol cross-reference, §3. |
| **PYTHON-ONLY** | Neither of the above; the survey's classification.csv calls it PORT (real, un-blocked compute) and no differential exists for it. | classification.csv + no matching differential. |
| **NEVER-PORT** | classification.csv calls it GLUE / ELSEWHERE / HARNESS / BLOCKED / DEAD / RETIRE / SPLIT-mostly-non-compute, or the triage's own read agrees. | classification.csv + triage cluster table. |

---

## 2. DELEGATING — the 9 files that actually run Rust in production

```
$ python3 - <<'EOF'
import re, pathlib
modules = [...]   # the 13 above
pat = re.compile(r'^\s*(?:from|import)\s+(' + '|'.join(modules) + r')\b', re.MULTILINE)
root = pathlib.Path("packages/temper-placer/src/temper_placer/router_v6")
for f in sorted(root.rglob("*.py")):
    text = f.read_text(errors="ignore")
    if pat.search(text):
        print(f.relative_to(root), len(text.splitlines()))
EOF
```

| File | LOC | Rust module | Note |
|---|---:|---|---|
| `bottleneck_geometry.py` | 1,184 | `temper_geometry` | Predates the survey; already counted delegating there. |
| `clearance_check.py` | 833 | `temper_drc_rs` | ditto |
| `_pipeline_route.py` | 630 | `temper_constraint_compiler` | ditto |
| `channel_widths.py` | 493 | `temper_geometry` | ditto |
| `creepage_check.py` | 458 | `temper_geometry` | ditto |
| `astar_core_rust.py` | 242 | `temper_rust_router` | ditto |
| `constraints_geometry.py` | 214 | `temper_geometry` | **New since the survey.** PR #732 landed after the survey was written (survey called it "in flight"); every numeric method on `Point`/`LineSegment`/`RotatedRect` now delegates. Real forward progress: −214 LOC off "Python remaining." |
| `congestion_tensor.py` | 170 | `temper_geometry` | Predates the survey. |
| `corridor.py` | 53 | `temper_geometry` | Predates the survey. Not to be confused with the *retired* `quality/corridor.py` (survey RETIRE, #750 — computed nothing, deleted; a different file, same stem). |

**Total: 9 files, 4,277 LOC.**

**Caveat (Trap 1, checked and largely ruled out for the remainder):** files
that call into these 9 for a *type* (`Point`, `LineSegment`, `ChannelWidths`)
without calling their delegated *methods* are not delegating themselves —
e.g. `constraints_drc_oracle.py` imports `Point`/`LineSegment` from
`constraints_geometry.py` but contains 762 LOC of its own DRC-oracle logic
beyond those primitives, so it stays classified by its own compute (§4), not
folded into DELEGATING. `_astar_search.py` is the one file that is mostly a
dispatch ladder *to* `astar_core_rust`'s Rust-backed functions (confirmed:
`from temper_placer.router_v6.astar_core_rust import _astar_search_rust`) —
its own classification (§5) already reflects this as GLUE, per the survey.

---

## 3. RUST-EXISTS-UNWIRED — the number nobody has

**Method.** Every `*_rust_differential.py` in `packages/temper-placer/tests/`
was grepped for the `REQUIRED_RUST_SYMBOLS` / `_pending_rust` convention this
program introduced on 2026-08-05/06 specifically for a differential that must
be green before its Rust exists:

```
$ find . -iname "*rust_differential*.py" | xargs grep -l "REQUIRED_RUST_SYMBOLS\|_pending_rust"
./packages/temper-placer/tests/heuristics/test_structural_rust_differential.py
./packages/temper-placer/tests/router_v6/test_congestion_rust_differential.py
./packages/temper-placer/tests/router_v6/test_dfm_rust_differential.py
./packages/temper-placer/tests/router_v6/test_quality_metrics_rust_differential.py
./packages/temper-placer/tests/router_v6/test_constraints_geometry_rust_differential.py
./packages/temper-placer/tests/router_v6/test_escape_via_rust_differential.py
./packages/temper-placer/tests/router_v6/test_net_ordering_rust_differential.py
```

For each, every name in `REQUIRED_RUST_SYMBOLS` was checked against the named
crate's `wrap_pyfunction!` registrations, and every registered symbol was
grepped against `packages/temper-placer/src/` for a caller outside the test
suite and the file that defines it.

| Cluster | Files | LOC | Rust crate | Symbols | Landing PR | Production caller? |
|---|---|---:|---|---:|---|---|
| Congestion & placement feedback | `congestion.py`, `congestion_analysis.py`, `congestion_heatmap.py`, `routing_demand.py`, `placement_suggestions.py`, `apply_suggestions.py` | 1,300 | `temper_geometry` | 23/23 registered | #751 (`13aee32b7`, 2026-08-06 10:26) | **None.** `grep -rl "congestion_grid_from_board_py\|...\|apply_update_positions_py" packages/temper-placer/src/` → only the test file. |
| Escape-via generation | `escape_via_generator.py` | 240 | `temper_geometry` | 2/2 registered | #751, same commit | None. |
| Net ordering | `net_ordering.py` | 361 | `temper_rust_router` | 7/7 registered | #751, same commit | None. |
| Post-route DFM | `thermal_relief.py`, `acid_trap_detection.py`, `copper_balance.py`, `annular_ring_check.py`, `teardrop_generation.py` | 1,597 | `temper_drc_rs` (`dfm_py` module) | 13/13 registered | #749 (`050bb5331`, 2026-08-05 17:00) | None. |
| Quality metrics | `metrics/slop_linter.py`, `quality/via_count.py` | 598 | `temper_quality_oracle` (`cluster_f`) | 23/23 registered | #750 (`20f2cdda8`, 2026-08-05 16:56) | None. (`quality/corridor.py`, the third module in this cluster, was retired outright — see §2's caveat — so its 8 Rust symbols exist for a deleted file.) |

**Total: 15 files, 4,096 LOC — verified Rust, zero production callers.**

**Cross-check against the task's own briefing.** The briefing cites PR #751
as "23 Rust symbols... 575-test differential passing, zero failures" for the
congestion cluster. Independently reproduced here: `REQUIRED_RUST_SYMBOLS`
in `test_congestion_rust_differential.py` has exactly 23 entries, all 23 are
registered in `congestion.rs`/`congestion_analysis.rs`/
`congestion_heatmap.rs`/`apply_suggestions.rs` via `wrap_pyfunction!`
(`grep -n wrap_pyfunction! packages/temper-geometry/src/congestion*.rs
packages/temper-geometry/src/apply_suggestions.rs`), and the file defines 40
`def test_*` functions (the 575 figure is presumably post-parametrization
expansion under pytest collection; not re-run here — no build was performed,
per the task's disk-budget guidance). What **is** independently confirmed
without a build: `grep -rl` for every one of the 23 symbol names across
`packages/temper-placer/src/` returns only the differential test file itself.

**A methodological trap found while doing this check, worth naming
explicitly:** `test_congestion_rust_differential.py`'s docstring still opens
with **"THIS SUITE IS DELIBERATELY RED"** — written when only Phase A
(oracle + RED differential, no Rust) existed. Phase B landed in the *same
squashed commit* on `origin/main` (`13aee32b7`) that also carries the
docstring, but the docstring text was never updated. The same pattern repeats
in `test_dfm_rust_differential.py` ("No Rust exists on this branch") and
`test_quality_metrics_rust_differential.py`, both stale in the same way after
#749/#750 landed. **The RED/GREEN status text in these docstrings cannot be
trusted after the fact — only checking symbol registration and production
call sites settles it.** This is exactly why the triage, reading these
clusters at commit `d5f459314` (7 minutes *after* all five clusters' Rust had
already landed on `origin/main` — see the commit timestamps in §6), still
called all five clusters plain PORT: the file bodies, the module docstrings,
and even the differential suites' own headers all read as "not yet done."

**A negative control, to show the method isn't just pattern-matching the
marker:** `packages/temper-placer/tests/heuristics/test_structural_rust_differential.py`
uses the identical `REQUIRED_RUST_SYMBOLS`/pending-Rust convention for
`heuristics/structural.py`'s `create_keepout_mask`. Checked the same way:
`temper_geometry.keepout_mask_flags_py` is registered, **and**
`heuristics/structural.py:75` contains `from temper_geometry import
keepout_mask_flags_py`, called unconditionally at line 86. This one **is**
wired — production calls it. So the Phase-A/Phase-B split by itself doesn't
predict whether the wiring happened; it has to be checked per cluster. Four
of five router_v6 clusters skipped the wiring step; the heuristics one and
`constraints_geometry.py` (§2) did not.

---

## 4. PYTHON-ONLY — real, un-blocked compute with no Rust twin at all

21 files, 6,736 LOC, where classification.csv says PORT and no differential
of any kind exists yet: the A* search family minus its already-delegated
kernel (`astar_core.py`, `_astar_theta_star.py`, `_astar_ordering.py`,
`astar_grid.py`), the DRC-distance cluster
(`constraints_drc_oracle.py`, `constraints_spatial_index.py`,
`connectivity.py`, `terminal_tree.py`, `terminal_extraction.py`),
occupancy/resource-bound/capacity/layer-capacity, `channel_mapping.py`
(survey: delete the unreachable nx branch, port the rest), `power_plane.py`,
`obstacle_map.py`, `routing_space.py`, `_zone_pour_stitch.py`,
`grid_converter.py`/`path_simplify.py`, `neighbor_validity.py` (not covered
by the triage's cluster table at all — see §6).

---

## 5. NEVER-PORT — 60 files, 13,488 LOC

Everything else: orchestration, contracts, harness, blocked-on-GEOS/scipy,
dead/retired. Full per-file breakdown is in the reconciled table, §7. Of
these 60 files, **41 (7,887 LOC)** are ones the triage also calls NEVER-PORT
or doesn't cover — real agreement. The other **19 (5,601 LOC)** are exactly
where the two documents disagree, covered next.

---

## 6. The ~3,100 LOC gap: how much is definitional, how much is real

The triage's own text states the disagreement as: survey "PORT 13,317 /
NEVER-PORT 9,859 / unresolved 1,144" vs. its own cluster read of "PORT
16,424 / NEVER-PORT 7,896" — a gap of **3,107 LOC**, computed at the
statement/partial-credit level the triage used for its self-cross-check.

Redone here at file granularity, with every file forced to one verdict using
classification.csv's post-correction bucket as ground truth (rather than
splitting SPLIT/UNKNOWN rows for partial credit):

```
$ python3 rv6_map.py   # script in this document's provenance; joins
                        # classification.csv, the triage's transcribed
                        # cluster table, and a live import/LOC scan
```

- **Files where triage=PORT and survey-bucket=PORT ("agree PORT"): 35 files, 10,717 LOC.**
- **Files where triage=NEVER-PORT and survey-bucket≠PORT ("agree NEVER-PORT"): 41 files, 7,887 LOC.**
- **Files where triage=PORT but survey-bucket≠PORT (disagreement): 19 files, 5,601 LOC.**
- **Files where triage=NEVER-PORT but survey-bucket=PORT: 0 files.** The triage never under-calls PORT relative to the survey — it only over-calls it. One direction, no exceptions.

| File | LOC | Survey bucket | Survey's own reason (from classification.csv) |
|---|---:|---|---|
| `_astar_search.py` | 679 | GLUE | "dispatch + fallback ladder around the Rust kernel; the only arithmetic is coordinate marshalling for the pyo3 call" |
| `constraint_model.py` | 653 | ELSEWHERE | "recorded Phase 2 contract in `docs/wave4-verdicts.yaml:110`" — the ledger itself already has this right |
| `constraints_design_rules.py` | 639 | SPLIT | 90 PORT / 20 Phase-3 / 40 BLOCKED (GEOS via ZoneManager STRtree) / 64 DEAD / 36 PORT-or-Phase-3 — genuinely mixed, not uniform PORT |
| `layer_assignment.py` | 557 | GLUE | "enum/pattern lookup; density 0.12; one 31-stmt kernel is separable" |
| `_astar_reconstruct.py` | 506 | GLUE | "run_astar_pathfinding is a 175-stmt driver... the search it calls is Rust" |
| `channel_skeleton.py` | 464 | BLOCKED | GEOS Voronoi determinism confirmed, but the real blocker (`edge_id` from unrounded float `repr`) survives |
| `bundle_analyzer.py` | 422 | UNKNOWN | "whether the GEOS hull is separable from the partitioning kernel was not determined" |
| `clearance_engine.py` | 286 | GLUE | "clearance-table lookup + voltage-class branching; density 0.15" |
| `bottleneck_analysis.py` | 221 | GLUE | "Stage wrapper + two ~16-stmt helpers" |
| `zone_emission.py` | 206 | BLOCKED | scipy dissolved, but a GEOS convex-hull boundary the survey's v1 missed was found (#748) |
| `dense_package_detection.py` | 198 | GLUE | "pitch estimation + package-type inference; density 0.20" |
| `trace_width_assignment.py` | 177 | GLUE | "keyword -> width table lookup; density 0.27" |
| `via_placement.py` | 177 | GLUE | "#749 CORRECTION: two `abs()` subtractions is its entire arithmetic" |
| `diff_pair_inference.py` | 163 | GLUE | "net-name pairing rules; density 0.15" |
| `audit_tree_geometry.py` | 116 | HARNESS | "post-solve audit helper; 0 `src` consumers, 1 test" |
| `placement_audit.py` | 97 | GLUE | "S1/#747 CORRECTION: not a GEOS blocker at all — advisory diagnostics whose output reaches only a `verbose` print" |
| `placement_legalization.py` | 31 | GLUE | "8-stmt guard delegating to `placement_audit`" |
| `metrics/__init__.py` | 5 | GLUE | package re-export |
| `quality/__init__.py` | 4 | GLUE | package re-export |

**Verdict on the gap: it is real, not definitional, and the survey is right
in all 19 cases checked.** None of it is explained by the
DELEGATING/RUST-EXISTS-UNWIRED distinction from §§2–3 — that axis is
orthogonal and affects a *different* set of files (the RUST-EXISTS-UNWIRED
15 are PORT in both documents; nobody disagrees about them, they're just
both wrong that they're outstanding work in the way they imply). The 5,601
LOC disagreement instead traces to the triage's cluster read folding several
files with independently re-verified GLUE/ELSEWHERE/BLOCKED/HARNESS/SPLIT/
UNKNOWN verdicts (`constraints_drc_oracle`'s neighbors in its "Spatial
DRC/connectivity/capacity/topology cluster" table row, mostly) wholesale into
its 8,911-LOC PORT bucket, without re-reading them individually — which the
triage document itself already suspected about this specific area and said
so (its own §2.1 note: "the true `router_v6` PORT figure is more likely in
the 13,300–16,400 range than a single point estimate... which neither pass
completed").

Two secondary, smaller-magnitude issues found while reconciling, neither
large enough to matter to the conclusion above but both real:

- **The triage's own per-cluster LOC sums have a small internal arithmetic
  drift.** Summing the 15 cluster rows in triage §2.1 gives 23,846 LOC, not
  the stated 24,320 (−474, ~2%); re-deriving each cluster's total directly
  from its listed filenames via `wc -l` reproduces the same small (20–55
  LOC) shortfall in three of the four largest clusters. Likely a counting
  convention difference (e.g. `splitlines()` vs a trailing-newline-sensitive
  count) rather than a wrong file list — not investigated further, flagged
  here so it isn't silently propagated.
- **Two files are missing from the triage's cluster table entirely:**
  `_net_policy.py` (61 LOC, survey: GLUE) and `neighbor_validity.py` (115
  LOC, survey: PORT — "its output is already the Rust A* kernel's input").
  176 LOC not assigned any triage verdict; accounts for part of the drift
  above.

---

## 7. The reconciled file-level table

All 105 files currently under
`packages/temper-placer/src/temper_placer/router_v6/`, one row each, the
table both source documents' `router_v6/` sections can be replaced by.
Reproduction: the script in §6, run against `origin/main` at `3524812c0`.

| File | LOC | Class | Survey bucket (2026-08-04) | Triage cluster verdict (2026-08-06) |
|---|---:|---|---|---|
| `bottleneck_geometry.py` | 1184 | DELEGATING | (not in CSV — already delegating at survey time) | not covered |
| `clearance_check.py` | 833 | DELEGATING | (not in CSV) | not covered |
| `_pipeline_route.py` | 630 | DELEGATING | (not in CSV) | not covered |
| `channel_widths.py` | 493 | DELEGATING | (not in CSV) | not covered |
| `creepage_check.py` | 458 | DELEGATING | (not in CSV) | not covered |
| `astar_core_rust.py` | 242 | DELEGATING | (not in CSV) | not covered |
| `constraints_geometry.py` | 214 | DELEGATING | PORT (in flight, PR #732) | not covered |
| `congestion_tensor.py` | 170 | DELEGATING | (not in CSV) | not covered |
| `corridor.py` | 53 | DELEGATING | (not in CSV) | not covered |
| `thermal_relief.py` | 544 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `congestion.py` | 476 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `net_ordering.py` | 361 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `acid_trap_detection.py` | 332 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `metrics/slop_linter.py` | 329 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `copper_balance.py` | 270 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `quality/via_count.py` | 269 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `escape_via_generator.py` | 240 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `annular_ring_check.py` | 230 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `teardrop_generation.py` | 221 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `routing_demand.py` | 187 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `congestion_analysis.py` | 178 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `placement_suggestions.py` | 178 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `apply_suggestions.py` | 154 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `congestion_heatmap.py` | 127 | RUST-EXISTS-UNWIRED | PORT | PORT |
| `constraints_drc_oracle.py` | 762 | PYTHON-ONLY | PORT | PORT |
| `astar_core.py` | 655 | PYTHON-ONLY | PORT | PORT |
| `channel_mapping.py` | 568 | PYTHON-ONLY | PORT (corrected from BLOCKED, #744 — delete the unreachable nx branch) | PORT |
| `occupancy_grid.py` | 550 | PYTHON-ONLY | PORT | PORT |
| `_astar_theta_star.py` | 431 | PYTHON-ONLY | PORT (not on the `route_pcb` production entry — see survey §2.1) | PORT |
| `constraints_spatial_index.py` | 403 | PYTHON-ONLY | PORT (corrected from BLOCKED, #743) | PORT |
| `resource_bound.py` | 390 | PYTHON-ONLY | PORT | PORT |
| `connectivity.py` | 383 | PYTHON-ONLY | PORT | PORT |
| `_zone_pour_stitch.py` | 363 | PYTHON-ONLY | PORT (corrected from BLOCKED, #743) | PORT |
| `astar_grid.py` | 350 | PYTHON-ONLY | PORT | PORT |
| `power_plane.py` | 319 | PYTHON-ONLY | PORT | PORT |
| `obstacle_map.py` | 293 | PYTHON-ONLY | PORT (corrected from BLOCKED, #747) | PORT |
| `routing_space.py` | 219 | PYTHON-ONLY | PORT (corrected from BLOCKED, #747) | PORT |
| `capacity_check.py` | 214 | PYTHON-ONLY | PORT | PORT |
| `layer_capacity.py` | 169 | PYTHON-ONLY | PORT | PORT |
| `_astar_ordering.py` | 162 | PYTHON-ONLY | PORT | PORT |
| `grid_converter.py` | 122 | PYTHON-ONLY | PORT | PORT |
| `neighbor_validity.py` | 115 | PYTHON-ONLY | PORT | **not covered by triage** |
| `path_simplify.py` | 112 | PYTHON-ONLY | PORT | PORT |
| `terminal_tree.py` | 81 | PYTHON-ONLY | PORT | PORT |
| `terminal_extraction.py` | 75 | PYTHON-ONLY | PORT | PORT |
| `_adapter_convert.py` | 995 | NEVER-PORT | GLUE | NEVER-PORT |
| `_astar_search.py` | 679 | NEVER-PORT | GLUE | **PORT (disagreement)** |
| `constraint_model.py` | 653 | NEVER-PORT | ELSEWHERE | **PORT (disagreement)** |
| `constraints_design_rules.py` | 639 | NEVER-PORT | SPLIT | **PORT (disagreement)** |
| `layer_assignment.py` | 557 | NEVER-PORT | GLUE | **PORT (disagreement)** |
| `benchmark.py` | 552 | NEVER-PORT | HARNESS | NEVER-PORT |
| `_astar_reconstruct.py` | 506 | NEVER-PORT | GLUE | **PORT (disagreement)** |
| `routability_check.py` | 477 | NEVER-PORT | BLOCKED (KTD8, `edt` crate rejected) | NEVER-PORT |
| `_pipeline_core.py` | 464 | NEVER-PORT | GLUE | NEVER-PORT |
| `channel_skeleton.py` | 464 | NEVER-PORT | BLOCKED | **PORT (disagreement)** |
| `_pipeline_verify.py` | 431 | NEVER-PORT | GLUE | NEVER-PORT |
| `bundle_analyzer.py` | 422 | NEVER-PORT | UNKNOWN | **PORT (disagreement)** |
| `diagnostics.py` | 350 | NEVER-PORT | ELSEWHERE | NEVER-PORT |
| `_adapter_core.py` | 322 | NEVER-PORT | GLUE | NEVER-PORT |
| `clearance_engine.py` | 286 | NEVER-PORT | GLUE | **PORT (disagreement)** |
| `manufacturing_report.py` | 286 | NEVER-PORT | GLUE | NEVER-PORT |
| `verifier.py` | 241 | NEVER-PORT | GLUE | NEVER-PORT |
| `routing_results.py` | 233 | NEVER-PORT | ELSEWHERE | NEVER-PORT |
| `terminal_tree_execution.py` | 225 | NEVER-PORT | ELSEWHERE | NEVER-PORT |
| `bottleneck_analysis.py` | 221 | NEVER-PORT | GLUE | **PORT (disagreement)** |
| `astar_monitor.py` | 213 | NEVER-PORT | HARNESS | NEVER-PORT |
| `zone_emission.py` | 206 | NEVER-PORT | BLOCKED (GEOS convex hull, #748) | **PORT (disagreement)** |
| `dense_package_detection.py` | 198 | NEVER-PORT | GLUE | **PORT (disagreement)** |
| `_astar_heuristics.py` | 196 | NEVER-PORT | BLOCKED (KTD8) | NEVER-PORT |
| `stage_ledger.py` | 193 | NEVER-PORT | GLUE | NEVER-PORT |
| `stage0_data.py` | 188 | NEVER-PORT | ELSEWHERE | NEVER-PORT |
| `kicad_connectivity.py` | 186 | NEVER-PORT | ELSEWHERE (Phase-3 formats/IO) | NEVER-PORT |
| `trace_width_assignment.py` | 177 | NEVER-PORT | GLUE | **PORT (disagreement)** |
| `via_placement.py` | 177 | NEVER-PORT | GLUE | **PORT (disagreement)** |
| `_routing_reports.py` | 175 | NEVER-PORT | ELSEWHERE | NEVER-PORT |
| `diff_pair_inference.py` | 163 | NEVER-PORT | GLUE | **PORT (disagreement)** |
| `test_boards.py` | 162 | NEVER-PORT | HARNESS | NEVER-PORT |
| `net_classification.py` | 157 | NEVER-PORT | GLUE | NEVER-PORT |
| `route_stage.py` | 157 | NEVER-PORT | GLUE | NEVER-PORT |
| `_adapter_types.py` | 137 | NEVER-PORT | ELSEWHERE | NEVER-PORT |
| `all_pad_evidence.py` | 130 | NEVER-PORT | HARNESS | NEVER-PORT |
| `_pipeline_types.py` | 128 | NEVER-PORT | ELSEWHERE | NEVER-PORT |
| `_pipeline_grid.py` | 118 | NEVER-PORT | GLUE | NEVER-PORT |
| `audit_tree_geometry.py` | 116 | NEVER-PORT | HARNESS | **PORT (disagreement)** |
| `__init__.py` | 109 | NEVER-PORT | GLUE | NEVER-PORT |
| `_strip_copper.py` | 103 | NEVER-PORT | ELSEWHERE (Phase-3 formats/IO) | NEVER-PORT |
| `audit_provenance.py` | 102 | NEVER-PORT | HARNESS | NEVER-PORT |
| `placement_audit.py` | 97 | NEVER-PORT | GLUE | **PORT (disagreement)** |
| `stage2_orchestrator.py` | 94 | NEVER-PORT | GLUE | NEVER-PORT |
| `grid_prep_stage.py` | 83 | NEVER-PORT | GLUE | NEVER-PORT |
| `result_aggregate_stage.py` | 71 | NEVER-PORT | GLUE | NEVER-PORT |
| `astar_pathfinding.py` | 68 | NEVER-PORT | GLUE | NEVER-PORT |
| `stage_validators.py` | 65 | NEVER-PORT | GLUE | NEVER-PORT |
| `adapter.py` | 64 | NEVER-PORT | GLUE | NEVER-PORT |
| `tree_route_geometry.py` | 64 | NEVER-PORT | ELSEWHERE | NEVER-PORT |
| `net_prep_stage.py` | 62 | NEVER-PORT | GLUE | NEVER-PORT |
| `stage4_orchestrator.py` | 62 | NEVER-PORT | GLUE | NEVER-PORT |
| `_net_policy.py` | 61 | NEVER-PORT | GLUE | **not covered by triage** |
| `_check_report_base.py` | 43 | NEVER-PORT | ELSEWHERE | NEVER-PORT |
| `topology_solver.py` | 43 | NEVER-PORT | SPLIT (24 stmts live contracts, 45 retired — #745) | NEVER-PORT |
| `topology_extraction.py` | 40 | NEVER-PORT | SPLIT (20 live contracts, 36 dead — #745) | NEVER-PORT |
| `pipeline.py` | 37 | NEVER-PORT | GLUE | NEVER-PORT |
| `placement_legalization.py` | 31 | NEVER-PORT | GLUE | **PORT (disagreement)** |
| `metrics/__init__.py` | 5 | NEVER-PORT | GLUE | **PORT (disagreement)** |
| `quality/__init__.py` | 4 | NEVER-PORT | GLUE | **PORT (disagreement)** |

**Totals: 105 files, 28,597 LOC.** DELEGATING 4,277 (15.0%) · RUST-EXISTS-UNWIRED
4,096 (14.3%) · PYTHON-ONLY 6,736 (23.6%) · NEVER-PORT 13,488 (47.2%).

`quality/corridor.py` (survey: RETIRE, #750 — "computes nothing," both
coordinate frames it compares are incompatible) does not appear: it has
already been deleted from `router_v6/` since the survey was written, which
is itself a small piece of forward progress neither source document credits
explicitly.

---

## 8. Does shim-rewiring have a gate? What the discipline docs actually say

Checked, verbatim, rather than assumed:

**`docs/migration-pipeline.md`** defines the six pipeline stages every
migration runs through. Stage 3 ("work") is spelled out completely:

> TDD: differential test pinning the pre-migration implementation as oracle,
> written first (red), then the Rust pyfunction (green). Behavioral A/B...
> Performance A/B... PBT... Metamorphic testing... Induction proof... Rust
> best practices... Commit + push to the worktree branch; the orchestrator
> merges and verifies.

Nothing in that list is "update the Python call site to import and use the
new Rust function." The stage's own definition of done is the differential
turning green — not the production code path changing.

**`docs/wave4-discipline-contract.md`**'s gate checklist (G1–G8) is entirely
about *correctness verification of the Rust*: G1 differential-oracle-first,
G2 bit-identical parity, G3 performance A/B, G4 PBT, G5 metamorphic testing,
G6 induction proof, G7 Rust best practices, G8 physics discipline (gated
surfaces only). None of the eight gates requires or checks that any Python
caller was updated. Grepping the document for `call site`, `wire`,
`delegat`, `shim` turns up only unrelated bit-exactness-catalog entries
(which crate file a given float-semantics fix lives in) — no gate language.

**The Phase A / Phase B split itself is an ad hoc convention, not a specified
program phase.** `tests/router_v6/_pending_rust.py`'s own docstring says so
directly:

> The repo had no convention for that state, because every Wave-4
> differential landed so far was written in the same PR as its Rust... This
> slice is the first PR that is deliberately Phase A only, so it has to
> choose one.

And "Phase B," as used in the commit messages that actually landed the Rust
(`feat(wave4): cluster-D DFM kernels to Rust — 17 symbols, differential
green (#749)`, `feat(wave4): cluster-F quality metrics to Rust — 23 kernels,
differential green (#750)`), is defined by its own success criterion:
**"differential green."** Not "production wired." The commit that adds the
Rust and turns the test green is, by its own stated definition, done.

**Conclusion: shim-rewiring was never specified as a deliverable of either
phase.** It isn't a corner someone cut under time pressure — it's a step the
pipeline doesn't name. `docs/wave4-verdicts.yaml`'s `router_v6/**` entry
(read, not edited) is a single `MIGRATE phase 5` pattern over the whole
subtree with no sub-clause distinguishing "Rust exists" from "Rust is
called," so there's no ledger mechanism to flag the gap either — a
`RUST-EXISTS-UNWIRED` file and a `PYTHON-ONLY` file both read identically as
"still needs work" under the ledger's current vocabulary.

**A third document independently touches this and also misses it.**
`docs/evidence/2026-08-06-wave4-owned-surface-closeout.md` (provenance commit
`8893ab5ca`, also 2026-08-06) audits every `MIGRATE` surface repo-wide using
its own four-state framework (MIGRATED / OWNED / JUSTIFIED-KEEP / UNMIGRATED
+ UNOWNED) and explicitly notes for `router_v6/**`: *"OWNED — router_v6
workstream... clusters D/F landed (#749/#750)."* It knows the DFM and
quality-metrics Rust landed — closer to correct than either of the two main
documents — but still classifies the whole subtree as one undifferentiated
`OWNED` bucket, the same vocabulary gap: no state in its framework, either,
distinguishes "kernel built and proven" from "kernel called."

---

## 9. What this document does not claim

- **Repo-wide RUST-EXISTS-UNWIRED total is not fully enumerated.** The method
  in §3 (grep for the `REQUIRED_RUST_SYMBOLS`/`_pending_rust` convention)
  finds every file using that *specific, newly-introduced* convention — 7
  files repo-wide, 6 of them in `router_v6/` (the 5 clusters in §3) plus
  `heuristics/structural.py` (checked and found to be wired — §3's negative
  control). The other ~113 `*_rust_differential.py` suites in the repo
  predate this convention; per `_pending_rust.py`'s own docstring, "every
  Wave-4 differential landed so far was written in the same PR as its Rust,"
  meaning historically Phase A/B were never split — so the specific failure
  mode this document quantifies (kernel built, never wired) is plausibly
  new, starting with this 2026-08-05/06 batch, rather than latent across the
  whole differential suite. This is a plausibility argument from the
  convention's own stated history, not an exhaustive symbol-by-symbol audit
  of all ~113 other suites, which was out of scope for the time available.
- **The 19-file, 5,601-LOC disagreement list was checked against
  classification.csv's stated reasons, not re-derived from the source
  independently for every file.** The survey's reasons are themselves the
  product of nine spike PRs with cited evidence (#743–#750); this document
  did not re-run those spikes, only checked that the triage's cluster read
  didn't reflect their conclusions.
- **`bundle_analyzer.py`'s UNKNOWN status is inherited, not resolved.**
  Whether its GEOS convex-hull seam is separable from its partitioning
  kernel remains undetermined, same as when the survey was written.

---

## Reproducing this document

```bash
# 13-module list (recursive — the correct one)
find packages -name pyproject.toml | xargs grep -l module-name

# DELEGATING scan (§2)
python3 - <<'EOF'
import re, pathlib
modules = ["temper_drc_rs","temper_dsn","temper_constraint_compiler",
"temper_design_bundle_python","temper_ipc","temper_orchestration",
"temper_io_types","temper_geometry","temper_quality_oracle",
"temper_placement_topology","temper_thermal","temper_rust_router",
"temper_constraints"]
pat = re.compile(r'^\s*(?:from|import)\s+(' + '|'.join(modules) + r')\b', re.MULTILINE)
root = pathlib.Path("packages/temper-placer/src/temper_placer/router_v6")
for f in sorted(root.rglob("*.py")):
    text = f.read_text(errors="ignore")
    m = pat.search(text)
    if m:
        print(f.relative_to(root), len(text.splitlines()), m.group(1))
EOF

# RUST-EXISTS-UNWIRED scan (§3)
find . -iname "*rust_differential*.py" | xargs grep -l "REQUIRED_RUST_SYMBOLS\|_pending_rust"
# then, per file: extract REQUIRED_RUST_SYMBOLS, grep each symbol against
# the named crate's src/*.rs for `wrap_pyfunction!`, and against
# packages/temper-placer/src/ for a production caller outside the test file.

# Congestion cluster spot-check, no build required:
grep -c '"[a-z_]*_py"' <(sed -n '/REQUIRED_RUST_SYMBOLS/,/^)/p' \
  packages/temper-placer/tests/router_v6/test_congestion_rust_differential.py)
grep -rl "congestion_grid_from_board_py" packages/temper-placer/src/
```

## Sources

- `docs/evidence/2026-08-06-never-port-triage.md`
- `docs/evidence/2026-08-04-router-v6-migration-survey.md` and
  `tools/measurements/router_v6_survey/classification.csv`
- `docs/evidence/2026-08-06-wave4-owned-surface-closeout.md`
- `docs/wave4-discipline-contract.md`, `docs/migration-pipeline.md`,
  `docs/wave4-verdicts.yaml` (read-only)
- `tests/router_v6/_pending_rust.py` docstring (the Phase A/B convention's
  own stated rationale and history)
- PR commit messages: `13aee32b7` (#751, congestion/escape-via/net-ordering),
  `050bb5331` (#749, DFM), `20f2cdda8` (#750, quality metrics)
