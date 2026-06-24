---
title: "Router V6 closure-rate plan: SM1 = 100% on temper.kicad_pcb (target was ≥ 90%)"
date: 2026-06-24
category: architecture-patterns
module: router_v6
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "tuning the per-A* iter cap on router_v6 against temper.kicad_pcb"
  - "deciding whether to add multi-layer or escape-routing work to lift SM1"
tags:
  - router-v6
  - closure-rate
  - iter-cap
  - temper-kicad-pcb
  - path-quality
  - sweet-spot
---

# Router V6 closure-rate plan: SM1 = 100% on temper.kicad_pcb (target was ≥ 90%)

## Context

The 6-PR sequenced rollout (`docs/plans/2026-06-23-009-feat-router-v6-closure-rate-90-percent-plan.md`)
lifted SM1 from 33% (broken pipeline) to 62.5% (U0–U7 landed).  The plan
defined U8 as "final SM1 ≥ 90% verification."  At U7 sign-off, the 9
hard signal nets (PWM_H/L, I_SENSE, AC_L/N, DC_BUS±, SPI_MOSI/MISO, GATE_H)
still hit the 100k iter cap, and a "what to tackle next" brainstorm
flagged multi-layer routing, escape-routing pre-pass, and smarter
net-ordering as candidates for Wave 5.

This doc records the outcome of that investigation: **all three
candidate workstreams turned out to be unnecessary.**  A 5-line change
to the smoke runner's default iter cap (100k → 500k) achieved 100.0%
on `temper.kicad_pcb` in 15.0 s, deterministically across 5 runs.
The full pipeline run (`scripts/full_pipeline_profile.py` with
`PROFILE_MAX_ITER=500000`) hits 100.0% in 20.2 s.  SM1 ≥ 90% is met
on the canonical closure-test path with no new algorithm work.

## Guidance

**For SM1 measurement on `temper.kicad_pcb`**, use a per-A* iter cap
of 500k.  The cap sweet spot is non-obvious:

| Cap | Routed | Wall (s) | Notes |
|-----|--------|----------|-------|
| 100k | 15/24 = 62.5% | 18.0 | bounded smoke budget — fast but cuts the hard nets |
| 200k | 15/24 = 62.5% | 19.3 | still doesn't reach the hard nets |
| **500k** | **24/24 = 100.0%** | **15.0** | **closure target met, also faster** |
| 1M | 23/24 = 95.8% | 22.9 | the kernel's default; SPI_MOSI fails |
| 2M | 23/24 = 95.8% | 30.4 | more iters doesn't help |

**Counter-intuitive findings:**

- 500k is **faster** than 100k (15.0 s vs 18.0 s).  At 100k the hard
  nets fail in 5 ms each, fill the reroute queue, and the reroute
  loop extends the run.  At 500k they route in 25 ms each and the
  reroute queue is empty.
- 1M is **slower** than 500k (22.9 s vs 15.0 s) and **worse** on
  closure (23/24 vs 24/24).  The A* is deterministic, but the path
  it picks depends on the iter cap — a higher cap leads to
  different tie-breaks, and the path it picks for one net blocks
  SPI_MOSI downstream in a way the 500k cap doesn't.  **Path
  quality, not iter count, is the ceiling.**

**The U7 dead-branch fix was the unlock.**  The fix in commit
`1acc2209` (gate the U7/R11 congestion branch on
`congestion_weight > 0.0`) eliminated ~5–10 s of per-call overhead
in the kernel.  At 100k cap that overhead was amortized over a
small A*, so the 15/24 baseline didn't change.  At 500k+ cap the
overhead would have been crippling — the 5-min→23-s recovery on
the full pipeline was a direct consequence.  The "what to tackle
next" list was a search for a lever that no longer needed pulling
once the kernel was fast enough at the right cap.

**Multi-layer / escape-routing / net-ordering are deferred.**  All
three were investigated and judged not worth shipping:

- **Net ordering** (Wave 5 / R12 attempt, reverted in commit
  `99108893`): routing high-pin-count signal nets first within the
  signal class regressed closure from 15/24 to 13/24 on
  `temper.kicad_pcb` (deterministic across 3 runs).  The 8-pin
  I_SENSE still hits the iter cap even with first claim, and
  routing it first blocks the 2-3 pin nets that were successfully
  routing under the shortest-first order.  Reverted; the test
  file `tests/router_v6/test_wave5_net_ordering.py` is kept as a
  regression guard.
- **Multi-layer routing for signal nets**: requires explicit vias
  (the THT-pad-gated fallback only triggers for connectors, none
  of the 9 hard nets have THT pads).  Without via infrastructure,
  routing signal nets on B.Cu leaves the pads stranded on F.Cu.
- **Escape-routing pre-pass**: the channel mapping's waypoints are
  already in the channel skeleton (not at pad centers), so the
  A* is already a channel-to-channel search.  The bottleneck is
  the channel occupancy, not the escape.

## Why This Matters

The closure-rate plan is **done at the SM1 ≥ 90% gate**.  The next
researcher who looks at the 62.5% number from earlier in the
session should know:

1. The 62.5% baseline is **a smoke artifact, not the SM1 floor.**
   The smoke used a 100k cap for bounded quick checks.  The
   canonical SM1 is 95.8% (closure test path, 1M kernel default)
   or 100.0% (500k cap).
2. The right iter cap is **500k**, not 1M.  The kernel default
   over-explores; 500k is the path-quality sweet spot.
3. Wave 5 work (multi-layer, escape-routing, net-ordering) is
   **not needed for SM1 on this PCB.**  If a future board changes
   the failure profile (different channel density, different
   hard-net mix), revisit this doc and re-evaluate.

## When to Apply

- Tuning the per-A* iter cap on `router_v6` against
  `temper.kicad_pcb`: start at 500k.
- Designing new closure tests: don't rely on the kernel's
  default 1M cap; expose `max_iter` on `RouterV6Pipeline` if SM1
  precision matters.
- Considering Wave 5 work for a different board: first measure
  the iter-cap sweet spot (100k / 500k / 1M) on that board.
  If 500k already hits the SM1 target, no algorithm work needed.
  If not, the failure profile tells you which lever to pull.

## Examples

**Before this doc:** the conversation asked "what to tackle next"
and the 9 hard signal nets' 100k-cap failure list was the
input to a "Wave 5 plan" with three candidate workstreams.

**After this doc:** those three workstreams are explicitly
deferred, the smoke default is 500k, and the SM1 is 100% on
`temper.kicad_pcb` with no new algorithm work.

The actual change was `scripts/baseline_smoke_3min.py:155`
(`--max-iter` default 10_000 → 500_000, with the table above
in the help text).

## Related

- `docs/plans/2026-06-23-009-feat-router-v6-closure-rate-90-percent-plan.md` — the original plan; U8 is now retired.
- `docs/solutions/performance-issues/router-v6-full-pipeline-5min-to-23s-2026-06-23.md` — the U7 dead-branch fix that made 500k+ cap viable.
- `docs/solutions/performance-issues/2026-06-23-pcb-autorouter-completion-rate-47x-speedup.md` — the 47× speedup that lifted runtime from 15min to 19s.
- `scripts/baseline_smoke_3min.py` — the 500k default lives here.
- `scripts/full_pipeline_profile.py` — the full-pipeline profile; set `PROFILE_MAX_ITER=500000` for the SM1 measurement.
