---
title: "Dense creepage repair is neighborhood topology, not a connector nudge"
date: "2026-08-31"
category: architecture-patterns
module: pcb-hardware-design
problem_type: architecture_pattern
component: isolation-barrier
severity: critical
applies_when:
  - "a mains-to-SELV creepage repair moves a connector or boundary component inside a dense populated region"
  - "a candidate clears its named safety pair but adds different safety signatures, shorts, or mechanical collisions"
  - "the moved footprint's approach copper and previously unrouted conductors must be evaluated with placement"
  - "a finite single-component search is exhausted without proving that every local neighborhood layout is infeasible"
  - "the checked-in land pattern differs from its manufacturer or approved-library authority"
symptoms:
  - "A candidate clears its named creepage pair while the board's total safety debt grows."
  - "Electrical connectivity passes even though the moved connector creates shorts or mechanical collisions."
  - "Authoritative footprint geometry changes the distance used to justify the placement."
related_components:
  - pcb-layout
  - req-safe
  - kicad-drc
  - rtd-connector-routing
tags:
  - mains-selv-isolation
  - pcb-floorplan
  - creepage
  - bounded-search
  - pareto-veto
  - connector-routing
  - kicad-drc
  - falsifiable-design
---

# Dense creepage repair is neighborhood topology, not a connector nudge

## Context

A localized reinforced-creepage repair can appear successful when judged only
by the named pad pair. In the K1-J1 investigation, replacing the project-local
J1 approximation with the authoritative connector land pattern made the
measured K1.4-J1.4 gap slightly worse, from 9.686463929644992 mm to
9.594676710156559 mm. Translating J1 then cleared the target corridor and
restored all four RTD nets, but both authorized placements introduced new
safety signatures, direct shorts, courtyard and fabrication-body collisions,
an inner-layer routed-creepage veto, and uncapped DRC regressions
(`docs/evidence/2026-08-30-k1-j1-creepage-repair.md`).

The investigation therefore solved a decision, not the board defect: neither
bounded connector-only translation is safe, so the correct output is evidence
plus a narrower next-step handoff. No candidate board, footprint change, DRC
ceiling, or provenance record was committed. The five added pad-only REQ-SAFE
signatures and the separate routed-copper DRC veto are itemized in the evidence
record rather than inferred from aggregate counts.

This was not the first local search to hit that shape. Earlier K1 and neighbor
campaigns found that geometry-only winners could introduce plated-hole,
shorting, or creepage regressions under live DRC, and that missing fabrication
geometry could make a collision audit appear clean by omission. Those earlier
bounded failures were search-axis results, not proofs that the whole safety
requirement was infeasible. (session history)

The checked-in board still describes J1 as a hand-built approximation and
claims its precision does not affect the high-voltage barrier, even though this
investigation measured J1.4 as the closest SELV copper to K1
(`pcb/temper.kicad_pcb:3790`). A safety
investigation must establish geometry authority before treating any placement
result as real.

## Guidance

Treat a localized safety-placement experiment as a bounded, Pareto-gated
design study rather than as a mandate to change the board.

1. **Make the physical model authoritative before optimizing it.** Verify the
   footprint's pad, drill, fabrication, and courtyard geometry against an
   authoritative source, then use that geometry on scratch boards. If the
   corrected land pattern changes the safety distance, report the delta
   explicitly. Do not silently commit the footprint update merely because it
   is more accurate; it still needs an accepted placement and routing context.

2. **Define the candidate budget and vetoes before moving copper.** A candidate
   is acceptable only if it improves the target condition without adding a
   cross-domain pair, increasing a hard-veto DRC rule, worsening a body
   collision, losing a routed endpoint, or invalidating an instrument. The
   repository's regional oracle implements this no-trade rule: new
   cross-domain pairs, relevant DRC rises, body collisions, endpoint drift,
   and instrument errors all contribute rejection reasons; acceptance requires
   no reasons (`packages/temper-quality-oracle/src/regional_feasibility.rs:107`).

3. **Move the connector and its copper as one design object.** Reroute the
   affected approaches on each scratch board and prove intended connectivity
   separately from creepage. The connectivity audit parses the written board
   and evaluates its pad, segment, and via graph
   (`packages/temper-placer/src/temper_placer/router_v6/pad_connectivity_audit.py:545`).
   Its `is_fake_completion` property distinguishes “copper exists” from “the
   pads are joined,” while zone-dependent cases remain unmeasured rather than
   being called connected
   (`packages/temper-placer/src/temper_placer/router_v6/pad_connectivity_audit.py:118`).

4. **Use independent instruments for independent claims.** Exact safety
   signatures answer whether the target pair was removed or substituted.
   Connectivity proves the nets are joined. KiCad DRC exposes shorts, mask,
   hole, and courtyard faults. Fabrication-body and containment checks address
   different mechanical questions. The isolation-barrier gate remains an
   independent fail-closed invariant
   (`scripts/check_isolation_keepout.py:894`).

5. **Reject suspect measurements before judging candidates.** The regional
   evaluator rejects missing or stale generated rules, missing project or
   footprint-library context, empty safety denominators, capped 199/499
   categories, and the known footprint-resolution failure signature
   (`scripts/evaluate_regional_layout.py:85`). The DRC API also fails when the
   KiCad project context cannot be resolved and invokes `kicad-cli` with
   `--all-track-errors` in a single-threaded environment
   (`packages/temper-placer/src/temper_placer/validation/_drc_api.py:581`).

6. **Stop when the bounded candidates fail.** Do not keep nudging the same
   component, accept a lower aggregate while new signatures appear, or raise
   DRC ceilings to absorb the result. Preserve the scratch measurements, leave
   production artifacts unchanged, and hand off the smallest larger design
   problem that can plausibly create space.

7. **Escalate from component placement to neighborhood floorplanning.** For
   this region, the next design unit is J1 plus R45, R58, R66, SW1, U22, and
   the U8 routing approach. Synchronize the authoritative J1 footprint,
   reserve the nominal K1-J1 safety corridor, and jointly place and reroute
   that low-voltage neighborhood. Only a collision-free candidate that clears
   the exact safety set and repeated set-based DRC should advance to the
   repository's full 120-sample DRC/provenance campaign.

## Why This Matters

Passing one distance check is not a safe PCB repair. A component translation
changes pad copper, holes, mask openings, courtyard, body envelope, and every
approach route simultaneously. Optimizing only the original K1-J1 metric can
therefore replace a reinforced-creepage finding with functional creepage
failures, direct shorts, or an unmanufacturable assembly.

Connectivity is similarly necessary but not sufficient. Both scratch
candidates connected all four RTD nets with no fake completion, yet each
remained unsafe because the connector and its new routes collided with the
populated neighborhood.

Historical local searches reinforce the same rule: a geometry-ranked C7
rotation placed high-voltage copper into the SELV region when evaluated with
live DRC, while other K1-region moves traded creepage improvement for
`pth_inside_courtyard` or `shorting_items` regressions. Complete physical-body
coverage and live board-level vetoes are therefore acceptance prerequisites,
not polish after a coordinate has been selected. (session history)

An evidence-only stop also protects measurement provenance. A 120-sample DRC
campaign is meaningful only for board bytes that could ship. When every
bounded candidate is rejected and the production board remains unchanged,
updating the long-horizon ceiling record would create noise without
representing a deliverable design. The stop preserves an honest baseline and
converts failed placement attempts into requirements for the next floorplan.

## When to Apply

Apply this pattern when:

- a safety, high-voltage, thermal, RF, or mechanically constrained PCB defect
  appears solvable by moving one footprint;
- correcting a land pattern changes the geometry used to justify the move;
- the footprint is already routed, so placement and approach copper cannot be
  evaluated independently;
- the board has enough legacy DRC debt that aggregate counts can hide
  signature substitution;
- candidate evaluation uses capped, nondeterministic, or context-sensitive
  tools;
- a finite local search clears the named requirement but fails another
  safety, connectivity, DRC, courtyard, body, enclosure, or manufacturability
  veto; or
- the next safe step requires moving a functional neighborhood rather than
  expanding an exhausted single-component search.

Do not use the stop as proof that no local solution exists. It proves only
that the predeclared candidates are infeasible under the measured acceptance
contract. The handoff should state exactly what was ruled out and what
additional placement freedom the next design iteration needs.

## Examples

### Target-only verdict versus professional verdict

The two connector translations looked successful on the original metric:

| Candidate | K1-J1 gap | RTD connectivity | Target-only verdict |
|---|---:|---|---|
| J1 at `(95.0, 242.0)` | 13.633236903180160 mm | 4/4 nets connected | Pass |
| J1 at `(95.0, 242.5)` | 14.067148771058212 mm | 4/4 nets connected | Pass |

The full regional verdict rejected both:

| Candidate | Safety vetoes | DRC errors/warnings | Mechanical result | Professional verdict |
|---|---:|---:|---|---|
| J1 at `(95.0, 242.0)` | 5 pad-only signatures plus J1.4-to-In3.Cu routed creepage | 425 / 409 versus 406 / 402 | Courtyard overlaps with R45/R58/R66/SW1/U22; regional evaluator reported 3 aggregate worsened fabrication-body collisions | Stop |
| J1 at `(95.0, 242.5)` | 5 pad-only signatures plus J1.4-to-In3.Cu routed creepage | 426 / 410 versus 406 / 402 | Courtyard overlaps with R45/R58/R66/SW1/U22; regional evaluator reported 3 aggregate worsened fabrication-body collisions and an additional J1.4-U22 conflict | Stop |

### Decision sequence

```text
authoritative footprint
        ↓
bounded scratch placement + affected copper
        ↓
exact safety-signature diff
        ↓
connectivity audit
        ↓
set-based DRC + courtyard/body/containment checks
        ↓
all vetoes clear? ── yes → candidate may advance to full provenance campaign
        │
        no
        ↓
leave production board unchanged
        ↓
publish evidence and refloorplan the local functional neighborhood
```

### Handoff wording

A useful handoff is constrained and falsifiable:

> The tested connector-only translations clear K1-J1 and restore RTD
> connectivity, but both add the five pad-only safety signatures itemized in
> the evidence record, a 10.2500 mm routed-creepage violation from J1.4 to the
> In3.Cu `discharge.r_snub1-p2` track, shorts, and mechanical collisions. Do not
> continue the J1-only nudge search. Jointly refloorplan J1, R45, R58, R66,
> SW1, U22, and the U8 approach using the authoritative J1 footprint. Protect
> both the K1-J1 corridor and the inner-layer high-voltage route, then require
> exact safety-set improvement and repeated set-based DRC before changing the
> production board.

That wording preserves the successful routing idea, rejects the unsafe
placements, and defines the next board-design unit without claiming that every
possible local solution has been exhausted.

## Related

- `docs/evidence/2026-08-30-k1-j1-creepage-repair.md` — the measured candidate
  evidence behind this pattern.
- `docs/solutions/architecture-patterns/physical-isolation-barrier-requires-domain-first-floorplan-2026-07-30.md`
  — the larger topology this stopped run hands off to; its current-state facts
  need a separate refresh against the PD3 board.
- `docs/solutions/workflow-issues/compound-engineering-safety-closure-evidence-2026-07-30.md`
  — why safety claims require independent evidence chains.
- `docs/solutions/design-patterns/proxy-audit-must-rerun-truth-validator-aligned-audit-2026-08-02.md`
  — exact safety truth must replace proxy improvement.
- `docs/solutions/best-practices/sufficient-condition-infeasible-is-not-requirement-infeasible-2026-07-28.md`
  — bound infeasibility conclusions to the formulation or candidate family
  actually tested.
- GitHub issues #517 and #518 — the outstanding REQ-SAFE re-layout and physical
  isolation-barrier workstreams.
