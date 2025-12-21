# Functional Safety Test Procedure (Under Load)

**Document Version:** 1.0
**Status:** DRAFT
**System:** Temper Induction Cooker

---

## 1. Overview

This procedure defines how to verify that the hardware and firmware safety interlocks function correctly while the system is under power and load. 

**WARNING:** These tests involve high power (up to 1.8kW) and intentional fault injection. Use extreme caution. 

---

## 2. Overcurrent Protection (OCP) Verification

**Purpose:** Verify that the hardware comparator (TLV3201) immediately shuts down the gate driver if current exceeds 50A peak.

### 2.1 Test Method: Current Injection (Safe)
1. Power off the DC bus.
2. Provide 3.3V bias to the sensing circuit.
3. Use a precision current source to inject a signal into the current transformer (CT) burden resistor matching 50A primary current.
4. Verify that the OCP fault latch engages and the gate driver DIS pin goes HIGH.

### 2.2 Test Method: Controlled Overload (Live)
1. Use a large iron pan with high coupling.
2. Slowly increase power while monitoring CT output on an oscilloscope.
3. Rapidly lower the operating frequency toward resonance to increase current.
4. Verify system trips exactly at 50A peak.

---

## 3. Thermal Shutdown Verification

**Purpose:** Verify that the system safely shuts down if temperatures exceed safe limits.

### 3.1 Heatsink Protection
1. Run the system at full power (1.8kW).
2. Partially block the cooling fan intake to allow heatsink temperature to rise.
3. Verify:
   - **Warning:** At 75°C, system enters derated power mode.
   - **Shutdown:** At 95°C, system enters FAULT state and disables gate drive.

### 3.2 Coil Area Protection
1. Use a pan without liquid to allow rapid heating.
2. Verify system shuts down when coil NTC sensor reaches 115°C.

---

## 4. Overvoltage Protection (OVP) Verification

**Purpose:** Verify system shutdown if DC bus voltage exceeds 400V.

### 4.1 Test Method: Variable AC Input
1. Use a Variac to slowly increase the AC input voltage beyond 120V AC.
2. Monitor DC bus voltage.
3. Verify that the system enters FAULT state when DC bus reaches 400V.

---

## 5. Watchdog Timeout Verification

**Purpose:** Verify that the hardware watchdog (TPS3823) shuts down the power stage if the MCU firmware hangs.

### 5.1 Procedure
1. Run the system in HEATING state at low power.
2. Use a debug command or a special firmware build to enter an infinite loop (disabling the watchdog kick).
3. Verify that the TPS3823 resets the MCU and the hardware latch disables the gate driver within 1.6 seconds.

---

## 6. Pass/Fail Criteria

| Test | Expected Action | Result |
|------|-----------------|--------|
| OCP Trip | Latched shutdown < 1µs | ☐ PASS ☐ FAIL |
| Thermal (Heatsink) | Derate at 75°C, Fault at 95°C | ☐ PASS ☐ FAIL |
| Thermal (Coil) | Fault at 115°C | ☐ PASS ☐ FAIL |
| OVP Trip | Fault at 400V DC | ☐ PASS ☐ FAIL |
| Watchdog | HW reset + shutdown on hang | ☐ PASS ☐ FAIL |
