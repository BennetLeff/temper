<!-- provenance: commit=3dd0f80440500113c736be0d67a9d75cdf80db82 dirty=false -->

# Measurement instruments that lie: a catalog of mis-set-up instruments that produced wrong conclusions

**Date:** 2026-08-19 (catalog consolidated from AGENTS.md; incidents span 2026-07-25 to 2026-08-18)
**Status:** living catalog — add new instrument failures here; keep the condensed signatures in AGENTS.md

Every instrument below produced a wrong conclusion that someone acted on.
They are recorded here because agents kept re-deriving them from scratch,
one session at a time.

**A number from a mis-set-up instrument is indistinguishable from a real
result.** In a single day these manufactured five phantom test failures, one
invalid baseline, a regression that never existed, and two hypotheses that
sent whole investigations down dead ends.

## DRC / kicad-cli

### `pcb/temper.kicad_dru` is gitignored and generated

Without regenerating it (`scripts/generate_kicad_dru.py`), **creepage reads
0** and clearance reads a different count entirely. Regenerate before any
DRC run. It also regenerates to a different byte size than any committed
copy.

### `_drc_api.run_drc(Path)` is necessary but NOT sufficient

The *board file* needs an `fp-lib-table` sibling. Without one,
`lib_footprint_issues` reads exactly the board's footprint count (168) and
`lib_footprint_mismatch` reads 0, **even through the correct API**. With
`pcb/fp-lib-table` beside it: 168 -> 16, mismatch -> 25. That 168/0 pair is
the signature; if you see it, your harness is wrong, not the board.

### kicad-cli saturation caps

`ERROR_LIMIT` = 199, `EXTENDED_ERROR_LIMIT` = 499. A count of **exactly**
199 or 499 is a cap, not a count.

### kicad-cli is nondeterministic run-to-run

Run 3x and intersect. Observed spreads: creepage {105,106,107}, total
{777,778}, and `shorting_items` rows whose net order swaps (`nets A and B`
vs `nets B and A`) — normalize before diffing or you will "find" changes
that are not there.

### kicad-cli reports one creepage violation per NET PAIR, not per pad pair

Clearing one pair unmasks another that was hidden behind it. Expect new
rows between parts you did not touch, and do not attribute them to your
change without checking. `DrcResult` exposes
`.error_count`/`.warning_count`/`.errors`/`.warnings` (not `.counts`);
`DrcError` exposes `.rule`/`.nets`/`.message`/`.items`. **Diff the
violation SETS, not the counts.**

### Ad-hoc DRC harnesses must copy the library table, not just the sidecars (2026-08-18)

A DRC scratch harness that copies only `temper.kicad_pcb` and
`temper.kicad_pro` — and points `KICAD_CONFIG_HOME` at an empty directory —
silently fails to resolve **every footprint on the board**.

The symptom is distinctive and worth memorising: **`lib_footprint_issues`
reads exactly the board's total footprint count** (168 here), and
**`lib_footprint_mismatch` reads 0**. A number equal to 100% of the
population is a resolution failure, not a census. The second reading is the
tell for the first — a footprint that never resolved cannot register as
*mismatched* against a library it never found, so the pair is corrupted in
opposite directions at once.

Measured, three controlled runs on the same board:

```
fp-lib-table + libs/   KICAD_CONFIG_HOME    lib_footprint_issues
       no                    empty                  168
      yes                    empty                  165
      yes                   seeded                   13   <- the truth
```

`KICAD10_FOOTPRINT_DIR` is **not** an OS environment variable. It is
defined inside `kicad_common.json`, under `KICAD_CONFIG_HOME`.

**`_drc_api._single_threaded_kicad_env` already does this correctly.** The
production path has never been wrong. Ad-hoc harnesses copied its
thread-pinning and not its environment construction — so mirror the whole
function, or better, call it.

Cost: this artifact was reported and repeated for hours as "the largest
unexplained DRC regression" and blocked a ceiling re-baseline, when the
stored ceiling of 13 had been correct the entire time.

**The deltas survived, the absolutes did not.** Because the error is
constant across a before/after pair, category *deltas* measured this way
remain valid; only *totals* are inflated. If you inherit a DRC total from a
document, check how it was measured before trusting it.

## Build / environment

### `make extensions` fails hard when `CONDA_PREFIX` is set

maturin refuses when it coexists with `VIRTUAL_ENV`. Use
`env -u CONDA_PREFIX`. A silent failure here left an extension unbuilt and
manufactured **5 phantom test failures** that read as real creepage
regressions.

### A stale `.so` fails loudly, not subtly

`AttributeError: module 'temper_rust_router' has no attribute '...'`.
`scripts/check_stale_extensions.py` reports which crates are stale. Any PR
that changes a pyo3 boundary leaves every unrebuilt checkout broken,
including CI's typecheck stubs.

### `scripts/check_venv_integrity.py` false-positives from worktrees nested under `.claude/worktrees/`

`classify_path` lets `other_worktrees` win because the main checkout is a
string prefix. It reports all editable installs as violations while
printing paths that are correct.

## Test harness

### Set pytest timeouts above 1200s for full-route tests

`test_route_pcb_production_board` needs ~1193s; a 900s cap manufactured a
"20th failure" that could not have passed on any branch.

### Hypothesis replays counterexamples from its example DB

A test that fails only on your branch may be replaying a stored case. Clear
the DB before concluding you caused it — and if the counterexample is real,
it deserves its own ticket rather than being written off as flake.

## Figures that look measured and are not

### `attempted_ripups` is a hardcoded literal

(`_astar_nlayer.py` `record_failure`), on a single-pass loop with no rip-up
mechanism. Every net reports 0. It is not evidence about displacement of
committed copper.

### `RouteProfileStats.python_time_ms` is structurally always 0.0

Since the Python search path was removed — and is still published as
`maze_router_python_ms`.

### A 16-character digest prefix is not a 64-character claim

Compare full digests programmatically. Note also that after a **squash**
merge the branch SHA is never an ancestor of `main` — that is expected, not
lost work.

## The general rule

**When a measurement contradicts a change you just made, suspect the
measurement before the change.** And when relaying someone else's number,
check whether it was measured or inherited — several figures that
circulated for a full day ("271 calls per route", "attempted_ripups == 0",
"the 200k budget cap") turned out to have no committed measurement behind
them.
