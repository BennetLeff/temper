---
date: 2026-06-30
topic: 4-layer-enforcement
---

# 4-Layer Board Enforcement

## Summary

Remove the 2-layer production path from the placer, enforce the canonical 4-layer stackup (F.Cu / In1.Cu / In2.Cu / B.Cu) at every pipeline boundary, catch layer-count deviations through property tests and a CI gate, and add professional PCB stackup validation checks so the 4-layer design is not just present but rigorous.

---

## Problem Frame

The Temper board is specified as a 4-layer design with inner ground and power planes. The placer and its surrounding infrastructure fully support 4-layer boards, and `default_4layer()` is the canonical factory used everywhere. However, a `default_2layer()` factory method also exists, producing a valid `LayerStackup` with only F.Cu and B.Cu — no planes, no inner layers. Nothing in the codebase prevents a Board from being created with a 2-layer stackup, and if one is, the generated `.kicad_pcb` file would silently contain only two copper layers rather than four.

The failure mode is the worst kind: a 2-layer board passes all existing checks but is electrically broken. Ground and power planes are simply absent. Return paths are undefined. EMI shielding is gone. Nothing warns that the board is wrong.

Separately, even when 4-layer output is correct, the stackup design has professional-quality gaps that a PCB engineer would catch before fabrication: asymmetric copper weight across the stackup (2 oz on L1, 1 oz on L2-L4), control signals on L4 referencing a power plane rather than a ground plane for high-speed return paths, and no controlled-impedance specification for the USB differential pair. These are the kinds of issues that produce boards that "look right" but fail in the field.

---

## Actors

- A1. **Developer**: Creates or modifies board definitions, runs the placer pipeline, generates KiCad output.
- A2. **Placer pipeline**: Consumes a Board specification and produces placement, routing, DRC, and KiCad file output.
- A3. **CI system**: Runs automated tests and gates on every push, verifies generated artifacts against invariants.

---

## Key Flows

- F1. **Board creation with enforced stackup**
  - **Trigger:** A Board or LayerStackup is constructed.
  - **Actors:** A1, A2
  - **Steps:** (1) Developer constructs a Board, either directly or via factory method. (2) Board validates its LayerStackup contains exactly 4 canonical layers. (3) If validation fails, construction raises immediately with a clear error message naming the missing or extra layers.
  - **Outcome:** Only a Board with the canonical 4-layer stackup exists in memory.
  - **Covered by:** R1, R2, R3

- F2. **Pipeline-to-KiCad output with layer verification**
  - **Trigger:** The placer pipeline is run to produce a `.kicad_pcb` file.
  - **Actors:** A1, A2
  - **Steps:** (1) Placer reads Board with canonical stackup. (2) Each pipeline stage validates the Board's layer count before processing. (3) KiCad writer validates the output contains exactly 4 copper layers with canonical names before writing. (4) Any mismatch aborts with a diagnostic.
  - **Outcome:** A `.kicad_pcb` file with exactly 4 copper layers matching the canonical names.
  - **Covered by:** R4, R5

- F3. **CI gate catches layer drift**
  - **Trigger:** A push or PR includes changes that affect generated PCB output.
  - **Actors:** A3
  - **Steps:** (1) CI regenerates the `.kicad_pcb` from the canonical spec. (2) CI diffs the regenerated file against the committed copy. (3) If the diff includes a change in copper layer count or layer names, CI fails with a clear report. (4) Property tests also verify that any pipeline output has exactly 4 layers.
  - **Outcome:** No commit can land that changes the board's layer count.
  - **Covered by:** R6, R7

---

## Requirements

**Priority tiers:** Must-Have (R1-R7, R12) — prevents silent wrong output and ensures warnings are surfaced. Should-Have (R9, R10) — addresses confirmed signal-integrity gaps. Could-Have (R8, R11) — prophylactic checks that do not fire against the current Temper stackup; their thresholds are deferred to planning.

### Layer enforcement at the model level

- R1. `LayerStackup` must reject creation with any number of layers other than 4. The canonical layer set is defined by the existing `STANDARD_LAYER_ORDER` (a tuple of `LayerIndex` enum members in `core/board.py`); the authoritative KiCad names are obtained via `str(layer_index)` and validated against `LAYER_NAME_TO_IDX`.
- R2. `default_2layer()` emits a deprecation warning for one release cycle, then is removed as a public production API. Existing call sites (none in production; manual test fixture only per audit) are migrated. Tests that need a 2-layer stackup use a clearly-named `_test_only_2layer()` or equivalent scoped helper.
- R3. `Board.__post_init__` validates that its `layer_stackup` matches the canonical definition (4 layers with correct names and types) and raises a descriptive error on mismatch rather than silently accepting a non-canonical stackup.

### Output and pipeline verification

- R4. The KiCad file writer validates that the output contains exactly 4 copper layers with the canonical names before writing. Writing is aborted on mismatch.
- R5. Each pipeline stage that accepts a `Board` validates the layer count against the canonical definition before processing. This catches any board-object mutation that might have occurred upstream. If Board objects are immutable in practice, per-stage validation is deferred to planning judgment (the construction-time (R3) and output-time (R4) checks provide adequate coverage).

### Tests and CI

- R6. A property test verifies that for any valid pipeline input, the generated `.kicad_pcb` contains exactly 4 copper layers with the canonical names.
- R7. A CI gate regenerates the `.kicad_pcb` from spec and diffs against the committed copy. Any diff that changes the copper layer count or layer names fails the gate. (This builds on the existing DFM layer-count invariant from the DFM property tests specification.)

### Professional stackup validation

- R8. **Copper symmetry check.** Validates that effective copper weight (nominal weight × estimated fill percentage) is balanced across the stackup, not raw copper weight. Raw 2oz on L1 with 30-40% fill is effectively similar to 1oz solid planes on L2-L3 at near-100% fill. Produces a warning only when effective imbalance exceeds a threshold suggesting real warping risk. The raw 2oz/1oz asymmetry in the Temper stackup does not trigger this — it is standard power-electronics practice where outer layers carry high current at lower fill, and inner planes are solid at lower weight.
- R9. **Return-path adjacency check (differential nets only).** For nets in the `Differential` class (USB D+/D-), each signal layer must have an adjacent reference plane. L1 references L2 (GND) — passes. L4 references L3 (PWR) — produces a warning recommending verification of return-path quality. Non-differential control signals on L4 referencing PWR are acceptable at the frequencies involved (SPI, GPIO, I2C) and do not trigger warnings.
- R10. **Controlled-impedance check.** USB differential pairs must have a documented target impedance. If no impedance specification exists, produce a warning. Typical target is 90Ω differential for USB 2.0.
- R11. **Copper balance check.** Verifies that copper density is reasonably balanced across all 4 layers. Significant imbalance (one layer near 0% fill while another is near 80% fill) produces a warning to prevent board warping during reflow. Note: R8 checks effective copper mass (nominal weight × fill) whereas R11 checks raw fill density — both guard against warping but catch different imbalance patterns.
- R12. **Stackup warning CI surface.** Stackup quality warnings (R8-R11) must be emitted as CI annotations or a structured report artifact surfaced in the PR/commit UI, not only as stdout. This ensures warnings are actually seen before fabrication rather than scrolling past unnoticed.

---

## Acceptance Examples

- AE1. **Covers R1, R3.** Given a `LayerStackup` with layers `[F.Cu, In1.Cu, In2.Cu, B.Cu]`, construction succeeds.
- AE2. **Covers R1.** Given a `LayerStackup` with only layers `[F.Cu, B.Cu]`, construction raises a `ValueError` indicating the missing inner layers.
- AE3. **Covers R2, R3.** Given a `Board` with no explicit `layer_stackup`, `__post_init__` applies `default_4layer()` and validates the canonical 4 layers — board creation succeeds.
- AE4. **Covers R4, R5.** Given a pipeline run with a valid canonical board, the KiCad writer produces a `.kicad_pcb` with exactly `(0 "F.Cu" ...) (1 "In1.Cu" ...) (2 "In2.Cu" ...) (31 "B.Cu" ...)` copper layer definitions.
- AE5. **Covers R6.** Property test fuzzes pipeline inputs; every generated `.kicad_pcb` is parsed and verified to contain exactly 4 copper layers.
- AE6. **Covers R7.** A commit that changes the `.kicad_pcb` layer count from 4 to 2 (or adds/removes a copper layer) fails CI with a diff showing the layer change.
- AE7. **Covers R8.** Given a stackup where the effective copper imbalance `(max_effective - min_effective) / total_effective` exceeds 25%, the symmetry check emits a warning: "Effective copper imbalance detected: L1 at 2oz × 95% fill vs L4 at 0.5oz × 20% fill. This may cause board warping during reflow." The current Temper stackup (L1=2oz at ~35% fill, L2-L3=1oz at ~95% fill, L4=1oz at ~30% fill) produces an imbalance of ~22.4% and passes without warning.
- AE8. **Covers R9.** Given the `Differential` net class (USB D+/D-) routed such that traces could land on L4, the adjacency check emits a warning: "L4 (control signals) references L3 (PWR plane). Verify return-path quality for differential nets. Consider adding stitching GND vias near the differential pair." Non-differential nets (SPI, GPIO, I2C) on L4 produce no warning.
- AE9. **Covers R10.** Given a `Differential` net class with no impedance specification configured, the controlled-impedance check emits a warning: "No target impedance specified for differential nets (USB D+/D-). Expected: 90Ω differential for USB 2.0."
- AE10. **Covers R11.** Given a stackup where one layer has <5% copper fill and another has >75% fill, the copper balance check emits a warning: "Copper density imbalance: L2 at 78% fill vs L4 at 3% fill. This may cause board warping during reflow." A stackup with all layers between 25–55% fill passes without warning. (Exact thresholds are deferred to planning per R11.)

---

## Success Criteria

- A developer who accidentally constructs a 2-layer Board gets a clear, immediate error — not silent wrong output.
- Any `.kicad_pcb` that enters the repo with a non-canonical layer count is blocked by CI.
- Stackup quality warnings are visible during pipeline runs so a developer can address them before sending to fabrication.
- A downstream planner can identify every enforcement point and understand what checks run where without reading implementation code.

---

## Scope Boundaries

- 6-layer extension is out of scope (confirmed by existing spec and `docs/brainstorms/2026-06-23-layer-names-consolidation-requirements.md`).
- Physical stackup redesign (changing copper weights, dielectric thicknesses, or layer assignments) is out of scope — we validate and warn but do not redesign.
- Via type extensions (blind, buried, microvia) are out of scope — the current design uses through-hole vias only, per the via spec.
- Controlled-impedance routing calculations (computing trace width from dielectric height and target impedance) are deferred to planning; R10 only checks that a specification exists.
- Removal of the `_test_only_2layer()` helper from tests is out of scope — tests may legitimately need simpler stackups for focused assertions.

---

## Key Decisions

- **Copper-weight asymmetry is a warning, not an error.** The 2oz L1 exists for HV current capacity and is part of the intentional design. Making this a hard error would block the pipeline on the current valid board. If the stackup is later redesigned for balanced copper, the check can be upgraded to error.
- **Copper symmetry compares effective weight (nominal × fill), not raw weight.** Raw 2oz on L1 at 30-40% fill is effectively similar to 1oz solid planes at near-100% fill. The raw asymmetry is misleading — effective copper mass is what causes warping.
- **Return-path adjacency check applies to differential nets only.** Low-speed control signals (SPI, GPIO, I2C) referencing a PWR plane through a 0.2mm dielectric are fine. Differential pairs (USB) are the only signals where return-path quality through a power plane warrants a warning.
- **Layer enforcement is at construction time (fail fast), not only at output time.** A board with the wrong stackup should never exist in memory. Output-time checks are a safety net, not the primary defense.
- **`_test_only_2layer()` is retained for tests.** Tests that use simplified stackups for focused assertions are legitimate. The naming convention (leading underscore + `test_only`) signals that this is not a production path.

---

## Dependencies / Assumptions

- The existing DFM property test specification (`docs/brainstorms/2026-06-25-dfm-property-tests-requirements.md`) already defines a Layer count invariant (R16) — this proposal extends and hardens that invariant rather than replacing it.
- The committed `.kicad_pcb` file (`pcb/temper.kicad_pcb`) currently defines 4 copper layers and is assumed accurate.
- The canonical layer names (F.Cu, In1.Cu, In2.Cu, B.Cu) are stable and defined by the `LayerIndex` IntEnum SSOT established in `docs/brainstorms/2026-06-23-layer-names-consolidation-requirements.md`.

---

## Outstanding Questions

### Resolve Before Planning

(All resolved — see Key Decisions.)

### Deferred to Planning

- [Affects R8] [Technical] What is the effective copper imbalance threshold (percentage) that triggers a warping-risk warning? AE7 uses 25% as an illustrative value.
- [Affects R8] [Technical] How is "estimated fill percentage" computed — pre-routing (footprint-based) or post-routing (trace-aware)? What granularity — global layer average or per-region?
- [Affects R11] [Technical] What is the acceptable copper balance threshold (percentage difference between max and min fill)?
- [Affects R10] [Needs research] What target impedance should USB D+/D- differential pairs use? USB 2.0 full-speed typically targets 90Ω differential. Verify against the actual MCU (ESP32-S3) USB specification.
- [Affects R10] [Technical] R10 checks only for existence of an impedance specification, not correctness. Should the check validate the value (e.g., 90Ω ± tolerance) or only presence?
- [Affects R9] [Technical] Should the return-path adjacency check consider plane stitching (e.g., GND vias near the differential pair) as mitigation?
- [Affects R3] [Technical] Does the placer pipeline serialize/deserialize Board objects between stages (pickle, JSON)? If so, construction-time validation may be bypassed and needs a deserialization guard.
- [Affects R5] [Technical] Are Board objects mutable mid-pipeline, or is per-stage validation redundant with construction-time (R3) and output-time (R4) checks?
- [Affects R7] [Technical] Should the CI diff gate use a semantic layer-count diff rather than a raw textual diff of the .kicad_pcb file to avoid false positives from benign KiCad version format changes?
