# Requirement-Traceability List

**Project:** Temper Induction Cooker  
**Version:** 1.0  
**Date:** 2026-06-22  
**Authoritative Gate Definition:** `docs/STRATEGY.md`  
**Criteria Source:** `docs/FUNCTIONAL_TEST_CRITERIA.md`

This table maps each non-negotiable safety and performance gate to the test artifact that covers it. Gaps are surfaced with linked issues.

## Coverage Summary

| Status | Count |
|--------|-------|
| Covered | 12 |
| Gap | 7 |
| Deferred | 0 |
| **Total** | **19** |

## Traceability Table

| Gate ID | Domain | Description | Criteria Ref | Covered By | Coverage Type | Status | Issue | Notes |
|---------|--------|-------------|-------------|------------|---------------|--------|-------|-------|
| EFF-01 | Performance | Efficiency >90% @1000W | §1.1 | `docs/FUNCTIONAL_TEST_PROCEDURE.md` Step 6 | hw-procedure | Covered | | Full-power HV validation |
| EFF-02 | Performance | Efficiency >92% @1800W | §1.1 | `docs/FUNCTIONAL_TEST_PROCEDURE.md` Step 6 | hw-procedure | Covered | | ZVS-active region only |
| EFF-03 | Performance | Standby <1.0W | §1.1 | No standby power test procedure exists | none | Gap | temper-thwr | Requires mains-connected off-state measurement |
| PWR-01 | Performance | 1000W ±10% | §1.2 | `docs/FUNCTIONAL_TEST_PROCEDURE.md` Step 6 | hw-procedure | Covered | | Verified at full-power HV |
| PWR-02 | Performance | 1800W ±5% | §1.2 | `docs/FUNCTIONAL_TEST_PROCEDURE.md` Step 6 | hw-procedure | Covered | | Verified at full-power HV |
| PID-01 | Performance | Accuracy ±2°C | §1.3 | `firmware/test/test_pid_control.c`, `firmware/test/test_main_pid.c` | unity-test | Covered | | Unity tests cover PID setpoint tracking |
| PID-02 | Performance | Stability ±1°C | §1.3 | `firmware/test/test_pid_control.c` | unity-test | Covered | | Unity tests cover steady-state deviation |
| PID-03 | Performance | Overshoot <5°C | §1.3 | `firmware/test/test_cascade_pid.c`, `firmware/test/test_main_cascade_pid.c` | unity-test | Covered | | Cascade PID tests cover step-response overshoot |
| PID-04 | Performance | Settling <5min | §1.3 | `firmware/test/test_pid_control.c` | unity-test | Covered | | Unity tests cover settling time bounds |
| OCP-01 | Protection | Primary OCP 45-55A, <1µs | §2.1 | `docs/FUNCTIONAL_TEST_PROCEDURE.md` Step 4 (I_SENSE injection); `simulation/testbenches/sim_17_ocp_protection.cir` | hw-procedure, simulation | Covered | | HW injection + SPICE simulation |
| OCP-02 | Protection | Secondary OCP 55-65A, <5µs | §2.1 | `docs/FUNCTIONAL_TEST_PROCEDURE.md` Step 4 | hw-procedure | Covered | | HW interlock verification |
| OVP-01 | Protection | DC Bus OVP 390-410V | §2.2 | `docs/FUNCTIONAL_TEST_PROCEDURE.md` Step 4 (V_BUS_SENSE injection); `simulation/testbenches/sim_18_ovp_protection.cir` | hw-procedure, simulation | Covered | | HW injection + SPICE simulation |
| THM-01 | Protection | Heatsink NTC 85°C shutdown | §2.3 | `docs/FUNCTIONAL_TEST_PROCEDURE.md` Step 4; `firmware/test/test_thermal_mass.c`; `simulation/testbenches/sim_31_coil_thermal.cir` | hw-procedure, unity-test, simulation | Covered | | Triple coverage: HW + firmware unit + thermal sim |
| THM-02 | Protection | Coil NTC 120°C shutdown | §2.3 | `docs/FUNCTIONAL_TEST_PROCEDURE.md` Step 4; `firmware/test/test_thermal_mass.c` | hw-procedure, unity-test | Covered | | HW + firmware unit test |
| UVL-01 | Protection | Gate Drive UVLO <12.0V | §2.4 | `docs/FUNCTIONAL_TEST_PROCEDURE.md` Step 2 (logic power validation covers 3.3V rail only; 15V rail UVLO not explicitly tested) | none | Gap | temper-yn4i | Gate drive UVLO requires dedicated 15V sag test. Logic rail (3.3V) UVLO is covered by Step 2. |
| UVL-02 | Protection | Logic UVLO <2.9V | §2.4 | `docs/FUNCTIONAL_TEST_PROCEDURE.md` Step 2 | hw-procedure | Covered | | Logic power validation covers 3.3V rail |
| EMC-01 | EMC | CISPR 14-1 Class B 150-500kHz | §3.1 | No EMC test procedure exists | none | Gap | temper-0045 | Requires pre-compliance conducted emissions test setup |
| EMC-02 | EMC | CISPR 14-1 Class B 0.5-5MHz | §3.1 | No EMC test procedure exists | none | Gap | temper-0045 | Same procedure as EMC-01 |
| EMC-03 | EMC | CISPR 14-1 Class B 5-30MHz | §3.1 | No EMC test procedure exists | none | Gap | temper-0045 | Same procedure as EMC-01 |
| MCH-01 | Mechanical | Button Force 2-5N | §4 | No mechanical test procedure exists | none | Gap | temper-drz8 | Requires force gauge fixture |
| MCH-02 | Mechanical | Knob Torque 0.5-2 N·cm | §4 | No mechanical test procedure exists | none | Gap | temper-drz8 | Requires torque gauge fixture |
| MCH-03 | Mechanical | Glass Load 20kg | §4 | No mechanical test procedure exists | none | Gap | temper-drz8 | Requires load test fixture |

## Gap Review Procedure

See `docs/PRE_FAB_SIGN_OFF.md` §3.1 for the per-fab-cycle gap review procedure.

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2026-06-22 | AI Agent | Initial traceability table created from `docs/FUNCTIONAL_TEST_CRITERIA.md` gates declared in `docs/STRATEGY.md` |
