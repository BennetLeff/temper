---
date: 2026-07-05
topic: constraint-completion-cp-sat-encoder
---

# Constraint-Model Completion: CP-SAT Encoder for 8/8 PCL Constraint Types

## Summary

Complete the CP-SAT constraint encoder so a temper-board placement satisfies the full design intent — replacing the existing soft-sum `_encode_loop_area` handler with a hard physics-grounded ceiling (`max_area_mm2=500mm²`, tol=0 — per the L_loop derivation), adding the missing `ANCHORED` / `KEEPOUT` / `ALIGNED` handlers, and adding discrete rotation (0°/90°/180°/270°) to all non-polarized parts as a net-new model-level capability. The decisive result is: *temper board places with all 8 constraint types honored AND with rotation enabled AND passes real KiCad DRC at 6mm* — at which point "CP-SAT places the board" means "satisfies the full design intent" instead of "5 of 8."

---

## Problem Frame

The CP-SAT feasibility spike (U0, ~62s) and the U8 parity harness validate CP-SAT against **4 of the 8 PCL constraint types** the board actually specifies (`SEPARATED`, `ENCLOSING`, `ON_SIDE`, `ADJACENT`). The post-parity umbrella roadmap (`docs/brainstorms/2026-07-03-post-parity-cp-sat-umbrella-roadmap-requirements.md` — referenced by name per doc-review coherence fix) identified the remaining four as blocking the routing workstream and as a correctness gap: "CP-SAT places the board" today means "satisfies half the design intent."

A post-implementation audit of `encoder.py:224` (verified in the #121 worktree — `from temper_placer.placer.cp_sat.encoder import ...` exists post-#121) surfaced a related, more acute issue: the existing `_encode_loop_area` handler is a **soft weighted-sum wirelength term** over consecutive loop pairs — exactly the paradigm-failure pattern the umbrella's Objective-Discipline Contract forbids. It encodes loop area as "minimize the sum of intra-loop Manhattan wirelength," with no ceiling and no constraint coupling. The L_loop physics derivation (`docs/solutions/best-practices/commutation-loop-area-physics-derivation-2026-07-04.md`, 500mm² = 79% of the 635mm² IGBT-overvoltage critical area) settled the kind question: loop area enters the encoder as a **hard ceiling** (`area ≤ 500mm²`, tol=0) because the failure mode is IGBT overvoltage destruction, not EMI preference. So the workstream includes *replacing* a forbidden soft handler, not only adding missing ones.

Rotation is the third axis. The JAX softmax rotation bug (250M rotation-logits) was the original symptom of trying to model a discrete choice as a continuous relaxation in JAX; CP-SAT handles discrete enumeration natively and correctly, which is the paradigm dividend this workstream actively collects. No rotation infrastructure exists anywhere in the CP-SAT model today (verified at grep-time — neither main nor worktree has rotation variables in `placer/cp_sat/`) — this is net-new model construction, not an extension.

**Round-2 doc-review headline correction (P0):** the original U0 spike validated 4/8 constraint types at ~62s; the **8/8 + 4-way rotation model this workstream introduces has not been empirically validated.** A maximalist rotation bet on ~30 rotatable components inflates the variable space by ~2^60 — model-size cost and solver budget are genuinely unknown. This doc resolves the gap by adding a **U0b extended spike** (per the brainstorm's "spike first, then parallel" answer) as its first implementation unit: it gates F1's JAX-retirement deletion AND this workstream's full implementation. U0b passes → both proceed; U0b fails → the paradigm decision is at issue.

---

## Actors

- A1. **CP-SAT encoder** (`placer/cp_sat/encoder.py`): the handler-dispatch module; subject of all unit additions and the loop-area replacement.
- A2. **CP-SAT model builder** (`placer/cp_sat/model.py`): per-component `x_start` / `y_start` / interval vars; rotation variables and footprint-variant sizing enter here.
- A3. **Post-solve audit** (`placer/cp_sat/audit.py`): the unconditionally-run verifier; gains three new audit checks (ANCHORED region membership, KEEPOUT exclusion, ALIGNED axis-tolerance).
- A4. **`core/loop_extractor.py`**: the existing `trace_commutation_loop` returns the ordered component list (`[C_BUS⁺, Q1, C_BUS⁻, Q2]`) — the source of truth for which positions enter the loop-area bounding rectangle.
- A5. **`validation/drc_runner.py`**: the real-acceptance gate (per umbrella F4); this workstream's incoming-KiCad-DRC-zero-violations fence.

---

## Key Flows

- F0. **U0b extended spike — 8/8 + rotation feasibility (gates everything)**
  - **Trigger:** Doc 2 start — before F1 / F2 / F3 of this workstream AND before Doc 1's R1 (JAX-retirement deletion) per the brainstorm "spike first, then parallel" decision.
  - **Actors:** A1, A4
  - **Steps:** Extend the U0 spike script to a U0b variant that adds (a) replacement of `_encode_loop_area` with the hard AABB ceiling (`max_area_mm2=500`, tol=0), (b) the three new handlers (ANCHORED, KEEPOUT, ALIGNED), and (c) the `IntVar rot_ref ∈ {0,1,2,3}` per non-polarized component with `AddElement`-dispatched `x_size`/`y_size`. Solve feasibility-only on the temper board against the full 8/8 + rotation model; record wall time and audit pass rate.
  - **Pre-registration:** **PASS** if FEASIBLE with zero audit violations on the temper board within 600s wall (6× the U0 budget, accounting for rotation's variable-space inflation). **FAIL** if INFEASIBLE, UNKNOWN-at-timeout, or any audit violation (post-rotation geometry mismatches the encoded footprint-variant dimensions — the classic AddElement/indexing bug). A pass unblocks F1 (JAX deletion per Doc 1) and unlocks F1/F2/F3 of this workstream. A fail is itself a paradigm-level finding — the spike stops the deletion; the structural argument is then in tension with empirical infeasibility, which the team must reconcile.
  - **Outcome:** A recorded `(status, wall_time, audit_pass)` triple gating the rest of this workstream AND Doc 1's R1.
  - **Covered by:** R1, R2, R3, R5 (gating instantiations)

- F1. **Hard loop-area ceiling**
  - **Trigger:** U0b passes.
  - **Actors:** A1, A4
  - **Steps:** Resolve loop component refs via `loop_extractor.trace_commutation_loop(netlist, switch_high, switch_low)` — verified signature is `(netlist, switch_high, switch_low) → Loop | None` (per doc-review round-2 #20), not `loop_name → ordered list`. The encoder uses the returned `Loop.components` field (or whatever ordered-ref-list attribute the `Loop` namedtuple exposes — verified at planning time) to construct the axis-aligned bounding rectangle of those placements as CP-SAT IntVars (`loop_x_min`, `loop_x_max`, `loop_y_min`, `loop_y_max`); add the hard linear constraint `(loop_x_max − loop_x_min) × (loop_y_max − loop_y_min) ≤ max_area_mm2_units`. The tolerance is strict (tol=0). The existing soft wirelength-sum handler is removed from the objective — loop-pair wirelength no longer enters `Minimize` at all.
  - **Outcome:** Either the placement satisfies the 500mm² ceiling as a feasibility constraint, or the solver returns UNSAT with the derated-IGBT-overvoltage rationale surfaced in the `because` field.
  - **Covered by:** R1, R5

- F2. **New ANCHORED / KEEPOUT / ALIGNED handlers**
  - **Trigger:** Parallel with F1 (independent handlers, no shared state).
  - **Actors:** A1, A3
  - **Steps:** Add three type handlers following the existing `_encode_separated` / `_encode_enclosing` / `_encode_on_side` dispatch pattern: (a) `_encode_anchored` fixes a single component at an exact position (zero-size `IntVar` domain `[pos_units, pos_units]`); (b) `_encode_keepout` adds `NoOverlap2D` intervals between component placements and the keepout rectangle, using the existing `AddNoOverlap2D` global propagator over a union of component-intervals and keepout-intervals; (c) `_encode_aligned` adds a tolerance-band equality constraint between component centers along one axis (`|cx_a − cx_b| ≤ tol_units`). Add three matching audit checks verifying the placement satisfies each encoded constraint.
  - **Outcome:** `TYPE_HANDLERS` covers 7 of 8 constraint types (8 of 8 after loop-area reclassification); `UNSUPPORTED_TYPES` is empty (or contains only intentionally-deferred future types).
  - **Covered by:** R2

- F3. **Discrete rotation for all non-polarized parts**
  - **Trigger:** After F2 — rotation interacts with all footprint-dependent constraint encodings (clearance, region membership, adjacency bounding box).
  - **Actors:** A2, A1, A3
  - **Steps:** Add a 4-valued `IntVar` `rot_ref ∈ {0, 1, 2, 3}` per rotatable component (default 0); polarized components (electrolytic capacitors, diodes with polarity markers, ICs with pin-1 indicated in the footprint) are fixed at `rot=0`. Replace the existing static `x_size` / `y_size` per component with footprint-variant sizing: `x_size_ref` and `y_size_ref` become `IntVar`s selected via `AddElement(rot_ref, [w_0, w_90, w_w_180, w_270])` (90°/270° swap width↔height; 0°/180° preserve). All existing `add_chebyshev_clearance`, `add_region_membership`, `add_proximity`, and the new loop-area-bounding-rectangle constructions must read the post-rotation sizes. Anchor-side `OnSide` constraints become orientation-aware (a connector on the left edge must present its `edge=flush` side *after* rotation).
  - **Outcome:** CP-SAT chooses rotation for each rotatable component as a true discrete variable; no softmax, no logit, no vanishing gradient. This is what JAX could not do.
  - **Covered by:** R3

- F4. **Audit-side completion + real-DRC gate**
  - **Trigger:** After F1+F2+F3 (audit must verify the new encoded constraints).
  - **Actors:** A3, A5
  - **Steps:** Add the three new audit checks (ANCHORED region membership, KEEPOUT exclusion, ALIGNED axis-tolerance) and the loop-area-ceiling audit. Distinguish audit's *geometric* satisfaction from KiCad DRC's *electric-rule* satisfaction — audit verifies the CP-SAT model's invariants; DRC verifies physical reality. Fix one shape-vs-spec drift edge as the decisive result warrants: KiCad DRC at the real 6mm design rules must return zero violations on the temper board.
  - **Outcome:** Audit ≥ X/X checks pass AND KiCad DRC zero violations — the two-tier acceptance gate from the umbrella (fast inner gate + truth gate).
  - **Covered by:** R4, R5

---

## Requirements

**[Hard loop-area replacement (R1)]**
- R1. The existing `_encode_loop_area` soft weighted-sum objective term is **removed**. The new handler encodes loop area as a **hard feasibility constraint**: the axis-aligned bounding rectangle of all loop-component placements (resolved via `loop_extractor.trace_commutation_loop`) satisfies `width_units × height_units ≤ max_area_mm2_units`. Tolerance is `tol=0` per the L_loop derivation's "no close-enough when IGBT overvoltage is at stake." No objective-term contribution for loop area. Handler uses `OnlyEnforceIf` on its assumption Boolean for UNSAT-core extraction, mirroring the encoded assumption pattern.

**[New type handlers (R2)]**
- R2. Three handlers added to `TYPE_HANDLERS`, removed from `UNSUPPORTED_TYPES`:
  - **`_encode_anchored`** — single-component exact-position fix; domains collapse to singletons.
  - **`_encode_keepout`** — components must not overlap the keepout rectangle; encoded by adding the keepout rectangle as an additional interval in the global `AddNoOverlap2D` call (preferred over per-component disjunctives — `NoOverlap2D`'s global propagator is more efficient and the pattern is the documented OR-Tools idiom for axis-aligned keepouts).
  - **`_encode_aligned`** — set of components pairwise within `tolerance_mm` along the specified axis; O(n²) linear inequality pairs over component centers, n is small in the expected case.
- Each new handler creates the assumption Boolean consumed by U7's UNSAT-core extraction and follows the existing handler signature (`constraint, components, model, ctx, board, netlist`).
- `UNSUPPORTED_TYPES` becomes **empty** (or — only if a future constraint type is added before this workstream lands — contains only that future type). The "5/8 supported, 3 logged as warnings" state ends.

**[Discrete rotation as a model-level construct (R3)]**
- R3. Every non-polarized component carries a 4-valued `IntVar rot_ref ∈ {0, 1, 2, 3}` representing 0°/90°/180°/270° rotation. Polarized components have a derived `is_polarized=True` flag set from the footprint (capacitor polarity marker, diode cathode line, IC pin-1 indicator in `pcb_spec.yaml` or the footprint library) and are pinned to `rot_ref=0` via `model.Add(rot_ref == 0)`. Per-component `x_size` and `y_size` consumed by all side-constraint helpers become `IntVar`s derived from `rot_ref` via `AddElement` (one direction fits the F3 description; the alternative of `OnlyEnforceIf` per rotation choice is acceptable if `AddElement`'s indexing semantics complicate the global propagator interactions). The static-sizing version of `add_chebyshev_clearance`, `add_region_membership`, `add_proximity`, and the F1 loop-area bounding rectangle all migrate to read the post-rotation `x_size`/`y_size` IntVars. Same for the wirelength objective's center-to-center computation.
- The polarized-component detection must not depend on a manually-maintained list — the doc states the source (footprint library / `pcb_spec.yaml`), and a per-footprint audit verifies each could be correctly classified. Misclassifying a polarized part as rotatable would silently corrupt the circuit; the test surface must include a polarized-part-flipped-orientation failure case.

**[Two-tier acceptance gate (R4)]**
- R4. **Two-tier gate composition is uniform across all per-workstream docs (per doc-review #15) — the inner gate is `CP-SAT audit + physics oracle`; the truth gate is `validation/drc_runner.run_drc()` against real 6mm KiCad DRC.** Per `2026-07-05-acceptance-gate-real-drc-and-unsat-ux-requirements.md` (Doc 4)'s R1 definition: audit verifies CP-SAT-invariant satisfaction (geometric check of the constraints the solver was *supposed* to enforce — catches encoder bugs); DRC verifies physical-rule satisfaction (the actual 6mm creepage rules — catches model-vs-reality drift, e.g. Chebyshev-vs-Euclidean safety-factor gaps). All six audit checks must pass after every solve on the temper board (652/652 today → N/N with the new ANCHORED / KEEPOUT / ALIGNED / loop-area-ceiling checks added). KiCad DRC must return zero violations on the temper board. The inner gate runs per-solve (cheap); the truth gate runs on accepted placements only — the gate composition matches Doc 4's R1 exactly, no per-doc variation.

**[Decisive result (R5)]**
- R5. The decisive result for this workstream, blocking the F3 place→route workstream's start, is: **the temper board places with all 8 PCL constraint types honored AND with non-polarized parts rotated AND passes real KiCad DRC at 6mm with zero violations.** The wirelength is whatever CP-SAT finds within its objective budget — the decisive result is feasibility + DRC clean + 8/8 constraint types, not "minimal wirelength." Per the umbrella's Decisive-Result-Discipline, this is non-negotiable: a workstream doc that omits this single sentence is rejected at review.

---

## Acceptance Examples

- AE1. **Covers R1, R5.** Given `configs/pcl/temper_induction.yaml` declaring `loop_area` with `max_area_mm2=500` and `loop_extractor.trace_commutation_loop` returning `[C_BUS⁺, Q1, C_BUS⁻, Q2]`, when CP-SAT solves, the axis-aligned bounding rectangle of those four placements has area ≤ 500mm² — verified by audit AND by manual geometric read-back of the placement output. No "loop wirelength" term appears in the CP-SAT `Minimize` objective.
- AE2. **Covers R2.** Given PCL declarations for all 8 ConstraintType values, when the encoder dispatches, `TYPE_HANDLERS` returns a callable for every type and `UNSUPPORTED_TYPES` is empty — no "not supported by CP-SAT v1 encoder" warning logs for any board-relevant constraint.
- AE3. **Covers R3.** Given the temper board with a non-polarized part at placement output `(x, y, rot=2)`, reading its footprint rotated by 180° produces a bounding box matching the `x_size` / `y_size` IntVar values used during solving. A polarized part placed at `rot=0` only — verified by asserting `rot_ref == 0` for the polarized class in tests.
- AE4. **Covers R3, R5.** Given a polarized electrolytic capacitor K_5 misclassified as rotatable, the test suite fails the polarized-flipped-orientation scenario (a polarized part rotated to 90° would connect its cathode to a non-cathode net) — the assertion is on the rotation-variable classification, not on placement geometry.
- AE5. **Covers R4.** Given the solved temper placement, the audit (with six check types including the new ANCHORED / KEEPOUT / ALIGNED / loop-area-ceiling checks) passes ≥ X/X, AND `validation/drc_runner.py` invoked with the real 6mm design rules returns zero violations on the same placement.
- AE6. **Covers R1, R5, R4.** Given an artificially-tightened loop constraint (`max_area_mm2=10` — below any feasible solution on the temper board's geometry), CP-SAT returns UNSAT, the unsat-core names loop_area as the conflicting constraint, and the surfaced `because` field cites the L_loop derivation's derated-IGBT-overvoltage rationale (per the existing `commutation.yaml` because field — or its updated value if the doc recommends a revision in the implementation phase).

---

## Success Criteria

- *Temper board places with 8/8 constraint types honored AND non-polarized parts rotated AND real KiCad DRC at 6mm returns zero violations* — the single decisive result, blocking the routing workstream.
- `_encode_loop_area` ceases to be a soft weighted-sum objective term — it is now a hard feasibility constraint with tol=0 per physics.
- CP-SAT's rotation is a true discrete variable: 4-valued `IntVar`, no softmax, no continuous relaxation. The JAX softmax-rotation bug class is gone.
- The fast-inner-gate vs truth-gate distinction (audit vs KiCad DRC) is operational — audit catches encoder bugs, DRC catches model-vs-reality drift, both run on every acceptance.
- A downstream planner can implement this without inventing product behavior; per the umbrella's discipline, the per-workstream doc carries the decisive result sentence (R5) verbatim.

---

## Scope Boundaries

- **Continuous-angle rotation** — out of scope; only the four discrete angles 0/90/180/270 are supported, faithfully to the footprint-rotation support EDA tools actually consume. Free-angle rotation enters the model only if footprints become polygon-aware, which is outside this workstream.
- **Soft-routed loop-area minimization inside the objective chain** — out of scope by the Objective-Discipline Contract; loop area enters the encoder **only** as a hard ceiling. There is no lexicographic-tier fallback; the L_loop derivation gives an absolute target, and the contract's path (1) is the only applicable path.
- **Cross-objective weighted-sum tradeoffs (loop vs wirelength, thermal residual vs spread)** — out of scope per the umbrella's Objective-Discipline Contract. The wirelength stays sole soft primary objective; spread stays the dominated ε-sum tiebreaker with the faithful-lex inequality enforced; loop area is hard; thermal is hard (already); no new soft terms enter.
- **Manually maintained polarized-part list** — out of scope; the polarized classification must derive from a footprint / spec source so it doesn't drift as footprints are added.
- **Place→route feedback loop construction** — out of scope; this workstream *enables* the Place→Route Loop workstream (`docs/brainstorms/2026-07-05-place-route-loop-feedback-as-constraint-requirements.md`) by making CP-SAT placement constraint-complete, but the place↔route seam construction lives in the place→route per-workstream doc.
- **`validation/drc_runner.py` integration surface (CLI vs library call vs sub-process)** — out of scope for this doc; the Acceptance Gate + UNSAT UX workstream (`docs/brainstorms/2026-07-05-acceptance-gate-real-drc-and-unsat-ux-requirements.md`) handles it. This doc binds the *bar* (zero violations at 6mm) but not the integration mechanism.
- **Other boards in the 5-board regression corpus** — out of scope for the decisive result, which is temper-specific per R5. The encoder handlers are general; whether they generalize cleanly to rp2040/bitaxe/piantor is a stretch property of the encoder, not a gating criterion for this workstream.

---

## Key Decisions

- **Loop area is a hard ceiling (tol=0), not a lex-opt level** — per the L_loop derivation (`docs/solutions/best-practices/commutation-loop-area-physics-derivation-2026-07-04.md`): the failure mode is IGBT overvoltage destruction above 635mm², and the 500mm² constraint sits at 79% of that hard physics limit with 21% parasitic margin. Path (1) of the Objective-Discipline Contract; lex-opt collapses entirely for loop area. The existing `_encode_loop_area` soft wirelength-sum handler is the *forbidden* pattern and is replaced, not extended.
- **All non-polarized parts get the 4-way rotation enumeration** — the brainstorm's selected option. Maximalist vs. selective-per-annotation was the choice; maximalist wins on the grounds that this is the strict upgrade over the JAX softmax bug and CP-SAT handles 4-way enumeration natively and correctly. The model-size cost is accepted; if it proves too high during implementation, a stretch goal allows selective rotation by class (e.g. "two-pad passives" rotatable by default, "multi-pad ICs" rotatable unless flagged) as an optimization, but **the default is every non-polarized part**.
- **Loop-area bounding rectangle, not pin-loop closure** — the F1 flow uses the *axis-aligned bounding rectangle* of the loop components. A more faithful encoding would close the loop pin-to-pin (`loop_extractor` returns the ordered component list; pin-level closure is a downstream refinement). The bounding rectangle is the conservative over-estimate and is the v1 form. If the bounding-rectangle area is too coarse (over-constrains), pin-aware loop closure is a follow-up, not in this workstream.
- **Loop components resolved at encode-time, not solve-time** — `loop_extractor.trace_commutation_loop(netlist, high_switch, low_switch)` runs once to produce the ordered ref list; the encoder uses that fixed list. Cannot hot-swap the loop if the placement would prefer a different high/low switch assignment — that's out of scope.
- **Polarized detection from footprint library, not from PCL** — the per-part polarized flag derives from `pcb_spec.yaml` or equivalent footprint metadata, not from a PCL annotation, so the classification stays correct as PCL configs vary per board.
- **Audit and KiCad DRC play distinct gates, run together** — the audit is the inner gate (geometric invariants; fast; per-solve); DRC is the truth gate (real KiCad rules; slower; per-acceptance). Both must pass.

---

## Dependencies / Assumptions

- **Hard prerequisite: PR #121 merged.** All "existing infrastructure" claims in this doc — the existing `_encode_loop_area` handler at `encoder.py:224`, the 652/652 audit-pass baseline, the `score_placement()` entry point — resolve against the post-#121 state, not main. (Round-2 doc-reviewers scanned main and reported these as missing; verifying against the worktree returns them at the cited locations.) This line is the explicit prerequisite contract the docs previously embedded only implicitly.
- **L_loop derivation completed and accepted** — verified in `docs/solutions/best-practices/commutation-loop-area-physics-derivation-2026-07-04.md` (2026-07-04): 500mm² = 79% of the 635mm² hard physical ceiling; the constraint is path (1) of the umbrella's Objective-Discipline Contract. *Resolve-Before-Planning blocker from the umbrella — CLEAR.*
- **`loop_extractor.trace_commutation_loop` returns the ordered `[C_BUS⁺, Q1, C_BUS⁻, Q2]` list reliably for the temper board** — verified at `packages/temper-placer/src/temper_placer/core/loop_extractor.py:268-321`; returns `Loop` namedtuple or `None` on failure. The encoder must handle the `None` case (log + skip constraint; does not raise — equivalent to a board with no detectable commutation loop, which is a degenerate case worth surfacing in audit but not blocking).
- **Polarized-part metadata is available** in `pcb_spec.yaml` or the footprint library — *unverified assumption*. If absent, the workstream's first implementation step is to derive it from footprint polarity markers (capacitor `+` pin, diode cathode, IC pin-1 dot). The doc names this as a Deferred-to-Planning technical question; it is the existence of the metadata, not its content, that's blocking if it doesn't exist.
- **`validation/drc_runner.py` exists and consumes a placed PCB** — verified during the umbrella's research scan; F4 works the integration surface. This workstream's R4 binds only the bar (zero violations at 6mm), not the integration mechanism.
- **The existing `add_chebyshev_clearance`, `add_region_membership`, `add_proximity`, and `add_edge_anchoring` helpers can be migrated to consume post-rotation `IntVar` sizes** — high-confidence, but the migration is non-trivial: every static `x_size[ref]` reference becomes `x_size_var[ref]` selected via `AddElement`. Any helper that hardcodes static sizes (e.g. `model.AddNoOverlap2D` interval construction) must read the post-rotation dimensions. *Verify before claiming the workstream is complete.*
- **Existing test fixtures still produce detectable commutation loops after rotation is enabled** — adding rotation variables *must not* break the existing 26 encoder tests / 33 audit tests. If fixtures need updating to provide rotation variables, that's expected and within scope.
- **BMC exhaustive-enumeration infrastructure (`router_v6/bmc.py`, `esl.py`) generalizes to rotation-augmented encodings** — unverified that the BMC enumeration over `rot_ref` stays tractable. Rotation expands the assignment-space by 4^(non-polarized-parts); with ~30 rotatable parts on the temper board that's ~10¹⁸ — BMC exhaustive can't cover this and the test strategy must use property-based sampling instead of exhaustive enumeration for rotation cases. *Explicit assumption the doc surfaces, not a silent default.*

---

## Outstanding Questions

### Resolve Before Planning

- [Affects R3][Needs research] **Polarized-part metadata availability spike** (per doc-review P0 #3): verify the footprint library / `pcb_spec.yaml` exposes per-component polarization markers (capacitor `+` pin, diode cathode, IC pin-1 indicator) for the temper board's parts. A rotated polarized part connects cathode to non-cathode net → a physically-unbuildable board undetectable by audit (audit checks geometry, not electrical) AND not caught by KiCad DRC (DRC checks clearance, not pin-polarity). *If polarization metadata is absent or unreliable*, the maximalist-rotation decision (per the brainstorm) must fall back to selective-per-class rotation or R3's handler must add a strict-default-lock + opt-in-rotation-via-flag. Resolve before planning the F3 rotation implementation; pair with the U0b spike (per F0's coverage) so that the spike catches any polarity-marker regression exposed by generating polarized-part fixtures with realistic footprint metadata.

### Deferred to Planning

- [Affects R3][Technical] Footprint metadata source for polarized classification (`pcb_spec.yaml` field vs footprint library parse vs separately-maintained YAML): the *existence* is the assumption; the *source* is this planning question.
- [Affects R3][Technical] `AddElement` vs `OnlyEnforceIf`-per-rotation-choice for the post-rotation size `IntVar`: `AddElement` is cleaner OR-Tools but interacts with `AddNoOverlap2D`'s global propagator in ways the planning agent should spike on a small fixture. The alternative is four BoolVars (one per rotation) with pairwise `exactly_one` and `OnlyEnforceIf` per static-size branch — heavier bookkeeping but stays closer to the existing helper signatures.
- [Affects R3][Technical] Test strategy for the ~10¹⁸ rotation-assignment space: BMC exhaustive is infeasible; property-based testing on `GeneratedCondition × random_rot_ref_assignment → audit pass` is the proposed approach. Planning agent selects the framework integration (Hypothesis patches are already in `tests/conftest.py`).
- [Affects R4][Technical] The placement→DRC integration wrapper (CLI shell-out vs library import) — F4 of the umbrella owns this, but the constraint-completion workstream's tests consume it. Decide together with the acceptance-gate workstream doc, not in isolation.
- [Affects R1][Technical] Whether the loop-area bounding rectangle should account for component-body clearance or only the copper footprint — the L_loop derivation treats it as the inductance loop's geometric area; copper vs body changes the ceiled quantity by footprint-margin quantities. Conservative default: copper footprint; refine if the 21% parasitic margin proves insufficient.
- [Affects R1][Needs research] Whether the existing `commutation.yaml` `because` field should be updated to reflect the L_loop derivation: it currently says "Commutation loop EMI scales with area. 500mm² max for acceptable EMI at 25kHz switching frequency." — the derivation shows the true failure mode is IGBT overvoltage destruction, not EMI (EMI is a secondary consequence of the same inductance). The derivation doc already recommends this revision (line 155); the encoder consumes whichever `because` text is present per the unsat-core, but the PCL `because` should reflect the actual physics.