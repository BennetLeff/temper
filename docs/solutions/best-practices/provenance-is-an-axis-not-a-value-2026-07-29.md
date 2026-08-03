---
title: "Provenance is an axis, not a value — domain_provenance split out from safety_domain"
date: "2026-07-29"
category: best-practices
module: net_classification
problem_type: best_practice
component: hardware_design
severity: high
applies_when:
  - "a domain value has a state meaning 'nothing applies here' (none, n/a, default, unclassified) and that state is being used to close out a batch of items no human has actually reviewed"
  - "a computation is being designed to produce the same value that would normally assert 'a human looked at this'"
  - "extending a classification to cover previously-undeclared items and the honest answer is 'derived, not reviewed'"
  - "a field's value implicitly carries a claim about HOW it was established, and that claim is being overloaded onto the value itself"
tags:
  - provenance
  - domain-provenance
  - safety-domain
  - monoid
  - audit-backlog
  - net-classification
  - reviewed-vs-derived
---

> **Status update (2026-08-03 refresh):** `scripts/gen_net_classification.py` / `scripts/derive_net_domains.py` (with `report_denominators` and `domain_provenance` values) exist only on the unmerged `feat/ato-net-classification-ssot` branch. The pattern stands; the reviewed/derived split is not emitted by any main script today — `scripts/check_domain_partition.py` is the live gate.


# Provenance is an axis, not a value

## Context

`safety_domain` in this project's net-classification model is a three-state
domain: `HV`, `SELV`, or `"none"`. `"none"` is not an absence — it is
documented in `scripts/_lib/net_classification.py` as "the explicit
'reviewed, not safety-relevant' state — a positive statement that someone
looked, which is why it is a value rather than an omission." That assertion
is load-bearing: `elec/domain_manifest.yaml` is a human safety-review
record, and every net marked `"none"` in it carries the implicit claim that
a person examined it and concluded it does not participate in the HV/SELV
boundary.

Commit `81cffb90` needed to declare domain for the 110 of 164 compiled nets
that `elec/domain_manifest.yaml` had never reviewed. No amount of computing
harder can make "a human looked at this" true for a net nobody has looked
at — `scripts/derive_net_domains.py` proposing `"none"` for any of those 110
nets would have silently converted a genuine review gap into what reads,
downstream, as a closed one.

The resolution (commit `f612b676`) added `domain_provenance` as an
independent field — `"reviewed"` or `"derived"` — folding through the same
commutative, idempotent monoid `safety_domain` already used, with matching
property-based tests. `safety_domain` still says HV/SELV/none/unwired.
`domain_provenance` separately says who decided it: the 54 nets
`elec/domain_manifest.yaml` already covers (plus 4 protective-impedance
chain-interior nodes the manifest judges directly) are `"reviewed"`; the 110
nets `derive_net_domains.py` proposed from netlist connectivity are
`"derived"`. `scripts/gen_net_classification.py`'s `report_denominators`
prints the reviewed/derived split on every run, so the size of the
human-audit backlog is queryable from CI output instead of invisible now
that every net carries *some* declaration.

## The pattern

**A value that carries an implicit claim about how it was established is
overloaded the moment that claim can be false.** `"none"` meaning
"reviewed and not relevant" works fine as long as every net that could ever
receive it has, in fact, been reviewed. It breaks the instant a system
needs to assign a *value* to something it has not been able to make the
*claim* about — and the break is silent, because `"none"` looks identical
whether a person spent an hour on the net or a script never touched it.

The fix generalizes past this one field: whenever a value's meaning bundles
"what is true" together with "how confident/verified is this," split the
provenance out as its own axis rather than picking the value that has the
closest-sounding meaning. Bundling them means every future consumer of the
value has to also know which meaning was intended at write time, with
nothing in the type system or schema to tell them apart.

## What to do

1. **When a domain's "nothing applies" state is also implicitly an
   assertion that a human looked, do not let automated derivation write
   that state.** If a script needs to propose a value for something in that
   state's domain, either the state needs to change to something the script
   can honestly claim, or provenance needs to be tracked separately so the
   claim isn't silently misattributed.
2. **Fold provenance through the same algebra as the value it accompanies.**
   `domain_provenance` uses the identical commutative/idempotent monoid
   `merge`/`fold` as `safety_domain` (see
   `scripts/_lib/net_classification.py`), with the same property tests, so
   a net's provenance is as order-independent and well-defined as its
   domain — not a bolt-on string nobody validates.
3. **Report the split on every run, not just at the moment it's
   introduced.** `report_denominators` makes "how many nets are still only
   derived" a number in CI output every time, keeping the backlog visible
   as new nets are added rather than requiring someone to re-audit the
   whole set.
4. **Scope any consumer that assumes "reviewed" to actually check
   provenance, not just presence.** `DomainManifestEmitter`'s cross-check
   against `elec/domain_manifest.yaml` (a human review record) is scoped to
   `provenance="reviewed"` nets only — otherwise 110 unreviewed proposals
   would dilute a document whose entire value is that everything in it was
   actually looked at by a person.

## Why This Matters

Before this split, closing the "110 undeclared nets" gap had exactly two
honest options: leave them undeclared (which is what an earlier pass in
this same effort did, and see
[[reimplementing-a-gate-reproduces-inputs-not-logic-2026-07-29]] for how
that pass also mis-measured the reason why), or mark them `"none"` and
silently claim 110 nets had been safety-reviewed when none had. Neither
option was acceptable for a mains-connected safety-critical board.
`domain_provenance` makes a third option honest: assign a real domain value
from netlist derivation, and say plainly, in a field a gate checks, that
nobody has reviewed it yet.

## When to Apply

- Designing or auditing any classification scheme where one state doubles
  as an implicit claim about verification, human review, or trust level.
- Extending automated derivation to cover a domain whose existing "closed"
  state was only ever written by a human process.
- Reviewing a field whose meaning silently depends on "how was this value
  produced" — check whether that dependency is written down anywhere a
  reader (or a gate) can see it.

## Examples

```python
# scripts/_lib/net_classification.py
HV_DOMAIN: Final = "HV"
SELV_DOMAIN: Final = "SELV"
NOT_SAFETY_RELEVANT: Final = "none"     # <- "someone looked, and it's not relevant"
UNWIRED_DOMAIN: Final = "unwired"

REVIEWED_PROVENANCE: Final = "reviewed"  # <- a human safety engineer looked
DERIVED_PROVENANCE: Final = "derived"    # <- derive_net_domains.py proposed it
```

```
# 110 previously-undeclared nets, split by provenance (commit 81cffb90):
10 HV   + 73 SELV  -> domain_provenance = "derived"   (netlist-connectivity proposal)
 4 mid-chain nodes  -> domain_provenance = "reviewed"  (manifest already judges these)
23 zero-pin nets    -> safety_domain = "unwired" (see encode-facts-as-facts-not-judgments)
10 + 73 + 4 + 23 = 110
```

## Related

- [[encode-facts-as-facts-not-judgments-2026-07-29]] — the sibling addition
  in the same commit: a fourth `safety_domain` state, `"unwired"`, for a
  machine-verifiable fact that isn't a safety judgment either.
- [[reimplementing-a-gate-reproduces-inputs-not-logic-2026-07-29]] — the
  correction one commit later that found the 110 nets were derivable at
  all, after an earlier pass wrongly concluded the board was one
  unpartitioned blob.
- `scripts/_lib/net_classification.py` — `merge`/`fold`, the monoid both
  `safety_domain` and `domain_provenance` fold through.
- `scripts/derive_net_domains.py` — the derivation that proposes
  `domain_provenance = "derived"` values, self-validated by reproducing all
  54 already-reviewed nets exactly before any of the 110 were trusted.
- Commit `f612b676` — `feat(net-classification): add domain_provenance axis
  and unwired domain state`.
- Commit `81cffb90` — `feat(elec): declare the remaining 110 net domains,
  all 164 nets now classified`.
