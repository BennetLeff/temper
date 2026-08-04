---
title: Fab-Rule Oracle - Plan
type: feat
date: 2026-08-02
topic: fab-rule-oracle
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R15)
---

# Fab-Rule Oracle - Plan

## Goal Capsule

**Objective:** layer the manufacturing ruleset (annular ring, solder mask, edge clearance) as a second oracle on top of electrical DRC, so the board's fab-readiness is measured against fab rules, not only electrical rules.

**Product authority:** temper-placer and board maintainer (single-maintainer project).

**Open blockers:** none.

---

## Product Contract

### Summary

The board currently receives one DRC verdict from electrical rules. The fab-rule oracle adds a second, independent verdict from the fab house's manufacturing ruleset. Fab-readiness becomes a measured comparison against a fab baseline, not an assumption.

### Problem Frame

Electrical DRC catches shorts, clearance, and creepage. It does not enforce the fab house's manufacturing capabilities. The existing manufacturing check (`validation/manufacturing.py::check_worst_case_drc`) is a placeholder that returns a trivial pass with zero checks. A board can be electrically clean and unmanufacturable, and today nothing measures that. The incident class: fab-readiness is asserted in prose and never measured.

### Requirements

- R15. **Fab-rule oracle** (Oracle / Board / P2): the manufacturing ruleset (annular ring, solder mask, edge clearance) is layered as a second oracle on top of electrical DRC — fab-readiness is measured against fab rules, not only electrical rules. (verbatim from origin)
  - Success signal: the board's fab-readiness verdict comes from a fab-rule violation set that is distinct from the electrical DRC set — annular ring, solder mask, and edge clearance each have a measured count and a comparison result.

### Key Technical Decisions

- KTD1. **Measure from parsed board geometry, not a second kicad-cli DRC pass** — fab thresholds differ from the board's own design rules, and a single kicad-cli run cannot vary them; the oracle computes each fab rule from the parsed board model (`io/kicad_parser.py::parse_kicad_pcb_v6`).
- KTD2. **The fab ruleset is data, not code** — `core/manufacturing.py::FabPreset` gains the fab-rule fields and `power_pcb_dataset/fab_rules.yaml` holds the board's fab contract; fab capabilities are per-vendor and change, and data keeps the oracle re-runnable.
- KTD3. **The fab verdict is a ceiling comparison against a measured baseline** — `power_pcb_dataset/fab_ceiling.json` records the baseline and adopts the measurement-provenance contract, mirroring the DRC ceiling pattern; a violation count without a baseline is not a measurement.
- KTD4. **The gate starts warn-gated (P2), but the oracle always measures** — the `check_refdes_identity_stability.py` precedent: prove bite before hardening a gate to merge-blocking.

### Assumptions

- Annular ring, solder mask, and edge clearance are computable from geometry exposed by `parse_kicad_pcb_v6` (pad sizes, drill sizes, track and zone copper, Edge.Cuts outline); if a needed geometry is not exposed, extending the parser is in-scope for U2.
- `FabPreset` lacks annular-ring and solder-mask fields today; the plan adds them with defaults from common fab capability, overridable per preset.
- The origin doc names no seed for R15; the plan anchors on `validation/manufacturing.py` (the placeholder) and `core/manufacturing.py` (FabPreset), which is the existing fab machinery.

---

## Implementation Units

### U1. Fab ruleset data model

**Goal:** FabPreset and a fab ruleset file carry the full fab-rule set (annular ring minimum, solder mask expansion and registration, edge clearance minimum) with validation that every required field is present.

**Requirements:** R15.

**Dependencies:** none.

**Files:** `packages/temper-placer/src/temper_placer/core/manufacturing.py`, `power_pcb_dataset/fab_rules.yaml` (new), `packages/temper-placer/tests/core/test_manufacturing.py` (extend).

**Approach:** Extend FabPreset with the fab-rule fields and keep the existing presets. Add `fab_rules.yaml` as the board's fab contract with named per-rule thresholds. Add a loader that validates required fields and rejects unknown rules.

**Patterns to follow:** the dataclass preset convention in `core/manufacturing.py`; config loading conventions in `io/config_loader.py`.

**Test scenarios:**
1. A FabPreset with all fab-rule fields set loads and reports the expected threshold for each rule.
2. A ruleset missing a required field (no annular-ring minimum) fails validation with the field named.
3. Each existing preset (jlcpcb_standard, jlcpcb_hdi, oshpark) resolves every fab rule to a finite positive value.
4. An unknown rule name in `fab_rules.yaml` is rejected rather than silently ignored.

**Verification:** the unit tests pass and the loader is exercised by the coverage gate (new public functions have tests, so no `.coverage-allowlist` additions).

### U2. Fab-rule measurement engine

**Goal:** a new fab oracle module computes annular ring, solder mask expansion, and edge clearance from the parsed board model and emits a per-rule violation set with margins.

**Requirements:** R15.

**Dependencies:** U1.

**Files:** `packages/temper-placer/src/temper_placer/validation/fab_oracle.py` (new), `packages/temper-placer/src/temper_placer/validation/manufacturing.py` (replace the placeholder), `packages/temper-placer/tests/validation/test_fab_oracle.py` (new).

**Approach:** For each rule, compute the nominal value from the parsed board (`parse_kicad_pcb_v6`) and compare it against the fab ruleset threshold, producing MarginReport-style findings (reuse the MarginReport dataclass shape). Annular ring derives from pad and drill geometry per footprint. Solder mask derives from mask openings against pad geometry. Edge clearance derives from copper items to the Edge.Cuts outline. The placeholder `check_worst_case_drc` either delegates to the engine or is removed.

**Patterns to follow:** the MarginReport and ManufacturingReport shapes in `validation/manufacturing.py`; `_drc_api.py`'s DrcResult conventions; `validation/drc_oracle.py`'s oracle-returns-report shape.

**Test scenarios:**
1. A synthetic board with an annular ring below the fab minimum yields one violation naming the pad and the measured vs required values.
2. A synthetic board with a mask opening that does not cover its pad yields a solder-mask violation.
3. A synthetic board with copper inside the fab edge clearance yields an edge-clearance violation naming the copper item.
4. A synthetic board that satisfies every fab rule yields zero violations and a pass rate of 1.0.
5. An SMD pad with no drill is exempt from the annular-ring rule and never produces one.
6. The engine reports the same violation count on two runs over a byte-identical board (determinism).

**Verification:** the unit tests pass; the engine is exercised against `pcb/temper.kicad_pcb` and produces a parseable report.

### U3. Fab baseline record

**Goal:** the first real measurement of `pcb/temper.kicad_pcb` against the fab ruleset is recorded as a baseline with provenance, so later runs have something to compare against.

**Requirements:** R15.

**Dependencies:** U2.

**Files:** `power_pcb_dataset/fab_ceiling.json` (new), `scripts/check_measurement_provenance.py` (register the artifact), `docs/evidence/2026-08-02-fab-oracle-baseline.md` (new).

**Approach:** Run the U2 engine over the committed board. Record per-rule counts and ceilings in `fab_ceiling.json` following the `drc_ceiling.json` shape (per-rule counts, provenance block, `_march` log). Register the artifact in `MEASURED_ARTIFACTS` so board staleness is caught by the existing provenance gate. Record the input hash of `pcb/temper.kicad_pcb` and `fab_rules.yaml`.

**Patterns to follow:** the shape and `_march` conventions of `power_pcb_dataset/drc_ceiling.json`; the artifact registry in `scripts/check_measurement_provenance.py`.

**Test scenarios:**
1. The registered `fab_ceiling.json` parses and its provenance block passes the existing measurement-provenance gate while `pcb/temper.kicad_pcb` is unchanged.
2. After the board content changes without a re-measurement, the provenance gate reports the fab baseline STALE (same behavior as the DRC ceiling).
3. The baseline's per-rule counts match the U2 engine's output on the same board content.

**Verification:** the provenance gate passes on the baseline PR and reports STALE on a simulated board change.

### U4. Fab oracle gate and bite proof

**Goal:** a CI gate reports the fab-rule verdict, fails above the recorded ceilings, and is proven to bite on each fab-rule class.

**Requirements:** R15.

**Dependencies:** U3.

**Files:** `scripts/check_fab_oracle.py` (new), `scripts/manifest.yaml` (entry), `packages/temper-placer/tests/validation/test_fab_oracle_gate.py` (new).

**Approach:** Add a check script that runs the engine, compares against the baseline ceilings, and fails on any ceiling exceedance. Wire it into the board gates workflow. Add probe tests that mutate a synthetic board copy to violate each fab rule and assert the gate fails on that class (anti-vacuity: the clean board must pass).

**Patterns to follow:** the CLI shape and fail-closed exit codes of `scripts/check_drc_ceiling_approval.py`; the anti-vacuity discipline of `scripts/check_vacuous_gates.py`; the `scripts/manifest.yaml` entry convention.

**Test scenarios:**
1. A board copy with one annular-ring violation below the minimum fails the gate with the rule named.
2. A board copy with one solder-mask violation fails the gate with the rule named.
3. A board copy with one edge-clearance violation fails the gate with the rule named.
4. The clean committed board passes the gate at the recorded baseline.
5. A missing `fab_rules.yaml` or missing baseline fails closed with a GATE ERROR, never a clean pass.

**Verification:** the gate passes on the clean board, fails on each injected violation class, and the script has a `scripts/manifest.yaml` entry.

---

## Verification Contract

- `uv run pytest packages/temper-placer/tests/core/test_manufacturing.py packages/temper-placer/tests/validation/test_fab_oracle.py packages/temper-placer/tests/validation/test_fab_oracle_gate.py` passes.
- `uv run python scripts/check_fab_oracle.py` passes on `pcb/temper.kicad_pcb` at the recorded baseline.
- `uv run python scripts/check_measurement_provenance.py` passes with `fab_ceiling.json` registered.
- `uv run python scripts/import_linter_gate.py` passes.
- No new zero-coverage public functions in `temper_placer/` (new fab code is exercised by tests).

---

## Definition of Done

- The fab-readiness verdict comes from the fab oracle, not from prose.
- Annular ring, solder mask, and edge clearance each have a measured count and a baseline ceiling.
- The gate bites on each fab-rule violation class (probe tests pass).
- Every new script has a `scripts/manifest.yaml` entry.
- Dead-end or experimental code from implementation is removed from the diff.

---

## Scope Boundaries

- Electrical DRC stays the authority for shorts, clearance, and creepage; the fab oracle does not duplicate it.
- The fab oracle does not change `pcb/temper.kicad_pcb` and does not trigger the DRC ceiling re-measurement convention.

### Deferred to Follow-Up Work

- Extending the fab oracle to additional rules (silk-to-pad, hole-to-edge, impedance classes) — new rules join `fab_rules.yaml` and the baseline later.
- Applying the R27 monotone-ceiling contract to `fab_ceiling.json` raises — once R27's checked contract lands, `fab_ceiling.json` adopts it.
- Hardening the fab gate to merge-blocking — pending bite-proven history (KTD4).

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` (R15)
- `packages/temper-placer/src/temper_placer/validation/manufacturing.py` (placeholder oracle)
- `packages/temper-placer/src/temper_placer/core/manufacturing.py` (FabPreset)
- `packages/temper-placer/src/temper_placer/io/kicad_parser.py` (parse_kicad_pcb_v6)
- `power_pcb_dataset/drc_ceiling.json` (ceiling and provenance shape)
- `scripts/check_measurement_provenance.py` (artifact registry)
