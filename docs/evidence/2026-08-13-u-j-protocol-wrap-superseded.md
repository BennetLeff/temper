<!-- provenance: commit=ca436efc4e2b6f3b50c1404e9bd1dfcff1f5bf08 dirty=UNKNOWN -->

# U-J (Protocol wrap) is superseded — the Rust pipeline executor already exists; the residual Python is the plan's own R-B JUSTIFIED-KEEP surface

**Date:** 2026-08-13
**Type:** plan-unit resolution (superseded-by-prior-units, R-B-consistent)

## The unit

The orchestration-port program's final unit, "U-J — Protocol wrap": wrap the
Rust orchestration behind the `protocol.py` Protocol-compat layer, keeping
the Python structural-typing surface intact while the compute is Rust. The
intended deliverable was "the run-loop machinery (`resolve_and_run`-style
sequencing) + the adapter marshalling" in Rust, with the Protocol ABCs + the
`isinstance`/`getattr` schema checks staying Python.

## Why it is superseded, not deferred

The portable content U-J was scoped to already landed in prior units
(U-A→U-I + O-C3/U0–U6):

1. **The Rust pipeline executor exists.** `packages/temper-orchestration/src/deterministic_pipeline.rs`
   (972 LOC) implements `run_pipeline` (line 282) and
   `DeterministicPipeline::run` (line 745) — the `Box<dyn Stage<BoardState>>`
   sequencing the plan's R-B specification calls for ("The Rust `PipelineRunner`
   sequences `Box<dyn Stage<BoardState>>` instances"). It carries native
   proptests (commit `61ef591df`).
2. **The adapters already wrap Rust stages for the structural-typing
   consumers.** `adapters/deterministic_adapter.py` (`_WrappedDeterministicStage`)
   marshals `StageInput.data` (a `BoardState`) into the Rust deterministic
   stage and back — the marshalling itself is the U0 `marshal.rs`
   `to_owned`/`to_python` boundary, already in Rust. `adapters/register_strategies.py`
   is the name→factory registry: pure glue, no compute.
3. **`protocol.py` is the plan's own recorded JUSTIFIED-KEEP.** R-B (plan
   `docs/plans/2026-08-09-001-feat-rust-orchestration-engine-plan.md`
   lines 939–955) names the `@runtime_checkable Protocol` layer "a typing
   construct, not runtime data — no pyclass mapping" and instructs the
   orchestration migration not to touch it.

The residual Python surface is therefore exactly the R-B-kept slice: the
`@runtime_checkable Protocol` ABCs + schema checks (`protocol.py`,
`_validate_schema`) and the thin sequence loop (`runner.py`'s
`PipelineRunner.run` — check contract, `stage.run(inp)`, time it, forward
`meta.timings`). Porting that loop to Rust would either duplicate the
already-landed `run_pipeline` or call the same Python stage objects from
Rust — zero compute moved, plus a new pyo3 surface to maintain.

## What was proven by attempting it

Three dispatch attempts (one lost, one hollow, one fabricated) produced no
commits and no Rust module. The closure came from reading the actual code
against the plan's own R-B: the gap U-J was scoped to close does not exist —
the compute under the Protocol-compat surface is already Rust. This is the
same resolution class as the R7 JUSTIFIED-KEEP for `_constraint_types/`
(`docs/evidence/2026-08-11-r7-constraint-types-resolution.md`): an honest
"no port needed," recorded rather than a port performed for completeness.

## Residual risk

None beyond R-B's already-recorded one: the Python structural-typing
consumers (e.g. `regression/closure_test.py`, the strategy-registry path)
keep the thin Python loop, and its wall-clock `meta.timings` are
non-deterministic Python-side data. That is a pre-existing, R-B-accepted
property of the kept surface, unchanged by this resolution.