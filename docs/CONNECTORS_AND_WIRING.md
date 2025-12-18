# Connector and Wiring Specification

**Project:** Temper Induction Cooker  
**Version:** 1.0  
**Date:** 2025-12-17

---

## 1. Connector Summary

| Ref | Function | Type | Part Number (PCB) | Mating Part | Pins | Rating |
|-----|----------|------|-------------------|-------------|------|--------|
| **J_IN** | AC Mains Input | IEC C20 Inlet | Schurter 4798.9000 (Panel) | IEC C19 Cord | 3 | 16A/250V |
| **J_COIL** | Coil Output | M4 Screw Terminal | Keystone 7761 | Ring Terminal M4 | 2 | 30A |
| **J_RTD1** | Pan Sensor | JST XH | JST B4B-XH-A | JST XHP-4 | 4 | 3A/250V |
| **J_RTD2** | Heatsink Sensor | JST XH | JST B4B-XH-A | JST XHP-4 | 4 | 3A/250V |
| **J_FAN** | Cooling Fan | Molex KK 254 | Molex 47053-1000 | Molex 22-01-3047 | 4 | 4A |
| **J_PROG** | UART Prog | 2.54mm Header | Generic 1x6 | Dupont 1x6 | 6 | 3A |
| **J_UI** | User Interface | JST XH | JST B8B-XH-A | JST XHP-8 | 8 | 3A/250V |
| **J_DEBUG** | JTAG Debug | 1.27mm Header | Samtec FTSH-105 | Ribbon Cable | 10 | 1A |

---

## 2. Pinout Definitions

### 2.1 AC Mains Input (J_IN)
*Panel Mount, Quick Connect or Solder terminals*
- **L**: Line (Hot) - Black/Brown Wire (14 AWG)
- **N**: Neutral - White/Blue Wire (14 AWG)
- **PE**: Earth - Green/Yellow Wire (14 AWG)

### 2.2 Coil Output (J_COIL)
*PCB High Current Screw Terminals*
- **1**: Coil A (High Voltage HF) - Litz Wire
- **2**: Coil B (High Voltage HF) - Litz Wire

### 2.3 RTD Sensors (J_RTD1, J_RTD2)
*4-Wire RTD Connection (PT100)*
- **1**: Bias + (Red)
- **2**: Sense + (Red)
- **3**: Sense - (White)
- **4**: Bias - (White)

### 2.4 Cooling Fan (J_FAN)
*Standard PC Fan Pinout*
- **1**: GND (Black)
- **2**: +12V (Yellow)
- **3**: Tachometer (Green)
- **4**: PWM Control (Blue)

### 2.5 Programming Header (J_PROG)
*FTDI Standard Pinout*
- **1**: GND
- **2**: CTS (Unused)
- **3**: VCC (3.3V Output)
- **4**: TXD (ESP32 TX)
- **5**: RXD (ESP32 RX)
- **6**: RTS (to EN/Reset)

### 2.6 User Interface (J_UI)
- **1**: +3.3V
- **2**: GND
- **3**: Encoder A
- **4**: Encoder B
- **5**: Encoder Button
- **6**: LED Data (WS2812 or Shift Reg)
- **7**: LED Clock (if needed)
- **8**: Spare / INT

---

## 3. Wiring and Harness Specifications

### 3.1 AC Input Harness
- **Gauge**: 14 AWG (2.08 mm²) minimum
- **Insulation**: 600V, 105°C (UL 1015 or TEW)
- **Terminals**: 
  - J_IN end: 6.3mm Quick Connects (insulated)
  - PCB end: Soldered or Screw Terminal (if J_AC_PCB used)
- **Twist**: Twist L/N wires to reduce EMI

### 3.2 Coil Connections
- **Wire**: Litz wire provided with coil assembly
- **Termination**: Crimped M4 Ring Terminals (Tin-plated copper)
- **Insulation**: Silicone sleeving over Litz ends
- **Routing**: Keep away from low-voltage logic!

### 3.3 Sensor Harnesses (RTD)
- **Gauge**: 24-26 AWG
- **Type**: Shielded Twisted Pair (for noise immunity)
- **Shielding**: Connect shield to Chassis Ground at PCB end only
- **Length**: Max 500mm

### 3.4 Logic Wiring (UI, Fan)
- **Gauge**: 26 AWG (Fan power: 24 AWG)
- **Type**: Ribbon cable or discrete wires in sleeving
- **Routing**: Secure to chassis, avoid sharp edges

---

## 4. Grounding and Shielding

- **PE (Protective Earth)**: Star point on Chassis.
- **PCB Grounding**: 
  - Mounting holes connected to Chassis GND via metal standoffs.
  - AC Inlet PE connected to Chassis Star Point.
  - PCB PE pad connected to Chassis Star Point.

---
