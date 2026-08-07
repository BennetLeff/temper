<!-- provenance: commit=7e1194b776aad76db2f1fd2a323defa0bebd5367 dirty=false -->

# Reference Oracle (kicad-cli) Sustained Throughput Baseline

**Date:** 2026-08-07
**Commit:** `7e1194b776aad76db2f1fd2a323defa0bebd5367` (worktree `agent-a155a16122a1f08e9`, clean)
**Purpose:** Measure the denominator for goal-set R7 ("sustained DRC/ERC check volume
exceeds what the reference oracle can sustain by at least an order of magnitude").
Nobody had measured `kicad-cli`'s own sustained throughput before this doc; the
WASM tier's throughput was already measured repeatedly (190,000 local invocations
at 3,379 inv/s — `docs/evidence/2026-08-07-phase1-u5-volume.md`; 25.4–32.9 tests/s
on Cloudflare Workers — `docs/evidence/2026-08-07-phase1-u8-multi-worker.md`), but
"10×" was meaningless without a measured baseline on the other side of the ratio.

## Bottom line

- **`kicad-cli` sustained DRC throughput on `pcb/temper.kicad_pcb`:** ~0.86–0.96
  whole-board checks/second single-process (~1.05–1.16 s/run); scales to ~5.6
  checks/second at 8 concurrent processes on this 12-core/24-thread machine, with
  scaling efficiency dropping from near-linear at 4 processes to ~73% at 8.
- **`kicad-cli` sustained ERC throughput on `pcb/temper.kicad_sch`:** ~1.8–2.4
  whole-schematic checks/second single-process (~0.42–0.54 s/run); scales to
  ~12.7 checks/second at 8 concurrent processes, efficiency dropping to ~66% at 8.
- **R7 as written is not well-posed.** The tier's published throughput figures
  (invocations/second, tests/second) count individual atomic rule-invocations —
  one Rust unit-test call testing one rule against one small input. `kicad-cli`'s
  throughput, measured here, counts whole-board passes — one process invocation
  that evaluates an entire board against dozens of rule categories and thousands
  of item-pairs, with no exposed counter for how many discrete rule evaluations
  happen inside that one pass. These are different units separated by an unknown
  (and, from the oracle side, unmeasurable) conversion factor. See "The unit
  problem" below for what a well-posed version of R7 would require.

## 1. Obtaining the pinned oracle (no root)

CI pins `kicad-cli 10.0.5` via the `kicad/kicad-10.0-releases` PPA
(`.github/docker/ci.Dockerfile:41`, `ARG KICAD_VERSION=10.0.5~ubuntu24.04.1`).

**This section fetches and executes an external, prebuilt binary package from
Launchpad/Ubuntu archive mirrors — the same package CI installs via `apt-get
install`, but obtained here without root by downloading and manually extracting
`.deb` archives, and run via `LD_LIBRARY_PATH` rather than system installation.**
Say this explicitly because it's a meaningfully different trust boundary than
"CI does this," even though the artifact is identical: no signature verification
beyond what `apt-get download` itself does against the configured archive, no
sandboxing beyond the invoking user's own privileges.

Procedure (matches what other agents in this sandbox had already done for this
same board — packages were verified and reused rather than re-fetched twice):

```bash
# Core KiCad + footprints from the pinned PPA (exact version match required)
apt-get download kicad=10.0.5~ubuntu24.04.1 kicad-footprints=10.0.5~ubuntu24.04.1

# Runtime deps not present on this base image, from the stock Ubuntu noble archive:
apt-get download libgit2-1.7 libnng1 libmbedtls14t64 libmbedx509-1t64 \
  libhttp-parser2.9 libwxgtk-webview3.2-1t64 libngspice0 \
  libocct-foundation-7.6t64 libocct-modeling-data-7.6t64 \
  libocct-modeling-algorithms-7.6t64 libocct-data-exchange-7.6t64 \
  libocct-ocaf-7.6t64

# Extract each .deb (no root — dpkg-deb -x writes into an arbitrary directory)
dpkg-deb -x <pkg>.deb <userspace-root>

# Run via LD_LIBRARY_PATH
LD_LIBRARY_PATH=<root>/usr/lib/x86_64-linux-gnu:<root>/usr/lib \
  <root>/usr/bin/kicad-cli version
```

**One additional dependency beyond the set above was needed and is worth
recording**: `_pcbnew.kiface` (the DRC/PCB engine) also requires
`libocct-visualization-7.6t64`, `libocct-draw-7.6t64`, and `occt-misc` — without
them `kicad-cli pcb drc` fails with `Failed to load shared library
'.../_pcbnew.kiface': libTKService.so.7: cannot open shared object file`. These
three were fetched the same way. Full package/version inventory actually used:

| Package | Version |
|---|---|
| kicad | 10.0.5~ubuntu24.04.1 |
| kicad-footprints | 10.0.5~ubuntu24.04.1 |
| libgit2-1.7 | 1.7.2+ds-1ubuntu3 |
| libhttp-parser2.9 | 2.9.4-6build1 |
| libmbedtls14t64 | 2.28.8-1 |
| libmbedx509-1t64 | 2.28.8-1 |
| libngspice0 | 42+ds-3build1 |
| libnng1 | 1.7.2-1build2 |
| libocct-data-exchange-7.6t64 | 7.6.3+dfsg1-7.1build1 |
| libocct-foundation-7.6t64 | 7.6.3+dfsg1-7.1build1 |
| libocct-modeling-algorithms-7.6t64 | 7.6.3+dfsg1-7.1build1 |
| libocct-modeling-data-7.6t64 | 7.6.3+dfsg1-7.1build1 |
| libocct-ocaf-7.6t64 | 7.6.3+dfsg1-7.1build1 |
| libocct-draw-7.6t64 | 7.6.3+dfsg1-7.1build1 |
| libocct-visualization-7.6t64 | 7.6.3+dfsg1-7.1build1 |
| occt-misc | 7.6.3+dfsg1-7.1build1 |
| libwxgtk-webview3.2-1t64 | 3.2.4+dfsg-4build1 |

Verified version before measuring:

```
$ kicad-cli version
17:11:58: Error: schema file '/usr/share/kicad/schemas/api.v1.schema.json' not found
10.0.5
```

The `schema file ... not found` line is benign — it's `kicad-cli`'s own API
schema validator complaining about a file that only ships with the full
`kicad` package's optional API server component, and it does not affect DRC/ERC.
It appears on every invocation below (elided from the tables for brevity) and
every run still exits 0 with a valid report.

**Exact version confirmed: `10.0.5`, matching `KICAD_VERSION` in
`.github/docker/ci.Dockerfile:41` exactly** — not just the major.minor.

## 2. Machine and load

- **Cores:** AMD Ryzen 9 5900X, 12 physical cores / 24 threads (SMT). `nproc` = 24.
- **Load throughout the measurement window:** load averages stayed in the
  **10.3–18.0 (1-min)** range across the entire run — this machine was **not**
  quiescent. It has been running many concurrent agents for hours (`uptime` at
  the start of this task: `up 4:40, load average: 15.24, 14.21, 12.64`). I did
  not find a quieter window during this task's execution; load never dropped
  below ~10 on 24 cores (i.e., never below ~40% of capacity already committed
  to other work) at any point I sampled, including immediately before, during,
  and after the harness ran.
- **Consequence:** every throughput figure below is a **lower bound** on what
  this hardware could sustain in isolation, most visibly in the parallel sweep
  (see §5) where scaling efficiency degrades faster than pure kicad-cli-vs-itself
  contention would predict, because 8 concurrent `kicad-cli` processes are
  competing with an already-present ~15-thread background load, not with an
  otherwise-idle 24-thread machine.
- Every measurement row below is stamped with the `/proc/loadavg` reading taken
  at that moment (1-min, 5-min, 15-min).

## 3. Method

Board files (unmodified, per task constraint): `pcb/temper.kicad_pcb`,
`pcb/temper.kicad_sch`.

**DRC** — matches `run_drc()` exactly (`packages/temper-placer/src/temper_placer/validation/_drc_api.py:474-491`)
except this measurement does **not** apply that function's single-thread pin
(`_single_threaded_kicad_env`, `MaximumThreads=1`). That pin exists for
determinism of the *violation count* on a byte-identical board (its own
comment cites "wall time is unaffected (~4.8s per run either way)" —
`docs/evidence/2026-08-04-drc-measurement-determinism.md`) and is specifically
irrelevant to a *throughput ceiling* measurement — a throughput question wants
`kicad-cli`'s real default behavior (its own internal `BS::thread_pool`,
sized to the machine), because that's what actually contends for cores when N
processes run concurrently, and that contention is exactly what "up to the
point of contention" (this task's brief) asks to characterize.

```
kicad-cli pcb drc --all-track-errors --format json --output <path> pcb/temper.kicad_pcb
```

**ERC** — no ERC runner exists in this repo to match, so flags follow
`kicad-cli sch erc --help` directly, requesting all severities:

```
kicad-cli sch erc --format json --severity-all --output <path> pcb/temper.kicad_sch
```

Both commands returned exit code 0 on every single-process run (violations are
reported in the JSON body, not via exit code — consistent with `run_drc()`'s
own comment that "kicad-cli returns 0 even with DRC errors").

**Two measurement phases per check type:**
1. **Sequential** (concurrency 1, one after another, n=15): establishes
   per-invocation wall-time distribution without any process-count confound.
2. **Parallel sweep** (concurrency ∈ {1, 2, 4, 8}, 3 repeated batches per
   level): launches `N` `kicad-cli` processes simultaneously via
   `subprocess.Popen`, each against its own output path, waits for all `N` to
   exit, and reports `N / batch_wall_time` as that batch's throughput.

Full harness: `/tmp/claude-1000/-home-bennet-Desktop-temper/4d2f49a7-f7d3-4b8d-b589-2d30d85392d3/scratchpad/r7_measure/harness.py` (scratchpad,
not committed — reproduction command is in §7). Raw per-run data:
`results.json` in the same directory.

## 4. DRC sequential results (n=15, concurrency 1)

| Metric | Value |
|---|---|
| Mean wall time | 1.161 s |
| Median wall time | 1.072 s |
| Stdev | 0.252 s |
| Min / Max | 0.986 s / 1.972 s |
| Violations found | 1624–1629 across runs (spread of 5) |
| Implied throughput (1/mean) | **0.861 checks/s** |

The 1624–1629 violation spread on a byte-identical, unmodified board matches
the known `clearance`-category nondeterminism documented in
`docs/evidence/2026-08-04-drc-measurement-determinism.md` (pointer-keyed dedup
containers) — expected and not a measurement artifact. `--all-track-errors` was
present on every run, so this is the same order of variance that doc's own
120-sample study reports, not the larger, unpinned-thread-pool variance.

## 5. ERC sequential results (n=15, concurrency 1)

| Metric | Value |
|---|---|
| Mean wall time | 0.543 s |
| Median wall time | 0.448 s |
| Stdev | 0.196 s |
| Min / Max | 0.365 s / 0.952 s |
| Violations found | 498 (identical on all 15 runs) |
| Implied throughput (1/mean) | **1.841 checks/s** |

The first ~5 sequential runs were slower (0.62–0.95 s) than the remainder
(0.37–0.45 s) — consistent with filesystem/page-cache warm-up for the
schematic hierarchy's sheet files, not measurement noise; the parallel-sweep
c=1 figure below (measured after this warm-up had already happened) is a
better estimate of steady-state single-process throughput.

## 6. Parallelism sweep

Each cell is the mean of 3 repeated batches at that concurrency; range shows
min–max across the 3 batches. `load` is `/proc/loadavg` sampled after the
batch completed.

### DRC (`pcb/temper.kicad_pcb`)

| Concurrency | Mean batch wall (s) | Throughput (checks/s) | Range (checks/s) | Speedup vs c=1 | Scaling efficiency | Load (1/5/15 min) |
|---|---|---|---|---|---|---|
| 1 | 1.046 | 0.959 | 0.911–1.034 | 1.00× | 100% | 16.6/16.9/14.6 |
| 2 | 1.368 | 1.494 | 1.218–1.736 | 1.56× | 78% | 18.0/17.2/14.8 |
| 4 | 1.210 | 3.314 | 3.105–3.443 | 3.46× | 86% | 17.2/17.0/14.7 |
| 8 | 1.438 | 5.617 | 4.876–6.017 | 5.86× | 73% | 16.7/16.9/14.7 |

### ERC (`pcb/temper.kicad_sch`)

| Concurrency | Mean batch wall (s) | Throughput (checks/s) | Range (checks/s) | Speedup vs c=1 | Scaling efficiency | Load (1/5/15 min) |
|---|---|---|---|---|---|---|
| 1 | 0.418 | 2.401 | 2.199–2.546 | 1.00× | 100% | 16.7/16.9/14.7 |
| 2 | 0.418 | 4.808 | 4.542–5.307 | 2.00× | 100% | 15.8/16.7/14.6 |
| 4 | 0.489 | 8.224 | 7.686–9.110 | 3.42× | 86% | 15.8/16.7/14.6 |
| 8 | 0.630 | 12.714 | 12.238–13.102 | 5.29× | 66% | 15.8/16.7/14.6 |

**Reading the curve:** both DRC and ERC scale close to linearly through
concurrency 4, then scaling efficiency drops at concurrency 8 (73% for DRC,
66% for ERC) — the visible "point of contention" the task asked to locate.
On an otherwise-idle 24-thread machine this point would likely sit higher
(each `kicad-cli` process's own internal thread pool is already competing with
~15 threads of *other* load throughout this run, per §2) — so 8 concurrent
processes is a demonstrated floor, not necessarily this hardware's ceiling.

**Sustained ceiling, best-measured cell:** DRC ~5.6 whole-board checks/second,
ERC ~12.7 whole-schematic checks/second, both at concurrency 8, both under
non-quiescent conditions.

## 7. The unit problem — is R7's "order of magnitude" well-posed?

**No, not as currently written**, and this is the central finding of this
document.

R7 says the tier's check volume must exceed "what the reference oracle can
sustain" by ≥10×. Making that comparison requires both sides to be counted in
the same unit. They currently aren't:

- **The tier's published numbers count atomic rule-invocations.** U5's
  "190,000 invocations at 3,379 inv/s" (`docs/evidence/2026-08-07-phase1-u5-volume.md`)
  is 95 registered Rust test functions × 2,000 repetitions — each "invocation"
  is one call to one `#[test]` function that exercises one rule against one
  fixed, synthetic input (mean 0.28 ms, **median 0.0012 ms** per invocation —
  consistent with a tight, allocation-free function call, not board-scale
  work). The Workers figures (25.4–32.9 "tests/s", `docs/evidence/2026-08-07-phase1-u8-multi-worker.md`)
  are the same unit, measured over HTTP instead of locally.
- **`kicad-cli`'s only directly measurable unit is a whole-board pass.** One
  DRC invocation evaluates the *entire* `pcb/temper.kicad_pcb` — 1,624–1,629
  violations found per run, drawn from dozens of distinct DRC rule categories
  (clearance, shorting, track crossings, unconnected items, etc.) applied to
  thousands of item-pairs across the whole board — in a single ~1.1 s process.
  `kicad-cli` does not expose a counter for how many discrete rule evaluations
  (as opposed to violations *found*) happen inside that pass; the JSON report
  lists only violations, not the (presumably much larger) set of checks that
  passed. There is no instrumentation point available from outside the binary
  to recover that count without building KiCad from source with added
  counters — out of scope here, and arguably out of scope for a throughput
  baseline in general.

These are not the same denomination, and there is currently no measured
conversion factor between them. Dividing "3,379 inv/s" by "0.86 checks/s"
produces a number (≈3,929×) that looks like a slam-dunk 10× claim, but it's an
artifact of comparing a microsecond-scale atomic operation against a
second-scale whole-board pass — it says nothing about whether the tier
actually checks a board's worth of rules 3,929 times faster than `kicad-cli`
does, because nobody has established how many tier "invocations" are needed to
cover what one `kicad-cli` DRC pass covers.

**What a well-posed R7 would need**, in decreasing order of rigor:

1. **Board-equivalents/second** (best option): define "one board-equivalent"
   as the full set of tier rule-invocations required to check one instance of
   `pcb/temper.kicad_pcb` (respectively `pcb/temper.kicad_sch` for ERC) end to
   end, then measure both systems' throughput in board-equivalents/second.
   This document establishes the oracle side of that ratio directly (§6, in
   real whole-board passes/second — no conversion needed on this side). The
   tier side is **not measured here** (out of this task's scope, and this task
   was explicitly told not to run the tier at volume) — it requires knowing
   how many of the tier's rule-invocations fire when checking this specific
   board, which the tier's own harness would need to report (e.g.,
   instrumenting `run_wasm_tests.mjs` or the Rust rule-kernel driver to count
   invocations against a real board input rather than fixed unit-test
   fixtures).
2. **Rule-evaluations/second**, if `kicad-cli` were built with an added
   internal counter — rejected here as out of scope (rebuilding KiCad from
   source with instrumentation is a materially larger undertaking than this
   baseline task, and the task's own framing ranks a defensible "not
   measurable as written" above "a number that flatters the tier").
3. **State both raw throughputs in their native units with the caveat made
   explicit** (what this document does) — defensible as a *baseline*, but
   insufficient on its own to resolve R7's pass/fail, because "checks/second"
   means two different things on the two sides of the inequality.

**Judgment:** R7 as currently phrased cannot be evaluated, in either
direction, until it is restated in a unit both systems can be measured
against — board-equivalents/second is the only candidate identified here that
is both operationally meaningful (it's what a CI gate actually cares about:
how many complete board check-passes fit in a given wall-clock budget) and
measurable on both sides without rebuilding either system. This document
supplies the oracle half of that measurement; the tier half remains open.

## 8. Reproduction

```bash
# From a machine with network access, no root required:
mkdir -p /tmp/kicad-oracle-baseline/debs /tmp/kicad-oracle-baseline/root
cd /tmp/kicad-oracle-baseline/debs
apt-get download kicad=10.0.5~ubuntu24.04.1 kicad-footprints=10.0.5~ubuntu24.04.1 \
  libgit2-1.7 libnng1 libmbedtls14t64 libmbedx509-1t64 libhttp-parser2.9 \
  libwxgtk-webview3.2-1t64 libngspice0 libocct-foundation-7.6t64 \
  libocct-modeling-data-7.6t64 libocct-modeling-algorithms-7.6t64 \
  libocct-data-exchange-7.6t64 libocct-ocaf-7.6t64 libocct-draw-7.6t64 \
  libocct-visualization-7.6t64 occt-misc

for f in *.deb; do dpkg-deb -x "$f" /tmp/kicad-oracle-baseline/root; done

export LD_LIBRARY_PATH=/tmp/kicad-oracle-baseline/root/usr/lib/x86_64-linux-gnu:/tmp/kicad-oracle-baseline/root/usr/lib
KICAD_CLI=/tmp/kicad-oracle-baseline/root/usr/bin/kicad-cli
$KICAD_CLI version   # must print 10.0.5

$KICAD_CLI pcb drc --all-track-errors --format json --output /tmp/drc.json pcb/temper.kicad_pcb
$KICAD_CLI sch erc --format json --severity-all --output /tmp/erc.json pcb/temper.kicad_sch
```

For the full timing harness (sequential + parallel sweep), see
`harness.py` referenced in §3; it is a plain Python script using
`subprocess.run`/`subprocess.Popen` and `time.perf_counter()`, no
dependencies beyond the standard library.

## Constraints observed

- `pcb/temper.kicad_pcb` and `pcb/*.kicad_sch` were not modified — every
  measurement run wrote its JSON report to a scratch path outside the repo and
  deleted it immediately after reading.
- `power_pcb_dataset/drc_ceiling.json` was not touched.
- No WASM Worker was deployed or invoked; the tier was not run at volume by
  this task.
