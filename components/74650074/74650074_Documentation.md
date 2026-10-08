# Würth 74650074 — M4 PCB power terminal

**Selected part:** Würth Elektronik REDCUBE THR WP-THRBU 74650074. Six instances are used: J2/J5 are separate coil lead terminals, J7/J8 are the positive removable-link ends, and J9/J10 are the negative removable-link ends. An external insulated jumper, never PCB copper, completes each link in normal service.

The stock KiCad footprint is `TerminalBlock_Wuerth:Wuerth_REDCUBE-THR_WP-THRBU_74650074_THR`. It has four physical solder pads **all numbered 1** because they belong to one metal terminal; source `PowerTerminalM4.p1` maps to logical pin 1. The center screw hole is non-plated and is not a net pin. The routing replayer rejects `J*.1` as ambiguous for these parts, so later routes must select and verify physical pad coordinates individually.

Würth specifies **50 A maximum at 20 °C**, **1.2 N·m** screw torque, **1.6–2.0 mm actual PCB thickness** and **THR reflow** assembly; wave soldering is not applicable. The nominal 1.6 mm planning stackup needs a fabricator tolerance check. The 50 A part rating does not establish current capacity through the assembled PCB, copper, lug and wire. The bare terminal has **no manufacturer voltage rating**; coil stud separation, exposed lugs, screws, wiring, high-frequency voltage and fault stress require a system insulation review. Initial coil-stud placement target is ≥30 mm centers, to be checked with actual lugs and enclosure geometry. Confirm hot current capacity, torque retention and vibration performance before powered service.

Sources: [Würth datasheet](https://www.we-online.com/components/products/datasheet/74650074.pdf), [power-stage source](../../zapote/power-stage-120v/elec/src/parts.ato), [terminal and jumper assembly](../../zapote/power-stage-120v/ASSEMBLY.md).
