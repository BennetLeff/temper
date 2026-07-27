---
date: 2026-07-25
topic: router-drc-legal-completion
---

# DRC-Legal Completion: Making the Router's Success Metric Observe Manufacturability

## Summary

`completion_rate` reports whether the router **found a path**, not whether the
path can be **fabricated**. On the current board it reports 78.57% while the
routes it produced contain 499 `clearance` violations and 123 `shorting_items`.
A short is a fatal defect on a mains-connected appliance. This proposes adding a
DRC-legality term to the router's success metric so that no completion figure
can be quoted as progress while the output is unmanufacturable, and then driving
`shorting_items` to zero.

---

## Problem Frame

On 2026-07-25 the board received its first real `Edge.Cuts` outline
(`(20,20)-(172,254)`, 152 × 234 mm) after a placeholder had left 113 of 149
footprints outside the board. Routing against a real board for the first time
produced:

| Metric | Value |
|---|---|
| `completion_rate` | 0.7857 (66 of 84 attempted) |
| segments / vias / zones | 3,265 / 48 / 98 |
| unconnected items | 276 (from 326) |
| DRC violations | 1,464 |

Violation profile: **499 `clearance`**, 597 silkscreen (199 each of
`silk_edge_clearance` / `silk_overlap` / `silk_over_copper`), **123
`shorting_items`**, 85 `solder_mask_bridge`.

The headline number and the fabrication reality disagree, and nothing currently
forces them to agree. `completion_rate` is computed from pathfinding outcomes;
it has no term that observes whether the emitted copper is legal. That is the
same defect shape as `docs/METHODOLOGY.md` §7 — a metric structurally unable to
see the failure that matters — one level up from the outline bug.

This matters beyond metric hygiene. `docs/STRATEGY.md` records "24/24 routed"
and "72/95 routed" as figures that went stale and misled planning for weeks.
78.57% is on track to become the third unless it is qualified now.

---

## Requirements

- **R1.** `RoutingResult` exposes a DRC-legality term alongside
  `completion_rate` — at minimum `shorting_items`, `clearance` violations, and
  `unconnected_items` measured on the emitted board. A caller must not be able
  to read completion without also being able to read legality.

- **R2.** A net counts as **routed** only if its path is DRC-legal. Nets whose
  emitted copper shorts or violates clearance are reported in a distinct
  category — not silently included in the completion numerator. Per
  `METHODOLOGY.md` §5, fail closed: unmeasured legality is not legality.

- **R3.** `shorting_items` on the production board reaches **zero**. This is the
  hard gate; clearance violations are the softer follow-on. 123 shorts on a
  mains board is a fabrication blocker, not a quality metric.

- **R4.** A regression gate asserts `shorting_items` never rises, wired as a
  real workflow step **without** `continue-on-error` (the repo has 36 such
  steps; see `docs/plans/2026-07-25-002-refactor-baseline-burndown-plan.md`).

- **R5.** Silkscreen violations (597 of 1,464, 41%) are separated into their own
  severity tier so they stop burying electrical defects — `METHODOLOGY.md` §6.2.
  They are cosmetic and must not be fixed before R3.

- **R6.** The legality term is emitted as a **cost field**, not only a verdict,
  so it can steer the router rather than merely judge it — `METHODOLOGY.md`
  §6.3. It stays **subordinate to the threshold**: the pass/fail check is the
  validated artifact and the field need only be monotone with it.

---

## Success Criteria

- `shorting_items == 0` on `pcb/temper.kicad_pcb` after routing.
- Completion and legality are reported together, and completion counts only
  DRC-legal nets.
- The regression gate demonstrably fails when a short is reintroduced —
  proven by injection, not assumed (`METHODOLOGY.md` §5, construction axis).

---

## Scope Boundaries

**In scope:** the completion metric's definition, shorting-item elimination,
the legality regression gate, silkscreen severity tiering.

**Out of scope:**
- Clearance violations beyond what falls out of fixing shorts — separate track.
- Placement changes. The current placement is an input to this work.
- The 18 nets that fail to route at all. Different problem: this brainstorm is
  about the 66 that *do* route producing illegal copper.
- Enclosure/outline tightening — rungs 3–4 of `METHODOLOGY.md` §10.

---

## Key Decisions

- **Legality gates completion, rather than being reported beside it.** A
  weaker "report both, let the reader decide" design is what allowed 24/24 and
  72/95 to propagate. The numerator itself must be honest.
- **Shorts before clearance.** Shorts are fatal; clearance violations are
  graded. Fixing 499 clearance violations first would burn the budget without
  removing the fabrication blocker.
- **Silkscreen is not fixed here.** 597 cosmetic violations are noise; tiering
  them is enough.

---

## Dependencies / Assumptions

- Assumes the rung-1 outline is stable for the duration of this work. Rung-3
  tightening will re-open these numbers and that is expected.
- Assumes the schematic/netlist is fixed. It is unvalidated
  (`STRATEGY.md`), but a well-formed netlist exercises the router identically —
  the pipeline and design loops are independent (`METHODOLOGY.md` §9).
- `router_v6` is currently frozen pending a trustworthy baseline. This work
  **unfreezes it deliberately**, because it is the first router change with a
  gate-advancing justification. The freeze rationale was "do not refactor the
  thing you are measuring" — measuring is now done.

---

## Outstanding Questions

- Are the 123 shorts concentrated in the zone-pour path (98 zones emitted) or
  in A* traces? This determines whether the fix is in pour generation or
  pathfinding, and should be answered before any code is written.
- Do shorts cluster on the high-fanout power/ground nets excluded from A*?
  If so this is a pour-stitching defect, not a router defect.
- Should `completion_rate` be redefined in place, or should a new
  `legal_completion_rate` be added and the old one deprecated? In-place risks
  silently changing every historical comparison; a new name risks both being
  quoted.

### Deferred to Planning

- Whether the legality cost field feeds A* directly or only the post-pass.
- Interaction with `enable_all_pad_tree`, currently default-off.
