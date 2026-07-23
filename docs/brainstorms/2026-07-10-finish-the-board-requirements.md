# Finish the Board — 100% Routed, Literal-Zero DRC/ERC — Requirements

**Date:** 2026-07-10
**Status:** Requirements — ready for planning
**Backfilled:** 2026-07-22 — this requirements doc was never committed at the time its plan (`docs/plans/2026-07-10-001`, commit `4698ce57`) was authored; it is reconstructed here from the plan's own Requirements/Scope sections and the contemporaneous handoff (`docs/handoffs/2026-07-11-finish-the-board-agent-brief.md`) so the plan's `origin:` link resolves. The investigation trail those sources preserve is the closest available record of what actually drove the work; the 2026-07-18 board-routing-completion brainstorm explicitly noted this file's absence and reconstructed the same context ("effectively reconstructs that missing context rather than extending a file that was never actually committed").

## Problem

The temper induction-cooker board (`power_pcb_dataset/corpus/temper/temper.kicad_pcb`) had never been routed to completion. The CP-SAT placer and `router_v6` had never run end-to-end together — every routing number in the project's arc (87.5%, 83.3%, the "Round 4" coexistence proof, per-net isolation test) was measured on the board's **original positions**, never on a CP-SAT placement. Three nets (`SPI_MOSI`, `SPI_CLK`, `I_SENSE`) were unrouted on the original layout, classifyable as an ordering/displacement problem (not a placement-topology failure) per Round 4 evidence showing all six critical nets coexist simultaneously.

The board needs to be taken to **100% routed** and **literal-zero DRC/ERC**, achieved entirely within the proven hard-constraint set, with **no constraint relaxation or resource padding** to buy the number. A "100% / zero" bought by weakening the problem is explicitly a false result.

## Verified current state (at the time)

- **Three unrouted signal nets** on the original-placement board: `SPI_MOSI` (3 pins), `SPI_CLK` (2 pins), `I_SENSE` (2 pins). Each individually routable in isolation; Round 4 of the routing log proves `GATE_H`, `GATE_L`, `PWM_H`, `SPI_CLK`, `SPI_MOSI`, `I_SENSE` all routed simultaneously — slack confirmed, not contention.
- **`V6RouterAdapter._build_temp_pcb` is broken**: present in source but not registered as a class method (suspected merge artifact); `rrr_route_all_nets` calls it and raises `AttributeError`. This blocks exposing any net-ordering hook. (See the handoff for later doubt on whether the ordering conclusion was correct — separately, the placement step was found to be broken, so the ordering fix in `pipeline.py:466–476` was applied against original positions, not CP-SAT placements.)
- **Existing ordering code was a no-op**: `router_v6/adapter.py:288–298` sort ran after `pipeline.run()` and `net_order` was never passed into the router; the live sort was in `pipeline.py:466–476` at Stage 0. A third `net_ordering.py` ordering path existed and needed reconciliation against the others.
- **No net-ordering module existed**: ordering was implicit in `rrr_route_all_nets` iteration. The plan could fix this with either a new `net_ordering.py` or an inline sort in the adapter.
- **22 placement-relevant intra-component clearance violations** on U_MCU/J_USB fine-pitch pads: the constraint rule was looser than the QFN/connector pad pitch — a rule-accuracy gap, not a relaxation.
- **33 `lib_footprint_issues` in DRC**: the headless `kicad-cli` DRC lacked the standard KiCad footprint library table (`Capacitor_SMD`, `Package_SO`, `MountingHole`, `Resistor_SMD`, `Package_TO_SOT_SMD`, …); the measuring instrument was misconfigured, not the board.
- **ERC had not been run** against the routed board.
- **History of false zeros** in this codebase (`weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08`, `baseline-extractor-four-silent-fail-metrics-2026-07-01`, `two-tier-acceptance-gate-unsat-surfacing-2026-07-05`): completion/zero counts were unsafe to trust absent an anti-false-zero guard.

## Requirements

- **R1** — Per-net routing diagnosis: confirm each unrouted net is individually routable (legal path exists) and that all critical nets coexist in at least one routing round, to classify the failure as ordering/displacement rather than placement-topology or contention.
- **R2** — Close router-capability failures via an ordering heuristic: route signal nets after power/HV nets so they aren't displaced by later rounds.
- **R3** — Close placement-topology failures: declared **off the table** when zero nets failed the legal-path-exists test.
- **R4** — Netclass calibration: assign fine-pitch nets (`SPI_*`, `USB_*`, `PWM_*`, `TEMP_SENSE` on U_MCU/J_USB) to a `FinePitch` netclass (0.1 mm clearance) so the rule matches the geometry — a rule-accuracy fix, not a relaxation.
- **R5** — Configure the DRC gate's footprint library table so `lib_footprint_issues` resolve and the gate measures the board, not the env.
- **R6** — ERC to zero on the routed board.
- **R7** — Anti-false-zero guard: "100% routed" and "0 DRC/ERC" count only when measured within the unchanged constraint set against a properly-configured gate, with every unrouted-net closure traceable to the R1 diagnosis. A relax, a padding, a misconfigured gate, or an unmeasured-aborted run is a **failure mode**, not a pass.

## Scope Boundaries

- No constraint relaxation to buy completion. Safety/regulatory hard floors (creepage, the 3.0 mm IEC 60335-1 floor, edge clearance, netclass SEPARATED) are inviolable.
- No adding layers to dodge diagnosis. The 4th layer is used for a net only when diagnosis proves that net genuinely needs it.
- No footprint rebuild / real-board migration.
- No new sophisticated router before a simpler one is shown to fall short. The ordering heuristic is the simple algorithm; escalate to negotiated-congestion only on evidence.
- Negotiated-congestion / PathFinder-style rip-up-reroute and 4th-layer routing are explicitly deferred follow-ups, escalated only if the ordering heuristic demonstrably falls short.

## Non-negotiable guards (the project's hard-won discipline)

1. **Measure the territory, not the map**: verify outcomes by actual `kicad-cli` DRC on the actual generated board, not by reading code or trusting a solver's "OPTIMAL".
2. **Never relax a hard safety/regulatory constraint to buy completion**.
3. **Fail-closed measurement**: a DRC/route run that can't complete (tool error, board won't load) is UNMEASURED, not "zero".
4. **A fix that exists in code is not a fix that works**: confirm effect by measurement at the point in the pipeline where it can actually take effect (the phantom adapter sort is the cautionary example — it was present in source but a no-op at runtime).

## Success Metrics

- **100% of nets routed** on the temper board, within the unchanged constraint set.
- **Literal-zero DRC and ERC**, measured against a properly-configured `kicad-cli` gate.
- Every unrouted-net closure traceable to the R1 diagnosis (ordering/displacement — no constraint relaxation, no resource padding, no added layers).
- The R7 anti-false-zero guard passes: constraint set matches the baseline, gate is properly configured, and zero was not bought by weakening the problem.

## Sources & References

- Plan: [`docs/plans/2026-07-10-001-feat-finish-the-board-plan.md`](../plans/2026-07-10-001-feat-finish-the-board-plan.md)
- Handoff (contemporary record): [`docs/handoffs/2026-07-11-finish-the-board-agent-brief.md`](../handoffs/2026-07-11-finish-the-board-agent-brief.md)
- Later continuation: [`docs/brainstorms/2026-07-18-board-routing-completion-requirements.md`](2026-07-18-board-routing-completion-requirements.md) — the 07-18 brainstorm explicitly noted this doc's absence and reconstructed the same context.
- Key learnings:
  - `docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md` (the 121→0 false-zero catch)
  - `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md` (CLEAN/VIOLATIONS/UNMEASURED)
  - `docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md` (a tolerance that swallows zero is a false-pass machine)