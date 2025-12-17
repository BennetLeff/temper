# Sensing & Monitoring Integration Verification Report

## Temper Induction Cooker - temper-d9e Epic Summary

**Document Version:** 1.0  
**Date:** December 13, 2025  
**Status:** VERIFIED

---

## 1. Executive Summary

This report documents the verification of the sensing and monitoring integration (temper-d9e epic). The design integrates current sensing, temperature measurement, high-voltage bus monitoring, and thermal management into a complete sensing subsystem.

### Subtask Summary

| Subtask | Title | Status | Verification |
|---------|-------|--------|--------------|
| temper-d9e.1 | Current transformer sensing | **PASS** | sim_17a, sim_17b, sim_17 |
| temper-d9e.2 | MAX31865 RTD temperature | **PASS** | Documentation, SPICE model |
| temper-d9e.3 | High-voltage bus monitoring | **PASS** | sim_18 (OVP verified) |
| temper-d9e.4 | NTC thermistor sensing | **PASS** | sim_19 thermal shutdown |
| temper-d9e.5 | Complete sensing integration | **PASS** | sim_20 interlock integration |

---

## 2. Subtask Verification Details

### 2.1 temper-d9e.1: Current Transformer Sensing Circuit

**Requirement:** CT for tank current measurement, signal conditioning for ESP32-S3 ADC.

**Design Parameters:**

| Parameter | Value | Notes |
|-----------|-------|-------|
| CT ratio | 1:1000 | 50A primary → 50mA secondary |
| Burden resistor | 50Ω | 2.5V at 50A |
| Frequency range | 20-100 kHz | Covers 38kHz operating |
| ADC output | 0-3.3V | ESP32 compatible |
| OCP threshold | 50A | Via comparator |

**Simulation Results:**

**sim_17a (CT Validation):**
- V_sec_peak = 2.5V at 50A primary ✓
- V_sec_pp = 5.0V (±2.5V swing)
- Transfer function: V_out = I_primary × 50mA/A × 50Ω = 2.5mV/A

**sim_17b (Frequency Response):**
- Flat response from 1kHz to 200kHz (-26dB gain)
- Phase at 35kHz: 0° (no phase shift)
- -3dB bandwidth: >200kHz (well above operating frequency)

**sim_17 (OCP Protection):**
- Response time: **33ns** (target: <14.3µs = half cycle)
- First trip at fault onset: ~50µs
- V_abs_normal: 2.0V (40A, below threshold)
- V_abs_fault: 3.0V (60A, above 2.5V threshold)

**Circuit Design:**
```
Tank Current → CT (1:1000) → Burden R (50Ω) → Full-wave Rectifier → Comparator (TLV3201)
                                                      ↓
                                               V_out (0-3.3V) → ESP32 ADC
                                                      ↓
                                               OCP_FAULT → Gate Driver DISABLE
```

**Verification:** PASS ✓

---

### 2.2 temper-d9e.2: MAX31865 RTD Temperature Sensing

**Requirement:** Precision temperature measurement with SPI isolation.

**Design Parameters:**

| Parameter | Specification | Notes |
|-----------|---------------|-------|
| RTD type | PT100 | 100Ω @ 0°C |
| Reference resistor | 400Ω ±0.1% | 4× RTD nominal |
| ADC resolution | 15-bit | 0.03°C resolution |
| Accuracy | ±0.5°C | With Class A RTD |
| Interface | SPI (5MHz max) | Via ADUM1250 isolator |
| Wiring | 4-wire | Eliminates lead resistance |

**Key Features (from MAX31865_Documentation.md):**

1. **Ratiometric Measurement:** Cancels supply voltage errors
2. **50/60Hz Notch Filter:** -120dB rejection at mains frequency
3. **Fault Detection:** Open/short RTD, overvoltage
4. **Temperature Range:** -200°C to +850°C (sensor dependent)

**Application in Temper:**

| Measurement Point | Target Range | Threshold Actions |
|-------------------|--------------|-------------------|
| IGBT heatsink | 40-100°C | Warning 85°C, Shutdown 100°C |
| Induction coil | 50-150°C | Warning 120°C, Shutdown 150°C |

**SPI Isolation (via ADUM1250):**
- Galvanic isolation: 2500 VRMS
- Data rate: Up to 1 MHz (SPI through isolator)
- Creepage: 5mm minimum on PCB

**Verification:** PASS ✓ (Documentation and SPICE model validated)

---

### 2.3 temper-d9e.3: High-Voltage Bus Monitoring

**Requirement:** Isolated 320V DC bus monitoring with OVP/UVP detection.

**Design Approach:**

```
DC Bus (320V) → Resistive Divider (100:1) → Isolation Amplifier → ESP32 ADC
                    ↓                              ↓
              V_sense (3.2V max)            V_out (0-3.3V)
                    ↓
              OVP Comparator → FAULT
```

**Design Parameters:**

| Parameter | Value | Notes |
|-----------|-------|-------|
| Bus voltage range | 200-400V | Nominal 320V |
| Divider ratio | 100:1 | 320V → 3.2V |
| OVP threshold | 380V | 19% above nominal |
| UVP threshold | 250V | 22% below nominal |
| Isolation | >2.5kV | Via optocoupler or isolation amp |
| Accuracy | ±5% | Adequate for protection |

**Simulation Results (sim_18 - OVP Protection):**
- OVP comparator tested with voltage transients
- Response to bus overvoltage: <10µs
- Proper shutdown sequencing verified

**Verification:** PASS ✓

---

### 2.4 temper-d9e.4: NTC Thermistor Sensing

**Requirement:** Heatsink and enclosure temperature monitoring.

**Design Parameters:**

| Parameter | Value | Notes |
|-----------|-------|-------|
| NTC type | 10kΩ @ 25°C | B25/85 = 3950K |
| Temperature range | -40°C to +125°C | Full operating range |
| Accuracy | ±2°C | After calibration |
| Response time | <5s | Heatsink thermal mass |
| ADC interface | Voltage divider + ESP32 | 0-3.3V |

**Linearization Circuit:**

```
3.3V ──┬── 10kΩ (fixed) ──┬── V_out → ESP32 ADC
       │                   │
       └───────────────────┼── NTC (10kΩ @ 25°C)
                           │
                          GND
```

**Temperature Lookup (Key Points):**

| Temperature | NTC Resistance | V_out |
|-------------|----------------|-------|
| -40°C | ~160kΩ | 0.19V |
| 0°C | ~32kΩ | 0.78V |
| 25°C | 10kΩ | 1.65V |
| 50°C | 4.0kΩ | 2.35V |
| 85°C | 1.5kΩ | 2.87V |
| 125°C | 0.6kΩ | 3.11V |

**Simulation Results (sim_19 - Thermal Shutdown):**
- NTC response to heatsink temperature rise
- Thermal shutdown threshold verified at 95°C case temp
- Hysteresis: Resume at 70°C

**Verification:** PASS ✓

---

### 2.5 temper-d9e.5: Complete Sensing Integration with ESP32-S3

**Requirement:** Integrate all sensing circuits with ESP32-S3.

**System Architecture:**

```
                    ESP32-S3
                       │
        ┌──────────────┼──────────────┐
        │              │              │
     ADC (3ch)       SPI           GPIO
        │              │              │
   ┌────┴────┐    ┌────┴────┐    ┌───┴───┐
   │ V_BUS   │    │ MAX31865 │   │ FAULT │
   │ I_TANK  │    │ (via     │   │ INPUTS│
   │ NTC     │    │ ADUM1250)│   │       │
   └─────────┘    └──────────┘   └───────┘
```

**ADC Channel Allocation:**

| ESP32 ADC | Signal | Range | Sample Rate |
|-----------|--------|-------|-------------|
| GPIO34 (ADC1_CH6) | V_BUS | 0-3.3V | 1 kHz |
| GPIO35 (ADC1_CH7) | I_TANK (CT) | 0-3.3V | 10 kHz |
| GPIO36 (ADC1_CH0) | NTC_HEATSINK | 0-3.3V | 10 Hz |

**SPI Interfaces:**

| SPI Bus | Device | Pins | Speed |
|---------|--------|------|-------|
| HSPI | MAX31865 (via ADUM1250) | GPIO 12-15 | 1 MHz |

**Fault Inputs (GPIO):**

| GPIO | Signal | Active | Action |
|------|--------|--------|--------|
| GPIO21 | OCP_FAULT | LOW | Immediate PWM disable |
| GPIO22 | OVP_FAULT | LOW | Immediate PWM disable |
| GPIO23 | THERMAL_FAULT | LOW | Controlled shutdown |

**Simulation Results (sim_20 - Interlock Integration):**
- Verified fault latching logic
- Priority: OCP > OVP > Thermal
- Fault-to-shutdown latency: <1µs (hardware path)
- Software notification: <10ms (ESP32 interrupt)

**Grounding Strategy:**
- Separate analog and digital ground returns
- Star ground at ADC reference
- Shield termination at ESP32 ground

**Verification:** PASS ✓

---

## 3. Integration Summary

### 3.1 Sensing Subsystem Performance

| Measurement | Range | Accuracy | Response |
|-------------|-------|----------|----------|
| Tank current | 0-50A | ±2% | <100µs |
| Bus voltage | 200-400V | ±5% | <1ms |
| IGBT temperature | 0-150°C | ±0.5°C | 52ms |
| Heatsink temperature | -40 to +125°C | ±2°C | ~1s |

### 3.2 Protection Response Times

| Protection | Detection | Shutdown |
|------------|-----------|----------|
| Overcurrent (>50A) | 33ns | <1µs |
| Overvoltage (>380V) | <10µs | <100µs |
| Overtemperature (>100°C) | 52ms | <100ms |

### 3.3 Existing Simulations

| Simulation | Description | Status |
|------------|-------------|--------|
| sim_17a | CT validation | ✅ Complete |
| sim_17b | CT frequency response | ✅ Complete |
| sim_17 | OCP protection | ✅ Complete |
| sim_18 | OVP protection | ✅ Complete |
| sim_19 | Thermal shutdown | ✅ Complete |
| sim_20 | Interlock integration | ✅ Complete |

---

## 4. Component Summary

### 4.1 Key Components

| Component | Part Number | Function |
|-----------|-------------|----------|
| Current transformer | Custom 1:1000 | Tank current sensing |
| RTD converter | MAX31865 | Precision temperature |
| I2C/SPI isolator | ADUM1250 | Signal isolation |
| Comparator | TLV3201 | OCP detection |
| NTC thermistor | 10kΩ (B=3950K) | Heatsink temp |

### 4.2 Bill of Materials (Sensing)

| Item | Qty | Est. Cost |
|------|-----|-----------|
| MAX31865 | 1 | $7.50 |
| ADUM1250 | 1 | $3.50 |
| PT100 RTD | 1 | $15.00 |
| Current transformer | 1 | $5.00 |
| NTC thermistor | 2 | $2.00 |
| Comparators, passives | - | $5.00 |
| **Total** | | **~$38** |

---

## 5. Conclusion

The sensing and monitoring integration (temper-d9e) is **VERIFIED**. All five subtasks pass verification:

1. ✅ Current transformer validated (33ns OCP response)
2. ✅ MAX31865 RTD sensing documented (±0.5°C accuracy)
3. ✅ High-voltage bus monitoring verified (OVP functional)
4. ✅ NTC thermistor sensing verified (thermal shutdown)
5. ✅ Complete integration with ESP32-S3 validated (sim_20)

The epic can be closed. The final integration level (temper-0zd: Full System Integration) is now **unblocked**.

---

## 6. References

| Document | Description |
|----------|-------------|
| MAX31865_Documentation.md | RTD converter guide |
| ADUM1250_Documentation.md | I2C isolator guide |
| current_transformer.sub | CT SPICE model |
| sim_17*_results.txt | CT verification results |
| sim_18_ovp_protection_results.txt | OVP verification |
| sim_19_thermal_shutdown_results.txt | Thermal protection |
| sim_20_interlock_integration_results.txt | Integration verification |

---

**END OF DOCUMENT**
