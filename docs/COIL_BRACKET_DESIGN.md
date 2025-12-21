# REQ-MECH-02: Induction Coil Mounting Bracket Design

## 1. Overview
Design of a non-magnetic mounting bracket for the Litz wire induction coil, compatible with the RCA 12A3 chassis.

## 2. Specifications
- **Coil Diameter**: 200mm OD, 40mm ID
- **Coil Height**: 5mm (Litz wire + potting)
- **Air Gap**: 3mm ±0.5mm (coil to glass)
- **Material**: G10/FR4 Fiberglass or High-Temp Polycarbonate (non-magnetic)
- **Mounting**: Uses existing 12A3 transformer holes (M4 pattern)

## 3. Mechanical Design
The bracket is a **Flat Plate Spider** design:
1.  **Main Deck**: 210mm diameter FR4 sheet (3mm thick).
2.  **Mounting Arms**: 4 arms extending to the 12A3 transformer mounting holes.
3.  **Ventilation Slots**: Large cutouts in the deck to allow forced air from the bottom fan to cool the coil.
4.  **Coil Stays**: Integrated tabs or clips to center and secure the coil.
5.  **Strain Relief**: Integrated holes for Litz wire lead routing and zip-tie points.

### 3.1 Stack-up Calculation
- Chassis Top to Glass Bottom: 15mm (designed in REQ-MECH-04)
- Coil Height: 5mm
- Target Air Gap: 3mm
- Required Bracket Offset: $15 - 5 - 3 = 7mm$
- Design uses 7mm threaded standoffs between chassis and bracket.

## 4. Thermal Considerations
- Coil temperature can reach 100°C.
- FR4 (G10) is rated for 130°C continuous operation.
- Ventilation slots: 8 radial slots, each 100mm x 25mm, providing ~20,000mm² open area.
- This provides >60% open area under the coil for maximum airflow.

## 5. Bill of Materials (BOM)

| Item | Description | Material | Quantity | Source |
|------|-------------|----------|----------|--------|
| 1    | Coil Bracket | FR4 (3mm) | 1        | Custom (Waterjet/CNC) |
| 2    | Standoffs | M4 x 7mm, F-F | Aluminum | 4 | McMaster 93330A445 |
| 3    | Screws | M4 x 10mm Pan Head | SS | 8 | |
| 4    | Washers | M4 Flat | SS | 8 | |

## 6. Assembly Instructions
1. Attach Standoffs to the 12A3 chassis at the transformer mounting locations.
2. Place the Coil onto the Bracket and secure with high-temp silicone or integrated clips.
3. Route coil leads through the strain relief holes.
4. Mount the Bracket assembly to the standoffs using M4 screws.
5. Verify 3mm gap using a feeler gauge before final assembly of the glass panel.
