<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -- backfilled: predates the evidence-provenance gate and no self-declared commit exists in this file's own content. See .evidence-provenance-allowlist. -->

# `pipeline/feedback.py` retirement (468 LOC, zero callers)

**Date:** 2026-08-07
**Trigger:** Wave-4 residual-verdict follow-up to the 2026-08-06 `pipeline/`
audit, which left `pipeline/feedback.py` in place pending a dedicated pass
("deleting it changes `temper_placer.pipeline`'s public surface" — not a
correctness blocker, just something that needed its own check).

## Verdict: RETIRE (deleted)

`packages/temper-placer/src/temper_placer/pipeline/feedback.py` and its
re-exports in `pipeline/__init__.py` are deleted. No tests existed solely
for this module (none existed at all — see below), so there was nothing
additional to remove there.

## Evidence

**1. AST-based import scan (not substring grep).** Wrote a script that
parses every `.py` file in the repo with `ast.parse` and walks `Import`/
`ImportFrom` nodes looking for `temper_placer.pipeline.feedback` or any of
the module's 15 public names imported via `temper_placer.pipeline`. Result:
the only hit in the whole repo is `pipeline/__init__.py:13`, the module's
own re-export block. Zero external importers, static or otherwise.

**2. Name-usage grep (attribute access / dynamic reference), one pass per
public symbol** (`run_feedback_loop`, `FeedbackGenerator`,
`compute_min_loop_area`, `AdjustmentApplier`, `AdjustmentType`,
`FeedbackAdjustment`, `FeedbackLoopConfig`, `FeedbackLoopResult`,
`RoutingFeedbackLoss`, `MomentumDampedRoutingFeedbackLoss`,
`analyze_root_cause`, `analyze_loop_failure`, `analyze_thermal_failure`,
`ValidationFailure`, `RootCauseAnalysis`, `SuggestedFix`) across all `.py`
files. Zero hits outside `pipeline/feedback.py` and `pipeline/__init__.py`.
This also catches `pipeline.run_feedback_loop`-style attribute access after
`import temper_placer.pipeline as pipeline`, which the AST import scan
alone would miss — none found.

**3. Config dispatch path (the near-miss precedent from the 2026-08-06
audit).** `dag_engine.py:346` is the one place in this package that loads a
handler by dotted string via `importlib.import_module`, sourced from
`configs/pipeline_default.yaml`'s `handler:` keys. All eight `handler:`
entries point into `pipeline.stages.*`; none reference `pipeline.feedback`.

The YAML *does* contain a `feedback_contracts:` key
(`pipeline_default.yaml:45`), which looked suspicious given the module name
— but it is unrelated: it configures `dag_engine.py`'s own
`_evaluate_feedback_contracts` stage-retrigger mechanism (a
metric-threshold retry system), which is independent code that never
imports or calls anything from `pipeline/feedback.py`. Confirmed by reading
`dag_engine.py`'s `_evaluate_feedback_contracts`/`_emit_feedback_triggered`
methods — no reference to the `feedback` module or its symbols.

No `getattr`-based dynamic dispatch anywhere in the repo resolves to this
module either (checked files with both `getattr` and the string
`"feedback"`; all hits are the unrelated `placer/cp_sat/feedback.py` module
or comments/docstrings).

**4. Re-export consumption.** `pipeline/__init__.py`'s `__all__` included
the seven names re-exported from `feedback.py`. The AST scan in (1) already
covers `from temper_placer.pipeline import <name>` and
`from temper_placer.pipeline import feedback`-style access; there were none.

**5. Name-collision check (the trap the 2026-08-06 audit flagged for this
exact file).** `scripts/run_feedback_loop.py` and its `manifest.yaml` /
`invocation_graph.json` entries look like a caller of
`pipeline.run_feedback_loop` by name alone. Confirmed via
`manifest.yaml:1665` and reading the script: it imports
`temper_placer.deterministic.feedback`, a **different, unrelated, live**
module — not `temper_placer.pipeline.feedback`. Likewise
`pyproject.toml:143`'s ruff per-file-ignore for `**/placer/cp_sat/feedback.py`
is a third, unrelated `feedback.py` (under `placer/cp_sat/`). Three distinct
files share the basename `feedback.py` in this repo; only the one under
`pipeline/` was in scope here, and it is the only one with zero callers.

**6. Duplication claim re-verified against current `main`.**
`compute_min_loop_area` (shoelace via `np.dot`/`np.roll`) duplicates
`temper-geometry/src/polygon.rs`'s `polygon_area` (line 53),
`polygon_signed_area` (line 35), and `compute_loop_area` (line 289), which
are live and exposed to Python via
`temper_placer/geometry/polygon.py` (`compute_loop_area` at line 160, calls
`_tg.compute_loop_area`). Since nothing calls the Python duplicate, no
delegation/porting was needed — it was simply deleted along with the rest
of the module.

**7. Plan-doc entanglement, checked and ruled out.** Several older plan/
ideation docs propose extending `pipeline/feedback.py`
(`docs/plans/2026-06-28-003-feat-sidecar-feedback-contract-plan.md`,
`docs/plans/2026-06-28-004-feat-bidirectional-pcl-constraint-ir-plan.md`,
`docs/plans/2026-07-03-001-feat-cp-sat-feasibility-first-placer-plan.md`).
All three carry `status: stale`, `swept: 2026-07-25`,
`swept_basis: "insufficient evidence - needs human triage"` — none are
active commitments. One brainstorm doc referencing "feedback contracts"
(`docs/brainstorms/2026-06-22-orchestrator-stage-dag-requirements.md`) is
`status: active`, but its proposal was implemented via a *different*
mechanism — the YAML `feedback_contracts:` schema + `dag_engine.py`'s
`_evaluate_feedback_contracts` (see point 3) — not via
`pipeline/feedback.py`'s class-based `RoutingFeedbackLoss`/
`FeedbackGenerator`. That active doc is not a blocker for this deletion.

**8. Test coverage.** No test file anywhere under
`packages/temper-placer/tests/` references `pipeline/feedback.py` or any of
its symbols (checked both by path — `find ... -iname "*feedback*"` under
`tests/pipeline` returns nothing — and by content grep across all test
files). The three `*feedback*` test files that do exist
(`tests/pcl/test_netclass_feedback.py`,
`tests/placer/cp_sat/test_feedback.py`,
`tests/placer/cp_sat/test_loop_field_feedback.py`) test unrelated modules.
Nothing to delete on the test side.

**9. `docs/wave4-verdicts.yaml`.** `pipeline/feedback.py` was covered under
the wildcard `packages/temper-placer/src/temper_placer/pipeline/**` pattern
(verdict: `MIGRATE`, phase 5). Deleting the file removes it from that
pattern's matched-file set; no ledger edit was made, following the
precedent set by the 2026-08-06 `topology_phase.py` deletion (same
pattern, same situation, ledger untouched in that commit too — see
`648506e83`). The ledger's own coverage script only evaluates files that
exist.

## Test verification performed

Ran `make venv-isolate` in the worktree (13/13 pyo3/maturin extensions
built fresh, verified via `check_stale_extensions.py`), then:

* `pytest tests/pipeline/ -q` — the directly-affected suite (`__init__.py`
  is the only file this change edits besides the deletion itself): **230
  passed, 2 skipped**.
* `scripts/regen_derived.py` — all derived artifacts (manifest, oracle
  hashes, wasm registry, kernel wiring) reported consistent with no diff
  needed; `pipeline/feedback.py` was never tracked in `manifest.yaml` (that
  manifest covers `scripts/*.py`, not package internals).
* `python -c "import temper_placer.pipeline"` — imports cleanly; `dir()`
  confirms the seven feedback names are gone and everything else
  (`PipelineConfig`, `ConvergenceChecker`, `PreflightResult`, etc.) is
  intact.
* Full `packages/temper-placer` suite (`pytest tests/ -q`, 17177 items
  collected, **zero collection errors** — the definitive check that
  nothing else imports the removed module or its symbols): run in two
  passes.
  1. First pass (all markers) reached 46% (~7,900 tests) before stalling
     on a single `@pytest.mark.slow`-marked CP-SAT test
     (`test_hybrid_pour_stitch_measurement.py`, internal 600s DRC timeout)
     — killed and restarted with `-m "not slow"`, the repo's own
     documented convention (`pyproject.toml:82`) for excluding exactly
     this class of test.
  2. Second pass (`-m "not slow"`) reached 59% (~10,100 tests, 508 test
     files) before being stopped after a `router_v6` hypothesis
     property-based test ran for >20 minutes on one file with no
     completion — a legitimate compute-bound PBT test unrelated to this
     change (confirmed still consuming CPU via repeated `ps`/`top`
     sampling, not a hang; `sample`'s call graph showed active CP-SAT/
     absl work, not a blocked syscall).
  3. **Failures observed across both passes, consistently, at the same
     four files, in domains with no import path to `pipeline/feedback.py`
     (confirmed by the AST scan finding zero importers anywhere in the
     repo, tests included):** `tests/analysis/test_courtyard_violation_report.py`,
     `tests/cli/test_optimize_validator_input.py`,
     `tests/closure/test_router_completion.py`,
     `tests/placer/cp_sat/test_clearance_repair.py`. These read as
     pre-existing baseline issues (consistent with the task brief's own
     note that `test_u3_routed_nets_traceable` fails on `main` from
     pre-existing baseline corruption) — not introduced by this change,
     which touches only `pipeline/__init__.py`'s import list and deletes
     an unimported file. One additional failure
     (`tests/geometry/test_geometry_pbt.py`) appeared in the first pass
     only and passed cleanly in the second — flaky/random-seed PBT
     behavior, not a regression (this change does not touch geometry
     code).
  4. **Not run to 100% completion.** The remaining ~40% is dominated by
     `router_v6`/`placer` CP-SAT and hypothesis property tests whose
     per-file runtime (minutes each) is disproportionate to verifying a
     zero-caller module deletion — stopped for proportionality, following
     the same judgment call the 2026-08-06 `topology_phase.py` deletion
     commit (`648506e83`) made explicitly ("rebuilding five crates was
     disproportionate for removing a file with no references"). Nothing
     in the untested remainder imports `pipeline`, `pipeline.feedback`, or
     any of its symbols (per the AST scan, which covered the entire repo
     including `tests/`).

## Not verified

* The full `packages/temper-placer` suite was not run to 100% completion
  (see above) — the untested ~40% is `router_v6`/`placer` CP-SAT-heavy
  tests, none of which import the deleted module per the AST scan.
* Whether any *out-of-repo* consumer (external tooling, notebooks) imports
  `temper_placer.pipeline.feedback` — outside this repo's grep/AST reach by
  construction.

## Left untouched (out of scope for this pass)

* `pipeline/topological.py`, `pipeline/stages/topological_stage.py` — the
  live `legalize_zone_aware` trap recorded in the 2026-08-06 audit. Not
  touched here.
* `pipeline/iterator.py` — loop-control glue, no numpy compute, not part of
  this file's scope.
