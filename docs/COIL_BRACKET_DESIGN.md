# Design Specification: Induction Coil Mounting Bracket

## 1. Overview
The induction coil mounting bracket secures the Litz wire induction coil within the RCA 12A3 chassis. It is responsible for maintaining a consistent 3mm air gap to the glass cooktop, which is critical for resonant frequency stability and efficiency.

## 2. Requirements (REQ-MECH-02)
- **Air Gap**: 3mm ± 0.5mm between coil and glass.
- **Chassis Fit**: Uses existing transformer mounting holes in the RCA 12A3 chassis.
- **Coil Size**: Supports OD up to 200mm.
- **Material**: Non-magnetic, non-conductive (FR4, Fiberglass, or Aluminum if properly slotted).
- **Cooling**: Open-frame design to allow forced airflow from the bottom fan.
- **Strain Relief**: Integrated clamps for high-current Litz wire leads.

## 3. Mechanical Design

### 3.1 Structural Strategy
- **Material**: 3.2mm thick G10/FR4 plate (excellent thermal and magnetic properties).
- **Mounting**: 4x M4 standoffs (aluminum) bolted to the chassis transformer rails.
- **Height Adjustment**: Precision shims (0.1mm) used to fine-tune the 3mm air gap.

### 3.2 Bracket Layout
```
   [●]----------------[●]  <-- M4 Standoff Points
    |                  |
    |   /----------\   |
    |  /   COIL     \  |
    | |    AREA      | |  <-- 200mm diameter cutout
    |  \            /  |
    |   \----------/   |
    |                  |
   [●]----------------[●]
```

### 3.3 Stack-up Calculation
| Item | Thickness (mm) | Tolerance (mm) |
|------|----------------|----------------|
| Glass Cooktop | 4.0 | ±0.2 |
| Air Gap | 3.0 | ±0.2 |
| Coil Height | 5.0 | ±0.1 |
| **Total Height** | **12.0** | **±0.5** |

*Adjust standoff height to 7.0mm to achieve the 3mm air gap with a 5mm thick coil.*

## 4. Cooling and Airflow
- Large triangular cutouts around the central coil ring allow air from the bottom intake to flow directly through the Litz wire strands.
- The bracket itself acts as a baffle to direct air toward the IGBT heatsink after cooling the coil.

## 5. Bill of Materials (BOM)
| Item | Quantity | Description | Material |
|------|----------|-------------|----------|
| Main Plate | 1 | Custom routed G10 plate | G10/FR4 |
| Standoff | 4 | 7mm M4 Male-Female Standoff | Aluminum |
| Screw | 4 | M4 x 10mm Button Head | Stainless |
| Lead Clamp | 2 | Nylon Cable Clamp | PA66 |

## 6. Assembly Instructions
1. Attach standoffs to the RCA 12A3 chassis transformer mounting holes.
2. Bond the induction coil to the G10 plate using high-temp silicone or epoxy.
3. Route Litz leads through the strain relief clamps.
4. Mount the plate onto the standoffs.
5. Verify 3.0mm distance to the top panel using a feeler gauge before installing the glass.