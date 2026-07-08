---
date: 2026-07-06
topic: netclass-aware-clearance-ssot
---

# Netclass-Aware Clearance: Single Source of Truth + Place/Route Enforcement + Per-Layer Experiment

## Summary

Define a netclass→clearance mapping as a single authoritative config file; consume it from both CP-SAT placement (preventive SEPARATED constraints) and router_v6 (preventive per-netclass routing spacing); write the same rules as `(net_class ...)` forms into the generated output `.kicad_pcb` so kicad-cli DRC checks at the same values the placer enforced. Backstop the preventive layers with the existing F3 feedback loop's DRC-violation-as-constraint-delta mechanism. A per-layer experiment measures how much of the current 121-vs-29-baseline DRC-violation gap each layer closes.

---

## Problem Frame

The umbrella-final-report's headline open item: CP-SAT placement produces 121 DRC errors vs the 29-violation human baseline, because the CP-SAT constraints enforce *geometric* clearance between component bodies (Chebyshev, broad categorical HV↔LV), but DRC checks *tracked geometry* with *per-netclass* rules — and the temper PCB currently has **zero netclass definitions in it** (verified: no `(net_class ...)` forms in `power_pcb_dataset/corpus/temper/temper.kicad_pcb`). kicad-cli DRC therefore runs at KiCad's default ~0.2mm clearance, not at the 6mm ACMains-to-signal rule the board *should* have. The manufacturing-relevant rules are missing from the board, not only from the placer — the "121 errors" are measuring the board against a default it was never designed to, not against real netclass-aware rules.

Net classification infrastructure already exists in the placer (`packages/temper-placer/src/temper_placer/core/net_classification.py`: GROUND / POWER / HV / SIGNAL net-name patterns plus pin-name patterns). Safety-isolation constraints cite IEC 60335-1 at 10mm reinforced isolation (`packages/temper-placer/configs/constraints/safety_isolation.yaml`). The existing F3 feedback loop already injects DRC-violation-derived `SeparatedConstraint` deltas at `packages/temper-placer/src/temper_placer/placer/cp_sat/feedback.py:239`. What's missing is the *mapping* between netclass pairs and the clearance values both halves of the placement-routing seam should enforce, and a single source of truth so the two halves and the truth gate stay aligned.

The structural risk this workstream exists to prevent: constraint drift between the rules the placer enforces and the rules kicad-cli DRC checks against. Hand-maintain `netclass_rules.yaml` and the PCB's `(net_class ...)` forms separately, and they will diverge — at which point the two-tier acceptance gate stops being meaningful (the preventive layer and the truth gate check against different rules, defeating the point of having both).

---

## Actors

- A1. **`netclass_rules.yaml`** — the single authoritative config artifact. Defines netclass names, voltage classes, and per-class-pair clearance values with `because` fields citing physics derivations where applicable. Consumed by both halves of the place↔route seam and by the output-PCB-writing step.
- A2. **CP-SAT encoder** (existing) — auto-generates preventive SEPARATED constraints for every cross-class component-net-pair from the authority, using the per-pair clearance in the rules. Two-tier: safety-critical pairs at physics-cited values with `because`; routine pairs at manufacturer defaults.
- A3. **router_v6** (existing) — routes with per-netclass spacing derived from the same authority. The router receives the rules and applies them during routing; its internal structural changes are out of scope (per Scope Boundaries).
- A4. **`temper optimize` output-write step** (existing) — gains a new responsibility: writing `(net_class ...)` forms into the generated output `.kicad_pcb` from the authority. The output PCB is a *derived artifact* — never hand-edited for netclass rules; the YAML is the only editable surface.
- A5. **kicad-cli DRC** (existing truth gate) — checks the generated output PCB. With the netclass forms written from the same authority the placer/router enforced, kicad-cli DRC's verdict is now meaningful: a "zero errors" verdict and a "placements enforced" verdict check against the *same* rules. The two-tier gate closes its drift-risk gap.
- A6. **F3 place→route feedback loop** (existing) — backstop. When preventive placement + preventive routing still leave a DRC violation, the existing `_handle_clearance_violation` path at `feedback.py:239` injects a `SeparatedConstraint` delta for the violating pair and triggers a CP-SAT re-solve per the hybrid backtracking policy (auto-soft for tunable pairs, escalate-to-operator on physics-grounded pairs).

---

## Key Flows

- F1. **Authority definition**
  - **Trigger:** Plan start.
  - **Actors:** A1
  - **Steps:** Define `netclass_rules.yaml` with two tiers: (a) safety-critical pairs (HV↔SIGNAL at 6.0mm per IEC 60335-1, HV↔GROUND per derating) with `because` fields citing physics derivations and IEC table IDs, matching the L_loop-derivation pattern; (b) routine pairs (POWER↔SIGNAL, POWER↔GROUND at 0.2mm or matching the manufacturer default) without per-pair `because`. Carries a `default_clearance_mm` for any pair not explicitly listed.
  - **Outcome:** A single editable file; one authority for placement, routing, and the truth gate.
  - **Covered by:** R1

- F2. **Preventive placement (CP-SAT)**
  - **Trigger:** `temper optimize --placer cp-sat` with `netclass_rules.yaml` loaded.
  - **Actors:** A2
  - **Steps:** Auto-generate SEPARATED constraints for every cross-class component-net-pair from the rules, using each pair's clearance value from the authority. Safety-critical pair values are hard constraints (tol=0); routine pair values are hard by default (no relax path — the existing backtracking policy governs if a constraint proves infeasible). The placement solver produces positions that satisfy every pair's clearance as a feasibility constraint, not as a soft weighted-sum objective.
  - **Outcome:** Placement that provably has enough room between component bodies for the router to route at netclass-aware spacing.
  - **Covered by:** R2

- F3. **Preventive routing (router_v6)**
  - **Trigger:** Placement from F2 handed to router_v6.
  - **Actors:** A3
  - **Steps:** The router receives the per-netclass spacing rules from the authority and applies them during routing. Track-to-track distance for any two nets is bounded below by the max of the two nets' class-pair clearance.
  - **Outcome:** Routing that produces tracks respecting per-netclass clearance rules by construction.
  - **Covered by:** R3

- F4. **Output-PCB netclass-form write**
  - **Trigger:** `temper optimize` writes the placed+routed output `.kicad_pcb`.
  - **Actors:** A4
  - **Steps:** Write `(net_class ...)` forms into the output PCB from the authority — netclass names, clearance values, track-width rules from the same YAML. This is a *derived* write (not requiring the input PCB to have the forms; the input temper PCB currently has none). If the input PCB had pre-existing forms, they are preserved and the YAML-derived rules merge in (override semantics defined in planning).
  - **Outcome:** The output PCB carries the same netclass definitions the placer and router enforced; kicad-cli DRC's verdict on this PCB checks against those rules.
  - **Covered by:** R4

- F5. **Reactive feedback (backstop)**
  - **Trigger:** The truth gate reports a DRC violation after placement+routing despite the preventive layers.
  - **Actors:** A6
  - **Steps:** The existing feedback loop injects a `SeparatedConstraint` for the violating net-pair with the violated clearance value; CP-SAT re-solves per the hybrid backtracking policy (auto-track soft-tunable injecting, escalate-to-operator on physics-grounded hard pairs). This backstop fires rarely if the preventive layers are working; when it fires, it's signal about preventive-layer gaps.
  - **Outcome:** Remaining post-preventive violations close or escalate.
  - **Covered by:** R5

- F6. **Per-layer experiment (decisive measurement)**
  - **Trigger:** All five flows above are functional.
  - **Actors:** A1–A5
  - **Steps:** Measure the 121-vs-baseline delta at three checkpoints: (a) placement-only constraints (CP-SAT with netclass-aware SEPARATED, router still without netclass-aware spacing — measures how much room placement alone buys); (b) placement + routing (both preventive layers active, no feedback — measures the preventive-layer total); (c) placement + routing + feedback (full pipeline — measures the backstop's marginal contribution). Record the DRC error count at each checkpoint against the 29-violation baseline.
  - **Outcome:** A table that quantifies each layer's contribution to closing the 121→≤29 gap and identifies the load-bearing layer (placement room vs routing rules vs reactive feedback) for follow-up tuning.
  - **Covered by:** R6

---

## Requirements

**[Single source of truth]**
- R1. `netclass_rules.yaml` is the sole editable surface for netclass→clearance (and track-width via netclass) rules. Two tiers: (a) safety-critical class-pairs (HV↔SIGNAL, HV↔GROUND per IEC derating) with `because` fields citing the specific physical derivation or IEC table ID — matching the L_loop-derivation pattern; (b) routine class-pairs (POWER↔SIGNAL, POWER↔GROUND, intra-HV) at manufacturer-default values without per-pair `because`. A `default_clearance_mm` field covers any pair the YAML doesn't explicitly list. The YAML's textual schema is stable through this doc's reader (planning spells out the exact shape).

**[Preventive placement]**
- R2. The CP-SAT encoder auto-generates SEPARATED constraints for every cross-class component-net-pair in the netlist from `netclass_rules.yaml`. Constraint values (clearance in mm) come directly from the authority — no per-board hand-tuning, no separate config. Safe-critical pairs are hard constraints (tol=0 per the Objective-Discipline Contract); routine pairs are hard by default with the hybrid backtracking policy governing relax-and-escalate behavior. This extends the existing `_encode_separated` handler, not a new constraint type.

**[Preventive routing]**
- R3. router_v6 routes with per-netclass spacing derived from the same `netclass_rules.yaml`. The cross-net-class distance between two tracks is bounded below by the max of the two nets' class-pair clearance value from the authority. This Bordeaux is additive with existing router_v6 constraints (channel widths, layer capacity); it does not replace them.

**[Output PCB as derived artifact]**
- R4. The `temper optimize` output-PCB write step generates `(net_class ...)` forms in the output `.kicad_pcb` from `netclass_rules.yaml`. The output PCB is a derived artifact of the YAML; the KiCad PCB is never hand-edited for netclass rules. If the input PCB has pre-existing `(net_class ...)` forms, they are preserved; the YAML-derived rules merge in with documented merge semantics (planning decides per-class overwrite vs union). The current temper input PCB has zero forms, so the merge is append-only in practice.

**[Reactive feedback (existing) ]**
- R5. The existing F3 feedback loop's `_handle_clearance_violation` path (`feedback.py:239`) is the backstop and operates unchanged. When the preventive layers leave a DRC violation, the loop injects a `SeparatedConstraint` for the violating pair and triggers a re-solve per the hybrid backtracking policy. No new code in F5; the requirement is verification that the existing handler consumes the YAML-derived values when injecting deltas (so it doesn't inject a default-tight value that conflicts with the YAML's physics-cited value on a critical pair).

**[Per-layer experiment]**
- R6. The experiment's decisive measurement is a three-row table, each row reporting DRC error count against the 29-violation human baseline:
  - **Row A** — placement-only preventive constraints (CP-SAT with F2 active, router without F3 active): measures how much room placement alone buys.
  - **Row B** — placement + routing (both preventive layers active, feedback loop off): measures the preventive-layer total.
  - **Row C** — placement + routing + feedback (full pipeline): measures the full close, including the backstop's marginal contribution.
  The table is recorded with which layer was load-bearing for closing the gap. Per the umbrella's Decisive-Result-Discipline, this is the workstream's adjudicating measurement; it does not gate the workstream's merge (the preventive code lands), but it gates the follow-up tuning (if Row A already closes the gap, further routing-side work is unnecessary; if only Row C closes the gap, preventive-layer scope was insufficient and the design should be revisited).

---

## Acceptance Examples

- AE1. **Covers R1.** Given `netclass_rules.yaml` declares `HV↔SIGNAL: 6.0mm` with `because: "IEC 60335-1 Table 16 reinforced isolation at 400V working voltage"` and `POWER↔SIGNAL: 0.2mm` (no `because` — manufacturer default), when CP-SAT and router_v6 and the output-PCB write step all load the file, the values they enforce and write into the PCB match the YAML's exactly (a later read-back of the output PCB's `(net_class ...)` forms returns the same clearance values).
- AE2. **Covers R2, R4.** Given `netclass_rules.yaml` declares `HV↔SIGNAL: 6.0mm`, when `temper optimize --placer cp-sat` runs, the CP-SAT placement positions every HV-tagged and SIGNAL-tagged component pair at ≥6.0mm Chebyshev edge-to-edge AND the generated output PCB's `HV` net class form declares `0.6mm` clearance against the `Signal` net class — both numbers traceable to the YAML's single 6.0mm value (times 0.1mm grid rescaling for the PCB's 0.1mm-form display, per planning's exact conversion choice).
- AE3. **Covers R3.** Given two routed tracks, one tagged HV and one tagged SIGNAL, when router_v6 routes them, the minimum cross-track distance ≥ 6.0mm.
- AE4. **Covers R5.** Given a DRC violation reported between a HV-to-SIGNAL pair at 5.8mm despite preventive placement and routing, when the feedback loop runs, it injects a `SeparatedConstraint` for that pair with `min_distance_mm: 6.0` (the YAML's value — not a tighter or looser default), re-solves, and either closes the violation or escalates to operator if it's a physics-grounded hard pair.
- AE5. **Covers R6.** Given the workstream's three checkpoints complete, the experiment report contains a three-row table (Rows A / B / C) each carrying DRC error count vs the 29-violation baseline, and a one-sentence "load-bearing layer" finding stating which layer contributed most to closing the gap.

---

## Success Criteria

- *DRC error count on the temper board with the full pipeline is ≤ 29 violations* (the human baseline) — the bar the umbrella's F2/F4 decisive result previously missed by 92 violations. Strict-zero is stretch, not gating; the framework closes most of the gap and the doc declares the trailing-edge delta.
- A single authoritative `netclass_rules.yaml` is the only editable surface for clearance rules; mutation of KiCad PCB netclass forms by hand (outside the YAML-derived output-write step) is detectable as drift and documented as a non-supported workflow.
- The three-row per-layer experiment table quantifies which layer (placement / routing / feedback) carries the gap closure. Planning adjusts follow-up scope based on the result.
- A downstream planner can scope the implementation without inventing the YAML schema, the encoder integration, the router integration, or the output-PCB write step — these decisions are documented here as scope-level commitments, with implementation specifics deferred to planning.

---

## Scope Boundaries

- **Full IEC 60335-1 Table 16 encoding is out of scope.** Only the rows relevant to this board's voltage classes (mains AC at 230Vrms/325Vpk, DC bus at 325V, IGBT power stage) get `because`-cited values. Full-table encoding is a follow-up if the tool serves multiple boards with varying voltage profiles or pollution degrees.
- **router_v6 internal architecture changes are out of scope.** The router consumes the rules and applies them; internal structural changes to its channel model or topology solver belong in a separate workstream if the rules don't compose with the existing model.
- **Schematic-editor-integrated netclass declaration is out of scope.** The PCB's `(net_class ...)` forms are generated by the `temper optimize` output-write step from the YAML, not synchronized from a schematic editor. KiCad's native schematic-netclass workflow is upstream of and orthogonal to this workstream; if a board designer uses KiCad's native workflow to define netclasses, the YAML and the schematic would both need separate edits — the SSOT discipline prevents drift *within this tool's outputs*, not across tool boundaries.
- **Placement-aware derived net clearance rules (e.g. "this signal net is adjacent to an HV pad so it inherits tighter clearance there") are out of scope.** The rules are class-pair rules (HV-net to SIGNAL-net), not per-pin or per-route-segment rules. Per-pin rules are a follow-up if the class-pair layer proves insufficient.
- **Track-width rules and via-size rules are in scope for the YAML and the output-PCB write step, not for the CP-SAT placer** (placement doesn't choose track widths). The YAML can carry them; router_v6 and the output-PCB write step use them; CP-SAT ignores them. This is a per-consumer contract, not a per-rule contract.
- **The KiCad input PCB (the corpus board being placed) is not modified by this workstream.** Only the output PCB generated by `temper optimize` carries the derived `(net_class ...)` forms. If pre-existing input PCB forms exist (the temper board has none), they are preserved.

---

## Key Decisions

- **SSOT = `netclass_rules.yaml` (new file), not a `pcb_spec.yaml` extension or the KiCad PCB itself.** A new standalone file because: (a) the rules are shareable across boards with the same voltage-class profile — embedding in `pcb_spec.yaml` forces per-board re-statement; (b) parsing `(net_class ...)` forms back out of the KiCad PCB would couple the placer to KiCad's file-format stability; (c) a plain YAML config is the existing pattern (per `safety_isolation.yaml`, `half_bridge_base.yaml`) — the existing project ethos is that constraint authority lives in YAML configs, not in tool-format files.
- **Two-tier over fully-explicit or fully-derived.** Safety-critical pairs get `because`-cited physically-grounded values matching the L_loop-derivation and IEC-60335-1-cited patterns; routine pairs get manufacturer defaults without per-pair derivation. The boundary is judgment-call per class-pair, with the default for ambiguous pairs being "two-tier explicit" (cite included) over "two-tier default" (number only). This is the existing PCL `tier` discipline extended to a new artifact.
- **The output PCB is a derived artifact.** The Yemen `(net_class ...)` forms generated from the YAML carry the same values the placer and router enforced. The hand-editing of PCB forms outside the YAML-derived output-write step is explicitly a non-supported workflow; any drift between YAML and PCB forms is the operator's responsibility to resolve by editing the YAML, never the PCB directly.
- **Track-width and via-size rules live in the YAML but are router+PCB-write scoped, not CP-SAT scoped.** The YAML carries them for router_v6 and the output-PCB write step; CP-SAT ignores them because placement doesn't choose track widths. One authority, multiple consumers, per-consumer contract for what to consume.
- **The F3 feedback loop dominates as the backstop; the preventive layers dominate as the primary closure.** Pre-placement + pre-routing are designed to close the gap; the feedback backstop fires on the residual (per the umbrella's "preventive layer > reactive layer" discipline). The experiment (R6) measures which layer is load-bearing for the actual close.
- **Experiment doesn't gate merge, gates follow-up tuning.** The preventive code lands regardless; the experiment's job is to tell planning where the next round of investment belongs (placement tightening vs routing rules vs feedback tuning). Per the umbrella's Decisive-Result-Discipline, an adjudicating measurement that doesn't gate merge still binds follow-up investment to evidence rather than guess.

---

## Dependencies / Assumptions

- **The `temper optimize` output-PCB write step currently exists and writes a `.kicad_pcb` file** — verified via the F3 workstream's end-to-end pipeline run (umbrella-final-report: "Pipeline runs end-to-end"). The output write step gains a new responsibility (netclass forms) but doesn't need to be built from scratch.
- **`core/net_classification.py` is consumable from the CP-SAT encoder and router_v6** — verified during the Phase 1.1 scan: GROUND / POWER / HV / SIGNAL net-name patterns with `classify_net()`, plus pin-name patterns. The encoder will call `classify_net()` per net in the netlist to determine class membership.
- **`safety_isolation.yaml`'s IEC 60335-1 Table 16 citation at 10mm/400V reinforced isolation is the source for HV↔SIGNAL's `because` text** — verified at `packages/temper-placer/configs/constraints/safety_isolation.yaml`. The 6mm HV↔SIGNAL value for non-reinforced (working) isolation can cite the same IEC table at the same working voltage but the lower row (or a re-derivation — planning determines which).
- **The KiCad PCB `(net_class ...)` form's syntax for clearance is known-encodable from Python** — *unverified assumption*: the write step needs to emit syntactically-correct `(net_class "HV" (clearance 6.0) ...)` forms. KiCad 9's PCB format syntax should support this, but the exact form and whether `(clearance ...)` is per-class or per-class-pair must be verified against the KiCad format spec (planning surfaces this as a deferred technical question).
- **router_v6 has an existing clearance-spacing surface for channel/track distance** — *unverified assumption*: `router_v6/channel_widths.py` and `constraint_model.py` were inspected during the Phase 1.1 scan but no netclass-aware clearance path was found. Planning must verify whether netclass-aware spacing slots into the existing channel-width model, the constraint-model layer, or a new insertion point; the brainstorm defers this to planning because it's router-internal architecture.
- **The existing `_handle_clearance_violation` handler at `feedback.py:239` injects `min_distance_mm` from the violation itself, not from a YAML** — *unverified*: the brainstorm's R5 assumes the injected value matches the YAML's authority when the YAML is loaded; planning must verify the handler reads the YAML after this workstream's integration, not just reads the DRC violation's number. The risk: handler injects a default-tightened value that conflicts with the YAML's physics-cited value on a safety-critical pair.

---

## Outstanding Questions

### Resolve Before Planning

_None — scope decisions (where the fix lands, rule source, SSOT mechanism) are resolved by the brainstorm answers; the open items below are technical and route cleanly to planning._

### Deferred to Planning

- [Affects R4][Technical] Exact KiCad `(net_class ...)` syntax for per-class-pair clearance — KiCad's format may support per-class only (with pairwise defined via `(net_class ...)` rules within the class) or per-class-pair explicitly. Planning verifies against KiCad 9's PCB format spec and chooses the encoding form.
- [Affects R3][Technical] Where netclass-aware spacing enters router_v6 — `channel_widths.py`? `constraint_model.py`? A new module? The brainstorm verified no existing surface; planning decides the insertion point against the router's internal architecture (out of scope per Scope Boundaries — the workstream adds the rule, not changes the architecture).
- [Affects R5][Technical] Whether `_handle_clearance_violation` needs modification to read the YAML's physics-cited value for the violating pair, or whether it already correctly inherits from the DRC violation's `required_mm` field. The risk: the handler might inject a default-clearance value that overrides the YAML's tighter physics-cited value on a safety-critical pair.
- [Affects R6][Technical] Exact experiment harness — three separate `temper optimize` runs with progressively more layers active, plus three kicad-cli DRC runs against the progressively-more-derived output PCBs. Or one run with layer toggle-flags. Planning decides the mechanism; the brainstorm binds only the three-row structure and the per-layer load-bearing finding.
- [Affects R1][User decision] Track-width and via-size per netclass — the YAML schema carries these fields, but the values (mm) for HV vs SIGNAL vs POWER classes are not determined by this brainstorm. Planning either punts (only clearance, the width fields are reserved-but-empty for v1) or derives them from manufacturer defaults (JLCPCB 6mil / 0.15mm minimums for the common order, higher for power). User call on whether v1 includes them.