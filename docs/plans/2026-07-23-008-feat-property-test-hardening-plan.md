---
title: "feat: Property-test hardening for netclass-rules conversion and forced-segment bypass"
type: feat
status: planned
date: 2026-07-23
origin: docs/brainstorms/2026-07-23-property-test-hardening-requirements.md
adversarial_review: true
review_findings:
  - "Treating an architectural problem (3 representations) as purely a testing problem understates it — R7 added to evaluate consolidation"
  - "R1 originally ignored 6 fields with no stage0 equivalent — same silent-drop pattern as the original bug; R1b added"
  - "R6's ≥1.0mm threshold was ungrounded — corrected to use safety_category field (HV/AC)"
  - "R5 adds public API with zero consumers; test could inspect PathfindingResult internals instead"
  - "R4 tests a dormant code path; should be deprioritized explicitly"
  - "Fail-closed alternative to forced segments never evaluated; added as option 1 in R6"
---

## Summary

Two fragile areas were found in the same investigation that root-caused the `design_rules` wiring bug (`2026-07-23-005`):

1. **Three parallel, only-partially-reconciled representations of "netclass rules."** The `_to_stage0_netclass_rules()` adapter built to fix the wiring gap silently drops fields — including `safety_category`, `creepage_mm`, and `voltage_v` — and silently fabricates flat defaults for unrecognized input, exactly the same failure signature it was built to close.

2. **The forced-segment fallback is invisible to every downstream consumer.** When plain A* cannot find a legal path, it draws a raw straight line with zero clearance checking and reports `success=True`. The aggregate `total_forced_segments` is dead code (never read), and `RoutingResult` has zero fields exposing which nets were fabricated. A caller cannot distinguish a clean route from a clearance-ignoring one. This is the actual cause of persistent `shorting_items` after the wiring fix landed.

Both are instances of the same underlying pattern: a real invariant the system assumes holds is not checked anywhere, so it silently stops holding and nothing notices.

> **Post-review:** The original doc prescribed testing-only responses to what is partially an architectural problem (three representations). R7 has been added to explicitly evaluate consolidation. The forced-segment response now includes fail-closed as option 1 — the simplest approach, already precedented in this codebase for tree-executed nets.

---

## Requirements

### Area A — Netclass Rules Representation Boundaries

#### R1 — Property test: `_to_stage0_netclass_rules()` round-trip totality
**Priority: P1 — red-then-green (finds a live bug)**

Generate arbitrary `core.netclass_rules_gen.NetClassRules` instances via Hypothesis (`st.builds` over `name`, `trace_width`, `clearance`, `via_diameter`, `via_drill`, `max_current_rating` — vary optional fields including `None`). Assert the stage0 output's `.clearance_mm`/`.trace_width_mm`/`.via_diameter_mm`/`.via_drill_mm`/`.name` equal the source's corresponding fields, **and** assert `.current_rating_amps == source.max_current_rating`.

The `current_rating_amps` assertion **fails today** — the mapping line doesn't exist — making this red-then-green work that finds a live bug (silent data loss at a representation boundary, structurally identical to the session's original bug).

#### R1b — Surface the six unrepresented fields instead of silently dropping them
**Priority: P1 — safety-relevant (post-review addition)**

`core.netclass_rules_gen.NetClassRules` has six fields with **no stage0 equivalent**: `creepage_mm`, `voltage_v`, `safety_category`, `routing_strategy`, `via_cost_multiplier`, `layer_costs`. `_to_stage0_netclass_rules()` silently drops all six on every conversion. R1's round-trip test only covers the fields that *do* map, meaning it would pass today (once `current_rating_amps` is fixed) while these six keep vanishing unremarked.

This is the same silent-drop failure class the whole investigation is about. `safety_category` (`"HV"`/`"LV"`/`"AC"`/`"iso"`) is specifically safety-relevant — dropping it during the exact conversion built to fix a safety-relevant clearance bug is a real gap.

**Options:**
- **(a) Extend `stage0_data.NetClassRules`** with slots for at least `safety_category` and `creepage_mm`/`voltage_v` (the three with clear safety relevance) so they survive conversion. **R6 depends on whichever option is chosen** — it needs `safety_category` to survive into whatever the A* engine's forced-segment logic can see.
- **(b) Assert loudly in the adapter** — if the fields are deliberately out of scope for the A* engine, log/raise on a non-default `safety_category` being dropped rather than silently discarding it. A `WARNING`-level log for a non-`None` `safety_category` at a minimum.

#### R2 — Property test: fail-loud on unrecognized shape
**Priority: P1 — highest value in Area A**

Generate objects lacking both `.clearance_mm` and `.clearance` (bare namespaces, objects with only some expected attributes) via `st.sampled_from`/`st.builds` over deliberately malformed shapes. Assert `_to_stage0_netclass_rules()` **raises** rather than silently returning a `NetClassRules` seeded from the hardcoded fallback constants (`0.2, 0.2, 0.6, 0.3`).

This is currently false — it fabricates silently. Implementing R2 requires changing `_to_stage0_netclass_rules()` to raise on an unrecognized shape instead of `getattr(rules, attr, default)`, which is a real code change, not just a test addition. This is the adapter meant to fix "silently falls back to flat defaults" itself silently falling back to flat defaults given bad input.

#### R3 — Property test: injected assignments are never silently dropped
**Priority: P2**

Generalizes the already-shipped `test_route_pcb_forwards_real_netclass_rules_to_pipeline_engine` (which sweeps one clearance value on one net) to a Hypothesis-generated **set** of `{net_name: class_name}` assignments of varying size, asserting every entry survives intact from `route_pcb(design_rules=...)` through to what `pipeline.run()` is called with. Catches partial-drop bugs that a single-net test misses.

#### R4 — Regression test: explicit precedence between native and injected netclasses
**Priority: P3 — gated, adjacent gap**

Construct a `.kicad_pcb` fixture with an embedded `(net_class ...)` section for a class name that collides with an injected class of the same name but different clearance value; assert the injected value wins (matching current behavior) — or, if the team decides native-file values should take precedence, record that deliberate decision.

> **Post-review deprioritization:** R4 tests a code path that is currently dormant on the production board (`assignments_size=0` from native extraction). R1–R3 and R5–R6 form a coherent package without R4. If written, keep it minimal — a single deterministic scenario, not property-based.

#### R7 — Evaluate consolidating the three netclass-rules representations
**Priority: P3 — evaluation, not implementation (post-review addition)**

R1–R4 make the existing three-way split safer. They do not address *why* three representations exist or whether that's still justified. Specifically: is `io/_parse_nets.py::_extract_design_rules()` (native `.kicad_pcb` file extraction) still needed now that `route_pcb()` injects the YAML SSOT directly? If vestigial, removing it eliminates one whole representation and its silent-precedence-conflict risk at the source — a stronger fix than any test.

This requirement is evaluation-only: produce a documented decision (keep, remove, or deferred with rationale). Do not implement consolidation in this plan.

---

### Area B — Forced-Segment Invisibility

#### R5 — `RoutingResult` must expose forced-segment visibility
**Priority: P1**

Add a field to `RoutingResult` (`forced_segment_nets: list[str]` or equivalent), threaded from `PathfindingResult.total_forced_segments`/per-path `forced_segment_count` through `_build_routing_result`.

> **Post-review:** This adds a public API field with zero current consumers. The test that asserts it exists could instead directly inspect `PathfindingResult` internals without growing the public API. Consider whether `PathfindingResult`-level inspection is sufficient — if yes, R5 maps to adding a test for existing internal tracking rather than new public surface. If external consumers genuinely need this, the field is justified. Decide before implementing.

**TDD ordering:** Write the test first (asserting the field exists and is populated for a net forced into a straight-line fallback via a constructed all-obstacle grid, reusing the wall-obstacle pattern from `test_all_pad_tree_routing.py`'s `grid.grid[:, 8] = 1`), confirm it fails (no such field), then implement.

#### R6 — Property test: HV/AC-class forced-segment escalation (fail-closed)
**Priority: P0 — single highest-value test across all three docs**

For nets whose `safety_category` is `"HV"` or `"AC"`, force a legal-path failure (all-obstacle grid) and assert the net does **not** silently return `success=True, reason="congestion_forced"`. Three options:

1. **Fail-closed (recommended — simplest, already precedented):** Set `allow_forced_segments=False` for HV/AC-class nets specifically, mirroring `allow_forced_segments=not tree_route_active`. Tree-executed nets already fail to `NetDisposition.INCOMPLETE` instead of fabricating copper; extending the same `False` gate to safety-critical netclasses requires no new status type, no new field — just reusing the flag that already exists for exactly this purpose.
2. **Raise or distinguishable failure status** (more invasive — new signal type).
3. **Populate R5's field** as a minimum bar, leaving the net formally "successful" but visible to a downstream gate.

Option 1 should be evaluated first — it's the least code, reuses an established pattern, and matches this codebase's fail-closed/`UNMEASURED` discipline most directly.

**Gate:** R6 depends on R1b — `safety_category` must survive `_to_stage0_netclass_rules()` (or reach the A* engine via another path) before the forced-segment logic can gate on it. Sequence R1b first.

**Impact:** This directly targets `SW_NODE` (HighVoltage), one of the nets still shorting post-wiring-fix. Enforcing "HV/AC nets must not silently forced-segment" would force this exact net to be visibly flagged or honestly left unrouted instead of silently drawn as an out-of-clearance straight line.

---

## Scope Boundaries

**In scope:** R1, R1b, R2, R3 (Area A property tests), R4 (precedence regression, minimal), R7 (representation consolidation evaluation), R5 (forced-segment visibility, with the public-API vs. internal-inspection decision), R6 (HV/AC forced-segment fail-closed).

**Out of scope:**
- Deciding the exact failure-mode API for R2/R6 beyond what's scoped above (raise vs. warn vs. new status).
- **Implementing** the consolidation R7 evaluates (R7 is evaluation-only).
- Any pinch points beyond Areas A and B (the dead-parameter sweep is `2026-07-23-006`'s territory).
- Full IEC 60335-1 compliance sign-off.

---

## Key Technical Decisions

- **TDD ordering is load-bearing.** R1's `current_rating_amps` assertion fails today — the test must be red before the code fix lands. R2's raise-on-unrecognized-shape assertion also fails today. Both are red-then-green work, not post-hoc verification.
- **R6 uses `safety_category`, not a numeric threshold.** The original ≥1.0mm proposal was an ungrounded proxy. The field that actually classifies nets as safety-critical already exists — use it. (Post-review correction.)
- **R6 option 1 (fail-closed) is precedented.** `allow_forced_segments=not tree_route_active` already exists. The question is whether to extend the same gate to HV/AC nets, not invent a new mechanism.
- **R1b must sequence before R6.** `safety_category` can't gate forced-segment behavior if it doesn't survive the conversion boundary.

---

## Dependencies / Assumptions

- R1b is a prerequisite for R6 — `safety_category` must be visible to the A* engine's forced-segment logic.
- R4 is gated on the same architectural decision as `2026-07-23-007`'s R3 (injection vs. native extraction).
- R5's public-API-vs-internal-inspection decision should be resolved before implementation.
- Hypothesis is already a dev dependency in `temper-placer` (used by existing property tests).

---

## Success Criteria

- [ ] R1: Hypothesis test fails (red) on `current_rating_amps` mismatch, passes (green) after mapping line added.
- [ ] R1b: `safety_category`, `creepage_mm`, `voltage_v` either survive conversion (option a) or trigger a loud warning on drop (option b).
- [ ] R2: Hypothesis test fails (red) on unrecognized-shape silent-fallback, passes (green) after adapter raises.
- [ ] R3: Hypothesis test with varied assignment sets confirms all entries survive `route_pcb()` → `pipeline.run()`.
- [ ] R4: Single deterministic regression test confirms injection-vs-native precedence is explicit, not accidental ordering.
- [ ] R5: Test fails (red) — `RoutingResult` has no forced-segment field. Passes (green) after field added and threaded through.
- [ ] R6: HV/AC-class net forced into legal-path failure does not silently return `success=True`; either fails to `INCOMPLETE` (option 1) or raises/warns/records (options 2/3). High-confidence that `SW_NODE` would be caught.
- [ ] R7: Documented decision on whether `io/_parse_nets.py::_extract_design_rules()` should be kept, removed, or deferred.

---

## Sources & References

- `docs/brainstorms/2026-07-23-property-test-hardening-requirements.md` — source requirements doc
- `docs/plans/2026-07-23-005-fix-router-design-rules-wiring-plan.md` — upstream fix; R8 there (forced-segment decision) is directly extended by R5/R6 here
- `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md` — fail-closed/`UNMEASURED` discipline
- `_adapter_convert.py` — `_to_stage0_netclass_rules()` (R1, R1b, R2)
- `_astar_reconstruct.py` — forced-segment block (R6), `PathfindingResult` (R5), `allow_forced_segments` gate
- `_adapter_types.py` — `RoutingResult` (R5)
- `stage0_data.py` — `NetClassRules`/`DesignRules`
- `core/netclass_rules_gen.py` — `NetClassRules` (YAML SSOT shape)
- `io/_parse_nets.py` — `_extract_design_rules()` (third representation, R4/R7)
