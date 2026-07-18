---
title: "test_gate.py's TestInnerGate/TestTruthGate/TestAcceptFlow tested an abandoned raw-violations-list API; AcceptanceGate had been refactored to real Placement/BaseConstraint domain objects with zero production callers to keep either version honest"
date: "2026-07-18"
category: test-failures
module: temper_placer
problem_type: test_failure
component: testing_framework
severity: medium
symptoms:
  - "TypeError: AcceptanceGate.inner_gate() got an unexpected keyword argument 'audit_violations'"
  - "TypeError: AcceptanceGate.accept() got an unexpected keyword argument 'audit_violations'"
  - "AttributeError: 'DrcResult' object has no attribute 'truth_passed'"
  - "11 of test_gate.py's 18 tests failed"
root_cause: test_isolation
resolution_type: test_fix
tags:
  - temper-placer
  - cp-sat
  - acceptance-gate
  - stale-test
  - dead-code
  - hidden-by-ci
---

# `test_gate.py` tested an abandoned API shape; `AcceptanceGate` has zero production callers

## Problem

11 of 18 tests in `test_gate.py` failed with `TypeError` (unexpected
`audit_violations` keyword) or `AttributeError` (`DrcResult` has no
`truth_passed`). The test file's mental model of `AcceptanceGate`:

- `inner_gate(audit_violations=[...])` -- takes a pre-computed list of
  violation strings, returns a `GateResult`-shaped object
  (`.inner_passed`, `.audit_violations`, `.truth_passed=None`).
- `truth_gate(pcb_path)` -- returns something with `.truth_passed`
  (bool), `.drc_errors`, `.drc_warnings`.
- `accept(placement, constraints, pcb_path, audit_violations=[...])` --
  returns a `GateResult`.

The actual current implementation is architecturally different:

- `inner_gate(placement: Placement, constraints: list[BaseConstraint],
  loop_components=None)` -- computes violations itself via
  `PlacementAuditor.audit()` from real domain objects, returns a raw
  `AuditReport` (`.passed`, `.failed`, `.violations`, `.all_pass`). There
  is no way to pass in a pre-computed violations list anymore -- the
  method's whole job changed from "wrap a given list" to "compute the
  list from real geometry."
- `truth_gate(pcb_path)` -- returns the raw `DrcResult` from
  `validation.drc_runner.run_drc()` directly. No `.truth_passed`
  attribute exists on `DrcResult` at all.
- `accept(placement, constraints, pcb_path=None, loop_components=None)`
  -- no `audit_violations` parameter; returns
  `tuple[bool, AuditReport, DrcResult | None]`, not a `GateResult`.

## Investigation

`GateResult` (the dataclass the old tests expected `inner_gate`/
`truth_gate`/`accept` to return) still exists in `gate.py`, unchanged and
still correctly tested by `TestGateResult` (7/7 passing, not part of the
11 failures) -- but **nothing constructs a `GateResult` instance
anywhere in the current codebase**. It's an orphaned type: the module's
own header docstring still describes a "two-tier rule" in terms that
match `GateResult`'s semantics ("inner_passed=true, truth_passed=false ->
NOT accepted"), but `accept()`'s real return type (a plain tuple of
`AuditReport`/`DrcResult`) doesn't fulfill that contract -- the
class-level refactor that introduced real `Placement`/`BaseConstraint`
domain objects into `inner_gate()`'s signature was never completed with
a matching update to `accept()`'s return type.

Checked `AcceptanceGate`'s real-world usage: **zero production call
sites** (grepped across `src/`; the only other reference is a bare
import/re-export in `placer/cp_sat/__init__.py`). This means neither the
old test-assumed API nor the current implementation's exact shape is
validated by any real caller -- the class exists in a half-finished
state, exercised only by its own (until now, broken) test suite.

A second, independent bug surfaced once the signature mismatches were
fixed: the tests patched `temper_placer.validation.drc_runner.run_drc`,
but `gate.py` does `from temper_placer.validation.drc_runner import
run_drc`, binding its own local name at import time. Patching the
origin module's attribute has no effect on a name already bound into a
different module's namespace -- a classic `mock.patch` target mistake.
Without this fix, the "mocked" tests were silently hitting the real
`kicad-cli` and failing with `Failed to load board` (a synthetic,
nonexistent PCB path).

## Resolution

Rewrote all 11 affected tests against the current, real implementation:
constructing actual `Placement` + `SeparatedConstraint` domain objects
(mirroring the existing, correct pattern in `test_audit.py`) and
asserting on `AuditReport`/`DrcResult`'s real fields, rather than
resurrecting the abandoned `GateResult`-producing design. Given zero
production callers exist, there is no live contract obligating either
direction -- updating the tests to match the more complete, more recent
implementation (real geometric checks via `PlacementAuditor`) is lower
risk than reverting working code to satisfy a stale mock-friendly API.
Also fixed the `mock.patch` target (`temper_placer.placer.cp_sat.gate`,
not the origin `drc_runner` module).

`test_truth_not_run_after_inner_only`'s original intent (calling
`inner_gate()` alone must never trigger DRC) is preserved -- rewritten as
an explicit `mock_run_drc.assert_not_called()` check, since `AuditReport`
has no `truth_passed=None` sentinel to assert on directly anymore.

**Verification:** `test_gate.py`: 18/18 pass (was 7/18).
`test_audit.py` (the adjacent, already-correct suite this rewrite
mirrors): unaffected, still 15/15.

## Why This Matters

This is the largest single batch in a series of test failures that had
never been observed because CI's "CP-SAT Placer Tests" step had never
run to completion on this branch (see
[`courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)).
Unlike most others in the batch, this one also surfaces a genuine design
question worth flagging rather than silently resolving: `AcceptanceGate`
is dead code with an incomplete refactor and an orphaned `GateResult`
type describing a contract the implementation doesn't fulfill. If this
class is meant to be wired up to a real caller in the future, the
`accept()` return type (raw tuple vs. `GateResult`) should be decided
deliberately rather than left as an accident of an unfinished refactor.

## Prevention

- **When a class has zero production callers, its test suite is the
  only thing keeping either the implementation or the test's mental
  model honest -- and neither is authoritative over the other.** Before
  "fixing" such a test failure, check for real callers first; the
  answer (fix the test vs. fix the implementation vs. flag as
  incomplete/dead code) depends entirely on which side, if either, has
  external consumers relying on it.
- **`mock.patch("original.module.function")` only works if the target
  module accesses the function via `original.module.function` at call
  time (e.g. `import original.module; original.module.function()`) --
  not if the target module did `from original.module import function`**,
  which binds a local name at import time that a later patch on the
  origin module cannot retroactively affect. Always patch where the name
  is looked up, not where it's defined.

## Related Issues

- [`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
  — the DRC ratchet gate fix that unblocked CI far enough to run this
  test file for the first time.
- [`docs/solutions/test-failures/cli-cp-sat-tuning-flags-removed-stale-test.md`](cli-cp-sat-tuning-flags-removed-stale-test.md)
  — sibling stale-test finding from the same CI-unblocking batch.
