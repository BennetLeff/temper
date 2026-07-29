---
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
title: Correct the Pad Geometry Model - Plan
date: 2026-07-28
status: active
---

# Correct the Pad Geometry Model - Plan

## Goal Capsule

**Objective.** Replace the `max(width, height) / 2` bounding-circle pad model
with shape-correct geometry everywhere it is used — the isolation safety gate,
the CP-SAT barrier constraint, and the shared router obstacle model — then
re-derive the conclusions that were computed on the old model.

**Product authority.** The pad model is a correctness primitive, not a tuning
knob. Two independent consumers depend on it never under-reporting copper
extent: a safety gate on a mains-connected design, and the router's obstacle
map. It currently under-reports for 434 of the 519 pads on the production
board.

**Open blockers.** None to start. The routing-golden churn (R7) is the main
risk and is a known cost, not an unknown.

## Product Contract

### Problem

`radius = max(width, height) / 2` does not describe any KiCad pad shape except
a circle. It is simultaneously:

- **too small at the corners** — a circle of that radius never contains a
  rectangle. Measured worst case among true `rect` pads on
  `pcb/temper.kicad_pcb`: `PS1` pad 1, a 3×3mm pad whose corners lie
  **0.621mm outside** the model circle.

  CORRECTION (2026-07-28, after this plan was handed off): an earlier draft
  cited `R30` pad 1 as an 8×8mm pad with 1.657mm of overshoot. That is wrong.
  `R30` pad 1 is `shape='circle'`, and for a circle pad `max(w,h)/2` is exact —
  it is the one shape the current model gets right. The error came from ranking
  pads by `max(size)` without filtering on the shape field, which is the same
  read-the-number-without-checking-what-it-describes mistake this plan exists to
  fix. The finding itself is unaffected: the model still under-reports for every
  `rect` and `roundrect` pad, which is 441 of 519 on this board. Only the
  headline magnitude and the example were wrong.
- **too large on the short axis** — a 9×4.8mm pad is modelled with a 4.5mm
  radius in the direction where its true half-extent is 2.4mm.

The code asserts the opposite of the first property. `check_isolation_keepout.py`
states a safety intrusion check "must never UNDER-approximate a pad's physical
extent" and then uses a formula that always does, for every non-circular pad.

Both error directions have already produced wrong answers:

| consumer | observed consequence |
|---|---|
| `check_isolation_keepout.py` | T1 reported 7.023mm vs a true 9.100mm; K1 reported 5.425mm vs a true 8.000mm. Both are **false FAILs**. |
| `isolation_barrier.py` (CP-SAT) | the `INFEASIBLE` barrier verdict, and the 7-part BOM blocker list derived from it, were computed on the same wrong model. |
| router obstacle model | under-approximation permits routing through pad copper; over-approximation wastes routing channel. Not yet quantified. |

### Users

The placer/router pipeline and the CI safety gates are the direct consumers.
The human consequence is BOM spend: the current blocker list names 7 isolator
components for re-sourcing, and at least 2 of those (T1, K1) appear to be
measurement artifacts.

### Requirements

- **R1** — Pad extent is computed from the pad's declared KiCad shape.
  `circle`, `oval`, `rect`, and `roundrect` must each be represented by their
  own geometry. A single shape-agnostic approximation is not acceptable.
- **R2** — The model must never under-report a pad's physical extent, in any
  direction, for any shape. Where an exact representation is impractical, the
  approximation must err outward.
- **R3** — Pad rotation must be honoured. Every pad on the current board has
  rotation 0, so this is untested in practice and must not be assumed away.
- **R4** — A single shared implementation backs every consumer. The formula is
  currently duplicated across `check_isolation_keepout.py`,
  `isolation_barrier.py`, `obstacle_map.py`, `escape_via_generator.py`, and
  `core/pin_geometry.py`'s `pin_world_radius()`; duplicates are how the gate and
  the CP-SAT constraint drifted into agreeing on a wrong answer.
- **R5** — The isolation gate's verdict is re-derived on the corrected model,
  and the per-isolator separation table is republished. Any component that
  changes verdict is called out explicitly.
- **R6** — The CP-SAT barrier feasibility is re-run on the corrected model. If
  it remains `INFEASIBLE`, the blocker list is restated with the components
  that genuinely block it. If it becomes feasible, that is a materially
  different finding and must be reported as such rather than absorbed.
- **R7** — Routing outputs are expected to change. Every golden, baseline, or
  ceiling that moves must be identified, re-recorded deliberately, and the
  re-recording justified — not silently accepted because CI went green.

### Non-goals

- Re-sourcing any component. This plan produces a corrected blocker list; the
  purchasing decision is separate.
- Changing the 8.0mm reinforced-creepage requirement, the corridor model, or
  `elec/domain_manifest.yaml`'s domain classification.
- Placing the `MAINS_SELV_ISOLATION_BARRIER` keepout zone.
- Improving router performance. Shape-correct geometry may be slower; that is
  acceptable unless it breaks a stated timing baseline, which R7 covers.

### Success criteria

- No consumer computes a pad extent smaller than the pad's true extent, for any
  shape, at any rotation, demonstrated by test.
- The isolation gate's per-isolator table is reproduced from the corrected
  model, with every verdict change from the current table named.
- The CP-SAT barrier verdict is restated on the corrected model.
- The full test suite passes, and every changed golden/baseline has a recorded
  reason.

### Key decisions

- **Scope is all three consumers, not just the safety gate.**
  `session-settled: user chose A+B+C after being shown that C (the shared
  router model, 8+ importers) carries high blast radius and would move every
  routed board.` The alternative — fixing only the gate — was rejected because
  it would leave the `INFEASIBLE` verdict standing on the old model.
- **A larger circle is not the fix.** Substituting the half-diagonal makes the
  model properly conservative but *more* wrong for the gate: T1 measures
  5.977mm under it, versus a true 9.100mm. Correctness requires shape-aware
  geometry, not a re-tuned radius.
- **Direction of conservatism is uniform.** Every consumer wants "at least the
  true extent" — the gate to avoid a false PASS on a safety check, the router
  to avoid routing through copper. There is no consumer that wants the
  approximation to err inward, so one shared implementation can serve all.

### Assumptions

- `shapely` is already a first-party dependency (`shapely>=2.1.2`) and is
  suitable for exact pad geometry. Unverified: whether the router's hot paths
  can afford polygon operations per pad, or whether they need a rasterised or
  bounded form.
- KiCad `custom`-shape pads do not appear on the current board. Unverified for
  boards outside `pcb/temper.kicad_pcb`.

### Outstanding questions

- Does the router need a fast conservative bound (e.g. an oriented bounding
  box) rather than exact polygons, and if so, does that bound satisfy R2?
- Does correcting the model change `check_copper_net_consistency.py`,
  `creepage_check.py`, or `clearance_check.py` verdicts? They were not surveyed
  in this brainstorm.

## How This Work Fits Together

The immediate trigger was a false FAIL on T1 in the isolation gate, found while
validating whether the mains↔SELV barrier is achievable. That investigation had
concluded the barrier is `INFEASIBLE` and named 7 isolator components for
re-sourcing. Because both the gate and the CP-SAT constraint use the same wrong
pad model, that conclusion is not yet trustworthy — which is what makes this a
prerequisite for the BOM decision rather than a cleanup task.

Related, not in scope: placing the barrier keepout zone, and the separate
`2026-07-28-001` provable-safety place-and-route plan.
