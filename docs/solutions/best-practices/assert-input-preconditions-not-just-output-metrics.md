---
title: "Assert input preconditions, not just output metrics — the board outline that survived four weeks of router work"
date: "2026-07-25"
category: best-practices
module: temper_placer
problem_type: best_practice
component: development_workflow
severity: critical
applies_when:
  - "a loop reports a metric and you have not confirmed the metric can observe the failure mode you care about"
  - "an error message is technically correct but the diagnosis built on top of it keeps not working"
  - "a new check lands in CI without first being proven against a known-bad input"
  - "a metric has been green for weeks in an area nobody has manually re-inspected"
  - "a validation layer is being extended (fast loop) faster than it is being falsified (proven oracle)"
tags:
  - loop-verification
  - precondition-assertion
  - blind-metric
  - fail-closed
  - validate-the-validator
  - fault-injection
  - board-outline
  - false-negative
---

# Assert input preconditions, not just output metrics

## Context

`pcb/temper.kicad_pcb` carried a placeholder `Edge.Cuts`: a 100 × 150 mm
rectangle at the origin. Footprint placement spanned x 31.5–145.9 mm, y
30.7–240.4 mm. **113 of 149 footprints (76%) sat outside the board
outline**, including the IGBT (U5) and the isolated gate driver (U6).

A/B, changing only the outline, same router commit / netlist / flags:

| | placeholder | real outline |
|---|---|---|
| completion_rate | 0.0000 | 0.7857 |
| nets routed / failed | 0 / 95 | 66 / 18 |
| segments emitted | 0 | 2,966 |

Every failing net reported this, 95 times:

```
no legal path found (forced segment disallowed)
```

— the fail-closed gate working correctly and saying so in
plain language. It was read as router congestion. Roughly four weeks of
router work followed: a fail-closed generalization, property tests, a
nine-reviewer code review, evidence files, a strategy section titled "the
honesty tangent."

KiCad DRC reported **5** `copper_edge_clearance` violations for a board
with 113 parts off it. The rule checks clearance *to* an edge, not
membership *within* an outline — it was structurally blind to the defect
that mattered. An anti-false-zero CI guard had been built to protect a
number that could not see the largest problem in the file.

The fix was three lines: assert every footprint lies inside `Edge.Cuts`.

Full incident writeup and the taxonomy this instantiates:
`docs/METHODOLOGY.md` §7 (reference failure), §4 (failure taxonomy), §5
(falsification axes).

## Guidance

1. **A loop is only verifiable if its metric can observe the failure
   mode.** Completion rate, DRC violation count, test-pass count — none
   are safe to trust until you know what they are blind to. Write the
   `blind_to` field down explicitly (METHODOLOGY §3) before trusting the
   metric next to it.
2. **Every loop needs a precondition assertion on its input, not only a
   quality metric on its output.** This is the generic fix, and it is
   cheap — three lines here. Loops default to trusting their input and
   scoring their output; the missing half is asserting the input.
3. **A correct error message can still be misread.** `forced segment
   disallowed` was true and precise — the router correctly refused an
   illegal path. Diagnosis failed one layer up, in the decision to treat
   a routing-capacity story as more plausible than a geometry story.
4. **Speed multiplies a diagnosis error; it does not dilute it.** The
   loop that chased this was fast and rigorous (594 commits in 14 days,
   METHODOLOGY §8) and closed entirely on a blind metric. Rigor inside a
   loop is not a substitute for an oracle on the loop itself.
5. **Validate your validators.** Inject a known defect and confirm the
   check fires (METHODOLOGY §5, construction axis). The blind spot is
   invisible from inside the loop that trusts the check — it is only
   visible from outside, by breaking things on purpose.

## Why This Matters

The blind-metric shape generalizes past this one board. Auditing for "a
check that exists, runs, and cannot observe the failure" found ten more
instances in one day: `check_traceability.py` exits 1 while invoked by no
workflow; import-linter is documented as merge-blocking but has been
crashing since ~2026-07-11 on deleted modules while printing PASSED
(confirmed by injecting a real forbidden import — still printed PASSED);
238 safety tests live in a directory no workflow references; and five
production gates return vacuously-true because `all([])` is `True` in
Python — one of which has a docstring asserting *"An UNMEASURED gate is
never green"* while returning green on an empty input. Each is the same
shape as the DRC edge-clearance rule: present, running, structurally
incapable of seeing the thing it exists to catch.

## When to Apply

- Before trusting a green completion / pass / coverage number in a
  pipeline you didn't just fault-inject.
- Before spending more than a day chasing a "capacity" or "tuning"
  explanation for a hard failure — check the input shape first.
- When adding any new check: prove it fires on a known-bad input before
  it goes into CI (METHODOLOGY §6 — "a check with no proof-of-fire is not
  registered").
- When a metric has been stable for weeks with no manual re-inspection of
  the underlying artifact.

## Examples

The precondition assertion at the router's input seam — the actual fix:

```python
def route_pcb(board, netlist, ...):
    for fp in netlist.footprints:
        assert board.outline.contains(fp.position), (
            f"{fp.ref} at {fp.position} lies outside Edge.Cuts "
            f"{board.outline.bounds} — placement/board-outline seam is broken"
        )
    ...
```

The Loop Contract field (METHODOLOGY §3) that would have named the gap at
design time, before any code ran:

```yaml
input_precondition: every footprint lies inside Edge.Cuts   # <-- was absent
blind_to: board geometry validity                            # <-- the missing line
```

## Related

- `docs/METHODOLOGY.md` §4 (failure taxonomy), §5 (falsification axes),
  §7 (this incident, full figures)
- `docs/solutions/logic-errors/polygon-edge-cuts-parser-invisible-bbox-2026-07-15.md`
  — a sibling Edge.Cuts bug: same file area, different shape-coverage gap
- `docs/solutions/best-practices/lie-proof-the-green-before-believing-it-2026-07-11.md`
  — same discipline, applied to silently-dropped constraints instead of an
  unobservable metric
- `docs/solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md`
  — a sibling case of layered CI masking hiding real failures for a week
