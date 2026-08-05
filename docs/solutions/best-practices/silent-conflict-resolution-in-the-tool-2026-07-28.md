---
title: "When the tool resolves a conflict for you, the API that hides it is the one you will reach for"
date: "2026-07-28"
category: best-practices
module: elec
problem_type: best_practice
component: hardware_design
severity: critical
applies_when:
  - "reading design metadata through a tool's convenience API that returns one value where the underlying model holds several"
  - "two sources of a declaration can be merged by the tool (linked signals, inherited class layers, overlays) and the merge is not surfaced"
  - "planning to detect disagreement between declarations without first checking whether the reader can still see the disagreement"
  - "a safety classification is read through any accessor whose signature returns a scalar"
tags:
  - fail-soft
  - silent-resolution
  - atopile
  - declaration-conflict
  - api-choice
  - net-classification
---

> **Status update (2026-08-03 refresh):** `scripts/_lib/ato_extract.py` and `scripts/_lib/net_classification.py` never landed on main (they live on the unmerged `feat/ato-net-classification-ssot` branch). The atopile silent-merge finding stands — the current atopile-declaration consumer is `packages/temper-design-bundle/src/atopile.rs`.


# When the tool resolves a conflict for you, the API that hides it is the one you will reach for

## What happened

The plan for declaring net safety domains in `.ato` named atopile's
`get_data_dict(addr)` as the reader, and specified that *merged-signal
disagreement is a generation error*. Both statements were reasonable.
Together they were unimplementable, and nothing in the plan revealed
that.

atopile merges assignments across `~` links. That is load-bearing and
good: declaring `safety_domain` on one signal makes it readable on every
signal joined to it, which is exactly what lets one declaration classify
a whole net. But when two linked instances declare the *same* field
differently, atopile keeps `assignments[0]` and drops the rest with no
warning.

Measured, on two signals joined with `~`:

```ato
    gamma ~ delta
    gamma.safety_domain = "HV"
    delta.safety_domain = "SELV"
```

Both read back `"SELV"`. Last write wins. An HV declaration is silently
replaced by a SELV one, on a mains-connected design, and the reader the
plan named cannot tell.

The evidence was not gone — it was one layer down. `Instance.assignments`
is a `deque`; `get_data_dict` returns `{k: v[0].value}`. The losing
assignments were still there, with their source contexts. Reading the
deque directly instead of the convenience accessor turned an invisible
coin flip into a report naming both values and both `file:line`s.

## Why the convenience API is the trap

`get_data_dict` has exactly the signature you want. It takes an address
and returns a dict of that instance's data. Nothing about it suggests it
is lossy, and for every non-conflicting field it is not. It is lossy only
in the case you are specifically trying to detect — which is why you will
choose it, and why it will look correct in every test you write from
happy-path examples.

The general shape: **an accessor that returns a scalar where the model
holds a sequence has already made a decision for you.** Whether that
decision is safe depends entirely on whether the sequence can ever hold
disagreement. Nobody documents that, because from inside the tool it is
not a decision at all — it is just how resolution works.

## What to do

1. **Before planning to detect a conflict, verify the reader can still
   see it.** Write the conflicting case first and check that the value
   you get back reflects it. If both members read the same, your detector
   has nothing to detect and you will discover this after building it.

2. **Prefer the accessor that returns the collection.** `assignments`
   over `get_data_dict`; the raw list over the resolved value. Resolve in
   your own code, where refusing to resolve is an option the tool did not
   offer you.

3. **Distinguish resolution from disagreement.** The first pass at this
   detector produced 513 false positives against the real design, in two
   distinct classes, and neither was a defect:
   - **463** were a component's own `field: type` declaration (value
     `None`) sitting above its assignment. A declaration is not a
     competing value.
   - **50** were genuine class-layer overrides — a component setting a
     default `footprint` that the instantiating module overrides. Normal,
     intended, and *indistinguishable at the deque level* from a
     link-merge clash: both are just a field with two values.

   Both were fixed by narrowing the predicate against a measured
   denominator, not by loosening the check. The 50 are pinned by a test
   asserting they are still present, so the scoping cannot quietly stop
   being load-bearing.

4. **Ordering can flip a hard error into a silent one.** In this same
   tool, assign-then-connect *raises* (`"The source and target separately
   defined values"`) while connect-then-assign resolves silently. The
   strict path and the silent path are the same two declarations in a
   different order. Do not conclude a tool is safe because one ordering
   errored.

## Related

- [[rename-orphans-derived-keys-2026-07-28]] — the defect that motivated
  declaring classification in the design source at all.
- [[fail-soft-defaults-hide-the-failure-2026-07-28]] — same shape one
  level up: a default that fires instead of an error. Here the tool
  supplied the default.
- `scripts/_lib/ato_extract.py` — the deque-reading extractor.
- `scripts/_lib/net_classification.py` — the fold that refuses to resolve
  disagreement, with the monoid laws that make it order-independent.
