# High-Voltage Safety Testing Procedure

**Document Version:** 1.0
**Status:** DRAFT
**Applicable Standard:** IEC 60335-1 (Safety of household and similar electrical appliances)

---

## ⚠️ WARNING: HIGH VOLTAGE TESTING

These tests involve lethal voltages (up to 3000V AC). 
- Perform tests in a designated high-voltage test area.
- Ensure all test personnel are trained in high-voltage safety.
- Use an isolation transformer for the device under test (DUT).
- Keep one hand in your pocket when making connections.
- Ensure a safety observer is present and knows where the emergency stop is.

---

## 1. Ground Bond Testing

**Purpose:** Verify that all accessible conductive parts are reliably connected to Protective Earth (PE) with a low resistance path capable of carrying fault current.

### 1.1 Equipment Required
- Ground Bond Tester or 4-wire Multimeter capable of high current (e.g., Fluke 87V in 4-wire mode if current source available).
- Preferred: Dedicated Ground Bond Tester providing 25A AC.

### 1.2 Procedure
1. Connect the tester's return lead to the PE pin of the AC inlet.
2. Apply a test current of **25A AC** (or 1.5 times the rated current, whichever is greater) between the PE pin and each accessible metal part.
3. Accessible parts to test:
   - Heatsinks
   - Metal chassis panels
   - Exposed screw heads
   - Connector shells
4. Measure the voltage drop and calculate resistance (R = V/I).

### 1.3 Acceptance Criteria
- Resistance from PE pin to any accessible part: **< 0.1 Ω**
- Test duration: **60 seconds** per test point.

---

## 2. Dielectric Strength (Hi-Pot) Testing

**Purpose:** Verify the integrity of the insulation barriers (Basic and Reinforced) between high-voltage circuits and user-accessible low-voltage circuits (SELV).

### 2.1 Equipment Required
- Hi-Pot Tester (e.g., Fluke 1507 or dedicated AC/DC Hi-Pot unit).
- **Test Voltage:** 3000V AC or 4242V DC.

### 2.2 Preparation
1. **DISCONNECT** ESP32-S3 module and any sensitive ICs that cannot withstand hi-pot voltages if they bridge the barrier (e.g. optoisolators are designed for this, but standard caps may not be).
2. **SHORT** together all AC inlet pins (L, N, PE).
3. **SHORT** together all SELV (3.3V, 5V, GND) rail test points.

### 2.3 Procedure (Mains to SELV)
1. Connect the Hi-Pot high-voltage lead to the shorted AC inlet (L+N).
2. Connect the Hi-Pot return lead to the shorted SELV rails.
3. Gradually increase the voltage from 0V to **3000V AC** over 5 seconds.
4. Maintain the test voltage for **60 seconds**.
5. Gradually decrease the voltage back to 0V.

### 2.4 Procedure (DC Bus to SELV)
1. Repeat the test between the high-voltage DC bus (+ and - shorted) and the SELV rails.
2. Test Voltage: **3000V AC**.
3. Duration: **60 seconds**.

### 2.5 Acceptance Criteria
- No breakdown or arcing shall occur.
- Leakage current: **< 5 mA**.

---

## 3. Leakage (Touch) Current Measurement

**Purpose:** Measure the current that could flow through a human body touching the appliance under normal and fault conditions.

### 3.1 Equipment Required
- Leakage Current Tester (e.g., Extech 380260).
- Measuring network matching IEC 60990 (human body model).

### 3.2 Procedure
1. Power the DUT through an isolation transformer at **110% of rated voltage** (132V AC).
2. Measure current between PE and each accessible metal part.
3. Perform measurements in the following states:
   - Normal operation.
   - Reversed polarity of AC input.
   - Single fault: PE disconnected (Open Earth).
   - Single fault: Neutral disconnected (Open Neutral).

### 3.3 Acceptance Criteria
- Touch current (Normal): **< 0.25 mA**.
- Touch current (Single Fault): **< 3.5 mA** (IEC 60335-1 limit).

---

## 4. Test Log and Sign-Off

Record all results in the `SAFETY_TEST_LOG`. Ensure all measurements are within limits before proceeding to functional load testing.
