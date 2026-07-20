---
date: 2026-07-20
topic: board-capacity-resolution-and-physical-sequencing
---

# Board Capacity Resolution & Physical-Board Sequencing

## Summary

Resolve #221 by enlarging the board outline to 1.30× (110×165mm), record that decision back onto the issue, and sequence the physical-board work that has been pending since 2026-07-15: execute the P0 schematic-fix chain (grounding → wiring → aux supply → sensing → EMI/surge → BOM verification) to a stable netlist first, then run placement and routing exactly once against the final outline and BOM.

---

## Problem Frame

`pcb/temper.kicad_pcb` is at 108.5% courtyard-area overfill (13,670.8mm² of components on a 12,600mm² board) — a genuine geometric infeasibility, not a placement bug. Issue #221 named three resolution paths (enlarge the board, shrink/relocate BOM, or accept a reviewed-overlap allowlist) but was closed on 2026-07-20 as "decision-support work complete" without any option actually being chosen — the closure gates on human sign-offs (mechanical/enclosure, circuit-design, or PCB-layout) that only a person can make.

This sits on top of a second stalled track: the entire P0 hardware-fix chain from the 2026-07-15 electrical-design audit (grounding/isolation, wiring bugs, aux supply, sensing front-ends, EMI/surge, BOM verification) is 100% `pending`, gated first on grounding (07-15-003). `docs/PRE_FAB_SIGN_OFF.md` — the document that ultimately gates fabrication — has zero checklist items completed. Meanwhile, this session just closed out the router/placement track (APC1, unconnected_items 149→0) against the *current* 100×150mm outline — work that a board resize will invalidate. Left undecided, both #221 and the P0 chain block any further real progress toward a fab-ready board, and the order in which they're tackled determines whether the placement/routing work gets done once or twice.

---

## Requirements

**Board capacity resolution**
- R1. The board outline shall be enlarged from 100×150mm to 110×165mm (1.30× scale).
- R2. The #221 decision shall be recorded back onto the GitHub issue (reopen-and-close, or an explicit closing comment) stating the chosen option (enlarge, 1.30×) and rationale, replacing its current "decision-support complete, unresolved" state.

**Physical-board execution sequencing**
- R3. The pending P0 hardware-fix chain (07-15-003 grounding/isolation → 004 wiring → 005 aux power → 006 sensing front-ends → 007 EMI/surge → 008 BOM verification) shall execute in its existing declared dependency order (003 first; 004–007 depend on 003; 008 depends on 003 and 005) to reach a stable netlist/BOM.
- R4. Placement (CP-SAT) and routing (router_v6/APC1) shall be re-run exactly once, against the 110×165mm outline and the post-P0-chain BOM/netlist — not before the P0 chain reaches a stable BOM.
- R5. Populating `docs/PRE_FAB_SIGN_OFF.md` is the downstream milestone this sequence feeds; it is not executed as part of this work.

---

## Acceptance Examples

- AE1. **Covers R3, R4.** Given the P0 schematic chain (07-15-003–008) has not yet reached a stable BOM, when someone considers re-running placement/routing on the new 110×165mm outline, then that re-run should wait — running it earlier risks a second re-route once BOM verification (008) changes components.

---

## Success Criteria

- #221 has a recorded, non-ambiguous decision (1.30×) instead of an unresolved closure; the board outline is dimensionally fab-feasible (no courtyard overfill even under pessimistic packing efficiency).
- The pending physical-board work has a clear, unblocked starting point and execution order, so the next session (or `ce-plan`) can begin at 07-15-003 without re-deriving sequencing.
- A downstream planner can take "apply 1.30× scale to the board outline, then re-run placer/router once the P0 chain lands" and "execute 07-15-003 through 008 in their existing dependency order" as concrete, unambiguous work items.

---

## Scope Boundaries

- Redesigning the individual P0 fixes (grounding architecture, wiring corrections, aux supply design, sensing front-ends, EMI/surge protection, BOM verification) — these remain their own already-written pending plan docs; this doc sequences their execution, it does not re-specify their content.
- Populating `docs/PRE_FAB_SIGN_OFF.md` — deferred; it is the milestone downstream of this sequence, not part of it.
- Software architecture refactors (#207/#206/#205 coupling issues) and pyo3 dependency cleanup — a separate, parallel track, explicitly out of scope here.
- Building a hardware-requirements traceability system to cover STRATEGY.md's gates (EFF/PWR/PID/OCP/OVP/THM/UVL/EMC/MCH) — `docs/traceability-registry.yaml` currently has zero entries for these; that gap is real but not addressed by this doc.

---

## Key Decisions

- **Scale factor: 1.30× over the issue's originally-framed 1.20×** — 1.20× is 73.1% overfill ratio at ideal packing but 104.4% (still infeasible) at a realistic 70% packing efficiency; 1.30× is the first scale that stays feasible (88.0%) even under that pessimistic assumption. Source: `docs/solutions/architecture-patterns/board-capacity-bom-decision-memo-2026-07-18.md`.
- **P0 schematic chain before the placement/routing re-run, not in parallel** — BOM verification (07-15-008) can change components; sequencing it before the single re-route pass avoids re-routing twice.
- **Enclosure treated as flexible** — no case/glass-top tooling is committed yet, so Option A (enlarge) is viable without a blocking mechanical constraint; this assumption should hold as the P0 chain and re-route proceed.

---

## Dependencies / Assumptions

- Assumes the existing pending plan docs (07-15-003 through 07-15-008) are still accurate as written — they predate this session by about a week and should be spot-checked for drift before execution starts.
- Assumes the router_v6/APC1 pipeline proven this session (149→0 unconnected on the current outline) generalizes to a resized board outline without pipeline changes, only a re-run.
- Assumes the eventual enclosure/mechanical design can accommodate 110×165mm without violating MCH-03 (20kg glass load) — not verified here, since the enclosure is still undesigned.

---

## Outstanding Questions

### Resolve Before Planning

- [Affects R2][User decision] Should #221 be reopened and re-closed with the decision recorded, or is a closing comment on the already-closed issue sufficient?

### Deferred to Planning

- [Affects R3][Needs research] Are the 07-15-003–008 pending plans still accurate given the ~1-week gap since they were written, or do they need a freshness check before execution starts?
- [Affects R4][Technical] Does resizing the board outline require any router_v6/CP-SAT configuration changes, or is it purely a change to the input outline?
