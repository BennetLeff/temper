# Wave 4 triage: `validation/results/battery_run.py` + `validation/helps_battery.py` — no port (KEEP, OUT-OF-RUNTIME)

<!-- provenance: commit=9478209623e068449f9b0bbb6edcba991322b7bd dirty=false -->

Target crate assigned: `packages/temper-quality-oracle`. Source:

- `packages/temper-placer/src/temper_placer/validation/results/battery_run.py` (1,003 LOC)
- `packages/temper-placer/src/temper_placer/validation/helps_battery.py` (531 LOC)

**Verdict: no port, no delete — KEEP as out-of-runtime verification tooling.**
Neither file is reachable from any runtime entry point (`temper` CLI, `route_pcb`,
the pipeline DAG). Both are live — imported and exercised by four test files with
real assertions, not dead code. Neither contains a numeric kernel; both are
orchestration, dict/dataclass assembly, and verdict-decision logic wrapped around
calls into the actual physics compute (`solve_thermal_fdm`, `ThermalScorer`),
which live in separate files outside this triage's scope. Under the stated goal —
**no Python at runtime, Python retained for verification** — this is exactly the
verification case: an A/B "keep/kill" experiment harness that decides whether a
physics feature (the thermal field) should ship, not code the shipped pipeline runs.

## What the files actually are

- `helps_battery.py` (U3 in the file's own numbering): the three-arm (`no_field` /
  `cheap_heuristic` / `physics_field`) A/B harness. `run_helps_battery` drives N
  perturbations through a caller-supplied `build_arm_placement` + `score_placement_fn`,
  accumulates per-arm margins, asserts A/B divergence (`_assert_divergence`,
  `_placements_equal`), checks a cost budget, and calls the pure `decide_verdict`
  function to produce `BatteryVerdict.KEEP | KILL | INCONCLUSIVE` against a
  pre-registered pass bar. A worst-case-per-perturbation guard (`#133`) can downgrade
  a mean-based KEEP to INCONCLUSIVE if any single perturbation misses the bar.
- `battery_run.py` (U10): the thermal-specific orchestrator. Wires
  `solve_thermal_fdm` (U5) + `ThermalScorer` (U7) + `OperatingPointGate` (U6) into
  `run_helps_battery`, adds a pre-battery smoke test (`_ensure_field_diverges` —
  aborts if field-on vs field-off produce identical positions, i.e. the field toggle
  is a no-op), a gate-first guard (`_ensure_operating_point_clean`), human-reference
  calibration, a between-arm-saturation guard (`#137` — catches a degenerate/garbage
  conductivity field producing identical scores across all arms), and assembles the
  `BatteryRunArtifact`/`BatteryRunReport` result with a content hash and
  save/load round trip.

Both files are pure dataclass/dict/`statistics.mean` orchestration around calls into
physics modules that are out of this triage's scope (`temper_placer.physics.thermal_fdm`,
`temper_placer.physics.copper_coverage`, `temper_placer.physics.heat_removal`,
`temper_placer.validation.thermal_scorer`).

## 1. Runtime reachability — checked by import edge, not substring match

- **Pipeline DAG.** `packages/temper-placer/configs/pipeline_default.yaml` lists eight
  `handler:` dotted paths, all under `temper_placer.pipeline.stages.*`
  (`input_stage`, `semantic_stage`, `topological_stage`, `preflight_stage`,
  `geometric_stage`, `routing_stage`, `refinement_stage`, `output_stage`). None
  reference `validation.results.battery_run` or `validation.helps_battery`.
  `dag_engine.py`'s `_load_handler` (line 341) resolves handlers via
  `importlib.import_module` + `getattr` on exactly those dotted strings — the same
  dispatch mechanism that nearly caused `TopologicalStage` to be wrongly deleted
  elsewhere in this program — so the YAML's static list is the full handler surface;
  there is no other dispatch table to check.
- **Repo-wide config/dotted-path grep.** `grep -rn "validation\.results\.battery_run\|validation\.helps_battery"` across `*.py *.yaml *.yml *.json *.toml`, filtered to non-test paths, returns only the files' own internal
  references (`results/__init__.py` importing `battery_run.py`; `battery_run.py`
  importing `helps_battery.py`). No config, script, or handler string anywhere in the
  repo names either module.
- **Package public surface.** `temper_placer/validation/__init__.py` re-exports 6
  submodules (`base`, `dead_parameter_probe`, `drc`, `drc_oracle`,
  `gate_input_registry`, `geometric`, `metrics`, `preflight`, `scheduler`, `spice`,
  `validation_gates`) — it does **not** import `results` or `helps_battery`. So even
  `from temper_placer.validation import *` does not pull either file in.
- **CLI.** `pyproject.toml` `[project.scripts]` maps both `temper-placer` and `temper`
  to `temper_placer.cli:main`. Grepped every file under `src/temper_placer/cli/` for
  `battery`: the only hit (`andon_commands.py`) is an unrelated docstring reading
  "the R1 battery has nothing to pin" (test-suite terminology, not this file) —
  confirmed a false positive by reading the surrounding sentence, not just the grep
  hit.
- **`route_pcb`.** `def route_pcb` exists only in
  `router_v6/_adapter_convert.py`, a different subsystem (routing, not placement
  thermal validation); it does not import from `validation.helps_battery` or
  `validation.results`.
- **Near-miss: `regression/reporter.py`'s `BatteryVerdictReport`.** This is a
  same-family but *distinct* dataclass (`field_name`, `verdict: str`,
  `verdict_details`, `cost_seconds`, `budget_exceeded`, `event`) with a docstring
  calling it "a battery verdict surfaced on the reporter" — it looks like a
  consumer of `battery_run.py`'s output but does not import either file; it is a
  hand-shaped mirror of a subset of `BatteryRunReport`'s fields. Its only method,
  `RegressionReporter.add_battery_verdict`, has **zero PRODUCTION callers** — it
  is called only from tests (`tests/validation/test_thermal_battery_run.py`, 3 call
  sites at lines 802/833/843). An earlier draft of this note said "zero callers
  repo-wide", which overstated the evidence: the grep behind it was scoped to
  exclude `tests/`, so the claim reached further than what was measured.

  The distinction does not change the verdict and in fact strengthens it: the
  method is exercised, so it is not dead scaffolding — it is test-only surface,
  which is exactly the "reachable only from tests" category this triage is
  establishing. It is not evidence of runtime reachability either way.

**Conclusion: neither file is reachable from the `temper` CLI, `route_pcb`, or the
pipeline DAG. Both are reachable only from tests.**

## 2. Dead-code check

Neither file is dead. Grepped every absolute import site
(`from temper_placer.validation.results.battery_run import ...`,
`from temper_placer.validation.helps_battery import ...`) plus the package-level
re-export chain:

- `results/__init__.py` re-exports `BatteryRunArtifact`, `BatteryRunReport`,
  `run_thermal_helps_battery` from `battery_run.py` — live within the package.
- `battery_run.py` imports `BatteryVerdict`, `HelpsBatteryResult`,
  `run_helps_battery` from `helps_battery.py` — live within the package.
- Test importers, all under `packages/temper-placer/tests/`:
  - `tests/validation/test_thermal_battery_run.py` (1,141 lines) — imports
    `BatteryRunArtifact`, `BatteryRunReport`, `run_thermal_helps_battery`,
    `_MinimalPlacement`, `BatteryVerdict` from `battery_run.py`. Exercises
    `run_thermal_helps_battery` directly across ~12 call sites, plus artifact
    save/load round-trip and `BatteryVerdictReport` construction.
  - `tests/validation/test_helps_battery.py` (labelled "U3 A/B harness with
    kill-capable verdict") — imports `BatteryVerdict`, `HelpsBatteryResult`,
    `run_helps_battery` and exercises KEEP/KILL/INCONCLUSIVE paths directly,
    including the temporal-gating check
    (`test_created_at_post_dates_battery_run_raises`).
  - `tests/validation/test_verdict_properties_pbt.py` — property-based tests
    (Hypothesis) directly against `decide_verdict` and `run_helps_battery`,
    asserting the verdict ordering (`KILL < INCONCLUSIVE < KEEP`) and monotonicity
    in `margin_gain`.
  - `tests/physics/test_copper_coverage.py` — imports `HelpsBatteryResult` and the
    `battery_run` module for its `#137` between-arm-saturation guard tests.

This is a well-tested harness, not dead code kept alive only by a trivial
self-referential test. The tests assert real decision-logic behavior (verdict
priority order, divergence-detection no-op catch, budget enforcement, the `#133`
worst-perturbation downgrade, the `#137` saturation guard) — the kind of coverage
that exists because the harness has a real job (deciding whether to keep or kill the
thermal-field feature), not because someone wrote a test to justify the file's
existence.

## 3. Numeric-compute check

`grep -n "np\.\|scipy\|linalg\|lapack"` across both files: every hit is
`np.random.default_rng`, `np.array`/`np.asarray` (dtype casts), `np.clip`,
`np.zeros_like`, `np.max`/`np.min`/`np.mean`, and one `np.allclose` — perturbation
generation, position clamping to board bounds, and array-summary logging. No
`np.dot`, `np.linalg`, `scipy`, or LAPACK call in either file. The only place a real
numeric solve happens is inside `solve_thermal_fdm` and `ThermalScorer.score`, which
these files call but do not implement — those modules are out of this triage's
scope (separate files, not `battery_run.py`/`helps_battery.py`). There is no
separable kernel here to FFI across; porting either file would mean reimplementing
dataclass assembly, JSON serialization, and a verdict decision tree in Rust for zero
runtime benefit, since nothing at runtime calls either file today.

## Why this stays Python

Same shape as this program's recorded OUT-OF-RUNTIME category
(`docs/plans/2026-08-06-001-docs-python-removal-retriage-plan.md`): "experiment
harnesses and validation runners" are dev/CI tooling, not shipped runtime, and are
in scope only under a "no Python in the repo" goal, not "no Python at runtime." The
task's stated goal here is the latter. Both files are, in the plan's own words,
squarely what that category was written to describe — `helps_battery.py`'s
module docstring literally says "the harness MUST be able to conclude 'kill' — that
is the whole point," which is a verification/decision tool for a physics feature,
not a code path any board goes through in production placement or routing.

## Process notes

- No Rust code was written; `packages/temper-quality-oracle` is unchanged by this
  branch, so no build was run (nothing to compile). `df -g /Users/bennet` before
  starting: 414 GB free (96% used but 19 GB free is the reported free-space column;
  well above the 8 GB floor either way), rechecked after the (no-op) build step —
  unchanged, since no build ran.
- Nothing was deleted. Both files are live (real test coverage, no zero-importer
  members found), so the "verify no test exists solely to exercise it" / "regen
  derived artifacts" / "confirm suites pass" deletion checklist does not apply here
  — there is no deletion in this PR.
- Not independently re-run: the pre-existing failures called out as expected
  (2 in `test_via_layer_properties_pbt.py`, 5 in `tests/validation/`) were not
  re-verified against this worktree's HEAD; this triage made no code changes that
  could affect them, so they were left alone per instructions rather than re-run to
  confirm the exact count.
- `docs/wave4-verdicts.yaml`, `power_pcb_dataset/drc_ceiling.json`, and all
  measurement baselines were not touched.
