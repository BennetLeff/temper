# Environmental Operating Specifications

**Project:** Temper Induction Cooker  
**Version:** 1.0  
**Date:** 2025-12-17

---

## 1. Operating Conditions

The Temper induction cooker is designed for indoor household use in a kitchen environment.

| Parameter | Min | Typical | Max | Unit | Notes |
|-----------|-----|---------|-----|------|-------|
| **Ambient Temperature** | 10 | 25 | 40 | °C | Rated power. Derate >40°C. |
| **Relative Humidity** | 30 | - | 85 | % | Non-condensing |
| **Altitude** | 0 | - | 2000 | m | >2000m requires voltage derating |
| **Supply Voltage (US)** | 108 | 120 | 132 | V AC | ±10% tolerance |
| **Supply Voltage (EU)** | 207 | 230 | 253 | V AC | ±10% tolerance |
| **Supply Frequency** | 47 | 50/60 | 63 | Hz | Universal |

### 1.1 Derating
- **Thermal Derating:** Linearly reduce max power from 100% at 40°C to 0% at 60°C ambient.
- **Altitude Derating:** Reduce max voltage rating by 10% for every 1000m above 2000m.

---

## 2. Storage and Transport Conditions

Conditions for the device when packed in original packaging and not in operation.

| Parameter | Min | Max | Unit | Notes |
|-----------|-----|-----|------|-------|
| **Temperature** | -20 | +60 | °C | Allows for shipping |
| **Humidity** | 10 | 90 | % | Non-condensing |
| **Duration** | - | 12 | Months | Shelf life before battery check |

---

## 3. Environmental Ratings

| Standard | Rating | Description |
|----------|--------|-------------|
| **IP Rating** | IP20 | Protected against solid objects >12.5mm (fingers). No liquid ingress protection guaranteed (spill-resistant design required). |
| **Pollution Degree** | PD2 | Normal household environment. Temporary conductivity caused by condensation is to be expected. |
| **Overvoltage Category** | CAT II | Appliance connected to mains. |
| **Insulation Class** | Class I | Protective Earth (PE) required. |

---

## 4. Environmental Stress Testing (IEC 60068)

Verification tests to ensure robustness.

### 4.1 Mechanical Stress

| Test | Standard | Parameters | Pass Criteria |
|------|----------|------------|---------------|
| **Vibration (Sine)** | IEC 60068-2-6 | 10-150Hz, 1g, 1 octave/min, 3 axes, 1hr/axis | No loose parts, functional check pass |
| **Mechanical Shock** | IEC 60068-2-27 | 15g, 11ms half-sine, 3 shocks/axis | No structural damage, functional check pass |
| **Free Fall (Drop)** | IEC 60068-2-31 | 75cm drop onto concrete (in packaging) | Packaging may deform, product must be undamaged |

### 4.2 Thermal Stress

| Test | Standard | Parameters | Pass Criteria |
|------|----------|------------|---------------|
| **Thermal Cycling** | IEC 60068-2-14 | -20°C to +60°C, 1°C/min, 1hr dwell, 10 cycles | No cracking, functional check pass |
| **Damp Heat** | IEC 60068-2-78 | 40°C, 93% RH, 96 hours | Dielectric strength > 1250V, leakage < 0.75mA |

---

## 5. Electromagnetic Environment

Designed for Residential, Commercial, and Light Industrial environments (IEC 61000-6-3 / IEC 61000-6-1).

- **Radiated Immunity:** 3 V/m (80 MHz - 1 GHz)
- **ESD Immunity:** ±4kV Contact, ±8kV Air
- **EFT/Burst:** ±1kV on Power Line
- **Surge:** ±1kV Line-Line, ±2kV Line-Earth

---
