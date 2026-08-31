---
title: Split Board Foundation - Plan
type: feat
date: 2026-08-30
topic: split-board-foundation
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
execution: code
---

# Split Board Foundation - Plan

## Goal Capsule

**Objective:** Make the approved power/control-board split explicit, testable, and fail-closed before either physical board is generated.

**Means:** Establish one interface contract, one domain partition, and one generation-readiness gate while preserving the current single-board artifact during migration.

**Product authority:** This plan owns the software and electrical-source foundation for the split. Connector selection, enclosure design, and physical PCB generation remain outside active scope.

**Open blockers:** Physical generation requires a frozen connector and pinout, verified mechanical partition and enclosure evidence, resolved `+3V3` transfer, shutdown open-wire behavior, and split fault aggregation.

## Product Contract

### Summary

The repository will carry one coherent, machine-checked contract for the approved power/control-board split. It will reject premature generation while keeping the existing production board buildable during migration.

### Problem Frame

The current board interleaves mains and SELV domains and cannot accept a credible isolation corridor without a full redesign. The repository already describes a split-board direction, but its interface count, ownership, and generation prerequisites are incomplete or inconsistent. Independent scaffolds would allow those representations to drift before physical layout begins.

### Key Decisions

- **Use separate power and control boards.** (session-settled: user-approved — chosen over another single-board redesign: the existing interleaved placement cannot support a credible isolation boundary.) Governs R1, R3, R6.
- **Design to PD3 and 12.6 mm.** (session-settled: user-approved — chosen over an unproven PD2 enclosure: no compliant sealed-compartment design is committed.) Governs R2, R7.
- **Block generation until physical prerequisites are real.** A deliberately blocked readiness verdict is preferable to placeholder PCB artifacts. Governs R5, R7, R8.
- **Preserve the current board during migration.** The foundation must coexist with the legacy production artifact. Governs R6.

### Requirements

**Interface authority**

- R1. One authoritative ten-net SELV interface shall define board ownership, signal direction, return path, and fault/status semantics; `I_SENSE` is the reconciled tenth net.
- R2. The interface contract shall record PD3 and 12.6 mm as the governing cross-domain isolation target.
- R3. Power-domain modules, SELV modules, and both sides of every isolator shall have complete, non-overlapping power-board or control-board ownership.
- R4. Unresolved fan PWM/tach behavior shall remain deferred and shall not silently enter the ten-net interface.

**Readiness and migration**

- R5. Split-board generation shall fail closed while connector, pinout, mechanical, enclosure, `+3V3`, shutdown open-wire, or fault-aggregation prerequisites are unresolved.
- R6. The foundation shall not alter or replace the current single-board production artifact.
- R7. Each future board shall require its own source entrypoint, PCB and netlist identity, DRC result, live provenance, and PD3 cross-domain evidence before it can be accepted.
- R8. A passing readiness verdict shall require evidence-backed physical inputs rather than placeholder values or empty artifacts.

**Repository enforcement**

- R9. Existing domain-partition checks shall enforce the split ownership and isolator mapping.
- R10. The split-board readiness check shall be registered in repository tooling and covered by focused tests without making unrelated legacy workflows fail merely because physical generation is not yet authorized.

### Acceptance Examples

- AE1. **Covers R1, R3.** Given the committed domain manifest, when ownership validation runs, then all ten interface nets and every isolator side resolve to exactly one board.
- AE2. **Covers R3, R9.** Given an HV module assigned to the control board, when domain validation runs, then it fails with the conflicting ownership.
- AE3. **Covers R5, R8.** Given no approved connector or enclosure evidence, when generation readiness is evaluated, then it returns a distinct blocked verdict and creates no PCB artifact.
- AE4. **Covers R6.** Given the new split hierarchy, when the existing production build runs, then it continues to build the legacy single-board entrypoint unchanged.
- AE5. **Covers R7.** Given only one future board's DRC or provenance record, when readiness is evaluated, then it remains blocked and names the missing board evidence.
- AE6. **Covers R4.** Given fan PWM/tach remains deferred, when the ten-net interface is validated, then neither signal is counted or inferred as an interface member.

<!-- ce-section: work-relationships -->
### How This Work Fits Together

This plan owns the contract and enforcement foundation. The broader breakdown is contextual and may change as physical design evidence arrives.

- **Depends on:** the approved split-board direction and PD3/12.6 mm safety target.
- **Enables:** connector and harness selection against a stable interface contract.
  - **Enables:** separate Atopile power/control entrypoints and generated board artifacts.
  - **Enables:** per-board placement, routing, DRC, and provenance work.
- **Can proceed independently of:** the unresolved enclosure and physical connector selection because readiness remains blocked.
- **Still to decide:** physical partition details, connector pinout, enclosure geometry, `+3V3`, shutdown open-wire behavior, fault aggregation, and deferred fan control.

### Scope Boundaries

- No connector or harness part selection.
- No enclosure dimensions, mounting, airflow, or cable-penetration design.
- No generation, placement, routing, or DRC measurement of new PCB artifacts.
- No replacement or mutation of `pcb/temper.kicad_pcb`.
- No fan PWM/tach interface commitment.

### Dependencies / Assumptions

- The approved architecture remains separate power and control boards.
- PD3 with 12.6 mm separation remains the governing target unless later physical evidence formally establishes a compliant alternative.
- A blocked readiness result is an expected pre-generation state, not a CI failure for workflows that do not request split-board generation.

### Outstanding Questions

**Resolved in the Planning Contract**

- KTD1 resolves the overlapping domain-manifest and validator implementations into one electrical authority.
- KTD2 keeps physical evidence in a separate readiness authority without duplicating ownership.
- KTD3 gives the explicit readiness command a distinct blocked result while routine validation remains green.

### Sources / Research

- `docs/superpowers/specs/2026-07-31-split-power-control-board-design.md`
- `elec/domain_manifest.yaml`
- `docs/evidence/2026-08-04-isolation-barrier-freeform-corridor.md`
- `docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md`

## Planning Contract

### Technical approach

Use `elec/domain_manifest.yaml` as the shared authority for board ownership and the ten-net interface. Extend the existing domain-partition validator so ownership, isolator sides, and interface semantics are validated together rather than by parallel parsers. Keep physical-generation prerequisites in the separate split-board manifest because they describe evidence artifacts, not electrical-domain ownership.

The component-free Atopile boundaries remain unreferenced by `src/main.ato:Top` until physical generation is authorized, and the domain validator checks their interface field-by-field against `elec/domain_manifest.yaml` so they cannot become a second authority. Board-ownership fields describe the target split only; they do not change the meaning or result of checks against the shipping single-board artifact.

The split-board readiness command has a fixed exit contract: `0` means ready, `2` means well-formed but blocked and includes a machine-readable list of unresolved prerequisites, and `1` means malformed. Ordinary CI asserts the committed manifest's expected blocked result without treating it as a failure in unrelated legacy workflows.

### Key technical decisions

- KTD1. Reconcile the two domain-manifest implementations by preserving the richer typed ten-net interface from `b1c93ce73` and folding the explicit module/isolator ownership and Atopile boundary from `f3b0d542c` into it. Governs R1-R4, R9.
- KTD2. Keep `elec/split_board_manifest.yaml` as the physical evidence/readiness authority introduced by `982ccce04`; it references, but does not duplicate, electrical ownership. Governs R5, R7, R8, R10.
- KTD3. Expose generation readiness through an explicit command and focused CI test, while routine domain validation continues to pass for the planned-but-blocked migration state. The command must consume the domain-interface readiness verdict; every future split-board generation target must call this command before writing PCB or netlist artifacts. Governs R5, R6, R10.
- KTD4. Cross-domain top-level modules are not assigned wholesale to either board. They must decompose into explicitly owned submodules or isolator-side pin groups, with every component accounted for exactly once. Governs R3, R9.
- KTD5. Physical evidence is accepted by semantics, not file existence: versioned evidence records must carry source identity and hashes, explicit approval state, and the engineering values used by the readiness decision. DRC provenance must reuse or exactly match the repository provenance validator, including clean/resolvable commits, current input hashes, and nondeterministic sample rules. Governs R7, R8.

### Existing patterns to follow

- `scripts/check_domain_partition.py` for manifest-backed electrical-domain validation.
- `scripts/check_measurement_provenance.py` for fail-closed artifact identity and provenance semantics.
- `scripts/manifest.yaml` and `scripts/trace_invocations.py` for script registration.
- `elec/src/main.ato` and the existing Atopile build configuration for preserving the legacy production entrypoint.

### Sequencing

U1 and U2 both depend on the current manifest but should be integrated serially because they overlap the same authority and validator tests. U3 depends on the reconciled U1/U2 contract. U4 runs after all code and generated invocation metadata are stable.

## Implementation Units

### U1. Reconcile the ten-net interface authority

**Covers:** R1, R2, R4; AE1, AE6; KTD1.

**Files:**

- `elec/domain_manifest.yaml`
- `docs/superpowers/specs/2026-07-31-split-power-control-board-design.md`
- `scripts/check_domain_partition.py`
- `scripts/tests/test_check_domain_partition.py`

**Work:** Integrate commit `b1c93ce73` as the interface-semantic base. Preserve the ten-net reconciliation, typed ownership/direction/return/fault fields, and PD3 target. Expose unresolved electrical semantics as a typed domain-interface readiness verdict for U3 to consume; do not implement physical prerequisite checks in the domain validator. Resolve overlap with U2 in favor of one manifest shape and one parser path.

**Test scenarios:**

- The real manifest validates exactly ten interface nets and names `I_SENSE` as the tenth.
- Duplicate, missing, directionless, returnless, or cross-domain interface entries fail with actionable diagnostics.
- Fan PWM/tach is not inferred into the interface.
- Unresolved `+3V3`, shutdown, or fault-aggregation semantics produce a typed interface-readiness block that U3 can consume.

### U2. Integrate board ownership and Atopile boundaries

**Covers:** R3, R6, R9; AE1, AE2, AE4; KTD1, KTD4.

**Blocked by:** U1.

**Files:**

- `elec/domain_manifest.yaml`
- `elec/src/split_board_hierarchy.ato`
- `scripts/check_domain_partition.py`
- `scripts/tests/test_check_domain_partition.py`

**Work:** Fold commit `f3b0d542c` into the reconciled authority. Keep explicit HV-to-power, SELV-to-control, and complete isolator-side ownership. Decompose cross-domain top-level modules into owned submodules or isolator-side pin groups; forbid ambiguous whole-module ownership and require every component to be accounted for once. Add component-free typed boundaries without importing them into the production `Top` entrypoint.

**Test scenarios:**

- Every declared module has exactly one board owner.
- Assigning HV to control or SELV to power fails.
- Every isolator pin group has complete, opposite-side ownership.
- Cross-domain modules cannot bypass component-level ownership through a whole-module assignment or exemption.
- The Atopile boundary exposes only the declared SELV interface.
- Changing either the manifest interface or the Atopile boundary alone fails their field-by-field consistency check.
- The legacy `src/main.ato:Top` build remains unchanged and does not import the split boundary.
- Existing single-board domain checks return the same result before and after target-state ownership fields are added.

### U3. Integrate physical generation-readiness gates

**Covers:** R5, R7, R8, R10; AE3, AE5; KTD2, KTD3, KTD5.

**Blocked by:** U1, U2.

**Files:**

- `elec/split_board_manifest.yaml`
- `scripts/check_split_board_contract.py`
- `scripts/tests/test_check_split_board_contract.py`
- `scripts/manifest.yaml`
- `scripts/invocation_graph.json`
- `Makefile`
- `.github/workflows/python-tests.yml`

**Work:** Integrate commit `982ccce04`. Make its explicit readiness command consume the typed domain-interface verdict and require separate power/control sources, PCBs, netlists, DRC reports, live provenance with matching input hashes, and PD3/12.6 mm evidence before readiness can pass. Evidence records must be versioned, explicitly approved, content-addressed, and carry the engineering values used by the decision. Reuse or exactly match `check_measurement_provenance.py` semantics for DRC evidence. Keep the planned incomplete state machine-readable and ensure ordinary CI tests assert the expected block without treating it as malformed input. Define the command as the mandatory pre-write guard for every future split-board generator; because no generator is created in this scope, enforce this now as a manifest/contract invariant and a testable integration API.

**Test scenarios:**

- The committed planned manifest returns the documented blocked verdict and names all missing evidence.
- The readiness command exits `2` with a machine-readable blocked payload for the committed manifest, exits `1` for malformed input, and exits `0` only when every prerequisite is valid.
- Renaming a board or interface reference in the domain manifest without updating the physical contract fails as a contract error.
- Malformed ownership, missing board identities, mismatched hashes, dirty provenance, or absent PD3 evidence fail as contract errors.
- Providing only one board's evidence remains blocked.
- Placeholder or empty artifacts never satisfy readiness.
- Unresolved electrical-interface semantics keep physical readiness blocked.
- Unapproved evidence, semantically incomplete evidence, unresolvable measurement commits, stale input hashes, dirty measurements, and insufficient samples for nondeterministic categories fail closed.
- A test generation facade exits before its first artifact write when readiness is blocked.
- Script registration and invocation metadata remain synchronized.

### U4. Verify the coherent foundation

**Covers:** R1-R10; AE1-AE6.

**Blocked by:** U1, U2, U3.

**Files:** No production files unless verification exposes an in-scope defect.

**Work:** Run the combined domain, split-contract, script-manifest, import-boundary, regeneration, and legacy-build checks. Confirm the current PCB and generated production board outputs are byte-for-byte untouched.

**Test scenarios:**

- All focused domain and split-contract tests pass together.
- The planned split contract is blocked only for explicitly unresolved physical prerequisites.
- `make regen-check`, script manifest, import boundaries, Ruff, and diff checks pass.
- No change appears under `pcb/`, DRC ceilings, oracle pins, or generated production board artifacts.

## Verification Contract

- Focused: `uv run pytest -q scripts/tests/test_check_domain_partition.py scripts/tests/test_check_split_board_contract.py`.
- Adjacent: `uv run pytest -q scripts/tests/test_netlist_stage_checks.py`.
- Static: Ruff on changed Python files and `uv run python scripts/import_linter_gate.py`.
- Repository metadata: script manifest gate, invocation tracing, and `make regen-check`.
- Readiness gate: `make check-split-board` returns the expected blocked verdict for the committed planned manifest and names each unresolved prerequisite.
- Atopile compatibility: run the existing production build/check path and verify `src/main.ato:Top` remains the sole production entrypoint.
- Diff safety: `git diff --check` and an explicit assertion that no files under `pcb/`, `power_pcb_dataset/drc_ceiling.json`, or `scripts/oracle_hashes.json` changed.

## Definition of Done

- The plan's ten-net interface, board ownership, and physical readiness rules have one non-conflicting representation each.
- Every R-ID and AE-ID is covered by an implementation unit and passing focused test.
- The committed migration state is valid but generation-blocked for named physical prerequisites.
- The existing single-board production artifact and build remain unchanged.
- All Verification Contract checks pass, or any pre-existing failure is reproduced on the untouched base and recorded as a residual.
- The implementation is committed on the feature branch and is ready for independent review and delivery.
