# Standalone thermal sensing / Rev B

A separate 100 × 45 mm, two-layer board monitors a heatsink and coil through two external lug NTC sensors. Both channels now assert their active-high fault output for overheating, either sensor lead disconnected, or a sensor short to ground/supply, within the conditional electrical model. Nominal hot trip/release targets remain 85/70 °C for the heatsink and 120/100 °C for the coil.

Each channel has a hot comparator, a separate open-wire comparator and a logic OR gate. The coil resistor network was retuned to separate a connected 0 °C sensor from an open wire. There is no enclosure. The sensors mount remotely, while the board and connectors remain in a cooler location.

- [PCB](candidate/section.kicad_pcb), [KiCad project](candidate/section.kicad_pro), [schematic PDF](evidence/schematic-revb.pdf), [3D view](evidence/board-revb-3d.png).
- [Source](../../elec/src/thermal_sense_unit.ato), [interfaces](INTERFACES.md), [parts](BOM.md), [model](MODEL.md).
- [Acceptance](ACCEPTANCE.md), [validation and replay](VALIDATION.md), [memory](memory/README.md).

Atopile source → strict native generation → agent-authored placement/routes → Rust and KiCad validation remains the construction flow. Luna supplied Rust implementation and circuit review; the coordinator authored the native routing and corrected model defects through counterexamples. No placement or routing algorithm was added.

This is a digital construction milestone. Bench tests remain NOT RUN. Comparator/loading allowances, temperature accuracy, fault timing and physical harness behavior still need qualification. The next standalone safety-interlock unit owns latching, deliberate reset, power-loss handling and heater shutdown. Whole-cooker integration follows the separate-unit milestones.
