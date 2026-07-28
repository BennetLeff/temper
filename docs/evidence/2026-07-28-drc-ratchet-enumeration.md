# DRC ratchet: fixing the early-return that hid every failing category but one

<!-- provenance: commit=7482c0f0c02fdd8c6e1dab2b2561d261867ebe39 dirty=UNKNOWN -->

**Date:** 2026-07-28
**Base commit:** `8838d524` (`docs/methodology-loop-discipline`)
**Fix commit:** `8e265fde` on `fix/drc-ratchet-enumeration` (this worktree)
**Board:** `pcb/temper.kicad_pcb`

## Falsifier, stated up front

> "Fixing the early return makes the six currently-invisible categories
> appear in the gate's output on the real board. If they still do not
> appear, the cause is not the early return and my diagnosis is wrong."

**The falsifier did NOT fire -- the fix produced the predicted effect.**
All six previously-invisible categories (`annular_width`,
`hole_clearance`, `hole_to_hole`, `tracks_crossing`, `drill_out_of_range`,
`via_diameter`) now appear in the real gate's output against the real
board, each explicitly tagged `[NEW]`, alongside the five regressed
categories (`clearance`, `shorting_items`, `solder_mask_bridge`,
`copper_edge_clearance`, `courtyards_overlap`) that were already knowable
from `violations_by_type` but were equally suppressed by the same early
return. A previously-invisible **aggregate warning ceiling breach**
(814 > 578) also surfaced as a side effect of removing the same
short-circuit -- it was not asked for by the falsifier, but it is the same
defect shape (the code never reached the warning check once the error
check had already triggered the early return).

## 1. The defect (confirmed)

`packages/temper-placer/src/temper_placer/regression/drc_ratchet.py`,
`_check_board()`, pre-fix (`8838d524`):

- Line 250: `if current_errors > entry.error_ceiling: return ...` -- returns
  immediately.
- Line 259: same shape for `current_warnings`.
- Line 275: the per-type loop, which correctly accumulates every violating
  rule -- but only runs if execution reaches it, which it never does once
  either aggregate check above has already returned.

Because the real board's aggregate error check (708-731, ceiling 85)
always trips first, the per-type loop -- and the warning-ceiling check --
never ran on this board, ever, regardless of what `violations_by_type`
recorded.

## 2. Before / after, real gate, real board (verbatim)

Both runs: `uv run --no-sync python scripts/ci_check_drc.py --backend kicad-cli`,
foreground, this worktree, board `pcb/temper.kicad_pcb` unchanged between
runs (only `drc_ratchet.py` differs).

### Before (commit `8838d524`, defect present)

```
DEBUG: Loading design_rules.py
FAIL: temper: DRC 708 exceeds ceiling 85 (+623 errors)
```

Exit code: 1. One line. No category is named. No warning check is even
reachable.

### After (commit `8e265fde`, fix applied)

```
DEBUG: Loading design_rules.py
FAIL: temper: DRC FAIL
  aggregate errors 731 exceeds ceiling 85 (+646)
  aggregate warnings 814 exceeds ceiling 578 (+236)
  per-type: 11 categories over ceiling (6 new, 5 regressed):
    [NEW] annular_width 4 > 0 (+4)
    [NEW] drill_out_of_range 4 > 0 (+4)
    [NEW] hole_clearance 24 > 0 (+24)
    [NEW] hole_to_hole 1 > 0 (+1)
    [NEW] tracks_crossing 2 > 0 (+2)
    [NEW] via_diameter 4 > 0 (+4)
    [   ] clearance 343 > 9 (+334)
    [   ] copper_edge_clearance 15 > 3 (+12)
    [   ] courtyards_overlap 11 > 10 (+1)
    [   ] shorting_items 169 > 33 (+136)
    [   ] solder_mask_bridge 154 > 30 (+124)
```

Exit code: 1 (unchanged -- the gate must still fail, and does).

The aggregate error count moved 708 -> 731 between the two runs. This is
the same kicad-cli run-to-run jitter already characterized in
`docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md` (N=5, range
705-731 on this exact board) -- not an effect of this fix, which touches
only how the result is reported, never the DRC computation itself. Both
numbers are inside the documented noise band.

## 3. What changed and why

### `DrcRatchetResult` gained structured fields, not a rewrite of its shape

Added `category_failures: list[DrcCategoryFailure]`,
`aggregate_error_delta: int`, `aggregate_warning_delta: int`, and populated
the previously-declared-but-dead `violation_deltas: dict[str, int]`
(`grep` before this change found no reader of that field anywhere in the
repo -- it was declared and never set). `DrcCategoryFailure` records
`rule`, `count`, `allowed`, and `is_new`.

`scripts/ci_check_drc.py` was checked (the only other consumer, besides
the test suite and the dataclass's own module) and reads exactly three
fields: `.passed`, `.message`, `.exit_code`. No CI workflow parses
`ci_check_drc.py`'s stdout beyond a static "regression suite executed"
blurb in `$GITHUB_STEP_SUMMARY` (`.github/workflows/regression.yml:128-129`)
-- it does not scrape per-line content. This means the structured fields
are additive: existing consumers are unaffected, and `.message` alone
still carries the complete report for anyone reading CI logs, while a
future step-summary table (or any other structured consumer) can read
`category_failures` directly instead of re-parsing text.

### Composing the message: multi-line, not one long joined line

At up to ~11 failing categories plus two aggregate lines, a single
semicolon-joined line (the old per-type style: `"rule1 c > a; rule2 c > a"`)
becomes a wall of text. The new format is one line per failing dimension,
indented under a one-line banner, with new categories visually grouped
first and tagged `[NEW]` vs `[   ]`:

```
{board_id}: DRC FAIL
  aggregate errors ... (if it failed)
  aggregate warnings ... (if it failed)
  per-type: N categories over ceiling (n_new new, n_regressed regressed):
    [NEW] rule count > allowed (+delta)
    [   ] rule count > allowed (+delta)
```

Each dimension line is only emitted if that dimension actually failed, so
a single-aggregate-only failure (or a per-type-only failure, as already
covered by the pre-existing tests) still reads as a short, unpadded
message -- the multi-line shape only grows when there is something to
report at each level, which is the exact quantity the falsifier's ~10
category case cares about.

### New vs. regressed categories are reported as visibly distinct facts

`drc_ceiling.json`'s own `_march` note is explicit that an absent category
has "an implicit ceiling of zero" by design -- that is a different claim
than "this category regressed past its recorded ceiling," because a new
category means the board grew a defect *type* the ratchet has never
tracked at all, not merely more of a kind it already watches. The fix
computes `is_new = rule not in entry.violations_by_type` per category and
sorts new categories first in the message, with an explicit `[NEW]` tag
and an `(n new, m regressed)` count in the summary line, rather than
interleaving them alphabetically and letting the reader work out which is
which from context.

### Exit-code semantics preserved

`exit_code=1` for any ceiling-exceeded failure, exactly as before, on
every path (aggregate-only, per-type-only, both). `detect_ceiling_raise`'s
`exit_code=2` path (ceiling raised without approval) is untouched --
this fix does not touch that method at all. No behavior change in when
the gate fails, only in what it prints when it does.

### Ceiling file untouched

`git diff 8838d524 8e265fde -- power_pcb_dataset/drc_ceiling.json` is
empty (verified below). No ceiling was raised, lowered, or otherwise
edited.

## 4. Regression tests: fail-before / pass-after, without `git stash`

Added `TestAggregateAndPerTypeEnumeration` to
`packages/temper-placer/tests/regression/test_drc_ratchet.py` (8 tests,
5 inherited unchanged from `TestPerTypeCeilings` plus 3 new: see below).
The decisive one is `test_aggregate_and_per_type_both_reported`, which
sets up a synthetic board exceeding both the aggregate error ceiling and
four per-type ceilings (two regressed, two brand-new) and asserts every
one of the six facts (aggregate line + 4 category lines + structured
fields) is present in a single result.

**Proof of fail-before/pass-after**, per the hard rule against
`git stash`: swapped the pre-fix source file in via
`git checkout <ref> -- <path>` (the ref being the parent commit, not a
stash), ran the new test class, then restored via
`git checkout HEAD -- <path>` (HEAD already pointed at the committed fix):

```
$ git checkout 8838d524 -- packages/temper-placer/src/temper_placer/regression/drc_ratchet.py
$ uv run --no-sync python -m pytest .../test_drc_ratchet.py::TestAggregateAndPerTypeEnumeration -v
...
test_aggregate_and_per_type_both_reported FAILED
  AssertionError: assert 'errors 497 exceeds ceiling 85' in
    'b: DRC 497 exceeds ceiling 85 (+412 errors)'
test_new_categories_are_labeled_distinctly_from_regressions FAILED
  AssertionError: assert '1 new, 0 regressed' in
    'b: DRC per-type ceiling exceeded -- via_diameter 4 > 0'
test_aggregate_warning_ceiling_reported_alongside_errors FAILED
  AssertionError: assert 'warnings 50 exceeds ceiling' in
    'b: DRC 50 exceeds ceiling 10 (+40 warnings)'
3 failed, 5 passed in 0.15s
```

Note the first failure's actual message: `'b: DRC 497 exceeds ceiling 85
(+412 errors)'` -- with the pre-fix code, none of `clearance`,
`shorting_items`, `annular_width`, or `hole_to_hole` appear anywhere in
that string, reproducing the exact real-board defect on a synthetic
fixture.

```
$ git checkout HEAD -- packages/temper-placer/src/temper_placer/regression/drc_ratchet.py
$ git status --short   # (empty -- tree matches HEAD)
$ uv run --no-sync python -m pytest packages/temper-placer/tests/regression/test_drc_ratchet.py -q
21 passed in 0.09s
```

21/21 (13 pre-existing + 8 in the new class, of which 5 are inherited
duplicates of `TestPerTypeCeilings`'s methods run again under the new
class name -- pytest collects inherited test methods, which is intentional
here since the new class subclasses the old one to reuse its `_entry`/
`_check` helpers).

## 5. Verification performed (all in this worktree, commit `8e265fde`)

Denominators stated per the hard rule.

| Check | Result |
|---|---|
| `scripts/check_domain_partition.py` | exit 0 |
| `scripts/capacity_budget_gate.py` | exit 0 |
| `scripts/mpn_fabrication_gate.py` | exit 0 |
| `scripts/check_derived_doc_drift.py` | exit 0 |
| `scripts/check_copper_net_consistency.py` | exit 0 |
| `scripts/check_rust_drc_presence.py` | exit 0 |
| `scripts/check_undeclared_imports.py` | exit 0 |
| `scripts/check_stale_extensions.py` | exit 0 (9/10 extensions fresh; `temper-constraints` missing but non-fatal locally -- `TEMPER_REQUIRE_FRESH_EXTENSIONS` unset, CI sets it; unrelated to this change) |
| `scripts/check_net_classification.py` | exit 0 |
| `make netlist` | exit 0 |
| `uv run --no-sync python -m pytest elec/validation -q` | **30/30 passed** |
| `uv run --no-sync python -m pytest packages/temper-placer/tests/regression/test_drc_ratchet.py -q` | **21/21 passed** |
| `git diff 8838d524 8e265fde -- power_pcb_dataset/drc_ceiling.json` | empty (ceiling file untouched) |
| `uv run --no-sync python scripts/ci_check_drc.py --backend kicad-cli` (final, post-fix, foreground) | exit 1, full 11-category enumeration (expected -- board genuinely exceeds ceiling; this is not a regression, it is the gate finally saying so completely) |

All exit codes were captured with direct redirection (`cmd > file 2>&1;
echo $?`), not through a pipe to another command, after an initial mistake
where several gates were checked via `cmd | tail -20; echo $?` -- which
captures `tail`'s exit status, not the gate's. All nine gates were re-run
with corrected capture and every one independently confirmed exit 0.

Environment note: this worktree had no `.venv` at all before this task
(fresh worktree checked out onto `8838d524`). `uv sync --all-packages`
(matching `.github/workflows/regression.yml`'s own setup step, not a bare
under-specified `uv sync`) was run once to build the initial environment;
every command after that used `uv run --no-sync` per the hard rule.

## 6. Design decisions not otherwise covered above

- **Why a dataclass (`DrcCategoryFailure`) instead of plain dicts/tuples
  in `category_failures`**: `is_new` needs a name, not a positional
  convention, given it is the single fact this task requires to be "loud."
  A `@property` for `delta` (`count - allowed`) avoids the alternative of
  computing and threading that arithmetic through two separate call sites
  (the message composer and any future structured consumer).
- **Why `violation_deltas` was populated rather than removed**: it was
  already part of the public dataclass shape and, being unread anywhere,
  removing it risked being read by this task's reviewers as scope creep
  (breaking a field name) rather than the additive change it should be.
  Populating it costs one dict comprehension and gives a flat
  `rule -> delta` view for a consumer that doesn't want the full
  `DrcCategoryFailure` list.
- **Why aggregate checks are still computed even when `current_by_type`
  is `None`** (the `rust` backend, which cannot break errors down): this
  matches pre-fix behavior exactly -- the rust backend path never had a
  per-type breakdown to lose, and this fix does not change what
  information that backend can supply, only whether the aggregate check
  it does supply gets to run to completion for kicad-cli.

## UNVERIFIED

- Whether any *other* out-of-repo CI consumer (a dashboard, a Slack
  notifier, anything outside this repo's own `.github/workflows/`)
  parses `ci_check_drc.py`'s stdout by line shape rather than treating it
  as opaque log text. Only in-repo consumers (`scripts/ci_check_drc.py`,
  the test suite, `.github/workflows/regression.yml`) were checked via
  `grep`.
- Long-run stability of the exact per-type counts shown in section 2's
  "after" run (`clearance` 343, `shorting_items` 169, etc.) -- these were
  captured from a single run and, per the already-documented jitter in
  `docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md`, are expected
  to vary run-to-run within roughly the same band; this document does not
  re-derive that jitter characterization, only confirms the categories
  the fix newly surfaces are the same six named in the discrepancy doc's
  investigation, plus the previously-undocumented aggregate-warning
  breach.
- `firmware/` and `scripts/manifest.yaml` were not touched by this change
  (confirmed via `git status`/`git diff` scoped to this task's edits);
  the sibling-agent collision warning in the task did not apply since no
  edit to either was needed.
