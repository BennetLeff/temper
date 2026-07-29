---
title: "Falsify the fix before believing it — a new gate or repair has to fail on its own motivating input, not just pass"
date: "2026-07-29"
category: best-practices
module: development_workflow
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - "writing a new drift/staleness/regression gate and it passes on the first run"
  - "the 'obvious' fix for a broken import or reference is to restore what was removed, rather than to check how the value is bound"
  - "a repair's own falsifier was flagged UNRESOLVED at merge time"
  - "a health check gates on a path, file, or flag existing rather than on the capability behind it actually working"
tags:
  - falsifier
  - vacuous-fix
  - gate-authoring
  - import-time-binding
  - block-splitting
  - unresolved-falsifier
  - anti-vacuous-truth
---

# Falsify the fix before believing it

## Context

`docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md`
catalogs four ways an *existing* CI check can look green while being
structurally incapable of failing, and
`docs/solutions/best-practices/gate-subset-blindness-2026-07-27.md` adds a
fifth, found the following day. The 2026-07-28/29 session found the same
shape recurring in a different place: not in an old, un-audited gate, but
in **the first version of a brand-new gate, and the first version of a
"fix"** — both authored the same day, both green on their first run, both
wrong.

**Sixth mechanism: a new gate passes its own motivating input because two
claim-units get merged into one during parsing.** PR #371 built a
`board_facts:` drift arm for `scripts/check_derived_doc_drift.py` and
falsified it against the real `docs/STRATEGY.md` sentence it was written
to catch: "The committed board carries **no routing**: 0 segments, 0 vias,
0 zones." The gate reported clean, exit 0. Cause: that bullet sits in a
list with no blank lines between items, so the blank-line-block splitter
treated the entire list as one claim unit, and a *sibling* bullet's "as of
2026-07-25" supersession marker satisfied the requirement on the stale
bullet's behalf. The gate was not wrong about what it checked — it was
wrong about where one claim ended and the next began, which produced the
exact same fail-open shape the anchor-based design was built to rule out,
reintroduced one layer down. Fixed by assessing per claim unit (one list
item with its continuation lines, one table row, one paragraph), verified
by two regression tests confirmed to fail against the previous splitter
before the fix landed.

**Seventh mechanism: the "obvious" fix restores a name without asking how
it's read.** PR #379: `_UNRESOLVED_REF_POLICY` had moved to
`_encoder_core`, and `encoder.py` never re-exported it, so
`test_golden_board_drc_regression` died at collection with an
`AttributeError` — the gate had been measuring nothing. The obvious
fix — restore the re-export on `encoder` — would have been *worse than
the bug*: `_encoder_solve.py` bound the constant with `from _encoder_core
import _UNRESOLVED_REF_POLICY`, which snapshots the value at **import
time**. Every test in the file downgrades the policy by monkeypatching
`encoder._UNRESOLVED_REF_POLICY = "warn"` — which, after restoring the
re-export, would set an attribute nothing reads. The test collects again,
turns green, and the fail-closed guard stays armed underneath it,
indistinguishable from a real fix by anything the test itself reports.
Fixed by having `_encoder_solve` read `_encoder_core._UNRESOLVED_REF_POLICY`
as a live module attribute at call time, and by adding
`TestUnresolvedRefPolicyIsReadLive`, three guards that pin the wiring and
were confirmed to fail by reintroducing the snapshot import. See
`docs/solutions/logic-errors/import-time-binding-defeats-monkeypatch-2026-07-29.md`
for the full technical mechanism.

**An eighth, adjacent shape: a health check that verifies a path exists
instead of the capability behind it.** PR #386's `_fill_zones_via_pcbnew`
hardcoded `/usr/bin/python3` and gated on `Path.exists()`. That path
**exists** on macOS — it just has no `pcbnew` module importable from it —
so the existence check passed, the subsequent `import pcbnew` failed, and
the entire zone/pour DRC test family silently skipped on every developer
machine. This is why the stale `PRODUCTION_UNCONNECTED_POST_U4_BASELINE =
260` baseline (see the companion stale-baseline document) went unverified
for six days: the one test that could have caught the drift was not
running anywhere it could have been noticed.

**The capstone instance predates all four above and is the most direct
statement of the lesson.** `60d441f2` reverted half of an earlier stackup
fix (`a1fe623e`, merged as `52ccd14c`) that cost 12x routing completion —
38.54% before, 3.12% after forcing outer copper layers to `signal`. The
merge commit for `a1fe623e` itself recorded its own falsifier as
**UNRESOLVED**: the implementing agent had stalled before reaching the
measurement that would have caught the regression, and the change merged
anyway. Nothing about that diagnosis was wrong in isolation — reclassifying
`In3.Cu` as nonexistent was correct and was kept — but the outer-layer half
was justified from what `POWER_PLANE_DESIGN.md` says the stackup should be,
not from what the checked-in board's zone pours make it actually behave
like, and it went in without the one measurement that would have shown the
12x cost.

## Guidance

1. **A new gate is not trustworthy until it has failed on the exact input
   it was written to catch.** Writing a check and watching it pass is not
   evidence — the check might be correct, or it might be silently
   satisfied by something adjacent, as PR #371's block-splitter was.
   Deliberately point the gate at its motivating violation and confirm a
   nonzero exit code before trusting a clean run means anything.
2. **Before restoring a moved or removed re-export, check how the
   *consumer* binds it.** `from module import NAME` snapshots at import
   time; a consumer that does this can never be fixed by patching the
   name on some other facade module, no matter how naturally "just
   re-export it" presents itself as the fix. Grep the consumer's imports,
   not just the producer's exports.
3. **If a repair's own falsifier is unresolved, the repair is unresolved.**
   `a1fe623e`'s merge commit recording "falsifier: UNRESOLVED" was not a
   footnote — it was the fix not being done yet. Treat an explicitly
   unresolved falsifier as a hold on merging, not as an acceptable
   condition to note and move past.
4. **A capability check has to attempt the capability, not the
   precondition for it.** `Path.exists()` on an interpreter path is not
   evidence that interpreter can do the thing the code needs. Probe the
   real capability (`import pcbnew`, in this case) and treat "path exists
   but capability fails" as a distinct, loud error rather than the same
   quiet skip as "path doesn't exist."
5. **When two adjacent things could satisfy the same textual/structural
   pattern (two list items, two constants, two paths), assume they will
   collide until proven otherwise.** The blank-line-block splitter and
   the `/usr/bin/python3` existence check both failed because the author
   reasoned about the intended case and not the adjacent one that could
   satisfy the same test by accident.

## Why This Matters

Every instance here produced a gate or fix that was, by its own report,
working. `check_derived_doc_drift.py` exited 0. `test_golden_board_drc_regression`
would have collected and passed. `_fill_zones_via_pcbnew`'s existence check
returned `True`. `a1fe623e` merged with green CI. None of these are cases
where an author skipped verification out of haste — in three of the four,
verification was attempted and produced a false positive; in the fourth,
the falsifier was explicitly flagged unresolved and the change was merged
regardless. The common failure is trusting a check's own report of itself
instead of independently constructing the case the check exists to catch
and confirming it turns red. This is the same discipline
`docs/METHODOLOGY.md` §5's "state the falsifier before implementing" names
for a first-time build; these five instances show it applies with equal
force to a same-day fix of an already-broken check, where the temptation
to declare victory the moment collection succeeds again is highest.

## When to Apply

- Immediately after writing any new drift, staleness, or regression gate:
  construct its motivating violation by hand and confirm the gate rejects
  it, before trusting a clean run on real input.
- Before "restoring" a re-export, alias, or moved constant: check every
  consumer's import style first — a `from X import Y` binding defeats
  patching `X.Y` after the fact from anywhere except the module `Y` was
  bound at.
- Before merging any change whose own commit or PR description records an
  unresolved falsifier, missing measurement, or "not yet verified" note —
  treat that note as a blocker, not a disclosure.
- When a check gates on a file, path, or flag's mere presence: verify it
  gates on the real capability instead, especially for anything that can
  "exist" on one platform without functioning (interpreters, optional
  system libraries, feature flags with no wired caller).

## Examples

```
# PR #371's first gate version: correct logic, wrong claim-unit boundary
- The committed board carries **no routing**: 0 segments, 0 vias, 0 zones.
- ...(sibling bullet)... as of 2026-07-25 ...
                          ^^^^^^^^^^^^^^^^^ satisfied the STALE bullet's
                          supersession requirement too, because both were
                          one blank-line-delimited block
# Gate exit 0 -- fixed by splitting per list item, not per block
```

```python
# PR #379's vacuous "fix" avoided -- what NOT to do:
# encoder.py: __getattr__ = lambda: _encoder_core._UNRESOLVED_REF_POLICY
# (restoring the re-export) -- _encoder_solve.py still holds its own
# `from _encoder_core import _UNRESOLVED_REF_POLICY` binding, snapshotted
# at import time. Patching `encoder.X` sets an attribute nothing reads.

# What was done instead: read the live module attribute at call time
on_unresolved=_encoder_core._UNRESOLVED_REF_POLICY,  # not a local import
```

## Related

- `docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md` —
  mechanisms 1-4, for *existing* gates being audited
- `docs/solutions/best-practices/gate-subset-blindness-2026-07-27.md` —
  mechanism 5, found the day after
- `docs/solutions/logic-errors/import-time-binding-defeats-monkeypatch-2026-07-29.md`
  — full technical detail on mechanism seven (PR #379)
- `docs/solutions/best-practices/stale-absolute-baseline-vs-mutable-board-2026-07-29.md`
  — the stale 260 baseline that mechanism eight (the `/usr/bin/python3`
  existence check) kept hidden from verification
- `docs/solutions/logic-errors/tree-router-layer-selection-must-intersect-grids-2026-07-29.md`
  — PR #386, source of mechanism eight
- `docs/solutions/best-practices/lie-proof-the-green-before-believing-it-2026-07-11.md`
  — an earlier statement of the same discipline, applied to a different
  incident
- PR #371 (`df5e1db5`), PR #379 (`e4e5e976`), PR #386 (`b39b382d`),
  `60d441f2` (the stackup partial revert) — the five instances this
  document generalizes from
- `docs/evidence/2026-07-28-stackup-partial-revert.md` — the 38.54% /
  3.12% / 38.54% measurement behind the capstone instance
