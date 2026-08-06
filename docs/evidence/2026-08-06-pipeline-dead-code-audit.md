# `pipeline/` audit: one dead module removed, one live bug found

**Date:** 2026-08-06
**Trigger:** a Wave-4 dispatch to migrate `pipeline/`'s numpy compute to Rust.
The port was **not** done — the compute turned out to be dead, duplicate, or
glue. Auditing *why* turned up a live defect that matters more than the port
would have.

## What was removed

`packages/temper-placer/src/temper_placer/pipeline/topology_phase.py` (133 LOC).

Zero references anywhere — `.py`, `.yaml`, `.json`, `.toml`, `.md`, and
critically **not** in `packages/temper-placer/configs/pipeline_default.yaml`,
which is the one place a module can be referenced without appearing in an
`import` (see below). Its three functions duplicate the live, already-migrated
implementations:

| dead copy | live implementation | status |
|---|---|---|
| `build_topological_graph` | `topological/graph.py:319` | Rust-backed, oracle pinned |
| `generate_initial_placement` | `topological/initial_placement.py:183` | Rust-backed, oracle pinned |

The live pair is consumed by `heuristics/topological_init.py` and covered by
`tests/topological/test_topological_rust_differential.py` — **443 passing**.
Porting the dead copy would have produced a second Rust kernel for code with
no callers.

## The live bug — `legalize_zone_aware` raises inside a scheduled stage

The JAX retirement replaced `legalize_zone_aware` with a local stub that
unconditionally raises, in **two** places:

```
pipeline/topological.py:59              def legalize_zone_aware(*a, **kw):
pipeline/stages/topological_stage.py:52     raise NotImplementedError(
                                                "legalize_zone_aware removed (JAX retirement)")
```

Both then *call* that stub a few lines later. `TopologicalStage` is **not dead
code**: `configs/pipeline_default.yaml:20` schedules it and
`pipeline/dag_engine.py:346` loads it dynamically via `importlib`, so it has no
static importer and greps clean.

```yaml
- name: topological
  handler: temper_placer.pipeline.stages.topological_stage.TopologicalStage
  requires: [board, netlist, constraints]
  provides: [deterministic_result]
  skip_if: "config.skip_topological == true"
```

The consequence is a closed trap:

* If the stage **runs**, it raises `NotImplementedError` from a stub.
* If it is **skipped** (`skip_topological`), it never provides
  `deterministic_result` — and the `geometric` stage requires it. That stage's
  fallback (`stages/geometric_stage.py:20`) imports
  `pipeline.topological.run_topological_phase`, which contains the *same*
  raising stub.

So the DAG path fails either way, and the error names JAX retirement rather
than the missing legalizer — misleading whoever hits it first.

**Not fixed here**, deliberately: repairing it means either restoring a
zone-aware legalizer or redesigning the stage's contract, which is a design
decision, not cleanup. Recorded so it is found before someone debugs the
symptom.

## Left in place, and why

* `pipeline/stages/topological_stage.py` — **live** in the DAG config. Deleting
  it on the "no importers" signal would have broken the pipeline. This is the
  audit's main near-miss.
* `pipeline/topological.py` — reachable only from `geometric_stage`'s fallback,
  which is already broken as above. Its fate belongs with that fix.
* `pipeline/feedback.py` (468 LOC) — `run_feedback_loop`, `FeedbackGenerator`
  and `compute_min_loop_area` have no callers outside `pipeline/__init__.py`'s
  re-exports. `compute_min_loop_area` (shoelace, `np.dot`/`np.roll`) also
  duplicates `temper-geometry/src/polygon.rs`'s `polygon_area` /
  `polygon_signed_area` / `compute_loop_area`, which is live via
  `temper_placer/geometry/polygon.py`. Left because deleting it changes
  `temper_placer.pipeline`'s public surface.

  Note the name collision that makes this look live: `scripts/run_feedback_loop.py`
  imports `temper_placer.deterministic.feedback`, **not**
  `temper_placer.pipeline.feedback`.
* `pipeline/iterator.py` — loop-control glue; imports `NDArray` for type hints
  and calls zero numpy functions.

## Method note

"No importers" is not sufficient evidence that a module is dead in this repo.
`dag_engine.py` resolves handlers by dotted string from
`configs/pipeline_default.yaml`, so a scheduled stage has no static reference.
Any dead-code sweep here must grep the DAG config as well as the source.

Tests were not run locally for the deletion: the installed extensions in this
checkout are stale relative to `main` (`temper_drc_rs` has no attribute
`ComponentPlacement`), and rebuilding five crates was disproportionate for
removing a file with no references. CI rebuilds them.
