---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implemented-digital-gate
product_contract_source: "2026-09-23 Zapote remaining-roadmap parallel plan, R6"
title: "Zapote integration readiness: source-locked port and fault graph"
date: 2026-09-23
execution: code
---

# Integration readiness milestone

## Decision

Determine whether the current standalone units and Rev38 interface can enter cooker-board composition. This gate is an integration **readiness** check, not a PCB, whole-board acceptance, or energized appliance test. The current answer is **BLOCKED**. No integrated board is edited.

## Inputs and authority

`zapote/integration/sources.tsv` binds each consumed Rev38 source, standalone source/native board, and relevant interface receipt by SHA-256. `units.tsv` preserves the closed unit acceptance-status inventory, including prior buck/MCU units whose exact source/native identities are not bound here. `ports.tsv` declares every named boundary with source statement and native connector pad/net where one exists; source-only and missing endpoints stay distinct from digitally constructed native endpoints. The checker re-hashes all locks and resolves native pad/net assignments from the actual saved KiCad board bytes. A name match in prose or a manually compatible domain is insufficient. Revision base is `a599fd27fe67f82afa4ee64f9fa7d2bc0fd6c19f`; the active Rev38 checkout is not consulted.

`edges.tsv` closes the required connection registry. `faults.tsv` closes seven sensing/fault contributors. Each contributor must account for open-wire, unpowered remote behavior, global validity, PFC inhibit, inverter inhibit and stop timing. Current source/native acceptance remains standalone digital construction only. A future integration gate may promote a connection only after the exact selected unit sources, physical/electrical contracts, both stop paths, and native identity are independently accepted and bound. A `READY_FOR_DESIGN` outcome permits composition work; it is not a release or physical qualification verdict.

## Planned checks and outcome

1. Reject altered, missing or unlocked inputs; reject absent source assertions or changed connector pin/net assignments.
2. Block direct Rev38 `VB_BANK/HOT0` into the legacy 170 V/0–250 V voltage-sense interface, including its common host return. Block HOT0-to-SELV and PFC HOT RUN used as gate-drive PERMIT.
3. Preserve the distinct `HV_RETURN` to `HOT0` low-side Kelvin/isolated-bias join as indeterminate until the exact join, bias isolation and return-current path are reviewed.
4. Block missing global `SENSOR_LIVE`, VD=VB as F2 continuity evidence, and omitted fan-off discharge heating.
5. Trace each sensing/cooling/auxiliary fault through interlock to **both** PFC and inverter stop; open-wire and unpowered remote states cannot be assumed safe from powered standalone Boolean behavior. Keep timing unknown until captured.
6. Preserve programming/UI reset and pin conflicts as a blocked integration dependency. Coordinator R5 work at `ab49fd5c3` is newer than this worktree base and must be source-locked when the branches integrate.

## Replay and handoff

Compile `zapote/integration/check.rs` with `rustc --edition=2021 -D warnings`; run the tests and then the CLI from repository root. The CLI's exit code 2 means blocked or indeterminate, and `matrix.tsv` is the deterministic current result. `RECEIPT.md` records tested commands and the exact remaining design/physical gates. Neither the source lock nor this checker qualifies a live stop or a whole-board wiring path.
