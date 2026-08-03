---
title: "Encode machine-verifiable facts as facts, not as judgments — the unwired domain state"
date: "2026-07-29"
category: best-practices
module: net_classification
problem_type: best_practice
component: hardware_design
severity: medium
applies_when:
  - "a classification scheme has a catch-all state that also means 'reviewed and not applicable', and some items could receive that state purely from a mechanical/structural fact rather than a judgment call"
  - "a net, field, or record has zero of the connections/references/usages that would make a category applicable, and you're deciding what value to assign it"
  - "adding a state to a domain and deciding whether a gate should be able to re-verify it against ground truth, or must trust it as asserted"
  - "the honest answer to 'is this genuinely unused or a forgotten connection' is 'nobody has decided' and the current scheme has no way to say that"
tags:
  - unwired-domain
  - fact-vs-judgment
  - self-verifying-state
  - net-classification
  - domain-provenance
  - gate-re-verification
---

> **Status update (2026-08-03 refresh):** the `scripts/_lib/net_classification.py` / `scripts/gen_net_classification.py` machinery described here (including `UNWIRED_DOMAIN` and the `unwired` state) exists only on the unmerged `feat/ato-net-classification-ssot` branch — it never landed on main. The pattern stands; the live domain SSOT on main is `elec/domain_manifest.yaml` + `scripts/check_domain_partition.py`.


# Encode machine-verifiable facts as facts, not as judgments

## Context

Of the 110 nets left undeclared before commit `81cffb90`, 23 have zero
connected pins in the compiled netlist (`elec/build/default.net`). The
"nothing applies" state already available, `safety_domain = "none"`,
means "reviewed and found not safety-relevant" — see
[[provenance-is-an-axis-not-a-value-2026-07-29]] for why that state
specifically asserts human review. Declaring these 23 nets `"none"` would
have made that assertion for all 23, when what is actually known about them
is narrower and different in kind: they have no wired pins, full stop, and
nobody has determined whether that's intentional (a genuinely unused
provision) or a forgotten connection.

The fix added a fourth `safety_domain` value, `UNWIRED_DOMAIN = "unwired"`,
documented in `scripts/_lib/net_classification.py` as "a machine-verifiable
FACT (this net has zero connected pins in the compiled netlist), not a
safety judgment." Distinct from `"none"` specifically because "genuinely
unused" versus "forgotten connection" is exactly the question nobody has
answered, and `"unwired"` doesn't pretend otherwise. Commit `b8e669f1`
added the corresponding verification: `check_unwired_nets_are_actually_
unwired` in `gen_net_classification.py` checks each `"unwired"`-declared net
against the compiled netlist directly, reusing `check_domain_partition.py`'s
own parser and freshness check — a net declared unwired that later gains a
wired pin becomes a **gate error**, not a silently stale claim.

## The pattern

**A fact and a judgment look identical as a string in a YAML file, and
require opposite handling.** `"unwired"` is checkable: run the generator,
count pins, compare. `"none"` (in this scheme) is not checkable by any
computation — it is a record of what a person concluded, and no amount of
static analysis can confirm or refute a conclusion nobody has stated
grounds for beyond "I looked and it's fine." Collapsing both into the same
catch-all value throws away the distinction that determines whether a gate
can ever re-verify the claim.

The generalizable move: when a domain has a state that is machine-derivable
from the artifact itself, give it its own value and let a gate
re-derive/re-check it on every run. Reserve the state that means "a human
decided" for cases where a human genuinely had to decide — and don't let
automated derivation write into that state, because doing so launders an
unreviewed proposal as a completed review (see
[[provenance-is-an-axis-not-a-value-2026-07-29]]).

## What to do

1. **Ask, for any "not applicable" catch-all value, whether every future
   member could always honestly receive it, or whether some future members
   will only ever satisfy a narrower, checkable condition.** If the answer
   is "some only satisfy the narrower condition," give that condition its
   own state.
2. **Make the new state self-verifying wherever the underlying fact is
   re-derivable.** `check_unwired_nets_are_actually_unwired` doesn't just
   accept `"unwired"` as declared — it re-parses the compiled netlist and
   confirms zero wired pins every run, turning a claim that could go stale
   into one that cannot silently drift from reality.
3. **Reuse existing parsing/freshness machinery for the re-check rather than
   writing a second netlist reader.** The unwired check reuses
   `check_domain_partition.py`'s parser and freshness check directly,
   avoiding a second implementation that could disagree with the first
   about what "the compiled netlist" currently says.
4. **Leave the open question open in the data model, not resolved by
   default.** `"unwired"` explicitly does not resolve "unused" vs.
   "forgotten" — it states the one fact that is actually known and defers
   the judgment. A scheme that forced a choice between `"none"` (implying
   reviewed) and some other partitioned domain would have manufactured an
   answer nobody actually has.

## Why This Matters

23 of 164 nets on a mains-connected board had zero wired pins and no
history of anyone deciding why. Marking them `"none"` would have shipped a
record claiming a safety engineer reviewed 23 more nets than actually
happened, indistinguishable in the manifest from the 54 nets someone
genuinely did review. `"unwired"` keeps the record honest about exactly
what is and isn't known, and — because it's re-verified against the
compiled netlist on every run — a net that quietly gains a connection later
(a forgotten stub becoming load-bearing) is caught structurally instead of
depending on someone re-reviewing 164 declarations by eye.

## When to Apply

- Adding a new classification value: check whether it will ever be
  assigned as a judgment call versus purely from a structural/mechanical
  fact about the artifact — split them if both cases occur.
- Reviewing a "none"/"n/a"/"unclassified" catch-all state that some
  automated process is about to start writing into — confirm the
  automation can actually make the claim that value asserts.
- Any time a check declares a fact about an artifact (zero pins, zero
  references, zero usages) — make the check re-verify that fact on every
  run rather than trusting a one-time declaration.

## Examples

```python
# scripts/_lib/net_classification.py
NOT_SAFETY_RELEVANT: Final = "none"      # a human reviewed it, found no relevance
UNWIRED_DOMAIN: Final = "unwired"        # zero wired pins -- a FACT, not a judgment
```

```
# scripts/gen_net_classification.py -- re-verified every run, not just declared once
check_unwired_nets_are_actually_unwired:
  for each net declared safety_domain = "unwired":
    parse elec/build/default.net directly
    if the net now has >=1 wired pin: GATE ERROR
      (a net declared unwired that gains a pin is a stale claim, not a pass)
```

## Related

- [[provenance-is-an-axis-not-a-value-2026-07-29]] — the sibling axis added
  in the same commit: separating "who decided" from "what was decided,"
  which is why `"unwired"` could not simply have been folded into `"none"`.
- `docs/solutions/best-practices/fail-soft-defaults-hide-the-failure-2026-07-28.md`
  — the inverse failure shape: a missing input silently substituted with a
  plausible value. Here the fix goes the other direction, giving the
  missing judgment an honest, checkable name instead of a plausible
  default.
- `scripts/_lib/net_classification.py` — `UNWIRED_DOMAIN` and the
  documented reasoning for why it never folds into `"none"`.
- `scripts/gen_net_classification.py` — `check_unwired_nets_are_actually_
  unwired`.
- Commit `f612b676` — introduces the `"unwired"` state.
- Commit `b8e669f1` — adds the re-verification gate.
- Commit `81cffb90` — applies it to the real 23 zero-pin nets found among
  the 110 previously-undeclared.
