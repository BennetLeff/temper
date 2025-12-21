# REQ-MECH-01: Spring-Loaded Pan Sensor Mount Design

## 1. Overview
Design of a spring-loaded mounting mechanism for the glass-contact RTD temperature sensor (PT100) for the Temper induction cooker.

## 2. Specifications
- **Contact Force**: 2N to 5N (adjustable via spring selection)
- **Travel Range**: 8mm total (5mm working range)
- **Sensor**: PT100 RTD (disk or button type)
- **Material**: Aluminum 6061 (thermal button), PTFE (guide bushing), Stainless Steel (spring)
- **Thermal Resistance**: Target < 0.5 K/W

## 3. Mechanical Design
The mount consists of:
1.  **Thermal Button**: 15mm diameter aluminum disk with integrated RTD pocket.
2.  **Plunger**: 6mm diameter shaft attached to the button.
3.  **Guide Bushing**: Low-friction PTFE sleeve mounted to the chassis.
4.  **Compression Spring**: Stainless steel, $k \approx 500 N/m$.
5.  **Retention Clip**: Prevents plunger from falling out.

### 3.1 Force Calculation
- Spring Constant ($k$): 500 N/m
- Pre-load ($x_0$): 2mm
- Working Compression ($\Delta x$): 4mm (for 4mm glass)
- Total Force ($F$): $k * (x_0 + \Delta x) = 500 * (0.002 + 0.004) = 3.0N$
- This meets the >2N requirement.

## 4. Thermal Analysis
- **Button Area ($A$)**: $1.76 \times 10^{-4} m^2$ (15mm diameter)
- **Aluminum Conductivity ($k$):** 205 W/mK
- **Button Thickness ($L$):** 3mm (path from glass to RTD)
- **Conduction Resistance ($R_{cond}$):** $L / (k * A) = 0.003 / (205 * 1.76 \times 10^{-4}) \approx 0.083 K/W$
- **Interface Resistance ($R_{int}$):** Estimated 0.2 K/W with high-performance thermal grease.
- **Total Resistance ($R_{total}$):** $\approx 0.28 K/W$
- This meets the <0.5 K/W requirement.

## 5. Bill of Materials (BOM)

| Item | Description | Material | Quantity | Source |
|------|-------------|----------|----------|--------|
| 1    | Thermal Button | Al 6061 | 1        | Custom (Machined) |
| 2    | Guide Bushing | PTFE | 1        | McMaster 6807K14 |
| 3    | Compression Spring | 0.25" OD, 1" L, 2.8 lb/in | 302 SS | 1 | McMaster 9657K274 |
| 4    | RTD Sensor | PT100, 2x2mm Class A | Ceramic | 1 | Digikey 223-1631-ND |
| 5    | Thermal Grease | Arctic Silver 5 | - | 1 | |

## 6. Assembly Instructions
1. Bond RTD into the pocket of the Thermal Button using thermally conductive epoxy (e.g., MG Chemicals 832TC).
2. Insert Plunger into the Guide Bushing.
3. Place Spring over the Plunger.
4. Secure assembly to the chassis using M3 screws.
5. Apply a thin layer of thermal grease to the top of the button before installing the glass.
