# Temper Project Strategy

**Version:** 1.0  
**Date:** 2026-06-22

## Target Problem

The Temper is a consumer induction cooker. It must deliver safe, precise, and efficient cooking to end users while meeting regulatory requirements for electrical safety and electromagnetic compatibility.

## Approach

- **Firmware-first safety**: All protection circuits (OCP, OVP, thermal shutdown, UVLO) are hardware-latched with firmware monitoring. Software cannot override hardware protection.
- **Test-everything validation**: Every protection and performance gate listed below is tested via Unity test, hardware procedure, or simulation before fab sign-off. No gate ships without coverage or an acknowledged gap.

## Non-Negotiable Safety and Performance Gates

These gates must be verified before any PCB fabrication release. A traceability mapping of each gate to its test coverage is maintained in `docs/TRACEABILITY.md`.

### Performance Gates

| Gate ID | Description | Reference |
|---------|-------------|-----------|
| EFF-01 | Efficiency >90% @1000W | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.1 |
| EFF-02 | Efficiency >92% @1800W | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.1 |
| EFF-03 | Standby power <1.0W | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.1 |
| PWR-01 | Power accuracy ±10% @1000W | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.2 |
| PWR-02 | Power accuracy ±5% @1800W | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.2 |
| PID-01 | Temperature accuracy ±2°C | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.3 |
| PID-02 | Temperature stability ±1°C (30min) | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.3 |
| PID-03 | Overshoot <5°C | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.3 |
| PID-04 | Settling time <5min | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.3 |

### Protection Gates

| Gate ID | Description | Reference |
|---------|-------------|-----------|
| OCP-01 | Primary OCP 45-55A, <1µs | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.1 |
| OCP-02 | Secondary OCP 55-65A, <5µs | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.1 |
| OVP-01 | DC Bus OVP 390-410V | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.2 |
| THM-01 | Heatsink NTC 85°C shutdown | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.3 |
| THM-02 | Coil NTC 120°C shutdown | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.3 |
| UVL-01 | Gate Drive UVLO <12.0V | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.4 |
| UVL-02 | Logic UVLO <2.9V | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.4 |

### EMC Gates

| Gate ID | Description | Reference |
|---------|-------------|-----------|
| EMC-01 | CISPR 14-1 Class B 150-500kHz | `docs/FUNCTIONAL_TEST_CRITERIA.md` §3.1 |
| EMC-02 | CISPR 14-1 Class B 0.5-5MHz | `docs/FUNCTIONAL_TEST_CRITERIA.md` §3.1 |
| EMC-03 | CISPR 14-1 Class B 5-30MHz | `docs/FUNCTIONAL_TEST_CRITERIA.md` §3.1 |

### Mechanical Gates

| Gate ID | Description | Reference |
|---------|-------------|-----------|
| MCH-01 | Button Force 2-5N | `docs/FUNCTIONAL_TEST_CRITERIA.md` §4 |
| MCH-02 | Knob Torque 0.5-2 N·cm | `docs/FUNCTIONAL_TEST_CRITERIA.md` §4 |
| MCH-03 | Glass Load 20kg | `docs/FUNCTIONAL_TEST_CRITERIA.md` §4 |
