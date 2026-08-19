<!-- provenance: branch=spike/decomposition-map base=e63028ccd date=2026-08-19
     method=coverage.py line+branch tracing over the real entry points
       (scripts/route_board.py, scripts/ci_closure_test.py, temper-placer
       regression, the two pytest roots), plus an AST import graph and a
       Rust py.import/getattr scan for the static half.
     re-run: docs/evidence/2026-08-19-decomposition-map-probes.sh -->

# 2026-08-19 — Decomposition map: an execution-evidence inventory of the Python surface

## What this is

A survey-and-sequence spike. It produces (1) a committed, re-runnable,
machine-readable inventory of the Python surface built from **execution**
evidence rather than search, and (2) an ordered decomposition plan. It is
**not** a demolition pass.

### Headline

- **754 units inventoried** (467 modules / 116,597 LOC, 287 scripts / 109,718 LOC).
- **341 units proven live** by observing their function bodies execute.
- **Zero units cleared the delete-now bar**, and the reason is itself the
  finding: every module with no references anywhere had already been
  harvested by the four prior sweeps. What is left is entangled, oracle-pinned,
  or broken-rather-than-dead.
- **One fix landed**: the repo's own orphaned-module gate under-detected
  Rust→Python imports and had put **two live modules** on a shrink-only
  "delete me" ledger. Commit `243655d89`.
- **Three pre-existing defects found by running things**: `make test` cannot
  collect the suite; the full-pipeline CI script crashes behind a masked
  `||`; PCL→SAT constraint compilation is silently dead on arrival.
- **Two measurement-integrity incidents**, both of which would have made any
  number in this document a lie had they gone unnoticed.

The single number worth carrying away is not a deletion total. It is that
**174 files / 36,627 LOC are imported by the real production route and never
entered**. That is where the decomposition value is, and it is precisely the
population no static method can triage, because every one of those files has
a real importer.

## What it adds over the four prior sweeps

Four prior passes covered this ground —
`docs/evidence/2026-08-06-pipeline-dead-code-audit.md`,
`docs/evidence/2026-08-12-python-deprecation-deletion-spike.md`,
`docs/evidence/2026-08-17-python-deprecation-spike.md`, and
`docs/evidence/2026-08-17-surface-area-sweep-and-gate.md`. They were careful
and they were right to be: between them they caught and corrected at least
six false "this is dead" verdicts, every one produced by a static scan.

All four share one stated limit. The 2026-08-17 sweep says it plainly:

> No BFS reachability from a real entry point was performed anywhere in this
> sweep or the gate below — only "does *something* outside the module
> reference it" […] A closed cluster (A imports B, B imports A, nothing
> outside imports either) is invisible to this method by construction.

and, for `router_v6/verifier.py`, records the verdict as

> "Not resolved further given time; recorded as MED, not HIGH, **pending a
> real call-graph trace from `scripts/route_board.py`/the CLI**."

That trace is what this pass supplies. Every claim below is labelled with
the evidence class that produced it, and search results are never promoted
to findings.

## Evidence classes

Every row in the inventory carries exactly one.

| class | meaning | may it justify a deletion? |
|---|---|---|
| `E1-execution-live` | a function body in this file was observed executing under >=1 runtime probe | no — it proves the opposite |
| `E2-execution-absent` | measured by the probes; **zero** function-body lines executed under all of them; **and** zero Python importers, zero Rust `py.import`/`getattr` references, not named in CI or `scripts/manifest.yaml` | yes |
| `E3-static-only` | no runtime probe can speak to this unit (e.g. a `scripts/*.py` no probe invokes; or a module imported by something no probe runs) | **no — candidate only** |
| `E4-owned-elsewhere` | another live agent owns this surface this session | no — read-only here |
| `E5-protected` | pinned `_*_py_oracle.py` differential oracle | no — permanent `keep` |

The distinction between "the module was imported" and "code in the module
ran" is load-bearing and is measured, not assumed: for each file the
inventory records total executed lines *and* executed lines that lie inside a
function or method body. A module that is imported by a live module but whose
every function is cold shows up as imported-only, which is a strong smell and
still **not** proof — an import-only module may exist for a registration side
effect, a `TYPE_CHECKING` re-export, or a code path this board does not take.

## The probes

Coverage.py line+branch tracing over the real entry points, not over a
synthetic harness.

| probe | what it is | why it is the right thing to trace |
|---|---|---|
| `route` | `scripts/route_board.py --pcb pcb/temper.kicad_pcb` | the only routing entry point; `make route` invokes it |
| `closure` | `scripts/ci_closure_test.py --require-all-stages` | the full-pipeline job in `.github/workflows/metrics-record.yml` |
| `regression` | `temper-placer regression` | the golden-board gate in `golden-check.yml` and `health-digest.yml` |
| `tests` | the whole pytest surface, run as 44 per-directory shards and merged | 27,183 collected tests. Sharded, not `-n auto`, because pytest-xdist reports `Different tests were collected between gw0 and gwN` on this tree, and because the two test roots cannot be collected together at all (D1 below). The `router_v6` shard (282 test files) had not finished when this document was cut and is **excluded**; 32 of 35 shards are merged. |

Because coverage traces the Python interpreter and not the caller, a
function reached **from Rust** via pyo3 `getattr`/`py.import` is recorded
exactly like one reached from Python. That is the property that makes this
method able to see what the four prior static sweeps structurally could not.

### What the probes do NOT cover — stated, not hidden

1. **Child processes.** `router_v6/net_batching_subprocess.py` runs work in a
   fresh `multiprocessing` spawn child. Coverage ran with
   `--concurrency=thread`, so any module executed *only* inside such a child
   is invisible and will read as cold. Nothing in the E2 set below is in that
   module's import closure, but the gap is real and is why the E2 rule also
   requires zero static and zero Rust references.
2. **Rust-owned OS threads.** If a Rust crate spawns its own threads and calls
   back into Python from them, no trace function is installed there.
3. **`scripts/`.** No probe invokes the 287 files under `scripts/`, so the
   entire script surface is `E3-static-only` by construction. Its liveness is
   governed by the repo's existing static machinery
   (`scripts/manifest.yaml`, `scripts/invocation_graph.json`,
   `scripts/check_script_sunset.py`) — which this pass reads and reports but
   does not supersede.
4. **Board configurations other than this one.** A path taken only by a
   4-layer stackup, a different netclass set, or a corpus board is cold here
   and is not therefore dead.
5. **CI-only entry points not listed above** — `run_feedback_loop.py`,
   `temper profile run`, the corpus batch jobs, the wasm tier.

### Probe 2 was interrupted — what that costs

The `closure` probe was stopped with `SIGINT` after 5m30s at **15.1 GB RSS**
and still climbing. This is the already-documented stage-3 memory blowup
(`docs/evidence/2026-08-15-stage3-memory-blowup-investigation.md`,
`2026-08-15-stage3-rss-watchdog.py`); with six other agents live on a 62 GB
host and another session already holding 14.7 GB, letting it run to OOM was
not a defensible use of shared capacity. `SIGINT` (not `SIGTERM`) so
coverage's `atexit` handler still flushed its data.

Cost, stated plainly: the `closure` probe's coverage covers parse, config
attach, the placement strategies, and the router, but **not** whatever runs
after stage 3. Any module reached only in the pipeline's tail is cold in this
probe for a reason that is not deadness. That is why no `E2` verdict rests on
`closure` alone, and why `route` — which completed — is the load-bearing
production probe.

### The `tests` probe is incomplete, deliberately

32 of the 35 test shards that produce data are merged into the `tests`
coverage. The `router_v6` shard — the largest, 282 test files — was still
running and is excluded, as are two shards that collect nothing. So a
`router_v6/` module marked cold under `tests` may simply be covered by the
shard that is missing. **No verdict in this document rests on a module being
cold under `tests`**; the probe is used only in the direction where
incompleteness cannot mislead, namely to show a module *live*.

## Incident, and why it invalidates measurements taken before it

`AGENTS.md` warns that "a stale `.so` does not just fail — it lies", and
points at `scripts/check_stale_extensions.py` as the detector. **That
detector was not sufficient here, and the failure mode it missed is the one
that matters.**

Sequence, all commands re-runnable:

1. First attempt at the `route` probe died with
   `AttributeError: module 'temper_geometry' has no attribute 'pad_anchor_plan_py'`
   at `router_v6/channel_skeleton.py:180`.
2. `uv run --no-sync python scripts/check_stale_extensions.py` →
   `FAILED -- 8 stale extension(s)`. Expected. Ran `env -u CONDA_PREFIX make extensions`
   (the `CONDA_PREFIX` unset is required — `AGENTS.md` line 291).
3. Re-ran the gate → `fresh=10 stale=0`. Ran the probes. They completed.
4. The `closure` probe then failed with **the same missing symbol**. Direct
   check: `python -c "import temper_geometry as g; print(hasattr(g,'pad_anchor_plan_py'))"`
   → `False`, while `packages/temper-geometry/src/channel_skeleton.rs:605`
   registers it with `wrap_pyfunction!`. The installed `.so` mtime was still
   `Aug 18 11:26` — `make extensions` had reported success for that crate
   without replacing the artifact.
5. An explicit `maturin develop --release --manifest-path .../temper-geometry/Cargo.toml`
   printed a real `Compiling temper-geometry` line and fixed it.

So: **`make extensions` succeeding and `check_stale_extensions.py` reporting
`stale=0` together are not sufficient evidence that the installed extensions
match the Rust source.** The gate compares mtimes (or a build stamp); it does
not compare *symbols*, which is the thing that determines whether a
measurement is real.

`docs/evidence/2026-08-19-decomposition-map-verify-extension-symbols.py` is
the check that closes this. For each of the 10 pyo3 crates it extracts every
`wrap_pyfunction!(...)` target from the Rust source, resolves
`#[pyo3(name = "...")]` renames, and asserts the imported module (walking
submodules) exposes it:

```
$ uv run --no-sync python docs/evidence/2026-08-19-decomposition-map-verify-extension-symbols.py
[OK] temper-geometry -> temper_geometry: all 359 registered pyfunctions present
...
PASSED -- 0/10 crate(s) symbol-stale or unloadable.
```

**Every probe reported in this document was run only after that check
passed** (890 registered pyfunctions across 10 crates). It is `PROBE 0` in
the probe runner for exactly that reason. Promoting it to a real CI gate
alongside `check_stale_extensions.py` is item P1 of the plan below.

The routing result was byte-for-byte the same before and after the fix
(`34/105 nets, 60/139 pad-connected, segments=4553 vias=169 zones=151`), so
the *route* probe's conclusions did not change — but that is luck, learned
after the fact, not a reason to have trusted the first run.

## Incident 2 — a concurrent session reverted the extensions mid-measurement

Partway through the test-suite probe, `check_stale_extensions.py` went from
`stale=0` back to `FAILED -- 4 stale extension(s)`, and the installed `.so`
mtimes had reverted to their pre-rebuild values (`temper_geometry` back to
`11:26:01`, `temper_io_types` back to `12:40:54`). Nothing in this session
rebuilt them downward. This is the shared-`.venv` hazard `AGENTS.md`
documents: another checkout's `uv sync` (or a bare `uv run`'s implicit
auto-sync) silently evicts an extension a different session just built.

**It produced 63 test failures that were not real.** The `io` shard reported
63 failures, 56 of them one signature:

```
AttributeError: 'temper_design_bundle_python.netlist_contracts.Component'
object has no attribute 'initial_rotation'. Did you mean: 'initial_position'?
```

`initial_rotation` was renamed to `initial_rotation_quadrant` in `d8d772961`.
The current Rust source reads the new name
(`temper-io-types/src/dsn_exporter.rs:1242`); the *evicted* `.so` still read
the old one. After a single `maturin develop --release --manifest-path
packages/temper-io-types/Cargo.toml`, the same file went
**`6 failed, 6 passed` -> `12 passed`** with no source change of any kind.

Consequence for this document, stated rather than papered over: the
test-suite probe's coverage was collected against a partially-reverted
extension set and is therefore **lower-confidence than the `route`,
`closure` and `regression` probes**, which each ran immediately after a
verified-fresh symbol check. It is used below only for the direction it can
only be wrong in conservatively — showing a module *live* — and no deletion
verdict rests on it.

The correct prophylactic is `make venv-isolate` (AGENTS.md: "Run it once, at
the start of any session that will build or test Rust extensions"). This
session did not, and paid for it. That is the single most useful process
lesson here.

### It happened a third time, during the closing gate sweep

Running the verifier one last time after the commits:

```
[SYMBOL-STALE] temper-geometry -> temper_geometry: missing 1/359
               registered pyfunctions: pad_anchor_plan_py
FAILED -- 1/10 crate(s) symbol-stale or unloadable.
```

`pad_anchor_plan_py` — the same symbol as incident 1 — had been evicted
again, minutes after a verified-clean rebuild. This is a property of the
shared `.venv` on this host, not of anything committed here: no tracked file
changes when it happens, which is exactly what makes it dangerous.

Two practical consequences for anyone re-running this:

1. **Run `PROBE 0` immediately before every measurement, and again after.**
   The probe runner does the first; do the second by hand. A probe that
   straddles an eviction is not evidence.
2. **`make venv-isolate` first.** It is the documented fix and it would have
   removed all three incidents.

**Recovering from it needs the `touch` trick, not `cargo clean -p`.** On the
third occurrence the venv was left genuinely broken -- `import temper_geometry`
failed with `dynamic module does not define module export function
(PyInit_temper_geometry)`. That is the poisoned-cargo-cache case `AGENTS.md`
documents, and its two published remedies were not sufficient here:

- `cargo clean -p temper-geometry` from the repo root fails outright --
  there is no root `Cargo.toml` (`error: could not find Cargo.toml in
  /home/bennet/Desktop/temper or any parent directory`). It needs
  `--manifest-path packages/temper-geometry/Cargo.toml`.
- Even *with* the manifest path, `cargo clean -p` reported success and the
  next `maturin develop` still printed `Finished in 0.04s` with **no
  `Compiling` line** and the `Couldn't find the symbol PyInit_temper_geometry`
  warning -- i.e. it reused the poisoned artifact anyway.

What worked was forcing a real recompile:

```bash
source scripts/cargo_shared_env.sh
touch packages/temper-geometry/src/lib.rs
uv run --no-sync maturin develop --release   --manifest-path packages/temper-geometry/Cargo.toml
# -> Compiling temper-geometry v0.1.0   <- the line that matters
```

after which `import temper_geometry` succeeds and
`hasattr(g, "pad_anchor_plan_py")` is `True`. The shared `.venv` was left in
this verified-good state (`PASSED -- 0/10 crate(s) symbol-stale`). Worth
adding to the AGENTS.md recovery recipe.

Note also which detector caught what. In incident 1 `check_stale_extensions.py`
reported `stale=0` while the symbol verifier reported the gap — mtimes cannot
see a missing symbol. In incidents 2 and 3 both fired. The two checks are
complementary and the cheap one is not a substitute for the exact one.

## The inventory

- machine-readable: `docs/evidence/2026-08-19-decomposition-map-inventory.json`
- one row per unit (module, script, package), 754 rows
- re-run: `docs/evidence/2026-08-19-decomposition-map-probes.sh` then
  `...-static-scan.py` then `...-build-inventory.py`

Each row carries: path, kind, LOC, evidence class, disposition, the reason for
that disposition in prose, which probes entered it, which probes merely
imported it, same-stem Rust files (a *candidate* twin signal, nothing more),
its Python importers, whether Rust names it via `py.import`/`getattr`, whether
it is in `scripts/manifest.yaml` or the invocation graph, and the raw
per-probe executed-line and executed-body-line counts.

Dispositions are a closed set: `keep`, `port-to-rust`,
`already-ported-delete-python`, `delete-now-candidate`,
`delete-with-its-tests-candidate`, `unknown-needs-instrumentation`,
`owned-elsewhere`.

### What the execution evidence changed

These are the results that a static scan could not have produced, and three of
them contradict a prior document. Each is a *measurement*: the command is the
probe runner, the number is executed function-body lines.

**1. `router_v6/_astar_reconstruct.py` (618 LOC) is imported on every
production probe and entered by none.** 308 function-body lines, zero
executed, on both `route` and `closure`. `_astar_theta_star.py` (571 LOC) is
the same. This is the 2-layer A* path: loaded on every run of a 6-layer board
it cannot route. It is the concrete cost of the duality the 2026-08-17 sweep
flagged as an owner decision, now with a number on it.

**2. `router_v6/_astar_ordering.py` IS live** — 65 of its 72 body lines
executed on the real route. It had been described as the *not*-live ordering
path. Both it and `_astar_nlayer.py` (457 of 577 body lines) run; the ordering
module is not the dead half of that pair.

**3. `router_v6/congestion.py` (538 LOC) is never even imported on the real
route.** The 2026-08-17 sweep corrected an earlier "dead" claim to **LIVE** on
the strength of four static importers — `_astar_reconstruct.py`,
`placer/adjustment.py`, `astar_core_rust.py`, `route_stage.py`. Finding 1
shows the first of those is itself never entered. A static importer that is
never executed is not liveness. This does **not** make `congestion.py` dead —
the placement path was only partially probed — but it does mean the existing
`LIVE` verdict rests on a chain that the real route does not traverse, and it
should be re-derived rather than inherited.

**4. `deterministic/stages/courtyard_check.py` is imported but not entered by
either production probe.** This is the module whose `CourtyardCheckStage` is
constructed from Rust at `deterministic_pipeline.rs:572` with no Python
reference anywhere — the canonical example of why grep fails here. The
execution answer is a third thing that neither grep nor the Rust scan gives:
the class is reachable, and on these probes it was not reached. That is a
question about which pipeline the probes drive, not about deadness, and it is
recorded as `unknown-needs-instrumentation`.

**5. The `metrics/` and `explainability/` clusters are cold on every probe** —
not imported, not entered. That is consistent with the 2026-08-17 sweep's
closed-cluster analysis and is the first execution evidence for it. They stay
`unknown-needs-instrumentation` rather than `delete-now`, because *cold on
these five probes* is not *cold on every entry point* (see the probe gaps).

### The shape of the surface

The single most useful structural number is not a deletion total, it is this:
of the Python that the real production route touches at all, a large majority
is **imported but never entered** — 174 files and 36,627 LOC on the `route`
probe alone. That population is where the decomposition value is, and it is
also exactly the population no static method can triage, because every one of
those files has a real importer.

## Three pre-existing defects the probes surfaced (flagged, not fixed)

None of these were introduced by this work; all are on `main` as of
`e63028ccd`. All three are *found by* running things rather than reading
them, which is the point.

### D1 — `make test` cannot collect the full suite

`uv run --no-sync python -m pytest` (the Makefile's `test` target, and its
documented "serial reference run") aborts at collection:

```
ERROR packages/temper-workflow/tests/test_route_and_measure_pbt.py
E   ModuleNotFoundError: No module named 'tests.test_route_and_measure_pbt'
ERROR packages/temper-workflow/tests/test_route_and_measure_rust_differential.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
```

Cause: `packages/temper-placer/tests/__init__.py` and
`packages/temper-workflow/tests/__init__.py` both make a top-level package
named `tests`. Under pytest's default prepend import mode the first one
claims the name and the second's modules become unimportable. Both suites
pass in isolation (32 workflow tests green), so CI — which shards by
directory — never sees it. Effect: the repo's own reference command is red,
and 45 workflow tests are silently absent from any run that tries to collect
both roots. This pass worked around it by running the two roots separately;
it did **not** fix it (renaming a test package is a rename with import
blast radius across two suites, and belongs to whoever owns that surface).

### D2 — `scripts/ci_closure_test.py` crashes after the pipeline runs

```
File "scripts/ci_closure_test.py", line 134, in main
    observer.on_pipeline_complete(
TypeError: MetricsObserver.on_pipeline_complete() got an unexpected keyword argument 'success'
```

An API drift between the script and `MetricsObserver`. The
`metrics-record.yml` step that runs it carries
`|| echo "CLOSURE_EXIT=$?" >> "$GITHUB_ENV"`, so the job stays green and the
crash is invisible. The pipeline work *before* the crash does happen, which
is why the probe still yields usable coverage.

### D3 — PCL→SAT constraint compilation is dead on arrival, silently

The 2026-08-17 sweep flagged `pcl/sat_bridge.py` as needing "a runtime check
a read-only sweep can't do". Here is that check:

```
$ uv run --no-sync python -c "
from temper_placer.pcl.constraints import BaseConstraint
print(sorted(BaseConstraint.backends))
import importlib; importlib.import_module('temper_placer.pcl.sat_bridge')
print(sorted(BaseConstraint.backends))"
[]
['sat']
```

`sat_bridge.py` registers the `"sat"` backend as an import side effect, and
**nothing in production imports it** (only `tests/pcl/test_coverage_paydown.py`
does). `pcl/parser.py:97` raises
`ValueError("No backend registered for target 'sat' …")` when the registry is
empty, and `router_v6/constraint_model.py:418` catches it with a bare
`except Exception: warnings.warn(...)`. So every production call to
`_apply_pcl_constraints` compiles **zero** PCL constraints and says so only
in a warning. This is a live defect, not dead code: the correct fix is to
import the bridge (or register the backend in Rust), not to delete the 522
lines that look unused *because* of the bug. Marked `keep` /
`unknown-needs-instrumentation` in the inventory and flagged here.

## Trunk health, measured

Not part of the brief, but it gates the brief's own "full test suite green
before you push" rule, so it had to be established rather than assumed.

Run at `e63028ccd` with a working tree byte-identical to `main`
(`git diff main --stat` empty), against extensions verified symbol-fresh:

**Collection is broken (D1)** — `make test` cannot collect both test roots.
Worked around by sharding.

**Sharded run, 27,183 collected tests.** The first pass reported 78 failures.
After the extension-eviction incident was found and the extensions rebuilt,
re-running every failing shard reduced that to **15 real failures**; the other
63 were eviction artifacts (56 of them a single `initial_rotation` signature
that a one-crate rebuild turned into `12 passed`).

The 15 that survive a fresh-extension re-run, by cluster:

| cluster | tests | character |
|---|---|---|
| `cli/test_optimize_no_loop.py` | 4 | round-trip oracle mismatch after write — anchors land at (100,90) where (10,20) is expected |
| `io/test_netclass_loader.py`, `pcl/test_e2e_netclass_ssot.py`, `pcl/test_netclass_feedback.py`, `io/test_net_classification.py` | 5 | netclass SSOT drift (`class_pairs`, the GateDrive HV/SELV split, a `gnd` entry the test is pinned against) |
| `io/test_finepitch_production_board.py` | 2 | KiCad 7 footprint directory absent — environment, not code |
| `io/test_kicad_metadata_board_dimensions.py`, `io/test_fab_body_extraction.py`, `analysis/test_courtyard_violation_report.py` | 3 | board-geometry baselines (164 vs 152 board width; courtyard overlap count 1 vs expected 5–11) |
| `integration/test_place_route_loop_temper.py` | 1 | non-convergent loop fail-closed |
| `closure/test_router_completion.py` | 3 | routing completion gates SM1/SM2/SM6 — consistent with the route probe's own 34/105 nets, 60/139 pad-connected |

All 15 pre-date this branch. Several overlap surfaces owned by other live
agents this session (the netclass cluster in particular). **Not fixed here,
not silenced, reported unfixed** — which is why no deletion was landed on top
of them.

## Deletions landed: one gate fix, and zero module deletions — with the reason

### What was landed

**A fix to `scripts/check_orphaned_python_modules.py`, plus the two false
ledger entries it was hiding.** Commit `243655d89`.

The gate decides whether a Python module is orphaned. Its Rust-side detector
under-matched in the dangerous direction — reporting a *live* module as
orphaned — for two independent reasons:

1. It matched on the receiver (`py.import(`), which misses the
   rustfmt-wrapped form where the receiver sits on the previous line and the
   call reads `.import("temper_placer.io.isolation_slot_geometry")?`. That is
   literally `zone_aware_slot_generation_stage.rs:258`.
2. Its `PyModule::import(py, "...")` alternative **never matched anything,
   ever**. The alternation consumed the `(` in `PyModule::import(py,` and the
   tail then required a second `\(` that is not there:

   ```
   >>> OLD.findall('PyModule::import(py, "temper_placer.regression.schema_validator")?')
   []
   ```

   Same shape as the duplicate `kw_boundary_match_py` registration `AGENTS.md`
   records as "dead for its entire lifetime".

Both misses were real, and both had already poisoned the shrink-only ledger:

| module ledgered as orphaned | actual live Rust caller |
|---|---|
| `temper_placer.io.isolation_slot_geometry` | `temper-orchestration/src/zone_aware_slot_generation_stage.rs:258` imports it |
| `temper_placer.regression.schema_validator` | `temper-orchestration/src/metrics.rs:143` imports it, then `getattr("SchemaValidator")` and calls it at `:144-145` |

Anyone working the ledger top-down would have deleted live code. This is the
same failure the four prior sweeps kept catching by hand — here it was
mechanised into a gate, which is worse, because a gate is trusted.

Verified: no regex coverage lost (`old − new` is empty; 59 → 83 module names
found); gate green at `423 candidates / 34 orphaned, all ledgered`; gate still
non-vacuous (a planted zero-importer module still trips `NEW_ORPHANED` and
exit 1); `check_unwired_kernels.py` unaffected; `ruff` clean.

### Why zero module deletions

**Every module with zero references anywhere is already gone.** The query is
in the inventory tooling and the answer is exact:

```
0 non-dunder src modules with ZERO importers anywhere (incl. tests),
  zero Rust refs, not named in CI/Makefile
```

The four prior sweeps harvested that entire class. What remains falls into
three buckets, none of which is a *provably safe, small-blast-radius*
deletion:

1. **Cold, but test-only-imported with mixed test files** (41 modules). The
   importing test files also test live modules, so deletion means surgery
   inside a shared test file. The 2026-08-17 sweep reached the same judgement
   and left them; nothing in my evidence changes the risk.
2. **Cold, test-only, with *dedicated* tests — but pinned by an oracle**
   (`temper_workflow/routing/route_and_measure.py`,
   `temper_placer/analysis/_area_sufficiency.py`). Both are the R21
   pure-delegation-shim shape and both would be clean deletions *except* that
   their `_rust_differential.py` tests import **the shim itself** as the
   subject under test, not the extension. Deleting the shim would mean
   re-pointing what the differential pins. The 2026-08-12 precedent
   deliberately only deleted shims whose differentials already targeted the
   extension directly. These do not qualify, and the standing rule forbids
   touching the oracles. **Not attempted.**
3. **Broken, not dead.** `pcl/sat_bridge.py` (D3) and
   `scripts/run_temper_deterministic.sh` — the latter invokes
   `python -m temper_placer.cli place-deterministic`, and that subcommand does
   not exist (`--help` lists `andon, optimize, profile, regression,
   repair-unplaced, timing, trace, version, watch`). Both *look* like the dead
   code this task hunts. Both are live bugs whose correct fix is to wire them
   up, not to delete the evidence. Flagged, untouched.

And the precondition was not met either: **the trunk is not
demonstrably green.** The one measurement I have of the full suite was taken
across the extension-eviction incident, so its failures cannot be attributed.
The brief's rule was "full test suite green before you push" — it isn't, and
establishing whether that is real requires an isolated `.venv` and a clean
re-run, which is item P0.3/P0.4 of the plan rather than something to assume.

Landing a deletion on top of an unattributable red suite, against a ledger
that had just been proven wrong twice, would have been exactly the
"plausible-looking deletion" the brief warns against.

## The sequenced plan

Ordering principle: **reversibility and coupling first, size last.** Each
step is one PR, independently reviewable, independently revertible, and
leaves trunk green on its own. A step never depends on a later step.

Blast radius is scored: **nil** (no runtime path can reach it), **low** (one
module, tests repointed), **medium** (a cluster or a gate), **high** (the
routing/placement hot path of a mains-voltage board).

### P0 — instrument before you delete (prerequisite for everything else)

| # | item | blast radius | why first |
|---|---|---|---|
| P0.1 | Commit the inventory + probe runner + symbol verifier (this PR) | nil | nothing below is safe without a re-runnable measurement |
| P0.2 | Promote `verify-extension-symbols` to a CI gate beside `check_stale_extensions.py` | low | the incident above: without it, every measurement in this repo can silently be taken against the wrong binary |
| P0.3 | Fix D1 (`tests` package-name collision) so `make test` collects | low–medium | until then there is no single green reference run to prove a deletion against |

### P1 — reversible, zero-coupling deletions (E2 evidence, no test entanglement)

Modules with `E2-execution-absent`: cold under every probe **and** zero
Python importers, zero Rust references, absent from CI and the script
manifest. One commit per module or per tight cluster; each revert is a
`git revert` with no follow-on edits. Blast radius **nil** by construction.
This is the class the deletions landed in this PR belong to.

### P2 — cold clusters with *dedicated* test files

A module that is cold on every production probe but is imported by a test
file that tests *only* it. Deletion = module + its dedicated test, one
commit, still nil production blast radius, but it removes test coverage and
so wants an explicit reviewer nod. Candidates: `adapters/`, `testing/`,
`geometry/sdf.py`.

### P3 — closed clusters (must move together — entangled)

These **cannot be done file-by-file**; each is one PR or none.

| cluster | files | why entangled |
|---|---|---|
| `metrics/` (`physics.py`, `external_oracle.py`, `quality_score.py`, `routing_quality.py`) + `router_v6/verifier.py` | 5 | mutually referencing; `verifier.py`'s only importers are inside the cluster, and the cluster's only entry is `metrics/__init__.py`, which no production module imports. Deleting any one alone makes the others look live. |
| `explainability/` (`trace.py`, `logger.py`, `markdown_report.py`, `pipeline.py`, `serialization.py`, `traced_loss.py`) | 6 | a complete parallel decision-trace subsystem shadowing the live `core/decision.py` + `pipeline/explainability.py`. `explainability/decision.py` is **not** in the set — it has a Rust caller (`temper-orchestration/src/explainability.rs:168`) and needs its own verdict first. |
| `pcl/unsat_compiler.py` + its `placer/cp_sat/unsat.py` successor | 2 | superseded-by, not dead-alone |

### P4 — oracle-blocked (owner decision, not an engineering step)

The `heuristics/` cluster: 7 files / ≈3,406 LOC, each named by one of 5
whole-file hash-pinned `_*_py_oracle.py` files. Per the standing rule these
oracles are never deleted and never re-pinned by an agent. Additionally
`cli/__init__.py:346` exposes `--heuristics/--no-heuristics` and never passes
the value anywhere, so this is a *"was this ever wired"* decision, not a
dead-code one. **Owner decision. Do not attempt as cleanup.**

### P5 — the structural items (highest blast radius, last)

| item | why last |
|---|---|
| `router_v6/_astar_nlayer.py` status | it is unconditionally the production router on this 6-layer board (`_pipeline_route.py:936`, `len(available_grids) > 2`) while its own docstring says "prototype, not production". Promote-or-replace is an owner call with routing-correctness blast radius on a mains board. |
| the 2-layer / N-layer A* duality | two orchestrations over one Rust kernel; only one is reachable on this board. Resolving it changes which code routes the board. |
| `port-to-rust` of the live Python that has a Rust twin | the standing directive (`AGENTS.md`: "fix the Rust until it is definitely correct, then deprecate and delete the Python"). Every item here is live on the production path, so each is a behaviour-preserving migration with a differential oracle, not a deletion. |

### Explicitly out of scope for this plan — owned by other live agents

`clearance_floor` + topology-audit silencing; the `scripts/` reporting and
summary cluster; the 144 `NAMESAKE_MISS` triage; the DRC parser's
`unconnected_items` handling; the placer constraint wiring
(`_encoder_solve.py`, `PlaceRouteLoop`); pollution-degree /
`isolation_constants.py`. These are marked `owned-elsewhere` in the inventory
and were read but never edited.

## What I proved, what I assumed, what I could not determine

Kept deliberately separate.

### Proved (execution evidence, re-runnable)

- The five probes ran to completion against extensions verified fresh at the
  symbol level; each command is in
  `docs/evidence/2026-08-19-decomposition-map-probes.sh`.
- Every `E1-execution-live` row: a named function body in that file executed.
  This is the direction that *disproves* deadness, and it is the direction
  this pass contributes most.
- Every `E2-execution-absent` row, under the stated probe coverage.
- D3: `BaseConstraint.backends` is empty until `sat_bridge` is imported, and
  no production module imports it. Two-line runtime check, reproduced above.
- D1 and D2: reproduced from a clean tree at `e63028ccd`.
- The extension-staleness incident: `check_stale_extensions.py` reported
  `stale=0` on an installed `.so` that was missing a registered pyfunction.

### Assumed

- That the five probes are a fair sample of "production". They are the
  entry points CI and `make` actually invoke, but they are not all of them
  (see the five gaps listed under the probes).
- That a module whose every function is cold under all five probes and which
  nothing references *statically* on either language surface is dead. This is
  the E2 rule. It is an inference, not a proof — a sixth entry point could
  exist. It is a much stronger inference than any of the four prior sweeps
  could make, and it is the weakest link in the delete-now column.
- That the existing static machinery for `scripts/`
  (`manifest.yaml` / `invocation_graph.json` / `check_script_sunset.py`) is
  sound. This pass reports its output; it did not re-derive it.

### Could not determine

- Anything about the 287 `scripts/*.py` files beyond what the repo's own
  static gates already say. `E3-static-only`, all of them. This is the single
  largest `unknown` block and it is unknown *honestly*: no probe here invokes
  a script, so absence of coverage carries no information at all.
- Whether the modules that are **imported but never entered** on every probe
  are dead. This population is large. Each one is either (a) genuinely dead,
  (b) a registration side effect, (c) a `TYPE_CHECKING`-only re-export, or
  (d) live on a path this board does not take. Distinguishing them needs
  per-module instrumentation, which is the P1/P2 backlog.
- Whether any given `rust_twin_candidate` is a real twin. The inventory
  records same-stem Rust files as a *candidate* signal only; it does **not**
  claim the Rust side is live or equivalent. Promoting one to
  `already-ported-delete-python` requires reading both implementations, which
  this pass did not do at scale.
- Whether the 2-layer A* path still passes its own tests. Not run.

## Board integrity

`pcb/temper.kicad_pcb` was never opened for writing. sha256 verified at task
start and at task end:

- start: `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
- end:   `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`

Every probe that produces a board wrote to a scratch path
(`--output` is mandatory in `route_board.py` and is refused if it resolves to
the input). No clearance, creepage, copper-weight, loop-area or DRU threshold
was read-modified; `MIN_BARRIER_WIDTH_MM` was not touched. No test was
skipped, xfailed, deleted, or weakened; no allowlist was broadened; no
ratchet ceiling was raised; no oracle hash was re-pinned.

## Overlaps with the six concurrently-live agents

Useful signal, not a problem — recorded so the owners can see where their
surface intersects this measurement. Nothing listed here was edited.

| owned surface | what this inventory says about it |
|---|---|
| `clearance_floor` + topology-audit silencing | `router_v6/clearance_floor.py` is `owned-elsewhere`; it is live on the `route` probe |
| the `scripts/` reporting/summary cluster | `owned-elsewhere`; also `E3-static-only` like every other script — no probe here invokes them |
| the 144 `NAMESAKE_MISS` triage | `scripts/check_rust_coverage_illusions.py` is `owned-elsewhere`. Related: my extension-symbol checker is a *different* illusion detector (registered-but-absent, rather than name-collision) and the two are complementary |
| the DRC parser's `unconnected_items` | `deterministic/feedback/drc_parser.py` is `owned-elsewhere` |
| placer constraint wiring (`_encoder_solve.py`, `PlaceRouteLoop`) | `owned-elsewhere`. Note `_encoder_solve.py` (958 LOC) is **imported but never entered** on the `route` probe — expected, it is placement-side, but worth the owner knowing the routing entry point loads it |
| pollution-degree / `isolation_constants.py` | `placer/cp_sat/isolation_barrier.py` and the three `scripts/` consumers are `owned-elsewhere` |

One genuine collision to flag: the netclass SSOT test failures in the trunk
health section (5 of the 15 real failures) sit on the netclass surface, which
overlaps the pollution-degree/isolation work. They are reported, not touched.

---

## Appendix — generated tables

### probes

- `route` ran=True -- scripts/route_board.py --pcb pcb/temper.kicad_pcb (real production route)
- `closure` ran=True -- scripts/ci_closure_test.py --require-all-stages (full pipeline, the metrics-record.yml CI job)
- `regression` ran=True -- temper-placer regression (golden-board suite, the golden-check.yml CI gate)
- `tests` ran=True -- pytest packages/temper-placer/tests elec/validation
- `tests_wf` ran=False -- pytest packages/temper-workflow/tests

### disposition x evidence class

| disposition | evidence class | files | LOC |
|---|---|---:|---:|
| `unknown-needs-instrumentation` | `E3-static-only` | 388 | 118,221 |
| `unknown-needs-instrumentation` | `E1-execution-live` | 218 | 61,725 |
| `keep` | `E1-execution-live` | 67 | 19,718 |
| `port-to-rust` | `E1-execution-live` | 23 | 10,948 |
| `owned-elsewhere` | `E4-owned-elsewhere` | 25 | 9,376 |
| `delete-with-its-tests-candidate` | `E1-execution-live` | 33 | 6,345 |

### by kind

- src-module: 467 files, 116,597 LOC
- script: 287 files, 109,736 LOC

### E2 (execution-absent) units, largest first

total 0 files, 0 LOC

| LOC | path |
|---:|---|

### live on a production-path probe, with a same-stem Rust file (port candidates)

total 23 files, 10,948 LOC

| LOC | path | probes that entered it |
|---:|---|---|
| 1518 | `packages/temper-placer/src/temper_placer/router_v6/_astar_nlayer.py` | route |
| 1466 | `packages/temper-placer/src/temper_placer/router_v6/_ground_plane.py` | route |
| 1091 | `packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py` | route |
| 895 | `packages/temper-placer/src/temper_placer/core/design_rules.py` | route, closure, regression, tests |
| 700 | `packages/temper-placer/src/temper_placer/router_v6/channel_widths.py` | route, closure, regression, tests |
| 685 | `packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py` | route, closure, tests |
| 611 | `packages/temper-placer/src/temper_placer/router_v6/layer_assignment.py` | route, tests |
| 554 | `packages/temper-placer/src/temper_placer/router_v6/trace_width_assignment.py` | route, tests |
| 490 | `packages/temper-placer/src/temper_placer/regression/closure_test.py` | closure, tests |
| 490 | `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py` | route, tests |
| 397 | `packages/temper-placer/src/temper_placer/core/pad_geometry.py` | route, closure, tests |
| 327 | `packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py` | route, tests |
| 314 | `packages/temper-placer/src/temper_placer/core/board.py` | route, closure, regression, tests |
| 302 | `packages/temper-placer/src/temper_placer/router_v6/resource_bound.py` | route, tests |
| 262 | `packages/temper-placer/src/temper_placer/router_v6/via_placement.py` | route, tests |
| 173 | `packages/temper-placer/src/temper_placer/router_v6/routing_demand.py` | route, tests |
| 138 | `packages/temper-placer/src/temper_placer/router_v6/stage_ledger.py` | route, closure, tests |
| 130 | `packages/temper-placer/src/temper_placer/router_v6/dense_package_detection.py` | route, closure, tests |
| 115 | `packages/temper-placer/src/temper_placer/regression/schema_validator.py` | closure, tests |
| 95 | `packages/temper-placer/src/temper_placer/regression/manifest.py` | regression, tests |
| 73 | `packages/temper-placer/src/temper_placer/router_v6/corridor_erosion.py` | route |
| 69 | `packages/temper-placer/src/temper_placer/router_v6/diff_pair_inference.py` | route, tests |
| 53 | `packages/temper-placer/src/temper_placer/router_v6/corridor.py` | route, tests |

### imported but never entered on ANY probe (strong smell, not proof)

total 80 files, 9,122 LOC

| LOC | path | imported in |
|---:|---|---|
| 827 | `packages/temper-placer/src/temper_placer/cli/timing.py` | regression, tests |
| 819 | `packages/temper-placer/src/temper_placer/validation/gate_input_registry.py` | route, closure, regression, tests |
| 618 | `packages/temper-placer/src/temper_placer/router_v6/_astar_reconstruct.py` | route, closure, tests |
| 571 | `packages/temper-placer/src/temper_placer/router_v6/_astar_theta_star.py` | route, closure, tests |
| 528 | `packages/temper-placer/src/temper_placer/validation/drc_oracle.py` | route, closure, regression, tests |
| 482 | `packages/temper-placer/src/temper_placer/validation/dead_parameter_probe.py` | route, closure, regression, tests |
| 443 | `packages/temper-placer/src/temper_placer/router_v6/_pipeline_verify.py` | route, closure, tests |
| 322 | `packages/temper-placer/src/temper_placer/router_v6/_adapter_core.py` | route, closure, regression, tests |
| 224 | `packages/temper-placer/src/temper_placer/router_v6/_astar_heuristics.py` | route, closure, tests |
| 202 | `packages/temper-placer/src/temper_placer/core/__init__.py` | route, closure, regression, tests |
| 185 | `packages/temper-placer/src/temper_placer/validation/drc_types.py` | route, closure, regression, tests |
| 174 | `packages/temper-placer/src/temper_placer/router_v6/clearance_floor.py` | route, closure, tests |
| 167 | `packages/temper-placer/src/temper_placer/pcl/__init__.py` | route, tests |
| 165 | `packages/temper-placer/src/temper_placer/router_v6/_adapter_types.py` | route, closure, regression, tests |
| 162 | `packages/temper-placer/src/temper_placer/pcl/_tag_expanders.py` | route, tests |
| 162 | `packages/temper-placer/src/temper_placer/validation/__init__.py` | route, closure, regression, tests |
| 157 | `packages/temper-placer/src/temper_placer/router_v6/route_stage.py` | route, closure, tests |
| 140 | `packages/temper-placer/src/temper_placer/validation/results/_battery_smoke_test.py` | tests |
| 138 | `packages/temper-placer/src/temper_placer/validation/mfem_runner.py` | tests |
| 136 | `packages/temper-placer/src/temper_placer/cli/trace_commands.py` | regression, tests |
| 123 | `packages/temper-placer/src/temper_placer/cli/watch_commands.py` | regression, tests |
| 117 | `packages/temper-placer/src/temper_placer/io/__init__.py` | route, closure, regression, tests |
| 112 | `packages/temper-placer/src/temper_placer/router_v6/grid_prep_stage.py` | route, closure, tests |
| 109 | `packages/temper-placer/src/temper_placer/router_v6/__init__.py` | route, closure, regression, tests |
| 90 | `packages/temper-placer/src/temper_placer/explainability/decision.py` | tests |
| 87 | `packages/temper-placer/src/temper_placer/core/geometry_types.py` | route, closure, regression, tests |
| 78 | `packages/temper-placer/src/temper_placer/core/net_types.py` | route, closure, regression, tests |
| 72 | `packages/temper-placer/src/temper_placer/core/loop.py` | route, closure, regression, tests |
| 71 | `packages/temper-placer/src/temper_placer/router_v6/result_aggregate_stage.py` | route, closure, tests |
| 71 | `packages/temper-placer/src/temper_placer/topological/__init__.py` | tests |
| 68 | `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` | route, closure, tests |
| 67 | `packages/temper-placer/src/temper_placer/deterministic/stages/__init__.py` | route, closure, regression, tests |
| 66 | `packages/temper-placer/src/temper_placer/manufacturing/stackup_validator.py` | tests |
| 64 | `packages/temper-placer/src/temper_placer/router_v6/adapter.py` | route, closure, regression, tests |
| 62 | `packages/temper-placer/src/temper_placer/pipeline/__init__.py` | closure, tests |
| 62 | `packages/temper-placer/src/temper_placer/router_v6/net_prep_stage.py` | route, closure, tests |
| 56 | `packages/temper-placer/src/temper_placer/cli/_io.py` | regression, tests |
| 56 | `packages/temper-placer/src/temper_placer/io/netclass_loader.py` | route, tests |
| 56 | `packages/temper-placer/src/temper_placer/placer/cp_sat/encoder.py` | route, tests |
| 53 | `packages/temper-placer/src/temper_placer/router_v6/topology_extraction.py` | route, closure, tests |

### `delete-with-its-tests-candidate` -- cold on every production probe, only test importers

total 33 files, 6,345 LOC. NONE of these is `delete-now`:
each one's deletion also removes test coverage, so each needs a reviewer's
explicit nod, and several are pinned by an oracle.

| LOC | path | test importers |
|---:|---|---:|
| 745 | `TP/validation/rtd_safety.py` | 6 |
| 546 | `TP/router_v6/routability_check.py` | 5 |
| 432 | `TP/physics/parameter_bounds.py` | 2 |
| 338 | `TP/placer/cp_sat/protective_impedance_colocation.py` | 1 |
| 336 | `TP/explainability/logger.py` | 4 |
| 283 | `TP/explainability/serialization.py` | 4 |
| 272 | `TP/heuristics/power_stage.py` | 4 |
| 241 | `TP/explainability/traced_loss.py` | 2 |
| 212 | `TP/router_v6/capacity_check.py` | 5 |
| 208 | `TP/regression/measure_closure.py` | 1 |
| 201 | `TP/pipeline/dag_expr.py` | 3 |
| 197 | `TP/explainability/pipeline.py` | 4 |
| 193 | `TP/adapters/router_v6_stage_adapter.py` | 2 |
| 186 | `TP/pcl/unsat_compiler.py` | 2 |
| 183 | `TP/analysis/_violation_report.py` | 2 |
| 171 | `TP/deterministic/instrumentation.py` | 2 |
| 171 | `TP/heuristics/__init__.py` | 4 |
| 145 | `TP/extraction/hypergraph_factory.py` | 3 |
| 145 | `TP/testing/golden_diff.py` | 3 |
| 144 | `TP/router_v6/congestion_analysis.py` | 4 |
| 118 | `TP/validation/trace_analyzer.py` | 3 |
| 113 | `TP/regression/cp_sat_comparison.py` | 3 |
| 111 | `TP/geometry/sdf.py` | 3 |
| 109 | `TP/placer/adjustment.py` | 3 |
| 98 | `TP/analysis/_area_sufficiency.py` | 2 |
| 86 | `TP/explainability/markdown_report.py` | 5 |
| 78 | `TP/deterministic/seed_filter.py` | 4 |
| 69 | `TP/validation/tht_check.py` | 3 |
| 67 | `TP/adapters/deterministic_adapter.py` | 2 |
| 56 | `TP/heuristics/mcu_subsystem.py` | 4 |
| 52 | `TP/testing/version_gate.py` | 3 |
| 26 | `TP/cli/_signal.py` | 1 |
| 13 | `TP/cli/_version.py` | 1 |
