---
title: "A known-red test needs to pin its failure reason, or a new defect can hide behind the old one"
date: "2026-07-30"
category: best-practices
module: ci_infrastructure
problem_type: best_practice
component: development_workflow
severity: critical
applies_when:
  - "a test or gate has been red for a diagnosed, accepted, pre-existing reason for more than one PR"
  - "triaging a failure by 'reproduce on origin/main first' -- comparing WHICH tests fail, not WHY"
  - "reviewing a PR whose only red check also fails on main, and concluding 'not my problem' without reading the failure body"
  - "deciding whether to add an xfail/skip for a known-failing test"
  - "a safety-relevant gate (DRC, isolation, clearance) is allowed to stay red for a scoped, documented reason"
tags:
  - known-failure-pin
  - xfail-alternative
  - ratchet-design
  - ci-masking
  - triage-discipline
  - golden-board-drc
---

# A known-red test needs to pin its failure reason, or a new defect can hide behind the old one

## Context

PR #460 (`fix/domain-clearance-copper-aware`) nearly merged while introducing
a destructive HV short -- `DC_BUS+` shorted to `SW_NODE` across the
half-bridge IGBTs on the golden board
(`power_pcb_dataset/corpus/temper/temper.kicad_pcb`). It was caught by a peer
session running a decisive experiment, not by CI.

CI missed it because `test_golden_board_drc_regression`
(`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`) was
already failing for an unrelated, pre-existing reason: `_apply_placements_to_
pcb` (`router_v6/_adapter_convert.py`) drops the CP-SAT solver's solved
rotation when writing footprints back to the board -- fixed in isolation by
PR #471, but deliberately left unwired into any caller, because wiring it in
measurably worsens this exact test's DRC numbers
(`docs/evidence/2026-07-30-placement-writer-rotation.md` Sec 3.2: applying
the fix on PR #460's own reported scenario moves `shorting_items` 1 -> 4 and
relocates it to a different net pair entirely).

Standard triage discipline in this repo is "reproduce the failure on
`origin/main` before attributing it to your change" --
`docs/solutions/best-practices/falsify-the-fix-before-believing-it-2026-07-29.md`
and related docs establish this as the correct default. But that discipline
compares **which tests fail**, not **why they fail**. A test red on `main`
for reason A (rotation-writer defect, `shorting_items=1`) and red on the PR
branch for reason B (a new, unrelated, far more severe short) looks
identical from the outside: same test name, same red X, same "already
failing on main." Nothing in that comparison distinguishes "the same known
issue" from "a new issue that happens to trip the same assertion."

This is the inverse of the un-masking cascade pattern in
`docs/solutions/best-practices/unmasking-cascades-are-expected-2026-07-29.md`
(fixing one layer reveals the next, previously-unreachable one): here, a
known-red layer absorbed a new, worse layer underneath it, and nothing made
that visible.

## The mechanism

`scripts/known_failure_pins.py` lets a test declare the *signature* of a
failure it is already known to have -- not just its name -- in a checked-in
registry, `known-failure-pins.yaml`:

```yaml
packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_golden_board_drc_regression:
  issue: docs/evidence/2026-07-30-placement-writer-rotation.md
  declared: "2026-07-30"
  expires: "2026-08-13"
  reason: >
    Writer drops solved rotation, producing 1 shorting_items + 1
    solder_mask_bridge on this seed.
  signature:
    shorting_items: 1
    solder_mask_bridge: 1
```

The test wraps its existing assertions -- unchanged thresholds, unchanged
logic -- in a `try`/`except AssertionError`, computes a signature (here,
`dict(sorted(fixable_counts.items()))`, the exact violation-type breakdown
the test already classifies violations into), and annotates the message:

```python
signature = dict(sorted(fixable_counts.items()))
try:
    assert shorting == 0, "..."
    assert mask_bridge == 0, "..."
    ...
except AssertionError as exc:
    raise AssertionError(
        annotate_failure(request.node.nodeid, signature, str(exc))
    ) from exc
```

Three outcomes, all still a failing (red) test -- see "Why not xfail" below:

1. **Signature matches the pin** -> the message is prefixed
   `[KNOWN-FAILURE, pinned]`, citing the linked evidence doc and the
   declared reason.
2. **Signature differs from the pin** (a new violation type, an extra count,
   anything not equal to the declared dict) -> the message is prefixed with
   a large, visually distinct `KNOWN-FAILURE PIN MISMATCH` block showing
   both signatures and an explicit warning not to assume this is the pinned
   issue.
3. **No pin declared for this test** -> the message comes back byte-for-byte
   unchanged. `annotate_failure` is the identity function on an unpinned
   nodeid.

## Why not xfail

This repo's tests may not use `pytest.xfail`/`skipif` to resolve a failure:
doing so reports the test as expected-to-fail, which removes it from the set
CI treats as red -- exactly the signal this mechanism exists to preserve. A
pinned test still fails, still shows red, still blocks whatever the test
normally blocks. All the mechanism changes is *what the failure message
says*, not *whether the test failed*. This is a deliberate, narrower promise
than xfail makes: it does not offer a way to make CI green while a known
defect remains; it only makes two different reds distinguishable from each
other.

## Why this cannot become a suppression list

A mechanism for declaring "known failures" is one refactor away from being
an xfail list that hides everything. Four independent guards, chosen to
mirror this repo's existing allowlist-ratchet shape
(`tools/loc_cap_check.py`, `.coverage-allowlist`, `.typecheck-allowlist`:
baseline + required justification + stale-entry detection):

1. **No pin, no effect.** `annotate_failure` on an unpinned nodeid returns
   the original message unmodified -- there is no "pin everything" mode, no
   wildcard, no way to declare a whole test file known-failing in one entry.
2. **Pins expire.** Each entry carries `declared`/`expires` dates
   (lifetime capped at `MAX_PIN_LIFETIME_DAYS = 21` by the gate). Past
   expiry, `check_signature` reports status `"expired"` and treats the pin
   as absent -- a pin does not silently keep matching forever just because
   nobody revisited it.
3. **Pins require a paper trail.** `issue` must point at a real, checked-in
   `docs/evidence/` or `docs/solutions/` file (this document, for the one
   pin this task's scope covers). The registry gate (`ORPHAN_ISSUE_LINK`)
   fails the build if the path doesn't exist on disk -- no bare claims.
4. **The registry is a ratchet.** `uv run python scripts/known_failure_pins.py`
   (wired as its own CI job, `known-failure-pins`, in
   `.github/workflows/python-tests.yml`) fails if the live-pin count exceeds
   `MAX_LIVE_PINS = 3`, if any pin is past its expiry, if a pin's lifetime
   exceeds the cap, if an `issue` link is dangling, or if a pinned nodeid no
   longer resolves to a real test (`ORPHAN_PIN` -- a pin cannot outlive the
   test it names). Raising either cap requires editing the constant in
   `scripts/known_failure_pins.py` in the same PR that adds the pin
   justifying it, so a reviewer sees the cap move in the diff.

`known-failure-pins.yaml` ships with **zero live entries**:
`test_golden_board_drc_regression` currently passes on `main` (the
rotation-writer defect is real but dormant on this board/seed/config -- see
the evidence doc), so there is nothing legitimately known-failing to pin
right now. The mechanism is wired into the test and proven (below) with
synthetic and monkeypatched scenarios; it stays inert until the test is
actually red for a diagnosed reason.

## Proof (falsifier)

Three properties were demonstrated, using the PR #460 shape concretely: a
pin for the rotation-writer defect (`shorting_items: 1,
solder_mask_bridge: 1`) versus that same signature plus one **extra**
`shorting_items` entry standing in for the `DC_BUS+`/`SW_NODE` short.

**1. Known failure recognised.** Ran the real
`test_golden_board_drc_regression` end-to-end (real CP-SAT solve, real
`_apply_placements_to_pcb` writer; only `_run_drc`, the kicad-cli boundary,
monkeypatched to a fixed violations payload matching the pin exactly) with
the pin declared:

```
RESULT: test FAILED (AssertionError), message below:
------------------------------------------------------------------------------
[KNOWN-FAILURE, pinned] packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_golden_board_drc_regression is pinned as known-failing (issue: docs/evidence/2026-07-30-placement-writer-rotation.md, declared 2026-07-30, expires 2026-08-13). Reason: Writer drops solved rotation, producing 1 shorting_items + 1 solder_mask_bridge. Observed failure signature matches the pinned signature exactly: {'shorting_items': 1, 'solder_mask_bridge': 1}. This is the pinned failure, not a new one.
Expected 0 fixable shorting_items, got 1. Fixable: {'shorting_items': 1, 'solder_mask_bridge': 1}
------------------------------------------------------------------------------
```

**2. A different failure in the same test is reported loudly as a changed
reason.** Same pin, same run, but `_run_drc` now returns one additional
`shorting_items` entry (`Pad 7 of DC_BUS+ and Pad 9 of SW_NODE`) -- the #460
case:

```
RESULT: test FAILED (AssertionError), message below:
------------------------------------------------------------------------------

################################################################
# KNOWN-FAILURE PIN MISMATCH -- packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_golden_board_drc_regression
################################################################
This test is pinned as known-failing for a SPECIFIC reason (issue: docs/evidence/2026-07-30-placement-writer-rotation.md, declared 2026-07-30):
    Writer drops solved rotation, producing 1 shorting_items + 1 solder_mask_bridge.
    pinned signature:   {'shorting_items': 1, 'solder_mask_bridge': 1}
but it just failed with a DIFFERENT signature:
    observed signature: {'shorting_items': 2, 'solder_mask_bridge': 1}
    changed entries (pinned -> observed): {'shorting_items': (1, 2)}
Do NOT assume this is the pinned issue. This is exactly the shape of the PR #460 near-miss: a test already red for reason A silently absorbed a new, unrelated reason B. Investigate this as a fresh, potentially more serious failure before dismissing it as 'pre-existing, matches origin/main.'
################################################################

Expected 0 fixable shorting_items, got 2. Fixable: {'shorting_items': 2, 'solder_mask_bridge': 1}
------------------------------------------------------------------------------
```

**3. The mechanism cannot silence a new failure with no declaration.** Same
first (matching) violations payload, but the registry emptied (no pin for
this nodeid at all):

```
RESULT: test FAILED (AssertionError), message below:
------------------------------------------------------------------------------
Expected 0 fixable shorting_items, got 1. Fixable: {'shorting_items': 1, 'solder_mask_bridge': 1}
------------------------------------------------------------------------------
```

Identical to the test's original, unmodified assertion message -- no
`[KNOWN-FAILURE]` prefix, no suppression, no different behavior at all.

All three transcripts were produced by a scratch driver invoking the real
`test_golden_board_drc_regression` function directly (not committed --
scratch-only per this task's constraints); the same three properties are
also covered as permanent, always-running unit tests in
`scripts/tests/test_known_failure_pins.py` (`TestKnownReasonRecognised`,
`TestChangedReasonIsLoud`, `TestUndeclaredFailureIsNeverSilenced`, plus
`TestExpiryDegradesToUnpinned` and `TestGateIsARatchetNotASuppressionList`
for the anti-suppression guards), gated in CI by the `known-failure-pins`
job.

## Guidance

1. **Pin the signature, not the test name.** "This test is known-failing" is
   not a falsifiable claim; "this test is known-failing with exactly this
   violation-type breakdown" is -- any deviation is visible by construction.
2. **A pin is not a fix and not a waiver.** It exists to keep two different
   red failures from being triaged as one. The test still fails, still
   blocks, still needs the same attention it would without a pin.
3. **Expire pins on a short clock.** A defect worth pinning is worth
   revisiting in three weeks, not indefinitely. If the pin is still needed
   at expiry, renewing it is a deliberate act with a fresh look at the
   evidence, not a rollover.
4. **Never widen a signature to make a mismatch go away.** If a pin stops
   matching, the right move is to investigate the new failure (it may be a
   regression), not to loosen the pinned dict until it matches again --
   that is the suppression-list failure mode this mechanism exists to
   prevent, just moved one layer down.
5. **Scope one pin at a time.** This mechanism was applied to exactly one
   test (`test_golden_board_drc_regression`) as the motivating case, not
   retrofitted across every currently-red test in the repo. Wider adoption
   should happen test-by-test, each with its own diagnosed reason and
   evidence doc, not as a bulk migration.

## Why This Matters

The alternative failure mode is not hypothetical: it is exactly what nearly
shipped a destructive mains-adjacent short. "Reproduce on `origin/main`" is
correct triage discipline for *whether* a test's pass/fail status changed;
it says nothing about *why* a still-failing test failed, and a reviewer (or
an automated check) skimming CI has no cheaper way to find out than reading
the full failure body character-by-character, every time, forever. Pinning
the reason moves that comparison from "eyeball the diff of a JSON blob" to
"read one sentence that says KNOWN or MISMATCH."

## When to Apply

- A test or gate has been red for a diagnosed, accepted reason across more
  than one PR, and a future different failure in the same test would be
  costly to miss (safety-relevant DRC/isolation/clearance gates especially).
- Before reaching for `xfail`/`skip` on a test whose failure is understood
  but not yet fixed -- a pin preserves the red signal that `xfail` would
  discard.
- When reviewing a PR whose only failing check also fails on `main`: read
  the pin verdict (if the test carries one) before concluding "pre-existing,
  not my problem."

## Related

- `docs/evidence/2026-07-30-placement-writer-rotation.md` -- the
  rotation-writer defect this document's example pin signature is drawn
  from, including the measurement showing why the fix is not wired on by
  default.
- `docs/solutions/best-practices/unmasking-cascades-are-expected-2026-07-29.md`
  -- the inverse pattern: a fix revealing a previously-unreachable failure,
  rather than a known failure absorbing a new one.
- `docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md` --
  taxonomy of ways a gate can look green and catch nothing; this mechanism
  is explicitly designed to avoid becoming mechanism 2 or 3 of that list
  (a default-off capability, an uninvoked code path) by staying wired into
  the test's normal, always-executed assertion path.
- `docs/solutions/best-practices/falsify-the-fix-before-believing-it-2026-07-29.md`
  -- the "reproduce on origin/main" discipline this mechanism sharpens
  rather than replaces.
- `tools/loc_cap_check.py`, `.coverage-allowlist`, `.typecheck-allowlist` --
  the monotonic-shrink ratchet shape this registry's anti-suppression
  guards follow.
- `scripts/known_failure_pins.py`, `known-failure-pins.yaml`,
  `scripts/tests/test_known_failure_pins.py` -- the mechanism, the registry
  (currently empty), and its test suite.
- `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_golden_board_drc_regression`
  -- the motivating instance this mechanism was wired into.
- PR #460 (`fix/domain-clearance-copper-aware`), PR #471 (rotation-writer
  fix, deliberately unwired).
