---
title: "Index: six documents from the 2026-08-19/20 verification session"
date: "2026-08-20"
category: index
module: temper
problem_type: methodology
component: documentation
severity: informational
applies_when:
  - "looking for what was found and fixed on 2026-08-19/20 without re-deriving it"
tags:
  - session-index
  - 2026-08-19
  - 2026-08-20
---

# Index: six documents from the 2026-08-19/20 verification session

This session (2026-08-19 through 2026-08-20) worked across several branches
verifying claims about DRC/metric tooling, the mains↔SELV isolation barrier,
five components believed to need substitution, a stale routing workaround,
and the declared 1800 W power rating. None of the branches below is merged
to main; none of this documentation changes any code, threshold, `.ato`
file, or the board (`pcb/temper.kicad_pcb` sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`,
unchanged throughout, including by the writing of these documents).

| Document | Subject | Headline |
|---|---|---|
| [`checks-that-cannot-fail-catalogue-2026-08-20.md`](architecture-patterns/checks-that-cannot-fail-catalogue-2026-08-20.md) | Ten checks that were structurally incapable of failing | A DRC parser reading 1 of 10 keys, a fraction rendered as a percent, a blocking SLO that never evaluated a record, a "CI tripwire" never wired to CI, a classifier matching 1 of 27 real net names, and more |
| [`isolation-barrier-single-scalar-vs-per-pairing-2026-08-20.md`](architecture-patterns/isolation-barrier-single-scalar-vs-per-pairing-2026-08-20.md) | `MIN_BARRIER_WIDTH_MM = 12.6` | One scalar for a 27-net domain boundary was simultaneously ~1.6× too generous (DC bus, 8.0 mm) and ~1.6× too small (resonant tank, ≥20.0 mm and not fully determinable) |
| [`five-parts-one-bench-measurement-2026-08-20.md`](best-practices/five-parts-one-bench-measurement-2026-08-20.md) | C6, K1, U6, T1, T2 | Under per-pairing figures, four of five clear; T1 alone remains, and its remaining question rests on a **simulated, not yet bench-measured**, 41–53 mV against a 1.0 V threshold |
| [`stale-backbone-layer-workaround-2026-08-20.md`](architecture-patterns/stale-backbone-layer-workaround-2026-08-20.md) | `BACKBONE_LAYER = "F.Cu"` | A workaround for a since-fixed audit-tool limitation, itself re-examined and correctly judged safe on the wrong axis, fail-closed 83 of 87 ground-plane MST edges; connectivity chain 339 → 304 → 282 → 251 |
| [`power-stage-1800w-rating-unreachable-2026-08-20.md`](logic-errors/power-stage-1800w-rating-unreachable-2026-08-20.md) | `p_output_max = 1800W` | A units error (input vs. output), unreachable on a 15 A branch at any component change (honestly derived ceiling: 1015 W), read by nothing until this session's fix |
| [`ato-assertion-vacuity-paydown-2026-08-20.md`](best-practices/ato-assertion-vacuity-paydown-2026-08-20.md) | Electrical assertion vacuity | Circuit-coupled assertions 12 → 27; 5 now fail against real component ratings (fuse/choke/relay undersized, gate driver oversubscribed, OVP divider over-rail) |

## Reading order

The isolation-barrier and five-parts documents are the most tightly coupled
— read them together. The catalogue document cross-references specific
findings in the other five; it is a reasonable starting point if the goal is
"what shape of defect keeps recurring in this codebase" rather than "what is
the current status of the barrier / the power budget."

## What every document in this set has in common

Each was written against a specific committed branch or commit, with the
figure re-checked directly (`git show`, `gh pr view`/`gh pr diff`) rather
than taken from the session's own prior summary. Three figures relayed at
the start of this documentation task did not reproduce and are recorded as
discrepancies rather than repeated:

1. **28.83 A** (fuse/choke/relay draw) — does not appear as a written
   literal anywhere in `git log --all`, but it is exactly reproduced by
   hand-evaluating the landed assertion's own formula (16.6667 A × 1.73 =
   28.8333 A); the repo's simulated figure for the same physical quantity is
   **28.81 A**. Both are legitimate citations for different derivations of
   the same draw (`docs/solutions/best-practices/ato-assertion-vacuity-paydown-2026-08-20.md`).
2. **1620 W** (power ceiling "at the repo's own eta_min = 0.90") — the repo
   states a bracket, **1530–1656 W**, not a point value, and the honestly
   derived figure using the design's actual simulated power factor is
   **1015 W** (`docs/solutions/logic-errors/power-stage-1800w-rating-unreachable-2026-08-20.md`).
3. **"Roughly 280 W, bound by bus-capacitor ripple"**, and **"I verified
   ZBNC18-13's C4 = 8UF/275ACV myself from the filing"** — neither reproduces
   as stated. The as-built ripple ceiling is **146 W** (bracket 133–158 W);
   an intermediate **277 W** figure exists once a superseded tank-current
   anchor is corrected, which is close to "~280 W" but is not the chain's
   endpoint — the chronologically last branch on this question
   (`analysis/bus-capacitance-selection`) shows a correctly sized capacitor
   bank removes the bus bank as the binding constraint entirely, at which
   point the rectifier diodes bind instead, at **396–704 W (central
   609 W)**. The FCC-filing verification claim is contradicted by the
   repo's own record, which states the filing retrieval failed (HTTP 403)
   and labels the ZBNC18-13 finding second-hand and unverified
   (`docs/solutions/logic-errors/power-stage-1800w-rating-unreachable-2026-08-20.md`).

One claim from the original session summary — that `check_placement_roundtrip`
was off by `board.origin` (8, 20) mm across 689 pads — was initially reported
as **could not verify** by a first search pass, then located and confirmed
on a second pass (`docs/solutions/architecture-patterns/checks-that-cannot-fail-catalogue-2026-08-20.md`,
row 7). It is a real, reproducible finding; the first miss was a search-scope
problem, not a defect in the underlying claim.

## Verification method

Each document was checked read-only against `origin/` branches — no branch
in this repository was checked out or modified to write these documents,
and `pcb/temper.kicad_pcb`'s sha256 was verified unchanged before and after
this documentation pass. Several figures were independently checked by more
than one pass (a dedicated verification review, this document's own direct
reads, and a correction relayed by the task coordinator from a separately
verifying peer session) and agreed exactly. Where a figure did not
reproduce, it is stated as such in the relevant document rather than
omitted or silently corrected.
