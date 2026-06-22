---
date: 2026-06-21
topic: gerber-first-board-order
status: ready-for-planning
---

# Requirements: Temper Gerber-First Board Order

## Goal

Order a physical v1.0 board that validates MCU bring-up and the complete LV sensor stack:

- MCU (ESP32-S3-WROOM-1-N8R8) boots from flash and runs firmware
- MAX31865 RTD interface responds over SPI
- NTC thermistor reads temperature through the ADC
- Safety interlock logic functions correctly

All HV components (LLC inverter, half-bridge, 340V DC bus circuitry) are marked DNP. The board is a safe, shippable LV-only artifact that ends the zero-physical-boards streak and produces real hardware learnings.

## Problem

Six months of work have been invested in routing, design rule enforcement, and schematic correctness — and zero physical boards have been fabricated. Hardware issues that simulation cannot surface (GPIO contention, SPI timing, NTC ADC noise floor, interlock race conditions) are unknowable until a board exists. The 6 schematic P0 bugs all affect the HV section; the LV section is electrically independent and has no blocking bugs. Waiting for HV to be clean before ordering any board is the wrong sequencing. JLCPCB delivers 5 boards in 5 days for ~$30.

## Success Criteria

1. MCU boots: ESP32-S3-WROOM-1-N8R8 runs bring-up firmware and USB serial output is visible
2. SPI: MAX31865 responds to a register read over SPI; a valid RTD resistance value is returned
3. NTC ADC: thermistor voltage divider reads a temperature within ±2°C of ambient
4. Interlock: safety interlock logic asserts and de-asserts correctly in response to firmware-driven test conditions
5. No HV components are present on the board (verified by visual inspection against the DNP list)

## Scope

### Pre-Order Checklist

**1. Verify LV DRC violations**

Current routing has 228 DRC violations, all believed to be in the HV section. Before Gerber export, run KiCad DRC and confirm zero violations touch LV nets. Specifically check:

- MCU power rails and GPIO nets
- SPI bus nets (MOSI, MISO, SCK, CS for MAX31865)
- NTC voltage divider nets
- Interlock signal nets
- LV ground plane continuity

If any LV violations exist, fix them. Do not fix HV violations — those are v1.1 work.

**2. DNP markup for all HV components**

Mark every component in the HV section as DNP in the KiCad schematic/BOM before Gerber export. HV section includes at minimum:

- Half-bridge MOSFETs and gate drivers
- LLC resonant tank components (inductors, resonant capacitors)
- HV bus capacitors
- LMR51430 switching regulator (wired at 340V — do not populate)
- EMI filter components (if present on board)
- Pan detection components (if present on board)
- Any component with a net connected to DC_BUS+, DC_BUS-, or SW_NODE

The DNP list must be reviewed against the schematic net list before submission. A mis-marked component that gets populated on the HV section is a safety hazard.

**3. Gerber export checklist**

- [ ] KiCad DRC passes with zero violations on LV nets
- [ ] DNP list exported and verified against schematic
- [ ] Gerber files generated for all 4 layers (F.Cu, In1.Cu, In2.Cu, B.Cu)
- [ ] Drill file exported
- [ ] Board outline (Edge.Cuts) present in Gerber set
- [ ] Silkscreen includes board version label: `v1.0-LV-ONLY`
- [ ] Gerber set reviewed in a Gerber viewer (e.g., JLCPCB's online viewer) before submission
- [ ] BOM exported with DNP column populated for all HV components
- [ ] JLCPCB order confirms: 4-layer, ENIG or HASL, standard 1.6mm, 5 boards

**4. Bring-up firmware**

A minimal bring-up firmware image must exist before the boards arrive. Required:

- USB serial output on boot (confirms MCU boots and USB stack works)
- SPI register read from MAX31865 (read configuration register 0x00; confirm 0x00 default value or write/readback)
- ADC read on NTC pin (raw ADC value printed to serial; temperature conversion optional for first pass)
- Interlock GPIO test (drive interlock output, read interlock feedback, confirm logic)

Firmware lives in `firmware/`. No production control loop logic is required. The bring-up image is a standalone test sketch.

## Bring-Up Sequence

Ordered from safest to most complex. Do not advance to the next step until the current step passes.

1. **Power-on**: Apply 3.3V LV supply. Confirm no smoke, no excess current draw, voltage rails nominal.
2. **MCU boot**: Connect USB. Confirm serial output appears. Confirm flash size (8MB) and PSRAM (8MB) are reported correctly by IDF boot log.
3. **SPI — MAX31865**: Run SPI register read. Confirm response. Write a known value to a writable register, read it back.
4. **NTC ADC**: Read NTC voltage divider. Confirm ADC value changes when touching the thermistor. Confirm temperature value is physically plausible.
5. **Safety interlock**: Drive interlock output GPIO. Confirm interlock feedback GPIO responds. Test both assert and de-assert transitions.

## Out of Scope

- HV bring-up of any kind — no HV components are populated; no HV testing occurs on v1.0 boards
- Routing changes to the HV section — those belong in v1.1
- Schematic P0 bug fixes — all 6 P0 bugs are in the HV section; fix them in v1.1 while v1.0 is in transit
- LLC resonant tank tuning or inverter validation
- Pan detection or EMI filter circuit work
- Production firmware or control loop implementation
- Any changes to `design_rules.py`, `.kicad_dru`, or the DRC runner — clean-base-sprint work, separate workstream

## Dependencies and Risks

**DNP markup completeness**: The single highest-risk item. Every HV net must be traced to its components and every such component must be DNP'd. A missed component that gets assembled creates a safety hazard. Mitigation: cross-reference DNP list against `TEMPER_NET_CLASSES` HV net assignments in `packages/temper-placer/temper_placer/core/design_rules.py` before submission.

**LV DRC violations unknown**: The 228 violations are believed to be HV-only, but this has not been verified by running DRC with HV components hidden/excluded. Must be confirmed before Gerber export. If LV violations exist, fix them in the current board file without touching HV routing.

**Bring-up firmware availability**: Firmware must be written before boards arrive. Five days is sufficient time if started at order placement. Risk: if firmware is not ready, board sits idle.

**4-layer stackup in Gerbers**: JLCPCB's default 4-layer stackup (JLC04161H-7628) must match the stackup configured in `pcb/temper.kicad_pcb`. Verify layer assignments match before export.

**LV/HV ground plane separation**: If the LV and HV ground planes share a net and are connected on the board, the DNP'd HV components still leave copper stubs. Confirm LV ground is safe to probe with standard bench equipment even with HV copper present but unpopulated.
