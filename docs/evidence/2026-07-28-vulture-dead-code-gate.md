# Vulture dead-code gate + F401: what was dead, what was pre-existing

<!-- provenance: commit=e0af5e467b45114c677b84cc9fdab8ca178be564 dirty=UNKNOWN -->

**Date:** 2026-07-28
**Scope:** `packages/temper-placer/tests/requirements/safety/_real_board_fixture.py`,
`packages/temper-placer/tests/router_v6/test_dfm_interaction.py`,
`deadcode-baseline.py`.
**Trigger:** `Repo Hygiene & Import Gates` failed on main for the first
time it was actually reachable -- it sat behind an unrelated failure in the
old 66-step job and was never exercised until `perf(ci): split Core Tests
so one red gate stops hiding 33 others` (`3ba5cf81`) separated the jobs.

---

## Two unrelated symptoms, one shared line

The ruff step reported (among 32 total findings):

```
F401 [*] `check_domain_partition.GateError` imported but unused
  116 |     GateError,
```

The vulture step reported, and failed the job on:

```
=== NEW DEAD CODE (not in baseline) ===
  packages/temper-placer/tests/requirements/safety/_real_board_fixture.py:115: GateError
  packages/temper-placer/tests/router_v6/test_dfm_interaction.py:911: unreachable 'else' block
```

Line 115/116 in `_real_board_fixture.py` is the same import both tools are
flagging: `from check_domain_partition import (GateError, Manifest, ...)`.
Ruff reports the name's own line (116); vulture reports the statement's
opening line (115). One fix (below) satisfies both.

---

## 1. The F401 -- traced, not assumed

**Question:** is this a consequence of today's `c59589b0`
("feat(gates): decide netlist freshness by content hash, not mtime"),
which touched `scripts/check_domain_partition.py` and
`scripts/tests/test_check_domain_partition.py` earlier today? **No.**

`git log --follow -p` on `_real_board_fixture.py` shows the
`from check_domain_partition import (...)` block, including `GateError`,
was introduced by `70503e6d` ("fix(safety): close domain-clearance
coverage gap, fail closed on unclassified-near-HV"), dated 2026-07-27 --
one full day before `c59589b0`. `c59589b0` never touched this file. The
import has been unused since the day it was written, not since today.

**Was it "unused because something that should use it was dropped"?**
Checked directly: grepping the whole file's history for `GateError` finds
exactly two hits at every revision since `70503e6d` -- the import itself,
and one comment:

```python
# Intentionally NOT wrapped in try/except GateError: a GateError here
# (e.g. a declared net that no longer exists in the compiled netlist)
# means the manifest and the compiled design have drifted apart -- a
# real defect that must fail this test loudly, not be swallowed into a
# skip (which would look identical to "everything is fine, nothing to
# check").
```

The comment is explicit: this code was deliberately written to *let*
`GateError` propagate uncaught, not to catch it. There is no dropped
`except GateError` clause to restore -- the import was pulled in
alongside six other names from the same module and never had a use.
Confirmed correct to delete, not a masked bug. Removed from the import
list; the six other names (`Manifest`, `Netlist`, `build_name_to_code`,
`load_manifest`, `parse_netlist`, `resolve_chain_refs`) are all used
elsewhere in the file (verified by grep before removing anything).

### "Found 32 errors" -- which of the 32 must be zero?

`.github/workflows/python-tests.yml`'s `hygiene-gates` job:

```yaml
- name: Lint with ruff
  continue-on-error: true  # TODO: temper-NNN -- 594 pre-existing ruff errors; hard-fail after 2026-09-01
  run: uv run ruff check packages/
```

`continue-on-error: true` means **none** of the 32 findings can fail this
job -- the step's own exit code is discarded by GitHub Actions regardless
of content. The job's actual failure came entirely from the next,
non-soft step, `Vulture dead-code gate` (no `continue-on-error`, exits 3
on new dead code). The ruff step is informational until the stated
2026-09-01 hard-fail date; it is not currently a gate. This F401 was still
worth fixing on its own merits (real unused import, zero behavior risk),
but it was never the thing blocking CI. `uv run ruff check packages/`
(the exact CI invocation) drops from 32 to 31 findings after this fix --
the other 31 are the pre-existing, tracked backlog, confirmed unrelated
by running the same command against `git stash`-restored originals.

---

## 2. Vulture "NEW dead code" -- both items examined for reachability

`scripts/vulture_gate.py` runs vulture twice against `packages/` (raw, and
against `deadcode-baseline.py` as a suppression file), diffs the two
result sets against the baseline file's own parsed entries, and buckets
into `new` (`reported - baseline`, exit 3), `stale` (`baseline - raw`,
exit 4), and `matched` (suppressed, silent). A finding is "NEW" purely by
`(file, line, name_or_kind)` tuple identity -- if a genuinely pre-existing,
already-reviewed finding's line number shifts because of unrelated edits
elsewhere in the file, it drops out of `matched` and appears as one `NEW`
entry plus one `STALE` entry for the old line, even though nothing
new was introduced. Both of today's findings were checked against this
possibility before deciding delete vs. baseline.

### Item 1: `_real_board_fixture.py:115: GateError` -- same root cause as the F401

Vulture's "unused import" detection here is the same fact ruff's F401
reports. Fixed by the single import-list edit above; nothing to baseline.

### Item 2: `test_dfm_interaction.py:911: unreachable 'else' block`

The paired `STALE` entry
(`# unreachable 'else' block (...test_dfm_interaction.py:898)`) was
already in `deadcode-baseline.py` before today. `git show e43d6540 --stat`
(today's earlier "repair 19 invariant-suite failures" commit, unrelated to
the freshness work) shows this file gained 47 lines / lost 34 elsewhere,
shifting the same construct from line 898 to 911. Confirmed identical
construct, not a new one, by reading both revisions:

```python
def test_error_can_be_caught_as_runtime_error(self):
    """Catching RuntimeError also catches ManufacturingDRCViolationError."""
    try:
        raise ManufacturingDRCViolationError("test")
    except RuntimeError:
        pass  # expected
    else:
        pytest.fail("RuntimeError should have caught the exception")
```

**Reachability check (why this is genuinely dead, not a vulture false
positive requiring baseline treatment):**
`ManufacturingDRCViolationError(RuntimeError)` --
confirmed at `packages/temper-placer/src/temper_placer/router_v6/_pipeline_types.py:99`,
and asserted by the adjacent test
`test_error_is_runtime_error_subclass`. The `raise` two lines above is
unconditional (no branch, no loop), so `except RuntimeError` always
matches and the `try` never completes without raising -- the `else`
clause's precondition ("no exception was raised") can never hold. This is
not a dynamic-dispatch/plugin/fixture case vulture is blind to; it is
ordinary, provable control flow. If `ManufacturingDRCViolationError` ever
stopped subclassing `RuntimeError`, the `raise` would propagate uncaught
and pytest would report this test as an **error** (not a silent pass) --
the same failure signal the `else: pytest.fail(...)` was trying to
provide, just via a different pytest outcome bucket. The `else` added no
coverage the bare `except` doesn't already give.

**Decision: delete, not baseline.** Removed the `else` clause and its
`pytest.fail(...)` call; kept the docstring, extended with the reachability
argument above so a future reader doesn't reintroduce it. This is a
genuine simplification, not a coverage loss -- verified by running the
test both before and after (see below).

**Baseline cleanup:** the now-stale `:898` baseline entry was removed
(the construct it pointed at no longer exists anywhere in the file, having
been deleted rather than merely moved). No new baseline entry was added
for line 911 -- there is nothing left there to suppress.

### `deadcode-baseline.py` delta, precisely

- **Removed:** 1 line --
  `# unreachable 'else' block (packages/temper-placer/tests/router_v6/test_dfm_interaction.py:898)`.
  Reason: the code it pointed at was deleted (see above), not moved; the
  line is stale, not a false positive to keep suppressing.
- **Added:** 0 lines. Neither vulture finding in this task was a false
  positive -- both were genuinely dead (an unused import; a provably
  unreachable `else`) -- so nothing new needed a baseline entry.
- Net effect: 58 entries -> 57 entries, no new suppressions.

---

## Scope: why a safety fixture and a DFM test, and why that's safe

Both edits were reached by following the vulture/ruff output directly, not
chosen up front:

- `_real_board_fixture.py` is where ruff's F401 and one of vulture's two
  `NEW` findings point -- the same import statement, same line. Nothing
  else in that file was touched.
- `test_dfm_interaction.py` is where vulture's other `NEW` finding (paired
  with the `STALE` baseline entry at the old line number) points.

**Reachability, not assumption, decided each one:**

- `GateError`: grepped the file's entire history since the import was
  introduced (`70503e6d`, 2026-07-27) for every mention of the name. Two
  hits, always: the import, and a comment explicitly stating the code
  deliberately does *not* catch it (`# Intentionally NOT wrapped in
  try/except GateError: ...`). No `__all__`, no re-export, no
  string-based/dynamic lookup of the name anywhere in the tree
  (`grep -rn "GateError" packages/ scripts/` was run and every hit
  inspected, not sampled). Nothing depends on this import existing.
- The `else` block: `ManufacturingDRCViolationError` is confirmed, by
  reading `_pipeline_types.py:99` directly, to subclass `RuntimeError` --
  the same fact the adjacent `test_error_is_runtime_error_subclass` test
  independently asserts. The two-line `try` body is an unconditional
  `raise` with no branch, no loop, no fixture, no parametrization, no
  dynamic dispatch -- ordinary straight-line control flow a human can
  verify by inspection, which vulture also gets right here (this is not
  one of the dynamic-dispatch/plugin/`pytest.fixture` cases vulture is
  known to misjudge). Not a workaround for a failure: the test passed
  before this edit and passes after it (see below), because the `else`
  branch never ran in either version.

**Neither edit changes measurement scope or outcome in
`packages/temper-placer/tests/requirements/`.** The safety fixture edit
touches only an import list -- zero logic, zero behavior change. Verified
directly, not assumed: built the real netlist locally (`make netlist`,
absent from this sandbox until this check, hence why earlier `pytest`
runs against `requirements/` upstream had silently skipped 6 real-board
tests instead of exercising them) and ran
`packages/temper-placer/tests/requirements/` both with and without this
branch's changes (`git stash push -u -- <the 4 changed files>`, rerun,
`git stash pop`). Identical result both times, byte-for-byte:

```
1 failed, 260 passed, 5 skipped
FAILED .../test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance
AssertionError: 9 REQ-SAFE-01 clearance/creepage violations on the real board (components matched: 158)
```

Same 9 violations, same component-match count, same pass/skip/fail
tallies before and after. This edit does not touch, mask, or alter that
real, pre-existing hardware finding in any way.

**Not geometry-adjacent.** Neither edited file is under
`packages/temper-placer/src` (where the concurrent `fix/pad-geometry-model`
branch is rewriting the pad-geometry model). `_real_board_fixture.py`
calls `parse_kicad_pcb` for component positions and nothing from a pad-
geometry model; `test_dfm_interaction.py` exercises DRC-report aggregation
(creepage/clearance/copper-balance report objects), not pad geometry
itself. No overlap to flag.

---

## Verification

```
$ uv run ruff check packages/temper-placer/tests/requirements/safety/_real_board_fixture.py \
    packages/temper-placer/tests/router_v6/test_dfm_interaction.py
All checks passed!

$ uv run ruff check packages/          # exact CI invocation
Found 31 errors.   # was 32; the fixed F401 is gone, rest is the tracked pre-existing backlog

$ uv run python scripts/vulture_gate.py
Vulture gate PASSED — 56 known finding(s) suppressed, 0 new, 0 stale

$ uv run python scripts/check_vacuous_gates.py
Anti-vacuous-truth gate passed. Scanned 542 file(s) ... 0 violations.

$ uv run pytest packages/temper-placer/tests/requirements/safety/ -q   # (no local netlist, real-board cases skip)
53 passed, 1 skipped

$ make netlist && uv run pytest packages/temper-placer/tests/requirements/ -q   # (real netlist built, real-board cases run)
1 failed, 260 passed, 5 skipped   # identical with and without this branch's 4 changed files (git stash proof above)

$ uv run pytest packages/temper-placer/tests/router_v6/test_dfm_interaction.py -q
34 passed, 1 failed  # TestAllModulesFail::test_all_seven_raise_still_produces_report

$ uv run pytest scripts/tests/test_check_domain_partition.py -q
36 passed
```

The one `test_dfm_interaction.py` failure
(`TestAllModulesFail::test_all_seven_raise_still_produces_report`) is
pre-existing and unrelated: reproduced against the unmodified file
(`git stash` the three files this change touches, re-run, same single
failure, `git stash pop` to restore) before touching anything here. Not
fixed as part of this task -- out of scope for a vulture/F401 cleanup, and
already a pre-existing failure independent of both today's freshness
change and this change.

## Explicitly out of scope / not attempted

- `test_all_seven_raise_still_produces_report`'s pre-existing failure --
  confirmed unrelated by reproducing on the unmodified tree; a real defect
  but a different one.
- The other 31 pre-existing `ruff check packages/` findings -- tracked by
  the job's own TODO (`temper-NNN`, hard-fail after 2026-09-01), not
  introduced or touched here.
- `deadcode-baseline.py`'s own `ruff check` findings (`B018`/`F821` on
  every line) -- that file is a data file for `vulture_gate.py`'s parser,
  never a target of `ruff check packages/` (it lives at repo root, outside
  `packages/`), and pre-dates this change.
