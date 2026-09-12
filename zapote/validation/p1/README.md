# P1 power paths, domains, and insulation

The P1 Rust owners are `zapote-drc::power_integrity` and
`zapote-erc::domain_contract`. They return the shared `CheckReport` and keep
object IDs, actual values, required values, population gaps, and
`indeterminate` status visible to the caller.

`validate_ampacity` requires an authored RMS current and finished copper
thickness for every path. It evaluates the native trace IDs with the copied
IPC external-layer scalar, checks every referenced via's copper annulus, and
requires native component-pad IDs. Peak current is retained in the contract
for review but is not silently substituted for RMS or converted into a
thermal claim. A 15 A PFC path therefore cannot escape through the donor's
old `>=20 A` selector.

`validate_isolation` requires an explicit barrier population. Missing barrier
records are indeterminate; an authored absent barrier fails; missing material,
cutout, or surface-path evidence stays indeterminate. Clearance and package
dimensions are never reported as creepage proof.

`validate_gate_drive` and `validate_pfc` are explicit adapters over the exact
pin/domain checker. `domain_contract` checks every reviewed package pin,
intentional NCs, expected domain classification, allowed crossings, and a
barrier identity for each observed crossing. It rejects unlisted crossings
and missing crossing evidence.

## Baseline evidence

The saved candidate inputs are the routed PFC at
`zapote/power-entry/candidate/section.kicad_pcb` and the routed gate-drive
candidate at `zapote/gate-drive/candidate/section.kicad_pcb` (their hashes and
existing native receipts are retained in each unit's `evidence/` directory).
The pre-P1 unit reports remain `INDETERMINATE`: they do not contain the
explicit current-path or complete insulation populations required by these
owners. That result is preserved in `baseline-2026-09-12.json`; no physical
qualification pass is inferred from the existing native DRC or clearance
reports.

The tests cover a passing reviewed contract, a narrow real trace, a removed
via annulus, a missing barrier, a missing observed crossing, a misclassified
feedback tap, and an intentional NC that is accidentally netted. Full
surface-path qualification remains incomplete until supported cutout/material
assumptions and an independent native path oracle are supplied.
