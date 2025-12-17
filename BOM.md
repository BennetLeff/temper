# Temper Induction Cooker - Bill of Materials (BOM)

**Project:** Temper - Production-grade Induction Cooker  
**Version:** 1.0  
**Date:** 2025-12-14  
**Status:** PCB Ready

---

## 1. Power Stage Components

### 1.1 IGBTs and Gate Driver

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| Q1, Q2 | 1200V 40A IGBT | IKW40N120H3FKSA1 | Infineon | 2 | TO-247 | Half-bridge |
| U_GD | Isolated Gate Driver | UCC21550BDWK | Texas Instruments | 1 | SOIC-16 | Dual channel |
| D_BOOT | Bootstrap Diode (SiC Schottky) | UJ3D1210TS | onsemi | 1 | TO-220 | 1200V 10A |
| C_BOOT | Bootstrap Capacitor | GRM32ER71H106KA12L | Murata | 1 | 1210 | 10µF 50V X7R |
| RG_ON | Gate Turn-On Resistor | RC1206FR-072R2L | Yageo | 2 | 1206 | 2.2Ω 1/4W |
| RGS | Gate-Source Pull-Down | RC0603FR-072K2L | Yageo | 2 | 0603 | 2.2kΩ |

### 1.2 Voltage Doubler Rectifier

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| D1, D2 | Ultrafast Rectifier | MUR1560 | ON Semiconductor | 2 | TO-220 | 15A 600V 35ns |
| C_BUS1, C_BUS2 | Bus Capacitors | EKZE251ELL332MM40S | United Chemi-Con | 2 | Radial | 3300µF 250V 105°C |
| R_BLEED1, R_BLEED2 | Bleeder Resistors | - | - | 2 | 2512 | 100kΩ 2W |
| NTC_INRUSH | Inrush Limiter | SL32 10015 | Ametherm | 1 | Radial | 10Ω 15A |
| K_BYPASS | Bypass Relay | G5LE-1-E | Omron | 1 | Through-hole | 10A 250VAC |

### 1.3 Resonant Tank

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| L_TANK | Tank Inductor | Custom | - | 1 | - | 80µH, 50A, ferrite |
| C_TANK1, C_TANK2 | Tank Capacitor | FKP4T021505D00 | WIMA | 2 | Radial 37.5mm | 150nF 1000VDC MKP4 |
| C_TANK1, C_TANK2 (alt) | Tank Capacitor (alt) | R76MR3150AA00M | KEMET | 2 | Radial | 150nF 800VDC R76 |

---

## 2. Power Management

### 2.1 Buck Converter (24V/12V → 5V)

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_BUCK | Synchronous Buck | LMR51430XDDCR | Texas Instruments | 1 | SOT-23-6 | 4.5-36V, 3A |
| L_BUCK | Buck Inductor | SRP1038A-6R8M | Bourns | 1 | 10x10mm | 6.8µH 5.6A |
| C_IN_BUCK | Input Capacitor | GRM32ER72A225KA35L | Murata | 1 | 1210 | 2.2µF 100V X7R |
| C_OUT_BUCK | Output Capacitor | GRM31CR61E226KE15L | Murata | 2 | 1206 | 22µF 25V X5R |
| C_BOOT_BUCK | Bootstrap Capacitor | GRM188R71H103KA01D | Murata | 1 | 0603 | 10nF 50V X7R |
| R_FB1 | Feedback Divider High | RC0603FR-07100KL | Yageo | 1 | 0603 | 100kΩ 1% |
| R_FB2 | Feedback Divider Low | RC0603FR-0732K4L | Yageo | 1 | 0603 | 32.4kΩ 1% |

### 2.2 LDO (5V → 3.3V)

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_LDO | Low-Noise LDO | XC6220B331MR-G | Torex | 1 | SOT-25 | 3.3V 700mA 6.5µV RMS |
| C_IN_LDO | Input Capacitor | GRM188R71H106KA73D | Murata | 1 | 0603 | 10µF 10V X5R |
| C_OUT_LDO | Output Capacitor | GRM21BR61E226ME44L | Murata | 1 | 0805 | 22µF 25V X5R |

---

## 3. Microcontroller

### 3.1 ESP32-S3 Module

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_MCU | WiFi+BLE SoC Module | ESP32-S3-WROOM-1-N4 | Espressif | 1 | Module | 4MB Flash, PCB antenna |
| C_DEC_MCU | Decoupling Caps | GRM188R71H104KA93D | Murata | 4 | 0603 | 100nF 50V X7R |
| C_BULK_MCU | Bulk Capacitor | GRM188R61E106MA73D | Murata | 1 | 0603 | 10µF 25V X5R |

---

## 4. Sensing and Interfaces

### 4.1 Temperature Sensing (RTD)

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_RTD1, U_RTD2 | RTD-to-Digital | MAX31865ATP+ | Analog Devices | 2 | TQFN-20 | SPI, PT100/PT1000 |
| R_REF | Reference Resistor | RC0603FR-07430RL | Yageo | 2 | 0603 | 430Ω 0.1% (PT100) |
| C_DEC_RTD | Decoupling | GRM188R71H104KA93D | Murata | 2 | 0603 | 100nF |

### 4.2 I2C Isolator

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_ISO | I2C Isolator | ADUM1250ARZ | Analog Devices | 1 | SOIC-8 | 2.5kV RMS isolation |
| R_SDA, R_SCL | I2C Pull-ups | RC0603FR-074K7L | Yageo | 4 | 0603 | 4.7kΩ (2 per side) |

### 4.3 Current Transformer

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| CT1 | Current Transformer | Application Specific | - | 1 | Toroid | 1:1000, 100kHz BW |
| R_BURDEN | Burden Resistor | RC2512FK-0750RL | Yageo | 1 | 2512 | 50Ω 1% 1W |

---

## 5. Safety Interlock System

### 5.1 Comparators

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_OCP | OCP Comparator | TLV3201AIDBVR | Texas Instruments | 1 | SOT-23-5 | 40ns prop delay |
| U_OVP | OVP Comparator | TLV3201AIDBVR | Texas Instruments | 1 | SOT-23-5 | 40ns prop delay |
| U_THERMAL | Thermal Comparator | TLV3201AIDBVR | Texas Instruments | 1 | SOT-23-5 | With hysteresis |

### 5.2 Logic ICs

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_OR | Triple 3-Input OR | 74HC4075D | Nexperia | 1 | SOIC-14 | Fault combining |
| U_NAND | Quad 2-Input NAND | 74HC00D | Nexperia | 1 | SOIC-14 | SR Latch |
| U_AND | Quad 2-Input AND | 74HC08D | Nexperia | 1 | SOIC-14 | Reset logic |
| U_INV | Hex Inverter | 74HC04D | Nexperia | 1 | SOIC-14 | Signal inversion |

### 5.3 Hardware Watchdog

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_WDT | Watchdog Timer | TPS3823-33DBVR | Texas Instruments | 1 | SOT-23-5 | 1.6s timeout |
| C_WDT | Decoupling | GRM155R71H104KE14D | Murata | 1 | 0402 | 100nF 50V X7R |

### 5.4 IGBT Desaturation Protection

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| D_DESAT_HS | DESAT Diode High-Side | STTH1R06 | STMicroelectronics | 1 | DO-201AD | 1200V 1A Fast |
| D_DESAT_LS | DESAT Diode Low-Side | STTH1R06 | STMicroelectronics | 1 | DO-201AD | 1200V 1A Fast |
| R_DESAT1_HS | Current Limit HS | ERJ-8ENF1004V | Panasonic | 1 | 1206 | 1MΩ 1% 0.25W |
| R_DESAT1_LS | Current Limit LS | ERJ-8ENF1004V | Panasonic | 1 | 1206 | 1MΩ 1% 0.25W |
| C_BLANK_HS | Blanking Cap HS | GRM1885C2A101JA01D | Murata | 1 | 0603 | 100pF 100V C0G |
| C_BLANK_LS | Blanking Cap LS | GRM1885C2A101JA01D | Murata | 1 | 0603 | 100pF 100V C0G |
| R_DIV1_HS | Voltage Divider High | ERJ-8ENF2203V | Panasonic | 1 | 1206 | 220kΩ 1% |
| R_DIV1_LS | Voltage Divider High | ERJ-8ENF2203V | Panasonic | 1 | 1206 | 220kΩ 1% |
| R_DIV2_HS | Voltage Divider Low | RC0603FR-0722KL | Yageo | 1 | 0603 | 22kΩ 1% |
| R_DIV2_LS | Voltage Divider Low | RC0603FR-0722KL | Yageo | 1 | 0603 | 22kΩ 1% |
| D_TVS_HS | Clamp Diode HS | SMBJ3.0CA | Littelfuse | 1 | SMB | 3.0V TVS |
| D_TVS_LS | Clamp Diode LS | SMBJ3.0CA | Littelfuse | 1 | SMB | 3.0V TVS |
| C_FILT_HS | Filter Cap HS | GRM155R71H104KE14D | Murata | 1 | 0402 | 100pF |
| C_FILT_LS | Filter Cap LS | GRM155R71H104KE14D | Murata | 1 | 0402 | 100pF |
| U_DESAT | Dual Comparator | LM393DR | Texas Instruments | 1 | SOIC-8 | 2 comparators |
| R_REF1 | Ref Divider High | RC0603FR-074K7L | Yageo | 1 | 0603 | 4.7kΩ 1% |
| R_REF2 | Ref Divider Low | RC0603FR-071KL | Yageo | 1 | 0603 | 1kΩ 1% |
| R_PULL_HS | Pull-up Resistor HS | RC0603FR-0710KL | Yageo | 1 | 0603 | 10kΩ |
| R_PULL_LS | Pull-up Resistor LS | RC0603FR-0710KL | Yageo | 1 | 0603 | 10kΩ |

### 5.5 OVP Voltage Divider

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| R_OVP1-3 | HV Divider High | CRCW12061M00FKEA | Vishay | 3 | 1206 | 1MΩ 200V 1% |
| R_OVP4 | HV Divider Low | CRCW120630K0FKEA | Vishay | 1 | 1206 | 30kΩ 1% |

### 5.6 Thermal Protection

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| NTC_IGBT | NTC Thermistor | NCU18XH103F6SRB | Murata | 1 | 0603 | 10kΩ @ 25°C B=3950 |
| R_NTC_PU | NTC Pull-up | RC0603FR-0710KL | Yageo | 1 | 0603 | 10kΩ 1% |

---

## 6. Precision Rectifier (OCP)

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_RECT | Dual Op-Amp | LM358DR | Texas Instruments | 1 | SOIC-8 | Precision rectifier |
| D_RECT1-4 | Fast Signal Diodes | 1N4148WS | Nexperia | 4 | SOD-323 | Fast recovery |

---

## 7. User Interface

### 7.1 Indicators

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| LED_OCP | OCP Fault LED | Red | - | 1 | 0603 | Red LED |
| LED_OVP | OVP Fault LED | Yellow | - | 1 | 0603 | Yellow LED |
| LED_THERMAL | Thermal Fault LED | Orange | - | 1 | 0603 | Orange LED |
| LED_WDT | Watchdog Fault LED | Blue | - | 1 | 0603 | Blue LED |
| LED_MASTER | Master Fault LED | Red | - | 1 | 3mm | Panel mount |
| R_LED | LED Current Limit | RC0603FR-07330RL | Yageo | 5 | 0603 | 330Ω |

### 7.2 Controls

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| S_RESET | Reset Button | Momentary NO | - | 1 | Panel | Panel mount |

---

## 8. PWM Interface Filter

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| R_PWM_A, R_PWM_B | Series Resistor | RC0603FR-0751RL | Yageo | 2 | 0603 | 51Ω |
| C_PWM_A, C_PWM_B | Filter Capacitor | GRM1885C1H330JA01D | Murata | 2 | 0603 | 33pF C0G |

---

## 9. Anti-Aliasing Filter (ADC)

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| R_AA | Filter Resistor | RC0603FR-071KL | Yageo | 1 | 0603 | 1kΩ 1% |
| C_AA | Filter Capacitor | GRM1885C1H162JA01D | Murata | 1 | 0603 | 1.6nF C0G |

---

## 10. Miscellaneous

### 10.1 Decoupling and Bypass

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| C_DEC | General Decoupling | GRM188R71H104KA93D | Murata | 20 | 0603 | 100nF 50V X7R |
| C_BULK | Bulk Capacitor | GRM188R61E106MA73D | Murata | 5 | 0603 | 10µF 25V X5R |

### 10.2 Test Points

| Ref | Description | Part Number | Manufacturer | Qty | Notes |
|-----|-------------|-------------|--------------|-----|-------|
| TP1 | OR_OUTPUT | - | - | 1 | Combined fault |
| TP2 | LATCH_Q | - | - | 1 | Latched state |
| TP3 | GATE_DISABLE | - | - | 1 | Final output |
| TP4 | V_BOOT | - | - | 1 | Bootstrap voltage |
| TP5 | SW_NODE | - | - | 1 | Half-bridge midpoint |

---

## BOM Summary

### By Category

| Category | Component Count | Est. Cost (1000 qty) |
|----------|----------------|----------------------|
| Power Stage (IGBT, Driver, Bootstrap) | 11 | $12.00 |
| Voltage Doubler | 7 | $28.00 |
| Power Management (Buck + LDO) | 10 | $5.00 |
| Microcontroller | 6 | $6.00 |
| Sensing (RTD, CT, I2C) | 12 | $15.00 |
| Safety Interlock | 16 | $6.00 |
| User Interface | 7 | $2.00 |
| Passives (Decoupling, Filters) | ~30 | $3.00 |
| **TOTAL** | **~100** | **~$77.00** |

### Critical Long-Lead Items

| Component | Lead Time | Alternative |
|-----------|-----------|-------------|
| IKW40N120H3FKSA1 | In stock | - |
| ESP32-S3-WROOM-1-N4 | 4-8 weeks | N8 variant |
| UJ3D1210TS | In stock | C4D10120A |
| UCC21550BDWK | 4-8 weeks | UCC21550DWK |

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-14 | Initial release |

---

## References

- SAFETY_INTERLOCK_DESIGN.md
- CT_SENSING_DESIGN.md
- VOLTAGE_DOUBLER_DESIGN.md
- SPLIT_RAIL_BOOTSTRAP_DESIGN.md
- COMPONENT_COMPATIBILITY_VERIFICATION.md
- sim_15_ldo_selection_verification.md
- sim_17-20 verification reports

---

**END OF BOM**
