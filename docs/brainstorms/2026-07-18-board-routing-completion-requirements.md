# Board Routing Completion — Resume Stalled Work, Then Escalate to Multi-Layer

**Date:** 2026-07-18
**Status:** Requirements — ready for planning
**Scope tier:** Deep — continuation of stalled routing-completion work, with a new evidence-based escalation phase

## Problem

The temper production board has never been routed. `routed_nets: 0` in the
current baseline; only 124 escape vias exist and 269 pads remain
unconnected. This is not a new problem — a plan already exists to close it
(`docs/plans/2026-07-10-001-feat-finish-the-board-plan.md`, "Finish the
Board — 100% Routed, Literal-Zero DRC/ERC") — but that plan was never
carried to completion or even proven to have failed. Only one commit ever
touched the plan file (its creation, `4698ce57`); it has status `active`
with no follow-up. Meanwhile, this session independently found hard
evidence that the plan's underlying sequencing assumption (single-layer
F.Cu routing, chosen deliberately in an earlier brainstorm) is
insufficient to reach the plan's own "literal-zero DRC" target — a
material update the stalled plan never had the chance to absorb.

This brainstorm has two jobs: (1) determine whether to resume the
2026-07-10 plan as-is or re-scope it given what's changed since, and (2)
scope the multi-layer routing escalation that single-layer's real
violation counts now justify.

## Existing state (verified 2026-07-18)

- **Routing has not progressed.** `power_pcb_dataset/baselines/temper_production_baseline.yaml`:
  `routed_nets: 0`, `escape_vias: 124`, `connectivity_unconnected_pads: 269`.
  It is not known whether the `V6RouterAdapter._build_temp_pcb` repair
  the 2026-07-10 plan specifies was ever attempted — no commit history
  exists on that file evidencing it.
- **The 2026-07-10 plan's origin brainstorm does not exist in the repo.**
  The plan's frontmatter cites `origin: docs/brainstorms/2026-07-10-finish-the-board-requirements.md`,
  but that file is not present (`ls` confirms no match). This doc
  effectively reconstructs that missing context rather than extending a
  file that was never actually committed.
- **The 2026-07-10 plan's diagnosis (R1) claims completion**, not
  something this session re-verified: 3/3 unrouted nets (`SPI_MOSI`,
  `SPI_CLK`, `I_SENSE`) individually routable, and "Round 4" of a prior
  routing log shows all six critical nets (`GATE_H`, `GATE_L`, `PWM_H`,
  plus the three signal nets) coexisting — classified as an
  ordering/displacement problem, not a placement-topology failure (R3
  explicitly ruled off the table). The plan's fix: repair the broken
  `_build_temp_pcb` method binding (present in source, not registered as
  a class method — suspected merge artifact) and add a net-ordering
  heuristic (signal nets route after power/HV nets).
- **Single-layer routing was deliberately chosen first, on purpose.**
  `docs/brainstorms/2026-07-08-single-layer-route-requirements.md`:
  "Route 100% of nets on the placed temper board on a single layer
  (F.Cu). This proves the router functions end-to-end on this board
  before adding multi-layer complexity." Multi-layer routing was
  explicitly named and deferred as "W2" in that doc's Scope Boundaries.
- **Single-layer routing, now measured with real evidence, produces far
  more than zero DRC violations.** `docs/solutions/test-failures/regression-drc-tests-missing-zone-loop-wiring.md`
  documents `test_regression_drc.py::test_golden_board_routing_drc_regression`
  (run against `power_pcb_dataset/corpus/temper/temper.kicad_pcb`, a
  *different, smaller* golden-board corpus than the production board)
  measuring **261 DRC violations locally, 443 in CI** (KiCad-version
  dependent: kicad-cli 10.0.4 vs 8.0) against a target of exactly 0.
  Breakdown: `clearance` (61-144), `shorting_items` (48-88),
  `solder_mask_bridge` (79-99), `tracks_crossing` (72-108),
  `diff_pair_gap_out_of_range` (1-4), offset by `unconnected_items: -84`.
  The test's own captured error message already names the suspected
  cause: "single-layer F.Cu routing with all 24 nets on one layer may
  produce track-to-track clearance issues." This confirms the 2026-07-08
  brainstorm's sequencing was correct to test single-layer first — it
  was insufficient, exactly as a first-proof-of-concept step should be
  expected to reveal.
- **The routing-capable loop path is more trustworthy now than when the
  2026-07-10 plan was written.** This session found and fixed a real bug
  in `PlaceRouteLoop.run()`: it silently ignored a caller's custom
  `gates=` registry unless `all_gates=True` was also passed, contradicting
  its own constructor's documented contract
  (`docs/solutions/logic-errors/place-route-loop-run-ignores-constructor-gates-without-all-gates-flag.md`).
  Any routing attempt made through this path before 2026-07-18 may have
  silently run with fewer gates active than intended.
- **The golden-board corpus and the production board are different
  files.** `test_regression_drc.py`'s `BOARD_PATH` points at
  `power_pcb_dataset/corpus/temper/temper.kicad_pcb`; the actual
  production board is `pcb/temper.kicad_pcb`. CI's routing-quality signal
  does not directly measure the production board.

## Requirements

### R1 — Resume-or-reassess the stalled 2026-07-10 plan

Before writing new implementation work, determine the current state of
`V6RouterAdapter._build_temp_pcb` and the net-ordering heuristic:
confirm whether either was ever implemented (git history suggests no),
and if not, resume that plan's U1-U2 units (adapter repair, net
ordering, verify against `pcb/temper.kicad_pcb`) as Phase 1 of this
work — its diagnosis has not been shown to be wrong, only unexecuted.

### R2 — Re-run routing with the `PlaceRouteLoop.run()` gate-dispatch fix in place

Any routing attempt must use the current, fixed `loop.py` (post
2026-07-18) so results reflect the intended gate set, not a silently
narrower one. Do not trust any pre-2026-07-18 routing run's gate
coverage without re-verifying.

### R3 — Target the production board directly, not only the corpus copy

Extend or add a routing-quality measurement against `pcb/temper.kicad_pcb`
itself (not solely `power_pcb_dataset/corpus/temper/temper.kicad_pcb`).
Decide whether `test_regression_drc.py` should be repointed, duplicated,
or supplemented — the corpus board's 261-443 violations are a proxy, not
a direct measurement of the board this project ships.

### R4 — Scope the multi-layer routing escalation (formerly deferred "W2")

Now justified by measured evidence rather than assumption. Requirements
for this phase:
- Determine which violation categories multi-layer routing would
  plausibly resolve (`clearance`, `tracks_crossing`, `solder_mask_bridge`
  look like direct single-layer-crowding symptoms; `shorting_items` and
  `diff_pair_gap_out_of_range` need individual diagnosis — a layer change
  alone may not fix a genuine net-adjacency short).
- Decide which additional layer(s) to route on and what stackup
  constraints apply (the board's existing layer count and stackup are
  assumed fixed inputs to this brainstorm, not something it re-opens).
- Preserve the same anti-false-zero discipline the 2026-07-10 plan
  specified (R7 in that plan): completion/zero counts only against a
  properly-configured gate, within a constraint set that wasn't relaxed
  to buy the number.

### R5 — Anti-false-zero guard, carried forward

Re-adopt the 2026-07-10 plan's R7 intent explicitly for this doc's scope:
any "100% routed" or "0 DRC" claim must be measured against a
properly-configured `kicad-cli` gate, on the unchanged (or explicitly
and visibly changed) constraint set, with every closure traceable to a
diagnosis — not a relaxed rule or a misconfigured measurement instrument.

## Success criteria

1. It is known, with evidence, whether `_build_temp_pcb` and the
   net-ordering heuristic were ever implemented — no more silent
   uncertainty about the 2026-07-10 plan's execution state.
2. `pcb/temper.kicad_pcb` reaches 100% net routing (or the remaining gap
   is diagnosed and classified, per the existing R1 method: legal-path-exists
   vs. genuine topology failure).
3. The routing-quality gate (whichever board it targets after R3) shows a
   measured, trending-toward-zero DRC violation count, with the
   multi-layer escalation's effect on each violation category documented,
   not assumed.
4. Any routing run's result is attributable to a known `PlaceRouteLoop`
   gate configuration (post the `all_gates`/`gates=` dispatch fix).

## Scope boundaries

**In scope:** resuming/re-verifying the 2026-07-10 plan's adapter and
ordering-heuristic work; re-running routing with the fixed loop dispatch;
scoping (not necessarily fully implementing) the multi-layer escalation;
deciding which board(s) the routing-quality CI gate should measure.

**Deferred:** full multi-layer implementation details (exact layer
assignment algorithm, via strategy) — this doc scopes the escalation's
requirements, a planning pass should design the mechanism.

**Outside scope:** the board-size/BOM capacity decision (separate sibling
brainstorm, `docs/brainstorms/2026-07-18-board-capacity-bom-decision-requirements.md`,
topic: whether `pcb/temper.kicad_pcb` needs to be resized or have its BOM
changed due to a courtyard-area-exceeding-board-area finding). Routing
work on the *current* board geometry may need to be redone if that
decision results in a resize — this is a real, acknowledged dependency,
not a blocker to scoping routing work now, since the two threads can
proceed in parallel until a resize decision (if any) actually lands.
Netclass calibration (R4) and DRC footprint-library-table configuration
(R5) from the 2026-07-10 plan are assumed still relevant but not
re-verified here — folding them into Phase 1 (R1 above) is a planning
decision, not re-litigated in this brainstorm.

## Open questions for planning

1. **Is the 2026-07-10 plan's diagnosis still accurate?** Its R1 table
   (3/3 signal nets individually routable, Round 4 six-net coexistence)
   was asserted, not re-verified this session. Planning should confirm
   this still holds before resuming the plan as-is.
2. **Which board does the routing-quality CI gate measure going
   forward?** Production board directly, golden corpus as a fast proxy,
   or both with an explicit relationship documented?
3. **What's the real fix for `shorting_items`?** This violation category
   (48-88 instances) is unlikely to be solved by adding a routing layer
   alone — may indicate a genuine netlist/placement issue needing its own
   diagnosis, separate from the layer-crowding hypothesis.
4. **Sequencing relative to the board-capacity brainstorm.** If that
   sibling doc's decision is "resize the board," does routing-completion
   work pause, or is there value in reaching 100%-routed-at-current-size
   first as a proof point before a resize?

## Evidence

- `power_pcb_dataset/baselines/temper_production_baseline.yaml` —
  `routed_nets: 0`, `escape_vias: 124`, `connectivity_unconnected_pads: 269`.
- `docs/plans/2026-07-10-001-feat-finish-the-board-plan.md` — stalled
  plan, single commit (`4698ce57`), status `active`, origin brainstorm
  missing from repo.
- `docs/brainstorms/2026-07-08-single-layer-route-requirements.md` —
  deliberate single-layer-first sequencing, multi-layer named and
  deferred as "W2".
- `docs/solutions/test-failures/regression-drc-tests-missing-zone-loop-wiring.md` —
  261 (local) / 443 (CI) routing-introduced DRC violations against a
  target of 0, measured on `power_pcb_dataset/corpus/temper/temper.kicad_pcb`.
- `docs/solutions/logic-errors/place-route-loop-run-ignores-constructor-gates-without-all-gates-flag.md` —
  `PlaceRouteLoop.run()` gate-dispatch bug, fixed 2026-07-18.
