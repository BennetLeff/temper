# Footprint-as-Code (FaC) Workflow for Temper

This project uses Atopile to define PCB footprints programmatically, ensuring that thermal management and high-voltage safety rules are baked into the component geometry.

## Core Utilities (`fac_utils.ato`)
- **ThermalViaArray**: Generates grids of stitching vias for power components.
- **HighCurrentPad**: Through-hole pads with annular rings sized for high-ampacity connections.
- **CreepageSlot**: Generates internal PCB cutouts to meet IEC 60335 creepage requirements.

## Generative Footprints (`footprints.ato`)
- **IGBT_TO247**: Optimized for IKW40N120H3 with collector thermal via arrays.
- **SOIC16W_Isolated**: For UCC21550, featuring an 8mm creepage slot between primary and secondary sides.
- **LitzPad_15A**: 2.5mm drill pad for resonant tank Litz wire bundles.
- **CST1005_Footprint**: Current transformer footprint with safety-compliant primary clearance.

## Pipeline Integration
Run `make footprints` to trigger the generation. The footprints are referenced by name in the BOM and can be exported to the `pcb/footprints.pretty` library.

## Best Practices
1. **DRY**: Always use the primitives in `fac_utils.ato` rather than raw dimensions.
2. **Safety First**: Assert creepage distances in code before generating the slot geometry.
3. **Thermal-First**: Every power pad should have an associated `ThermalViaArray`.
