# Execution Map, Phase 1 (2026-08-14) — checkpoint, in progress

Status: **checkpoint commit while a production route run is still in flight**
(held/monitored by another agent in this session, not by this process — see
"Route status" below). This document will be updated as that run resolves.
Everything below is either directly measured (labeled MEASURED) or a static
call-graph finding (labeled STATIC) — never inferred results presented as
measured.

## Scope and instrumentation coverage (read this before any finding below)

- **Board used**: `pcb/temper.kicad_pcb` on `main` (sha256
  `6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64`,
  verified unchanged before and after every run in this session). This is
  the `main`-branch board, not the router-lineage (`1b15b274`) or PR #1152
  (`b7d865b7`) variants.
- **Worktree**: `.claude/worktrees/execution-map-phase1`, branch
  `census/execution-map-phase1`, off `origin/main`. Isolated `.venv` via
  `make venv-isolate` (not the shared repo `.venv`).
- **Production entrypoint confirmed** (STATIC, read `scripts/route_board.py`
  directly): `make route` and `.github/workflows/board-regeneration.yml`
  both invoke `scripts/route_board.py` with **no flags** beyond `--pcb`/
  `--output` (board-regeneration.yml additionally sets `PYTHONHASHSEED=0`
  and `ulimit -v 8388608`). Every `--pruning`/`--net-batching`/
  `--nlayer-astar-spike` `action="store_true"` flag defaults `False`, so the
  shipped behavior is: `enable_geographic_pruning=False`,
  `enable_net_batching=False`, `enable_nlayer_astar_spike=False`. This
  confirms the task's premise directly from source, not from the task
  description alone.
- **DRC gate confirmed** (STATIC + MEASURED): `.github/workflows/
  regression.yml:190` runs `scripts/ci_check_drc.py --backend kicad-cli`.
  `DrcRatchet(backend="kicad-cli")` uses KiCad's external `kicad-cli` binary
  as the truth source; the **`rust` backend
  (`temper_drc_rs.run_drc()`/`create_default_registry()`) is never invoked
  by this gate** — confirmed both by reading `ci_check_drc.py` (only ever
  constructs `DrcRatchet(ceiling_path, backend=args.backend)` with
  `args.backend` fixed to `"kicad-cli"` by the CI invocation) and by direct
  Rust coverage measurement (see below): `rules/mod.rs::create_default_
  registry` shows 0 executed regions under a full `ci_check_drc.py
  --backend kicad-cli` run.
- **No subprocess/parallel-mode gap for this entrypoint** (STATIC +
  MEASURED). `scripts/route_board.py` has exactly one `subprocess.run` call
  site (line 477), inside `run_measurement`'s per-run worker dispatch, which
  is only reachable when `args.runs is not None` (the `--runs N` measurement
  mode). `run_single` — the path `make route`/CI actually take (`--output
  PATH`, no `--runs`) — calls `route_once()`/`route_pcb()` directly
  in-process; it never touches `subprocess`. Confirmed empirically too:
  `ps aux` during both live `route_board.py` attempts (PIDs 3263518 and
  3274009, see below) showed exactly one Python process throughout, no
  children. **Conclusion: plain `coverage run` (no `--parallel-mode`, no
  `coverage combine`) captures 100% of what this specific production
  invocation executes.** The task's own caveat about `--net-batching`
  spawning workers is real but does not apply to `make route`/CI's actual
  invocation — it would only apply to a `--runs --net-batching` diagnostic
  run, which I have not attempted and explicitly did not need for this
  measurement.
- **Python coverage of the production ROUTE: zero data, all three
  attempts.** All three `route_board.py` runs were killed (kernel OOM twice,
  my own memory guard once) before `coverage`'s SQLite backend could flush
  — `SIGKILL`/late `SIGTERM` bypass the atexit save entirely, so **no
  partial route coverage survives any attempt** to report, even labeled
  partial. This is a clean, total gap for the routing entrypoint
  specifically — not glossed over, not approximated. See "Route status"
  below for the full memory-blowup finding, which is itself the most useful
  output of the route side of this phase.
- **Python coverage of the DRC gate (`ci_check_drc.py --backend
  kicad-cli`): complete, real, and committed.** This run finished normally
  (exit non-zero, a pre-existing/unrelated stale-ceiling FAIL — not caused
  by this session — but it ran to completion and `coverage` flushed
  cleanly). 36% statement coverage across everything `.coveragerc`'s broad
  `source = .` sees exercised by this one gate; full report at
  `docs/evidence/2026-08-14-execution-map-phase1-py-coverage-drcgate.txt`.
  `core/ipc2152.py` and `router_v6/_astar_nlayer.py` do not appear in this
  report **at all** (not partially covered — absent), because this
  particular gate never imports the router; that's expected and is not
  evidence about their production liveness one way or the other on its
  own — it's the routing entrypoint's coverage (currently unobtainable,
  see above) that would settle their production status directly, not this
  one.
- **Rust coverage**: real, measured, but only for **`temper-drc-rs`** (plus
  whatever of **`temper-geometry`** got statically compiled into that
  cdylib as a path dependency — its source shows up in `temper-drc-rs`'s own
  coverage mapping) under **one** completed run: `ci_check_drc.py --backend
  kicad-cli`. `temper-rust-router` and `temper-orchestration` were also
  built instrumented but never got a completed run before their host
  process (route_board.py) was OOM-killed twice — **zero coverage data for
  those two crates' actual behavior during routing**. This is a real,
  disclosed gap, not glossed over.
- **Crates NOT instrumented at all this session**: `temper-quality-oracle`,
  `temper-constraints`, `temper-constraint-compiler`, `temper-thermal`,
  `temper-io-types`, `temper-workflow`, `temper-data-model`,
  `temper-rust-router-core` (as its own top-level binary — some of its code
  is statically pulled into `temper-rust-router`'s instrumented build, not
  independently confirmed), `temper-design-bundle`. For these, only the
  STATIC call-graph evidence in `.unwired-kernel-inventory` (the existing
  `scripts/check_unwired_kernels.py` ledger — 1031 registered pyo3 symbols,
  112 unwired, all pre-triaged with NEVER-WIRE-BY-DESIGN / ORPHANED-DELETE /
  WIRE tags as of 2026-08-12) applies. That ledger only sees
  pyo3-registered symbols, so pure-Rust-internal functions in these crates
  are structurally invisible to it, exactly as the task predicted.
- **A spurious profraw set found and excluded.** ~15 `default_<hash>_<pid>.
  profraw` files turned up scattered in package source directories
  (`packages/temper-drc-rs/`, `packages/temper-geometry/`, etc.) as
  untracked files in this worktree — PIDs matched the *build* processes
  (maturin/cargo), not any route or DRC run. Merged and checked against
  `libtemper_drc_rs.so`: **0.00% total coverage** — they don't correlate to
  this binary at all (build-script-time execution of something else, most
  likely `pyo3-build-config`'s own build probing, which also gets compiled
  under a global `RUSTFLAGS=-C instrument-coverage`). These were moved out
  of the worktree (to the scratchpad) and **excluded from every merge in
  this report** to avoid exactly the contamination the task warned about
  (build/test execution masquerading as production coverage). This is a
  disclosed instrumentation blind spot, not a finding about the product.

## Route status (as of this commit) — closed, do not retry

**Three** full `route_board.py` (single-run, `run_single`, no flags beyond
`--pcb`/`--output`) attempts, **all three OOM-killed** partway through the
Stage-3/4 SAT-solve phase. The coordinator of this session (holding/
monitoring attempt 3 independently) has instructed **no further retry**;
this section is closed. The memory-blowup finding itself, detailed below,
is the most useful thing to come out of the route side of this phase.

1. First attempt (PID 3263518, Python `coverage run` + all three Rust
   crates instrumented, **no** `PYTHONHASHSEED` set): RSS grew from ~1 GB at
   t≈200s to 59.3 GB at t≈390s, kernel OOM-killed it
   (`journalctl -k`: `oom-kill: ... task=coverage,pid=3263518 ...
   Killed process 3263518 (coverage) ... anon-rss:59315548kB`). Zero
   coverage data survived (SIGKILL, no atexit flush).
2. Second attempt (PID 3274009, same instrumentation, **`PYTHONHASHSEED=0`
   added** to match `board-regeneration.yml` exactly): same shape — RSS flat
   at ~1 GB until t≈270s, then climbed to 57+ GB by t≈388s. A safety guard I
   armed (kill at `MemAvailable < 4 GB`) fired first this time, killing it
   at t≈388s before a kernel-level OOM. Zero coverage data survived (guard
   uses SIGTERM→SIGKILL, no flush either — the growth is too explosive by
   the time the guard fires to expect a clean exit).

Pinning `PYTHONHASHSEED=0` did **not** fix the blowup by itself (attempt 2
still died). The isolating test was attempt 3: **Python-only, zero Rust
instrumentation** (extensions reverted to standard non-instrumented release
builds via `make extensions`, confirmed by `import temper_drc_rs,
temper_rust_router, temper_orchestration` succeeding post-revert),
`PYTHONHASHSEED=0`, PID 3283781. **It died the same way** — RSS flat at
~1 GB through t≈270s, then climbed from 18 GB to 57.9 GB in **15 seconds**
(t≈349s→364s: `avail_kb` 17,666,804 → 1,557,908; the memory-guard I'd armed
fired and killed it at t≈389s, avail 1.56 GB). This isolates the cause:
**it is not Rust instrumentation overhead** — a Python-only `coverage run`
(branch=True) of this exact production entrypoint reproduces the same ~50x
blowup relative to the ~1 GB RSS an *uninstrumented* route run peaks at
today (per the coordinator's independent measurement this session). The
remaining candidate is `coverage.py`'s branch-tracing itself interacting
badly with this pipeline's Stage-3/4 SAT-solve phase — plausibly a
`sys.settrace`/`sys.monitoring` interaction with a very hot, very deep
Python↔Rust call boundary (the SAT solve drives repeated FFI calls back
into Python-level constraint/heuristic code) that grows unboundedly rather
than the bounded per-line accounting `coverage.py` normally does. This is
not confirmed further — three attempts is the ceiling for this phase per
the coordinator's explicit instruction; **do not retry with the same
approach** (see "Next steps" below for what a cheaper follow-up would look
like).

**This most likely explains three previously-unattributed failures from
elsewhere in this session today**, per the coordinator: two board-scale
`enable_manufacturing_drc` runs that vanished silently at ~150s against a
124.3s uninstrumented baseline with no traceback and no `dmesg` OOM entry,
and the "Hybrid Pour Evidence" workflow's `pytest exit -9`. Memory
exhaustion under aggregate multi-agent load (six agents running heavy
builds/routes concurrently in this session, per the coordinator) fits all
three: a `SIGKILL` from either the kernel OOM killer or another agent's
`ulimit`/guard leaves no traceback and, if the killing agent's own guard
fired rather than the kernel's OOM killer, no `dmesg` entry either — which
is exactly what happened to my own attempt 3 (my guard fired at 4 GB
available, pre-empting a kernel-level OOM that would have logged one).
**This retires a standing mystery from earlier in the session rather than
adding a new, unrelated one**: at least a strong contributing cause, not
necessarily the sole one, since the earlier `enable_manufacturing_drc`
deaths were not running under `coverage` at all — meaning whatever
Python/Rust interaction (or aggregate memory pressure from six concurrent
heavy processes, independent of any single job's own instrumentation) is
responsible is not exclusive to `coverage`-instrumented runs.

## Rust findings (MEASURED, `ci_check_drc.py --backend kicad-cli` only)

Full report: `rust_coverage_report.txt` / `rust_coverage_drc_rs.json` in
this session's scratchpad (not committed — see below). Headline: **2.87%
region coverage** of everything statically linked into `temper_drc_rs.so`
(which includes `temper-geometry` source, since it's compiled in as a path
dependency) during a single `ci_check_drc.py --backend kicad-cli` run.
Low overall % is expected and not itself a finding — most of that binary is
DRC/oracle/marshal machinery for code paths this one gate doesn't take
(construction of `DrcBoardSnapshot`/oracle marshaling/differential-only
kernels), not evidence of dead code by itself.

Specific, targeted results (file-level, confirms/extends the task's
motivating examples):

| File | Region cover | Category |
|---|---|---|
| `temper-drc-rs/src/rules/safety/creepage.rs` (`CreepageCheck`) | **0.00%** | Confirmed dark under the CI DRC gate. See below for full reachability picture — not simply dead. |
| `temper-drc-rs/src/router_clearance.rs` | **0.00%** under DRC gate | Expected — this kernel is invoked from *routing* (`router_v6/clearance_check.py` → `temper_drc_rs.verify_route_clearance`), not from the DRC ratchet gate. Its liveness during *routing* is exactly what the still-pending route run would confirm; not yet measured. |
| `temper-drc-rs/src/rules/mod.rs` (`create_default_registry`, the whole 17+-check Rust rule registry incl. `CreepageCheck`, `HVLVSeparationCheck`, `IsolationCheck`, `ClearanceCheck`, ...) | **0.00%** | The entire registry is unreached by the CI-required DRC gate — not just `CreepageCheck`. See reachability below. |
| `temper-geometry/src/creepage_check.rs` (`calculate_required_creepage_py`, the kernel `router_v6/creepage_check.py` actually delegates to) | **0.00%** under DRC-gate run | Expected — this is the *routing*-path creepage kernel, not exercised by the DRC ratchet. Its liveness during routing is not yet measured (route run pending). |
| `temper-drc-rs/src/ipc.rs`, `ipc_pyo3.rs` (IPC-2152 Rust side — **not** the Python `core/ipc2152.py::ipc2152_min_width` the task calls out, a different implementation in a different language) | 44.44% / 43.42% | Partially live even under kicad-cli-backend DRC — some IPC helper is called regardless of backend. |
| `temper-drc-rs/src/drc_ratchet.rs` (Rust-side ratchet helpers, distinct from the Python `temper_placer.regression.drc_ratchet` the gate script imports) | 57.14% | Substantially live — ceiling/comparison logic used regardless of backend. |

### `CreepageCheck` reachability (STATIC, cross-checked against the MEASURED 0%)

Not simply dead — genuinely **runs only in other entrypoints**, none of
which are the CI-required gate:

- `rules/mod.rs::create_default_registry()` (which registers
  `CreepageCheck`) is called from exactly one non-test production site:
  `temper-drc-rs/src/lib.rs`'s `run_drc()` pyfunction.
- `run_drc()`'s only non-test Python callers: `validation/drc_runner.py`,
  `regression/drc_ratchet.py` (its **default** `backend="rust"` constructor
  path — but CI's `ci_check_drc.py` always passes `backend="kicad-cli"`
  explicitly, so this default is never hit in CI), `placer/cp_sat/gates.py`
  (**`DrcGate`**, imported by `placer/cp_sat/loop.py` — the CP-SAT
  **placement** loop, a different pipeline stage than routing;
  `route_board.py` never invokes placement, it routes from the board's
  existing positions), `validation/drc_oracle.py`, and several diagnostic/
  calibration scripts (`scripts/calibrate_drc_ceiling.py`,
  `scripts/check_drc_determinism.py`, `scripts/ci_closure_test.py`,
  `scripts/check_corpus_specificity.py`, `scripts/full_pipeline_profile.py`)
  that are not invoked by any CI workflow's `run:` step (grepped
  `.github/workflows/*.yml` and `Makefile` — no match).
- **Category: runs only in another entrypoint (the CP-SAT placement loop),
  IF that loop itself runs in production** — and I did not find it invoked
  by any CI workflow either (`placer-regression.yml`'s JAX/placement step
  was retired 2026-07-27 per its own comment; I did not fully trace what,
  if anything, replaced it as a production placement-generation trigger —
  outstanding).
- The live routing-time creepage check is a **different, separately
  implemented kernel** (`temper-geometry`'s `calculate_required_creepage_
  py`, delegated to by `router_v6/creepage_check.py`, itself called via
  `_pipeline_verify.py` → `_pipeline_core.py`, confirmed by grep of the
  import chain) — this is presumably what's alive during routing, not yet
  confirmed by a completed route-coverage run.

This matches and sharpens the task's claim: `CreepageCheck` is dark under
the CI-required gate, and the reason is architectural (wrong entrypoint
family, not merely "unused") — the registry it lives in belongs to a
`rust`-backend DRC path CI deliberately does not use, and a placement-stage
consumer that itself may not run in CI either.

## Python findings (STATIC only so far — no completed coverage run)

- `core/ipc2152.py::ipc2152_min_width`: grepped every `.py` file in the
  repo — the **only** two references are its own definition and its own
  test (`tests/core/test_ipc2152.py`). Zero production call sites. Matches
  the task's claim exactly; not yet cross-checked against a completed
  coverage run (would trivially show 0 hits, since coverage only sees files
  actually imported by the process under measurement).
- `router_v6/_astar_nlayer.py` (N-layer A* spike): `enable_nlayer_astar_
  spike` defaults `False` in every call site from `route_board.py` down to
  `route_pcb()`; `make route`/CI never pass `--nlayer-astar-spike`.
  Confirmed dark-by-default from source directly (not just from the task
  description). Category: **flag-gated, flag off by default in
  production.**
- Found ~30+ other `enable_*: bool = False`-defaulting parameters across
  `router_v6/*.py` (`enable_all_pad_tree`, `enable_connectivity_verifier`,
  `enable_manufacturing_drc`, `enable_zone_pours`, `enable_bundling`,
  `enable_via_vars`, `enable_erc_check`, `enable_coarse_to_fine`, `enable_
  smoothing`, `enable_theta_star`, `enable_lazy_theta_star`, `enable_pad_
  teardrops`, ...) — not yet individually traced to a default-off
  confirmation at every call site the way `nlayer_astar_spike` was; this is
  exactly the class of finding a completed Python coverage run would rank
  automatically (0%-hit branches under each `if enable_X:`) rather than
  requiring one-by-one manual tracing. Flagging as the highest-value thing
  the pending route-coverage run will resolve.

## Test-gate cross-reference — the highest-value output of this phase (relayed, not independently re-derived)

Another agent in this session reports **66 Rust test modules / 467 test
functions gated behind a Cargo feature CI never enables** — native-arm CI
runs `cargo test --no-default-features`, while the gated tests are
`#[cfg(feature = "python")]` — and that **462 of 467 have never executed in
CI, ever**. This is test-side dead code (never-*tested*), a different axis
from this document's never-*executed-in-production* axis. Per the
coordinator's framing, the intersection is the sharpest signal available:
**a module with zero production coverage (this document's axis) that is
also in the never-run-in-CI test set (the other agent's axis) is code that
neither ships nor is tested** — strictly worse than either fact alone, and
the ranking criterion this phase should lead with once both sets are
enumerable side by side.

I have **not** independently re-derived the 66-module/467-function list —
relaying it, not re-measuring it. What I did independently confirm by
reading source directly: the mechanism is identical to what this document
already found for `router_clearance.rs`. `#[cfg(feature = "python")]` gates
lines 993–1005 of `packages/temper-drc-rs/src/router_clearance.rs`
(including `get_clearance`/`verify_route_clearance`), and its own
`#[cfg(test)]` module at line 1065 sits inside that same feature gate — so
it is very likely a member of the other agent's 462-strong never-run set,
though I have not cross-checked it against their actual list by name.

**Known intersection members from this document's own measurement**
(zero production coverage under the one gate I completed, `ci_check_drc.py
--backend kicad-cli`) that plausibly also sit in the never-run-in-CI test
set, given they share the same `#[cfg(feature = "python")]`/
`--no-default-features` shape:
`temper-drc-rs/src/rules/safety/creepage.rs` (`CreepageCheck` and its own
`#[cfg(test)]` module), `temper-drc-rs/src/rules/mod.rs`
(`create_default_registry` and its tests at lines 411/474/952), and
`temper-drc-rs/src/router_clearance.rs`. **Not yet confirmed by name
against the other agent's 467-function list** — flagging as the single
highest-priority follow-up for whoever picks this up next, since it is a
five-minute diff against their list, not a new measurement.

## What's NOT in this checkpoint

- No ranked, complete "never-executed, ranked by safety relevance" table
  yet — that requires the pending Python coverage run (or, failing that, an
  explicit statement that it could not be obtained and why) plus a second
  Rust coverage pass for `temper-rust-router` and `temper-orchestration`
  against a *completed* route (currently zero data for both).
- `temper-orchestration/src/clearance.rs::get_clearance_impl` vs.
  `temper-drc-rs/router_clearance.rs` — the task's fourth motivating
  example — is **not yet resolved with measurement**. Static grep confirms
  `router_v6/clearance_check.py` calls `temper_drc_rs.verify_route_
  clearance` (i.e. `router_clearance.rs`), consistent with the task's claim
  that this, not `temper-orchestration/clearance.rs`, is the always-on
  kernel — but I have zero Rust coverage data for either crate during an
  actual route, twice, due to OOM. This is the single most important
  outstanding measurement.

## Next steps: a cheaper Python-coverage approach for the route (proposed, NOT launched)

Per the coordinator's instruction, no further instrumented full-route
attempt without explicit sign-off. Options, cheapest first, none launched:

1. **Single-stage coverage, not full-pipeline.** `route_pcb()` runs Stage
   0–4 in one call; the SAT-solve phase (Stage 3, where the blowup starts
   at t≈260–270s every time) is the expensive/dangerous part. Wrapping only
   an earlier or later stage in isolation (if the pipeline exposes
   stage-level entry points — `router_v6/_pipeline_core.py` suggests it
   does) under `coverage` would cover the cheap stages fully and leave
   Stage 3/4 to a different technique below, rather than an all-or-nothing
   8–11-minute run.
2. **A smaller board.** `power_pcb_dataset/corpus/temper/temper.kicad_pcb`
   (546 lines) or `packages/temper-placer/tests/fixtures/large_board.
   kicad_pcb` (1321 lines) vs. the production board — much cheaper to route
   and instrument, at the cost of not being the actual production board (a
   different net count changes which `enable_*` branches and net-class
   code paths get exercised, so this would need explicit labeling as
   "reachability on a smaller board," not "production coverage").
3. **`sys.monitoring` (PEP 669, Python 3.12+) instead of `coverage.py`'s
   `sys.settrace`.** Lower per-event overhead, and this repo's `.venv` is
   already CPython 3.12. Untested here — the risk is it has the same
   unbounded-growth interaction with the Stage-3 FFI-heavy loop that
   `coverage.py` did, since the growth pattern (flat until t≈260s, then
   exponential) suggests an interaction with the SAT-solve phase itself,
   not necessarily specific to `coverage.py`'s implementation.
4. **Sampling instead of full tracing** (e.g. `py-spy` periodic stack
   sampling) — would show *which* functions are hot, not full line/branch
   coverage, so it under-delivers relative to the task's actual ask (a
   diff of executed vs. defined) but would be nearly free memory-wise and
   could at least confirm which of the ~30 `enable_*`-gated modules are on
   the call stack during a real route, without needing full instrumentation.

None of these would explain *why* `coverage.py` alone triggers a 50x memory
blowup at exactly the SAT-solve boundary — that mechanism is still
unexplained and, per the coordinator, out of scope to chase further this
session.

## Artifacts

Committed to git, alongside this file:
- `docs/evidence/2026-08-14-execution-map-phase1-rust-coverage-own-crates.txt`
  — file-level Rust coverage (`temper-drc-rs` + statically-linked
  `temper-geometry`), 133 files, under the completed `ci_check_drc.py
  --backend kicad-cli` run. 113 of 133 files show 0.00% region coverage
  under this one gate.
- `docs/evidence/2026-08-14-execution-map-phase1-py-coverage-drcgate.txt`
  — full Python statement/branch coverage report for the same completed
  run (36% TOTAL across everything `.coveragerc` sees; per-file detail with
  missing line numbers).

Not committed (scratchpad only, regenerable from what's listed, large/
binary, disk-tight repo):
`/tmp/claude-1000/-home-bennet-Desktop-temper/c0bf43ed-bc14-4a43-9c79-57bf591cf8ab/scratchpad/execmap/`
— `.coveragerc`, `production_rust.profdata` / `drcgate.profdata` (441 KB
each, LLVM merged profile data), `rust_coverage_drc_rs.json` (16 MB,
function-level), `profraw/` (raw counters, both genuine and the excluded
build-time set), `target-cov/` (private instrumented Cargo target dir,
several hundred MB — holds the instrumented `.so` objects the `.profdata`
files need to be re-reported against, `libtemper_drc_rs.so`,
`libtemper_rust_router.so`, `libtemper_orchestration.so`).
