# CI health after the extended-suites split — measurement, not a victory lap

<!-- provenance: commit=d27b9e3ec6d138f07ac12a0638acdb3e323930cc dirty=false -->

**Date:** 2026-07-29

This is a measurement pass. No gate, threshold, test, workflow, or baseline was
changed to produce it. Part 1 checks whether PR #435 (merged, `d27b9e3e`) actually
fixed what it was supposed to fix. Part 2 is a current red-gate inventory of
`main`. Both were produced from `gh run list` / `gh run view` against
`BennetLeff/temper`, from a disposable worktree at `origin/main` tip
(`d27b9e3ec6d138f07ac12a0638acdb3e323930cc`).

## Part 1 — Did the extended-suites split actually work?

**Short answer: unknown. It cannot be verified yet, and that itself is the
finding.** PR #435 merged into `main` at `d27b9e3e` (mergedAt
2026-07-29T19:21:41Z). There is exactly **one** `main`-branch run of
`python-tests.yml` since that merge — run
[30484061772](https://github.com/BennetLeff/temper/actions/runs/30484061772),
created 2026-07-29T19:21:44Z — and as of this writing (checked repeatedly up to
19:39:54Z, ~18 minutes after creation) it is still **queued**: every job in it,
including both new jobs (`Extended Test Suites (bundle / workflow / checks)`,
`Extended Test Suites (cp-sat)`), reports `status: queued` with zero elapsed
run time. Nothing has started executing. A parallel check of the whole repo
(`gh api repos/BennetLeff/temper/actions/runs`, filtered to
`in_progress`/`queued`) shows **27 workflow runs** presently competing for
runners — consistent with the heavy concurrent-agent load already documented
elsewhere in this repo (60+ live worktrees). The queue backlog is itself part
of the CI-health picture: whatever the split fixed about *intra-job* CPU
contention, it does nothing about *inter-run* queue contention, and right now
the latter is severe enough that zero post-split data exists to judge the
former.

**Do not read anything below this line as "the split worked."** It is what is
knowable today, and no more.

### Historical (pre-split) baseline — for reference only, not re-measured here

These numbers were already established before this pass (PR #435's own
description and `docs/evidence/2026-07-29-extended-suites-timeout-split.md`)
and are repeated here only as the baseline the split was judged against. Only
the first row has a citable run ID; the other two are re-runs of an
undisclosed "commit N" in the source material, so their run IDs are not
recoverable and are not invented here:

| Run | Wall-clock | Outcome | Headroom vs. 25m timeout |
|---|---:|---|---:|
| `main`, run [30429718944](https://github.com/BennetLeff/temper/actions/runs/30429718944) | 18m05s | success | 6m55s |
| PR re-run, commit N (run ID not recorded in source) | 25m03s | **killed by `timeout-minutes: 25`** | −3s (over) |
| PR re-run, same commit N, retry (run ID not recorded in source) | 24m31s | success | 29s |

Independently re-verified here: run 30429718944's `Extended Test Suites
(bundle / cp-sat / workflow / checks)` job ran 2026-07-29T07:02:01Z →
07:20:06Z = **18m05s**, conclusion `success` — matches the cited figure
exactly.

### What IS measurable right now: the split changed nothing about which tests run

Since there's no completed run to pull post-split test counts from, this was
checked structurally instead: diffing the actual `run:` step bodies between
the pre-split combined job (`git show 84b8a650:.github/workflows/python-tests.yml`,
the commit immediately before the merge) and the two new post-split jobs in
the merged file.

- **cp-sat**: old backgrounded process ran
  `cd packages/temper-placer && uv run pytest tests/placer/cp_sat/
  tests/metrics/test_external_oracle.py tests/cli/test_cp_sat_flag.py -v
  --tb=short -p no:cacheprovider --maxfail=10`. New `extended-cpsat` job's
  "Run cp-sat suite" step: byte-identical command.
- **bundle**: old — `cargo test --manifest-path
  packages/temper-design-bundle/Cargo.toml && uv run python3 -c "import
  temper_design_bundle_python; ..."`. New `extended-bundle-workflow-checks`
  job: byte-identical.
- **workflow**: old — `cd packages/temper-workflow && uv run pytest tests/ -v
  --tb=short`. New job: byte-identical.
- **checks**: old — `uv run python tools/check_kicad_layers.py && cd
  packages/temper-placer && uv run pytest tests/io/test_4layer_output_properties.py
  -v --tb=short && uv run python3 firmware/test/gen_transition_table.py
  --generate && git diff --exit-code firmware/test/test_transition_table_generated.c`.
  New job: byte-identical.

Both `continue-on-error: true` annotations and the `TODO: temper-NNN` comment
are carried forward unchanged, as PR #435 claimed.

For reference, run 30429718944's actual collected/passed counts (pulled from
its step log, `gh run view --log`), so a future pass has a concrete number to
reconcile against once a post-split run completes:

| Suite | Collected | Result |
|---|---:|---|
| cp-sat (`tests/placer/cp_sat/` + oracle + cli flag) | 411 items | 409 passed, 1 failed, 1 skipped |
| checks (`test_4layer_output_properties.py`) | 5 items | 5 passed |
| workflow (`packages/temper-workflow/tests/`) | 0 items | 0 passed ("no tests ran") — this directory appears to genuinely have no tests today, not a collection failure |
| bundle (`cargo test`, temper-design-bundle) | 26 tests (3 `cargo test` result blocks: 24 + 2 + 0) | 26 passed |

Per the structural diff above, `extended-cpsat` should reproduce the 411/409/1/1
line exactly, and `extended-bundle-workflow-checks` should reproduce
26+0+5=31 passing, once either has a completed run to check. **This is not yet
confirmed at runtime — only at the source-diff level.** A follow-up
measurement should pull these counts from the first completed post-split run
and confirm they reconcile; if they don't, per the task brief that would be a
serious finding.

### Verdict

- **Fixed / partially fixed / moved: cannot be determined yet.** Zero
  completed post-split main runs exist. One is in flight, stuck in `queued`
  for at least 18 minutes against a backdrop of 27 concurrently
  queued/in-progress runs repo-wide.
- The one thing that IS confirmed: the split did not drop, add, or reorder any
  test (structural diff, above) — consistent with the PR's own claim, though
  not yet runtime-verified.
- **Recommendation, not an action taken here**: re-run this measurement once
  several post-split `main` runs have completed. Until then, treat "the split
  fixed the timeout" as an unverified claim, exactly as the task brief warned.

## Part 2 — Current red-gate inventory on `main`

Method: for each workflow that can run against `main` (push-to-main trigger,
or schedule against the default branch), the most recent **completed**
`main`-branch run was pulled via `gh run list --branch main --workflow
<file> --json ... ` and, where the conclusion was `failure`, every failing
job/step was pulled via `gh run view --json jobs` and the raw log
(`gh run view --log --job <id>`).

Workflows that trigger **only** on `pull_request` or `release: published`
were excluded — they have no meaningful "main" run to report (their most
recent `--branch main`-tagged entries, where any exist, are stale artifacts
from 20+ days ago that predate their current trigger config, with an empty
`jobs` array on re-query — consistent with being uninvokable against `main`
today, not a live gate). Excluded: `cp-sat-benchmarks.yml`,
`human-reference-check.yml`, `pr-perf-check.yml`,
`literal-removal-advisory.yml`, `pr-pipeline-scorecard.yml`,
`release-artifacts.yml`.

### New / unexpected first (this is what matters most)

**PR #435 itself introduces a new, confirmed gate failure — found while checking
this document's own provenance stamp, not from a completed CI run.** Its
companion evidence doc, `docs/evidence/2026-07-29-extended-suites-timeout-split.md`,
carries `<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -->` but was never added
to `.evidence-provenance-allowlist` (confirmed: `grep -n
"extended-suites-timeout-split" .evidence-provenance-allowlist` returns
nothing). Running the actual gate script locally against `d27b9e3e` (this
worktree's checkout, the exact post-merge tip) reproduces the failure directly:

```
FAIL: 2026-07-29-extended-suites-timeout-split.md: declares commit=UNKNOWN but
is not on .evidence-provenance-allowlist (UNKNOWN provenance requires an
explicit allowlist entry)
Evidence provenance gate FAILED (exit 3)
```

This is deterministic (the gate script has no timing dependency), so it will
fail identically whenever `Evidence provenance gate (docs/evidence/)` (a step
inside `Provenance & Anti-Vacuity Gates`, `python-tests.yml`) next actually
runs on `main` — including, most likely, the still-queued run 30484061772
discussed in Part 1, once it starts. **Classification: real code defect,
introduced by PR #435 itself** — the PR added an evidence doc without
following its own repo's evidence-provenance convention (either a real commit
SHA, or an allowlist entry with a `# TODO: temper-xxx` ticket). This was not
caught before merge because, per the task's Part 1 finding, PR #435's own
CI verification was never actually watched to completion. This is separate
from, and additional to, the two items below. **Not fixed here** — fixing it
would mean editing `.evidence-provenance-allowlist` or the file's own stamp,
both out of scope for a measurement-only pass; this is reported so a human or
a follow-up PR can add the allowlist entry (with a ticket) or backfill the
real commit SHA.

| Workflow | Job | Failing step | Classification | Notes |
|---|---|---|---|---|
| `python-tests.yml` | Provenance & Anti-Vacuity Gates | Measurement-provenance gate (drc_ceiling.json input freshness) | **stale artifact — attributable, expected under the task's own caveat** | `GATE RESULT: ERROR ... 1 stale record(s)`: `power_pcb_dataset/drc_ceiling.json#boards.temper` reports `pcb/temper.kicad_pcb: content hash changed since measurement`. This is exactly the situation flagged in this task's brief: another agent is actively modifying `pcb/temper.kicad_pcb` right now, which invalidates the ceiling file's content-hash provenance. Confirmed present across essentially every `python-tests.yml` run in the last several hours (30477654336, 30475722601, 30473311035, 30472345401, 30469095061, 30468003194, 30442762922, 30442750259 — 8/8 checked). Not a new defect; it will clear once the PCB edit lands and the ceiling is re-measured against it. **Not counted as a new red** per the task's explicit instruction. |
| `metrics-record.yml` | Record Pipeline Metrics | Generate HTML report | **real code defect + infrastructure gap** | Root cause chain in the log: the closure-test step reports `ERROR: DRC failed: kicad-cli is not available. Install KiCad 8+ and ensure kicad-cli is in PATH` and `ERROR: Placement not available: All strategies exhausted for phase='placement'`, producing 0.3% completion and no `packages/temper-placer/pipeline_execution.json`. The next step, "Generate HTML report", then crashes with an unhandled `FileNotFoundError` instead of failing cleanly. Unlike `python-tests.yml`/`regression.yml`, this workflow's job runs on bare `ubuntu-latest` with no `container: image: ghcr.io/bennetleff/temper-ci:latest` — i.e. it was never given `kicad-cli` in the first place, so the closure test's DRC step can never succeed here. Confirmed failing identically across every run checked today (spot-checked 8 runs from 01:31Z through 18:23Z, all `failure` on the same step) — this is chronic, not a one-off. |
| `metrics-trend-check.yml` | Weekly Metrics Drift Check | Run SPC check | **real code defect** | `pipeline_metrics: error: argument command: invalid choice: 'spc' (choose from trend, record)`. The workflow invokes a `spc` subcommand that the `pipeline_metrics` CLI does not implement (only `trend` and `record` exist). This is a workflow/script drift, not test flakiness — the script and its caller disagree about the CLI surface. Most recent completed run: 30261340546 (2026-07-27, weekly schedule; next scheduled run has not occurred since). |
| `regression.yml` | regression | KiCad DRC truth gate | **ambiguous — likely the same concurrent-edit noise as above, but not proven** | `FAIL: temper: DRC FAIL` — `track_dangling 29 > 28 (+1)`, one category one count over the ratchet ceiling. The gate's own output flags a caveat: `kicad-cli version mismatch -- running 10.0.5, ceiling measured with 10.0.4 (numbers may not be directly comparable)`. Given (a) the single-count margin, (b) the tool's own admission the ceiling and the measurement used different `kicad-cli` versions, and (c) the same concurrent `pcb/temper.kicad_pcb` editing already confirmed above, this reads as likely measurement noise from an in-flight PCB edit rather than a committed regression — but that is not proven here (no bisection was run, per the measurement-only constraint). **Recommend re-measuring once the concurrent PCB edit lands and the ceiling is refreshed**, rather than treating this as a confirmed new defect. |

Additional volatility note (not from the most-recent run, so not counted
above, but relevant to reading the rest of this table): `Cross-Source
Consistency Gates` → `MPN fabrication gate tests` intermittently failed
earlier today (runs 30469095061, 30468003194, 30442762922, 30442750259) on
`test_gate_flags_the_resonant_tank_capacitor_on_real_tree_today` — the test
asserts the gate must currently flag a real violation on today's tree
(`expected exit 3 ... got 0`). It was **not** failing in the most recent
completed run (30477654336) or several before it. This is a test that encodes
an assumption about the *live, mutable* state of the tree during a period of
heavy concurrent editing — it will keep flickering as long as something else
is actively changing the resonant tank capacitor's MPN/value. Not included in
the main table because it is not present in the most recent completed run,
per this document's stated method.

`firmware-perf-record.yml` deserves a mention even though its most recent
*completed* run is old (30369151889, 2026-07-28, conclusion `cancelled`): every
trigger since then (4 runs, 2026-07-29 06:21Z through 16:47Z) is still sitting
in `queued` with zero job progress. The workflow's own header comment is
explicit about why: `runs-on: [self-hosted, esp32]` — "Requires a self-hosted
runner with ESP32-S3 hardware attached... Deferred until hardware runner is
provisioned." **Classification: hardware** (needs a board/purchasing
decision) — exactly the category the task anticipated, just surfaced here as
"queued forever" rather than a clean failure, because no matching runner
exists to ever pick the job up.

### Known-expected reds — confirmed still exactly those two

Both re-verified against the most recent completed `python-tests.yml` run,
[30477654336](https://github.com/BennetLeff/temper/actions/runs/30477654336)
(created 2026-07-29T17:56:51Z, completed 19:13:25Z, headSha `a247227df7`):

| Job | Failing step | Classification | Confirmed detail |
|---|---|---|---|
| Board & Netlist Gates | Physical mains<->SELV isolation-barrier gate | **hardware / physical layout decision** | `Barrier zone NOT FOUND (name='MAINS_SELV_ISOLATION_BARRIER'). ... 0 other keepout zone(s) present`. Exact match to the task's expected description. |
| Requirements Tests (safety / EMC / review / DFM) | Requirements tests (safety / EMC / review / DFM) | **real code defect (placement), tracked** | `76 REQ-SAFE-01 clearance/creepage violations on the real board across 33 pair(s) (11 of the records are intra-footprint, i.e. unfixable by moving anything). Components matched: 158.` Exact match: 76 violations, 33 pairs, as expected. |

No other job failed in this run beyond the three discussed above (Provenance
& Anti-Vacuity Gates, Board & Netlist Gates, Requirements Tests). Every other
job in the run — Cargo/Rustc Smoke Check, Repo Hygiene & Import Gates, Rust
Checks, LOC Cap Gate, Cross-Source Consistency Gates, all four Invariant
tests jobs, Pipeline Closure Test, Extended Test Suites (still the old
combined job — this run predates the split), Generated Repo State, Core
Tests, Type Check — is `success` (A* 4x4 Exhaustive Verification (Nightly) is
`skipped`, expected for a non-nightly trigger).

### Full per-workflow summary (most recent completed `main` run of each)

| Workflow | Most recent completed run | Conclusion | In scope? |
|---|---|---|---|
| architecture-poster.yml | 30479671011 | success | yes |
| codeql.yml | 30479669976 | success | yes |
| corpus-batch.yml | 30191048126 (2026-07-26, weekly) | success | yes |
| dashboard-deploy.yml | 28344527122 (2026-06-29) | success | yes |
| docker-build.yml | 30382315437 | success | yes |
| firmware-perf-record.yml | 30369151889 (2026-07-28) | cancelled | yes — see hardware note above; every trigger since is stuck `queued` |
| firmware-tests.yml | 30472345267 | success | yes |
| golden-check.yml | 30479678141 | success | yes |
| health-digest.yml | 30262358012 (2026-07-27, weekly) | success | yes |
| lint-workflows.yml | 30479670322 | success | yes |
| metrics-reconcile.yml | 30482075277 | success | yes |
| metrics-record.yml | 30479669940 | **failure** | yes — new finding, see above |
| metrics-trend-check.yml | 30261340546 (2026-07-27, weekly) | **failure** | yes — new finding, see above |
| placer-regression.yml | 30479669771 | success | yes |
| python-tests.yml | 30477654336 | **failure** | yes — the two known-expected reds + attributable stale-provenance red |
| regression.yml | 30479669790 | **failure** | yes — see ambiguous finding above |
| release-please.yml | 30483303908 | success | yes |
| cp-sat-benchmarks.yml | — | — | excluded, `pull_request`-only trigger |
| human-reference-check.yml | — | — | excluded, `pull_request`-only trigger |
| pr-perf-check.yml | — | — | excluded, `pull_request`-only trigger |
| literal-removal-advisory.yml | — | — | excluded, `pull_request`-only trigger, never run |
| pr-pipeline-scorecard.yml | — | — | excluded, `pull_request`-only trigger, never run |
| release-artifacts.yml | — | — | excluded, `release: published`-only trigger, never run |

## Constraints honored

- No workflow, test, threshold, baseline, or gate file was modified. The only
  file created is this one.
- `pcb/temper.kicad_pcb`, `elec/src/modules.ato`,
  `power_pcb_dataset/drc_ceiling.json`, and `.github/workflows/*` were not
  touched.
- Every number above is cited to a specific `gh run view`/`gh run list`
  result; nothing was extrapolated or invented. Where data was thin (Part 1
  post-split), that is stated plainly rather than papered over.
- Work was done in a disposable worktree
  (`scratchpad/ci-health-wt`) off `origin/main`, on a fresh branch,
  never merged locally.
