---
title: Round coexistence is a cheaper slack detector than seed-stability or reorder tests
date: "2026-07-10"
category: best-practices
module: temper_placer
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - "a routing failure could be ordering-displacement or genuine contention, and you need to know which"
  - "the router produces per-round routing logs (each net routed/failed per round)"
  - "seed-stability looks like it discriminates but can't — the seed varies within tiers, not across them"
tags:
  - routing
  - diagnosis
  - slack-detection
  - coexistence
  - seed-stability
---

# Round coexistence is a cheaper slack detector than seed-stability or reorder tests

## Context

A board routes at 87.5% with the same 3 signal nets failing across multiple seeds. The failure appeared stable under randomization — suggesting genuine contention (the nets are jointly unroutable, and no ordering can fix it). But the seed varied only within priority tiers, not across them: signal nets were always ordered last, so they always lost the channel to higher-priority power nets. Seed-stability couldn't discriminate the two branches, and the explicit reorder test (route signals first, watch whether others break) was blocked by a broken adapter.

## Guidance

Before concluding "it's fundamentally X," look for **direct evidence of not-X** — it's often already in the routing logs, cheaper than the inference you were about to trust. For distinguishing ordering from contention: find a single round in the routing log where **all** the critical nets coexist simultaneously.

- **Coexistence round exists** → slack is proven. The nets *can* all fit. The failure is ordering/displacement — the cheap branch. A reorder fix is safe: routing signals last won't displace power nets because they already coexisted.
- **No coexistence round** → the nets may genuinely be jointly unroutable under the current constraints. Contention is not ruled out — escalate to the negotiated-congestion rung only here.

A single positive observation (one round where all six nets are simultaneously routed) conclusively rules out the "fundamentally jointly unroutable" hypothesis. That's a one-line grep of the routing log — no code change, no reorder test infrastructure, no seed sweep — while a seed sweep can produce the same failure pattern under *either* hypothesis and gives you nothing.

## Why This Matters

The two "genuine contention" turns of the temper board diagnosis were plausible but wrong — they trusted an indirect inference (seed-stability, final-round displacement) that a direct positive check overturned for free, from evidence already in the Round 4 log. The generalization: "does a coexisting state exist?" beats "is the failure stable under randomization?" every time.

## When to Apply

- Any routing failure where the router produces per-round logs and the nets could be fighting for scarce channels.
- When you're about to build a negotiated-congestion engine on "seed-stable failure" or "final-round displacement" evidence — check the logs for a coexistence round first. The cathedral might be unnecessary.
- Extends beyond routing: any diagnosis where "stable under X" is being treated as evidence for a fundamental limitation — look for direct counter-evidence first.

## Examples

On the temper board, parsing the routing log from `route_pcb`:

```
Round 4: GATE_H, GATE_L, PWM_H, SPI_CLK, SPI_MOSI, I_SENSE — all routed simultaneously.
>>> SLACK PROVEN — ordering fix is safe.
```

One round, one grep, the entire "genuine contention" hypothesis retired. The ordering fix is safe because Round 4 proved these six nets can all coexist — the failure is displacement, not zero-sum resource contention.

## Related

This is **step 2 of the routing-diagnosis ladder** — within the router-side branch established by step 1.
- `docs/solutions/best-practices/per-net-isolation-routing-diagnosis-2026-07-10.md` — step 1 (isolation: router-side vs placement-side)
- `docs/solutions/best-practices/seed-stability-doesnt-discriminate-ordering-contention-2026-07-10.md` — the anti-pattern that makes this check necessary (why seed-stability is a non-result)
- `docs/solutions/best-practices/three-target-verification-ladder-correctness-soundness-validity-2026-07-10.md` (the same "direct counter-evidence beats indirect inference" pattern)
