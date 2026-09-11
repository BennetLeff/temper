# Buck Rev A release checklist — status: READY FOR ORDER REVIEW (2026-09-10)

Final export must be regenerated against the replacement frozen Rev A. No purchase or fabrication order is authorized. C11/C12 use Samsung CL32B226KAJNNWE; Samsung DC-bias behavior remains unverified.

## Preparation (done)

- [x] `procurement/bom.csv` reconciled to Atopile core + frozen connector selection (9 core + J1/J2).
- [x] `procurement/digikey.csv` has dated exact SKUs, packaging, stock and CT prices; Samsung C11/C12 replacement is recorded with its qualification limit.
- [x] `procurement/quantity-worksheet.csv` — 5 bare / 2 populated planning assumption; installed vs spares separated.
- [x] `export-release.sh` validates complete manifest/freeze binding, snapshots identity, uses schematic parity and invalidates stale artifacts on failure.
- [x] Frozen fabrication/assembly notes document the JLCPCB capability match and manual treatment for unfilled via-in-pad joints.

## Export + inspection

- [x] Board freeze present with file hashes, tool version, connector pinout, TP population, fab spec.
- [x] Export run against exact revision; source hashes match before and after.
- [x] Native ERC/DRC: zero errors, zero unrouted, zero schematic-parity issues and no warnings.
- [x] Gerbers and drills inspected; review record is `verification/visual-review.md`.
- [x] ZIP opened and compared to manifest: 15 intended fabrication entries, no stale docs/procurement files.
- [x] BOM ↔ positions ↔ schematic/PCB reconciled: 9 SMT + 2 manual THT refs; no TP5 or synthetic terminals.
- [x] Docs consistently label J1.1 VIN/J1.2 GND/J2.1 3V3/J2.2 GND.

## Acceptance (plan 2)

- [x] All purchased population has exact MPNs + dated DigiKey mapping; Samsung C11/C12 substitution and qualification limit are explicit.
- [x] Installed / order / spares quantities separated and consistent.
- [x] CAD, BOM, coordinates, Gerbers, drills, drawings describe one frozen revision.
- [x] Exported layers + final ZIP visually inspected and checksummed.
- [x] Assembly + fabrication notes specify actual stackup, pinout, via-in-pad treatment and population.
- [x] Second agent can regenerate via documented tool + command.
- [x] Status distinguishes "ready for order review" from "ordered / assembled / qualified".

## Stop conditions

Stop final release for: mismatched freeze, incorrect footprint/pinout, missing essential manufacturing output, native error, unreviewed warning, or a part with no feasible purchasing path. Missing optional 3D cosmetics or unresolved later thermal/model qualification alone do not block. Do not run unrelated firmware/placer/harness suites for export-only work. Do not alter production DRC ceilings.

Ordering instructions: preparing this package does NOT authorize purchase or fabrication. A later explicit order decision is recorded separately as "ordered".
