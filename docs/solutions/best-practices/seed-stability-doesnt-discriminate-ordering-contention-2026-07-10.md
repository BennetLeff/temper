---
title: Seed-stability doesn't discriminate ordering from contention when seeds vary within priority tiers
date: "2026-07-10"
category: best-practices
module: temper_placer
problem_type: best_practice
component: testing_framework
severity: medium
applies_when:
  - "a routing failure is stable across seeds and you're interpreting that as 'genuine contention'"
  - "the router orders nets by priority class (power/HV first, signals last) and the seed varies within tiers"
  - "you're about to commit to a large fix based on seed-stability alone"
tags:
  - routing
  - diagnosis
  - seed-stability
  - false-inference
---

# Seed-stability doesn't discriminate ordering from contention when seeds vary within priority tiers

## Context

A board routed at 87.5% with the same 3 signal nets failing across 5 seeds. "Seed-stable" was interpreted as "genuine contention" — the nets are jointly unroutable — which would require negotiated-congestion (an engine rebuild). But the router orders nets by netclass priority: power and HV nets first, signal nets last. The seed varies tie-breaking and search randomization *within* priority tiers, not *across* them. So "same 3 signal nets fail across 5 seeds" is fully consistent with both hypotheses:

- **Ordering:** these three are always ordered last, they always lose the channel to higher-priority nets, and there's slack that would appear if they went first — which no seed ever tries.
- **Contention:** the three genuinely over-subscribe a shared region, and no ordering fits all of them.

Seed-stability proves "deterministic," which is consistent with either branch. It answers nothing about which branch you're in.

## Guidance

When seed-stability is the only evidence for a fundamental limitation, check whether the seed actually varies the *discriminating variable*. If the seed only varies within priority tiers and the suspect nets are always in the same tier (always last), seed-stability is a non-result — you've tested zero configurations of the variable that matters.

The true discriminator is the **explicit reorder test**: force the suspect nets to route first (or last), and watch whether previously-routed nets break. This directly measures whether total demand exceeds channel supply (contention) or whether there's slack (ordering). A single reorder test is strictly more informative than a thousand seed sweeps that never touch the priority order.

## Why This Matters

The temper board diagnosis spent two turns on "genuine contention" based on seed-stability, only to be overturned by a single coexistence round in the existing routing log. The seed sweep had tested zero configurations where signal nets routed before power nets — the only configurations that could have discriminated the two hypotheses. The error was treating a non-result (stable-under-non-discriminating-variation) as evidence. One explicit positive check (Round 4 coexistence) retired the entire cathedral (negotiated-congestion) and confirmed the shed (ordering).

## When to Apply

- Any time "stable under randomization" is cited as evidence for a fundamental limitation — check whether the randomization varied the variable that actually discriminates.
- Routing failures where nets are tiered by priority class.
- More broadly: any diagnosis where "it fails consistently" is being used to claim "it's intrinsically broken" — find the variable that would prove the opposite, and vary that one specifically.

## Examples

```
WRONG (non-discriminating):
  "Same 3 signal nets fail across 5 seeds → genuine contention → build negotiated-congestion."

RIGHT (discriminating):
  "Does a single round exist where all 6 critical nets coexist? Round 4: yes. 
   Slack is proven. Ordering fix is safe. No engine needed."
```

## Related

- `docs/solutions/best-practices/round-coexistence-cheaper-than-seed-stability-2026-07-10.md` (the direct positive check that overturns the seed-stability inference)
- `docs/solutions/best-practices/per-net-isolation-routing-diagnosis-2026-07-10.md` (the companion diagnosis: "does a legal path exist?")
