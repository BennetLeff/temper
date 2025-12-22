# Design Specification: Chassis Airflow Ducting

## 1. Overview
The airflow ducting system manages the cooling requirements of the Temper induction cooker within the enclosed RCA 12A3 chassis. It ensures that 100W+ of heat from the IGBTs and additional losses from the coil are efficiently removed using forced convection.

## 2. Requirements (REQ-MECH-03)
- **Airflow Rate**: ≥ 15 CFM across IGBT heatsink fins.
- **Intake**: Draw cool air from the existing bottom vents of the RCA 12A3.
- **Exhaust**: Expel hot air through the rear panel (new 80mm opening required).
- **Fan Support**: Integrated mounting for an 80mm PWM fan.
- **Acoustics**: < 45 dBA at 1 meter during full power operation.
- **Material**: High-temperature ABS or PETG (3D printable).

## 3. Ducting Architecture

### 3.1 Design Strategy
- **Intake Plenum**: A shallow plenum at the bottom of the chassis collects air from the spread-out vents and directs it to the fan.
- **Primary Duct**: A rectangular duct housing the 80mm fan, positioned horizontally.
- **Heatsink Interface**: The duct tapers to match the cross-section of the aluminum heatsink (120mm x 40mm), ensuring all air passes through the fins.

### 3.2 Airflow Path
```
Cool Air (Bottom Vents)
      |
[ Intake Plenum ]
      |
 [ 80mm PWM Fan ]
      |
 [ Transition Duct ]
      |
 [ IGBT Heatsink ]
      |
 [ Exhaust Vent ]
```

## 4. Fan Selection
| Parameter | Specification | Model |
|-----------|---------------|-------|
| Size | 80mm x 80mm x 25mm | Noctua NF-A8 PWM |
| Max Airflow | 32.6 CFM | |
| Noise | 17.7 dBA | |
| Static Pressure | 2.33 mm H₂O | |

*Static pressure is critical to overcome the resistance of the heatsink fins.*

## 5. Performance Estimation
- **Heatsink Area**: 120mm x 40mm x 100mm (fins).
- **Efficiency**: With 32 CFM fan and duct losses, we expect ~20-22 CFM net flow.
- **Temperature Rise**:
  - P_loss = 100W
  - ΔT_air = (3.16 * P_loss) / CFM
  - ΔT_air = (3.16 * 100) / 20 = 15.8°C
- **Result**: Exhaust air will be ~51°C at 35°C ambient, well within component limits.

## 6. Manufacturing
- **Method**: FDM 3D Printing.
- **Infill**: 30% Gyroid for structural rigidity.
- **Walls**: 3 perimeters (1.2mm).
- **Finishing**: High-temp foil tape used to seal joints between duct and heatsink.

## 7. Bill of Materials (BOM)
| Item | Quantity | Description | Material |
|------|----------|-------------|----------|
| Main Duct | 1 | 3D Printed Transition | PETG |
| Intake Shroud | 1 | 3D Printed Shroud | PETG |
| Fan | 1 | 80mm PWM Fan | Noctua NF-A8 |
| Gasket | 1 | Silicone strip seal | Silicone |
| Guard | 1 | 80mm Wire Fan Guard | Steel |