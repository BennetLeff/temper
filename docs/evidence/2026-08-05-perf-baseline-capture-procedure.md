# The perf-baseline capture procedure for the NO_BASELINE Wave-4 arms (2026-08-05)

<!-- provenance: commit=c5875adadca33875b6060132aa979a73c3e22669 dirty=false (base=origin/main c5875adadca33875b6060132aa979a73c3e22669; read-only investigation in the isolated worktree /private/tmp/wt5-perf on branch docs/wave4-perf-baseline-capture; working tree clean at measurement time; live CI evidence harvested from run 30963399407 (main push, #701 merge) and run 30963522090 (PR feat/wave4-phase3-write-engine-rust) -->

**Date:** 2026-08-05
**Scope:** Wave 4 program R2 — the performance A/B hard gate
(`.github/workflows/pr-perf-check.yml` + `benchmarks/perf_ab.py` +
`scripts/pr_perf_compare.py`). This document turns the human-in-the-loop
baseline append — the one step the harness deliberately leaves to a person —
into a precisely documented procedure, and records what a read-only
investigation found about the emit path for the arms that are currently
`NO_BASELINE` on `main`.

---

## Summary

`power_pcb_dataset/metrics/perf_ab_baseline.jsonl` contains **12 rows, all of
them `bottleneck-geometry`** (6 × `cell_capacity_batch`, 6 ×
`hard_blocked_batch`). `benchmarks/perf_ab.py` registers **13 arms**
(`perf_ab.py:849-863`), so **11 arms on `main` have no baseline row at all**:

| arm | added by |
|---|---|
| `loaders/loaders` | #712 (merge `adcc3e53f`) |
| `physics-emi/predict`, `physics-safety/filter_delay`, `physics-heat_removal/build_h_field`, `physics-copper_coverage/copper_masks`, `physics-tj_cross_check/device_cross_check`, `physics-parameter_bounds/classify` | #720 (merge `c6dff729b`) |
| `config-loader/preprocess_config`, `footprint-library/from_yaml_string` | #716 (merge `3400e7ecc`) |
| `parse-engine/parse_kicad_pcb` | #723 (merge `f24d96326`) |
| `board-netlist/contracts_construction` | #701 (merge `6290942be`) |

Because each of these arms exists on `main` (so it is classified
`NO_BASELINE`, not `NEW_BENCHMARK`), **every PR that touches the trigger
paths currently fails the hard gate closed** — verified live on PR run
`30963522090` (`feat/wave4-phase3-write-engine-rust`, after #701 merged),
which failed with exactly these 11 `NO_BASELINE` keys. This is the state the
capture procedure below unblocks.

The emit path itself is sound: the main-push / `workflow_dispatch` capture
runs emit all 13 arms with a real `git_commit` SHA (verified on run
`30963399407`, see Findings F1–F2), publish them inline and as an artifact,
and never write the baseline file — the append is the only missing piece, and
it is missing because the workflow deliberately keeps it human-in-the-loop.

---

## The capture procedure

### 0. The contract you are satisfying

The harness contract (`benchmarks/perf_ab.py:40-60`): **capture on CI, never
locally.** A darwin-captured baseline is ~-11% biased against the linux/x86_64
CI container and provably blinds the 20% margin to every regression in the
+20..+35% band. Every row in this procedure comes from the CI container via
`.github/workflows/pr-perf-check.yml`.

The width contract (`perf_ab.py:62-77`, `pr-perf-check.yml:241-243`): the
comparator medians the **trailing 5 rows** per `(module, board, stage)`
(`pr_perf_compare.py:46,137-163`). A key with fewer than 5 rows is unsmoothed
— the exact failure that turned a `typing.cast()` no-op into a +26.6%
"regression" on PR #544. **Target 5+ rows per arm; do not append a partial
batch** (see Finding F5 — the window test enforces ≥5 rows per key and will
flag a thin append).

### 1. Trigger the capture on `main` — 5+ times

Either trigger is valid; both run the identical command in the identical
container, so rows are comparable by construction.

- **On demand (recommended for a batch):**
  ```bash
  gh workflow run pr-perf-check.yml --ref main
  ```
  Repeat **5 times** (one per target row per arm). The workflow has a
  `workflow_dispatch` trigger (`pr-perf-check.yml:52`) and cancels
  in-progress runs per SHA (`pr-perf-check.yml:6-7`), so run them
  sequentially.
- **Passively:** wait for a `main` push that touches the trigger paths
  (`pr-perf-check.yml:40-48`: `packages/**`, `benchmarks/**`,
  `scripts/pr_perf_compare.py`, `scripts/tests/test_pr_perf_compare.py`,
  `power_pcb_dataset/metrics/perf_ab_baseline.jsonl`,
  `.github/workflows/pr-perf-check.yml`).

### 2. Harvest the rows from a completed run

```bash
gh run list --workflow=pr-perf-check.yml --branch main --limit 10
# pick a completed run; record its <run_id> and its head SHA:
gh run view <run_id> --json headSha

gh api "/repos/BennetLeff/temper/actions/runs/<run_id>/logs" > run-<run_id>.zip
unzip -p run-<run_id>.zip "0_PR Performance Comparison.txt" \
  | grep -o '{"schema_version": 2.*' > rows-<run_id>.jsonl
```

Each run emits **13 NDJSON records** — one per registered arm — in the
`PipelineMetricsRecord` shape (`perf_ab.py:866-894`):
`schema_version`, `timestamp`, `git_commit`, `board: "synthetic"`, `stage`,
`module`, and `metrics: {rust_over_oracle_ratio, rust_wall_us,
oracle_wall_us}`. The rows also appear inline in the job's step summary and as
the `perf-ab-baseline-rows-<run_id>-<run_attempt>` artifact
(`pr-perf-check.yml:231-255`); the log harvest above is the copy-paste-free
route.

### 3. Real-SHA verification (mandatory before any row is trusted)

```bash
python3 - <<'EOF'
import json, subprocess, sys
rows = [json.loads(l) for l in open("rows-<run_id>.jsonl")]
assert rows, "no records harvested"
commits = {r["git_commit"] for r in rows}
assert all(len(c) == 40 and c != "HEAD" and c != "" for c in commits), \
    f"defective git_commit values: {commits - {c for c in commits if len(c)==40 and c not in ('HEAD','')}}"
# every commit must resolve in the object store (mirrors check_evidence_provenance.py)
proc = subprocess.run(
    ["git", "cat-file", "--batch-check=%(objectname) %(objecttype)"],
    input="\n".join(sorted(commits)) + "\n", capture_output=True, text=True)
resolved = {line.split()[0] for line in proc.stdout.splitlines() if "missing" not in line}
assert commits <= resolved, f"unresolvable commits: {commits - resolved}"
print(f"{len(rows)} rows, {len(commits)} distinct commit(s): {sorted(commits)}")
EOF
```

This is the check that caught the #720 defect: 30 locally-measured physics
rows committed with `git_commit: "HEAD"` (removed in review commit
`fef34cc65`; zero `"HEAD"` rows remain in the baseline file — verified). The
emit path now records real SHAs (Finding F2), and this step confirms it per
harvest.

### 4. Validity check — the commit must not modify the benchmarked code

A row is a usable baseline sample only if the commit that produced it did not
modify the code the benchmark measures (`perf_ab.py:79-81`). For a
`workflow_dispatch` run against `main`, the measured SHA *is* a main tip, so
the row measures exactly the code it will baseline — valid by construction;
still verify the append PR itself touches only the baseline file. For a row
harvested from a main push, confirm the push's diff does not touch
`benchmarks/perf_ab.py` or the migrated kernels:

```bash
git show --stat <sha> | head -30
```

### 5. Append — all rows for all arms, in one reviewed PR

Accumulate the row files from **5+ runs** (13 arms × 5 runs = 65 rows), then
append them all in a single PR that touches nothing else:

```bash
cat rows-<run_id-1>.jsonl rows-<run_id-2>.jsonl ... >> power_pcb_dataset/metrics/perf_ab_baseline.jsonl
git add power_pcb_dataset/metrics/perf_ab_baseline.jsonl
```

Do **not** append one run at a time: a partial append (1–4 rows per arm)
leaves the new keys unsmoothed and trips the window test
(`test_pr_perf_compare.py:278-306`). Timestamps differ per row, so there is
no dedupe concern; just do not harvest the same run twice.

### 6. Post-append verification (in the PR branch)

First rebuild `main`'s registry file, exactly as the workflow does
(`pr-perf-check.yml:149-171` — AST-extract the `_BENCHMARKS` keys from
`origin/main`'s `benchmarks/perf_ab.py`):

```bash
git show "origin/main:benchmarks/perf_ab.py" > /tmp/main-perf-ab.py
python3 - <<'EOF' > /tmp/main-benchmarks.tsv
import ast, pathlib
src = pathlib.Path("/tmp/main-perf-ab.py").read_text()
tree = ast.parse(src)
for node in ast.walk(tree):
    if not isinstance(node, ast.AnnAssign):
        continue
    if getattr(node.target, "id", None) != "_BENCHMARKS" or not isinstance(node.value, ast.Dict):
        continue
    for k in node.value.keys:
        if isinstance(k, ast.Tuple) and len(k.elts) == 2:
            a, b = k.elts
            if isinstance(a, ast.Constant) and isinstance(b, ast.Constant):
                print(f"{a.value}\t{b.value}")
EOF
```

Then run the comparator against a **CI-produced** PR metrics file (harvest a
recent PR run's `0_PR Performance Comparison.txt` the same way as step 2 —
never run the harness locally):

```bash
python3 scripts/pr_perf_compare.py \
  --pr-metrics /tmp/pr-metrics.jsonl \
  --baseline-jsonl power_pcb_dataset/metrics/perf_ab_baseline.jsonl \
  --main-benchmarks /tmp/main-benchmarks.tsv
```

Expected outcomes, in order:

1. **Zero `NO_BASELINE` rows** — every previously-unbaselined arm now gets a
   real delta row. (Verified against the real file: before the append the
   comparator reports all 11 keys as `NO_BASELINE` and exits 1; after
   appending run `30963399407`'s 13 rows it reports deltas for all 13 arms,
   zero `NO_BASELINE`, and exits 0 — see Reproduction.)
2. **Every delta within margin** — `rust_over_oracle_ratio` is gated at
   `TIMING_MARGIN = 0.20` (`pr_perf_compare.py:57`). Use a PR metrics file
   from a *different* run than the appended rows so the deltas are non-zero
   and the ratio gate is actually exercised.
3. **The window test passes** — run the harness's own tests:
   ```bash
   python3 -m pytest scripts/tests/test_pr_perf_compare.py -q
   ```
   including `test_committed_baseline_fills_the_rolling_window`, which fails
   if any `(module, board, stage)` key has fewer than `DEFAULT_WINDOW` (5)
   rows.

Commit with a message naming the runs appended (e.g. `perf(ab): baseline
rows for the 11 Wave-4 NO_BASELINE arms from CI runs <ids>`), open the PR,
and merge. The workflow's own gate on that PR will confirm end-to-end: the PR
run emits the same 13 arms and compares them against the now-populated
baseline fetched from `main`.

---

## Findings

### F1 — The main-push / dispatch emit path covers ALL registered arms (no gap)

`run_benchmarks` iterates the full `_BENCHMARKS` registry with no per-arm
selection (`benchmarks/perf_ab.py:869`), and the workflow's "Run the
performance A/B" step has no event guard, so it runs on PR, main-push, and
`workflow_dispatch` (`pr-perf-check.yml:123-128`).

Live proof: run `30963399407` (main push, #701 merge, SHA
`6290942be7dd438308b73c95f619f7d24503f91f`) emitted **13/13 records** — all
11 currently-unbaselined arms plus the 2 baselined bottleneck-geometry arms.
There is no wiring gap here that needs a code change; the rows exist, they
just have not been appended.

### F2 — Real-SHA recording is in place; the `git_commit: "HEAD"` defect is gone (verified)

`MEASURED_SHA: ${{ github.event.pull_request.head.sha || github.sha }}`
(`pr-perf-check.yml:75`, introduced by #691 / `f2b09d846`) falls through to
the actual pushed/dispatched SHA on `push` and `workflow_dispatch`, and the
harness is invoked with `--commit "$MEASURED_SHA"` (`pr-perf-check.yml:126`).
All 13 records in run `30963399407` carry `git_commit:
"6290942be7dd438308b73c95f619f7d24503f91f"`.

The historical defect is fully cleaned: #720 originally committed 30
darwin-measured physics rows with `git_commit: "HEAD"`; review commit
`fef34cc65` ("drop local-darwin baseline rows; physics arms NO_BASELINE until
CI capture") removed all 30. The committed baseline today contains **zero**
`git_commit: "HEAD"` rows (verified by grep). Nothing to remove.

### F3 — Capture publishes rows; it never writes the baseline file (by design, no gap)

The capture steps (`pr-perf-check.yml:231-255`, guarded by
`if: github.event_name != 'pull_request'`) emit the rows twice — inline in the
job summary and as the `perf-ab-baseline-rows-<run>-<attempt>` artifact — and
explicitly do **not** auto-commit (`pr-perf-check.yml:216-230`): the baseline
is the bar a hard merge gate measures against, every appended row moves it,
and a row is only valid if its commit did not modify the benchmarked code — a
judgement no unattended push can make. The append is a reviewed PR. This
document is the procedure for that reviewed append.

### F4 — The `NO_BASELINE` set is 11 arms across 5 PRs, not 8 across 3 (premise correction)

The dispatch brief named three groups — loaders (#712), the six physics arms
(#720), board-netlist (#701). The baseline file (12 rows, all
`bottleneck-geometry`) shows the actual unbaselined set is **11 keys across 5
PRs**: the three named groups **plus** `config-loader/preprocess_config` and
`footprint-library/from_yaml_string` (#716) and `parse-engine/parse_kicad_pcb`
(#723). All five PRs landed their arms as `NEW_BENCHMARK` (reported, not
failed — `pr_perf_compare.py:193-221`), which is correct at merge time and is
exactly what produces the post-merge `NO_BASELINE` state. The capture batch
must cover all 11 keys.

Live proof of the resulting blocked state: PR run `30963522090`
(`feat/wave4-phase3-write-engine-rust`, after #701 merged) failed the hard
gate with exactly these 11 `NO_BASELINE` keys.

### F5 — The baseline-window test is dormant: `test_pr_perf_compare.py` runs nowhere in CI (gap)

`scripts/tests/test_pr_perf_compare.py` is listed as a trigger path of
`pr-perf-check.yml` (`:22, :46`) but the workflow contains **no pytest step**
(290 lines, read in full), and `python-tests.yml`'s pytest invocations never
include it (grep of every `pytest scripts/tests/...` line). So the 24 tests
that pin the gate's fail-closed behavior — including
`test_committed_baseline_fills_the_rolling_window`
(`test_pr_perf_compare.py:278-306`, asserts every baseline key has ≥5 rows)
— currently run nowhere except when a person invokes them.

That is why the capture procedure above makes running the window test a
mandatory step of the append PR. **Named follow-up F-CI-1 (code change, not
made here):** add a pytest step for `scripts/tests/test_pr_perf_compare.py`
to `pr-perf-check.yml` after "Install dependencies" (or add the file to a
`python-tests.yml` job), so a thin or regressed append fails CI instead of
landing silently. Once wired, the append policy "5+ rows per arm in the
landing PR" becomes enforced rather than conventional.

### F6 — `temper profile run --module all` is not on the perf path (verified, no gap)

The task asked where `temper profile run --module all --board temper --json`
is invoked. Nowhere on the gated path: the workflow replaced it with
`benchmarks/perf_ab.py` (`pr-perf-check.yml:112-116`), because
`profile_pipeline` timed a dataclass constructor (emitting `wall_time_ms: 0`)
and the router benchmark polluted the NDJSON stream. `perf_ab.py` is the only
producer.

### F7 — n-per-arm: the harness medians 9 in-process repeats; "5 rows" means 5 CI runs

`DEFAULT_WARMUP = 3`, `DEFAULT_REPEATS = 9` (`perf_ab.py:108-109`), and
`_time_us` returns the median of the 9 repeats (`perf_ab.py:130-144`), so
each emitted record is already a within-run median of 9. The 5+ row convention
is **not** internal to the harness — it is 5 separate CI runs accumulated in
the file, which is what the comparator's trailing-5 median
(`pr_perf_compare.py:46,137-163`) and the window test consume. The capture
procedure therefore repeats the trigger 5 times and appends the whole batch.
Margins are `TIMING_MARGIN = 0.20`, `COMPLETION_MARGIN = 0.10`,
`IMPROVEMENT_THRESHOLD = 0.10` (`pr_perf_compare.py:57-59`), justified by the
noise-floor measurement (`docs/evidence/2026-08-04-perf-ab-harness-noise-floor.md`:
sd 4.6%, worst excursion 9.9% vs a 20% margin). The capture procedure must
not disturb them — it does not.

---

## What this unblocks

Once the 11 arms have baseline rows (5+ each), on the next `main` fetch:

- **Every Wave-4 PR touching the trigger paths stops failing the perf gate on
  vacuity.** Today any `packages/**` PR is red with 11 `NO_BASELINE`
  failures (live: run `30963522090`); with rows present the same PR gets 13
  real delta rows and passes if within margin.
- **The gate starts actually covering the loaders, physics, config/parse,
  and board-netlist migrations.** `rust_over_oracle_ratio` regression
  protection (20% margin) is what the Wave-4 R1b discipline contract asks
  for; until rows land, these arms are reported but never gated.
- **The rolling median works again.** With 5 rows per key, CI run-to-run
  noise (≤9.9%) is smoothed — the fix that turned PR #544's +26.6% false
  positive into +15.7% pass applies to all 13 arms, not just
  `bottleneck-geometry`.

---

## Reproduction (what was actually verified for this document)

All verification was read-only, in the isolated worktree at
`/private/tmp/wt5-perf` (HEAD `c5875adad`, clean). No production file was
modified.

```sh
# 1. Harvest run 30963399407 (main push, #701 merge) — 13 records, real SHA
gh api "/repos/BennetLeff/temper/actions/runs/30963399407/logs" > run.zip
unzip -p run.zip "0_PR Performance Comparison.txt" | grep -o '{"schema_version": 2.*' > /tmp/pr-metrics.jsonl
# -> 13 records, all git_commit=6290942be7dd438308b73c95f619f7d24503f91f

# 2. Current state (baseline = committed file): all 11 new arms NO_BASELINE, exit 1
python3 scripts/pr_perf_compare.py --pr-metrics /tmp/pr-metrics.jsonl \
  --baseline-jsonl power_pcb_dataset/metrics/perf_ab_baseline.jsonl \
  --main-benchmarks /tmp/main-benchmarks.tsv

# 3. After appending the 13 harvested rows to a copy of the baseline:
#    zero NO_BASELINE, deltas for all 13 arms, gate passes (exit 0)
cat power_pcb_dataset/metrics/perf_ab_baseline.jsonl /tmp/pr-metrics.jsonl > /tmp/baseline-after.jsonl
python3 scripts/pr_perf_compare.py --pr-metrics /tmp/pr-metrics.jsonl \
  --baseline-jsonl /tmp/baseline-after.jsonl --main-benchmarks /tmp/main-benchmarks.tsv
```

(Step 3's deltas are +0.0% because the same run supplied both sides; in the
real procedure the PR metrics file comes from a different run, so deltas are
non-zero and the ratio gate is exercised.)

## Sources

- Capture/gate wiring: `.github/workflows/pr-perf-check.yml` (`:40-52` push +
  dispatch triggers, `:75` `MEASURED_SHA`, `:123-128` run step, `:133-172`
  PR-only baseline/registry fetch, `:203-210` PR-only hard gate, `:212-255`
  capture-only publish/upload, `:216-230` no-auto-commit decision).
- Harness contract and record shape: `benchmarks/perf_ab.py` (`:40-60`
  capture-on-CI contract, `:62-77` 5-row width, `:108-109` warmup/repeats,
  `:849-863` registry, `:866-894` `run_benchmarks`, `:897-931` CLI).
- Comparator classification and margins: `scripts/pr_perf_compare.py`
  (`:46` window, `:57-59` margins, `:137-163` median baseline, `:193-221`
  NEW_BENCHMARK vs NO_BASELINE, `:258-281` fail-closed gate).
- Window test and classification pins: `scripts/tests/test_pr_perf_compare.py`
  (`:278-306` window, `:318-328` NEW_BENCHMARK, `:331-342` NO_BASELINE,
  `:345-356` strict-degradation).
- Margin justification: `docs/evidence/2026-08-04-perf-ab-harness-noise-floor.md`;
  baseline history: `docs/evidence/2026-08-04-perf-ab-baseline-widening.md`.
- #720 darwin-row removal: commit `fef34cc65` ("drop local-darwin baseline
  rows; physics arms NO_BASELINE until CI capture (review P1-2)").
- Live runs: `30963399407` (main push, #701 merge — emit-path proof),
  `30963522090` (PR — 11-NO_BASELINE blocked-state proof).
