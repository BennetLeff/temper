# Safety Clearances Analysis for Temper PCB

## The Problem

Standard component packages have pin clearances that violate IEC 60664-1 when used at high voltages:

| Component | Voltage | Required | Actual | Status |
|-----------|---------|----------|--------|--------|
| TO-247 IGBT | 400V | 2.0mm | 1.95mm | MARGINAL |
| QFN-56 | 3.3V | 0.2mm | 0.16mm | OK (low voltage) |
| USB-C | 3.3V | 0.2mm | 0.1mm | OK (low voltage) |

## Professional Solutions

### 1. Conformal Coating (Recommended)

Apply conformal coating to the entire board. This changes the pollution degree from 2 to 1, which dramatically reduces clearance requirements:

| Voltage | PD2 Clearance | PD1 Clearance |
|---------|---------------|---------------|
| 400V | 2.0mm | 0.8mm |
| 600V | 3.0mm | 1.0mm |

**With conformal coating, TO-247 at 1.95mm is SAFE for 400V.**

Common coatings:
- Acrylic (easy rework)
- Silicone (flexible, high temp)
- Polyurethane (chemical resistant)
- Parylene (best protection, expensive)

### 2. Creepage Slots

Add slots in the PCB between high-voltage pads to increase creepage distance:

```
Before:        After:
[PAD]--[PAD]   [PAD]  |  [PAD]
                      |
              (slot increases path)
```

This is common for AC mains isolation but less practical for TO-247 packages.

### 3. Potting/Encapsulation

Fully encapsulate the power section in epoxy or silicone. This:
- Eliminates air gaps (no arcing)
- Provides mechanical protection
- Improves thermal performance

Used in: motor drives, EV inverters, industrial power supplies.

### 4. Component Selection

Choose packages designed for the voltage:
- **TO-247**: Standard for 600-1200V IGBTs, designed with this in mind
- **TO-264**: Larger package with 6.45mm pitch for higher voltages
- **Modules**: IGBT modules with integrated isolation

### 5. Accept Industry Practice

The TO-247 package has been used for 400-1200V applications for decades. The package design accounts for:
- Molded plastic body provides additional insulation
- Lead frame geometry optimized for HV
- Millions of units in field without issues

## Our Approach

For the Temper induction heater:

1. **Conformal coating required** - Specify in BOM and assembly instructions
2. **Proper net class clearances** - 6mm for AC mains, 2mm for DC bus (routing only)
3. **Footprint exceptions** - Allow package-inherent clearances with coating
4. **Assembly notes** - Document coating requirements

## Design Rules Summary

```
# Routing clearances (strict)
AC Mains to LV: 6.0mm
HV DC to LV: 2.0mm
Signal: 0.2mm

# Footprint exceptions (with conformal coating)
TO-247 internal: 1.5mm (package inherent)
QFN/BGA: 0.1mm (low voltage only)
```

## References

- IEC 60664-1: Insulation coordination for equipment within low-voltage systems
- IEC 60335-1: Safety of household appliances
- IPC-2221B: Generic Standard on Printed Board Design
- UL 60950-1: Safety of Information Technology Equipment
