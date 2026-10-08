# Verification of the digital corrections — 2026-10-03

The user confirmed there is no assembled hardware. All physical qualification
remains `NOT_RUN`. These results establish specified source, arithmetic and
nominal geometry properties only.

| Check | Result and evidence boundary |
|---|---|
| Standalone coil model | 11/11 Rust tests pass. The high-line/carbon-pan case failed before replacing the obsolete 85 A screen with the source's 45 A normal-operation analysis allocation. This allocation is not an implemented regulator or measured protection guarantee. |
| Standalone power model | 6/6 Rust tests pass. Selected four-single-switch topology is distinguished from historical parallel-device and half-bridge comparisons. |
| Model output preservation | Both final optimized binaries reproduce their saved outputs byte for byte after simplification; coil uses default seed 20260925 and n=20000. |
| HOT5 circuit candidate | Atopile 0.2.69 compilation/export passes: 142 parts / 88 nets. Rust connectivity audit and 58/58 tests pass, including five deliberately broken HOT5 circuits. All eight hashes in `zapote/power-stage-120v/build-receipt.json` match final files. |
| Existing component identity | Compared final path-to-designator map to `fda5ab9ece24ef1ee6f2317604c5ca73367d5201:zapote/power-stage-120v/frozen/default.net`: 135/135 old designators preserved, seven new parts appended. The old frozen file supplies the reference map, not proof of current component values; the new resolved export supplies current identity. |
| R4 complete STEP | Sol worker rebuilt 406 named parts and reimported 434 valid solids. Assembly SHA-256: `2e89923f65e466831395a10a2ac7e307ded48fbb8b49e5c19e87b4da1df21291`. Parent verified all recorded CAD source/input hashes. |
| R4 panel and compartment | 19/19 nominal panel checks pass; ten prior compartment hits become zero. Historical PCB distances are geometric only. The general checker has 18 computed passes, one inherited click-stack failure, and physical qualification unverified. |
| Independent saved-part correspondence | Cadgen/build123d compared 257 named occurrences with individual saved STEP files: all match under its bounds/volume/solid-count criteria. This is not topological equivalence or a fit claim for native-18. |
| Service and visual inspection | Sampled top-cover lifts at 1, 5 and 26 mm clear the checked historical assembly; a direct rear lid pull collides at 5 mm. Fresh CadQuery/Matplotlib section visually inspected. The cadgen snapshot service was unavailable, so no successful new browser/snapshot render is claimed. |
| Snapshot path regression | Wrapper run from `/private/tmp` resolves all eight input/output paths inside this package. Absolute and escaping template paths are rejected. This verifies job preparation, not the unavailable rendering service. |
| Repository gates | `make regen` and `make regen-check` pass after adding the skills/output/zapote directory descriptions. Import boundary gate passes: five contracts kept, zero broken, using `PYTHONPATH=packages/temper-placer/src` and import-linter 2.14. `git diff --cached --check` passes. |
| Python checks | All CAD and export helpers compile. Ruff 0.16.5 passes for the new service/section/snapshot helpers, circuit exporter and directory-map update. The imported CAD suite still has 235 findings, predominantly inherited compact style/unused names. The repository's unchanged `packages/` lint target has 581 findings. These are recorded as failures, not waived passes; no broad unrelated cleanup was applied. |

No native KiCad board was edited, so no new routing, ERC/DRC, fabrication,
or DRC-ceiling result is claimed. Native-18 remains the 135-part board;
the HOT5 source candidate still needs native layout integration. The R4
historical PCB input is not native-18. Full repository firmware/placer tests
were not run for this isolated circuit/model/CAD change.

See [remaining dependencies](README.md#remaining-dependencies-in-order)
for the unresolved power envelope, current-board cooling/package, switch
travel/force, insulation/material, and physical test requirements.
