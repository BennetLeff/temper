---
title: "Three type/import bugs left the deterministic placer pipeline unrunnable on any board"
date: "2026-07-15"
category: logic-errors
module: temper-placer
problem_type: logic_error
component: tooling
symptoms:
  - "AttributeError: 'str' object has no attribute 'name' in deterministic/stages/setup.py's net_class_setup"
  - "AttributeError: 'list' object has no attribute 'get' in PlacementValidationStage, masked by a `# type: ignore[arg-type]` at the call site"
  - "NameError: name 'field' is not defined in validation/drc_runner.py at class-definition time"
  - "temper_placer.regression.cli run-corpus fails for every corpus board (confirmed on the untouched 'minimal' board) with 'LossContext.from_netlist_and_board removed (JAX retirement)'"
root_cause: logic_error
resolution_type: code_fix
severity: high
tags: [placer, deterministic-pipeline, jax-retirement, type-mismatch, corpus-regression, stub-rot]
---

# Three type/import bugs left the deterministic placer pipeline unrunnable on any board

## Problem

`temper_placer.deterministic.create_drc_aware_pipeline()` — the current, real placement pipeline that replaced the JAX-based optimizer — could not complete an end-to-end run against **any** board, not just a new one. Three independent type/import bugs, each in a different stage, each masking or crashing on the next call, meant nobody had actually exercised the full 22-stage pipeline since whatever refactor introduced them.

This surfaced while trying to re-benchmark the placer against a new production board (unrelated feature work): the corpus regression runner (`make regression` / `temper_placer.regression.cli run-corpus`) failed immediately, and tracing why led through the deterministic pipeline instead of a quick baseline regeneration.

## Symptoms

- `cargo`/`pytest`-adjacent smoke test of the pipeline crashed at stage 11 (`drc_oracle_setup`) with `AttributeError: 'str' object has no attribute 'name'`.
- After fixing that, crashed at stage 10 (`placement_validation`) with `AttributeError: 'list' object has no attribute 'get'`.
- A completely separate test (`test_setup_stage`) failed at import time with `NameError: name 'field' is not defined`, unrelated to the first two bugs but discovered in the same sweep.
- `temper_placer.regression.cli run-corpus --board minimal` (untouched corpus board, unrelated to any of this work) failed with `LossContext.from_netlist_and_board removed (JAX retirement). Use temper_placer.placer.deterministic.PlacementResult instead.` — confirming the regression gate has been silently broken repo-wide, not just for one board.

## What Didn't Work

- Assuming the corpus regression runner (`corpus_runner.py`) was the only broken piece. It imports from `temper_placer.core.loss_types` and defines local stub classes that raise `NotImplementedError("JAX losses removed.")` — a deliberate, planned outcome of `docs/plans/2026-07-05-001-feat-jax-retirement-production-rollback-plan.md` ("remove JAX imports... or is quarantined if dependent"). Porting `corpus_runner.py` itself would not have produced a working baseline, because the pipeline it should have called (`create_drc_aware_pipeline`) had its own, unrelated bugs.
- Assuming the *old* `TopologicalStage`/`GeometricStage` DAG pipeline (`temper_placer.pipeline.stages.*`) was the current production path. Its `legalize_zone_aware` is also a JAX-retirement stub (`raise NotImplementedError`), and `GeometricStage`'s docstring claims "CP-SAT placement dispatch" but its body never actually invokes CP-SAT — it just passes through positions from the (also-stubbed) topological phase. This pipeline is not the currently-exercised path; `temper_placer.deterministic.create_drc_aware_pipeline()` is.

## Solution

Three independent one-line-class fixes, found by running the pipeline stage-by-stage against a real board and reading each traceback back to its source:

**1. `deterministic/stages/setup.py` — wrong attribute access on an already-plain string:**

```python
# Before
for net, class_name in self.design_rules.net_classes.items():
    matrix.set_net_class(net, class_name.name)

# After
for net, class_name in self.design_rules.net_classes.items():
    matrix.set_net_class(net, class_name)
```

`net_classes` is `dict[str, str]` everywhere it's populated (`config_loader.py` reads it straight from YAML: `constraints.net_classes = config["net_classes"]`). The sibling `else` branch two lines down already treated the equivalent value as a plain string with no `.name` access — the two branches had simply drifted apart.

**2. `deterministic/stages/placement_validation.py` — constructor default type didn't match the class's own usage:**

```python
# Before
def __init__(self, constraints: list | None = None, ...):
    self.constraints = constraints or []
...
def _get_proximity_constraints(self):
    return self.constraints.get("placement_proximity", [])  # dict-only API

# After
def __init__(self, constraints: dict | None = None, ...):
    self.constraints = constraints or {}
```

The real call site (`deterministic/__init__.py`) always passes a `dict` and had `constraints=placement_constraints,  # type: ignore[arg-type]` — a type-checker suppression sitting directly on top of the bug, rather than a fix. Removed the now-unneeded `# type: ignore` once the annotation matched reality.

**3. `validation/drc_runner.py` — missing import:**

```python
# Before
from dataclasses import dataclass as _dataclass
...
class CheckRunner:
    checks: list[_Check] = field(default_factory=list)  # field never imported

# After
from dataclasses import dataclass as _dataclass
from dataclasses import field
```

## Why This Works

All three are the same shape: a value's *actual* runtime type (plain string, dict, a stdlib symbol) had drifted from what a specific call site assumed, and nothing caught it because the pipeline had not been run end-to-end since whatever change introduced the drift. None of the three bugs are related to each other in cause — they just compounded in the same code path because nothing was exercising that path.

## Prevention

- **Run the full pipeline, not just its unit tests, after a refactor that touches shared types** (`net_classes`, constraint containers). `packages/temper-placer/tests/deterministic/` was 306/309 green the whole time these three bugs existed — the unit tests mock or bypass the exact seams where the type drift lived. An end-to-end smoke test against a real board (even the small quarantined fixture) would have caught all three immediately.
- **Treat `# type: ignore[arg-type]` on a call site as a bug report, not a suppression.** The `placement_validation.py` bug was already flagged by the type checker at the exact call site; the comment silenced it instead of fixing the annotation.
- **A stubbed function that raises `NotImplementedError` is a live regression risk, not a closed one**, if anything still calls it in a path a CI gate is supposed to cover. `corpus_runner.py`'s JAX-retirement stubs mean `make regression` currently passes 0 real boards and fails closed for all of them — but nothing in CI currently runs `make regression` and fails the build on it, so this has been silently broken with no alert. If a corpus/regression gate is meant to be load-bearing, it needs a CI step that treats "0 boards passed" as a build failure, not merely a script that can be run manually.

## Related Issues

- `docs/plans/2026-07-05-001-feat-jax-retirement-production-rollback-plan.md` — the refactor that intentionally stubbed `corpus_runner.py`; its own stated success criterion ("regression corpus runner works without JAX, or is quarantined if dependent") landed on the quarantine branch, and follow-through to a working port never happened.
- `docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md` — a related, earlier case of the same corpus-baseline machinery silently producing wrong or non-functional results with no gate catching it.
- `docs/plans/2026-07-15-001-feat-artifact-identity-provenance-plan.md`, unit U6 — the re-benchmarking task that surfaced this; still blocked on a separate, deeper gap (see the handoff note in that plan) where `zone_aware_slot_generation`/`component_assignment` produce zero placements for a ~100-component board with no zone-defining config.

### Fifth bug: polygon board outlines invisible to bbox parser (2026-07-15)

`_extract_board_geometry` in `kicad_parser.py` only consumed Edge.Cuts
items with `start`/`end` attributes (`gr_rect`, `gr_line`). The generated
production board's outline is a `gr_poly` with a `coordinates` list. The
bounding-box loop skipped it entirely, producing `-inf` for width/height.

The `-inf` propagated through every downstream stage: component positions,
zone geometry fallback bounds, slot grid generation, and KD-tree pad centers.
Because `edge_cuts` was non-empty (the `gr_poly` exists on the Edge.Cuts
layer), the "No Edge.Cuts found → use default" guard never fired.

**Fix**: Extend the bbox loop to consume `GrPoly.coordinates` and
`GrArc.start/mid/end`. Add a non-finite guard that falls back to
`Board.temper_default()` when no coordinates were consumed.

**Prevention smoke test**: `tests/io/test_production_board_smoke.py` —
asserts finite bbox, component count >= 80, all positions finite, and
no unexpected fallback warnings. Run on every push that touches the parser.

This is the **fourth** bug the missing end-to-end smoke test would have
caught at parse time. The smoke test now exists.
