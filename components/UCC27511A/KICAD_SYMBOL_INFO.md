# UCC27511A KiCad Symbol - Technical Details

## Symbol Visual Layout

```
                VDD (Pin 1)
                    │
                    ▼
    ┌───────────────────────────┐
    │                           │
    │      UCC27511A            │
IN+ │                           │ OUTH
 ───┤6   ┌─────────┐           2├───
    │    │ ▶       │            │
    │    │ DRIVER  │            │
IN- │    │ 4A/8A   │            │ OUTL  
 ───┤5   └─────────┘           3├───
    │                           │
    │                           │
    └───────────────────────────┘
                    │
                    ▼
                GND (Pin 4)
```

## Pin Definitions

### Power Pins
- **Pin 1 (VDD)**: Power input, 4.5V to 18V
  - Type: `power_in`
  - Requires bypass: 10μF + 100nF ceramic
  - Typical: 12V for induction cooker

- **Pin 4 (GND)**: Ground reference
  - Type: `power_in`
  - Connects to IGBT emitter (low-side configuration)
  - NOT mains ground in induction cooker!

### Input Pins
- **Pin 6 (IN+)**: Non-inverting input
  - Type: `input`
  - TTL/CMOS compatible (VIH = 2.2V, VIL = 1.2V)
  - Input resistance: 200kΩ
  - Typical: Connect to MCU PWM output

- **Pin 5 (IN-)**: Inverting input
  - Type: `input`
  - TTL/CMOS compatible
  - Typical: Tie to GND for non-inverting operation
  - Can be used as DISABLE input (active high)

### Output Pins
- **Pin 2 (OUTH)**: High-side output (source)
  - Type: `output`
  - Peak current: 4A (source)
  - Output resistance: 6Ω
  - Use for: Turn-ON path with higher resistance

- **Pin 3 (OUTL)**: Low-side output (sink)
  - Type: `output`
  - Peak current: 8A (sink)
  - Output resistance: 0.5Ω
  - Use for: Turn-OFF path (recommended for single-output use)

## SPICE Integration Properties

The symbol includes these SPICE properties for seamless simulation:

| Property | Value | Description |
|----------|-------|-------------|
| `Spice_Primitive` | `X` | Subcircuit type |
| `Spice_Model` | `UCC27511A` | Model name to instantiate |
| `Spice_Lib_File` | `UCC27511A.lib` | Library file path |
| `Spice_Netlist_Enabled` | `Y` | Enable SPICE netlist generation |

### SPICE Netlist Example

When used in KiCad, this symbol generates:

```spice
XU1 VDD GND INP INN OUTH OUTL UCC27511A
```

Where:
- `XU1` = Instance name (reference designator)
- Pin order matches subcircuit definition in `UCC27511A.lib`

## Metadata Properties

### Component Information
- **Value**: UCC27511A
- **Description**: 4A/8A Single-Channel High-Speed Low-Side Gate Driver, SOT-23-6
- **Manufacturer**: Texas Instruments
- **MPN**: UCC27511ADBVR

### Documentation Links
- **Datasheet**: https://www.ti.com/lit/ds/symlink/ucc27511a.pdf
- **Product Page**: https://www.ti.com/product/UCC27511A

### Search Keywords
- gate driver
- low-side
- IGBT
- MOSFET
- induction cooker

### Footprint Assignment
- **Default Footprint**: `Package_TO_SOT_SMD:SOT-23-6`
- **Package**: SOT-23-6 (DBV)
- **Dimensions**: 2.90mm × 1.60mm × 1.10mm (L×W×H)

## Symbol File Format

- **Format**: KiCad S-expression (version 20220914)
- **Generator**: kicad_symbol_editor
- **Compatibility**: KiCad 6.0 and later

## Usage in Different KiCad Versions

### KiCad 6.x / 7.x / 8.x
✅ Fully compatible - use as-is

### KiCad 5.x
⚠️ Not directly compatible - KiCad 5 uses .lib format
- Option 1: Upgrade to KiCad 6+
- Option 2: Manually recreate symbol in KiCad 5 symbol editor

## Symbol Quality Checklist

- ✅ Pin numbers match datasheet (1-6)
- ✅ Pin names match datasheet exactly
- ✅ Pin types correct (power_in, input, output)
- ✅ Visual layout clear and logical
- ✅ Reference designator "U" (standard for ICs)
- ✅ Footprint assignment included
- ✅ Datasheet link included
- ✅ SPICE model properties set
- ✅ Description complete
- ✅ Keywords for searchability
- ✅ Manufacturer information

## Common Schematic Patterns

### Pattern 1: Basic Gate Driver
```
U1: UCC27511A
  Pin 1 (VDD)  ← 12V supply
  Pin 6 (IN+)  ← MCU PWM
  Pin 5 (IN-)  ← GND
  Pin 3 (OUTL) → Gate resistor → IGBT
  Pin 2 (OUTH) ← Not connected
  Pin 4 (GND)  ← GND
```

### Pattern 2: Split Output Drive
```
U1: UCC27511A
  Pin 2 (OUTH) → 15Ω → Schottky → IGBT gate
  Pin 3 (OUTL) → 5Ω → Schottky → IGBT gate
```

### Pattern 3: Inverting Mode
```
U1: UCC27511A
  Pin 6 (IN+)  ← VDD (via 1kΩ)
  Pin 5 (IN-)  ← MCU PWM (inverted signal)
  Pin 3 (OUTL) → Gate
```

## Bill of Materials (KiCad BOM)

When used in schematic, exports to BOM as:

| Reference | Value | Footprint | MPN | Qty |
|-----------|-------|-----------|-----|-----|
| U1 | UCC27511A | Package_TO_SOT_SMD:SOT-23-6 | UCC27511ADBVR | 1 |

---

## Support

For questions about the symbol or SPICE model:
- See: `UCC27511A_Documentation.md`
- See: `README.md`
- TI Support: https://e2e.ti.com/

**Symbol Version**: 1.0  
**Date**: December 9, 2025  
**Status**: ✅ Production Ready
