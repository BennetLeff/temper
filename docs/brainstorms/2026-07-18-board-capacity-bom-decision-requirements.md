# Board Capacity vs. BOM: A Decision Is Required Before "Literal-Zero DRC" Is Achievable

**Date:** 2026-07-18
**Status:** Requirements — decision needed, not yet agreed
**Scope tier:** Deep — hardware/mechanical decision with software follow-on

## Problem

`pcb/temper.kicad_pcb` (149 components, 100mm x 150mm) cannot physically
reach zero courtyard-overlap DRC violations at its current size with its
current BOM. This is not a placement-algorithm limitation — it's a raw
area shortfall, confirmed by direct measurement, not inferred from
solver behavior. No further placement-software work can close this gap;
a real engineering decision about board size or BOM composition is
required first.

This blocks the `docs/plans/2026-07-10-001-feat-finish-the-board-plan.md`
goal of "100% Routed, Literal-Zero DRC/ERC." That plan's own scope
boundaries explicitly rule out "No constraint relaxation to buy
completion" and "No footprint rebuild / real-board migration" (lines
33, 35) — i.e. its premise is that literal-zero DRC is reachable within
the *unchanged* board/BOM. That premise does not hold for the
courtyard-overlap category. Either the plan's scope boundary needs to be
revisited, or one of the options below needs to be chosen and executed
before that plan (or a routing-completion successor to it) can honestly
target literal-zero courtyard DRC.

## Existing state (verified 2026-07-18)

- Real board size, read directly from the `Edge.Cuts` polygon in
  `pcb/temper.kicad_pcb`: exactly 100mm x 150mm = 15,000 mm^2.
- Usable placement area after the pipeline's 5mm edge margin:
  (100-10) x (150-10) = 12,600 mm^2.
- Total component courtyard area across all 149 components: **13,670.8
  mm^2 — 108.5% of usable area**, before any allowance for real-world
  packing inefficiency (irregular rectangle/circle shapes never tile at
  100% efficiency; only identical squares do).
- At realistic packing efficiencies for this component mix (50-80%,
  generously), the board would need **136%-217% of its current usable
  area** to fit the BOM with zero overlap — i.e. the board would need to
  be roughly **1.4x to 2.2x larger** (candidate range: ~120x170mm to
  ~150x220mm), or the footprint area would need to shrink by a
  comparable factor.
- The 8 largest components account for **57.5% of total courtyard area**
  (7,860.1 of 13,670.8 mm^2) despite being ~5% of the component count:

  | Ref | Courtyard area (mm^2) | Likely role |
  |---|---|---|
  | L1 | 1428.0 | largest inductor |
  | PS1 | 1196.6 | power supply module |
  | C2 | 989.4 | bulk capacitor |
  | C3 | 989.4 | bulk capacitor |
  | C4 | 989.4 | bulk capacitor (35mm radial can) |
  | C5 | 989.4 | bulk capacitor |
  | K1 | 716.8 | relay/contactor |
  | U22 | 561.2 | large IC/module |

- Confirmed this is not a software bug: both the courtyard-collision
  *detector* (a Shapely STRtree indexing bug) and the courtyard
  *geometry extraction* (was silently falling back to a wrong
  pad-bounding-box approximation for 142/149 footprints) were found and
  fixed this session. With both fixed, the resolution loop still
  oscillates between ~26-48 unresolved pairs regardless of iteration
  budget (10x more iterations only moved the number from 43 to 31, with
  no downward trend) — the signature of an unsatisfiable constraint, not
  slow convergence.
- Full analysis, including the iteration-budget experiment, in
  `docs/solutions/architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md`.
- Real kicad-cli DRC on the current board confirms this is not
  theoretical: 27-29 `courtyards_overlap` and 16-18
  `pth_inside_courtyard` errors persist after both software fixes
  (`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`).

## Options

No option is pre-selected — this section lays out the fork in the road
for a human decision, not a recommendation.

| Option | What it means | Technical feasibility | Cost / schedule | Risk |
|---|---|---|---|---|
| **A. Enlarge the board** | Grow board outline to roughly 1.4x-2.2x current usable area (e.g. ~120x170mm to ~150x220mm) | High — removes the constraint entirely, placement software already works once area is sufficient | Re-spins mechanical enclosure/chassis fit, glass-top sizing (MCH-03: Glass Load 20kg gate in `docs/STRATEGY.md`), possibly cost per unit (larger PCB) | Enclosure/mechanical redesign is outside the placer/router's control; could cascade into industrial-design rework not scoped here |
| **B. Shrink/relocate the BOM's largest components** | Swap L1, PS1, C2-C5, K1, U22 (57.5% of area) for smaller-package alternatives or re-derive their electrical requirements | Medium — depends on whether smaller packages exist that meet the electrical spec (inductance/current rating for L1, capacitance/ripple-current for C2-C5, contact rating for K1, thermal/power for PS1); some of these (bulk caps, inductor) are physically size-constrained by the electrical requirement itself, not just package choice | Requires real component sourcing/electrical-engineering review per part, not a placement decision; could be fast (drop-in smaller package) or slow (re-derive circuit) per component | Undersizing any of these (esp. bulk DC-link caps, the commutation inductor) risks the EFF/PWR/thermal performance gates in `docs/STRATEGY.md`, not just DRC |
| **C. Accept some overlaps as reviewed-safe** | Formally document specific courtyard "overlaps" as non-physical conflicts (common in dense power electronics where courtyard margin is deliberately conservative) after human review of each flagged pair | High for the software side (just an exception list); zero for the physics unless overlaps are individually verified truly non-physical | Cheapest option if genuinely applicable — no redesign — but requires a real engineer to review 27-29 courtyard pairs + 16-18 PTH pairs one at a time | If the courtyard margin exists for a real reason (creepage, thermal, mechanical clearance for taller components), rubber-stamping overlaps could mask a genuine manufacturing or safety defect; this is the option most likely to be *wrong* if done carelessly |
| **D. Some combination of A/B/C** | E.g. modest board growth (1.2x) + relocating the 2-3 worst offenders + accepting a handful of reviewed marginal overlaps | Not yet analyzed — no numbers computed for a blended scenario | Unknown — needs its own area/cost tradeoff pass | Splits risk across three unknowns instead of concentrating it |

## Requirements

Whichever option is chosen:

### R1 — Decision is traceable and falsifiable
The chosen option (or blend) must be recorded with the specific
numbers it targets (new board dimensions, specific component
substitutions with new package courtyard areas, or the specific list of
accepted-overlap pairs with written justification per pair) — not a
vague "we'll make it fit."

### R2 — Re-verify area sufficiency before declaring done
After the change, re-run the same area calculation this brainstorm is
based on (`docs/solutions/architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md`'s
method) against the new board size and/or BOM to confirm the shortfall
is actually closed — not just "looks bigger now."

### R3 — Option-specific sub-requirements

- **If A (enlarge board):** confirm new dimensions against mechanical
  constraints (enclosure, glass-top, MCH-03 20kg load gate) before
  committing to exact numbers — this is not solely a placer decision.
- **If B (shrink BOM):** each substituted component must be
  re-verified against its original electrical requirement (inductance,
  capacitance/ripple current, contact rating, thermal dissipation) by
  someone with circuit-design authority, not inferred from courtyard
  area alone.
- **If C (accept overlaps):** each accepted pair needs a written
  one-line justification (e.g. "courtyard margin conservative for tall
  connector J1, no physical clearance conflict with adjacent low-profile
  part") reviewable independently of this brainstorm, and the accepted
  list must be encoded somewhere `CourtyardCheckStage`/the DRC gate can
  read (an explicit allowlist, not a threshold fudge) so future drift is
  caught.

## Success criteria

1. A specific option (or blend) is chosen and recorded with concrete
   numbers (board dimensions, or exact component substitutions, or an
   exact accepted-overlap list).
2. Re-running the area-sufficiency calculation against the chosen
   change confirms the 108.5%+ shortfall is closed (option A/B) or that
   every remaining courtyard flag is on the explicit accepted list
   (option C).
3. `docs/plans/2026-07-10-001-feat-finish-the-board-plan.md`'s scope
   boundary is either satisfied as originally written (options B/C, no
   board/BOM change beyond documented exceptions) or explicitly amended
   to acknowledge the board/BOM change (option A/D) before that plan (or
   its successor) claims literal-zero courtyard DRC.

## Scope boundaries

**In scope:** deciding between board resize, BOM substitution, or
reviewed-overlap acceptance (or a blend); specifying the concrete
numbers/list for the chosen option; confirming re-verification method.

**Deferred:**
- Actually executing the mechanical enclosure redesign (option A) —
  this brainstorm only decides *whether* to grow the board, not the
  enclosure engineering itself.
- Actually re-deriving circuit requirements for substituted components
  (option B) — this brainstorm identifies *which* components are the
  highest-leverage targets, not their replacement part numbers.

**Outside scope (separate initiatives):**
- The routing-completion work (`docs/plans/2026-07-10-001` and any
  successor) — depends on this decision but is not part of it.
- The single-layer-routing DRC-quality gap
  (`docs/brainstorms/2026-07-08-single-layer-route-requirements.md`) —
  an independent, non-courtyard DRC problem.
- Any change to the placement/routing software itself — this decision
  concerns the board/BOM, not the toolchain, which was confirmed
  correct as of the two bug fixes cited above.

## Open questions for planning

1. **Mechanical headroom for option A.** Is there known slack in the
   enclosure/glass-top design for a larger PCB, or is 100x150mm already
   a hard external constraint? This brainstorm has no visibility into
   mechanical/industrial-design status.
2. **Which of the 8 largest components are electrically size-flexible.**
   L1 (inductor) and the bulk caps (C2-C5) are plausibly
   size-constrained by their electrical role (inductance/ESR,
   capacitance/ripple current) rather than pure package choice — needs
   circuit-design input, not placement analysis, to know how much
   smaller they could realistically go.
3. **Whether any of the 27-29 courtyard-overlap / 16-18
   pth_inside_courtyard pairs are genuinely non-physical.** No one has
   yet reviewed the specific flagged pairs individually — option C is
   currently a hypothesis, not a verified path. A first useful step
   regardless of final decision: dump the specific pairs (available via
   `kicad-cli pcb drc` raw JSON per
   `docs/solutions/logic-errors/drc-api-wrapper-components-and-location-always-empty.md`)
   and have someone with PCB layout authority visually inspect a sample.
4. **Cost/schedule delta between A and B.** Not estimated here — needs
   real component sourcing (B) vs. mechanical/enclosure (A) input to
   compare.

## Evidence

- `docs/solutions/architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md`
  — full area calculation, iteration-budget experiment proving this is
  not a convergence issue, top-8-component breakdown.
- `docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`
  — the sibling investigation establishing both software bugs (STRtree
  indexing, courtyard geometry extraction) were fixed and are not the
  cause of the remaining gap.
- `docs/plans/2026-07-10-001-feat-finish-the-board-plan.md` — the
  "Finish the Board" plan whose scope boundary this decision directly
  affects (lines 33, 35: no constraint relaxation, no footprint
  rebuild/real-board migration).
- `docs/STRATEGY.md` — MCH-03 (Glass Load 20kg) and other mechanical
  gates relevant to option A; EFF-01/02, PWR-01/02 performance gates
  relevant to option B's electrical-sizing risk.
