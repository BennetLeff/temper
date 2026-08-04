---
title: "Firmware-assumption contract oracle - Plan"
type: feat
date: 2026-08-02
topic: firmware-assumption-contract
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R18)
---

# Firmware-assumption contract oracle - Plan

## Goal Capsule

**Objective:** A machine-readable registry of firmware constants that have a board derivation, with an oracle that re-derives each constant from the actual board's components and fails the run when hardware and firmware disagree about a load-bearing value.

**Product authority:** temper firmware maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none at planning time. Execution depends on a parser for the board file's placed components (U2) being implementable against the current `pcb/temper.kicad_pcb` (Assumption A2).

---

## Product Contract

### Summary

Every firmware constant that derives from a board component is reverse-checked against the actual board, so the "hardware and firmware cannot disagree" contract is enforced by a gate, not by review. The registry starts with the two documented derivations: the PLL minimum frequency from tank capacitance, and the MAX31865 threshold words from the reference resistor.

### Problem Frame

The incident class this idea exists for: the tank capacitor staged off the board while firmware's `PLL_MIN_FREQ_HZ` assumes its 300 nF — hardware and firmware disagreed about resonance, and no gate caught it because every existing check compared declarations against declarations. A declared-vs-declared check cannot see a component that is missing from the board. The oracle re-derives from the board itself, so the off-board-component class fails at commit time.

### Requirements

- R18. Firmware-assumption contract oracle (Oracle / Firmware / P1): every firmware config constant with a board derivation (e.g., `PLL_MIN_FREQ_HZ` from tank capacitance) is reverse-checked against the actual board's components — hardware and firmware cannot disagree about a load-bearing value.
  - **Success signal:** for every registered constant, a gate re-derives the value from the actual board's placed components and fails the run on disagreement; a registered component missing from the board is a failure, not a value mismatch.

### Key Technical Decisions

- KTD1. **A registry file is the single record of derivations.** Each entry names the firmware constant, its firmware source, the derivation formula, the board inputs, and the failure mode; the oracle iterates the registry so adding a derivation is data, not new check code.
- KTD2. **The board file, not the `.ato` declarations, is the physical truth.** Board inputs are extracted from the placed components in `pcb/temper.kicad_pcb`; the `.ato` declarations remain the design intent and are cross-checked only as a secondary signal.
- KTD3. **One derivation implementation, two checks.** The formula library is shared between the existing declared-vs-declared gate (`scripts/check_pll_range_consistency.py`) and the new board-vs-firmware oracle, so the two cannot drift.
- KTD4. **Tolerances live inside the derivation, never as an output fudge.** A registered tolerance (e.g., ±10 % capacitor tolerance) is applied within the formula; a disagreement outside the derived band fails with both values named, matching the repo's ceiling-approval discipline of attributed, never-silent, deltas.

### Assumptions

- A1. **Seed discrepancy:** the portfolio seed `firmware/config.yaml` exists but does not contain `PLL_MIN_FREQ_HZ` — that constant lives in `firmware/components/control/pll_control.h` with its derivation documented inline, and its inputs live in `elec/src/main.ato` and `elec/src/modules.ato`. The registry therefore spans `firmware/config.yaml`, `firmware/components/control/pll_control.h`, and the `elec/src/*.ato` files; the plan records this explicitly rather than pretending the seed is a single file.
- A2. **Board parsing is implementable:** the placed tank capacitors and the reference resistor are extractable from `pcb/temper.kicad_pcb` (footprints/netlist) with the repo's existing KiCad parsing patterns. If a registered component cannot be located on the board, the oracle reports UNMEASURED, never a silent pass.
- A3. **The current board is expected to fail or report UNMEASURED:** `tank.c_tank3` is staged off the board (see Sources), so the oracle's first run against the current board proves the defect class rather than passing.
- A4. **Portfolio R7's success-signal field** is satisfied by the idea text's outcome clause; no separate signal was published for R18.

---

## Implementation Units

### U1. Board-derivation registry and formula library

**Goal:** A registry (one YAML entry per board-derived constant) and a formula library implementing each derivation once, with unit-tested reference vectors.

**Requirements:** R18

**Dependencies:** none

**Files:**
- `firmware/tools/board_derivations.yaml` (new registry)
- `firmware/tools/board_derivation_lib.py` (new formula library)
- `firmware/tools/test_board_derivation_lib.py` (new host pytest)

**Approach:** Seed the registry with the two documented derivations. Entry 1: `PLL_MIN_FREQ_HZ` from `firmware/components/control/pll_control.h`, derived from loaded tank inductance and total tank capacitance worst-cased by both tolerances, floor = 1.05 x worst-case loaded resonance (the formula already documented in `scripts/check_pll_range_consistency.py` and `elec/src/main.ato`). Entry 2: `MAX31865_LOW_THRESHOLD_WORD` and `MAX31865_HIGH_THRESHOLD_WORD` from `firmware/config.yaml`, derived from the reference resistor and PT100 resistance range via the MAX31865 15-bit ADC scaling. Each formula is implemented once in the library with named inputs and named constants.

**Patterns to follow:** The derivation arithmetic in `scripts/check_pll_range_consistency.py`; the `c_tank_total` / `l_tank_assumed` / `c_tank_tolerance` / `l_tank_tolerance` declarations in `elec/src/main.ato`; the `r_ref` declaration in `elec/src/modules.ato`; the host-pytest pattern of `firmware/test/test_codegen_tools.py`.

**Test scenarios:**
1. Happy path: `PLL_MIN_FREQ_HZ` re-derived from the declared inputs (loaded inductance, 300 nF total, ±10 % tolerances) yields the documented 44 kHz floor.
2. Happy path: the MAX31865 threshold words re-derived from a 430 Ω reference resistor and the 10 Ω / 300 Ω PT100 boundaries match the committed values in `firmware/config.yaml`.
3. Edge case: each formula exposes its intermediate quantities (worst-case L, worst-case C, loaded resonance) so a derivation change is attributable.
4. Error path: a registry entry with a missing formula key fails registration with the entry named.

**Verification:** Host pytest on `firmware/tools/test_board_derivation_lib.py` passes; each seeded formula reproduces the committed firmware value from the declared `.ato` inputs.

### U2. Board-side component extraction

**Goal:** A board parser that locates each registered component in `pcb/temper.kicad_pcb` and returns its value (or its absence), so the oracle can re-derive from physical truth.

**Requirements:** R18

**Dependencies:** U1

**Files:**
- `firmware/tools/board_component_extractor.py` (new)
- `firmware/tools/test_board_component_extractor.py` (new host pytest)
- `pcb/temper.kicad_pcb` (read-only input)

**Approach:** Parse the board file for the registered component refdes and read their placed values and footprints. The extractor reports three outcomes per component: placed with a parseable value, placed with an unparseable value, or absent from the board. Absence is a first-class outcome because the defect class is a staged-off component, not a wrong value.

**Patterns to follow:** The KiCad parsing patterns used by the placer's board-side validators (see the `netlist`/`preflight` machinery referenced in the portfolio Sources); the UNMEASURED-reporting convention used by repo gates when a probe cannot run.

**Test scenarios:**
1. Happy path: extraction of the tank capacitors from the current board file returns the placed refdes and their capacitance values.
2. Edge case: a component present in the registry but absent from the board (the `tank.c_tank3` case) is reported as absent, not as a zero-value.
3. Error path: a board file that cannot be parsed fails the extractor with the parse error, never an empty success.

**Verification:** Host pytest passes; the extractor's report on the current board names each registered component's disposition (placed / absent / unparseable).

### U3. Oracle check

**Goal:** The oracle re-derives every registered constant from board inputs, compares against the firmware constant, and exits nonzero on any disagreement.

**Requirements:** R18

**Dependencies:** U1, U2

**Files:**
- `scripts/check_firmware_board_contract.py` (new check, with `scripts/manifest.yaml` entry)
- `scripts/check_pll_range_consistency.py` (modified to share the formula library)

**Approach:** For each registry entry, the oracle: (1) extracts the board inputs, (2) applies the shared derivation, (3) compares the board-derived value to the firmware constant, applying registered tolerances inside the formula. It emits a per-entry verdict and a named failure (constant, firmware value, board-derived value) on disagreement. A registered component reported absent fails the run as a missing-component error. The declared-vs-declared checks in `scripts/check_pll_range_consistency.py` continue to run and share the same formula code path.

**Patterns to follow:** The fail-with-attribution shape of `scripts/check_pll_range_consistency.py`; the script manifest convention in `scripts/manifest.yaml`; the ceiling-approval discipline of named, attributed failures in `scripts/check_drc_ceiling_approval.py`.

**Test scenarios:**
1. Happy path: with the tank caps placed at the declared total, the oracle re-derives the PLL floor equal to the firmware constant and passes.
2. Error path: a board whose placed tank capacitance is below the declared total (one cap absent) fails with the constant, both values, and the missing component named.
3. Error path: a board whose reference resistor differs from 430 Ω fails the MAX31865 threshold-word entry with the recomputed words.
4. Edge case: a registry entry whose board input cannot be extracted reports UNMEASURED and does not pass silently.

**Verification:** The oracle's unit tests pass; a dry run against the current board produces a named, attributable failure or UNMEASURED per entry, never a silent pass.

### U4. CI wiring and coverage guard

**Goal:** The oracle runs in CI on the firmware and board path, and the registry is guarded against drift from the constants it covers.

**Requirements:** R18

**Dependencies:** U3

**Files:**
- `.github/workflows/firmware-tests.yml` (add the oracle step, or extend the board gates workflow)
- `firmware/tools/check_board_derivation_coverage.py` (new drift guard)

**Approach:** Add the oracle step to the firmware CI path so every firmware or board change re-checks the board-derived constants. The drift guard scans `firmware/config.yaml` and `firmware/components/control/pll_control.h` for constants annotated with a board-derivation marker and fails when an annotated constant has no registry entry, so new derivations cannot ship unregistered.

**Patterns to follow:** The drift-check steps in `.github/workflows/firmware-tests.yml` (regenerate-and-compare shape); the `scripts/manifest.yaml` entry requirement for new scripts.

**Test scenarios:**
1. Happy path: registry covers all annotated constants and the oracle passes.
2. Error path: a constant newly annotated with a board-derivation marker but missing from the registry fails the drift guard naming the constant.
3. Error path: a registry entry whose board input is UNMEASURED is reported as UNMEASURED, not as pass.

**Verification:** The CI step runs the oracle and the drift guard on every firmware-path change; both scripts carry `scripts/manifest.yaml` entries.

---

## Verification Contract

- Host pytest for `firmware/tools/test_board_derivation_lib.py`, `firmware/tools/test_board_component_extractor.py`, and the oracle's tests.
- Oracle dry run: `scripts/check_firmware_board_contract.py` against the current `pcb/temper.kicad_pcb` must emit a per-entry verdict with no silent passes.
- CI: the firmware workflow runs the oracle and the coverage guard; `scripts/check_pll_range_consistency.py` remains green with the shared formula library.

## Definition of Done

- U1's registry contains the two seeded derivations with unit-tested formulas.
- U2's extractor reports each registered component's disposition on the current board.
- U3's oracle fails on any disagreement and never silently passes an UNMEASURED entry.
- U4's CI step and drift guard are live.
- No drift is introduced in the generated headers by this plan's changes; codegen outputs stay byte-stable.

---

## Scope Boundaries

- The registry covers the two documented board derivations; constants without a board derivation (timeouts, setpoint ranges) are out of scope.
- Full netlist-to-board reconciliation (wholesale renumbering, missing components at scale) is owned by R16 and out of scope here.
- Moving `PLL_MIN_FREQ_HZ` from `firmware/components/control/pll_control.h` into `firmware/config.yaml` is a firmware refactor, not this oracle's job.

### Deferred to Follow-Up Work

- Registering new derivations as they are documented (each is a data addition to the registry).
- Board-BOM cross-checks against the fab bill of materials once one exists.
- Folding the oracle into the board-defect mutation corpus of R38 so mutated boards are caught by it.

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — R18, R16 (netlist reconciliation), R8 (seed anchoring).
- `firmware/components/control/pll_control.h` — the `PLL_MIN_FREQ_HZ` derivation block (worst-cased loaded resonance, ZVS floor).
- `firmware/config.yaml` — the MAX31865 threshold-word entries and their 430 Ω RREF documentation.
- `elec/src/main.ato` — `c_tank_total`, `l_tank_assumed`, `l_tank_tolerance`, `c_tank_tolerance` declarations and the floor derivation notes.
- `elec/src/modules.ato` — `r_ref` (430 Ω) and the tank capacitor parts.
- `scripts/check_pll_range_consistency.py` — the existing declared-vs-declared gate whose formula the oracle shares.
- `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md` — the off-board `tank.c_tank3` defect class and the `PLL_MIN_FREQ_HZ = 44000` derivation from 300 nF.
- `docs/evidence/2026-07-29-pll-floor-cap-tolerance.md` and `docs/evidence/2026-07-29-tank-coil-specification.md` — the derivation evidence chain.

---
