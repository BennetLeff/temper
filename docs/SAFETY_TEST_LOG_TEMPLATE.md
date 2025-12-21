# Safety Test Log - Template

**System:** Temper Induction Cooker
**PCB Serial Number:** _________________
**Build Date:** _________________
**Tester Name:** _________________

---

## 1. Pre-Power-On Checks (Visual & Continuity)

| Check | Requirement | Result | Value | Sign-off |
|-------|-------------|--------|-------|----------|
| Visual Inspection | No defects | ☐ PASS ☐ FAIL | N/A | |
| PE to Chassis | < 0.1 Ω | ☐ PASS ☐ FAIL | _______ Ω | |
| PE to Heatsink | < 0.1 Ω | ☐ PASS ☐ FAIL | _______ Ω | |
| Ground Bond (25A) | < 0.1 Ω | ☐ PASS ☐ FAIL | _______ Ω | |

---

## 2. High-Voltage Isolation Tests

| Boundary | Test Voltage | Limit | Actual Leakage | Sign-off |
|----------|--------------|-------|----------------|----------|
| Mains to SELV | 3000V AC | < 5 mA | _______ mA | |
| DC Bus to SELV | 3000V AC | < 5 mA | _______ mA | |
| Isolation Res. | 500V DC | > 10 MΩ | _______ MΩ | |

---

## 3. Leakage (Touch) Current

| Condition | Limit | Actual | Sign-off |
|-----------|-------|--------|----------|
| Normal | < 0.25 mA | _______ mA | |
| Open Earth (Fault) | < 3.5 mA | _______ mA | |

---

## 4. Functional Safety (Interlocks)

| Interlock | Target | Trip Point | Result | Sign-off |
|-----------|--------|------------|--------|----------|
| OCP (Current) | 50A peak | _______ A | ☐ PASS ☐ FAIL | |
| OVP (Voltage) | 400V DC | _______ V | ☐ PASS ☐ FAIL | |
| Thermal (HS) | 95°C | _______ °C | ☐ PASS ☐ FAIL | |
| Thermal (Coil) | 115°C | _______ °C | ☐ PASS ☐ FAIL | |
| Watchdog | < 1.6s | _______ s | ☐ PASS ☐ FAIL | |

---

## 5. Final Verdict

**The system is verified safe for operation at full power.**

☐ **YES**  ☐ **NO**

**Engineer Signature:** _________________  **Date:** _________________
