# Wave 4 owned-surface close-out: every MIGRATE surface classified (2026-08-06)

<!-- provenance: commit=8893ab5ca75283f0a538d0b6154711e6a3f97b76 dirty=false -->

**Scope:** post-regression ledger close-out. Read-only audit of every `MIGRATE`
surface in `docs/wave4-verdicts.yaml` against the codebase at the provenance
commit. No code migrated, no files deleted, no Rust written. Corrections to the
ledger are recorded as dated comments only; no verdict is flipped.

**Why this pass exists:** the program's owned surface is nearly exhausted. The
ledger still names surfaces `MIGRATE phase N`, but a MIGRATE verdict is an
assignment, not a promise that the surface is unmigrated. This audit re-derives,
for every MIGRATE surface, which of four states it is actually in: **MIGRATED**
(files are delegation shims over a `temper_*` crate on `origin/main`),
**OWNED** (an open PR or branch carries the remainder), **JUSTIFIED-KEEP**
(a Phase-6 verdict or recorded blocker covers it), or **UNMIGRATED + UNOWNED**
(should be none; each one found is flagged).

**A note on the dispatch brief's owned list.** The brief named nine surfaces as
owned-by-open-PR: router_v6, pipeline, heuristics, pcl (#721), placer core
(#724), metrics (#697), DSN (#694), _constraint_types (#719), topological
(#714). **Seven of those PRs merged while this audit ran** (pcl #721, core
#724, metrics #697, DSN #694, _constraint_types #719, analysis #737, topological
#714, plus #692/#755/#741/#795). The owned list below reflects the state at the
provenance commit, not the brief's snapshot.

---

## 1. Per-surface classification

`CRATE` = the file imports one of the shipped pyo3 modules
(`temper_design_bundle_python`, `temper_geometry`, `temper_io_types`,
`temper_thermal`, `temper_drc_rs`, `temper_rust_router`,
`temper_orchestration`, `temper_constraint_compiler`, `temper_dsn`,
`temper_quality_oracle`, `temper_ipc`, `temper_constraints`,
`temper_placement_topology`). A file can legitimately sit in `MIGRATE` but be
plain Python if its verdict was recorded but the work is unowned — that is the
class this audit exists to surface.

| Surface | Verdict (ledger) | Files | CRATE | Plain | Classification |
|---|---|---|---|---:|---:|---|
| `core/**` | MIGRATE P2 | 37 | 14 | 23 | **OWNED→MIGRATED partial** — #724 merged (contract layer); 23 plain files (bus_cohort, decision, graph, hypergraph, net_graph, netclass_rules_gen, power_topology, specification, stackup, topology, loop_ownership, loop_extractor, community, courtyard, differential_pair, geometry_types, interfaces, isolation_constants, pin_geometry, routing_validator, state, `__init__`, `_contract_dataclass_compat`) are **UNMIGRATED + UNOWNED** |
| `pcl/**` | MIGRATE P2 | 18 | 3 | 15 | **OWNED→MIGRATED partial** — #721 merged (tag_dispatch, _parse_utils); constraints.py, parser, sat_bridge, linter, resolver + 10 more plain and **UNOWNED**. Always-migrate note (2026-08-05) stands |
| `_constraint_types/**` | MIGRATE P2 | 9 | 0 | 9 | **VERDICT IN CONFLICT** — #719 merged (2026-08-06) with a measured verdict *"do not migrate `_constraint_types` — not a pyo3-pyclass candidate"*, and it *deliberately did not edit the ledger*. The ledger entry is untouched; the merged verdict now contradicts it. Recorded as a correction comment, not flipped |
| `io/**` | MIGRATE P3 | 42 | 24 | 18 | **MIGRATED partial + OWNED + UNOWNED** — parse engine/loaders/DSN landed (#712/#716/#723/#701/#694). 18 plain: write engine candidate-4 (`kicad_exporter`, `kicad_writer`, `_write_*`, `placement_exporter`) on branches `feat/wave4-phase3-write-engine-rust`/`-p2` with **no PR ever opened** (flagged §3); `net_class_manager` is a planned RETIRE (plan R8) never executed; `real_board` (#702, new); boundary_registry/snapshot/via_dedup/zone_manager plain+unowned |
| `geometry/**` | MIGRATE P4 | 11 | 10 | 1 | **MIGRATED + JUSTIFIED-KEEP** — #695 merged (drc_inflate); `kicad_transform.py` kept on the GEOS/rotation-convention blocker recorded in #695 |
| `metrics/**` | MIGRATE P4 | 7 | 3 | 4 | **OWNED→MIGRATED partial** — #697 merged (quality.py); `aesthetic`, `external_oracle`, `physics`, `__init__` plain and **UNOWNED** |
| `regression/**` | MIGRATE P4 | 14 | 1 | 13 | **OWNED** — #793 open (verdict split in review); its carve-out (6 harness modules → JUSTIFIED-KEEP) is **pending, not in the ledger** (recorded §2) |
| `physics/**` | MIGRATE P4 | 13 | 12 | 1 | **MIGRATED** (#720) — `loop_area.py` is the recorded KTD9 scipy keep. Ledger note claims "KTD9 recorded below" but **no such ledger entry exists** (correction §4) |
| `topological/**` | MIGRATE P4 | 6 | 5 | 1 | **MIGRATED** — #714 merged (2026-08-06); the BLAS `ddot` parity defect was resolved in-PR (benchmark pins the unfused association; VERIFICATION.md §1). `__init__` is a re-export |
| `analysis/**` | MIGRATE P4 | 3 | 2 | 1 | **MIGRATED** — #737 merged; `__init__` re-export |
| `manufacturing/**` | MIGRATE P4 | 4 | 3 | 1 | **MIGRATED** — #766 merged; `__init__` re-export |
| `validation/**` | MIGRATE P4 | 37 | 16 | 21 | **MIGRATED partial + UNOWNED remainder** — #717 (DRC-check) + #761 (remainder) merged. 21 plain: `drc_types`/`drc_result` (Phase-2 contracts, ledger note says they "land earlier" — they have not landed and have no owner), mfem_*, scheduler, scorecard, helps_battery, metrics, manufacturing, validation_gates, _drc_api, base, results/*, prereg/__init__, spice_* — **UNMIGRATED + UNOWNED** |
| `pipeline/**` | MIGRATE P5 | 30 | 0 | 30 | **OWNED** — #731 open (dag_expr slice, DO NOT MERGE); 0 crate files on main |
| `deterministic/**` | MIGRATE P5 | 52 | 14 | 38 | **MIGRATED partial + UNOWNED remainder** — #762 (leaf stages) + #767 (hubs) merged. 9 orchestration hubs carry R3-style records (hubs evidence 2026-08-04): state, stages/base, stages/setup, feedback/{orchestrator,drc_runner}, instrumentation, flags, guard_strip, courtyard. **25 leaf-stage files (5,467 LOC) carry no record and have no owner** — `_phase_*`, `_grid_stage`, apply_placements, clearance_grid, component_assignment, config_attach, connectivity_validation, courtyard_check, drc_sweep, drc_validation, fine_pitch_escape, hv_lv_partition, layer_assignment, net_ordering, phased_component_assignment(+validator), placement_validation, power_plane, routing_metrics, sequential_routing_dataclasses, via_validation, zone_aware_slot_generation. Flagged §3 |
| `cli/**` | MIGRATE P5 | 11 | 2 | 9 | **MIGRATED partial** — #754 merged (timing, trace_commands); remaining 9 carry R3-style glue records (orchestration VERIFICATION.md) |
| `heuristics/**` | MIGRATE P5 | 12 | 0 | 12 | **OWNED** — branch `feat/wave4-phase5-heuristics-rust` (wip, no PR); 0 crate files on main |
| `router_v6/**` | MIGRATE P5 | 105 | 9 | 96 | **OWNED** — router_v6 workstream (#741 survey, #751 tests, spikes #743–#748, #755 retire); clusters D/F landed (#749/#750) |
| `adapters/**` | MIGRATE P5 | 5 | 0 | 5 | **R3 glue records** — #754 recorded all five as pure-dispatch glue (orchestration VERIFICATION.md); no crate imports by design |
| `report/**` | MIGRATE P5 | 3 | 3 | 0 | **MIGRATED** — #758 merged |
| `requirements/**` | MIGRATE P5 | 5 | 2 | 3 | **MIGRATED partial** — #758 merged (clearance, _copper); `_geometry`, `validators/__init__`, `__init__` remain (shared geometry helpers / re-exports) |
| `explainability/**` | MIGRATE P5 | 8 | 7 | 1 | **MIGRATED** — #758 merged; `__init__` re-export |
| `temper-workflow/**` | MIGRATE P5 | 9 | 1 | 8 | **MIGRATED partial** — #754 merged (route_and_measure shim); metrics recorded as R3 glue |
| `placer/*.py` | MIGRATE P4 | 4 | 0 | 4 | **UNMIGRATED + UNOWNED — FLAG** (`deterministic.py`, `template.py`, `adjustment.py`, `__init__.py`, 708 LOC) |
| `constraints/**` | MIGRATE P4 | 5 | 3 | 2 | **MIGRATED** — #715 merged; `__init__`+`_payload` remain (data containers) |
| `extraction/**` | MIGRATE P4 | 1 | 1 | 0 | **MIGRATED** — #766 merged |
| `runner.py` | MIGRATE P5 | 1 | 0 | 1 | **UNMIGRATED + UNOWNED — FLAG** (242 LOC) |
| `strategy_registry.py` | MIGRATE P5 | 1 | 0 | 1 | **UNMIGRATED + UNOWNED — FLAG** (85 LOC) |

`placer/cp_sat/**` is JUSTIFIED-KEEP (Phase-1 verdict), not MIGRATE; `fields/**`
is JUSTIFIED-KEEP (ledger entry with blocker); package-root
`__init__/__main__/_version/protocol.py`, `visualization/**`, `scripts/**`,
`benchmarks/**`, and the test suite are JUSTIFIED-KEEP per the Phase-6 verdicts.

---

## 2. Owned elsewhere (open PR or branch at the provenance commit)

| Surface | Owner | State |
|---|---|---|
| `pipeline/**` | PR **#731** (dag_expr slice) | OPEN, DO NOT MERGE — gate set incomplete |
| `regression/**` | PR **#793** (verdict split) | OPEN, in review; carve-out **pending** — the ledger does not yet carry the 6-module JUSTIFIED-KEEP carve-out or the MIGRATE-exclude list. When it merges, the ledger's `regression/**` entry must gain the carve-out exactly as drafted in the PR (the ledger diff is already reviewed, just not landed) |
| `router_v6/**` | router_v6 workstream: #741 (survey), #751 (test Phase A), spikes #743/#744/#746/#747/#748, #755 (retire) | OPEN |
| `heuristics/**` | branch `feat/wave4-phase5-heuristics-rust` | wip, no PR yet |
| `io/**` write-engine candidate-4 | branches `feat/wave4-phase3-write-engine-rust`, `-p2` | **owned by branch only — no PR has ever been opened.** The work exists (write shims over `temper_io_types`), last commit 2026-08-04, both 100+ commits behind main. Flagged §3 |

Surfaces that were owned at dispatch but **merged during this audit**, moving
them from OWNED to MIGRATED/partial: `pcl/**` (#721), `core/**` (#724),
`metrics/**` (#697), `io/**` DSN (#694), `_constraint_types/**` (#719, as a
docs verdict), `topological/**` (#714), `analysis/**` (#737),
`geometry/**` (#695), plus #692/#755/#741/#795.

---

## 3. Blocked list and the loudly-flagged UNMIGRATED + UNOWNED surfaces

The task brief's expectation was "should be none". The audit found **three
wholly-unowned MIGRATE surfaces and two unowned partial remainders** that are
not recorded anywhere:

### 3.1 Truly UNMIGRATED + UNOWNED MIGRATE surfaces (1,035 LOC)

| Surface | Files | LOC | Ledger |
|---|---|---|---|
| `placer/*.py` | `deterministic.py`, `template.py`, `adjustment.py`, `__init__.py` | 708 | MIGRATE phase 4 |
| `runner.py` | — | 242 | MIGRATE phase 5 |
| `strategy_registry.py` | — | 85 | MIGRATE phase 5 |

No open PR, no branch, no issue, no R3 record mentions any of these. `template.py`
is in the guarded-file list of `check_no_raw_rotation_trig.py` (real rotation
geometry); `runner.py` and `strategy_registry.py` are the Phase-5 orchestration
seam the plan explicitly routes to Phase 5 ("PipelineRunner, adapters,
strategy_registry"). **Needs a decision**: either an owner pulls them into the
remaining Phase-4/5 work, or they get a recorded R3 blocker. They cannot stay
MIGRATE with nothing behind the pattern.

### 3.2 Unowned partial remainders inside partially-migrated surfaces (≈25,400 LOC)

- **`core/**`** — 23 plain files / 3,577 LOC after #724 (bus_cohort, decision,
  graph, hypergraph, net_graph, netclass_rules_gen, power_topology,
  specification, stackup, topology, loop_ownership, loop_extractor, + 12 more).
- **`validation/**`** — 21 plain files / 7,076 LOC after #717+#761. Includes
  `drc_types.py` (581) and `drc_result.py` (779), which the ledger note calls
  "Phase 2 contracts [that] land earlier" — they have not landed, and the plan's
  own record (line 144) left them "to be decided at their pull". That pull has
  never happened.
- **`deterministic/**`** — 25 leaf-stage files / 5,467 LOC with no R3 record and
  no owner (see §1 table).
- **`pcl/**`** — 15 plain files / 4,031 LOC after #721, including the always-
  migrate-pinned `constraints.py`.
- **`metrics/**`** — 4 plain files / 645 LOC after #697.
- **`io/**`** — write-engine candidate-4 on branches with no PR (2,603 LOC:
  `kicad_exporter`, `kicad_writer`, `_write_*`, `placement_exporter`), plus
  net_class_manager (RETIRE candidate), real_board, boundary_registry,
  snapshot, via_dedup, zone_manager (1,974 LOC).

### 3.3 Blocked items

- **`topological/**`** — the brief's "blocked on a parity defect" is **stale**:
  #714 merged 2026-08-06 with the defect resolved (BLAS `ddot` binding, 32-seed
  evidence in the PR). Not blocked.
- **`regression/**` (#793)** — merge-blocked in review; carve-out pending.
- **`_constraint_types/**`** — blocked on a **verdict decision**, not a defect:
  #719 merged a measured keep-verdict but left the ledger as MIGRATE. A product
  authority needs to reconcile the two (see §4).

---

## 4. Ledger corrections recorded (comments, no verdict flips)

Three corrections were added to `docs/wave4-verdicts.yaml` as dated comments
(2026-08-06). No verdict changed.

1. **`_constraint_types/**`** — comment noting #719 merged (2026-08-06) with a
   measured verdict that the surface is not a pyo3-pyclass candidate and should
   be JUSTIFIED-KEEP, deliberately without touching the ledger. The MIGRATE
   entry stands only because the decision was not recorded; the merged record
   now contradicts it. Decision owed.
2. **`physics/**`** — the note "scipy spsolve inside this tree is a separate
   JUSTIFIED-KEEP (KTD9) recorded below" has **no corresponding ledger entry**.
   The KTD9 keep is real (`loop_area.py`, `thermal_fdm.py`) and recorded in the
   plan/VERIFICATION.md, but the phrase "recorded below" names an entry that
   does not exist in this file. Comment added so the note is not read as
   pointing at a phantom carve-out.
3. **`scripts/*.py`** — its `exclude:` list references `scripts/internal_route.py`
   and `scripts/placement_quality_report.py`, **both deleted by #708 on
   2026-08-04**. #692 re-added the carve-outs after the deletion landed, so the
   exclude entries are dead (they exempt nothing; the gate's dead-exclude check
   is glob-shape-based and does not notice). The in-file comment already says the
   carve-outs "were removed"; the entry contradicts it. Comment added; the two
   exclude lines are candidates for removal on the repo's own §9.1 precedent
   (an entry scoped to a deleted file "exempts nothing, and reads as a live gap
   that is already closed").

---

## 5. Final LOC picture

`check_verdict_coverage.py` at the provenance commit:

| verdict | files | LOC | share |
|---|---:|---:|---:|
| MIGRATE | 457 | 103,476 | 23.2% |
| RETIRE | 0 | 0 | 0.0% |
| JUSTIFIED-KEEP | 1,115 | 342,124 | 76.8% |
| UNDECIDED | 0 | 0 | 0.0% |

R7 completion: **100.0%** — the gate exits 0 and every Python file under the
roots matches exactly one entry. That number measures verdict *coverage*, not
migration *completion*: it is correct that the ledger is well-formed and total,
and it is also true (this document's point) that **26,408 LOC** of
MIGRATE-pattern code is not yet shims and not yet owned (1,035 LOC wholly
unowned standalone surfaces + 25,373 LOC of unowned partial remainders).

Within the MIGRATE bucket: **135 files / 33,920 LOC** are crate shims
(migrated); **318 files / 68,871 LOC** are plain Python. Of the plain remainder,
the wholly-unowned standalone surfaces are §3.1 (1,035 LOC) plus the §3.2
remainders. The remaining MIGRATE plain files are covered by R3-style records,
JUSTIFIED-KEEP carve-outs, or open owners.

---

## 6. Residual notes

- **#575 ratchet debt.** The DRC shorting/total ratchets in
  `test_regression_drc.py` (committed-board 90→133, router-output 125→145/199,
  totals 1283→1405/1436→1524) remain open; the K2 re-solve is the attributed
  cause and the four stale constants need a coordinated board-workstream
  re-baseline (issue #517 context). It is independent of the regression
  migration verdict but touches `regression/drc_ratchet.py`, whose kernel moves
  in #793.
- **Topological parity defect.** Resolved and merged with #714. Recorded here so
  the "blocked on a parity defect" shorthand from the dispatch brief is not
  carried forward.
- **R24 register.** `power_pcb_dataset/physics_soundness_register.yaml` holds 4
  entries and `scripts/physics_soundness_register_gate.py` exits 0 — the R24
  discipline is an inventory, not a policy, and no physics-gated surface is
  unregistered.
- **The `_constraint_types` decision is the one open verdict conflict.**
  Everything else in this audit is a status finding; that one is a decision
  owed to product authority.

---

## 7. Method and provenance

- Worktree: `docs/wave4-owned-surface-closeout`, rebased onto `origin/main`
  (provenance commit `8893ab5ca`) at write time; all git reads qualified with
  `origin/<ref>`.
- Surfaces enumerated from `docs/wave4-verdicts.yaml`; per-file crate-shim
  detection by import-scan over the shipped pyo3 module names (§1).
- Ownership verified by `gh pr list` / `gh pr view` and `git branch -r`; a
  surface counts as OWNED only if an open PR or live branch references it.
- The verdict gate (`check_verdict_coverage.py`) exits 0 after the corrections.
- No `git stash` used; no files outside `docs/wave4-verdicts.yaml` and this
  evidence doc were modified.
