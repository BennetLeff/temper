# Reference Layouts for Validation

This directory contains hand-placed PCB layouts used as ground truth for validating optimizer output.

## Layouts

### 1. temper_final.kicad_pcb
**Description:** Final hand-routed Temper induction cooker PCB

**Status:** TODO - Create from actual Temper design

**Contents should include:**
- Full half-bridge topology with IKW40N120H3 IGBTs
- UCC21550 gate drivers with bootstrap supplies
- ESP32-S3 MCU with all peripherals
- LMR51430 buck converters for auxiliary power
- MAX31865 RTD interface
- Sensing circuits (current transformers, voltage dividers)
- Safety interlocks (watchdog, protection circuits)
- All power and signal routing complete
- Proper clearances for HV (high voltage) sections
- Thermal reliefs for heat-generating components

**Metrics (estimated):**
- Components: ~80
- Nets: ~150
- Board size: ~150mm × 100mm
- Layers: 4 (top, bottom, internal power, internal signal)
- Total wirelength: ~2500 mm
- DRC violations: 0
- Routing completion: 100%

---

### 2. half_bridge.kicad_pcb
**Description:** Simplified power stage only (no MCU, no control)

**Status:** TODO - Create

**Contents should include:**
- Half-bridge topology (2x IKW40N120H3 IGBTs)
- UCC21550 gate drivers
- DC bus input terminals
- Output inductor terminals
- Bootstrap capacitors and diodes
- Gate drive power supply
- Current sense circuitry

**Metrics (estimated):**
- Components: ~20
- Nets: ~30
- Board size: ~80mm × 60mm
- Layers: 2 (top, bottom)
- Total wirelength: ~600 mm
- DRC violations: 0
- Routing completion: 100%

---

### 3. gate_driver.kicad_pcb
**Description:** UCC21550 gate driver evaluation board

**Status:** TODO - Create

**Contents should include:**
- UCC21550 gate driver IC
- Input logic (PWM, enable signals)
- Bootstrap capacitor
- Gate resistors
- Output clamp diodes
- Test points for measurements
- Power supply decoupling

**Metrics (estimated):**
- Components: ~15
- Nets: ~25
- Board size: ~50mm × 50mm
- Layers: 2 (top, bottom)
- Total wirelength: ~200 mm
- DRC violations: 0
- Routing completion: 100%

---

## Creating Reference Layouts

To create actual reference layouts from the existing KiCad schematics:

1. **Layout the board in KiCad:**
   - Open corresponding schematic (e.g., `pcb/half_bridge.kicad_sch`)
   - Create netlist: Tools → Generate Netlist
   - Switch to PCB editor
   - Update PCB from netlist: Tools → Update PCB
   - Place components manually following best practices
   - Route all nets (auto-route with manual touch-up)
   - Run DRC: Inspection → DRC (Alt+D)
   - Fix all violations

2. **Export to this directory:**
   - File → Export → PCB
   - Save as `temper_final.kicad_pcb` (or appropriate name)
   - Place in this `data/reference_layouts/` directory

3. **Document metrics:**
   - Component count
   - Net count
   - Board dimensions
   - Layer count
   - Wirelength summary
   - DRC violation count
   - Routing completion rate

## Validation Usage

Once reference layouts exist, use them with `temper-validate` CLI:

```bash
# Compare optimizer output against hand-placed reference
temper-validate compare optimized.kicad_pcb \
    data/reference_layouts/temper_final.kicad_pcb \
    --output comparison.md \
    --format markdown

# Score optimizer placement
temper-validate score optimized.kicad_pcb \
    --reference data/reference_layouts/temper_final.kicad_pcb

# Generate visual comparison
temper-validate visualize \
    data/reference_layouts/temper_final.kicad_pcb \
    optimized.kicad_pcb \
    --output comparison.html
```

## Notes

- These are **hand-placed** layouts, not optimizer output
- They represent the "gold standard" for validation
- Optimizer should aim for:
  - Wirelength within 10% of reference
  - DRC score ≥ 80
  - Routing completion ≥ 95%
  - Aggregate score ≥ 80

- TODO: Create actual `.kicad_pcb` files from existing schematics
