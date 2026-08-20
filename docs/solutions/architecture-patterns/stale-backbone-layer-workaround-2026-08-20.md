---
title: "BACKBONE_LAYER = F.Cu: a workaround that outlived the bug it worked around by five days, and the constant that outlived the fix by three more"
date: "2026-08-20"
category: architecture-patterns
module: temper-placer
problem_type: architecture_pattern
component: router
severity: high
applies_when:
  - "a routing/plane generator hardcodes a layer choice as a workaround for a limitation in a different tool (an audit script, a DRC checker)"
  - "the tool the workaround was compensating for gets fixed, and nobody re-checks whether the workaround's OWN cost (not just its correctness) still applies"
  - "a ground/power plane generator reports 0 segments on an inner layer while an outer layer is fully congested"
  - "reviewing whether rip-up or net-ordering could substitute for a placement/floorplan fix"
tags:
  - stale-workaround
  - ground-plane
  - backbone-layer
  - mst-edges
  - creepage-halo
  - rip-up
  - net-ordering
  - pad-connectivity-audit
  - temper-placer
---

# `BACKBONE_LAYER = "F.Cu"`: a workaround that outlived the bug it worked around by five days, and the constant that outlived the fix by three more

## Verdict, up front

Both plane generators (`packages/temper-placer/src/temper_placer/router_v6/_ground_plane.py`
and `.../router_v6/_power_islands.py`) hardcoded `BACKBONE_LAYER = "F.Cu"`.
The reason was a real limitation in `pad_connectivity_audit.py`: it unioned a
via's graph nodes only for layers literally named in the via's `layers`
tuple, so an In1.Cu segment could never be recognized as meeting an F.Cu/B.Cu
through-via. Routing the ground/power backbone on an inner layer would have
looked, to the audit, disconnected.

That limitation was fixed in `dabbeaf73` (2026-08-16). The workaround was not
removed until `a71765efe`/`fd4e73644` (2026-08-19) — **three more days**
after the fix, five days after the workaround itself landed
(`ce4c132d6`, 2026-08-11). In the interim, F.Cu — already carrying 652
routed segments and a 27,499 mm² HV keepout — was where the ground/power
backbone was forced to route, and it fail-closed **83 of 87** ground-plane
MST edges.

## Timeline

| Date | Commit | What happened |
|---|---|---|
| 2026-08-11 | `ce4c132d6` | `BACKBONE_LAYER = "F.Cu"` introduced in the In1.Cu ground-plane generator, as a workaround for `pad_connectivity_audit.py`'s via-union limitation |
| 2026-08-16 | `dabbeaf73` | `pad_connectivity_audit.py` fixed to parse untyped `(via ...)` s-expressions as THROUGH vias. Its own evidence-doc diff explicitly re-examines `BACKBONE_LAYER`: *"this also supersedes `_ground_plane.py`'s `BACKBONE_LAYER = "F.Cu"` rationale comment... but the backbone layer itself is unchanged — F.Cu is one of the via's declared layers and still unions correctly."* |
| 2026-08-19 | `a71765efe` | Ground backbone moved to In1.Cu. In1.Cu segments 0 → 294. `unconnected_items` 339 → 304. |
| 2026-08-19 | `fd4e73644` | Power-island backbones moved to In2.Cu. In2.Cu segments 0 → 227; F.Cu 652 → 578 → 485 across the two fixes. `unconnected_items` 304 → 282. |
| 2026-08-19 | `6a6718a21` | Root-cause analysis of the remaining zero-copper nets (see below). |
| 2026-08-19 | `bc3a19b06` | Per-pairing placement routed and measured: `unconnected_items` 282 → 251. |
| 2026-08-20 | `4ea597f2d` | Rip-up and net-ordering shown not to substitute for the placement/backbone fix (see below). |

```
git show ce4c132d6 -s
git show dabbeaf73 -s
git show a71765efe -s
git show fd4e73644 -s
```

## The judgement that was right on its own axis and wrong on the other

`dabbeaf73`'s re-examination of `BACKBONE_LAYER` is not a mistake in the
usual sense — it is a **correct** answer to the question it asked
(*does the audit's via union still work with the backbone on F.Cu?* — yes)
and it never asked the other question that mattered (*is F.Cu, independent
of audit correctness, too congested to route the backbone on?*). F.Cu
carried 652 routed segments and a 27,499 mm² HV keepout at the time; routing
an 87-edge minimum-spanning-tree ground backbone through that congestion
fail-closed 83 of the 87 edges. This is catalogued as a variant of the
"checks that cannot fail" pattern in
`docs/solutions/architecture-patterns/checks-that-cannot-fail-catalogue-2026-08-20.md`
— a check that reasons correctly about its own stated scope and is silent
about a cost outside that scope.

## The connectivity chain, measured at each step

| Step | `unconnected_items` | What changed |
|---|---:|---|
| Baseline (origin/main) | **339** | The same field PR #1390 (`fix/drc-parser-unconnected-items`) made *visible* in kicad-cli's output — this document drives the number down; that PR made it readable. Same board, same field, not a coincidence. |
| After `a71765efe` (gnd backbone → In1.Cu) | **304** | In1.Cu segments 0 → 294 |
| After `fd4e73644` (power islands → In2.Cu) | **282** | In2.Cu segments 0 → 227; F.Cu 652 → 578 → 485 |
| After `bc3a19b06` (per-pairing compliant placement, routed) | **251** | −31 from re-placement under the per-pairing creepage figures |

```
git show a71765efe   # In1.Cu 0->294, unconnected 339->304
git show fd4e73644   # In2.Cu 0->227, unconnected 304->282
git show bc3a19b06 -s
```

## Why 63 nets stayed at zero copper before the backbone fix — mechanism A

`6a6718a21` (`analysis/mechanism-a-zero-copper`) root-causes 50 of the 63
zero-copper nets: **187 pad pairs on the committed placement are already
closer than their required creepage, across 74 nets (44 of them in this
zero-copper set)**. The mechanism: a net whose pad sits inside another net's
required-creepage halo cannot route without violating that halo, so the
router correctly declines to route it — the failure is upstream, in
placement, not in the router. Also measured: 182 of 498 own-layer pad cells
are freed and then re-blocked by the halo mechanism (36.5%).

```
git show 6a6718a21 -s
```

## Rip-up and net-ordering do not substitute for the placement fix

Two mechanisms that might, in principle, work around a congested-backbone
placement without re-placing anything were checked and ruled out
(`4ea597f2d`, `agent/ripup-production-path`):

- **Rip-up does not exist on the production router path.** Five full
  production routes, fully instrumented: `_unmark_route_blocked` called
  **0 times**, 0 of 105 nets attempted twice. Even in the mechanism's most
  favorable theoretical framing, it is worth **at most 4 nets / 17 edges**
  (realistically 3/14) — nowhere near the 83-edge gap the backbone
  workaround caused.
- **Net ordering is not a substitute.** Both tested permutations were
  net-negative: fully-connected count moved 79 → 74 and 79 → 75 respectively
  — worse, not better, than the baseline ordering.

```
git show 4ea597f2d -s
```

## A corroborating find on the same branch

`bc3a19b06` (routing the per-pairing placement) independently reproduces a
defect catalogued in the companion "checks that cannot fail" document:
`check_placement_roundtrip`'s only production caller (`cli/__init__.py:760`)
passes the `normalize=True` coordinate frame while the function's own
docstring assumes file coordinates — displacing all 689 pad comparisons by
`board.origin` = (8, 20) mm. Reported there, not fixed in either branch.

## What remains open

- **251 `unconnected_items` is still not zero.** The chain in this document
  reduces the number from 339 to 251; it does not close it.
- **The routed per-pairing placement is not landable as-is, independent of
  T1/T2.** `bc3a19b06`'s own measurement: `hole_clearance` +24 and
  `drill_out_of_range` +14 are placement-caused, because the CP-SAT model
  constrains inter-component separation and creepage but not hole-to-hole
  spacing or drill-to-edge.
- **Creepage at the old 12.6 mm scalar does not improve from routing this
  placement** (106 → 108, inside documented flicker) — routed copper
  generates its own creepage violations independent of the static pad-pair
  gain.
- **23 of the remaining 36 zero-copper nets still have a pad inside a
  foreign creepage halo** — mechanism A is reduced by this session's work,
  not eliminated.
- None of `fix/gnd-plane-backbone-on-in1cu`, `fix/power-islands-backbone-on-in2cu`,
  `agent/per-pairing-placement-route`, or `agent/ripup-production-path` is
  merged to main as of this writing.

## Related

- `docs/solutions/architecture-patterns/checks-that-cannot-fail-catalogue-2026-08-20.md` — the `check_placement_roundtrip` off-by-origin defect this branch independently reproduced, and the framing of `dabbeaf73`'s judgement as a variant of the same pattern.
- `docs/solutions/architecture-patterns/isolation-barrier-single-scalar-vs-per-pairing-2026-08-20.md` — the per-pairing creepage figures this placement was re-solved against.
- Branches: `fix/gnd-plane-backbone-on-in1cu` (`a71765efe`), `fix/power-islands-backbone-on-in2cu` (`fd4e73644`), `agent/per-pairing-placement-route` (`bc3a19b06`, `30edd0a93`), `agent/ripup-production-path` (`4ea597f2d`), `analysis/mechanism-a-zero-copper` (`6a6718a21`).
- PR #1390 (`fix/drc-parser-unconnected-items`) — makes the `unconnected_items` field this document tracks actually visible; see the companion catalogue document, row 1.

## Verification notes

All figures above were checked twice: once by a dedicated verification pass
(re-run against every cited commit with `git show`, read-only, no branch
checked out), and a second time via a correction relayed by the task
coordinator from an independent peer verification. Both passes agree
exactly, including the sharper framing of `dabbeaf73`'s decision (a
deliberate, correct-on-its-axis judgement, not an oversight) and the
three-step 339→304→282→251 chain. No figure in this document failed to
reproduce.
