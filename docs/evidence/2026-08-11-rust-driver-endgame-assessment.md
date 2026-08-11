<!-- provenance: commit=3bd1413e7e05a6f5e1bc52768faf3614aab29c52 dirty=false -->

# The Rust-driver endgame: what's actually irreducible (U6 assessment)

**Scope.** Investigation only, per
[`docs/plans/2026-08-11-003-feat-migration-pipeline-wire-and-retire-plan.md`](../plans/2026-08-11-003-feat-migration-pipeline-wire-and-retire-plan.md)
§U6. No code under `packages/**`, `scripts/**`, or any oracle was touched. The
question: if the top-level driver of this repo became Rust instead of Python,
how much of the 172,119 LOC of production Python (665 files,
`scripts/check_migration_narrowing.py::production_py_files`, re-measured today
at **172,295 LOC / 665 files** — the figure is current, not stale) actually
disappears, how much is real rewrite work, and how much is genuinely stuck?

**Headline, stated up front per the brief's instruction to lead with this:**
the irreducible CPython core is **small and it is not primarily a feature-coverage
problem anymore.** The CP-SAT/OR-Tools boundary — the one hard dependency named
in the plan — is **2,800–4,400 LOC**, not the 172k the "CPython-bound" framing
implies, and this repo's own prior spikes (2026-08-01 through 2026-08-07,
cited throughout §1) have already done the expensive verification work: a
pure-Rust CP solver (Pumpkin) has been run through a 108-run differential
against the real production board with **zero soundness or correctness
failures**, and an OR-Tools-via-FFI path has been shown to be a **bytes-in,
bytes-out protobuf boundary with no Python-specific coupling at all**. Neither
result has been folded back into `docs/wave4-verdicts.yaml`, which still
carries the older "acceptance is unassertable" framing and one stale 757-LOC
ghost entry for a file deleted five days ago. Beyond CP-SAT, the two other
candidate blockers this brief asked about — scipy and the Plotly visualizer —
are **already fully resolved** (scipy: migrated off entirely as of commit
`3ba16bfbd`; the visualizer: deleted today, `88928f4ca`). What remains outside
CP-SAT is not architecturally blocked, it is unported: real rewrite work,
sized in §5.

---

## 1. The irreducible core: CP-SAT / OR-Tools

### 1.1 How deep is the ortools API surface, really?

`packages/temper-placer/src/temper_placer/placer/cp_sat/` is **10,115 LOC**
across 37 files today (down from 11,257 LOC at the 2026-08-04 R7 pass —
see §1.4 on why). The R7 axis marks the *whole subtree* `JUSTIFIED-KEEP`
("every module ... calls the ortools API or exists to build/interpret a
`cp_model.CpModel`"), which reads as if the entire 10k LOC is solver-bound.
It is not, and the repo's own R1 (Python-removal) axis already says so,
file-by-file:

| Cluster | LOC (measured today) | Touches ortools directly? | R1 verdict in `wave4-verdicts.yaml` |
|---|---:|---|---|
| `_encoder_solve.py` | 717 | Yes — `ortools.CpSolver().Solve()` | BLOCKER-ORTOOLS |
| `model.py` | 518 | Yes — 59 raw `cp_model`/`model_ref` call sites (`NewIntVar`, `NewIntervalVar`, `AddElement`, `AddNoOverlap2D`, `AddMultiplicationEquality`, `AddAbsEquality`, `AddAssumption`, `OnlyEnforceIf`, `CpSolver`, …) | BLOCKER-ORTOOLS |
| `__init__.py` + `_encoder_core.py` + `encoder.py` | 584 (50+478+56) | Indirect — dispatches into `model.py`'s wrapper, no raw API calls of its own | BLOCKER-ORTOOLS |
| `handlers/keepout.py`, `handlers/separated.py` | 200 | Yes — call `model.model_ref` directly for reified constraints (`OnlyEnforceIf`, `AddBoolOr`) | BLOCKER-ORTOOLS |
| `handlers/adjacent.py`, `aligned.py`, `anchored.py`, `enclosing.py`, `loop_area.py`, `onside.py` | 406 | **No** — build every constraint through named `CpSatModel` methods and arithmetic on `IntVar`-like objects; zero `ortools` imports (verified: `handlers/_model_protocol.py` names this explicitly as a `Protocol` boundary) | BLOCKER-ORTOOLS (by inclusion in the handler cluster, not by API touch) |
| `unsat.py` + `unsat_surface.py` | 433 | Yes — `SufficientAssumptionsForInfeasibility` | BLOCKER-ORTOOLS |
| `fixed_copper.py` | 875 | Partially — 18 raw `model_ref` calls concentrated in a ~200-line reification tail; the majority of the file is rotated-pad/keepout geometry computation | **absent from the R1 axis entirely** (verified: no `fixed_copper` entry anywhere in `removal_surfaces:`) |
| `isolation_barrier.py` | 671 | Barely — exactly one real call, `model.model_ref.Add(cvars.rot_ref == rotation_index)`; the file's own docstring explains at length why it deliberately does *not* encode corridor position as an `IntVar` | **absent from the R1 axis entirely** |
| `gates.py`, `_loop_core.py`, `loop.py`, `_loop_gates.py`, `_loop_routing.py`, `_loop_types.py`, `_loop_utils.py`, `gate.py`, `delta_mapper.py`, `netclass_constraints.py` | **3,266 measured** (ledger cites 2,238 — stale; `gates.py` alone is now 1,169 LOC and has grown substantially since that figure was recorded) | **No** — loop orchestration, gate contracts, violation→delta dispatch; calls the encoder as a function boundary | PORT ("no ortools call in this cluster itself") |
| `_loop_stability.py` | 168 | **No** — round-history bookkeeping for the repair loop's stopping criteria | PORT (separate `paths:` entry) |
| `validator_audit.py`, `feedback.py` | 986 (509+477) | **No** — post-solve violation classification/reporting, dispatch tables | PORT |
| `audit.py`, `domain_clearance.py` | 1,015 (383+632) | **No** — `audit.py` is the R24 post-solve geometric auditor, explicitly noted elsewhere in the ledger as "Rust-backed via `temper-geometry`"; `domain_clearance.py` imports `temper_orchestration`/Rust-backed classifiers directly and emits plain `SeparatedConstraint` data objects, not ortools types | **absent from the R1 axis entirely** — the ledger's own prose admits this for `domain_clearance.py` ("not named in this cluster or anywhere else in the re-triage... left UNDECIDED by omission"); `audit.py` has the identical gap, unremarked |
| `handlers/_protocol.py`, `_registry.py`, `_shared.py`, `handlers/__init__.py` | 142 | Trivial type-alias/registry infra | UNDECIDED (ledger names this gap explicitly) |
| `handlers/_model_protocol.py` | 134 | Trivial (Protocol/type-alias definitions only; docstring quotes ortools types but imports none) | not scored either axis |

**The real boundary is a single choke point, not a diffuse dependency.**
`CpSatModel(` — the constructor for the ortools-backed wrapper — is
instantiated in exactly **one place in the entire package**:
`_encoder_solve.py:221`. Every orchestration file above (loop control, gates,
audits, feedback classification) calls `solve_placement(...)`, a plain
function returning a dataclass (`CpSolverSolution`: status, objective,
positions, rotations, sizes, wall time — no ortools types), and never touches
a `CpModel`/`IntVar` itself. This is already the shape of a clean FFI/subprocess
boundary — it did not need to be built, it already exists.

**Net: the genuinely ortools-bound code is 2,800–4,400 LOC**, not 10,115 and
certainly not 172k:
- **Floor (~2,850 LOC):** `_encoder_solve.py` (717) + `model.py` (518) +
  `__init__.py`/`_encoder_core.py`/`encoder.py` (584) + all 8 handler files
  (200 raw-API + 406 protocol-clean = 606) + `unsat.py`/`unsat_surface.py`
  (433) = **2,858**, reconciling within rounding against the ledger's own
  post-correction total (§1.4: 3,599 stated − 757 stale `clearance_repair.py`
  entry = 2,842).
- **Ceiling (~4,400 LOC):** floor + the two files with genuine (if partial)
  direct `model_ref` coupling that are missing from the R1 axis entirely —
  `fixed_copper.py` (875) and `isolation_barrier.py` (671) — counted in full
  even though most of each file's content is portable geometry with only a
  thin reification tail. `domain_clearance.py` and `audit.py` are **not**
  added to this ceiling despite the identical "missing from the ledger" gap:
  unlike the first two, neither has a verified direct ortools call — both are
  already Rust-backed data producers that happen to be un-triaged, not
  under-counted blockers. Their 1,015 LOC belongs in the PORT-eligible
  ("must move, not blocked") bucket, not here.

Six of the eight constraint handlers, and the entire loop/gate/audit/feedback
orchestration layer (≈5,840 LOC, once `_loop_stability.py`,
`validator_audit.py`/`feedback.py`, and the two ledger-omitted-but-portable
files above are counted), already don't touch ortools and are correctly
scored PORT (or should be, pending a ledger fix) — this is not a new finding
for most of it, it's what the repo's own R1 ledger already says once you read
past the R7 subtree-level KEEP; the `audit.py`/`domain_clearance.py` gap is
this document's own addition to that picture.

### 1.2 Existing spikes already answer "what are the real options" — do not re-derive

This repo ran four increasingly rigorous spikes on this exact question between
2026-08-01 and 2026-08-07, and the results are more conclusive than the brief's
framing assumes:

**Option A — OR-Tools via a thin Rust↔C++ FFI shim, keep the same solver.**
`docs/evidence/2026-08-06-ortools-ffi-spike.md`: the CP-SAT C++ entry points
(`operations_research::sat::Solve`/`SolveWithParameters`) take and return
**protobuf messages** (`CpModelProto`/`CpSolverResponse`) — "bytes in, bytes
out." The `.so`/`.dylib` already ships inside the `ortools` Python wheel and
already exports these symbols; the schema (`FileDescriptorSet`, 6,937 bytes,
29 messages) is extractable from the installed wheel with no OR-Tools source
checkout, and `prost_build` consumes it directly. Every API this codebase
actually uses — including `SufficientAssumptionsForInfeasibility`, the one
the spike flagged as the API most likely to be Python-side logic — is a
proto field, not host logic. **Verdict: feasible, and the encoder port this
implies gets the best differential in the whole migration program**, because
two implementations either emit byte-identical `CpModelProto`s or they don't.
Cost: OR-Tools' C++ headers/libs become a native build input (23 MB dylib +
absl dependencies), not a `uv` dependency — a packaging change to CI images,
not a modeling rewrite.

**Option B — a pure-Rust CP solver (Pumpkin), no OR-Tools at all.**
Independently more interesting, and separately verified twice
(`docs/evidence/2026-08-04-wave4-residual-verdicts.md` §1.1,
`docs/evidence/2026-08-07-pumpkin-engine-differential.md`). Pumpkin 0.5.0
covers **12 of the 13 constraint classes** this placer's encoder uses natively
(`equals`/`less_than_or_equals` for linear, `implied_by` for every
`OnlyEnforceIf`, `element` for rotation-driven size selection, `times` for
the area term, `absolute` for the displacement objective, `extract_core` for
UNSAT cores). The one gap, `AddNoOverlap2D`, is the spike's own §1.5 finding
that it's redundant for correctness here — the per-pair SEPARATED disjunction
already enforces pairwise clearance; `NoOverlap2D` is only a propagation
strength hint. A standalone Pumpkin engine was then built and run through the
same equivalence harness used to validate OR-Tools itself, on 108 real solves
across three corpora **including the real 33-component golden board at
production constraint count (543 constraints)**:
  - **Zero soundness disagreements, zero independent-verifier failures**,
    across all 108 runs. (An independent, from-scratch geometric checker —
    not either engine's own say-so — caught one real bug during this
    process: a `round()` vs. round-half-even parity mismatch in the Rust
    engine's `mm_to_units`, found and fixed before the differential passed.)
  - On the golden board, Pumpkin is **dramatically faster**: 14–35ms vs.
    OR-Tools' seed-dependent 2.5–30s+ (OR-Tools timed out on 12 of 18 runs at
    the harness's 30s budget; Pumpkin never timed out once).
  - On the one objective-bearing corpus, Pumpkin does **not** reliably prove
    optimal within the harness's own 5-second convenience budget — but a
    follow-up measurement (`docs/evidence/2026-08-07-cpsat-objective-frequency.md`)
    traced that 5s figure to an arbitrary test-harness literal with no
    connection to any real deadline, gate, or SLA in this repo, and found
    that the objective-bearing solve path (`minimize_displacement_to`) is
    reachable from **exactly one opt-in code path** (a manual clearance-repair
    routine, invoked 5 times across 482 commits touching this surface —
    every automatically-triggered production solve, including the CI-gating
    golden-board regression test and the full `PlaceRouteLoop`, is
    objective-free by static construction). That path's own production
    timeout default is 180,000ms, and Pumpkin's measured time-to-optimum
    (5–50s, 65s worst-case-reliable) fits inside it with 3–30× headroom. A
    real, separately-flagged risk — non-monotone timeout sensitivity (giving
    Pumpkin *more* time does not monotonically help a fixed seed) — argues
    for retry/seed diversity in the caller, which is already how the
    multi-round repair design behaves.

**These two spikes together substantially close the "acceptance is
unassertable" blocker the ledger still states.** The 2026-08-04 verdict named
four open acceptance criteria: (a) bit-identical output can't be asserted
across engines (true by construction, not resolvable, and the harness design
already accounts for it via independent verification instead); (b) search
quality unmeasured — **now measured**, 108 runs; (c) every pure-Rust candidate
is pre-1.0 — **still true**, Pumpkin 0.5.0 is not a 1.0 release; (d) "good
enough" has no gate expressing it — **now has a measured answer** (frequency
+ real timeout budget), though still not a machine-checked gate. Both
evidence documents explicitly recommend a `wave4-verdicts.yaml` update
reflecting this and explicitly note "not applied here, per scope" — **that
update was never applied.** `docs/wave4-verdicts.yaml`'s BLOCKER-ORTOOLS
blocker text (line 438) is word-for-word the 2026-08-04 framing; it does not
mention Pumpkin's 108-run result, the objective-frequency measurement, or the
180,000ms production budget. This is not this document's boundary to fix
(`docs/wave4-verdicts.yaml` is U2/U3 territory), but it means the ledger
currently understates how far this question has already been walked.

**Option C — reformulate as pure SAT, reusing `rustsat`+`rustsat-cadical`.**
The brief was right to flag this as unproven precedent, and it does not
transfer. `rustsat`/`rustsat-cadical` in `temper-rust-router-core` solve
propositional CNF (`solver.rs`: `CaDiCaL::default()`, clause-level API) for
bounded-model-checking and combinator verification — a different problem
class from CP-SAT's typed integer domains, interval scheduling
(`NoOverlap2D`), element selection, and multiplication constraints. Using it
for placement would mean bit-blasting every integer variable and hand-encoding
`NoOverlap2D`-equivalent disjunctions as clauses from scratch — a genuine
reformulation project with no in-tree precedent and unclear scaling on a
150+-component board, for no benefit over Option B (Pumpkin already offers a
native, typed CP modelling surface with measured correctness). **Not
recommended**; costed here only because the brief asked for it to be costed
rather than assumed.

**Option D — MILP via HiGHS (`good_lp`/`highs`, `rust-or` org).** Considered
because it's the one option with genuine `wasm32` support (`good_lp` +
`highs` compile to WASM; both Pumpkin and an OR-Tools FFI shim are native-only,
same as today). Not useful here: `rustsat-cadical`'s wasm32 exclusion via
`sat-gated` already establishes that CP-SAT-class solving is out of the wasm
tier by design regardless of which Rust option is picked (the brief's own
framing), so the one advantage MILP has doesn't apply, and it costs a bigger
reformulation than Option B for the same "no native CP-SAT global constraints"
problem SAT has (no-overlap becomes big-M disjunctions, not a native
primitive). **Not recommended**, same reasoning as Option C.

**Option E — keep the placer as a Python subprocess, drive everything else
from Rust.** Genuinely viable as an interim or permanent shape and cheaper
than any of A/B: the CLI (`temper_placer.cli:main`) or a thin new entry point
already accepts a board+constraints and returns a placed board; a Rust driver
calls it exactly the way it already calls `kicad-cli` and `ngspice` (§2.4).
This keeps ~10k LOC of Python alive indefinitely (the whole `cp_sat/`
subtree, not just the 2,800–4,400 LOC core, since nothing forces splitting
the orchestration layer out once it's behind a subprocess boundary anyway),
in exchange for zero solver-migration risk. Worth stating as the pragmatic
floor: **even under total inaction on CP-SAT, the driver can still become
Rust** — this is exactly the brief's point that Category 2 (subprocess-callable)
collapses the "CPython-bound" argument for everything *except* the in-process
solver call itself.

### 1.3 What Rust bindings to OR-Tools exist today, independent of this repo's spikes

Cross-checked against the current ecosystem (2026-08): `cp_sat` (KardinalAI,
docs.rs, 34★/15 forks/38 commits, v0.4.1's docs build currently failing) and
`cpsat-rs` (v0.1.2, 2026-04) both wrap OR-Tools' C++ library via FFI — neither
reimplements the solver. Both require a **system-installed OR-Tools C++
build** (`ORTOOLS_PREFIX`, default `/opt/ortools`), not a vendored/static
link and not a `cargo`-only dependency — the same native-build-dependency
shape the in-repo FFI spike (Option A) already priced, just pre-packaged with
moderate but real maturity risk (13 open issues on the more mature of the two).
Neither claims `wasm32` support, consistent with the C++ dependency. Using one
of these instead of a hand-rolled shim is a real option, but doesn't change
the packaging cost calculus in §1.2 Option A — you still need OR-Tools' C++
build available wherever this code compiles.

### 1.4 A concrete ledger drift, worth fixing separately

`docs/wave4-verdicts.yaml`'s BLOCKER-ORTOOLS entry for `clearance_repair.py`
(757 LOC, "`run_clearance_repair_solve` is a round-loop wrapper around
`solve_placement`... called repeatedly with overrides") describes a file and
function that **no longer exist**: `clearance_repair.py` was deleted 2026-08-09
(`9985bae48`, "retire dormant clearance_repair module" — zero production
importers, verified by AST sweep) and `run_clearance_repair_solve` has zero
remaining references anywhere in the tree (confirmed by direct grep). The
ledger's stated BLOCKER-ORTOOLS total (3,599 LOC, six entries) is therefore
757 LOC stale; the live total across the five surviving entries is 2,842 LOC,
matching §1.1's floor figure. `wave4-verdicts.yaml`'s last edit
(`88928f4ca`, today) postdates the deletion by two days, so this wasn't caught
by the same pass that removed the visualization entries. Not fixed here —
out of this document's boundary — but a one-line finding worth handing to
whichever unit owns the ledger next.

---

## 2. Beyond CP-SAT: what else did the brief ask to check, and what's actually there

### 2.1 scipy — already fully resolved, not merely "portable in principle"

Both prior-art documents (`docs/wave4-verdicts.yaml`'s BLOCKER-SCIPY note and
`docs/evidence/2026-08-11-python-deprecation-inventory.md` §4.3) describe
`router_v6/routability_check.py` and `router_v6/_astar_heuristics.py` as
still calling `scipy.ndimage.distance_transform_edt`/`label`, with "migration
itself is unstarted." That is now stale. Both call sites were migrated to
`temper_geometry.exact_edt_transform` / `connected_components_8_transform`
(commits `1efa1cb33`, `3ba16bfbd`) — `routability_check.py`'s own docstring
now states outright "this module is scipy-free as of that migration." A
repo-wide check confirms it: **zero production files under `packages/*/src`,
`scripts/`, or `tools/` import scipy at all** (`grep -rE
"^\s*(import scipy|from scipy)"` returns nothing outside test oracles, where
the pre-migration scipy call is deliberately retained as the R19 pinned
differential reference — exactly the FREEZE-eligible shape U4/U5 of the
parent plan target). scipy is fully closed as a blocker.

### 2.2 matplotlib/Plotly visualization — already resolved, today

`visualization/**` (11 files, 5,508 LOC) — previously JUSTIFIED-KEEP/REPLACE
on the grounds that Plotly's HTML/JSON output has no bit-identical bar to port
against and no rendering-regression gate exists to score a Rust
re-implementation — was deleted **today** (`88928f4ca`, "drop the deleted
visualization module from `.importlinter` + record the deprecation in the
verdicts ledger"): zero production consumers, its one external use (a
rotation-convention test oracle) re-pointed at `kicad_transform`/`pcbnew`
directly. `find packages/temper-placer/src/temper_placer/visualization` now
returns nothing. `pipeline/terminal_dashboard.py` + `visualization.py`
(rich/click-based, live via the `watch` CLI) are unrelated and unaffected.
Only remaining matplotlib usage in the whole tree: `packages/temper-placer/debug_plot.py`,
a single unmanifested dev script.

### 2.3 numpy — not irreducible, just unported

68 production files import numpy. None of it is architecturally blocked —
`ndarray` is a mature, complete Rust equivalent for everything numpy is used
for here (grid arithmetic, dtype-cast buffers feeding the `temper_geometry`
FFI boundary that `routability_check.py` already round-trips through via
`tobytes()`/`frombuffer`). This is real rewrite work (68 files), not a
blocker category.

### 2.4 Subprocess-bound external tools — Category 2, confirmed, not just asserted

Verified directly rather than assumed, per the brief's caution:
- `kicad-cli` (DRC, `make drc`) — subprocess, `--all-track-errors`, already
  known.
- `ngspice` (`validation/spice.py`, 905 LOC) — `subprocess`, batch mode
  (`-b`), text-parsing wrapper. JUSTIFIED-KEEP is recorded on record for
  "ngspice boundary, no marshalers to migrate" — correct in that ngspice
  itself can't move, but the 905 LOC of Python *around* the subprocess call
  (argument construction, output parsing, measurement extraction) is
  ordinary text-processing glue, callable from Rust exactly as it is from
  Python.
- `atopile`/`ato` (`make netlist`, `make schematics`) — an external tool,
  invoked via `uv tool run`, not part of this repo's Python at all; its
  presence in the Makefile is irrelevant to the production-Python LOC count
  either way.

All three confirm the brief's framing directly: nothing about these requires
CPython as the caller.

### 2.5 `_constraint_types/**` (1,033 LOC, pydantic) — looks like CP-SAT, is not

Flagged because AGENTS.md and the ledger both record this as R7
JUSTIFIED-KEEP with unusually strong language ("final authority, never
reimplemented in Rust"): `temper-design-bundle`'s `config_loader.rs` (already
Rust) calls back into Python's `PlacementConstraints.model_validate` for
validation. On its face this reads like a second CP-SAT — a Rust caller that
cannot get free of Python. It is not the same shape. **`config_loader.rs`
calls back into Python only because the current driver *is* Python** —
exactly the brief's Category 2/3 pattern, not a third-party-library blocker.
If the top-level driver were Rust, there is no architectural reason a
`serde`-based schema (with hand-written validators reproducing pydantic's
custom-validator semantics) couldn't be the authority instead; the R1 axis
already agrees (`_constraint_types/**` is scored **PORT**, not
BLOCKER-anything: "under full removal a pydantic schema also has to leave
Python one way or another"). The cost is real — 34 models, custom exception
types, and the `gen_config_reference` CI gate that reads `model_fields` all
need re-proving equivalent — but it is bounded, ordinary rewrite work, not an
open research question the way CP-SAT is.

### 2.6 Packaging: a different-shaped, smaller question

`packages/temper-placer/pyproject.toml` builds with **hatchling**, not
maturin, and ships two console-script entry points
(`temper-placer`/`temper` → `temper_placer.cli:main`) resolved by Python
packaging machinery that requires an importable Python package root — a
pyo3 extension is *imported by* that root under this build backend, it can't
replace it (`docs/evidence/2026-08-04-wave4-residual-verdicts.md` §2, already
verified there, not re-derived here). This affects roughly 521 LOC of
distribution-root files (`__init__.py`, `__main__.py`, `runner.py`,
`strategy_registry.py`, `protocol.py`) — small, and re-decidable purely as a
packaging choice (moving to a `clap`-based native binary with no Python
package root at all) rather than a migration question.

---

## 3. The top-level driver: what actually orchestrates this system today

| Entry point | What it drives | Language coupling | Rust-equivalent shape |
|---|---|---|---|
| `Makefile` `build: netlist footprints schematics route drc` | `netlist`/`schematics`: subprocess to external `ato` CLI + `scripts/write_build_stamp.py` (trivial). `footprints`: a no-op stub (shell `echo`). `route`: `scripts/route_board.py` → `temper_placer.router_v6.adapter.route_pcb` (real orchestration, largely Rust-delegating already — 51 of `router_v6`'s files call into a Rust crate). `drc`: subprocess `kicad-cli`. | All five targets are `make` recipes calling either a subprocess or a Python entry point; none require CPython as the driving process — a Rust `xtask`/CLI could issue the identical subprocess calls and call the same `route_pcb`-equivalent logic via FFI once ported. | A Rust CLI subcommand per target, unpacking `route_board.py`'s 591 LOC of subprocess/JSON-report glue directly. |
| Placement (deliberately **not** in `make build` — "a separate, human-gated CP-SAT solve," per the Makefile's own comment) | `temper-placer`/`temper` console scripts → `temper_placer.cli:main` (click, 2,137 LOC across `cli/`) → the `cp_sat/` encoder described in §1. | This is where §1's boundary actually lives. | A Rust CLI (`clap`) driving `solve_placement`-equivalent logic via whichever of §1.2's Options A/B/E is chosen; the CLI wrapper itself (`click`→`clap`) is already R1-scored REPLACE, not a blocker. |
| `temper-orchestration` (Rust, 29,165 LOC total across `src/`+`tests/`) | Already-Rust pipeline-stage engine (`PipelineRunner`, `DerivationStage`, `PreflightStage`), imported by 40+ production Python files (`deterministic/stages/*`, `pipeline/*`, `router_v6/*`). | **This is the clearest concrete evidence for the brief's "self-referential" claim.** `board_state.rs`'s `BoardState` struct holds its `board`/`netlist`/`config`/`violations`/`placements`/`routes`/… fields as `Option<pyo3::Py<PyAny>>` — under a comment reading literally `// ---- Marshalling-pending (Phase A): Py<PyAny> ----`. This is Rust code that already does the real work, shaped around holding a *pointer to a Python object* only because its caller is Python today. The crate's 51 `#[test]` functions across 11 integration-test files (`stages_runner.rs` et al.) all import `pyo3` for exactly one reason: they construct fake Python objects from Python builtins (`FakeBoard`, `FakeComp`, …) to drive `BoardState` through its GIL-shaped API, then read results back via `py.getattr`/`dict.get_item`. None of this is compute — `DerivationStage`/`PreflightStage` are pure Rust logic underneath. If the driver were Rust, `BoardState`'s fields would hold native Rust structs (the same shape `_constraint_types`/`config_loader.rs` would produce post-§2.5), the 51 tests would construct plain Rust values instead of embedding a fake Python interpreter, and pyo3 would disappear from this crate's dependency graph entirely — with **zero change to the actual pipeline logic**, because that logic never was Python-bound; it was always Rust reading through a Python-shaped window. | Already Rust. The only change needed is replacing the `Py<PyAny>` fields with native types once something upstream of them stops being Python. |

---

## 4. Sizing the endgame

Ranges, not false precision — the brief's own instruction, and warranted:
several of the inputs below (R1's own 302-of-663-file triage, the ledger
drift in §1.4) are already known-incomplete.

**Disappears outright (driver flips to Rust, no rewrite needed):**
- pyo3 surface area in already-Rust crates whose Python-shaped types exist
  only to serve a Python caller (`temper-orchestration`'s `Py<PyAny>`
  fields and their 51-test pyo3 harness — not production Python LOC, but
  real complexity that evaporates).
- The CLI wrapper layer once its callers move (`click`→`clap`, ~2,100 LOC in
  `temper_placer/cli/`), already R1-scored REPLACE.
- **Estimated: a few thousand LOC of glue/marshalling code, not a large
  share of the 172k.** This category was never as large as "Category 2/3
  collapses" made it sound, because most of what collapses is *coupling*
  (pyo3 dependency, GIL-shaped test fixtures), not raw line count.

**Must be rewritten (real work, not architecturally blocked):**
- **PORT bucket, R1 axis: 211 files / 45,804 LOC** (69% of the 302 files
  triaged so far under `temper_placer`+`temper_workflow`) — the single
  largest bucket, "mechanical orchestration/glue, no third-party blocker."
  This is the actual prize if the driver flips: none of it needs a research
  spike, all of it needs someone to write the Rust and prove equivalence.
- **REPLACE bucket: 28 files / 8,838 LOC** minus the 5,508 already deleted
  today (§2.2) — CLI (already counted above) + reporting/diagnostics
  (`benchmark.py`, `diagnostics.py`, `manufacturing_report.py`, ~2,177 LOC).
- **`router_v6/`: 30,617 LOC / 106 files**, of which roughly half already
  delegates to Rust per-call (the brief's cited 51-of-102 baseline, now 106
  files — the ratio hasn't been re-measured here but the shape is
  unchanged); the other half is exactly the kind of orchestration/adapter
  code (`_adapter_convert.py`, `adapter.py`, I/O writers) the R1 PORT bucket
  above already covers.
- numpy call sites (68 files) — bounded rewrite against `ndarray`, no
  blocker.
- `_constraint_types/**` (1,033 LOC) — bounded rewrite against `serde` +
  hand-written validators, no blocker, but real work re-proving pydantic's
  validation semantics.
- **scripts/ (61,624 LOC) mostly does NOT collapse, and this matters for
  scoping.** The 2026-08-04 residual-verdicts pass costed this directly:
  68 of the ~102 surviving scripts (29,919 LOC, ci-gates + shell-invoked)
  are JUSTIFIED-KEEP for reasons **orthogonal to the driver language** —
  deliberate code duplication as a fail-closed-independence discipline
  (documented in-code, not inferred), the requirement that gates run when
  the Rust workspace itself fails to compile, and a CI topology where 22 of
  26 workflows set up no Rust toolchain at all. Flipping the driver to Rust
  does not remove any of these constraints. The remaining ~11,554 LOC
  (utility/measurement scripts) is a genuine mix, roughly two-thirds
  verification instrumentation that must keep hosting a Python arm to A/B
  against (same reasoning as `benchmarks/**`, 449 LOC, also JUSTIFIED-KEEP)
  and one-third thin shells that would move with whatever they wrap.
- **Total real-rewrite estimate: on the order of 60,000–90,000 LOC** —
  the PORT bucket extrapolated across the ~360 files R1 hasn't triaged yet
  under the same roots, plus `router_v6`'s unmigrated half, plus numpy/
  constraint-types rewrites. This is a rough extrapolation, not a
  measurement — the honest range reflects that ~360 of 663 production files
  have never been scored on the removal axis at all (§7 of the 2026-08-04
  doc says so explicitly), and `scripts/`+`benchmarks/` were scored but
  mostly land KEEP for structural, non-language reasons above.

**Genuinely irreducible while the current architecture holds:**
- **CP-SAT/OR-Tools core: 2,800–4,400 LOC** (§1.1), *if* Option E (subprocess)
  is rejected in favor of A or B. If Option E is chosen instead, the
  irreducible-while-Python-runs figure is closer to the full 10,115 LOC
  `cp_sat/` subtree, but nothing forces that — Option E just removes the
  incentive to also migrate the orchestration layer around it, since it's
  already behind a clean subprocess-compatible function boundary either way.
- The ~68 ci-gate/shell-invoked scripts (29,919 LOC) for structural CI
  reasons, not language-coupling ones — these would very likely remain
  Python-based tooling indefinitely regardless of what drives the product
  build, unless the CI topology itself changes (a much larger, separate
  decision).
- `benchmarks/**` (449 LOC) and the instrumentation two-thirds of
  `scripts/`'s utility class (~7,700 LOC) for as long as any Python oracle
  is still being differentially tested against — this shrinks automatically
  as U4/U5's FREEZE mechanism retires oracles, it is not a permanent floor.

---

## 5. Is it worth it?

**Yes, with a specific, bounded scope — not the unconditional "move
everything" the Category-2/3 framing implies.**

The honest shape of this decision: the ~60,000–90,000 LOC PORT-class rewrite
(§4's middle tier) is exactly the kind of work this repo's migration pipeline
already knows how to do — differential test, A/B, PBT, the works — because it
is the same shape as the 456 files/107,958 LOC the R7 axis already scored
MIGRATE before this task even started. Flipping the driver to Rust doesn't
change *how* that work gets done, it just removes the "but the caller is
Python, so what's the point" objection for the last mile of orchestration
code. That argument is worth making and this document makes it: **most of
what currently reads as "CPython-bound" is bound to today's driver, not to
CPython**, and the plan's own framing (Q3) is basically right.

Where the plan's optimism should be tempered: the CP-SAT boundary is real
work even in the best case. Option B (Pumpkin) is the strongest path
available today — correctness is measured, not assumed, on the actual
production board — but it is a pre-1.0 dependency and the objective-search
performance gap, while inside the real production budget, is not zero risk.
Option A (OR-Tools FFI) is lower-risk on solve quality but adds a native C++
build dependency to every environment that builds this code, which is a real
operational cost this repo does not have today (the Python wheel bundles it
invisibly). Either one is a genuine, multi-week engineering project with its
own migration-pipeline discipline (proto-exact differential for A, the
existing 108-run equivalence harness extended to full production coverage
for B) — not a research question anymore, but not free either.

**Recommendation:** treat this as two separate, differently-paced tracks,
not one endgame:

1. **Drive the orchestration/glue layer from Rust now**, behind Option E
   (subprocess) for the placer specifically. This captures the large
   majority of the "collapse" the brief describes — `route_board.py`,
   `router_v6`'s adapters, the CLI, `temper-orchestration`'s `Py<PyAny>`
   fields — without waiting on a CP-SAT decision, and every one of those
   files already has, or can get, the standard migration-pipeline treatment
   this plan's U1–U5 are building tooling for.
2. **Treat CP-SAT as its own, later, explicitly-scoped project**, picking
   between Option A and Option B on engineering grounds (operational cost of
   a C++ build dependency vs. pre-1.0 solver risk) once the orchestration
   work above has landed and there's a real Rust driver to plug it into —
   not before. Update `docs/wave4-verdicts.yaml` first (§1.4) so the next
   person costing this doesn't re-run spikes this repo has already run.

**Where to stop, honestly:** the ~68 ci-gate scripts and the
instrumentation/oracle-hosting Python (§4's last bullet) are not worth
migrating under this goal at all — their JUSTIFIED-KEEP reasoning has nothing
to do with which language drives the product build, and forcing them to move
anyway would spend real effort undoing a deliberately-chosen fail-closed
design for no product benefit. The last 15–20% of the 172k (call it
25,000–35,000 LOC: ci-gates + benchmarks + the instrumentation share of
utility scripts) genuinely does cost more than it returns under this
specific goal ("more Rust, less Python" for the *driver*) — it returns real
value under a different goal ("no Python anywhere in the repo, ever"), which
this plan and its predecessors have both explicitly and correctly left open
rather than assumed.
