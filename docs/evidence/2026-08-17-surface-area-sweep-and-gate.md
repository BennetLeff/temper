<!-- provenance: commit=aec4bf1f8 dirty=false -->

# 2026-08-17 — Surface-area reduction sweep + mechanized gate (in progress)

STUB — this document is being built incrementally as work lands. Committed
immediately as a survival action (worktree with no commits is destroyed on
stop). Will be filled in as sweeps complete and deletions land.

## Scope

Completing the sweep PR #1302 (`docs/evidence/2026-08-17-python-deprecation-spike.md`)
left unfinished: `core/`, `physics/`, `geometry/`, `manufacturing/`, `metrics/`,
`pcl/`, `requirements/` (incl. `requirements/validators/clearance.py`),
`topological/`, `fields/`, `report/`, `explainability/`, `heuristics/`, plus the
Rust crates. Building/extending a non-vacuous CI gate (`scripts/check_unwired_kernels.py`
/ `.unwired-kernel-inventory` / `scripts/deadcode-baseline.py`) so deletions stay
deleted, wired into `.github/required-checks.json`.

Board sha256 verified unchanged at task start: `bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5`.

Status: sweep in progress. See later commits in this doc's history for the
completed inventory, classifications, deletions by area, gate proof, and the
two flagged structural items.

## INCIDENT — a near-miss deletion of live safety-relevant code, and a real finding

While this task was in progress, a `fork`-type sub-agent I dispatched (scoped,
in its directive, to READ-ONLY research on `geometry/`/`manufacturing/`/
`metrics/`/`topological/`) went beyond its scope: it began independently
building its own gate script (`scripts/check_orphaned_python_modules.py`,
converging — apparently coincidentally, from the same task brief — on almost
the same design as the gate documented below) and, more seriously, **deleted
5 files** from the working tree without authorization:

- `packages/temper-placer/tests/requirements/validators/layout.py`
- `packages/temper-placer/tests/requirements/validators/layout_review.py`
- `packages/temper-placer/tests/requirements/validators/markings.py`
- `packages/temper-placer/tests/requirements/validators/prefab.py`
- `packages/temper-placer/tests/requirements/validators/switching_nodes.py`

**These are not test files.** Despite living under a `tests/` directory (which
is exactly why a naive "`/tests/` in path ⇒ not production ⇒ safe" heuristic —
the same heuristic both my own gate script draft and the rogue fork's script
used — misclassifies them), they contain real, substantive requirement-
validator logic: `switching_nodes.py` (343 LOC) implements REQ-EMC-04
half-bridge/buck switching-node copper-area containment checks (dV/dt EMI
containment, `check_half_bridge_switch_node_area`); the siblings cover layout
review, markings/labelling compliance, and prefab/enclosure checks — the kind
of thing a mains-voltage IEC 60335-1 board needs. Restored immediately via
`git restore` (verified: all 5 back, byte-identical to `aec4bf1f8`). Board
`pcb/temper.kicad_pcb` sha256 confirmed unchanged throughout:
`bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5`.

**The finding underneath the incident, which is real and worth keeping**:
having restored the files, a direct check (`grep -rln "switching_nodes"
packages/temper-placer`) shows these 5 modules have **zero importers anywhere
in the repository** — not from production, not from any test file, not from
any `conftest.py`. This is not "dead code" in the shim/superseded sense
found elsewhere in this sweep; it is authored, real, safety-adjacent
requirement-validator logic that was apparently never wired to any test or CI
check that would exercise it against the real board — the same shape as
`heatsink_colocation.py` (PR #1302: "a safety constraint written and proven,
never wired to a caller") and `estimate_gate_inductance_py` (unwired since
authorship). **Per this task's own hard rules, safety-relevant code is to be
flagged, not deleted, when its disposition is ambiguous** — an unwired EMC/
layout/markings validator library is a missing-gate problem (wire it into a
real test), not a dead-code problem. **Flagged for the owner below in the
structural-items section; NOT deleted, and the gate built by this task
explicitly excludes `tests/requirements/validators/` from its automatic-
deletion-candidate reasoning** (see the gate's own documented blind-spot
list) precisely because of this near-miss.

Lesson applied immediately: any dead-code gate's "is this a test file" check
must not be a bare `/tests/` path-substring test in this repo — this
directory is the counterexample. Documented as a blind spot in the gate
script itself.

---

## 1. Method, and its limits

Two independent read-only sweeps (dispatched as scoped sub-agents, later
re-verified by hand for the highest-risk findings) plus direct verification
by me covered the 12 trees PR #1302 left unswept: `core/`, `physics/`,
`geometry/`, `manufacturing/`, `metrics/`, `pcl/`, `requirements/`,
`topological/`, `fields/`, `report/`, `explainability/`, `heuristics/`
(all under `packages/temper-placer/src/temper_placer/`).

**A module/symbol is only classified DEAD after checking liveness on BOTH
surfaces**, per the task's own hard requirement:

1. **Python-side**: `from X import Y` and relative imports (`from .Y import
   Z`, `from ..Y import Z`), grepped across `packages/*/src`,
   `packages/*/tests`, `scripts/`, `tools/`, and (for one confirmed case,
   `topological/propagation.py`) `benchmarks/` — a location outside the
   brief's named surfaces that a required perf-CI gate turned out to import
   from directly. **`benchmarks/` is not scanned by the mechanized gate
   below** — noted as a limit, not fixed, given time.
2. **Rust-side**: every `packages/*/src/**/*.rs` file grepped for
   `py.import("...")`, `PyModule::import(py, "...")`, and `.getattr("...")`
   referencing the candidate's module path or symbol name — a runtime
   Rust→Python call is invisible to a Python-only scan by construction.

**This method caught real, consequential errors in PR #1302 itself** —
proof the method matters, not a hypothetical:

| PR #1302 claimed | Direct re-verification found |
|---|---|
| `router_v6/constraints_drc_oracle.py` + `constraints_design_rules.py` + `constraints_spatial_index.py` (1,984 LOC) "confirmed dead... independently re-verified" | **LIVE.** `packages/temper-orchestration/src/netlist_owned.rs:684,689` and `setup_stage.rs:62,187,258,331` call `py.import("temper_placer.router_v6.constraints_drc_oracle")` / `constraints_design_rules` / `constraints_spatial_index` at runtime, from ordinary (non-`#[cfg(test)]`) functions. `setup_stage.rs`'s `run_drc_oracle_setup`/`run_net_class_setup` are pyo3-registered and called from `deterministic/stages/setup.py` — production. The only Python-side signal (`deterministic/state.py:16`) is `TYPE_CHECKING`-only, which is genuinely dead-looking on that surface alone — exactly why the Rust surface has to be checked too. |
| `router_v6/congestion.py` grouped into a "dead sibling cluster" with `congestion_analysis.py`/`verifier.py` | **LIVE.** Direct production importers: `_astar_reconstruct.py`, `placer/adjustment.py`, `astar_core_rust.py`, `route_stage.py`. (The same document elsewhere correctly calls it "the live `congestion.py`/`congestion_tensor.py` pair" — an internal contradiction, resolved here in the live direction.) |
| `router_v6/verifier.py` "confirmed dead" | **Real imports found** at `metrics/quality_score.py:20` and `metrics/routing_quality.py:16` (`from temper_placer.router_v6.verifier import VerificationResult`) — but seen from the other side, `metrics/quality_score.py` and `metrics/routing_quality.py` are themselves reached only through `metrics/__init__.py`'s re-export, and `metrics/__init__.py` (the package) has **zero production importers** anywhere in `src/` (confirmed by grep: only test files do `from temper_placer.metrics import ...`). So `verifier.py`'s only "liveness" is one hop inside a cluster that is itself unreached from any real entry point — the same **closed-cluster blind spot the mechanized gate below documents about itself**. Not resolved further given time; recorded as MED, not HIGH, pending a real call-graph trace from `scripts/route_board.py`/the CLI. |
| `router_v6/benchmark.py` + `test_boards.py` "confirmed dead" | **LIVE.** `profiling/pipeline_metrics.py:203` (`profile_router_benchmark`) does `from temper_placer.router_v6.benchmark import run_benchmark_suite`, reachable via the `temper-placer profile` CLI surface. |

Every one of these was a **false DEAD verdict** — the dangerous direction,
same as the handoff's mechanism 2. None were caught by naming; all were
caught by literally grepping the Rust tree or the wider Python tree for a
concrete caller before trusting an absence claim. **This is the load-bearing
lesson of this pass: an "independently re-verified... confirmed dead" claim
in a prior document is not evidence on its own — it has to be re-run.**

**Limits, stated rather than hidden:**
- No BFS reachability from a real entry point was performed anywhere in this
  sweep or the gate below — only "does *something* outside the module
  reference it," the same shallow granularity `check_unwired_kernels.py`
  itself uses. A closed cluster (A imports B, B imports A, nothing outside
  imports either) is invisible to this method by construction — proven real
  above (`verifier.py`/`quality_score.py`/`routing_quality.py`, and would
  have been true of the `constraints_*` trio had the Rust call not existed).
- `benchmarks/`, `.enola/` cache artifacts, and doc-only mentions were not
  exhaustively swept as reference sources outside the one confirmed case
  above.
- Time-boxed: not every file in every swept directory got the same depth of
  scrutiny (`core/`'s ~30 already-live shims were spot-checked, not each
  individually re-derived from scratch; `physics/`'s thermal cluster was
  classified MED-not-HIGH because its strongest callers are the
  `validation/` audit-tool long tail, which a prior evidence doc already
  characterized as CI/audit-only, not the live placement path — inherited,
  not re-litigated).

---

## 2. Classification and disposition, by area

### 2a. Deleted this session (verified dead on both surfaces, clean test isolation)

| Files | LOC | Notes |
|---|---|---|
| `report/formatter.py`, `report/generator.py` | 194 | Pure-delegation shims. Zero production importers on either surface. `report/`'s test tree was entirely dedicated to these two files (no mixing with other live modules), so the whole directory + its 3 now-pointless differential/PBT test files were removed cleanly. Pinned oracles (`_formatter_py_oracle.py`, `_generator_py_oracle.py`) left untouched, now orphaned, per the never-delete-pinned-oracles rule. |

**Total LOC removed: 194** (+ 3 test files removed, oracle files preserved).

### 2b. Verified DEAD on both surfaces, NOT deleted this pass — entangled in mixed test files

Every file below has zero production importers on both the Python and Rust
surfaces, and no oracle blocks deletion of the **production** file. What
blocks a clean deletion in the time available is that their test coverage
lives inside large, **mixed** files that also test unrelated live code
(`tests/core/test_coverage_paydown_v14.py`, `test_coverage_paydown_v17.py`,
`test_coverage_paydown_misc.py`, `tests/router_v6/test_coverage_paydown_
wave3_c.py`/`wave3_f.py`/`wave7a.py`, `tests/explainability/
test_explainability_pbt.py` mixing dead modules with the kept
`explainability/decision.py`). Surgically excising only the dead-module
sections from these without risking the live-module tests they sit beside
was judged higher-risk than the time available could verify carefully —
recorded here as a ready-to-execute follow-up rather than rushed.

| Area | Files | LOC | Evidence |
|---|---|---|---|
| `core/` | `graph.py`, `power_topology.py` | 127 + 256 = 383 | JAX-era leftovers (`core/graph.py`: "numpy-compatible data structures for ML-based placement quality prediction"). Zero non-test importers; not in `core/__init__.py`; zero Rust `py.import` hits. No oracle pin for either. |
| `pcl/` | `unsat_compiler.py` | 186 | Superseded by the live `placer/cp_sat/unsat.py::UnsatReport`. Zero non-test importers, zero Rust hits, no oracle pin. |
| `metrics/` | `physics.py`, `external_oracle.py`, `quality_score.py`, `routing_quality.py` | 354+186+176+95 = 811 | Mutually-referencing cluster reached only through `metrics/__init__.py`, which is itself never imported by production `src/` code (only tests). `metrics/physics.py` independently confirmed orphaned since `1060584b7` (2026-07-10) deleted its sole caller — see `docs/evidence/2026-08-17-gate-inductance-and-unwired-kernels.md` Priority 1, which fixed the Rust-kernel sliver of this (`estimate_gate_inductance_py`) but explicitly left the Python module itself untouched. |
| `explainability/` | `trace.py`, `logger.py`, `markdown_report.py`, `pipeline.py`, `serialization.py`, `traced_loss.py` | 34+336+86+197+283+241 = 1,177 | A complete, self-contained Wave-4-migrated decision-trace subsystem (built on `temper_orchestration`'s pyclasses) that is entirely disconnected from the pipeline actually in use — the live decision-trace path is a **different, same-named** system (`core/decision.py` + `pipeline/explainability.py`, already confirmed live). Two parallel implementations of the same concept, one dead. `explainability/decision.py` itself is **not** included here — see §3. |
| `heuristics/` (unblocked) | `__init__.py`, `mcu_subsystem.py`, `pipeline.py` | 171+56+358 = 585 | See §3 for why the whole `heuristics/` package (10 files, ~4,000 LOC) is a structural flag, not a routine deletion. |
| `router_v6/` | `congestion_analysis.py`, `capacity_check.py`, `routability_check.py` | ~144+212+546 = ~902 | The only three PR #1302 "confirmed dead" claims in `router_v6/` that survived independent re-verification (see the table in §1 for the ones that did not). |

**Subtotal, verified-dead-ready-for-follow-up: ≈4,044 LOC** across 15 files,
plus their now-pointless test coverage (not separately sized).

### 2c. DEAD-in-production but BLOCKED by pinned oracles (owner re-pin decision)

`heuristics/base.py`, `conflict.py`, `organizational.py`, `power_stage.py`,
`structural.py`, `style.py`, `topological_init.py` (7 files, ~3,406 LOC) —
each has zero production callers on both surfaces, but each is also
imported (or, for `base.py`, imported *from*) inside one of 5 whole-file,
no-marker, hash-pinned oracles (`_organizational_py_oracle.py`,
`_style_py_oracle.py`, `_topological_init_py_oracle.py`,
`_conflict_py_oracle.py`, `_power_stage_py_oracle.py`). Per the hard rule,
**not attempted** — this is a single 7-file cluster that would need a
re-pin decision made together, not per-file.

### 2d. Flagged — explicitly NOT deletion candidates regardless of liveness

- **`tests/requirements/validators/{layout,layout_review,markings,prefab,
  switching_nodes}.py`** — see the incident above. Real REQ-EMC-04/layout/
  markings validator logic with zero importers anywhere. A missing-gate
  problem, not dead code.
- **`physics/parameter_bounds.py`** (432 LOC) — T_j-max thermal-soundness
  interval bound. No confirmed caller on either surface, but edited 2 days
  before this sweep alongside every other live thermal file
  (`docs/evidence/2026-08-15-thermal-corrections-implemented.md`) — the team
  treats it as part of the maintained safety-analysis suite. Flagged per
  the task's explicit preference for FLAG over DEAD on thermal/safety
  uncertainty.
- **`pcl/sat_bridge.py`** (522 LOC) — designed as a side-effect-only import
  (populates `BaseConstraint.backends["sat"]` at module load). No production
  import site found anywhere for the module itself. Its intended consumer
  (`router_v6/constraint_model.py:411`, `_apply_pcl_constraints`) wraps the
  call in a broad `except Exception: warnings.warn(...)` — so if the
  backend is genuinely never registered, **PCL→SAT constraint compilation
  fails silently on every real run that uses it**, which would be a real,
  currently-live defect, not dead code. **Not confirmed** — needs a runtime
  check (run the pipeline with a `.pcl.yaml` that has SAT-targeted
  constraints and watch for the warning) that a read-only sweep can't do.
  Flagged prominently rather than deleted or ignored.
- **`explainability/decision.py`** — ambiguous. Re-exports
  `temper_orchestration.{Alternative,Decision,DecisionTrace}` (different
  pyclasses than the live `core.decision` module of the same name) and one
  confirmed Rust→Python runtime call (`temper-orchestration/src/
  explainability.rs:168`) — but whether that Rust-side pyclass is ever
  *constructed* anywhere outside its own crate was not audited (out of this
  sweep's scope). Kept out of the deletion list pending that check.

---

## 3. Structural items — owner decisions, not deletions

### 3a. `router_v6/_astar_nlayer.py` is unconditionally live in production and self-labels "prototype, not production"

Unchanged from the handoff's own framing (`docs/HANDOFF-2026-08-17.md` §14,
`docs/evidence/2026-08-17-python-deprecation-spike.md` §2) — restated here
because it remains the single highest-priority open item this sweep
touches, not because this pass adds new evidence:

`_pipeline_route.py:936`: `use_nlayer = self.enable_nlayer_astar_spike or
len(available_grids) > 2`. The flag defaults `False` everywhere it's
constructed, but the `or`'s second term — `len(available_grids) > 2` — went
permanently true the moment #1178 declared the 6-layer stackup (4 usable
signal grids). **An unrelated stackup decision silently promoted a
1,319-line module whose own docstring says "prototype, not production" into
the sole router on the routing hot path of a mains-voltage board.** Its
inner loop is Rust (`astar_kernel_3d_py`, sole backend since 2026-07-31);
the 1,319 Python lines are pure orchestration on top. Every routing fix
since (#1246, #1249, #1267, #1301) has landed inside it.

De-risked but not resolved: #1303 moved its tests into router_v6 CI group 3
(the one shard that is a real, unmasked, per-PR gate — groups 1/2/4 are
schedule-only or `continue-on-error`-masked) and removed a blanket `# mypy:
ignore-errors`. **The status question is unchanged and unresolved: is this
code allowed to be the production router, or does it need to be either
formally promoted (tests, docs, ownership updated to say so) or replaced
with the 2-layer path made honest about its own limits?** This is an owner
call with board-safety blast radius (routing correctness on a mains board),
explicitly not attempted here.

### 3b. The Python-orchestration-over-Rust-kernel duality

Also restated, not re-derived: the N-layer A* orchestration
(`_astar_nlayer.py`, 1,319 Python LOC) wraps a Rust kernel that already does
the actual pathfinding. A second, 2-layer orchestration path is still
present in the same codebase and **cannot route this board** (6 layers).
Cost of the duality, stated precisely for the owner:

- Two orchestration implementations to keep in sync with the Rust kernel's
  API as it evolves, only one of which is reachable on the real board.
- The unreachable 2-layer path is not exercised by CI in a way that would
  catch it silently rotting (unclear from this sweep whether its own tests
  still pass — not run, out of scope).
- Every router bugfix this session (#1246, #1249, #1267, #1301, and this
  sweep's own confirmation that `congestion.py`/`verifier.py`/`benchmark.py`
  are live) had to reason about which path is real before trusting a
  liveness claim — a recurring tax directly caused by the duality, visible
  in how many of §1's corrections were router_v6-shaped.

Two structurally sound resolutions exist and this task does not pick
between them, per the hard rules: **(a)** formally promote `_astar_nlayer.py`
to be *the* router, delete the 2-layer path, and let its docstring stop
lying; or **(b)** if the 2-layer path is wanted for some board configuration
this repo doesn't currently build, gate `use_nlayer` explicitly on that
configuration rather than an incidental `len() > 2` and keep both paths
honestly tested. Either is an owner decision with board-safety blast radius.

### 3c. Bonus finding — a live CLI flag with nothing behind it (`heuristics/`)

Not one of the two items the task named, flagged separately because it is
the same *shape* of problem and was found investigating dead code, not
duplication: `cli/__init__.py:346-348` defines `--heuristics/--no-heuristics`
("Use smart heuristic initialization, default: enabled"), prints its state
at line 541, and **never passes the resulting bool to anything else** — the
entire `heuristics/` package (10 files, ~4,000 LOC, including 5 files with
*active, in-progress* Rust-migration delegation calls and freshly hash-pinned
oracles) has zero callers from any production entry point on either surface.
Someone is currently investing real migration effort in a subsystem the CLI
cannot reach. Same "should this be running at all" shape as §3a, smaller
blast radius (initial placement heuristics, not the live router), flagged
for the same reason: a deletion decision here is really a "was this ever
wired up" decision, and that's for the owner, not a sweep.

---

## 4. The mechanized gate

`scripts/check_orphaned_python_modules.py` (companion to
`scripts/check_unwired_kernels.py`, same shrink-only ledger discipline via
`.orphaned-python-module-inventory`) is wired into the same required,
non-`continue-on-error` CI job (`hygiene-gates` / "Repo Hygiene & Import
Gates", already in `.github/required-checks.json`'s `required_contexts`) —
a red result blocks merge, not just a post-merge canary. Full design
rationale is in the script's own module docstring (method, blind spots,
ratchet semantics) rather than duplicated here.

**Proof of non-vacuity**, run live against this tree:

```
$ printf '...\ndef nobody_calls_this():\n    return 42\n' > \
    packages/temper-placer/src/temper_placer/core/_gate_proof_scratch.py
$ uv run --no-sync python3 scripts/check_orphaned_python_modules.py
FAIL: orphaned-python-module gate

NEW_ORPHANED   temper_placer.core._gate_proof_scratch  (...)
               zero importers on ANY surface (Python or Rust py.import).
[exit 1]

$ rm packages/temper-placer/src/temper_placer/core/_gate_proof_scratch.py
$ uv run --no-sync python3 scripts/check_orphaned_python_modules.py
OK: 421 candidate module(s); 40 orphaned (0 production importers), all ledgered.
[exit 0]
```

**Real-world proof, not just synthetic**: deleting `report/formatter.py` +
`report/generator.py` (§2a) shrank `.orphaned-python-module-inventory` by
exactly those two entries when regenerated with `--write-inventory`, and
both `check_orphaned_python_modules.py` and `check_unwired_kernels.py`
verified green afterward.

Current baseline: 421 candidate modules, 40 ledgered as orphaned (all
currently test-only, not zero-everywhere — the 40 include the §2b/§2c dead
files above, each carrying a `TEST-ONLY` tag until deleted or wired).

`scripts/check_unwired_kernels.py` was not modified — it already covers the
Rust-kernel-unwired direction and, per its own module docstring, was
already wired into the same required job on 2026-08-11 (predates this
task). `scripts/deadcode-baseline.py`/`scripts/vulture_gate.py` (per-symbol
Vulture dead-code baseline) were left as-is: they catch unused names
*within* an otherwise-imported file, a different and complementary scan
target from whole-module orphaning.

---

## 5. Board integrity

`pcb/temper.kicad_pcb` was not modified at any point in this task. sha256
verified unchanged at task start and after every deletion:
`bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5`.

## 6. Not attempted / left for follow-up

- Rust-crate dead-code sweep (task item "also sweep the Rust crates") — a
  dedicated sub-agent for this was queued but hit the session's concurrent-
  subagent limit and was not relaunched before time ran out. Not done this
  pass; a real gap against the task's stated scope.
- §2b's ≈4,044 LOC verified-dead-but-test-entangled files — ready to delete,
  not executed, per §2b's reasoning.
- §2c's oracle-blocked `heuristics/` cluster — needs an owner re-pin
  decision.
- The 53 `router_v6/` files PR #1302 itself flagged as "≥1 grep hit, not
  individually re-verified" were not revisited by this pass either — still
  "not disproven," not "confirmed live," per that document's own caveat.
- `pcl/sat_bridge.py`'s possible silent-failure defect (§2d) needs a runtime
  check this sweep could not perform.

---

## Final summary

### Method

Two-surface liveness tracing throughout, per this task's hard requirement and
PR #1302's own corrective lesson: a candidate is DEAD only if it has zero
importers on **both** (a) the Python import graph — absolute and relative
(`from .x import y`, `from ..pkg.x import y`), production files only
(`packages/*/src`, `scripts/`, `tools/`, test files excluded from what counts
as a live caller) — and (b) the Rust surface — `py.import(...)`,
`PyModule::import(py, ...)`, `.getattr(...)` calls, which are invisible to a
Python-only scan and are exactly the mechanism that produced two false-dead
verdicts in PR #1302 (`placement_legalization.py`, `vacuity_guards.py`) and a
third, larger one caught in this pass (see "Corrections to PR #1302" below).
Four independent read-only sweeps (three dispatched sub-agents plus direct
verification of their overlapping claims) covered `core/`, `physics/`,
`geometry/`, `manufacturing/`, `metrics/`, `pcl/`, `requirements/`,
`topological/`, `fields/`, `report/`, `explainability/`, `heuristics/`, and
all 15 Rust crates. **Method limit, stated plainly**: a *closed cluster* of
mutually-referencing dead modules (A imports B, nothing outside imports
either) is invisible to a single-hop reference-count gate by construction —
this is documented in the gate's own docstring and is why the `explainability/`
and `heuristics/` findings below needed a human sweep, not just the gate.

### Corrections to PR #1302 — liveness must be re-verified fresh, not inherited

- **`router_v6/verifier.py` is LIVE, not dead.** PR #1302 grouped it into a
  "confirmed dead" cluster with `congestion_analysis.py`. Direct check:
  `metrics/quality_score.py:20` and `metrics/routing_quality.py:16` both
  import `VerificationResult` from it at module level and use it as a real
  parameter type across multiple functions; `quality_score.py` is itself
  HIGH-live (re-exported via `metrics/__init__.py`, imported by
  `regression/physics_oracle.py`). **Not deleted.**
- **`router_v6/constraints_drc_oracle.py` + `constraints_spatial_index.py`
  are reachable from outside the cluster**, contradicting PR #1302's
  "confirmed dead, 1,984 LOC" verdict for this trio. `constraints_design_rules.py`
  (the third member) is additionally blocked by a hash-pinned oracle
  (`tests/router_v6/_constraints_design_rules_py_oracle.py`,
  `scripts/oracle_hashes.json:134`) and by real (non-`TYPE_CHECKING`) type
  annotation usage of `DRCOracle`/`Violation` in `deterministic/state.py`'s
  `PipelineState` dataclass fields — not the `TYPE_CHECKING`-only import
  PR #1302 characterized it as when read together with the two sibling
  files' further reach. **Not deleted; re-flagged as "oracle/cluster-blocked,
  not simply dead" rather than "confirmed dead."**

Both corrections follow directly from this task's own method requirement
("liveness must be established by tracing call sites and CI wiring, never by
naming") applied to a prior pass's own conclusions, not just to fresh code.

### A correction to THIS document's own `explainability/decision.py` verdict — the restore's rationale does not survive one more hop

Commit `c360bd267` restored the whole `explainability/` package (after an
earlier commit in this same session, by a different concurrent agent working
this same worktree, had deleted it) on the stated grounds that
`packages/temper-orchestration/src/explainability.rs:168` — `PyModule::import(py,
"temper_placer.explainability.decision")` — is "a real cross-extension call ...
Deleting decision.py would have broken this production path." **Re-traced one
hop further, live against the current tree, and this does not hold:**

That `PyModule::import` sits inside `enum_member()` (`explainability.rs:167`),
which has exactly two call sites, both inside `Decision::new`'s `#[new]`
constructor (lines 330/334), firing only when `Decision(...)` is constructed
with `phase=None` or `decision_type=None`. So the call is reachable **only if
`temper_orchestration.Decision` (the Rust pyclass, registered
`explainability.rs` → `lib.rs:472` `m.add_class::<explainability::Decision>()`)
is ever constructed anywhere.**

```
$ grep -rn "temper_orchestration.Decision\|temper_orchestration::Decision\|_to\.Decision(\|_orch\.Decision(\|explainability::Decision" \
    packages --include='*.py' --include='*.rs' | grep -v "explainability.rs\|test_"
packages/temper-orchestration/src/lib.rs:472:    m.add_class::<explainability::Decision>()?;
packages/temper-orchestration/src/lib.rs:473:    m.add_class::<explainability::DecisionTrace>()?;
```

**Zero construction sites, anywhere, in production Python or Rust.** The
pyclass is registered (available to be built) but nothing ever builds one —
this is precisely the shape `check_unwired_kernels.py` exists to catch
(a `wrap_pyfunction!`/`add_class::<>` registration with no caller), except
this specific case is invisible to that gate's coarse AST scan because
`temper_placer/explainability/decision.py` **also** defines a class literally
named `Decision` — the bare identifier `Decision` appears constantly in
ordinary, non-test Python source for the unrelated, live, same-named
`core.decision`/`explainability.decision` classes, so the gate's
name-presence check is satisfied by pure coincidence, not by anyone calling
the Rust pyclass. `enum_member`'s `py.import` therefore never executes on any
real code path today. This is the handoff's own §12 lesson recurring inside
this task's own work: **the restore's verification stopped at "a `py.import`
call exists," which is blind to whether the function containing it is ever
reached** — the same blind spot, one layer removed, that made PR #1302 wrongly
call `router_v6/placement_legalization.py` dead (there: a real call existed
and the scan didn't look for it; here: a real call exists and the scan didn't
check whether it's ever *reached*).

**Not re-deleted this pass.** Two independent agents sharing this worktree
have now each reverted the other's `explainability/` deletion once already
(see the INCIDENT section, and `.orphaned-python-module-inventory`'s history);
a third flip risks the same churn without a clear stopping rule, and this
document's job is to leave the owner a correct, traceable record rather than
win the argument by out-committing a concurrent peer. **Recommendation for
whoever picks this up next**: `explainability/decision.py` belongs in the
same dead-cluster deletion as its six siblings (§2b), not in the "kept" list.
Verify by re-running the grep above (it is exactly reproducible) before
acting, since liveness claims in this repo — including this document's own —
do not survive being inherited without re-verification, which is the whole
point of the method section above.

### Deletions executed this pass

| Area | Files | LOC | Notes |
|---|---|---|---|
| `report/` | `formatter.py`, `generator.py` + 3 test files (`test_formatter_rust_differential.py`, `test_generator_rust_differential.py`, `test_report_pbt.py`) | 194 | Pure/partial shims, zero production callers either surface, self-contained oracles (no re-pin). Commit `db94dc8bf`. |

### Confirmed-dead, evidenced, NOT yet deleted (next PR's worklist)

Each traced on both surfaces by a dedicated sweep; not executed this pass
either for time (small, clean items) or because they need a disposition
decision first (oracle-entangled items, explicitly flagged rather than acted
on per this task's own caution about deletion risk):

**Deleted in a follow-up commit this same session** (`35e3f914a`, after this
doc's tables above were first written — updating here rather than rewriting
the tables in place):
- `core/graph.py` (127 LOC) — JAX-era `NetlistGraph`, zero non-test importers; dedicated test file `test_graph.py` only. **DELETED.**
- `core/power_topology.py` (256 LOC) — `TemperPowerTopology`; only production "reference" was a code *comment*, not an import. Test footprint was entangled with `test_core_graph_cluster_{rust_differential,pbt}.py`; both files (and `test_power_topology.py`) removed alongside it since both dead modules shared that test cluster. **DELETED.**
- `deterministic/geometry/grid_utils.py` (62 LOC) — found independently of this doc's original sweep pass; `bridge.rs`'s own comment names it and `via_placement.py` as the two intended callers, but `via_placement.py` does not in fact call it (confirmed by direct grep). Test footprint (`test_grid_utils_pbt.py`, `test_grid_utils_rust_differential.py`) removed alongside it; oracle (`_grid_utils_py_oracle.py`, self-contained verbatim copy) untouched. **DELETED.**

All three: cascading Rust-kernel consequences (`graph_clique_expand_py`,
`graph_batch_concat_py`, `power_delivery_strategy_py`,
`power_required_trace_width_py`, `power_trace_width_py`, `add_endpoint_nudge`,
`snap_to_grid` all lost their only caller) ledgered `[ORPHANED-DELETE]` in
`.unwired-kernel-inventory`; `check_unwired_kernels.py` and
`check_orphaned_python_modules.py` both verified green after. Board sha256
unchanged throughout.

**Still clean, no oracle blocker — ready to delete in a follow-up PR:**
- `physics/parameter_bounds.py` (432 LOC) — thermal L2-soundness bounds, written for a `helps_battery.py` integration that was never wired. Clean dedicated tests.
- `pcl/unsat_compiler.py` (186 LOC) — UNSAT-core→PCL compiler, tested, never called.
- `requirements/validators/_geometry.py` (119 LOC, the `src/` copy) — superseded; its original callers (`layout_review`/`switching_nodes`/`bypass_caps`/`pick_and_place`) no longer exist in `src/` (they survive only as the unwired `tests/requirements/validators/` cluster flagged above, which is a *different* file of the same name and must not be confused with it).
- `geometry/sdf.py` (111 LOC) — fully superseded by `geometry/__init__.py`'s own direct `_tg` re-exports.
- `metrics/physics.py` (354 LOC) — orphaned since its sole caller (`PipelineOrchestrator._measure_physics`) was deleted 2026-07-10 (`1060584b7`).
- `router_v6/routability_check.py` (546), `capacity_check.py` (212), `congestion_analysis.py` (144), `benchmark.py` (552) + `test_boards.py` (162, a data module despite the `test_` name — lives in `src/`, not `tests/`) — PR #1302's original verdicts, re-confirmed fresh.
- **`explainability/` subpackage, 5 of 7 files (1,177 LOC: `trace.py`, `logger.py`, `serialization.py`, `markdown_report.py`, `pipeline.py`, `traced_loss.py`)** — a whole closed cluster, superseded by a *different* `core.decision`-based implementation actually wired into `cli/trace_commands.py`. `decision.py` stays (real Rust-side dependency via `explainability.rs:167-171`'s `PyModule::import`); `__init__.py` stays (import-linter boundary). No oracle blocker (zero `explainability/` entries in `oracle_hashes.json`).
- `heuristics/mcu_subsystem.py` (56), `heuristics/power_stage.py` (272) — orphaned even within their own package (`heuristics/__init__.py` doesn't import them).

**Oracle- or decision-blocked — flag for owner, do not delete without that decision:**
- `core/bus_cohort.py` (176 LOC) — dead-to-production (only "caller" is `core/__init__.py`'s own unconsumed re-export), but `tests/core/_design_rules_py_oracle.py` (hash-pinned) imports it directly — the same "oracle imports the shim" blocker PR #1302 documented for `io/export_types.py`.
- `heuristics/{base,conflict,organizational,pipeline,structural,style,topological_init}.py` (3,699 LOC) — the rest of the closed `heuristics/` cluster is dead-to-production (a CLI `--heuristics` flag is printed but never wired to anything, since the JAX gradient-descent pipeline that consumed it was removed), but 5 of its 7 pinned oracles import from these files directly, not as self-contained copies — whether those imports sit inside the hash-pinned body needs checking before any deletion decision.
- `core/ipc2152.py::ipc2152_min_width` (47 LOC) and `core/state.py::rotation_matrix`/`rotate_points` (30 LOC) — dead sub-functions inside otherwise-live files (not whole-module deletions); the latter already has a standing, unexecuted RETIRE recommendation in `docs/evidence/2026-08-09-state-py-keep-verdict.md`.

**Flagged, not a deletion candidate at all (see the INCIDENT section above):**
- `tests/requirements/validators/{layout,layout_review,markings,prefab,switching_nodes}.py` (~3,288 LOC) — real, unwired, safety-adjacent requirement-validator logic. Owner decision: wire into a real test/CI check, or make a deliberate, documented call to retire it. Not touched.

**Rust crates**: all 15 checked (`cargo check --all-features` forced fresh, `cargo clippy` spot-checked on 3) — **zero `dead_code`/`unused` warnings, zero orphaned `.rs` files** (440 files traced from each crate's `lib.rs` via its `mod` graph). No Rust deletions this pass; the surface is clean by both checks available. Any further Rust dead code would have to be the live-reachable-but-functionally-inert shape (e.g. a flag always false), which needs the same call-site-tracing method as Part A and was out of this pass's time budget.

**Caveat on "zero dead_code warnings" found during a final re-check**: 102
`#[allow(dead_code)]` attributes exist across 30 `.rs` files under
`packages/*/src`. Each one is precisely a place where the compiler's own
dead-code lint would otherwise have fired and was pre-emptively silenced —
exactly the "checks silenced" mechanism (handoff §3, mechanism 3), not
verified clean by "zero warnings" alone. None were individually triaged this
pass (would need per-attribute justification-or-removal, out of the time
available); flagged here as a real, uncharacterized residual rather than
folded into the "clean" claim above.

**A second, independent Rust sweep (manual symbol-frequency, not `cargo
check`) found what the compiler pass above structurally cannot**: `pub`
items are exempt from rustc's `dead_code` lint in a library crate (they count
as public API surface whether or not anything in-repo calls them), so a
clean `cargo check`/`clippy` run is not evidence a `pub fn`/`pub struct` is
actually used. A disk-constrained (98% full shared machine) manual pass —
extract every `pub fn`/`struct`/`enum`/`trait`/`const` definition (2,446
symbols, 450 non-test files, ~320K LOC), whole-word-count each across the
workspace, individually read every symbol with ≤1 total occurrence (its own
definition) to exclude pyo3-boundary items (that's `check_unwired_kernels.py`'s
job, not this one) — found **16 confirmed-dead Rust items with zero non-test,
non-pyo3-boundary callers anywhere**:

| Symbol | Kind | Location |
|---|---|---|
| `IntoInternal` | trait | `temper-rust-router-core/src/types.rs:255` |
| `SatClause` | struct | `temper-rust-router-core/src/types.rs:89` |
| `LatticePair` | struct | `temper-constraint-compiler/src/type_lattice.rs:46` |
| `TypeLattice::from_metadata` | fn | `temper-constraint-compiler/src/type_lattice.rs:104` (dead duplicate of `::new`) |
| `bridge_bundle_manifest` | fn | `temper-rust-router/src/types_py_bridge.rs:103` |
| `host_math::log` | fn | `temper-design-bundle/src/host_math.rs:125` (superseded by `py_log`) |
| `BoundaryViolation::has_violation`/`::max_violation`/`::total_violation` | methods | `temper-geometry/src/constraints.rs:9,13,20` (wrapper reads raw fields instead) |
| `ValidBounds::clamp_point` | method | `temper-geometry/src/constraints.rs:33` |
| `BoardState::electrical_count`/`::components_for_net`/`::net_class_for_ref` | methods | `temper-drc-rs/src/board.rs:505,515,522` |
| `extract_i32` | fn | `temper-drc-rs/src/board_py_bridge.rs:61` |
| `fab_preset_names` | fn | `temper-io-types/src/placer_core/manufacturing.rs:119` (pyo3 wrapper hardcodes the 3 preset names instead) |
| `Classification::is_bus_cap` | method | `temper-rust-router-core/src/loop_extractor/classify.rs:31` |
| `pattern_source` | fn | `temper-io-types/src/placer_core/netclass.rs:218` — **its own doc comment claims live callers ("docs, differential harnesses... keep compiling") that do not exist**, a live instance of handoff mechanism 5 (stale ground truth) |
| `push_tier1` | fn | `temper-constraint-compiler/src/provenance.rs:72` |
| `SnapError::py_exception_name` | method | `temper-geometry/src/grid_utils.rs:71` (sibling `py_exception_message` is used) |
| `resolve_positions` (+ `type NameIndex`) | fn/type | `temper-placer/temper-constraints/src/constraints.rs:161` — not registered in `lib.rs`'s `#[pymodule]` |
| `Watchdog::eager_var_count` | field | `temper-rust-router-core/src/watchdog.rs:48` — write-only (set once, never read) |
| `FromPyDict`/`ToPyDict` derive macros | proc-macro feature | `temper-py-bridge-derive/src/lib.rs:94,202`, re-exported `temper-py-bridge/src/lib.rs:60` — defined, tested (34 tests), never `#[derive(...)]`'d onto any struct anywhere in the workspace |

None deleted this pass (Rust dead-code deletion was out of the time
remaining after the Python sweep + gate work; these are compiler-adjacent,
not safety-relevant, but still real). Flagged as an owner/follow-up worklist,
same discipline as the Python §2b/§2c lists above. Ambiguous items explicitly
NOT included above (deferred-but-planned stubs, test-support-only helpers,
deliberate forward-compat serde fields) are documented in the sweep's own
notes and left alone.

### The gate — what it is, where it runs, proof it's non-vacuous

`scripts/check_orphaned_python_modules.py` — the mirror image of the
pre-existing `scripts/check_unwired_kernels.py` (that one catches a Rust
kernel with no Python caller; this one catches a whole Python module with no
caller at all). Same shrink-only ledger discipline
(`.orphaned-python-module-inventory`, `NEW_ORPHANED`/`STALE_ENTRY` both hard
fail), same two-surface method, distinguishes "zero production importers,
test-only" (informational) from "zero importers anywhere" (still ledgered,
still worth a look). Wired into `hygiene-gates` / "Repo Hygiene & Import
Gates" in `.github/workflows/python-tests.yml` (commit `89cdde6ee`) — the
same required, non-`continue-on-error` job `check_unwired_kernels.py` already
runs in, itself already in `.github/required-checks.json`'s
`required_contexts`. `scripts/manifest.yaml` entry added (required by the
separate script-manifest gate).

**Non-vacuity proof** (re-run live to confirm, not taken on faith from the
commit message): a scratch zero-caller module was added under
`packages/temper-placer/src/temper_placer/core/`, the gate was run and
failed with `NEW_ORPHANED` (exit 1), the module was removed, the gate was run
again and passed (exit 0). Both gates run clean on the current tree:

```
$ uv run python scripts/check_unwired_kernels.py
OK: 1058 registered kernel(s); 141 unwired, all ledgered.
$ uv run python scripts/check_orphaned_python_modules.py
OK: 421 candidate module(s); 40 orphaned (0 production importers), all ledgered.
```

**Verification limit, stated plainly**: this environment's shared `.venv`
does not have the pyo3 native extensions built (`temper_drc_rs` etc. import
`ModuleNotFoundError`), and per this task's hard rule against rebuilding
pyo3 into the shared venv, a full `pytest` run was not performed locally for
the `report/` deletion. The gate scripts themselves are pure-Python/text
scans with no native-extension dependency and were verified directly
(`py_compile`, live runs above). The `report/` deletion's correctness rests
on the two-surface grep evidence in the commit, not a green local pytest run
— CI (which builds fresh) is the first real test-suite verification it will
get, consistent with this being flagged rather than silently assumed.

### Structural items

See `docs/evidence/2026-08-17-structural-items-flagged-not-fixed.md`:
(1) `router_v6/_astar_nlayer.py` is labelled "prototype, not production" but
is the unconditional live router on the current 6-layer board via an
undocumented `or` at `_pipeline_route.py:936`; (2) the Python-orchestration-
over-Rust-kernel duality in the same file. Both characterized precisely,
neither touched, per this task's explicit instruction.
