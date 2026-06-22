---
date: 2026-06-21
topic: source-of-truth-validation
---

# Source-of-Truth Consolidation and Automated Validation

## Summary

A five-phase initiative that converts the Temper PCB toolchain from one where constraint bugs are caught by human review into one where they're caught structurally — by the type system, CI, and the constraint generators themselves. The phases are sequenced by dependency: zero-cost catches first, core Pydantic architecture second, derived-artifact verification third, cross-layer voltage consistency fourth, and schematic pre-placement oracle fifth.

---

## Problem Frame

A clean-base sprint in June 2026 fixed twelve or more bugs across `packages/temper-placer`, `packages/temper-drc`, and the KiCad DRU generator — all of them silent. KiCad accepted DRU condition expressions that were semantically wrong and never fired. Validation functions referenced nonexistent field names and returned `False` forever. Two new DRC checks were implemented but never wired into the CLI's hardcoded list and never ran. A debug `print()` in a class body fired on every import. ISO keyword typos caused isolation components to be silently misclassified.

Stepping back, every bug shares a common shape: a constraint exists in one place and is interpreted in another, with no machine-enforced link between the two. The zone-bounds duplication (benders ILP code duplicating YAML values, producing 28mm placement errors) and the HV clearance gap (2.0mm declared in Python, 3.0mm required by IEC 60664-1 at 400V) are the same pattern at a larger scale. The toolchain has no structural defense against this class of failure — bugs are found only when a human notices the output is wrong.

This initiative adds five layers of structural defense, from zero-cost one-liners to a full schematic constraint oracle, each making a previously-silent failure loud.

---

## Actors

- A1. **Developer** — edits `TEMPER_NET_CLASSES`, adds DRC checks, places components in Atopile. Primary source of the bugs this initiative prevents.
- A2. **CI pipeline** — runs lint, tests, DRU generation, round-trip parse, and KiCad headless DRC on every push. The primary enforcement layer for Phases 1–3.
- A3. **Atopile compiler** (`ato compile`) — the enforcement point for Phase 5's schematic oracle; fails the build when component constraints are violated.

---

## Key Flows

- F1. **Developer changes a net class constraint**
  - **Trigger:** A1 edits a clearance, trace width, or voltage value in the net class definition.
  - **Actors:** A1, A2
  - **Steps:** (1) A1 edits the Pydantic model. (2) Model validators fire at import, catching IEC norm violations immediately. (3) A1 runs the DRU generator; the updated DRU is produced. (4) A2 runs CI: golden-file diff detects the change, round-trip parse verifies the emitted values match the source, KiCad headless DRC asserts the expected violations still appear on the fixture board. (5) A2 passes or fails with a specific error naming which assertion broke and why.
  - **Outcome:** A constraint change that is either valid (all CI steps pass) or invalid (at least one step fails with a named, human-readable error) — never silently wrong.
  - **Covered by:** R4, R5, R6, R7, R8

- F2. **Developer adds a new DRC check**
  - **Trigger:** A1 creates a new `Check` subclass in `packages/temper-drc/`.
  - **Actors:** A1, A2
  - **Steps:** (1) A1 adds the decorator to the new class. (2) The registry includes it automatically. (3) A2 runs CI: the factory count test detects the new check; linting detects any `*Check` class without the decorator. (4) If A1 forgot the decorator, the lint rule fails with a named message.
  - **Outcome:** The check appears in `create_temper_checks()` with zero additional edits. Forgetting the decorator produces a lint failure, not a silently unregistered check.
  - **Covered by:** R3

- F3. **Developer adds a component with insufficient voltage rating**
  - **Trigger:** A1 places a component in the Atopile schematic whose rated voltage is below the working voltage of the net it connects to.
  - **Actors:** A1, A3
  - **Steps:** (1) A1 runs `ato compile`. (2) The oracle queries VoltageMap for the net's working voltage. (3) The oracle compares it against the component's declared voltage rating. (4) `ato compile` exits nonzero with a message naming the component, the net, the component's rating, and the required minimum.
  - **Outcome:** The violation is reported before any PCB artifact is generated; no layout work is wasted on a wrong part selection.
  - **Covered by:** R13, R15

---

## Requirements

**Phase 1 — Zero-cost safety net**

- R1. Ruff rule `T201` is enabled in the project ruff configuration. Bare `print()` calls outside of `if __name__ == "__main__"` guards or test files produce a lint error that fails CI.
- R2. All structural invariants in the design rules module and DRU generator are asserted at module scope, following the `assert set(class_order) == set(TEMPER_NET_CLASSES.keys())` pattern established in the sprint. A developer who introduces a drift error sees a named `AssertionError` at import time, before any test runs.

**Phase 2 — Core architecture**

- R3. A class decorator registers each `Check` subclass into a module-level registry at definition time. `create_temper_checks()` returns `list(registry.values())`. A lint rule flags any class matching `*Check(Check)` that lacks the decorator. Adding a check requires exactly one edit; there is no separate registration step.
- R4. `TEMPER_NET_CLASSES` and `TEMPER_NET_ASSIGNMENTS` are replaced with Pydantic model instances. All downstream consumers (DRU generator, DRC checks, ILP solver inputs) access net class fields as typed attributes. A field rename or typo produces an `AttributeError` at import time rather than a silent wrong value at DRC run time.
- R5. Each entry in the Pydantic net-class model carries an `iec_reference` field with: standard identifier, applicable voltage range, pollution degree assumption, and `normative_minimum_mm`. A model validator asserts `declared_clearance >= normative_minimum` and raises a named `ValidationError` at import time when violated. An IEC 60664-1 lookup function (voltage, pollution degree → minimum clearance mm) is implemented as a shared module; this same function is consumed by Phase 4's VoltageMap generator.

**Phase 3 — Derived artifact verification**

- R6. The generated `pcb/temper.kicad_dru` is committed to version control and treated as a versioned artifact. A CI step regenerates it from source and diffs the output against the committed file; any content change fails CI unless the committed file is intentionally updated. The command to update the golden file is documented in `CLAUDE.md`.
- R7. After generation, a CI test parses the DRU file, extracts per-rule clearance and width values, and asserts they match the corresponding Pydantic model values. A generator bug that produces a valid-syntax but wrong-value rule fails this test. The test lives in `packages/temper-drc/tests/`.
- R8. A minimal fixture board (committed under `pcb/fixtures/`) contains at least one HV/LV net pair spaced below the IEC-required minimum. A CI step runs `kicad-cli pcb drc` against this fixture with the generated DRU and asserts the expected clearance violation appears in the DRC report. A rule that is syntactically valid but semantically dead (zero violations on a board known to have violations) fails CI.

**Phase 4 — Cross-layer voltage consistency**

- R9. A `VoltageMap` Pydantic model declares the working voltage for each power domain on the board. This is the single canonical declaration of bus voltages; no other file independently states voltage values for the same domains.
- R10. A code generator reads `VoltageMap` and emits Atopile `assert` statements for each voltage rail into the Atopile source tree. Hand-authored voltage assertions that duplicate the map are removed; the Atopile source references only the generated file.
- R11. The same generator reads `VoltageMap` and, using the shared IEC 60664-1 lookup from R5, computes the required minimum clearance for each power domain. If any domain's computed minimum exceeds the declared clearance in the Pydantic net-class model, the generator raises an error naming the domain, the computed minimum, and the declared value. This resolves the current 2.0mm / 3.0mm HighVoltage discrepancy.
- R12. The VoltageMap generator is covered by tests: given a change to a bus voltage value, the emitted Atopile assertions and IEC minimums update to reflect the new value; given a clearance value below the IEC minimum, the generator raises a named error.

**Phase 5 — Schematic pre-placement oracle**

- R13. At `ato compile` time, each placed component's declared voltage rating is compared against the VoltageMap working voltage for the net it connects to. A rating below the working voltage causes `ato compile` to exit nonzero with a message naming: the component reference, the net name, the component's rated voltage, and the required minimum.
- R14. At `ato compile` time, each isolation component's declared creepage distance is compared against the IEC minimum at the relevant voltage differential (derived from VoltageMap). A component whose creepage is below the IEC minimum causes `ato compile` to exit nonzero with a message naming: the component reference, the measured isolation voltage differential, the component's creepage, and the required minimum.
- R15. The oracle reads voltage values exclusively from `VoltageMap` and IEC minimums exclusively from the shared lookup function (R5). No voltage or clearance constant is duplicated into the Atopile assertion logic.

---

## Acceptance Examples

- AE1. **Covers R5.** Given `HighVoltage` declares `clearance=2.0` and the IEC 60664-1 lookup at 400V / PD2 / OVC II returns 3.0mm (Table F.2), when `import temper_placer.core.design_rules` executes, a `ValidationError` is raised with a message identifying `HighVoltage`, the declared value (2.0mm), and the IEC minimum (3.0mm). The import does not succeed.

- AE2. **Covers R3.** Given a developer adds a `CreepageV2Check(Check)` class without the `@register_check` decorator, when the CI lint step runs, it fails with a message naming the unregistered class. `create_temper_checks()` does not include it.

- AE3. **Covers R6.** Given the DRU generator is changed such that one clearance rule emits `2.0` instead of `3.0`, when CI runs, the golden-file diff step fails and outputs a diff showing the change. The CI step that runs KiCad headless DRC does not reach the fixture board test because the golden-file step fails first.

- AE4. **Covers R8.** Given a DRU condition expression is changed to `A.Attribute == 'SMD'` (which KiCad accepts but never evaluates as true), when `kicad-cli pcb drc` runs against the fixture board, the expected HV/LV clearance violation is absent from the report. CI fails with a message indicating the expected violation was not found.

- AE5. **Covers R11.** Given `VoltageMap` declares `DC_BUS = 400V` and the IEC minimum at 400V is 3.0mm, and `HighVoltage.clearance = 2.0`, when the VoltageMap generator runs, it raises an error: `"HighVoltage: declared clearance 2.0mm is below IEC minimum 3.0mm at 400V"`.

- AE6. **Covers R13.** Given a component rated at 250V is placed on `DC_BUS+` (working voltage 400V), when `ato compile elec/src/main.ato` runs, it exits nonzero: `"Component U7 voltage rating 250V is below DC_BUS+ working voltage 400V"`.

---

## Success Criteria

- A developer who introduces a field name typo in a `TEMPER_NET_CLASSES` consumer sees a named `AttributeError` at `python -m temper_drc` — not a wrong DRC result hours later.
- A developer who adds a DRC check and forgets to decorate it sees a lint failure at CI — not an unexercised check that silently never runs.
- A change to a clearance value in the Pydantic model that would produce wrong output in the DRU file is caught before merge — by the golden-file diff, the round-trip parse, or the KiCad headless DRC, depending on the failure mode.
- The HV clearance discrepancy (2.0mm declared, 3.0mm IEC minimum at 400V) is a CI failure, not a manual review finding.
- `ato compile` is the authoritative gate for schematic-layer component selection constraints; a board that fails R13 or R14 never reaches the PCB layout stage.
- After Phase 1–3 land, the sprint-level bug class ("implemented but silent") does not recur across the next three routing sessions.

---

## Scope Boundaries

- **KiCad Python plugin approach** — replacing the DRU file as the KiCad integration point is out of scope; the generated DRU file remains the KiCad boundary.
- **File-watcher daemon** — always-on background constraint evaluation is deferred; revisit after Phases 1–3 have stabilized the signal-to-noise ratio.
- **Hypothesis property-based testing** — round-trip property tests are a natural extension of Phase 3 once the KiCad headless fixture is in place; treated as a Phase 3 enhancement, not a requirement.
- **Component library metadata enforcement** — Phase 5 requires that KiCad component symbols carry voltage rating and creepage attributes; populating and enforcing the full library is ongoing work, not a Phase 5 deliverable. Phase 5 validates components that already carry these attributes.
- **ISO_KEYWORDS as `StrEnum`** — addressed by the Pydantic model's typed vocabulary; no separate StrEnum migration is required.

---

## Key Decisions

- **Phase sequencing is dependency-driven, not priority-driven.** Ideas 4 (IEC citations) and 6 (VoltageMap generator) share one IEC 60664-1 lookup function; that function is a Phase 2 deliverable that Phase 4 depends on. Reordering the phases would require duplicating the lookup or shipping it incomplete.
- **Pydantic migration is one coordinated changeset, not incremental.** `NetClassRules` is already a `@dataclass`; switching it to a Pydantic model requires updating all consumers simultaneously. There is no clean incremental path because `dict` key access and attribute access are not interchangeable.
- **DRU file remains the KiCad integration boundary.** A KiCad Python plugin that replaces the DRU entirely would be cleaner architecturally but requires maintaining a plugin against KiCad's internal API across versions. The DRU file approach is more portable and already supported by `kiutils`.
- **Phase 5 oracle targets `ato compile`, not KiCad schematic editing.** The enforcement experience is a failed compile with a named error, not a visual warning during symbol drag-and-drop. This is a deliberate scope choice: Atopile's assertion mechanism is already available and requires no UI integration.

---

## Dependencies / Assumptions

- **Pydantic is already available** in the uv workspace (temper-drc uses it); no new top-level dependency is introduced.
- **KiCad 7+ ships `kicad-cli`** with the `pcb drc` subcommand. Phase 3 Tier 3 (R8) assumes this binary is installable in the CI environment (Docker image or GitHub Actions runner). This is an unverified assumption for the CI setup — confirm during planning.
- **`kiutils` is available on PyPI** and supports the current `.kicad_dru` S-expression format (version `1.1.1` confirmed). The round-trip parse in R7 depends on it.
- **Atopile components carry voltage rating and creepage metadata** as standard attributes. Phase 5 (R13, R14) can only validate components that already declare these fields; the oracle does not infer them from part numbers.
- **The IEC 60664-1 table is implemented correctly.** The voltage → minimum clearance lookup must be verified by an EE against the standard before Phase 2 lands. An incorrect table produces wrong IEC citations and wrong VoltageMap-derived minimums — the failure is quiet and safety-critical.

---

## Outstanding Questions

### Resolve Before Planning

- **[Resolved]** Fixture board — committed binary in `pcb/fixtures/`. Update command to be documented in `CLAUDE.md`.
- **[Resolved]** Pollution degree — **PD2 (normal indoor)**. Temper is a consumer counter-top cooktop; IEC 60664-1 Table F.2 OVC II at 340–400V gives **3.0mm minimum clearance**. The IEC 60664-1 lookup function in R5 hardcodes PD2; R11 enforces 3.0mm as the floor for the HighVoltage net class. The current 2.0mm declaration is a CI failure under R5 and R11.

### Deferred to Planning

- **[Affects R4][Technical]** Which downstream consumers of `TEMPER_NET_CLASSES` exist outside of `packages/temper-drc` and `scripts/generate_kicad_dru.py`? Confirm the full consumer list before the Pydantic migration to avoid missed updates.
- **[Affects R10][Technical]** Which Atopile file currently contains the hand-authored voltage assertions, and what is the expected output format for the generated replacement? The generator must produce syntactically valid Atopile DSL.
- **[Affects R8][Needs research]** Does `kicad-cli pcb drc` produce machine-readable output (JSON or XML) suitable for programmatic assertion, or does it produce human-readable text that requires parsing? Confirm before implementing the CI assertion step.
