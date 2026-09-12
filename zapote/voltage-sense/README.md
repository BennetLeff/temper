# Standalone voltage sensing / OVP

A separate 78 × 42 mm, two-layer board for monitoring the cooker's **positive half-bus** and asserting a hardware overvoltage signal. Atopile source → strict native generation → agent-authored placement/routes → Rust and KiCad checks are complete. This is a digital construction milestone; device applicability, physical qualification and integration remain open.

- [Native PCB](candidate/section.kicad_pcb), [KiCad project](candidate/section.kicad_pro), [schematic PDF](evidence/schematic.pdf), [3D view](evidence/board-3d.png).
- [Source](../../elec/src/voltage_sense_unit.ato), [interfaces](INTERFACES.md), [BOM](bom/README.md).
- [Acceptance](ACCEPTANCE.md), [validation and replay](VALIDATION.md), [model and official sources](MODEL.md), [lessons](memory/README.md).

J1 accepts a low-current sense connection; this board does not carry cooker load current. J2 provides host power, common return, OVP and analog monitor. The host interface is **not isolated**. The 3D view omits J1's body model; its actual footprint is present. There is no enclosure.

Luna agents supplied circuit analysis, arithmetic review and implementation drafts. The coordinator corrected drafts, authored the final drawing and routing, ran checks and reviewed native renders. No placer or router search algorithm was introduced or run. Existing full-cooker source and firmware were not changed to imply integration.

Next: the standalone thermal-protection unit, followed by the remaining units in the cooker roadmap. Integration comes after unit milestones.
