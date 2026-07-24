---
date: 2026-07-24
topic: router-forced-segment-fail-closed
---

# Router Forced-Segment Fallback: Uniform Fail-Closed Disposition

## Summary

This proposes making the plain A* router's forced-segment fallback fail closed for every net, not just HV/AC-class ones: when it can't find a real, clearance-respecting path, the net is reported honestly as unrouted rather than drawn as fabricated, clearance-violating copper. It accepts a real (possibly lower) completion count in exchange for trustworthy DRC/shorting measurements, and is scoped purely to that measurement fix — re-routing the newly-honest unrouted nets is separate follow-up work.

---

## Problem Frame

Earlier this session, `route_pcb()` was found to have never forwarded real per-net design rules to the A* pathfinding engine — every net this router has ever traced, including the 400V HV bus, was clearance-checked at a flat 0.2mm default for the router's entire history. That fix landed, along with a fail-closed gate (`_allow_forced_segments`) that stops the plain A* pathfinder's zero-clearance forced-segment fallback specifically for HV/AC-class nets when no legal path can be found.

A subsequent re-measurement showed the fix was necessary but not sufficient: `shorting_items` on the production board did not improve (199 → 200 violations) after the clearance-wiring fix landed. The root cause is that the forced-segment fallback — which draws a raw, unchecked line between waypoints whenever the pathfinder can't route around congestion — is still active by default for every net outside the HV/AC gate. Congested, high-fanout power and ground nets (`vcc`, `+3V3`, `PWR_RTN`) are exactly the nets most likely to hit this fallback, and they carry real current on a mains-connected induction cooker, so a clearance violation there is a genuine short/fire risk, not a cosmetic defect.

This also sits directly upstream of two active tracks: the finish-the-board plan's goal of an honest, CI-enforced DRC-to-zero gate, and the hybrid-pour-stitch work's pending decision on whether to promote pad-tree/zone-pour routing to default-on — both of which depend on the router's completion and shorting counts actually meaning what they claim to mean.

---

## Requirements

**Forced-segment disposition**
- R1. When the plain A* pathfinder's forced-segment fallback would trigger for any net — no legal, clearance-respecting path was found — the net must be reported as unrouted/incomplete rather than having a zero-clearance line drawn for it, regardless of net class (signal, power, ground, HV).
- R2. The fail-closed policy applies uniformly across every net class. No net class receives an exemption that allows fabricated, clearance-violating copper.
- R3. The unrouted/incomplete disposition must be clearly distinguishable from a genuine successful route in the router's result and reporting, consistent with the existing tree-executor precedent (`NetDisposition.INCOMPLETE`), so downstream consumers cannot mistake a forced-segment failure for a real success.

**Measurement and baseline**
- R4. After this change ships, the router's completion count (currently 24/24) reflects only genuinely, safely routed nets. The resulting number — even if lower than today's — becomes the new honest baseline; no compatibility shim or "old vs. new" flag is required.
- R5. Downstream tracks that consume this completion/shorting measurement (the finish-the-board DRC/ERC gate work, the hybrid-pour-stitch `enable_all_pad_tree`/`enable_zone_pours` promotion decision) are not blocked by this change; they measure against the new baseline going forward with no special handling.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3.** Given a congested net (e.g. a power/ground net like the ones currently observed shorting) where the plain A* pathfinder cannot find a clearance-respecting path to complete the route, when the router finishes processing that net, the net is reported as unrouted/incomplete and no clearance-violating trace segment appears in the output — the same behavior already shipped for HV/AC-class nets, now applied without a class exception.
- AE2. **Covers R4, R5.** Given the router is re-run on the current production board after this change ships, when the completion summary is generated, the reported "X/24 routed" number reflects only genuinely clearance-respecting routes — even if X is less than 24 — and no override or flag is needed for that number to be treated as correct going forward.

---

## Success Criteria

- The router's forced-segment escape hatch no longer fabricates clearance-violating copper for any net, of any class.
- A re-measurement after this ships produces a trustworthy completion count and a `shorting_items` count that reflect reality, not an artifact of the escape hatch.
- Downstream plans (finish-the-board DRC/ERC gate, hybrid-pour-stitch promotion decision) can pick up the new baseline without additional interpretation work.
- `ce-plan` can turn this into an implementation plan without inventing which nets are affected, what "incomplete" means structurally, or whether re-routing is in scope.

---

## Scope Boundaries

- Re-routing or re-closing the nets that flip to unrouted as a result of this change — separate follow-up work, likely requiring real pathfinding/ripup-reroute improvements, not part of this work.
- CI integration of the DRC/ERC anti-false-zero guard (`docs/plans/2026-07-23-001-feat-finish-the-board-drc-erc-guard-plan.md`) — separate, ongoing track; this work only supplies it a trustworthy input number.
- The `enable_all_pad_tree`/`enable_zone_pours` default-on promotion decision (`docs/plans/2026-07-22-001-feat-hybrid-pour-trace-stitch-plan.md`) — separate decision; this work only gives it a trustworthy baseline to measure against.
- Broader pathfinding/ripup-reroute algorithm improvements aimed at reducing how often the forced-segment fallback is needed in the first place.
- Any change to the tree-executor's own routing path — it already has its own INCOMPLETE-disposition handling for failed nets and is unaffected by this work.
- Full IEC 60335-1 compliance sign-off — a separate, downstream certification activity.

---

## Key Decisions

- **Honesty over completion count**: the router reports a real, possibly lower, completion number rather than preserving the current 24/24 via a more complex geometry-aware clearance check. Rationale: matches this codebase's established anti-fabricated-copper / fail-closed discipline (already applied by the tree executor and the HV/AC-only gate), and for a mains-connected appliance a wrong "success" is worse than an honest "not yet."
- **Uniform application across all net classes, not split by risk tier**: simpler, matches the tree executor's existing precedent of one disposition regardless of net class, and avoids introducing a second net-class judgment call to maintain going forward.
- **Re-closing newly-unrouted nets is explicitly deferred**: this work is scoped to making the measurement honest, not to keeping the board fully routed through the transition.

---

## Dependencies / Assumptions

- Builds directly on the HV/AC-only fail-closed gate shipped earlier this session (property-test-hardening plan, R6) — same underlying philosophy, generalized to remove the net-class condition.
- Assumes the existing forced-segment gating already threaded through the plain A* pathfinding functions is the right integration point to generalize, rather than a net-new mechanism (to be confirmed during planning's codebase research).
- Assumes downstream consumers (finish-the-board DRC/ERC gate, hybrid-pour-stitch promotion decision) read the completion/shorting numbers freshly each time rather than caching a previously-recorded "24/24" figure anywhere that would need separate updating.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R1][Technical] Confirm whether the existing HV/AC-only gate is the single correct generalization point, or whether the plain A* pathfinder's forced-segment logic has more than one call site that independently needs the same change.
- [Affects R4][Needs research] Exactly how many, and which, nets on the current production board will flip from "routed" to "unrouted" once this ships — not knowable without a live re-measurement; capture as the plan's verification step rather than assumed here.
