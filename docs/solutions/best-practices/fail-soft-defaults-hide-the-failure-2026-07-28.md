---
title: "Fail-soft defaults hide the failure they cause — a fabricated copper layer and a silently-assumed 230V anchor"
date: "2026-07-28"
category: best-practices
module: temper_placer
problem_type: best_practice
component: hardware_design
severity: high
applies_when:
  - "a function accepts an optional argument and substitutes a hardcoded default when it's missing, in a safety- or correctness-relevant computation"
  - "a substring/membership test decides whether a whole layer, region, or category is included, and a false match silently changes what's excluded"
  - "reviewing `getattr(x, 'field', default)`, `.get(key, default)`, or an unguarded fallback branch in code that feeds a safety verdict"
  - "a check's output looks plausible (a real number, not zero or an error) but the code path that produced it never received the input it needed"
tags:
  - fail-soft-default
  - silent-fallback
  - phantom-layer
  - voltage-rating-default
  - fail-closed
  - defensive-coding-antipattern
---

# Fail-soft defaults hide the failure they cause

## Context

Two independent instances, in unrelated code, of the same shape: a
function receives an input it needs to answer a safety-relevant question
correctly, doesn't get it, and silently substitutes a plausible-looking
value instead of failing loudly.

**Instance 1 — a fabricated copper layer.**
`_extract_stackup()`'s fallback path (`_parse_board.py`, pre-fix) tested
`".Cu" in name` to decide whether a board entry was a copper layer.
`Edge.Cuts` contains the substring `".Cu"`, so the fallback fabricated a
fourth copper layer, `In3.Cu`, that does not exist on this board and could
not be manufactured or routed onto. The check ran, produced a plausible
answer (a real-looking, numbered layer name), and gave no signal that
anything had gone wrong — the failure was only visible by independently
inspecting `board.setup.stackup` (`None` on this board) and noticing the
fabricated layer had no basis in the actual stackup declaration. Fixed by
`.endswith(".Cu")`
(`docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md`
covers the fix's own unintended consequence in the same commit).

**Instance 2 — a silently-assumed anchor voltage.**
`_run_manufacturing_drc()` calls `verify_creepage()` passing only
`routing_results`, never `voltage_ratings`
(`docs/evidence/2026-07-27-creepage-burndown.md`). Inside
`verify_creepage()`, `hv_voltage = voltage_ratings.get(hv_net, 230.0)`
defaults **every** anchor net — including nets the classifier had already
misidentified — to 230V, regardless of what that net's actual working
voltage is. The consequence is not a crash and not an obviously-wrong
number: every violation the check reports gets evaluated against a flat
3.2mm creepage requirement (the 230V-appropriate figure), whether the real
anchor net operates at 12V, 340V, or anything else. A downstream reviewer
sees a populated violations list with plausible-looking distances and has
no way to tell, from the output alone, that the voltage input was never
supplied at all.

Both instances share the same shape: a missing or wrong input is
converted, inline, into a value indistinguishable from a genuinely correct
one, at the exact point where failing loudly was the correct behavior.

## The pattern

**A fail-soft default doesn't fail — it substitutes.** The difference
matters because a failure is visible (an exception, a `None`, an error
log) and a substitution is not: the code keeps running, produces a
value shaped exactly like every other value it produces, and nothing
downstream is positioned to tell the two apart. This is a narrower,
sharper case than a gate that is merely blind to a defect (which at
least produces an unambiguous verdict on the input it did see) — here
the *input itself* is wrong, silently, before any check logic even runs,
so every downstream computation inherits a corrupted premise while
looking completely healthy.

Both instances here are individually cheap causes: a one-character
substring test, and an unguarded `.get(..., default)` at a single call
site. Neither required a design mistake to introduce — `getattr`/`.get`
with a default is the normal, idiomatic way to handle an optional field
in Python, and a substring test is the normal way to do a quick string
match. The defect is not that the mechanism is exotic; it's that it was
applied at a point where the "missing" case and the "correctly computed"
case are safety-relevant to distinguish, and the code made no attempt to
distinguish them.

## Guidance

1. **Before writing `getattr(x, field, default)` or `d.get(key, default)`
   in any function that feeds a safety, compliance, or correctness
   verdict, ask whether the default is a genuinely valid fallback value or
   a value that merely lets execution continue.** `230.0` is a real
   voltage that appears nowhere in this design's own net list as a
   correct value for most nets it gets applied to — it is not a
   conservative default, it is an arbitrary one that happens to produce a
   plausible-looking number.
2. **A membership/substring test that gates category inclusion (is this a
   copper layer? is this layer a plane?) needs the same anchoring
   discipline as a net-name classifier.** `".Cu" in name` and `"GND" in
   net_name` are the identical AST shape and the identical failure mode —
   see
   `docs/solutions/best-practices/substring-net-classification-drifts-from-ssot-2026-07-27.md`
   — an unanchored `in` test is never safe to use as a boundary decision,
   regardless of what category it's deciding.
3. **When a function's correctness depends on receiving a specific input
   (`voltage_ratings`, a stackup table, a manifest), make that input
   required, not optional with a default.** If the caller genuinely cannot
   supply it in some contexts, that gap belongs in the caller's contract
   (raise, or return an explicit "not evaluated" state) — not papered over
   inside the callee with a value that looks like a normal answer.
4. **Prefer a loud failure (raise, assert, an explicit `UNKNOWN`/`unmeasured`
   sentinel that downstream code must handle) over any default that
   produces a value of the same type and shape as a correct one.** A
   `None` or an exception at least forces the caller to notice; a `230.0`
   or a fabricated `In3.Cu` does not.
5. **Audit for this shape specifically where a check's output looks
   healthy** — a populated violation list, a named layer, a plausible
   number — **rather than only where a check crashes or returns
   empty.** Both instances here produced normal-looking output; neither
   produced an obvious red flag, which is exactly why they survived until
   an unrelated investigation traced the actual call site.

## Why This Matters

Neither instance here announced itself. The fabricated `In3.Cu` layer
looked like a real, numbered inner layer in every log and data structure
that touched it, until someone checked it against the board's own stackup
declaration and found no basis for it. The 230V default produced a
populated, plausible creepage-violation report — the kind of output a
reviewer reads as "the check ran and found some issues," not as "the
check never received the one input it needed to be correct." A defensive
default is supposed to make code more robust; applied at a
safety-relevant boundary, it instead makes the failure indistinguishable
from success, which is the one property a safety check can least afford.

## When to Apply

- Reviewing any `getattr(..., default)` or `.get(key, default)` call
  inside a function whose output feeds a safety, compliance, or
  correctness verdict — check whether the default is a genuinely valid
  value or merely a value that avoids a crash.
- Writing or reviewing any membership/substring test (`in`) used to decide
  category inclusion for a layer, net, region, or component — anchor it,
  or replace it with an explicit lookup against the authoritative source.
- When a function has an optional parameter that materially changes its
  output's correctness (`voltage_ratings`, a classification table, a
  manifest) — check every call site to confirm the parameter is actually
  supplied, not silently omitted.
- When a check's output looks healthy (nonzero, well-formed, plausible) —
  trace at least one input back to its actual source before trusting the
  output, rather than only auditing checks that crash or return empty.

## Examples

```python
# WRONG — a substring test fabricates a nonexistent layer
is_copper = ".Cu" in name          # "Edge.Cuts" contains ".Cu"
# RIGHT
is_copper = name.endswith(".Cu")
```

```python
# WRONG — a missing input becomes an arbitrary, plausible-looking default
def verify_creepage(routing_results, voltage_ratings=None):
    voltage_ratings = voltage_ratings or {}
    for hv_net in anchor_nets:
        hv_voltage = voltage_ratings.get(hv_net, 230.0)   # <- silently wrong
                                                            #    for most nets
        ...

# RIGHT — the missing input is a loud failure, not a silent substitution
def verify_creepage(routing_results, voltage_ratings):
    for hv_net in anchor_nets:
        if hv_net not in voltage_ratings:
            raise ValueError(
                f"no declared voltage rating for anchor net {hv_net!r} -- "
                f"cannot evaluate creepage without it"
            )
        hv_voltage = voltage_ratings[hv_net]
        ...
```

## Related

- `docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md`
  — the fix for Instance 1's fabricated layer, and the unrelated
  regression the same commit introduced fixing it.
- `docs/solutions/best-practices/substring-net-classification-drifts-from-ssot-2026-07-27.md`
  — the anchoring discipline (`re.search` with word boundaries instead of
  bare `in`) that generalizes past net-name classification to any
  membership test deciding a safety-relevant category, including
  Instance 1's layer test.
- `docs/solutions/best-practices/assert-input-preconditions-not-just-output-metrics.md`
  — the sibling discipline this doc narrows: assert what a function's
  input actually is before trusting what it outputs, here applied to a
  single optional parameter rather than a whole loop's input shape.
- `docs/evidence/2026-07-28-stackup-partial-revert.md` — Instance 1's
  fix and the `.endswith(".Cu")` half that remains correct today.
- `docs/evidence/2026-07-27-creepage-burndown.md` — Instance 2's full
  context: the `voltage_ratings.get(hv_net, 230.0)` call site and its
  effect on the reported violation set.
