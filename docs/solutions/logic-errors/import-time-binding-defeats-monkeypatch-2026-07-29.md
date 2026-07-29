---
title: "encoder.py never re-exported a moved constant, and the obvious re-export fix would have made monkeypatching it silently vacuous"
date: "2026-07-29"
category: logic-errors
module: temper_placer
problem_type: logic_error
severity: high
symptoms:
  - "test_golden_board_drc_regression died at collection: AttributeError, module 'temper_placer.placer.cp_sat.encoder' has no attribute '_UNRESOLVED_REF_POLICY' -- the gate had been measuring nothing"
  - "the module that defines _UNRESOLVED_REF_POLICY (_encoder_core) and the module tests were patching it on (encoder, the old facade) had diverged after a refactor, with no error until the constant was actually looked up"
  - "PLACEMENT_IRREDUCIBLE_TYPES = {\"lib_footprint_issues\"} -- a set literal one character-class away from the real violation type lib_footprint_mismatch -- silently charged 32 library-drift violations against a placement budget the placer cannot influence"
root_cause: "_UNRESOLVED_REF_POLICY was moved from encoder.py to _encoder_core.py during a refactor, and encoder.py never re-exported it, so any code still reading encoder._UNRESOLVED_REF_POLICY raised AttributeError. Restoring the re-export would not have fixed the real defect: _encoder_solve.py consumed the constant via `from temper_placer.placer.cp_sat._encoder_core import _UNRESOLVED_REF_POLICY`, a `from ... import` binding that snapshots the value into _encoder_solve's own module namespace at import time. Tests downgrade the policy by monkeypatching encoder._UNRESOLVED_REF_POLICY, which -- after restoring the re-export -- would set an attribute on a module _encoder_solve never reads at call time, leaving the fail-closed 'raise' policy armed underneath a green test."
resolution_type: code_fix
tags:
  - temper-placer
  - cp-sat
  - python-import-semantics
  - monkeypatch
  - vacuous-fix
  - facade-drift
  - typo-classification
  - golden-board-gate
---

# `encoder.py` never re-exported a moved constant, and the obvious fix would have been vacuous

## Context

`test_golden_board_drc_regression` — a `@pytest.mark.slow` gate that
measures real DRC violations on the production board and classifies them
into placement-fixable vs. placement-irreducible categories — died at
**collection**, before any board was routed or measured, with:

```
AttributeError: module 'temper_placer.placer.cp_sat.encoder' has no
attribute '_UNRESOLVED_REF_POLICY'
```

`_UNRESOLVED_REF_POLICY` had, at some earlier point, moved from
`encoder.py` to `_encoder_core.py` as part of splitting the CP-SAT encoder
into a core module and a thinner facade. `encoder.py` never re-exported
it. Two test call sites in `test_regression_drc.py` and
`test_phase1_anti_false_zero.py` were still reaching for
`temper_placer.placer.cp_sat.encoder._UNRESOLVED_REF_POLICY` to
monkeypatch it from `"raise"` (fail-closed) to `"warn"`, so the test could
observe DRC on a board with unresolved constraint refs instead of crashing
outright. The gate had been measuring nothing since the module split.

## Investigation Path

### Step 1: The obvious fix

The reflexive repair — add `_UNRESOLVED_REF_POLICY =
_encoder_core._UNRESOLVED_REF_POLICY` (or a re-export) back to
`encoder.py` — would make the `AttributeError` disappear and the test
collect again. It was rejected before being applied, by tracing how the
constant is actually **consumed**, not just where it's defined:

```python
# _encoder_solve.py, before this fix
from temper_placer.placer.cp_sat._encoder_core import (
    _UNRESOLVED_REF_POLICY,   # <-- binds a snapshot into _encoder_solve's
    EncoderContext,           #     own module namespace, once, at import
    encode_constraints,       #     time
    validate_constraint_refs,
)
...
    on_unresolved=_UNRESOLVED_REF_POLICY,   # reads the LOCAL snapshot
```

`from module import NAME` copies the value of `module.NAME` into the
importing module's namespace at the moment the import statement executes.
After that, `_encoder_solve._UNRESOLVED_REF_POLICY` and
`_encoder_core._UNRESOLVED_REF_POLICY` are two independent names that
happen to have started out equal — mutating one does not affect the
other, ever, regardless of which module is "canonical."

### Step 2: Why the obvious fix would have been *worse* than the bug

If `encoder.py` had re-exported the constant, the test's `monkeypatch.setattr(
encoder, "_UNRESOLVED_REF_POLICY", "warn")` would succeed — it would set an
attribute on the `encoder` module object. But `_encoder_solve.solve_placement`
never reads `encoder._UNRESOLVED_REF_POLICY` at all; it reads its own
import-time snapshot of `_encoder_core._UNRESOLVED_REF_POLICY`, captured
before the test ever runs. The monkeypatch would set an attribute nothing
reads. `test_golden_board_drc_regression` would collect, run, and pass —
green — while the fail-closed `"raise"` policy stayed armed underneath it,
completely undetectable from the test's own passing status. This is
**more dangerous than the collection-time crash it replaces**: a crash is
loud and gets fixed; a vacuous pass looks identical to a real one.

### Step 3: The actual fix

`_encoder_solve.py` was changed to import the **module**, not the name,
and read the attribute live at call time:

```python
from temper_placer.placer.cp_sat import _encoder_core
...
    on_unresolved=_encoder_core._UNRESOLVED_REF_POLICY,  # read at call time
```

Both test call sites were updated to patch `_encoder_core` directly (the
one place the constant is actually defined and actually read from), not
the `encoder` facade. `TestUnresolvedRefPolicyIsReadLive` (three new tests
in `test_encoder.py`) pins the wiring:

- `test_solve_module_holds_no_policy_snapshot` — asserts
  `"_UNRESOLVED_REF_POLICY" not in vars(_encoder_solve)`, i.e. no local
  binding exists to go stale again.
- `test_solve_placement_reads_policy_through_the_core_module` — asserts
  `"_encoder_core"` and `"_UNRESOLVED_REF_POLICY"` both appear in
  `solve_placement.__code__.co_names`, i.e. the function's bytecode
  actually performs the attribute lookup rather than reading a captured
  local.
- `test_core_is_the_sole_definition` — asserts `_encoder_core._UNRESOLVED_REF_POLICY`
  is a `str`, pinning `_encoder_core` as the one canonical definition.

All three were confirmed to **fail** by reintroducing the snapshot-import
form, before being merged passing.

### Step 4: Unmasking exposed a second, independent bug

With the collection-time crash gone, `test_golden_board_drc_regression`
ran for the first time in a while and its own classification logic was
now visible to inspect:

```python
PLACEMENT_IRREDUCIBLE_TYPES = {"lib_footprint_issues"}
```

The real KiCad DRC violation type for a footprint that differs from its
library definition is `lib_footprint_mismatch` — one character-class away
from `lib_footprint_issues`, which does not appear anywhere in the actual
violation output. Every one of 32 `lib_footprint_mismatch` violations on
the production board was therefore falling into the *fixable* (placement-
attributable) bucket instead of the *irreducible* one, charging a
placement quality budget with defects the placer cannot influence —
re-placing a footprint cannot change whether its board geometry matches
its library footprint. Fixed by adding the correct type:

```python
PLACEMENT_IRREDUCIBLE_TYPES = {"lib_footprint_issues", "lib_footprint_mismatch"}
```

With the correct classification, the gate passes at 10 ≤ 15 — the
threshold itself is untouched, and both counts remain visible in the
assertion message so the correction is auditable, not hidden inside a
raised or lowered number.

## Guidance

### Fix

1. `_encoder_solve.py` imports `_encoder_core` (the module) instead of
   `from _encoder_core import _UNRESOLVED_REF_POLICY` (the name), and
   reads `_encoder_core._UNRESOLVED_REF_POLICY` at the point of use.
2. Both test call sites (`test_regression_drc.py`,
   `test_phase1_anti_false_zero.py`) patch `_encoder_core` directly.
3. `PLACEMENT_IRREDUCIBLE_TYPES` in `test_regression_drc.py` gained
   `lib_footprint_mismatch` alongside the pre-existing (and still
   possibly-real) `lib_footprint_issues`.

### Tests added

`TestUnresolvedRefPolicyIsReadLive` (three tests, `test_encoder.py`) — see
Step 3 above; all three verified RED against the pre-fix snapshot-import
form before being merged.

### Verification

`route_pcb`/`solve_placement` on the production board now emits "cannot
resolve refs" warnings where it previously raised, confirming the policy
is read live rather than frozen at import. The golden-board gate now
passes at 10 ≤ 15 fixable violations, with 32 correctly-reclassified
`lib_footprint_mismatch` violations visible in the irreducible count.

## Why This Matters

**`from module import NAME` is a value copy, not a reference.** This is
standard Python semantics, not a bug in the language — but it is exactly
the semantics that makes "just re-export the moved constant" look like a
complete fix when it is not: the re-export makes the *lookup* succeed
again without making the *consumer* read the *live* value. A test that
monkeypatches a module attribute to change behavior has to patch the
module the consuming code actually reads from at the moment it reads it,
not the module where the name is merely defined or merely re-exported.
Any refactor that splits a module into a facade plus a core, or moves a
constant "for organization," has to also audit every `from X import Y`
consumer of that constant for exactly this trap — a passing test after
such a move is not evidence the behavior it's supposed to gate is still
controllable.

**Un-masking one bug revealed a second, unrelated one underneath it.**
The `lib_footprint_mismatch` misclassification had presumably been
present the entire time the gate was dead at collection — it could not
have been caught, because the gate never got far enough to evaluate its
own classification logic. This is expected, not surprising: see
`docs/solutions/best-practices/unmasking-cascades-are-expected-2026-07-29.md`.

## When to Apply

- When restoring any moved, renamed, or re-exported name: grep every
  consumer for `from <module> import <name>` specifically, and check
  whether the consumer reads the name once (at import) or repeatedly (at
  call time via the module). Only the latter can be redirected by
  patching the defining module.
- When a test monkeypatches a module attribute to change downstream
  behavior: verify (e.g. via `__code__.co_names`, or a dedicated pinning
  test) that the code under test actually performs a live attribute
  lookup on the patched module, not a cached local.
- When a violation/error type constant is compared against a hardcoded
  set or string: diff it against the actual enum/type strings the
  producer emits, not against what "sounds right" — a one-character
  divergence (`_issues` vs. `_mismatch`) produces no error, just silent
  miscategorization.
- After unmasking any dead gate (an `AttributeError`, an import error, a
  silent skip): budget for the gate's own internal logic to have a second,
  independent defect that was simply never reached before.

## Related

- `docs/solutions/best-practices/falsify-the-fix-before-believing-it-2026-07-29.md`
  — this incident as instance seven of a broader "verify the fix, don't
  just watch it pass" taxonomy
- `docs/solutions/best-practices/unmasking-cascades-are-expected-2026-07-29.md`
  — the `lib_footprint_mismatch` discovery as one of two cascades from
  the same week
- `docs/solutions/test-failures/regression-drc-tests-missing-zone-loop-wiring.md`
  — an earlier, related `test_regression_drc.py` gate-wiring failure in
  the same file, also masking real DRC-quality regressions
- PR #379 (`e4e5e976`) — the fix this document covers
