# Design Specification: Spring-Loaded Pan Sensor Mount

## 1. Overview
The pan sensor mount is a critical mechanical component that ensures the RTD (PT100) sensor maintains consistent physical and thermal contact with the underside of the glass-ceramic cooktop. This is essential for accurate closed-loop temperature control.

## 2. Requirements (REQ-MECH-01)
- **Contact Force**: ≥ 2N (to ensure thermal interface contact).
- **Travel Range**: ≥ 5mm (to accommodate chassis flex and glass tolerances).
- **Thermal Resistance**: < 0.5 K/W from glass to sensor element.
- **Sensor Compatibility**: PT100 RTD (1/10 DIN accuracy preferred).
- **Material**: Non-magnetic (Aluminum, PTFE, or high-temp plastics).
- **Service Life**: 10,000+ thermal/mechanical cycles.

## 3. Mechanical Design

### 3.1 Components
1. **Sensor Button**: Aluminum 6061 or Copper disk (Ø12mm, 3mm thick).
2. **Spring**: Stainless steel compression spring (non-magnetic).
3. **Guide Housing**: PTFE or PEEK sleeve to minimize friction and handle high temperatures.
4. **Base Plate**: Aluminum bracket attached to the main RCA 12A3 chassis.

### 3.2 Spring Specification
- **Free Length**: 15mm
- **Spring Rate**: 0.5 N/mm
- **Pre-load**: 2.5mm (to provide 1.25N at contact)
- **Compressed Force**: 3.75N at 5mm travel (safety margin included)

### 3.3 Assembly Stack-up
```
[ Pan ]
------------------- [ Glass-Ceramic (4mm) ]
      (Thermal Grease)
   [ Aluminum Button ]
   [ PT100 Element ]
   [ PTFE Guide Sleeve ]
   [ Compression Spring ]
   [ Chassis Base Plate ]
```

## 4. Thermal Analysis
- **Interface**: A thin layer of boron nitride-filled thermal grease is applied between the button and glass.
- **Button Material**: Aluminum 6061 (k = 167 W/m·K) provides rapid response.
- **Isolation**: The PTFE sleeve acts as a thermal insulator to prevent chassis heat-sinking from affecting the measurement.

## 5. Bill of Materials (BOM)
| Item | Part Number | Description | Material |
|------|-------------|-------------|----------|
| Sensor Disk | Custom | Ø12mm x 3mm Disk | Aluminum 6061 |
| Spring | 9657K274 | Comp. Spring, 0.5 N/mm | 302 Stainless |
| Housing | Custom | Ø14mm ID Guide | PTFE |
| Sensor | PT100 | Thin-film Platinum RTD | Alumina/Platinum |

## 6. Manufacturing Notes
- The button surface in contact with the glass must be polished to < 0.8µm Ra.
- Clearance between button and sleeve should be 0.1mm to allow free movement while preventing tilting.
- Silicone potting can be used to secure the RTD element inside the aluminum button.