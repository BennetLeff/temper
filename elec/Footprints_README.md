# Footprint-as-Code (FaC) Workflow for Temper

This project uses Atopile to define PCB footprints programmatically, ensuring that thermal management and high-voltage safety rules are baked into the component geometry.

## Core Utilities (`fac_utils.ato`)
- **ThermalViaArray**: Generates grids of stitching vias for power components.
- **HighCurrentPad**: Through-hole pads with annular rings sized for high-ampacity connections.
- **CreepageSlot**: Generates internal PCB cutouts to meet IEC 60335 creepage requirements.

## Generative Footprints (`footprints.ato`)
- **IGBT_TO247**: Optimized for IKW40N120H3 with collector thermal via arrays.
- **SOIC16W_Isolated**: For UCC21550 (U7), featuring a 6.0x11.2mm routed
  creepage slot between the primary and secondary pin rows -- 8.627mm
  governing creepage, verified in
  `docs/evidence/2026-07-28-isolator-creepage-slots.md`. The real footprint
  is `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`; this `.ato` module is
  a documentation-synced placeholder, not the generation source (see
  `Makefile`'s `footprints` target).
- **H11L1_DIP6_Isolated**: For the H11L1 ZCD optocoupler (U3), a routed
  DIP-6_W7.62mm land pattern with a 5.0x9.0mm creepage slot between the two
  pin rows -- 9.128mm governing creepage. Real footprint:
  `pcb/libs/lib.pretty/H11L1_DIP6_Isolated.kicad_mod`.
- **LitzPad_15A**: 2.5mm drill pad for resonant tank Litz wire bundles.
- **CST1005_Footprint**: Current transformer footprint with safety-compliant primary clearance.

## Pipeline Integration
Run `make footprints` to trigger the generation. The footprints are referenced by name in the BOM and can be exported to the `pcb/footprints.pretty` library.

## Best Practices
1. **DRY**: Always use the primitives in `fac_utils.ato` rather than raw dimensions.
2. **Safety First**: Assert creepage distances in code before generating the slot geometry.
3. **Thermal-First**: Every power pad should have an associated `ThermalViaArray`.
