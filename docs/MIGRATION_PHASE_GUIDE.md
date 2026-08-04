# Wave 4 Migration — Per-Phase Implementation Guide

A build-elsewhere reference for the Python→Rust consolidation. Everything here is
measured against `origin/main`, not estimated. Where a figure came from a running
migration rather than a plan, it says so.

Governing documents, in precedence order:

| Document | Owns |
|---|---|
| `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md` | phases, the R1 gate set, the R3 residual procedure |
| `docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md` | why the migration exists; deprecation criteria (D6, R19–R22) |
| `docs/wave4-verdicts.yaml` | the per-surface verdict. **This file is the phase assignment.** |
| `docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md` | Phase 3 candidate breakdown |

`scripts/check_verdict_coverage.py` enforces the ledger: every Python file under
its roots must match exactly one entry, a `JUSTIFIED-KEEP` must name a blocker,
a `MIGRATE` must name a phase. It runs in `Repo Hygiene & Import Gates`.

---

## The unit of work

A migration is not "port a file". It is a **delegation shim plus a differential
against a pinned oracle**, and the oracle is the evidence:

```
packages/<crate>/src/<module>.rs                        the implementation
packages/temper-placer/src/temper_placer/<mod>.py       becomes a delegation shim
packages/temper-placer/tests/**/_<mod>_py_oracle.py     VERBATIM pre-migration copy
packages/temper-placer/tests/**/test_<mod>_rust_differential.py
packages/temper-placer/tests/**/test_<mod>_pbt.py
packages/<crate>/VERIFICATION.md                        proof or explicit N/A
```

`90bdacbe2` (the `core/priority.py` migration) is the reference shape. Read it
before writing anything.

The oracle is a **verbatim** copy, not a paraphrase. It is the other arm of the
differential; if it drifts, the differential proves nothing.

---

## The R1 gate set — every migration, no carve-outs

- **R1a — behavioural A/B.** Differential against the pinned oracle, asserting
  **bit-identical** output. Compare floats via `float.hex()`, never a tolerance.
  Carry each non-float leaf's concrete `type` in the comparison key, so
  `int`-vs-`float` and `f32`-vs-`f64` cannot hide behind numeric equality.
  Compare numpy arrays as `(dtype, shape, tobytes())`.
- **R1b — performance A/B.** `scripts/pr_perf_compare.py`, margins
  `TIMING_MARGIN=0.20`, `COMPLETION_MARGIN=0.10`. For pure-delegation or
  I/O-shaped surfaces this is the *no-regression-beyond-noise* arm — do not
  manufacture a speedup claim.
- **R1c — >= 5 non-vacuous properties per module.**
- **R1d — >= 3 metamorphic relations per module**, honestly bounded.
- **R1e — `VERIFICATION.md` entry.** Induction proof where the module has
  recursive or iterative structure; a structural proof or an explicit
  non-applicability note otherwise. State which and why.
- **R1f — TDD.** The differential is written first and demonstrated RED.
- **R1g — Rust practice.** Borrow over clone, no `unwrap` outside tests,
  `catch_unwind` at every pyo3 boundary.
- **R1h — physics-gated surfaces** additionally take the R24 discipline from
  `AGENTS.md`: Chebyshev-style soundness proof, BMC-exhaustive validation on
  small N, post-solve audit. See `docs/physics-verification-methodology.md`.

### Anti-vacuity is not optional

Mutate the Rust, confirm the differential **fails**, revert, and record every
mutation and what caught it. Landed migrations ran 6, 8 and 11 mutants.

Two of them found mutants that **survived**, and closed the gap by adding
discriminating cases rather than lowering the claim. One survivor was a provable
*equivalent* mutant (1 mismatch in 2×10⁵ samples, at `5e-324`) and was still
closed by adding a subnormal input.

A differential that has never been shown to fail is not evidence.

---

## Numerical traps — all of these were found by real migrations

These recur. Assume each applies until measured otherwise.

**Summation strategy.** One module can carry three different roundings:
`np.sum` is a blocked pairwise reduction and disagrees with naive accumulation
for every n >= 8 (exact for n <= 7); CPython 3.12's `sum()` is
Neumaier-compensated; `+=` is neither. Establish which each call site uses.

**dtype polymorphism.** numpy arithmetic runs in the *caller's* dtype, and NEP 50
makes promotion data-dependent. An f64 port of an f32 pipeline is bit-wrong: one
migration measured `0.5999999940395355` against numpy's `0.6000000238418579`.
Track promotion per operand — numpy promotes per operation.

**NaN semantics.** `np.minimum`/`np.maximum` propagate NaN from either operand;
Rust's `f64::min`/`max` discard it.

**Iteration order.** If a fold runs over a `set` or `dict`, its low bits may
already vary per process. **Do not sort to stabilise it** — that is a behaviour
change no differential can catch. Prove Rust matches Python for every
permutation, and show the permutation set discriminates.

**Empty-input semantics.** `all()`/`any()`/`mean()` over an empty sequence is
where vacuity hides. Establish and assert the empty behaviour of every aggregate.

**Library semantics are not reimplementable.** Three landed cases:
- PyYAML is YAML **1.1**; `serde_yaml` is **1.2**. They disagree on `on`/`off`,
  `012`, `1_000`. Re-tokenising in Rust changes behaviour while the differential
  on shipped fixtures stays green.
- GEOS `buffer(r).bounds` is **not** `bounds ± r` — 169/169 mismatches measured,
  worst 2.4e-3 mm against a 0.2 mm clearance.
- `np.linalg.eigh` is LAPACK and not bit-reproducible.

When the boundary cannot be crossed bit-exactly, **keep the Python call across
the boundary and argue it in-source**, or record an R3 `JUSTIFIED-KEEP` with a
named blocker. Both are successful outcomes.

**Darwin/Linux divergence.** `kicad-cli` geometric counts differ ~+107 on `total`
between macOS 10.4 and the pinned Linux 10.0.5. Perf ratios carry a measured
~11% platform bias. **Never compare a local measurement against a CI-recorded
one**, and capture baselines on CI.

---

## Phase 0 — discipline contract and A/B harness *(landed)*

The spine: every other phase's acceptance is defined here.

Delivered: `pr_perf_compare.py` exits non-zero on regression; the
`continue-on-error` mask removed; a missing baseline fails closed; the context
registered as required via `context_triggers`; the baseline given a growth path
(`push: branches: [main]`, capture on main, gate on PRs) and widened to n=6.

**Two failure modes worth inheriting.** The gate reported *success* for weeks
while its comparison script died with `JSONDecodeError` — `main()` returned 0
unconditionally, `load_pr_metrics` used `json.load` on NDJSON, a missing file
returned `[]`, and `continue-on-error` swallowed the traceback. Separately, a
darwin-captured baseline was **-11% biased**, which would have made the gate miss
every regression between +20% and +35% while reporting a spurious "IMPROVED" on
clean PRs.

---

## Phase 1 — ortools CP-SAT boundary *(verdict: KEEP)*

Not a migration. A decision gate, and it is decided.

**The blocker is not feature coverage.** Pumpkin 0.4.0 covers 12 of 13 constraint
classes, including half-reification (`Constraint::implied_by`, exactly
`OnlyEnforceIf`) and assumption cores (`extract_core`) — the feature everyone
assumed was absent. The only gap, `AddNoOverlap2D`, is documented in-repo as
redundant for correctness.

**The real blocker** is that acceptance is *candidate quality under a wall-clock
budget, adjudicated by a human on 120-sample DRC*, and no gate expresses that. In
`de59c0458`, Run A and Run B came from the same engine with the same seed and
different recipes; one regressed DRC across the ceiling and was discarded, the
other landed. A REPLACE has no parity gate it could pass.

**Open defect, unfixed:** three solve sites, two with unfrozen params.
`unsat.py:277` sets neither `random_seed` nor `num_search_workers` (auto-detect,
measured 12 workers), so **the minimal unsat core is not reproducible across
machines**. `model.py:434-436` sets workers but no seed. R4's version-locked solve
contract is therefore **not met**. `pyproject.toml` also declares ortools twice,
`>=9.12` and `>=9.10`; the effective floor is the looser one.

---

## Phase 2 — contracts as pyo3 pyclasses *(partially landed)*

**~12,204 LOC remaining.** The pivot: parse output and orchestration calls both
flow through these objects, so migrating them first makes Phases 3 and 5
tractable.

Landed in `temper-design-bundle`: `net_types`, `loops`, `design_rules`, `gates`,
`priority`. In flight: `core/board.py` + `core/netlist.py`.

**The technique that makes float32 contracts bit-exact:** never re-implement
numpy's cast. Call `numpy.array(obj, dtype=numpy.float32)` with the identical
argument the oracle builds. Store fields as opaque `Py<PyAny>` with
Python-operator arithmetic, so `Component("R1","fp",(1,2)).width` remains
`int 1` — widening becomes *unrepresentable*, not merely untested.

**The gap a contract differential cannot see.** A differential compares values,
so it cannot detect that a type stopped supporting an operation nobody declared
it needed. Two regressions escaped it: `board.traces` attribute injection, and
`dataclasses.replace()` (load-bearing in `apply_placements.py`). Both were found
only by running the **broad suite against a pre-migration baseline of the same
selection** — 10 failed/5 passed before, 15/0 after. The absolute count could not
show it, because ~10 environment failures sat on both sides.

**Do this for every contract migration.** Baseline the broad suite first.

Known R3 keeps: `LayerIndex` stays a Python `IntEnum` (pyo3 cannot subclass
`int`, and consumers rely on int-ness); `compute_eigenvector_centrality` stays
Python (LAPACK).

Type-check note: the ratchet is monotonic-shrink. Fix the **stubs**
(`packages/temper-placer/stubs/temper_design_bundle_python/__init__.pyi`), not
the baseline — `replace()` needs typeshed's `DataclassInstance` protocol.

---

## Phase 3 — formats / IO *(in progress)*

**~9,235 LOC.** Closing condition: **kiutils no longer imports in product code**,
the corpus round trip is bit-identical, and every `io/` module carries a verdict.

Candidates, measured. 3–5 depend on candidate 1:

| # | Scope | LOC | Risk |
|---|---|---:|---|
| 1 | `core/board.py`, `core/netlist.py` → pyclasses | 1,243 | High — 100+ consumers each |
| 2 | `io/netclass_loader.py`, `io/loop_loader.py` | 402 | Low — **landed** |
| 3 | parse engine: `kicad_parser`, `_parse_*`, `_kicad_types`, `kicad_metadata` | 1,983 | High — float-parse parity |
| 4 | write engine: `kicad_exporter`, `_write_*`, `kicad_writer`, `placement_exporter` | 2,493 | High — inputs unmigrated |
| 5 | config/reference loaders | 1,677 | Medium — pydantic boundary |
| 6 | DSN surface | 795 | Medium — **landed**; determinism pinned |
| 7 | residuals — mostly R3 verdicts | 1,352 | Low-Med |

**Candidate 2's central judgment, which generalises:** PyYAML stayed on the
Python side. `yaml.safe_load`, `pathlib.Path.glob` and `yaml.dump` are called
*back* across the boundary; everything downstream — field mapping, default
evaluation order, coercion, enum resolution, error strings, sort/dedup, the
skipped-key warning, `except Exception` cause chaining — is Rust.

**Candidate 6's determinism pins:** `round()` is half-to-**even** (`f64::round`
shifts geometry a 10 µm unit on every `.5` tick); `str::to_lowercase` applies the
Greek final-sigma rule CPython does not, *and it builds sort keys*; dict
**insertion** order needs an `InsertionMap`, not a `HashMap`; Python's `$`
matches before a trailing newline and the regex crate's does not.

Candidate 6 also found **two live divergences in already-landed Rust**: an empty
comment emitted a bare `;` (Rust tested emptiness, Python truthiness), and a
`bool` rendered as `1` (pyo3's `PyInt` check accepts `bool`; CPython renders
`True`).

Scope note: 105 of candidate 6's costed 795 LOC were already Rust shims. **Survey
before migrating** — one Phase 4 surface was 9 of 11 files already delegating.

---

## Phase 4 — remaining compute *(in progress)*

**~29,880 LOC**, independent of Phase 3 per R8. Surfaces: `validation/` 13,814,
`heuristics/` 4,319, `physics/` 4,233, `regression/` 3,165, `explainability/`
2,182, `topological/` 1,501, plus `metrics/` and the `geometry/` remainder.

`physics/loop_area.py` and `physics/thermal_fdm.py` carry the **KTD9** keep —
`scipy.spsolve` deliberately retained, ~5e-13 K parity measured. `scipy` does not
appear in `thermal_potential.py` or `operating_point.py`.

**A measured warning about Phase 4's value.** One migrated kernel came out
**1.9× slower**: the cost was Python-list marshalling, not the kernel, with
crossover at n ≈ 256. Another was 5.1× faster. Measure before assuming a win, and
prefer surfaces whose *callers* will also migrate — a Rust kernel behind a
per-call marshalling boundary can be net-negative.

**A `dlsym` trap.** `RTLD_DEFAULT` is `-2` on Darwin, not `NULL`. Passing `NULL`
makes `dlsym` return null, and LLVM then lowers the fallback `powf(x,2.0)`→`x*x`
and `powf(x,0.5)`→`sqrt(x)` — silently reintroducing a forbidden optimisation.
**The randomised differential missed this; only the mutation sweep caught it.**

---

## Phase 5 — orchestration *(not started)*

**~55,596 LOC — the largest phase.** `pipeline/`, deterministic stages, `cli/`,
`heuristics/` decision points, `router_v6` orchestration remainder,
`_adapter_convert.py`, `adapters/`, `report/`, `requirements/`,
`explainability/`, `temper-workflow`.

Lowest compute value, highest call-site churn. This is where strangler wrappers
and dispatch flags live, and where the pyo3 boundary finally collapses: every
`#[pyfunction]` that exists because Python calls it becomes an internal Rust call
once its caller migrates.

**Current boundary surface, for ordering:** ~512 markers across ~44k Rust LOC.
`temper-drc-rs` is 0.3% boundary-dense (the target shape, because its callers
already moved); `temper-rust-router` is 4.5% (mostly boundary). 58 `Py<PyAny>`
fields — 28 in `temper-design-bundle`, 11 in `temper-constraint-compiler`, 10 in
`temper-rust-router` — are the deepest form of not-really-migrated: data lives in
Python and Rust carries a handle.

**Order Phase 5 by boundary crossings removed, not by LOC.**

---

## Phase 6 — residuals *(verdicts recorded)*

Closes the program: every surface carries a verdict. Recorded keeps and their
blockers:

| Surface | Verdict | Blocker |
|---|---|---|
| `placer/cp_sat/**` (11,257) | JUSTIFIED-KEEP | the ortools boundary, above |
| `visualization/**` (6,086) | JUSTIFIED-KEEP | acceptance unassertable; no gate scores it |
| `scripts/**` (~60k) | JUSTIFIED-KEEP | **gate independence** — four gate scripts carry deliberately duplicated parsers so no gate's correctness depends on a sibling's internals. Consolidating destroys the property. Plus bootstrap (`check_rust_drc_presence.py` cannot be a Rust binary) and cost (22 of 26 workflows have no Rust toolchain) |
| `benchmarks/**` | JUSTIFIED-KEEP | must host the perf A/B's Python arm |
| `profiling/`, `testing/`, `fixtures/` | JUSTIFIED-KEEP | instrumentation and test helpers; migrating them makes the harness depend on the boundary it checks |
| package root `*.py` | JUSTIFIED-KEEP | a pyo3 distribution still needs a Python package root |

**"Consolidation" is never a sufficient justification** (D6). The coverage gate
enforces this structurally: a `JUSTIFIED-KEEP` without a `blocker:` fails.

The ~155k-LOC test suite sits outside the ledger's roots and still owes a verdict.

---

## Deprecation — when Python can actually be deleted

Per goal-set D6 / R19–R22. A migration landing reaches only the first two states:

1. the Python module becomes a delegation shim
2. its pre-migration implementation is retained as the differential's oracle
3. **shim and oracle removed** — a separate, evidenced decision

**R20 is the gate on state 3:** a differential is removed only when the property
and metamorphic suites are shown to catch **every mutant it caught**. Re-run the
migration's mutation campaign with the differential disabled; any survivor keeps
the differential. The campaigns already exist, so this is re-running evidence.

**R21:** a shim is removed only when no consumer imports it, demonstrated by the
import gate rather than by search.

**R22:** a `JUSTIFIED-KEEP` surface is never deprecated while its blocker holds.

**Import-dead is not reference-free.** One retired script had 23 referencing
files — four shell scripts, two production modules, three gate scripts, an
allowlist, and two derived artifacts (`scripts/invocation_graph.json`,
`scripts/manifest.yaml`). The manifest marked it `category: keep`, because the
sunset gate keys off `last_run` and callers, not importability.

---

## Operational notes

- **Qualify every git read with `origin/main`.** The working copy sits on a
  feature branch. This produced four false "the code is missing" conclusions in
  one session.
- **A stale venv misreports the Rust surface.** The installed
  `temper_design_bundle_python` is a shim re-exporting the compiled module. Read
  source or rebuild.
- **Bare `uv run` in a test re-syncs the venv and reverts `maturin develop`
  mid-suite.** Set `UV_NO_SYNC=1`.
- **A new script needs a `scripts/manifest.yaml` entry** (purpose, owner,
  category, disposition, imports) or the manifest gate fails.
- **A new plan doc needs the regenerated `docs/plans/README.md` in the same
  commit**; a doc under `docs/evidence/` needs a
  `provenance: commit=<sha> dirty=<bool>` line.
- **Editing a test file shifts vulture baseline line numbers** — re-record them,
  do not delete the findings.
- **Disk**: each worktree is a multi-GB release build. Check
  `df -h /System/Volumes/Data`, never `df -h /`. Five parallel building agents
  exhausted the volume and lost their work.
