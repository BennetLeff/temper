<!-- provenance: commit=28b2b17eba9c27dfa32b871e2f57926ef213d0d7 dirty=false -->
# Oracle FREEZE — batch 1 retirement record (2026-08-20)

Branch: `migration/retire-oracle-batch-1` (PR for review).
Tooling: `scripts/gen_oracle_freeze.py` + `scripts/_lib/oracle_freeze.py` +
`scripts/oracle_freeze_specs/*.py` (U4 of
`docs/plans/2026-08-11-003-feat-migration-pipeline-wire-and-retire-plan.md`),
template `copper_reach.py` (first retiree, PR #1021).

## Retired (2 oracles → 2 Rust golden-vector tests)

| Oracle | Kernel | Spec | Golden test |
|---|---|---|---|
| `tests/regression/_measure_closure_py_oracle.py` (175 LOC) | `temper-design-bundle/src/measure_closure.rs::compute_drc_clearance_pass_pct` | `scripts/oracle_freeze_specs/measure_closure.py` | `measure_closure::frozen_tests::frozen_measure_closure_*` (96 cases, 7 non-vacuity checks) |
| `tests/regression/_schema_validator_py_oracle.py` (87 LOC) | `temper-design-bundle/src/schema_validator.rs::validate_schema` | `scripts/oracle_freeze_specs/schema_validator.py` | `schema_validator::frozen_tests::frozen_schema_validator_*` (104 cases, 10 non-vacuity checks) |

Both oracles were VERBATIM from pre-migration commit `0a29f15e3`, created
at `de1f6ac9d`, unchanged for **1489 commits** as of the freeze — far past
the plan's 10-consecutive-commit retirement bar.

What changed per retirement (copper_reach precedent):
- `scripts/oracle_freeze_specs/<name>.py` written (copper_reach template);
  `run_oracle` drives the pinned oracle's own code (stubbed `ClosureTest.run`
  for measure_closure; temp-YAML `SchemaValidator` for schema_validator) so
  the corpus is the oracle's byte-for-byte output, not a re-transcription.
- `gen_oracle_freeze.py --spec <name>` baked the corpus into the kernel
  file's own `#[cfg(test)] mod frozen_tests` (golden const + assert loop +
  non-vacuity guard). Both kernels are pure functions (no pyo3 objects in
  or out — only the `PyResult` wrapper, unwrapped in the test), so the
  golden tests are plain Rust data.
- The Python oracle file was `git rm`'d; its `scripts/oracle_hashes.json`
  entry removed (165 → 163 entries).
- The differential test file was reduced to the
  `test_shipped_module_delegates_to_rust` wiring check (Stage 7 concern —
  FREEZE deliberately does not touch wiring).
- The Python modules themselves were NOT deleted (see per-module notes
  below); neither is in `.orphaned-python-module-inventory` as deletable.

Python LOC removed: 262 (175 + 87 oracle files).

## Verified

- `cargo test --features python frozen_measure_closure frozen_schema_validator`
  (temper-design-bundle): 4/4 pass (2 golden + 2 non-vacuity per kernel).
- `scripts/check_oracle_hashes.py`: 163/163 OK.
- `scripts/check_stale_extensions.py`: 10/10 fresh after `make extensions`.
- `make regen-check`: all derived artifacts consistent (wasm registry for
  temper-design-bundle unchanged — the new `frozen_tests` modules census as
  `[python-gated]`, the crate's established exclusion).
- pytest: `tests/regression/` 461 pass, `tests/pipeline/` 626 pass,
  `tests/explainability/` pass (in combined run), placer adjustment/deterministic
  24 pass. `tests/placer/cp_sat/test_tank_creepage.py` has 26 PRE-EXISTING
  failures on `origin/main` (netclass creepage config `6.3 < PD3 10.0`), unrelated
  to this change (the diff touches none of the design-rules config).

## Skipped (9 oracles) — reasons, for the next batch

Retirement bar met for all (each unchanged since creation), but the
FREEZE model requires a golden-vector test that is plain Rust data calling
a pure kernel. Each skip below violates that requirement structurally:

| Oracle | Kernel | Why skipped |
|---|---|---|
| `_cp_sat_comparison_py_oracle.py` | `cp_sat_comparison.rs::compare_metric_dicts` | Kernel's contract is live `PyDict` in / `PyDict` out — a golden test must construct and inspect Python dicts under the GIL (pyo3-bound test code, not plain Rust data; not wasm32-executable). Freezing would require refactoring the working kernel to split a pure core from pyo3 marshalling — out of scope for batch 1. |
| `_dag_expr_py_oracle.py` | `temper-io-types/src/dag_expr.rs` | Parser outputs are Python `ast` objects (incl. the custom `_AccessorExpr` node) — not renderable as Rust const data; evaluator requires live `config`/`state` objects via `hasattr`/`getattr`. |
| `_placer_adjustment_py_oracle.py` | `temper-io-types placer_core` | Kernel receives Python callables (`_numpy_dist_f64`, `_uniform`, `_cos_sin`) and depends on numpy dtype semantics + the global `np.random` stream — the "arbitrary callables" skip category, literally. |
| `_hypergraph_factory_py_oracle.py` | `hypergraph_factory.rs` (pyo3 pyclasses) | Oracle outputs are `scipy.sparse.coo_matrix` + numpy arrays + `PhysicsHypergraph` dataclasses; inputs are `Netlist` pyclasses — live-object outputs, not const-renderable. |
| explain_oracle/* (5: logger, markdown_report, pipeline, serialization, traced_loss) | `temper-io-types explain.rs` / `temper-orchestration explainability.rs` | Survey-flagged category: context managers (`TracedLossContext`), decorators (`@traced`), `json.dumps`/`datetime.fromisoformat`/Enum construction, live `Decision`/`DecisionTrace` objects — Python marshalling Rust deliberately does not own (see `.orphaned-python-module-inventory` and the crates' VERIFICATION.md). |

## Per-module Python shim disposition (not deleted)

- `regression/measure_closure.py` — thin harness over kept `ClosureTest.run()`
  (payload assembly, truth gates, promotion-gate CLI); stays.
- `regression/schema_validator.py` — shim formatting reason codes into exact
  messages with Python `str()` (int-vs-float type-carrying); its import path
  is pinned inside VERBATIM oracle `tests/pipeline/_metrics_observer_py_oracle.py`
  (bytes cannot be edited); stays.

## Regeneration note

Re-running a retired spec's generator fails with an actionable import error
by design; revive the oracle from git history for one session first
(`git show de1f6ac9d:packages/temper-placer/tests/regression/_<name>_py_oracle.py`),
run, discard. `gen_oracle_freeze.py` is not a CI drift gate.
