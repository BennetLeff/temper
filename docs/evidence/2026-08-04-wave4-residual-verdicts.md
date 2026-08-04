# Wave 4 R7: closing the UNDECIDED verdict backlog — five surfaces (2026-08-04)

<!-- provenance: commit=ebf9326ffa763c0051f87c2629fb690b1dfd9a58 dirty=false -->

**Scope:** read-only analysis plus decision recording. No code was migrated, no
files deleted, no Rust written. The deliverable is the verdict; where a verdict
is RETIRE, the deletion is a separate change.

**Result:** R7 completion **57.5% → 100.0%** of LOC under the ledger's roots.

| verdict | files | LOC | share |
|---|---|---|---|
| MIGRATE | 456 | 107,958 | 56.8% |
| RETIRE | 2 | 1,386 | 0.7% |
| JUSTIFIED-KEEP | 231 | 80,598 | 42.4% |
| UNDECIDED | 0 | 0 | 0.0% |

Reaching 100% was not the goal and is a reason for suspicion, not comfort. §7
records where the evidence is thinnest and which verdict should be revisited
first. The measured LOC total moves 189,912 → 189,942 because
`scripts/check_verdict_coverage.py` is itself under a ledger root and grew by 30
lines (§6).

---

## 1. Surface 1 — `placer/**` (11,973 LOC): the ortools CP-SAT boundary

The Phase 1 spike (`docs/evidence/2026-08-01-ortools-cpsat-spike.md`) had already
reached **KEEP** and is recorded in the plan. This pass did not redo the survey.
It verified the load-bearing claims against `origin/main` and corrected the
blocker, which was materially wrong.

### 1.1 The stated blocker was feature coverage. It should not have been.

The spike recorded the blocker as "no pure-Rust engine covers the element / 2D
no-overlap / product / assumption-core surface", and marked Pumpkin's reification
support **needs-verification**. Verified 2026-08-04 against the crate itself:

| Spike class | Pumpkin 0.4.0 | Source |
|---|---|---|
| C1/C2 linear | `equals`, `less_than_or_equals`, `plus`, `binary_*` | docs.rs fn index |
| C3 reified linear (`OnlyEnforceIf`) | **`Constraint::implied_by`** — "post the constraint `r -> constraint`" | `pumpkin-crates/core/src/constraints/mod.rs:22-27` |
| — full reification | `NegatableConstraint::reify` → `r <-> C` | same file, lines 57-81 |
| C4 `AddBoolOr` | `clause` | docs.rs fn index |
| C5 `AddElement` | `element` | docs.rs `fn.element.html` |
| C6 `AddNoOverlap2D` | **absent** (`disjunctive_strict` is 1D `NoOverlap`) | docs.rs |
| C7 `AddMultiplicationEquality` | `times` | docs.rs `fn.times.html` |
| C8 `AddAbsEquality` | `absolute` | docs.rs `fn.absolute.html` |
| C9/C12 assumptions + cores | `extract_core()` on `UnsatisfiableUnderAssumptions` | docs.rs |
| C11 objective | optimisation API | docs.rs |

**12 of 13 classes are covered natively.** The two the spike specifically assumed
absent — half-reification and assumption cores — are both present, and C3 is the
highest-load row in the whole enumeration (every `OnlyEnforceIf` in the repo).
The single gap, `AddNoOverlap2D`, is documented **in the spike's own §1.5** as
redundant for correctness: "the per-pair SEPARATED Chebyshev disjunction
(`C3+C4`) already enforces pairwise clearance", kept only as a propagation
strength hint. Removing it is a solve-quality change, not a semantics change.

Pumpkin 0.4.0 released 2026-06-23; ~8,896 downloads (crates.io API).
`implied_by` appears in 15 files across the Pumpkin repo (GitHub code search),
including the flatzinc compiler and the Python bindings, so it is load-bearing
API, not an experiment.

Not independently verified: C10 (`AddHint` / solution hints). The 12-of-13 count
does not depend on it.

### 1.2 The honest blocker

Not feature coverage. Acceptance is unassertable:

- **(a)** R1a's bit-identical bar cannot be asserted across solver engines by
  construction — different search, so identical output is at best empirical.
- **(b)** Search quality on this board class is unmeasured for every candidate.
- **(c)** Every pure-Rust candidate is pre-1.0.
- **(d)** What "good enough" means is a human judgment about candidate quality
  under a wall-clock budget, and **no gate in this repo expresses it.**

**(d) must fall first.** Without a gate expressing solution acceptance, (b) has
no pass mark to measure against, and the KEEP is re-decidable only in name. This
ordering is the actionable part of the correction.

### 1.3 Two defects in the solve contract the KEEP depends on

The spike's §4 asserts the frozen params hold "at both call sites
(`model.py:434-436`, `_encoder_solve.py:390-394`)". There are **three** solve
sites on `origin/main`, with three different postures:

| Site | `random_seed` | `num_search_workers` | Reproducible across machines? |
|---|---|---|---|
| `_encoder_solve.py:497-500` | `= seed` | `= 4` | yes |
| `model.py:434-436` | **never set** | `= 8` | defaults to 0 so stable in practice, but unpinned — and the spike records it as frozen, which is false |
| `unsat.py:275-277` | **never set** | **never set** | **no** |

`unsat.py::_check_assumptions_infeasible` leaves `num_search_workers` at the
CP-SAT default of 0 = auto-detect, so the worker count tracks the host's core
count. **The minimal unsat core is therefore not reproducible across machines** —
and this is the MUS-refinement path the spike itself identifies as the *portable*
half of the core surface. KEEP acceptance criterion 1 (version-locked solve
contract) is **not met today**. Fixing it is a code change, out of scope here.

**Version floor.** The spike names `pyproject.toml:28` (`ortools>=9.12`).
`packages/temper-placer/pyproject.toml` declares ortools **twice** — `>=9.12` at
line 28 and `>=9.10` at line 43 — and `uv.lock` carries both specifiers. The
effective floor is the looser 9.10. `uv.lock` pins 9.15.6755, so today's install
matches the measured version, but metadata permits floating past it. Both
declarations need tightening.

### 1.4 Verdict and split

The plan's own Phase 1 rationale draws the line: the ortools model/solve wiring
is gated; "the remaining placer compute beyond the ortools boundary" is Phase 4.

- `placer/cp_sat/**` (11,257 LOC) → **JUSTIFIED-KEEP**. Every module here calls
  the ortools API or exists to build/interpret a `cp_model.CpModel`. Note
  `cp_sat/gates.py` already delegates to `temper_design_bundle_python` (Phase 2,
  landed); the Python file remains as the delegation shim, this repo's standard
  post-migration shape.
- `placer/*.py` (716 LOC — deterministic, template, adjustment, `__init__`) →
  **MIGRATE, Phase 4**. None import ortools. `template.py` carries real rotation
  geometry (it is in `check_no_raw_rotation_trig.py`'s guarded-file list).

### 1.5 R4 "done for KEEP", status

| R4 requirement | Status |
|---|---|
| Named blocker | **Done, corrected** — §1.2, recorded in the plan's Phase 1 section |
| Version-locked solve contract | **Not met** — two unpinned solve sites (§1.3) and two loose version floors |
| R24 audit across the boundary | **Holds** — `cp_sat/audit.py` remains wired post-solve, Rust-backed via temper-geometry |
| KTD9-style measured parity | **Not met** — no corpus baseline recorded; blocked on the same param pinning |

The KEEP verdict is sound. Its acceptance criteria are only partly satisfied, and
saying so is the point of recording it.

---

## 2. Surface 2 — package root `*.py` (521 LOC)

Enumerated file-by-file rather than as one `*.py` entry: six files, three
verdicts. Enumeration also means a *new* package-root file matches no entry and
fails the check — correct behaviour under R7.

| File | LOC | Verdict | Reason |
|---|---|---|---|
| `protocol.py` | 141 | JUSTIFIED-KEEP | **Already decided** in the plan's Phase-2 residual pass (2026-08-03). Recorded against the file, not re-decided. |
| `runner.py` | 242 | MIGRATE Phase 5 | That same record routes it: "orchestration seam (PipelineRunner, adapters, strategy_registry) → Phase 5" |
| `strategy_registry.py` | 85 | MIGRATE Phase 5 | named in the same sentence |
| `__init__.py` | 39 | JUSTIFIED-KEEP | distribution root |
| `__main__.py` | 13 | JUSTIFIED-KEEP | distribution root |
| `_version.py` | 1 | JUSTIFIED-KEEP | distribution root |

The ledger's `owed:` asked "whether a pyo3-backed distribution keeps a Python
package root at all", and warned that assuming yes would violate D6. Verified,
not assumed: `packages/temper-placer/pyproject.toml` builds with **hatchling**
(`build-backend = "hatchling.build"`), not maturin, and declares two console
entry points (`temper-placer`, `temper` → `temper_placer.cli:main`). Both are
resolved by Python packaging machinery that requires an importable Python
package root. A pyo3 extension is imported *by* that root; under this build
backend it cannot replace it.

Re-decidable: if the distribution moves to maturin and ships `temper_placer` as
a native extension module. That is a packaging decision, and it would *delete*
these three files rather than port them.

---

## 3. Surface 3 — `visualization/**` (6,086 LOC) → JUSTIFIED-KEEP

The renderer emits an HTML document embedding Plotly figure JSON, consumed by a
browser and accepted by human visual judgment.

- **Acceptance is unassertable.** plotly.py's figure→JSON serialization (key
  order, float repr, bundled JS version) is an implementation detail of the
  Python library. A Rust re-implementation emits a byte-different document that
  R1a's bit-identical bar cannot adjudicate, and the repo has no image-diff or
  figure-schema regression gate that could score it instead.
- **Not on the product path.** plotly and websockets are already optional guarded
  imports — `report.py:46` (`PLOTLY_AVAILABLE = importlib.util.find_spec(...)`)
  and `server.py:38-46` (falls back to a mock server). The surface does not load
  on the default install path and carries no hot-path compute.
- **Its only gated content is already governed.** `board_renderer.py` and
  `model.py` are in `check_no_raw_rotation_trig.py`'s guarded-file list, which
  keeps them on the shared rotation convention. That gate's own notes describe
  them as rendering "a visual proxy of the real board" and the rotation handling
  as "currently a no-op" (discrete quadrant-only state; `PadView` has no
  production constructor).

Deliberately *not* claimed: "no mature Rust drop-in". A Rust Plotly crate exists;
that is not the obstacle, and writing it as one would be false.

Re-decidable if a rendering regression gate lands (making equivalence
assertable), or if product authority retargets the renderer to WASM/web — a
rewrite for a different runtime, decided as a product question, not a migration.

---

## 4. Surface 4 — `scripts/**` (61,624 LOC): a genuine mix

Measured composition (top-level joined against `scripts/manifest.yaml`
dispositions):

| class | files | LOC |
|---|---|---|
| ci-gate | 61 | 27,664 |
| utility | 34 | 11,381 |
| shell-invoked | 7 | 2,255 |
| measurement | 1 | 173 |
| `scripts/tests/**` | — | 19,359 |
| `scripts/_lib/**` | — | 792 |

### 4.1 RETIRE ×2 (1,386 LOC) — import-dead, verified

An AST sweep of every module-level (unguarded) `temper_placer.*` import across
all of `scripts/` and `benchmarks/` returned exactly two files:

- **`scripts/internal_route.py`** (811 LOC) — imports `jax.numpy` (jax is in no
  dependency set) plus eight names from `temper_placer.routing.*` and
  `temper_placer.io.trace_writer`. Neither package exists; `routing` was renamed
  `router_v6` without this script following. It cannot be imported, so it cannot
  have run since. `check_no_raw_rotation_trig.py`'s notes already spotted this in
  passing; `scripts/route_board.py`'s docstring says it supersedes it.
- **`scripts/placement_quality_report.py`** (575 LOC) — unguarded module-level
  imports of `temper_placer.losses.base` and `temper_placer.routing.analysis`.
  Both are JAX-era packages that no longer exist.

Distinguished from a false positive: `route_board.py` and
`check_no_raw_rotation_trig.py` mention `temper_placer.routing` only in
docstrings, and `batch_pipeline_validate.py`'s `temper_placer.losses` import sits
inside a `try:` block and degrades gracefully. None of those three is dead.

**This contradicts `scripts/manifest.yaml`, which records all 102 survivors as
`category: keep`.** Both are `disposition: shell-invoked`, which is why the
sunset clock missed them: `check_script_sunset.py` keys off `last_run` dates and
the invocation graph, not importability. A script with a caller in a shell
snippet looks live even when it raises `ImportError` on line 13. Closing that gap
is a separate change; it is a gate gap, not a verdict.

### 4.2 The rest → JUSTIFIED-KEEP, on a blocker that is the inverse of consolidation

D6 exists to stop "it's glue" being dressed up as a blocker. The blocker here is
the opposite claim: **these gates are correct *because* they are duplicated and
independent, so consolidating them into a shared crate would destroy the
property.** This is a recorded repo discipline, not an inference:

- `check_isolation_keepout.py:186-189` — "self-contained loader — deliberately
  NOT imported from `check_domain_partition.py`: this gate's correctness must not
  depend on a sibling gate's internal representation changing out from under it,
  same reasoning `check_copper_net_consistency.py` gives for its own copy".
- `check_footprint_drift.py:100-104` — "a DELIBERATE copy of the equivalent
  parser in `check_copper_net_consistency.py` (itself explained there as
  deliberately not importing `gen_pcb_skeleton.py`'s version)".
- `measure_cross_domain_creepage.py:29-31` — "copied rather than imported for the
  same fail-closed-independence reason".

Each cites `docs/METHODOLOGY.md` Sec 4/5 (failure taxonomy / five falsification
axes) and its fail-closed contract. Migrating 61 ci-gate scripts into a crate
would share exactly the parsers whose duplication is the protected property.

Two further blockers, both verified:

- **Bootstrap.** The gates must run when the Rust workspace does not compile.
  `check_rust_drc_presence.py` literally checks that Rust DRC is present; it
  cannot be a Rust binary. A compile error would otherwise silently disable the
  gate suite exactly when it is most needed.
- **CI cost, against the binding constraint.** Only 4 of 26 workflows set up a
  Rust toolchain (`regression`, `codeql`, `r9-evidence`, `python-tests`). The
  other 22 run gates on bare Python — `required-checks.yml:50` is literally
  `run: python3 scripts/check_required_checks.py`, with no setup step at all.
  Migrating would add a cargo build to every gate job on a CI that is
  capacity-bound rather than speed-bound.

`scripts/_lib/**` (792 LOC) is imported into the gates' own interpreter and
inherits their bootstrap constraint verbatim. `scripts/tests/**` (19,359 LOC) is
the pytest suite proving the gates work — the same reasoning already recorded for
`testing/` and `fixtures/`, plus the requirement that it run and fail closed when
the Rust build is broken.

### 4.3 The weaker half, stated plainly

The above is strong for the 68 ci-gate + shell-invoked scripts (29,919 LOC). It
does **not** carry the 35 utility + measurement scripts (11,554 LOC), and letting
it appear to would be the smuggling D6 forbids. Their rationale, separately:

- Roughly two thirds of that LOC is itself verification instrumentation —
  `constraint_mutation_runner.py` (1,883), the netlist/board defect mutators,
  `kicad_pad_rotation_oracle.py`, `bench_rust_constraints.py`,
  `bench_rust_geometry.py`, `profile_rust_topology.py`,
  `measure_cross_domain_creepage.py` (909), the baseline blessers. These inherit
  the benchmarks/ blocker (§5): an instrument that compares a Python arm against
  a Rust arm must be able to run the Python arm.
- The remainder is manual board and repo tooling (`route_board.py`,
  `add_power_planes.py`, `generate_kicad_dru.py`, `worktree_report.py`) — thin
  shells over temper_placer library code already assigned to Phases 2–5.
  Migrating the shell moves no compute, and the full R1 battery (5 PBT
  properties, 3 metamorphic relations, an induction proof) against a script run
  a few times a year is the written cost-benefit R3 explicitly admits — the same
  form the plan already used for `protocol.py`.

RETIRE was already run on this surface and is not being re-litigated:
`scripts/manifest.yaml` (audited 2026-08-02, completeness gated by
`check_manifest_gate.py`) records **40 scripts already deleted** and all
survivors as `category: keep`. The two exceptions in §4.1 are what that audit
missed.

---

## 5. Surface 5 — `benchmarks/**` (449 LOC) → JUSTIFIED-KEEP

The strongest blocker in this pass. `benchmarks/perf_ab.py` is the R1b/R2
performance A/B — the gate every Wave 4 migration must pass. Its own design note:

> the A/B runs **both arms in one process, back to back** — the verbatim
> pre-migration Python oracle and the Rust kernel it was replaced by

> Why the *same* oracle the differential test uses. […] This harness **imports
> that exact copy** rather than reimplementing it, so the two gates cannot drift
> apart.

A Rust-only harness cannot import and execute a verbatim *Python* pre-migration
implementation. Migrating it would delete the baseline arm of the gate that
authorizes every other migration. `benchmarks/cp_sat_bench.py` likewise drives
the ortools boundary that Phase 1 decided to KEEP.

Re-decidable only when the last Python oracle retires — at which point the
harness has no arm left to compare and becomes a RETIRE candidate, not a MIGRATE
one.

---

## 6. Ledger schema changes

`scripts/check_verdict_coverage.py` gained three things, all additive:

1. **`exclude:`** — a surface may list exact repo-relative paths its pattern
   would otherwise claim, so one file inside a broad surface can carry its own
   verdict (needed for the two RETIRE scripts inside `scripts/*.py`). Resolved by
   explicit carve-out rather than pattern precedence, so the exception stays
   visible in the ledger instead of being implied by entry ordering. The
   "exactly one entry per file" invariant is preserved.
2. **RETIRE now requires `justification:`** — R3 defines RETIRE as "dead or
   obsolete, deleted with justification", which the checker did not enforce.
   First use of RETIRE, so no existing entry changes.
3. **Dead-exclude detection** — an `exclude:` path that its own pattern does not
   match is a typo or a stale carve-out, and errors.

Both `exclude` failure modes already failed closed: a typo'd path leaves the file
matching two entries (multi-match error), and excluding a file no other entry
claims leaves it unmatched (coverage error).

---

## 7. Where the evidence is thinnest

Honest accounting, in order of which verdict to revisit first:

1. **`scripts/*.py` utility class (11,554 LOC)** — the weakest verdict recorded
   here, and flagged as such in the ledger entry itself. It rests on a
   cost-benefit argument rather than a hard blocker, and the boundary between
   "instrument that must host the Python arm" and "thin shell not worth
   migrating" was drawn by reading names and spot-checking, not by auditing all
   35 files. A per-file pass would sharpen it.
2. **`visualization/**`** — the "no gate can score it" argument does the most
   work here. It is true today and checkable, but it is an argument from absence:
   the verdict flips the moment someone writes a rendering regression gate, and
   nothing prevents that.
3. **Pumpkin C10 (`AddHint`)** — not independently verified. The 12-of-13 count
   does not depend on it, but the enumeration is not complete without it.
4. **The test suite is outside the ledger's roots entirely.** `roots:` covers
   `packages/temper-placer/src/temper_placer`, `packages/temper-workflow`,
   `scripts`, `benchmarks`. The plan's Phase 6 names the Python test suite
   (~155k LOC in `packages/temper-placer/tests`) as a residual owing a verdict
   under R3 — it is not measured by this check at all, so **"100% R7 completion"
   means 100% of what the ledger looks at, not 100% of the repo's Python.**
   Widening `roots:` would add a surface larger than every decided surface
   combined; that is its own decision and is deliberately not taken here.

## 8. Provenance of the inputs

The task referenced a prior agent's findings file at
`.../scratchpad/AGENT_FINDINGS_UNCOMMITTED.md`. **That file does not exist** —
the scratchpad directory survives but the file is absent, and no copy exists
under any session scratchpad. Its Pumpkin claims were therefore treated as
unverified hearsay and re-derived from primary sources (docs.rs, crates.io API,
GitHub code search against `ConSol-Lab/Pumpkin`), which is why §1.1 cites the
crate rather than the report. The two solve-site defects were likewise confirmed
directly against `origin/main` rather than taken on report. The conclusions
happen to agree with the summary relayed in the task; the citations here are
first-hand.

## 9. Addendum — the two RETIRE verdicts, executed (2026-08-04)

This section was added by the follow-up change that performed the deletion §4
decided. The measurements above are unchanged and still stand at the commit in
the provenance line; what follows is the record of the action, not a new
measurement.

Both files were deleted. Their ledger entries in `docs/wave4-verdicts.yaml`
were removed at the same time, along with their two `exclude:` carve-outs from
the `scripts/*.py` JUSTIFIED-KEEP pattern. **The justifications are reproduced
verbatim below, because this document is now their only home.** Removing a
ledger entry for a file that no longer exists is bookkeeping; retracting the
reasoning would not be.

### 9.1 Why the entries were removed rather than left in place

`scripts/check_verdict_coverage.py` was read before deciding. It does **not**
error on a `surfaces:` entry whose `pattern:` matches no file — `validate_entries`
checks verdict validity, the required `justification:`/`blocker:`/`owed:`/`phase:`
fields, and `exclude:` carve-outs, and its carve-out check is
`matches(ex, s["pattern"])`, a pure glob-shape comparison that never touches the
filesystem. So a stale `scripts/internal_route.py` exclude would still have
"matched" the `scripts/*.py` pattern as a string and passed. **Nothing in the
gate forced this cleanup.**

The entries were removed anyway, on the repo's own precedent rather than on gate
pressure. `.undeclared-imports-allowlist` records the identical decision for
`jax::scripts/check_perf_regression.py`: an entry scoped to a file that no longer
exists "exempts nothing, and reads as a live gap that is already closed". The
same holds for a verdict — a RETIRE decision on a deleted file is not a pending
decision, and leaving it in the ledger would misreport the backlog. The ledger's
own framing (§6) is that it covers "every Python file under the ledger's roots";
a file that is not there has no coverage obligation to discharge.

After the change the ledger still reports **100.0% R7 completion**, with RETIRE
at 0 files / 0 LOC — the verdict was not lost, it was discharged.

### 9.2 The verdicts, preserved verbatim

> **`scripts/internal_route.py` — RETIRE.** Import-dead, verified 2026-08-04 by
> AST sweep of every top-level import in scripts/ and benchmarks/. Imports
> `jax.numpy` (jax is not in any dependency set) and eight names from
> `temper_placer.routing.*` plus `temper_placer.io.trace_writer`, none of which
> exist -- the package was renamed to router_v6 without this script following.
> It cannot be imported, so it cannot have run since. Already noticed in passing
> by scripts/check_no_raw_rotation_trig.py's own notes; superseded by
> scripts/route_board.py, which says so in its docstring.

> **`scripts/placement_quality_report.py` — RETIRE.** Import-dead, same
> 2026-08-04 sweep. Unguarded module-level imports of `temper_placer.losses.base`
> and `temper_placer.routing.analysis`; neither package exists (both are JAX-era,
> retired). Manifest disposition is shell-invoked, which is why the sunset clock
> missed it: that gate keys off last_run dates and the invocation graph, not
> importability -- a gap worth closing separately.

### 9.3 Deadness re-derived independently before deleting

The RETIRE verdicts were not inherited. Re-verified against `origin/main`:

| check | result |
|---|---|
| `temper_placer.routing` on `origin/main` | absent (`git ls-tree`) |
| `temper_placer.losses` on `origin/main` | absent (`git ls-tree`) |
| `jax` in any `pyproject.toml` | absent |
| `import temper_placer` in the project venv | succeeds |
| `import temper_placer.routing` / `.losses` / `jax` | `ModuleNotFoundError` |
| `python scripts/internal_route.py --help` | `ModuleNotFoundError: No module named 'jax'` |
| `python scripts/placement_quality_report.py --help` | fails before reaching its own body |

`temper_placer` itself imports cleanly, so these are genuine missing
subpackages, not an unconfigured environment. No Python file anywhere imports
either script, and no `subprocess`/`exec` call names them.

### 9.4 Further RETIRE candidates found, and deliberately not deleted

Four shell scripts existed only to drive `internal_route.py`. They are recorded
here as candidates and **left in place** — this change deletes what §4 decided,
and shell scripts are outside the ledger's `roots:` (which cover `*.py` only), so
no verdict has been recorded for them and it is not this change's place to invent
one.

| script | status | evidence |
|---|---|---|
| `scripts/route_v3.sh` | dead — pure wrapper | its only command was `uv run scripts/internal_route.py` |
| `scripts/verify_occupancy_strict.sh` | dead | routes via `internal_route.py` under `set -euo pipefail`, then DRCs that output |
| `scripts/sprint1_validation.sh` | dead end-to-end | step 2 routes via `internal_route.py` under `set -euo pipefail`; steps 3–5 consume its output |
| `scripts/run_physics_flow.sh` | doubly dead | step 3 is `internal_route.py`; step 2 calls `add_power_planes_v2.py`, which does not exist in the repo |

None is invoked by CI, the `Makefile`, or any other script — the only references
are `scripts/invocation_graph.json` and two prose mentions in
`docs/plans/2026-06-22-001-feat-purge-and-protect-plan.md` and
`docs/legacy/DRC_REMEDIATION_ARCHITECTURE.md`. `sprint1_validation.sh` is the
only one with any independent content (it also calls `validate_footprints.py`
and `compare_drc_reports.py`), so it is the only one where deletion would lose
anything, and even that is unreachable past step 2.

**A gap worth closing separately:** `scripts/check_script_sunset.py` keys off
`last_run` dates and the invocation graph, not importability, which is why it
never flagged either deleted script. It would not flag these four either — a
shell script that invokes a nonexistent target is invisible to it.
