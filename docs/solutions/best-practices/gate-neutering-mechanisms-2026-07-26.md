---
title: "Gate neutering mechanisms — the four ways a CI check can exist, be tested, and still never fail"
date: "2026-07-26"
category: best-practices
module: ci_infrastructure
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - "auditing a CI pipeline for gates that are documented as merge-blocking"
  - "a `continue-on-error: true` line has a TODO comment older than a few weeks"
  - "a gate, script, or test directory is not referenced by name in any workflow file"
  - "a validator aggregates per-item results with a bare all(...) or similar reduction"
  - "a feature or check ships behind a default-false flag with no caller that flips it"
tags:
  - vacuous-truth
  - continue-on-error
  - unwired-check
  - ci-masking
  - fail-closed
  - anti-vacuous-truth
  - gate-audit
---

# Gate neutering mechanisms — the four ways a CI check can exist, be tested, and still never fail

## Context

`docs/solutions/best-practices/assert-input-preconditions-not-just-output-metrics.md`
documents an audit that found ten checks in one day that existed, ran, and
were structurally incapable of catching the defect they existed for. This doc
is the taxonomy behind that count — the specific mechanisms, so that an audit
of a *different* pipeline knows what to grep for instead of rediscovering the
list by accident. `docs/METHODOLOGY.md` §4 names the failure classes (missing,
wrong, unwired, vacuous, wrong threshold, silently skipped) and §12 makes
"existing detectors gate" a standing rule; this doc is the field guide for
finding violations of that rule.

Four mechanisms, each independently sufficient to neuter a gate that looks
green:

1. **`continue-on-error: true` after the exit code is computed correctly.**
   `.github/workflows/python-tests.yml`'s "Run extended test suites in
   parallel" step (line 260) correctly aggregates five parallel test runs —
   `FAIL=0; for pid in ...; do wait $pid || FAIL=1; done; exit $FAIL` — and
   then the step is marked `continue-on-error: true` (line 298). The exit
   code is right; the workflow throws it away. The same file carries ten such
   annotations, each with a `TODO: temper-NNN ... hard-fail after
   2026-09-01` comment (lines 246, 250, 298, 301, 314, 325, 329, 396, 438,
   444) — a documented, dated intent to re-enable that is easy to forget once
   the annotation stops looking urgent.
2. **A default-off flag with no caller that flips it.** A stage exists, is
   unit-tested, and is wired into the pipeline behind a parameter that
   defaults to `False` — and nothing in production ever passes `True`. See
   the manufacturing DRC stage below.
3. **An uninvoked code path.** The check binary/script runs correctly when
   invoked directly (a traceability gate exits 1 on a real violation) but no
   workflow file invokes it — the ten found in one day included exactly this:
   `check_traceability.py` exits 1 while invoked by no workflow, and 238
   safety tests live in a directory no workflow references. Full catalog in
   `assert-input-preconditions-not-just-output-metrics.md`.
4. **Vacuous truth: `all(...)` over an empty collection.** `all([])` is
   `True` in Python. A gate that aggregates per-item checks with a bare
   `all(...)` reports a clean verdict on an input it never measured. Five
   production gates did this — one with a docstring asserting *"An UNMEASURED
   gate is never green"* while returning green on an empty input.

A related but distinct case is a gate that is off, correctly, and whose first
real check crashes the moment it is turned on: the manufacturing DRC stage
(`enable_manufacturing_drc`, default `False`) was wired into `route_pcb()`
after being found never to have run, and its first production-scale run did
not finish in 27 minutes at 9.2 GB RSS before the run was killed
(`docs/evidence/2026-07-26-manufacturing-drc-scalability.md`). The stage
was not neutered maliciously or by oversight here — it is a check that has
never once executed on real data, so mechanism 2 and "untested at scale" compound.

## Guidance

1. **Grep every workflow file for `continue-on-error` and read the comment.**
   A `TODO ... hard-fail after <date>` that has passed its date is a check
   that has quietly become advisory. Age the annotation; do not just count
   its presence.
2. **For every check documented as "merge-blocking," find the workflow line
   that invokes it by name.** If grep doesn't find it, the check runs on
   nobody's PR regardless of what its own tests say.
3. **Ban unguarded `all()` and `any()`-shaped reductions in gate/validator
   code**, or better, mechanize the ban: `scripts/check_vacuous_gates.py`
   scans every `.py` file under `gate`/`valid` path components for an
   unguarded `all(...)` call and fails if one exists with no non-empty
   assertion in front of it. This is `docs/METHODOLOGY.md` §5's
   "Anti-vacuous-truth" rule turned into a check on the checks.
4. **A default-off flag is not evidence the feature works — only that it
   compiles.** Before trusting a stage exists, run it once at production
   scale with the flag flipped, and budget for it to fail on first contact
   (`docs/solutions/best-practices/assert-input-preconditions-not-just-output-metrics.md`'s
   `blind_to` field applies here too: a stage's own tests all pass, on
   fixtures small enough to hide an O(n²) cost).
5. **A check with no proof-of-fire is not registered** (`docs/METHODOLOGY.md`
   §12). Before believing any of the four mechanisms above is absent from a
   gate, inject a real violation and confirm the gate turns red — the
   construction axis (§5) is the only one that closes all four at once.

## Why This Matters

None of these four mechanisms produce an error. Each produces a gate that is
green, present in the pipeline definition, backed by passing unit tests, and
incapable of blocking anything. They are cheaper to introduce than to notice:
`continue-on-error` is one line added under deadline pressure with an honest
intent to revisit; a default-false flag is the normal, safe way to ship new
infrastructure; `all([])` is what the standard library does by default. The
audit that found ten in one day did not find ten instances of carelessness —
it found four cheap, well-intentioned mechanisms, each applied once or twice,
compounding into a pipeline where roughly a third of what looked like
coverage was not.

## When to Apply

- Auditing any pipeline where "CI is green" is being used as evidence a
  change is safe.
- Before trusting a gate that has been green for weeks without a known
  fault-injection test proving it can turn red.
- When adding `continue-on-error: true` — write the hard-fail date in the
  same commit, and put a reminder where it will actually be seen.
- When reviewing any validator that reduces a list of per-item results —
  check what it does on the empty list before trusting what it does on a
  populated one.

## Examples

```yaml
# .github/workflows/python-tests.yml:260-298 — exit code computed correctly,
# then discarded
- name: Run extended test suites in parallel
  run: |
    ...
    FAIL=0
    for pid in $BUNDLE_PID $INVARIANT_PID $CPSAT_PID $WORKFLOW_PID $CHECKS_PID; do
      wait $pid || FAIL=1
    done
    exit $FAIL
  continue-on-error: true  # TODO: temper-NNN -- parallel test suite flakiness; hard-fail after 2026-09-01
```

```python
# scripts/check_vacuous_gates.py — the mechanized form of mechanism 4
# "all() over an empty collection is vacuously True in Python -- a
#  verification function that aggregates per-item results with a bare
#  all(...) therefore reports a clean verdict for input it never
#  actually measured" -- scans gate/validator modules, fails CI on any
#  unguarded all(...) call.
```

## Related

- `docs/solutions/best-practices/assert-input-preconditions-not-just-output-metrics.md`
  — the incident this taxonomy generalizes from, with the full ten-item
  catalog and the board-outline story
- `docs/METHODOLOGY.md` §4 (failure taxonomy: missing / wrong / unwired /
  vacuous / wrong-threshold / silently-skipped), §5 "Anti-vacuous-truth", §12
  standing rules
- `docs/evidence/2026-07-26-manufacturing-drc-scalability.md` — the
  default-off stage that does not finish at production scale on first enable
- `docs/solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md`
  — a sibling case of layered CI masking (build failure hiding test failure
  hiding install failure) found and fixed the same week
- `docs/solutions/architecture-patterns/silent-guard-condition-infrastructure-failure-pattern-2026-07-02.md`
  — the same "green but unreachable" shape applied to application guard
  conditions rather than CI gates
- `scripts/check_vacuous_gates.py` — mechanized anti-vacuous-truth gate
