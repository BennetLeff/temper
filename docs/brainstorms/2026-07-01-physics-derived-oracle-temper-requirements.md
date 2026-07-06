---
date: 2026-07-01
topic: physics-derived-oracle-temper
---

# Physics-Derived Oracle for the Temper Board

## Summary

A full closed loop on the temper induction-burner board that wires the existing physics infrastructure (`pcb_spec.yaml` → `derive_constraints_from_spec` → `quality_config` → `compute_quality_report` → IPC-2221 threshold → pass/fail) end-to-end, starting with HV/LV net classification and creepage. The metric goes from dark (`return 1.0`) to live, validated three ways, with value proven by an A/B placement diff: run the placer without HV/LV classification, then with — if the placements differ, the constraint has teeth.

---

## Problem Frame

The project's quality metrics are dark exactly where the placer's value lives. Five power-electronics score functions (`thermal_score`, `zone_compliance_score`, `hv_lv_clearance_score`, `loop_area_score`, `congestion_score`) each have an early `return 1.0` when their input set is empty — and the input sets are empty because the temper board's nets are not classified as HV/LV/AC. The corpus `constraints.yaml` classifies nets as `["Signal", "Power"]` only; no net has `safety_category: "HV"`. The `ClearanceLoss` term in the placer's loss function (`losses/clearance.py`, weight `100.0`) has never constrained a single HV-LV pair because `hv_components` and `lv_components` are always empty.

The physics infrastructure to fix this exists and is unwired: `configs/pcb_spec.yaml` has the electrical spec (max junction temp, power dissipation per component, max loop area, switching frequency); `configs/pcl/temper_induction.yaml` has PCL constraints (HV_ZONE, MCU_ZONE, Q1/Q2 adjacency, gate-drive loop, IEC 60335-1 reinforced isolation); `core/ipc2221.py` has clearance tables; `core/loop_extractor.py` has commutation-loop extraction; `pipeline/derivation.py` has `derive_constraints_from_spec`. The corpus runner bypasses all of it, using the geometric-only `constraints.yaml` instead.

The consequence: every PR's regression run reports perfect thermal, zone, HV/LV clearance, loop-area, and congestion scores that have never evaluated a real constraint. A metric that can't fail is the failure mode this work removes. The oracle that works for an N=1 power board is physics — creepage ≥ IPC-2221, loop area ≤ spec, junction temp ≤ limit — not self-comparison and not cross-board benchmarking.

---

## Actors

- A1. **Maintainer (domain expert)**: classifies the temper board's nets against the schematic and verifies the classification is correct. The one human-in-the-loop step in the chain.
- A2. **Placer optimizer**: runs with the clearance loss term live (HV/LV pairs populated) and produces a placement that the physics oracle evaluates.
- A3. **CI runner**: runs the closed loop (classify → derive → place → measure → threshold → pass/fail) and reports the result.

---

## Key Flows

- F1. **Net classification (human-in-the-loop)**
  - **Trigger:** maintainer classifies the temper board's nets against the schematic.
  - **Actors:** A1
  - **Steps:**
    1. Maintainer identifies which nets in `temper.kicad_pcb` are mains HV, which are LV logic, which are gate-drive, which are AC.
    2. Classifications are written to the board's net-class definitions (in the PCB file or a config that the parser reads), using the `safety_category` system documented in CLAUDE.md §5.
    3. Maintainer verifies each classification against the schematic.
  - **Outcome:** the temper board's nets carry real `safety_category` values; `hv_components` and `lv_components` are non-empty when the parser runs.
  - **Covered by:** R1, R2

- F2. **Physics oracle (closed loop)**
  - **Trigger:** CI or maintainer runs the placer on temper with the physics infrastructure wired.
  - **Actors:** A2, A3
  - **Steps:**
    1. Load `pcb_spec.yaml` → `derive_constraints_from_spec` → constraints with zones, loops, thermal, HV/LV component sets.
    2. Run the placer with the `ClearanceLoss` term live (HV/LV pairs populated).
    3. Run `compute_quality_report` on the placer's output → produces real physics scores (not `1.0` defaults).
    4. Compare the HV/LV clearance measurement to the IPC-2221 threshold for mains-derived creepage.
    5. Report pass/fail against the threshold.
  - **Outcome:** the placer's output is evaluated against a physics-derived absolute threshold that does not reference the placer's own previous output.
  - **Covered by:** R3, R4, R5, R6, R7

- F3. **A/B placement diff (value proof)**
  - **Trigger:** maintainer runs the placer twice on temper — once without HV/LV classification, once with.
  - **Actors:** A2
  - **Steps:**
    1. Run the placer with the current (dark) clearance loss — no HV/LV pairs.
    2. Run the placer with HV/LV classification wired — clearance loss is live.
    3. Diff the two placements: did HV components move away from LV components?
  - **Outcome:** if the placements differ, the constraint has teeth. If they don't, either the geometric losses were already separating HV/LV (constraint is redundant) or the clearance loss weight is too weak (needs retuning). Both are findings.
  - **Covered by:** R8

---

## Requirements

**Net classification**

- R1. The temper board's nets are classified with `safety_category` values (`"HV"`, `"LV"`, `"AC"`, `"iso"`, or `None`) using the system documented in CLAUDE.md §5. Classifications live in the PCB file's net-class definitions or in a config the parser reads — the SSOT location is a planning decision, but the classifications must flow through `parse_kicad_pcb` → `net_class_assignments` → `comp.net_class`.
- R2. The maintainer (domain expert) verifies each net's classification against the temper schematic. This is the one human-in-the-loop validation step; it cannot be automated. The verification is recorded (e.g., a checklist or a comment block naming each classified net and its schematic justification).

**Constraint derivation and quality config population**

- R3. The corpus runner (or a new physics-oracle runner) loads `configs/pcb_spec.yaml` and calls `derive_constraints_from_spec` to produce constraints with `zone_assignments`, `critical_loops`, `thermal_constraints`, and HV/LV component sets — not the geometric-only `constraints.yaml`.
- R4. The `quality_config` passed to `compute_quality_report` is populated from the derived constraints (parallel to the existing logic in `baseline_extractor.py:218-240`): `hv_components` from `comp.net_class == "HighVoltage"`, `lv_components` from `comp.net_class == "Signal"`, `thermal_components` from `thermal_constraints`, `zone_assignments` from the derived zones, `loop_components` from `critical_loops`.

**Metric computation**

- R5. `compute_quality_report` on the temper board produces real, finite, non-`1.0` values for `hv_lv_clearance_score` (and, once the inputs are populated, `thermal_score`, `zone_compliance_score`, `loop_area_score`). A score that returns `1.0` because its input set is empty is a bug, not a pass.

**Validation: three-case**

- R6. The HV/LV clearance metric is validated three ways: (a) **Pass case** — the existing human placement in `temper.kicad_pcb` passes the IPC-2221 threshold (known-good reference). (b) **Fail case** — a deliberately-unsafe fixture (two HV/LV components placed at a distance below the IPC-2221 threshold) fails the metric. (c) **Classification check** — the maintainer confirms each net's `safety_category` matches the schematic (covered by R2). A metric that cannot fail is the bug being removed; the fail-case fixture is load-bearing.
- R7. A differential cross-check against KiCad's own DRC is planned as a follow-on validation (not in the first slice). The metric's HV/LV clearance measurement is compared to KiCad's DRC clearance violations on the same placement. This is deferred, not skipped — it validates the metric against an independent tool once the three-case validation passes.

**Value proof: A/B placement diff**

- R8. The placer is run twice on temper — once without HV/LV classification (current state, clearance loss dark), once with (clearance loss live). The two placements are diffed. If the placements differ (HV components move away from LV components), the constraint has teeth. If they don't, the clearance loss weight (`100.0` in `constraints.yaml`) may need retuning — it was calibrated when the clearance loss was dark and may be too weak to influence the optimizer now that HV/LV pairs exist.

**Threshold**

- R9. The HV/LV clearance threshold is derived from IPC-2221 (`core/ipc2221.py`) based on the temper board's mains voltage, not inherited from the `default_hv_lv_clearance: 10.0` default in `losses/clearance.py` or the `min_hv_lv_clearance: 8.0` default in `quality.py`. The threshold is a physics-derived absolute number that does not reference the placer's own output.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R5.** Given `temper.kicad_pcb` with nets classified per R1, when `parse_kicad_pcb` runs, then `hv_components` is non-empty and `compute_quality_report` returns a `hv_lv_clearance_score` that is finite and not `1.0`.
- AE2. **Covers R6.** Given the existing human placement in `temper.kicad_pcb`, when the HV/LV clearance metric runs, then the score passes the IPC-2221 threshold (the human placement is known-good).
- AE3. **Covers R6.** Given a fixture with two components placed at 2mm when the IPC-2221 threshold is ≥ 8mm, when the HV/LV clearance metric runs, then the score fails (strictly below the pass threshold).
- AE4. **Covers R8.** Given the placer run without HV/LV classification produces placement A, and the placer run with HV/LV classification produces placement B, when the two placements are diffed, then either (a) HV components in B are farther from LV components than in A (constraint has teeth), or (b) the placements are identical (constraint weight needs retuning — recorded as a finding, not a failure).
- AE5. **Covers R9.** Given the temper board's mains voltage (230V or 120V, per the electrical spec), when the IPC-2221 threshold is derived, then the threshold is a specific mm value that does not reference `default_hv_lv_clearance` or the placer's previous output.

---

## Success Criteria

- The HV/LV clearance metric on the temper board produces a real, finite, non-`1.0` number that is traceable to a measured clearance between real HV and LV components — not a dark default.
- The metric passes on the human placement (known-good) and fails on a deliberate violation (known-bad). Both directions are proven.
- The A/B placement diff shows whether wiring the clearance loss live changes the placer's output. Either outcome is signal: placements differ (constraint has teeth) or placements are identical (weight needs retuning).
- A future planner or implementer can follow the wiring pattern established here (classify → derive → populate → measure → threshold → A/B diff) to add the next physics metric (thermal, loop area, EMI) without re-deriving the path.
- The `return 1.0` early-return pattern is no longer the default state for any physics metric on the temper board — a metric returning `1.0` because its input set is empty is treated as a bug, not a pass.

---

## Scope Boundaries

- Thermal, loop-area, and EMI metrics are deferred until HV/LV clearance proves the wiring pattern end-to-end. Each follows the same path (classify inputs → derive constraints → populate quality_config → measure → threshold) once the pattern is established.
- The human-reference corpus oracle requirements doc (`docs/brainstorms/2026-07-01-human-reference-corpus-oracle-requirements.md`) is not abandoned — it is the geometric regression floor (runs weekly via `corpus-batch.yml`), just no longer the primary signal.
- Cross-board physics thresholds are out of scope — each board has its own electrical spec; the physics oracle is inherently N=1.
- The corpus regression gate fix (R16 from the corpus-oracle doc) remains a prerequisite — the physics oracle supplements the geometric gate, it does not replace it.
- KiCad DRC differential cross-check is deferred (R7), not skipped.
- FreeRouting integration is out of scope (per prior decision).

---

## Key Decisions

- **Physics oracle over human-reference oracle as primary signal.** For an N=1 power board, creepage/loop/thermal against IPC-2221 is a real oracle that doesn't reference the placer's own output. HPWL-vs-human is a geometric proxy that can't see power-electronics correctness. The human-reference oracle stays as the regression floor; the physics oracle is the correctness signal.
- **Full closed loop (layers 1-6) over live-metric-only.** A metric that can't fail is the bug being removed. The closed loop (classify → derive → measure → threshold → A/B diff) proves the metric can pass AND fail AND change the placer's behavior. Stopping at "metric produces a number" would ship a more sophisticated `return 1.0`.
- **HV/LV clearance first, other physics metrics follow.** Clearance is the #1 safety property for a mains induction burner and the wiring pattern. Once it's proven end-to-end, thermal, loop-area, and EMI reuse the same path.
- **A/B placement diff as the defining value proof.** The strongest signal is whether wiring the constraint live changes the placer's output. If it does, the constraint has teeth. If it doesn't, the weight is too weak or the geometric losses were already separating HV/LV — both are findings worth having.
- **Net classification is the one human-in-the-loop step.** Which nets are mains HV vs. LV logic vs. gate-drive is a domain-expert decision verified against the schematic, not a measured quantity. The rest of the chain is automatic once the classification is in place.

---

## Dependencies / Assumptions

- `derive_constraints_from_spec` in `pipeline/derivation.py` produces constraints with `zone_assignments`, `critical_loops`, `thermal_constraints`, and HV/LV component sets when given `configs/pcb_spec.yaml` as input. Verify during planning; if the derivation is incomplete, the wiring path may need extension.
- `parse_kicad_pcb` populates `comp.net_class` from the PCB file's net-class definitions (or a config the parser reads). The `safety_category` field on net classes (CLAUDE.md §5) flows through to `comp.net_class` such that `comp.net_class == "HighVoltage"` is true for HV-classified components. Verify during planning.
- The temper board's schematic is available to the maintainer for net-classification verification (R2). If the schematic is not in the repo, the classification step requires external reference.
- The clearance loss weight (`100.0` in `constraints.yaml`) was calibrated when the clearance loss was dark. Once HV/LV pairs exist, the weight may need retuning — the A/B diff (R8) will reveal this.
- `core/ipc2221.py` has a function that returns a required creepage distance given a voltage and pollution degree. Verify during planning; if the function's signature or inputs don't match the temper board's mains voltage, the threshold derivation may need adaptation.
- The existing human placement in `temper.kicad_pcb` is actually safe (passes IPC-2221). If the human placement fails the threshold, either the metric is miscalibrated or the human placement has a real safety issue — both are signal, but the pass-case validation (R6a) depends on this assumption.

---

## Outstanding Questions

### Resolve Before Planning

- *None.*

### Deferred to Planning

- [Affects R1][Technical] Where do net classifications live — in the PCB file's net-class definitions (SSOT, but edits the binary source), or in a separate config the parser reads (easier to version-control, but introduces a second source of truth)? CLAUDE.md §5 describes the `safety_category` system; verify which location the parser actually reads from.
- [Affects R3][Technical] Does the corpus runner need to be modified to call `derive_constraints_from_spec`, or does a new physics-oracle runner exist alongside it? The corpus runner currently uses `constraints.yaml` (geometric-only); the physics path needs `pcb_spec.yaml` + derivation.
- [Affects R6][Technical] How is the deliberately-unsafe fixture for the fail-case produced? Reuse an existing fixture generator in `tests/fixtures/generators/`, or construct a minimal two-component fixture by hand?
- [Affects R8][Technical] How are the two placements diffed — coordinate-level (per-component position delta) or metric-level (clearance score delta)? Coordinate-level is more informative but requires a diff tool or script.
- [Affects R9][Needs research] What is the temper board's actual mains voltage (230V or 120V), and what pollution degree applies? This determines the IPC-2221 threshold. Check `pcb_spec.yaml` or the schematic.
- [Affects R9][Needs research] Does `core/ipc2221.py` expose a function that takes voltage + pollution degree and returns a required creepage distance, or does it expose a lookup table? The threshold derivation depends on the API shape.
