<!-- provenance: commit=753da757781f227019c4ef95a4508ed320de7051 dirty=true -->

# Python CI load inventory: what can leave GitHub Actions

**Date:** 2026-08-11
**Scope:** the Python side of "GitHub Actions should run only CPython-bound work." The
Rust `cargo test` side is a separate agent's inventory
(`docs/evidence/2026-08-11-native-cargo-test-duplication-inventory.md`, PR #988 —
its own headline finding is that the obvious cargo-test duplication was already
resolved before this session started).

**Methodology.** All frequency numbers below are measured from real run history
(`gh run list` / `gh api .../actions/runs/<id>/jobs`), not guessed. `push`-to-`main`
runs that GitHub cancels before any job starts cost ~0 runner-minutes (verified: a
sampled cancelled run's job list is empty) and are excluded from "executing"
frequency — only runs that actually produce job start/completion timestamps are
counted. Where a table cell says "measured," the underlying `gh` commands and raw
numbers are in this document's body. Where it says "estimated," it is explicitly
flagged as such and is **not** included in the Part 3 landed total, per R25.

This repo's push-to-`main` rate is unusually high — many concurrent agent
worktrees commit directly to `main` — so even a modest per-run job cost compounds
into a large weekly total. That volume is exactly why trigger-narrowing (not
deleting tests) is this document's main lever.

---

## Part 1 — measured Python CI load

### 1.1 `python-tests.yml` (the big one — 3839 lines, 20 jobs)

Both `push` (branch `main`) and `pull_request` triggers carry a ~100-entry
`paths:` filter covering nearly the whole repo (`packages/**`, `scripts/**`,
`elec/**`, `docs/evidence/**`, ...), so in practice almost every push/PR trips the
workflow. A `changes` job (stdlib Python + `git diff`, no container, ~15s) computes
finer-grained per-job path predicates for exactly 7 of the 20 jobs
(`cargo-smoke`, `test`, `rust-checks`, `board-provenance-requirements-gates`,
`consistency-gates`, `hygiene-gates`, `invariant-router-v6-3`) — see
`scripts/classify_changed_paths.py` and `.github/required-checks.json`'s
`job_triggers`. **On `push`, every one of those 7 still runs unconditionally**
(`if: github.event_name == 'push' || needs.changes.outputs.<id> == 'true'`) — the
path predicate only narrows the *PR* path. This is a deliberate, documented
design (trunk pushes always get the full gate set) and is not touched here.

Measured trigger volume, `python-tests.yml`, 2026-08-07T18:44Z–2026-08-11T14:27Z
(91.7h window, 250-run sample):

| Trigger | Total runs | Executing (jobs actually ran) | Cancelled (0 jobs) | Weekly (executing, extrapolated) |
|---|---|---|---|---|
| `push` → `main` | 166 | 87 (52%) | 79 | **~159/week** |
| `pull_request` | 78 | 72 (92%) | 5 (+1 in-progress) | **~132/week** |

Per-run job-minutes, measured directly from `gh api .../jobs` timestamps on 4
representative push runs and 2 PR runs (job list below; every job's
`started_at`→`completed_at` delta, summed):

| Path | Jobs that run | Measured job-minutes/run |
|---|---|---|
| `push` → `main` (before this PR) | all 18 real jobs (`astar-nightly` skips outside `schedule`) | **~103.4 min** |
| `pull_request` | 9 jobs (the 7 path-conditional + `changes` + `fast-gates`; the 8 trunk-only jobs report `started_at == completed_at`, i.e. skip instantly) | **~47.8 min** |

**Honest total for `python-tests.yml` before this PR:** `159/wk × 103.4min` (push)
`+ 132/wk × 47.8min` (PR) `+ ~1/day × 103.4min` (nightly schedule, same job set as
push) ≈ **23,470 job-minutes/week (~391 hours/week)**.

### 1.2 Other Python-bearing workflows (measured by a research fork, cross-checked)

| Workflow | Trigger / paths | Measured weekly runs | Min/run | Est. weekly min |
|---|---|---|---|---|
| `placer-regression.yml` | push+PR, path-filtered to `packages/temper-placer/src/**` etc. | push ~140/wk | 5× redundant matrix, ~6.4 each | **~3574 wasted** (of a legitimate job) |
| `metrics-reconcile.yml` | `schedule` */30 + `workflow_run` + `workflow_dispatch` | schedule leg ~149/wk | 6.65 | **~991 wasted** (schedule leg only) |
| `codeql.yml` | push (path-filtered) + weekly schedule | ~184/wk | 9.83 | ~1809 (security scanner, not test execution — context only) |
| `regression.yml` | push+PR, path-filtered, already dedupes the 2-3 heavy cp-sat tests against `python-tests.yml` | ~173/wk | 7.6 | ~1315 (MUST STAY) |
| `metrics-record.yml` | push, path-filtered to `packages/**`/`pcb/**` | ~123/wk | 9.73 | ~1197 (mostly MUST STAY; see 3.3) |
| `golden-check.yml` | push+PR, path-filtered | ~139/wk | 6.4 | ~890 (MUST STAY — kicad-cli DRC) |
| `architecture-poster.yml` (generate job) | push | ~184/wk (est.) | 2.9 | ~534 (small, legitimate) |
| `human-reference-check.yml`, `cp-sat-benchmarks.yml`, `pr-pipeline-scorecard.yml`, `architecture-poster.yml`'s `pr-diff` job | opt-in via `ci-advisory` PR label (added 2026-08-04) | ~0 effective (100% `skipped` in last 10-20 runs each) | — | ~0 |
| `board-regeneration.yml`, `r9-evidence.yml`, `corpus-batch.yml`, `health-digest.yml`, `metrics-trend-check.yml` | nightly/weekly cron only, deliberately kept off the push pool | low | — | small, already optimal |
| `erc-gate.yml`, `firmware-tests.yml` | push+PR, narrowly path-filtered (`firmware/**`, `pcb/**`) | — | — | legitimate MUST STAY, no Python-load issue found |
| `docker-build.yml`, `dashboard-deploy.yml`, `release-please.yml`, `release-artifacts.yml`, `required-checks.yml`, `lint-workflows.yml` | event/release-triggered or lightweight aggregator | — | — | no targets |

`pr-perf-check.yml`'s "PR Performance Comparison" job is a **required check**
(`.github/required-checks.json`'s `required_contexts`) with its own path filter
already in place; it is real Python benchmark comparison work
(`scripts/pr_perf_compare.py`, `benchmarks/perf_ab.py`) and stays.

---

## Part 2 — classification

### ALREADY REDUNDANT

**None found**, in either `python-tests.yml` or the rest of the survey, with a
provable covering Rust/wasm test. This was checked explicitly against
`packages/*/src/wasm_test_registry.rs` and `tools/wasm/wasm_tier_topology.json`
for anything named `*_oracle*`/`*differential*`/`*parity*` (the naming pattern a
migrated-kernel test carries) before concluding — see below, every one of those
is a **retained oracle**, not dead weight.

The one confirmed native-Rust-work-out-of-Actions example this session
(`extended-bundle-workflow-checks`'s `cargo test --manifest-path
packages/temper-design-bundle/Cargo.toml` removed 2026-08-11, per that job's
inline comment) was already landed before this inventory started — it's Rust
test dedup, in scope for the sibling agent's PR #988, not this one.

### RETAINED DIFFERENTIAL ORACLES — explicitly NOT redundant (read `docs/migration-pipeline.md` stage 3 before ever revisiting this)

`python-tests.yml`'s `test` ("Core Tests") job runs five step-groups whose own
comments state plainly: *"the ONLY tests that pin the migrated Rust kernels
bit-exactly against the verbatim Python oracles"* —

- "Run validation DRC differentials" (`tests/validation/test_drc_*_rust_differential.py`, `tests/deterministic/**/*_rust_differential.py`, 176-test floor)
- "Run Phase-5 report/explainability/clearance differentials" (131-test floor)
- "Run Phase-5 cli differentials" (63-test floor)
- "Run Phase-5 workflow differentials" (32-test floor, `temper-workflow` package)
- "Run Wave-4 round-2 differentials" (1092-test floor)

Each is exactly the stage-3 pattern from `docs/migration-pipeline.md`: *"TDD:
differential test pinning the pre-migration implementation as oracle, written
first (red), then the Rust pyfunction (green)"* and *"Behavioral A/B: bit-identical
parity asserted on identical inputs."* They run on every PR and every push
(`pytest_guard.py --min-tests N` floors so a silently-shrunk collection fails
loudly). **These are not candidates for removal, path-filtering-away, or
"replace with the wasm tier"** — the wasm tier proves the Rust side is internally
correct against its own property/metamorphic suite; these suites are the only
place the Rust side is checked against the *original Python behavior it must
match*. Losing them loses the ability to detect a migration that is
internally-consistent-but-wrong. Classified here explicitly, per this task's own
caution, rather than left ambiguous.

They are also, mechanically, **CPython-bound**: they import the compiled pyo3
extensions (`temper_drc_rs`, `temper_io_types`, `temper_orchestration`, ...)
directly, which requires a real CPython interpreter, not a wasm32 sandbox.

`regression.yml`'s `-m "slow or l4_regression"` run of
`test_round_trip_integrity.py` is the answer to "are the 41 tests marked `slow`
in `packages/temper-placer` (and excluded from every `-m "not slow"` invocation
in `python-tests.yml`) actually covered anywhere, or silently never run" — they
are; `regression.yml` is push/PR-triggered (path-filtered) and runs them.
Flagged and checked per this task's "skipped tests are not free" caution, not
found to be a gap.

### MOVABLE OFF ACTIONS — landed in this PR (see Part 3 for the exact numbers)

1. **`python-tests.yml`: 4 fully-masked, zero-signal jobs**, each triggered on
   every `push` to `main` (`if: github.event_name != 'pull_request'`, which
   includes `push`) despite being structurally incapable of ever failing a
   build:
   - `extended-bundle-workflow-checks` — its one substantive step is
     `continue-on-error: true`
   - `extended-cpsat` — same
   - `invariant-router-v6-1` — same (masked because of a real, tracked
     `occupancy_grid.py` bug — see that step's own comment; the mask itself,
     not the bug, is what's addressed here)
   - `closure` ("Pipeline Closure Test") — its only substantive step is
     `continue-on-error: true`

   None of the four appears in `.github/required-checks.json`'s
   `required_contexts`, and none is referenced by `scripts/classify_changed_paths.py`
   or the manifest's `job_triggers` — confirmed by direct grep before editing.
   **Sibling jobs were deliberately left untouched**: `extended-cpsat-slow`,
   `invariant-router-v6-2`, `invariant-router-v6-4` all had their masks removed
   on 2026-08-05/07 once a real signal existed (their own comments document
   this), and `invariant-rest` has one masked step and one **hard gate**
   ("Run validation invariant tests") — moving its trigger would delay a real
   trunk-blocking check from "next push" to "next nightly," a genuine behavior
   change this PR does not make. Changed: `if:` narrowed from
   `github.event_name != 'pull_request'` to
   `github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'`
   on the 4 jobs above. Nightly cadence (cron `0 3 * * *`, same workflow) and
   on-demand `workflow_dispatch` are unchanged — the only thing removed is the
   redundant near-continuous execution on every trunk push.

2. **`placer-regression.yml`: collapsed a vestigial 5-board matrix to 1 job.**
   The per-board corpus regression step that the matrix existed for was retired
   2026-07-27 (dead-code comments in the file document this); the one step that
   survived, "Check for baseline changes without approval," is a `git
   diff`/`git log` check that never reads `matrix.board` and produces an
   identical verdict regardless of which of the 5 boards it happened to run
   under. Removed the `strategy.matrix` block entirely.

3. **`metrics-reconcile.yml`: dropped the `schedule: "*/30 * * * *"` trigger.**
   `workflow_run: { workflows: ["Metrics Record"], types: [completed] }` already
   fires every time there's new data to reconcile (no `conclusion:` filter, so
   it fires on failure too) — the cron was a blind poll of a strict subset of
   what the event trigger already covers.

### MOVABLE OFF ACTIONS — identified, NOT landed (estimated only, flagged for a maintainer)

- **`metrics-record.yml`'s "Profile router benchmarks" step**: `continue-on-error:
  true`, own comment says it's "a genuinely heavy, multi-minute benchmark...
  kept non-blocking until a maintainer confirms one complete CI run finishes."
  Runs on ~123 pushes/week. Fully masked (gates nothing) exactly like the 4
  jobs landed above, but this session could not confirm its actual measured
  duration or whether any downstream consumer reads its output within the time
  available — proposing a number here would be a guess, which R25 says not to
  do. Two candidate fixes for a maintainer: drop it, or gate it behind
  `schedule`/`workflow_dispatch` the same way the 4 landed jobs were.

### CPYTHON-BOUND, MUST STAY

This is the legitimate residual and is large — consistent with "the goal is not
zero." All of `python-tests.yml`'s `test`, `rust-checks`,
`board-provenance-requirements-gates`, `consistency-gates`, `hygiene-gates`,
`invariant-router-v6-2/3/4`, `invariant-rest`'s hard-gate step, and `fast-gates`
jobs; `regression.yml`; `golden-check.yml`; `erc-gate.yml`; `firmware-tests.yml`;
`metrics-record.yml` outside the one flagged step; `pr-perf-check.yml`'s required
comparison job. These import compiled pyo3 extensions, shell out to `kicad-cli`,
build/diff real board and netlist files, or run scripts too small to justify a
Worker deploy. None of this was touched.

### WASTE (noted, not landed — immaterial or out of the safe subset)

- `python-tests.yml`'s "Coverage gate (temper-placer)" step: its own command
  ends in `|| echo "::warning ...`, which makes the step exit 0 unconditionally
  regardless of the underlying check's verdict (already documented as
  intentional, warn-only, "Phase 1 paydown pending" — not new). It genuinely
  "runs but proves nothing," but it costs seconds (reads an already-produced
  `coverage.json`, no extra pytest run) inside a job (`test`) that must run
  anyway — removing it would not move any number in this document, so it is
  noted, not touched.
- `human-reference-check.yml`'s substantive step is separately broken
  (`import jax` → `ModuleNotFoundError`, `jax` undeclared as a dependency) —
  but the workflow is opt-in (`ci-advisory` label) and not required, so it
  costs nothing when unused. Flagged for correctness, out of scope for a
  CI-*load* task.

---

## Part 3 — the honest total

### Landed and measured (R25: only what this PR actually removes)

| Change | Frequency removed | Min/occurrence | Weekly minutes removed |
|---|---|---|---|
| `python-tests.yml`: 4 masked jobs off the push path | ~159 push runs/week | 29.11 (5.43+6.20+11.00+6.48) | **~4,629** |
| `placer-regression.yml`: 5-board matrix → 1 job | ~140 push runs/week | 25.6 (4 redundant boards × ~6.4) | **~3,584** |
| `metrics-reconcile.yml`: drop 30-min cron leg | ~149 runs/week | 6.65 | **~991** |
| **Total landed** | | | **~9,204 job-minutes/week (~153 hours/week)** |

At GitHub-hosted-runner list pricing this is real pool cost, not just wall-clock
— none of the three changes reduces test coverage: the 4 masked jobs keep
identical nightly + on-demand cadence, the board matrix's 4 removed legs were
computing the same board-independent answer 4 extra times, and the metrics
reconcile cron was a strict subset of its own event trigger.

### Removable, estimated (not landed — explicitly excluded from the total above per R25)

- `metrics-record.yml`'s masked "Profile router benchmarks" step: duration
  unconfirmed; at even a conservative 5 min/run × 123 runs/week this would be
  another **~615 min/week**, but this is a guess and is not counted.
- `invariant-rest`'s masked first step (the 3rd, smallest, mask remaining among
  the router_v6/io/etc. invariant jobs) could in principle be split from its
  hard-gate sibling step into its own job and narrowed the same way as the 4
  landed jobs — **not done here** because splitting a step out of an existing
  job is a bigger structural change than narrowing a job-level `if:`, and this
  PR stays inside "pure waste removal, path filters, trigger narrowing." Left
  for a follow-up if a maintainer wants it.

### What remains after this PR (CPython-bound residual, by design not reduced)

`python-tests.yml` alone remains at approximately `23,470 − 4,629 ≈ 18,841`
job-minutes/week. Adding the other workflows' MUST-STAY totals from the Part 1
table (`regression.yml` ~1,315, `metrics-record.yml` ~1,197,
`golden-check.yml` ~890, `architecture-poster.yml` ~534, plus smaller nightly/weekly
jobs) puts the durable Python-on-Actions residual in the neighborhood of
**~22,800 job-minutes/week (~380 hours/week)**. That number is dominated by
retained differential oracles and real CPython-extension tests running at this
repo's very high push-to-`main` rate (~159-plus executing pushes/week measured on
`python-tests.yml` alone) — it is large because the push rate is large, not
because any individual job is bloated. `codeql.yml` (~1,809 min/week) is not
included in that residual: it's a security scanner over Python/Rust/C++/Actions
source, not Python test execution, and is already the smallest footprint that
covers 4 languages.
