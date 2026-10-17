# Standalone thermal sensing / Rev A

A separate 66 × 43 mm, two-layer board monitors a heatsink and coil through two external lug NTC sensors. Each channel exposes an active-high hot flag and its analog sense voltage. The intended nominal thresholds are 85/70 °C trip/release for the heatsink and 120/100 °C for the coil.

Atopile source → strict native generation → agent-authored placement/routes → Rust and KiCad validation is the construction flow. No placement or routing search algorithm was introduced or run. This is a digital construction milestone; physical protection performance is not qualified.

- [PCB](candidate/section.kicad_pcb), [KiCad project](candidate/section.kicad_pro), [schematic PDF](evidence/schematic.pdf), [3D view](evidence/board-3d.png).
- [Source](../../elec/src/thermal_sense_unit.ato), [interfaces](INTERFACES.md), [parts](BOM.md), [model](MODEL.md).
- [Acceptance](ACCEPTANCE.md), [validation and replay](VALIDATION.md), [memory](memory/README.md).

The sensors mount remotely. The PCB connectors stay in a cooler location; there is no enclosure. An open sensor or short to supply reads cold. The unit contains no open-sensor diagnostic or shutdown latch. These limitations must be addressed in the interlock/integration design.

Luna supplied circuit analysis and Rust implementation; the coordinator reviewed and corrected the work, authored the native layout, and retained independent checks. The next standalone unit is the safety interlock. Whole-cooker integration follows the separate-unit milestones.
